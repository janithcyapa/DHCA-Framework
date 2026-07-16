"""
Zone Controller.
Encapsulates the EKF and MPC for a specific zone.
"""
import numpy as np
import scipy.sparse as sparse
import osqp
import time

class ZoneController:
    def __init__(self, zone_name):
        self.zone_name = zone_name
        self.ready = False
        
        # --- EKF Initialization ---
        # State vector x: [T_in, T_m, W_in, C_in, d_T, d_W, N_occ, alpha_ext, alpha_int, beta_air, beta_mass]
        self.x = np.zeros(11)
        self.x[0] = 22.0    # x1: T_in (C)
        self.x[1] = 22.0    # x2: T_m (C)
        self.x[2] = 0.008   # x3: W_in (kg/kg)
        self.x[3] = 400.0   # x4: C_in (ppm)
        self.x[4] = 0.0     # x5: d_T
        self.x[5] = 0.0     # x6: d_W
        self.x[6] = 0.0     # x7: N_occ
        self.x[7] = 200.0   # x8: alpha_ext (typically 1/0.005)
        self.x[8] = 500.0   # x9: alpha_int (typically 1/0.002)
        self.x[9] = 3.3e-6  # x10: beta_air (typically 1/300000)
        self.x[10] = 1e-7   # x11: beta_mass (typically 1/10000000)

        # Covariance Matrix P
        self.P = np.diag([1.0, 1.0, 1e-4, 100.0, 1.0, 1e-4, 1.0, 10.0, 10.0, 1e-12, 1e-14])
        # Process Noise Covariance Q
        self.Q = np.diag([1e-7, 1e-4, 1e-7, 1e-7, 1e-2, 1e-2, 0.1, 1e-4, 1e-4, 1e-9, 1e-9])
        # Measurement Noise Covariance R
        self.R = np.diag([0.01, 1e-8, 10.0])
        
        self.H = np.zeros((3, 11))
        self.H[0, 0] = 1.0
        self.H[1, 2] = 1.0
        self.H[2, 3] = 1.0

        self.rho_air = 1.204
        self.c_p = 1006.0
        self.q_person = 100.0
        self.g_w_person = 5e-5
        self.g_co2_person = 3.82e-6 * 1e6
        
        # --- MPC Initialization ---
        self.N = 10
        self.u_prev = 0.0 # u_{-1}
        
        # Deadband Limits
        self.T_ref = 22.0
        self.T_max = self.T_ref + 2.0
        self.T_min = self.T_ref - 2.0
        self.W_max = 0.0080  # Reduced to control humidity better
        self.W_min = 0.0020  # Reduced to match typical lower limits
        self.C_max = 1000.0
        self.u_min = 0.0
        self.u_max = 2.0  # Max volumetric flow rate m3/s
        
        # Objective Weights
        self.r = 1.0           # Flow penalty
        self.r_delta = 10.0    # Rate of change penalty
        self.lambda_T = 1e3    # Reduced soft constraint penalty for Temp
        self.lambda_W = 1e3    # Reduced soft constraint penalty for Humidity
        self.lambda_C = 1e3    # Reduced soft constraint penalty for CO2
        
        self.setup_mpc_constants()
        
    def setup_mpc_constants(self):
        N = self.N
        
        D = np.zeros((N, N))
        np.fill_diagonal(D, 1.0)
        for i in range(1, N):
            D[i, i-1] = -1.0
        self.D = D
        
        E = np.zeros(N)
        E[0] = 1.0
        self.E = E
        
        R_mat = np.eye(N) * self.r
        R_delta_mat = np.eye(N) * self.r_delta
        
        H_U = 2 * (R_mat + self.D.T @ R_delta_mat @ self.D)
        H_eps_T = 2 * np.eye(N) * self.lambda_T
        H_eps_W = 2 * np.eye(N) * self.lambda_W
        H_eps_C = 2 * np.eye(N) * self.lambda_C
        
        H = np.zeros((4*N, 4*N))
        H[0:N, 0:N] = H_U
        H[N:2*N, N:2*N] = H_eps_T
        H[2*N:3*N, 2*N:3*N] = H_eps_W
        H[3*N:4*N, 3*N:4*N] = H_eps_C
        self.H_sparse = sparse.csc_matrix(H)
        
        self.I_N = np.eye(N)
        self.O_N = np.zeros((N, N))
        self.zeros_N = np.zeros(N)
        
        self.ST = np.zeros((N, 4*N))
        self.SW = np.zeros((N, 4*N))
        self.SC = np.zeros((N, 4*N))
        for i in range(N):
            self.ST[i, i*4 + 0] = 1.0
            self.SW[i, i*4 + 2] = 1.0
            self.SC[i, i*4 + 3] = 1.0

    def step(self, dt, state_data, logger):
        print(f"[{self.zone_name}] Starting step with dt={dt}")
        start_time = time.perf_counter()
        
        T_out = state_data.get('T_out', 22.0)
        T_s = state_data.get('T_s', 13.0)
        W_s = state_data.get('W_s', 0.008)
        C_s = state_data.get('C_s', 400.0)
        u_mass = state_data.get('VAV_Flow', 0.0)
        u = u_mass / self.rho_air

        z = np.array([
            state_data.get('T_in', self.x[0]),
            state_data.get('W_in', self.x[2]),
            state_data.get('C_in', self.x[3])
        ])

        # --- EKF Predict Phase ---
        n_steps = max(1, int(dt / 5.0))
        dt_sub = dt / n_steps
        try:
                    x_pred = self.x.copy()
                    P_pred = self.P.copy()
                    
                    for _ in range(n_steps):
                        x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11 = x_pred
                        f_x = np.zeros(11)
                        f_x[0] = x10 * (x8*(T_out - x1) + x9*(x2 - x1) + x7 * self.q_person + self.rho_air * self.c_p * u * (T_s - x1) + x5)
                        f_x[1] = x11 * (x9*(x1 - x2))
                        f_x[2] = x10 * self.c_p * (x7 * self.g_w_person + self.rho_air * u * (W_s - x3) + x6)
                        f_x[3] = x10 * self.rho_air * self.c_p * (x7 * self.g_co2_person + u * (C_s - x4))
                        
                        F = np.zeros((11, 11))
                        F[0, 0] = x10 * (-x8 - x9 - self.rho_air * self.c_p * u)
                        F[0, 1] = x10 * x9
                        F[0, 4] = x10
                        F[0, 6] = x10 * self.q_person
                        F[0, 7] = x10 * (T_out - x1)
                        F[0, 8] = x10 * (x2 - x1)
                        F[0, 9] = x8 * (T_out - x1) + x9 * (x2 - x1) + x7 * self.q_person + self.rho_air * self.c_p * u * (T_s - x1) + x5
                        F[1, 0] = x11 * x9
                        F[1, 1] = -x11 * x9
                        F[1, 8] = x11 * (x1 - x2)
                        F[1, 10] = x9 * (x1 - x2)
                        F[2, 2] = -x10 * self.c_p * self.rho_air * u
                        F[2, 5] = x10 * self.c_p
                        F[2, 6] = x10 * self.c_p * self.g_w_person
                        F[2, 9] = self.c_p * (x7 * self.g_w_person + self.rho_air * u * (W_s - x3) + x6)
                        F[3, 3] = -x10 * self.rho_air * self.c_p * u
                        F[3, 6] = x10 * self.rho_air * self.c_p * self.g_co2_person
                        F[3, 9] = self.rho_air * self.c_p * (x7 * self.g_co2_person + u * (C_s - x4))
                        
                        Phi = np.eye(11) + F * dt_sub
                        x_pred = x_pred + f_x * dt_sub
                        P_pred = Phi @ P_pred @ Phi.T + self.Q * (dt_sub / dt)
                        P_pred = (P_pred + P_pred.T) / 2.0
                    
                    # --- EKF Update ---
                    y_k = z - self.H @ x_pred
                    S_k = self.H @ P_pred @ self.H.T + self.R
                    try:
                        S_inv = np.linalg.inv(S_k)
                    except np.linalg.LinAlgError:
                        S_inv = np.linalg.pinv(S_k + np.eye(3) * 1e-6)
                    K_k = P_pred @ self.H.T @ S_inv
                    
                    self.x = x_pred + K_k @ y_k
                    I_KH = np.eye(11) - K_k @ self.H
                    self.P = I_KH @ P_pred @ I_KH.T + K_k @ self.R @ K_k.T
                    self.P = (self.P + self.P.T) / 2.0
                    
                    self.x[6] = max(0.0, self.x[6])
                    self.x[7] = np.clip(self.x[7], 1.0, 5000.0)
                    self.x[8] = np.clip(self.x[8], 1.0, 5000.0)
                    self.x[9] = np.clip(self.x[9], 1e-7, 1e-4)
                    self.x[10] = np.clip(self.x[10], 1e-9, 1e-5)
            
                    # --- MPC Formulation ---
                    # print(f"[{self.zone_name}] Starting MPC formulation")
                    # 1. Linearization around x_0 (from updated EKF state) and u_{-1}
                    x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11 = self.x
                    T_in, T_m, W_in, C_in = x1, x2, x3, x4
                    u0 = self.u_prev
                    
                    f_x = np.zeros(4)
                    f_x[0] = x10 * (x8*(T_out - T_in) + x9*(T_m - T_in) + x7 * self.q_person + self.rho_air * self.c_p * u0 * (T_s - T_in) + x5)
                    f_x[1] = x11 * (x9*(T_in - T_m))
                    f_x[2] = x10 * self.c_p * (x7 * self.g_w_person + self.rho_air * u0 * (W_s - W_in) + x6)
                    f_x[3] = x10 * self.rho_air * self.c_p * (x7 * self.g_co2_person + u0 * (C_s - C_in))
                    
                    Ac = np.zeros((4, 4))
                    Ac[0, 0] = x10 * (-x8 - x9 - self.rho_air * self.c_p * u0)
                    Ac[0, 1] = x10 * x9
                    Ac[1, 0] = x11 * x9
                    Ac[1, 1] = -x11 * x9
                    Ac[2, 2] = -x10 * self.c_p * self.rho_air * u0
                    Ac[3, 3] = -x10 * self.rho_air * self.c_p * u0
                    
                    Bc = np.zeros((4, 1))
                    Bc[0, 0] = x10 * self.rho_air * self.c_p * (T_s - T_in)
                    Bc[1, 0] = 0.0
                    Bc[2, 0] = x10 * self.c_p * self.rho_air * (W_s - W_in)
                    Bc[3, 0] = x10 * self.rho_air * self.c_p * (C_s - C_in)
                    
                    x_0_mpc = np.array([T_in, T_m, W_in, C_in])
                    cc = f_x - Ac @ x_0_mpc - Bc.flatten() * u0
                    
                    Ad = np.eye(4) + Ac * dt
                    Bd = Bc * dt
                    cd = cc * dt
                    
                    # 2. Prediction Matrices
                    N = self.N
                    Psi = np.zeros((4*N, 4))
                    Theta = np.zeros((4*N, N))
                    Phi = np.zeros((4*N, 4))
                    
                    A_pows = [np.eye(4)]
                    for i in range(1, N + 1):
                        A_pows.append(A_pows[-1] @ Ad)
                        
                    sum_A = np.zeros((4, 4))
                    for i in range(N):
                        Psi[i*4:(i+1)*4, :] = A_pows[i+1]
                        sum_A = sum_A + A_pows[i]
                        Phi[i*4:(i+1)*4, :] = sum_A
                        for j in range(i + 1):
                            Theta[i*4:(i+1)*4, j:j+1] = A_pows[i - j] @ Bd
                            
                    FT = self.ST @ Theta
                    gT = self.ST @ (Psi @ x_0_mpc + Phi @ cd)
                    
                    FW = self.SW @ Theta
                    gW = self.SW @ (Psi @ x_0_mpc + Phi @ cd)
                    
                    FC = self.SC @ Theta
                    gC = self.SC @ (Psi @ x_0_mpc + Phi @ cd)
                    
                    # 3. Assemble QP
                    f_U = -2 * self.r_delta * self.D.T @ self.E * self.u_prev
                    f = np.concatenate([f_U, self.zeros_N, self.zeros_N, self.zeros_N])
                    
                    A_ineq = np.block([
                        [FT, -self.I_N, self.O_N, self.O_N],
                        [-FT, -self.I_N, self.O_N, self.O_N],
                        [FW, self.O_N, -self.I_N, self.O_N],
                        [-FW, self.O_N, -self.I_N, self.O_N],
                        [FC, self.O_N, self.O_N, -self.I_N],
                        [self.O_N, -self.I_N, self.O_N, self.O_N],
                        [self.O_N, self.O_N, -self.I_N, self.O_N],
                        [self.O_N, self.O_N, self.O_N, -self.I_N],
                        [self.I_N, self.O_N, self.O_N, self.O_N],
                        [-self.I_N, self.O_N, self.O_N, self.O_N]
                    ])
                    
                    b_ineq = np.concatenate([
                        np.ones(N) * self.T_max - gT,
                        -np.ones(N) * self.T_min + gT,
                        np.ones(N) * self.W_max - gW,
                        -np.ones(N) * self.W_min + gW,
                        np.ones(N) * self.C_max - gC,
                        self.zeros_N,
                        self.zeros_N,
                        self.zeros_N,
                        np.ones(N) * self.u_max,
                        -np.ones(N) * self.u_min
                    ])
                    
                    A_sparse = sparse.csc_matrix(A_ineq)
                    
                    # print(f"[{self.zone_name}] Setting up OSQP solver")
                    solver = osqp.OSQP()
                    solver.setup(P=self.H_sparse, q=f, A=A_sparse, l=-np.inf*np.ones_like(b_ineq), u=b_ineq, verbose=False, max_iter=50000, eps_abs=1e-4, eps_rel=1e-4)
                    # print(f"[{self.zone_name}] Solving OSQP")
                    res = solver.solve()
                    print(f"[{self.zone_name}] OSQP solved, status={res.info.status_val}")
                    
                    if res.info.status_val in [1, 2]: # 1: SOLVED, 2: SOLVED_INACCURATE
                        u_cmd = res.x[0]
                        self.u_prev = u_cmd
                    else:
                        u_cmd = self.u_prev
                    
                    u_mass_cmd = u_cmd * self.rho_air
                    
                    # --- Logging ---
                    exec_time_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.add(f"{self.zone_name}_MPC_Time_ms", exec_time_ms)
                    logger.add(f"{self.zone_name}_MPC_Status", res.info.status_val)
                    
                    state_names = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass"]
                    for i, name in enumerate(state_names):
                        logger.add(f"{self.zone_name}_EKF_x_{name}", self.x[i])
                        logger.add(f"{self.zone_name}_EKF_P_{name}", self.P[i, i])
                        
                    logger.add(f"{self.zone_name}_EKF_K_T_in", K_k[0, 0])
                    logger.add(f"{self.zone_name}_EKF_K_W_in", K_k[2, 1])
                    logger.add(f"{self.zone_name}_EKF_K_C_in", K_k[3, 2])
                    logger.add(f"{self.zone_name}_EKF_K_N_occ_from_C_in", K_k[6, 2])
                    
                    ideal_hum = (self.W_max + self.W_min) / 2.0
                    logger.add(f"{self.zone_name}_ideal_temp", self.T_ref)
                    logger.add(f"{self.zone_name}_ideal_hum", ideal_hum)
                    logger.add(f"{self.zone_name}_ideal_co2", 400.0)
                    logger.add(f"{self.zone_name}_u_cmd", u_mass_cmd)
                    
                    return {
                        'ideal_temp': self.T_ref,
                        'ideal_hum': ideal_hum,
                        'ideal_co2': 400.0,
                        'u_cmd': u_mass_cmd
                    }
        except Exception as e:
            import traceback
            print(f'Exception in ZoneController.step for {self.zone_name}: {e}')
            traceback.print_exc()
            raise e
