"""
Zone Controller.
Encapsulates the EKF and MPC for a specific zone.
"""
import numpy as np
import scipy.sparse as sparse
import osqp
import time
import math


def w_sat(T_C, P_atm=101325.0):
    """
    Saturation humidity ratio (kg/kg dry air) at a given dry-bulb/dew-point
    temperature T_C, via the inverse of the Magnus formula used elsewhere
    in this codebase (see AHUCoordinator.T_sat). This is the coldest/driest
    air a coil can produce at temperature T_C -- the true physical floor
    for dehumidification WITHOUT reheat.
    """
    gamma = 17.625 * T_C / (243.04 + T_C)
    P_w = 610.94 * math.exp(gamma)
    return 0.62198 * P_w / (P_atm - P_w)


class ZoneController:
    def __init__(self, zone_name):
        self.zone_name = zone_name
        self.ready = False
        
        # --- EKF Initialization ---
        # State vector x: [T_in, T_m, W_in, C_in, d_T, d_W, N_occ, alpha_ext, alpha_int, beta_air, beta_mass]
        self.x = np.zeros(11)
        
        # --- Physical States ---
        # Initialize at typical comfortable ambient conditions
        self.x[0] = 22.0    # x1: T_in (C) - Typical room temperature (71.6 F)
        self.x[1] = 22.0    # x2: T_m (C) - Assume walls/furniture are in thermal equilibrium with the air
        self.x[2] = 0.008   # x3: W_in (kg/kg) - Roughly 50% Relative Humidity at 22C
        self.x[3] = 400.0   # x4: C_in (ppm) - Standard outdoor baseline CO2 concentration
        
        # --- Disturbances ---
        # Let the EKF discover these; it is safe to start them at 0
        self.x[4] = 0.0     # x5: d_T - Unmodeled sensible heat
        self.x[5] = 0.0     # x6: d_W - Unmodeled latent heat/moisture
        self.x[6] = 0.0     # x7: N_occ - Assume the room starts empty
        
        # --- Structural Parameters ---
        # These are the inverses of Resistance (R) and Capacitance (C). 
        # Using the standard values suggested in your comments.
        self.x[7] = 200.0   # x8: alpha_ext (1/R_ext) - e.g., 1 / 0.005. Moderate envelope conductance.
        self.x[8] = 500.0   # x9: alpha_int (1/R_int) - e.g., 1 / 0.002. Good thermal linkage between air and mass.
        self.x[9] = 3.3e-6  # x10: beta_air (1/C_air) - ~1/300,000. Typical air volume heat capacity.
        self.x[10] = 1e-7   # x11: beta_mass (1/C_mass) - 1/10,000,000. Heavy thermal mass (concrete/furniture).


        # Covariance Matrix P
        self.P = np.diag([1.0, 1.0, 1e-4, 100.0, 1.0, 1e-4, 1.0, 10000.0, 10000.0, 1e-12, 1e-14])
        # Process Noise Covariance Q
        self.Q = np.diag([1e-7, 1e-4, 1e-7, 1e-7, 1e-2, 1e-2, 0.1, 10, 10, 1e-9, 1e-9])
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
        self.N = 20
        
        # Objective Weights — Priority: Temperature >> Humidity >> CO2
        self.r = 0.001
        self.r_delta = 15.0        # was 1e10 — this is what was breaking everything
        self.lambda_T = 1e4       # was 1e5
        self.lambda_W = 1e3       # was 1e-5
        self.lambda_C = 1e1       # was 1e-5
        self.mu_T = 1e4           # was 1e10 — see below for why

        self.du_max = 0.05

        self.max_iter=10000
        self.eps_abs=1e-4
        self.eps_rel=1e-4




        self.u_prev = 0.5  # Start at a moderate flow, not 0 — avoids stuck-at-zero fallback
        
        T_in = self.x[0] 
        rh_min = 0.30
        rh_max = 0.60
        def get_w_from_rh(T, rh):
            p_sat = 610.94 * math.exp(17.625 * T / (243.04 + T))
            p_vapor = rh * p_sat
            return 0.62198 * p_vapor / (101325.0 - p_vapor)

        # Deadband Limits
        self.T_ref = 22.0
        self.T_delta = 1.0
        self.T_max = self.T_ref + self.T_delta
        self.T_min = self.T_ref -self.T_delta
        # self.W_max = 0.0100  # ~60% RH at 22C — relaxed upper limit for feasibility
        # self.W_min = 0.0050  # ~30% RH at 22C — physically achievable lower limit
        self.W_min = get_w_from_rh(T_in, rh_min)
        self.W_max = get_w_from_rh(T_in, rh_max)

        self.C_max = 1000.0
        self.u_min = 0.0
        self.u_max = 2.0  # Max volumetric flow rate m3/s

        self.T_s_min = 10.0
        self.T_s_max = 40.0
        self.W_s_min = w_sat(self.T_s_min) 
        self.W_s_max = 0.015
        

        
        self.setup_mpc_constants()
        
    def setup_mpc_constants(self):
        N = self.N
        
        # Differencing matrix for rate-of-change penalty
        D = np.zeros((N, N))
        np.fill_diagonal(D, 1.0)
        for i in range(1, N):
            D[i, i-1] = -1.0
        self.D = D
        
        E = np.zeros(N)
        E[0] = 1.0
        self.E = E
        
        self.I_N = np.eye(N)
        self.O_N = np.zeros((N, N))
        self.zeros_N = np.zeros(N)
        
        # Selection matrices to extract T, W, C from stacked state predictions
        self.ST = np.zeros((N, 4*N))
        self.SW = np.zeros((N, 4*N))
        self.SC = np.zeros((N, 4*N))
        for i in range(N):
            self.ST[i, i*4 + 0] = 1.0
            self.SW[i, i*4 + 2] = 1.0
            self.SC[i, i*4 + 3] = 1.0

    def _build_hessian(self, N):
        """Build QP Hessian with regularization for guaranteed positive-definiteness."""
        R_mat = np.eye(N) * self.r
        R_delta_mat = np.eye(N) * self.r_delta
        
        H_U = 2.0 * (R_mat + self.D.T @ R_delta_mat @ self.D)
        H_eps_T = 2.0 * np.eye(N) * self.lambda_T
        H_eps_W = 2.0 * np.eye(N) * self.lambda_W
        H_eps_C = 2.0 * np.eye(N) * self.lambda_C
        
        n_vars = 4 * N
        H = np.zeros((n_vars, n_vars))
        H[0:N, 0:N] = H_U
        H[N:2*N, N:2*N] = H_eps_T
        H[2*N:3*N, 2*N:3*N] = H_eps_W
        H[3*N:4*N, 3*N:4*N] = H_eps_C
        
        # Regularization: ensure strict positive-definiteness to prevent OSQP Status 7
        H += np.eye(n_vars) * 1e-6
        
        return sparse.csc_matrix(H)

    def _fallback_control(self, state_data):
        """
        Proportional fallback controller when MPC fails to solve.
        Uses simple error-based logic rather than just returning u_prev.
        """
        T_in = state_data.get('T_in', self.x[0])
        W_in = state_data.get('W_in', self.x[2])
        C_in = state_data.get('C_in', self.x[3])
        T_s = state_data.get('T_s', 13.0)
        
        # Temperature error: positive means zone is too hot, needs more cooling flow
        e_T = T_in - self.T_ref
        
        # CO2 error: positive means zone has too much CO2, needs more fresh air
        e_C = max(0.0, C_in - self.C_max) / self.C_max
        
        # Humidity error: positive means too humid
        W_ref = (self.W_max + self.W_min) / 2.0
        e_W = max(0.0, W_in - self.W_max) / self.W_max
        
        # If zone is colder than supply air, reduce flow (don't pump cold air into cold zone)
        if T_in < T_s + 1.0:
            # Zone is cold enough — minimal flow for ventilation only
            u_fb = 0.1
        elif e_T > 0.5:
            # Zone is too hot — increase flow proportionally
            u_fb = min(self.u_max, 0.3 + e_T * 0.3)
        elif e_T < -0.5:
            # Zone is too cold — reduce flow
            u_fb = 0.1
        else:
            # In deadband — moderate flow for ventilation + humidity/CO2
            u_fb = 0.2 + e_C * 0.5 + e_W * 0.3
        
        u_fb = np.clip(u_fb, self.u_min, self.u_max)
        u_fb = np.clip(u_fb, self.u_prev - self.du_max, self.u_prev + self.du_max)  # NEW
        return u_fb

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

                    # Calculate Normalized Innovation Squared (NIS)
                    # This condenses multi-dimensional residual checks into a single metric
                    self.NIS = float(y_k.T @ S_inv @ y_k)
                    
                    self.x[6] = max(0.0, self.x[6])
                    self.x[7] = np.clip(self.x[7], 1.0, 5000.0)
                    self.x[8] = np.clip(self.x[8], 1.0, 5000.0)
                    self.x[9] = np.clip(self.x[9], 1e-7, 1e-4)
                    self.x[10] = np.clip(self.x[10], 1e-9, 1e-5)
            
                    # --- MPC Formulation ---
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
                    Phi_pred = np.zeros((4*N, 4))
                    
                    A_pows = [np.eye(4)]
                    for i in range(1, N + 1):
                        A_pows.append(A_pows[-1] @ Ad)
                        
                    sum_A = np.zeros((4, 4))
                    for i in range(N):
                        Psi[i*4:(i+1)*4, :] = A_pows[i+1]
                        sum_A = sum_A + A_pows[i]
                        Phi_pred[i*4:(i+1)*4, :] = sum_A
                        for j in range(i + 1):
                            Theta[i*4:(i+1)*4, j:j+1] = A_pows[i - j] @ Bd
                            
                    FT = self.ST @ Theta
                    gT = self.ST @ (Psi @ x_0_mpc + Phi_pred @ cd)
                    
                    FW = self.SW @ Theta
                    gW = self.SW @ (Psi @ x_0_mpc + Phi_pred @ cd)
                    
                    FC = self.SC @ Theta
                    gC = self.SC @ (Psi @ x_0_mpc + Phi_pred @ cd)
                    
                    # 3. Assemble QP using OSQP's native two-sided constraint format
                    #    Decision variables: z = [u(N), eps_T(N), eps_W(N), eps_C(N)]
                    #    Proper two-sided: l <= A_con @ z <= u_con
                    
                    # Build regularized Hessian
                    H_sparse = self._build_hessian(N)
                    
                    # Linear cost
                    f_U = -2.0 * self.r_delta * self.D.T @ self.E * self.u_prev

                    # NEW
                    f_eps_T = np.ones(N) * self.mu_T
                    f = np.concatenate([f_U, f_eps_T, self.zeros_N, self.zeros_N])
                    
                    # f = np.concatenate([f_U, self.zeros_N, self.zeros_N, self.zeros_N])
                    
                    # --- Constraint assembly (two-sided format) ---
                    
                    A_con = np.block([
                        # Temp soft constraints (upper, then lower)
                        [FT, -self.I_N, self.O_N, self.O_N],
                        [-FT, -self.I_N, self.O_N, self.O_N],
                        # Humidity soft constraints (upper, then lower)
                        [FW, self.O_N, -self.I_N, self.O_N],
                        [-FW, self.O_N, -self.I_N, self.O_N],
                        # CO2 soft constraint (upper only)
                        [FC, self.O_N, self.O_N, -self.I_N],
                        # Slack non-negativity: eps_T >= 0
                        [self.O_N, self.I_N, self.O_N, self.O_N],
                        # Slack non-negativity: eps_W >= 0
                        [self.O_N, self.O_N, self.I_N, self.O_N],
                        # Slack non-negativity: eps_C >= 0
                        [self.O_N, self.O_N, self.O_N, self.I_N],
                        # Input bounds
                        [self.I_N, self.O_N, self.O_N, self.O_N],
                        # NEW: rate constraint on u
                        [self.D, self.O_N, self.O_N, self.O_N],   
                    ])

                    n_con = 10 * N
                    l_con = np.zeros(n_con)
                    u_con = np.zeros(n_con)

                    # Block 1: FT@u - eps_T <= T_max - gT
                    l_con[0:N] = -np.inf
                    u_con[0:N] = np.ones(N) * self.T_max - gT

                    # Block 2: -FT@u - eps_T <= -T_min + gT
                    l_con[N:2*N] = -np.inf
                    u_con[N:2*N] = -np.ones(N) * self.T_min + gT

                    # Block 3: FW@u - eps_W <= W_max - gW
                    l_con[2*N:3*N] = -np.inf
                    u_con[2*N:3*N] = np.ones(N) * self.W_max - gW

                    # Block 4: -FW@u - eps_W <= -W_min + gW
                    l_con[3*N:4*N] = -np.inf
                    u_con[3*N:4*N] = -np.ones(N) * self.W_min + gW

                    # Block 5: FC@u - eps_C <= C_max - gC
                    l_con[4*N:5*N] = -np.inf
                    u_con[4*N:5*N] = np.ones(N) * self.C_max - gC

                    # Block 6-8: 0 <= eps <= inf
                    l_con[5*N:8*N] = 0.0
                    u_con[5*N:8*N] = np.inf

                    # Block 9: u_min <= u <= u_max
                    l_con[8*N:9*N] = np.ones(N) * self.u_min
                    u_con[8*N:9*N] = np.ones(N) * self.u_max

                    l_con[9*N:10*N] = -self.du_max * np.ones(N) + self.E * self.u_prev
                    u_con[9*N:10*N] =  self.du_max * np.ones(N) + self.E * self.u_prev

                    A_sparse = sparse.csc_matrix(A_con)
                    
                    solver = osqp.OSQP()
                    solver.setup(
                        P=H_sparse, q=f, A=A_sparse, l=l_con, u=u_con,
                        verbose=False,
                        max_iter=self.max_iter,
                        eps_abs=self.eps_abs,
                        eps_rel=self.eps_rel,
                        polish=True,
                        adaptive_rho=True,
                    )
                    res = solver.solve()
                    mpc_status = res.info.status_val
                    print(f"[{self.zone_name}] OSQP solved, status={mpc_status}")
                    
                    if mpc_status in [1, 2]:  # 1: SOLVED, 2: SOLVED_INACCURATE
                        u_cmd = np.clip(res.x[0], self.u_min, self.u_max)
                        self.u_prev = u_cmd
                    else:
                        # Proportional fallback instead of blindly using u_prev
                        u_cmd = self._fallback_control(state_data)
                        self.u_prev = u_cmd
                        print(f"[{self.zone_name}] MPC failed (status={mpc_status}), fallback u={u_cmd:.3f}")
                    
                    u_mass_cmd = u_cmd * self.rho_air
                    
                    # --- Logging ---
                    exec_time_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.add(f"{self.zone_name}_MPC_Time_ms", exec_time_ms)
                    logger.add(f"{self.zone_name}_MPC_Status", mpc_status)
                    
                    
                    state_names = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass"]
                    for i, name in enumerate(state_names):
                        logger.add(f"{self.zone_name}_EKF_x_{name}", self.x[i])
                        logger.add(f"{self.zone_name}_EKF_P_{name}", self.P[i, i])
                        
                    # 2. Log EKF Health Diagnostics
                    # Innovation/Residuals (Expected to be zero-mean white noise)
                    logger.add(f"{self.zone_name}_EKF_y_T_in", y_k[0])
                    logger.add(f"{self.zone_name}_EKF_y_W_in", y_k[1])
                    logger.add(f"{self.zone_name}_EKF_y_C_in", y_k[2])
                    
                    # NIS (For 3 measurements, 95% of samples should fall between 0.216 and 7.815)
                    logger.add(f"{self.zone_name}_EKF_NIS", self.NIS)
                    
                    # Trace of P (Expected to drop initially and then stabilize)
                    logger.add(f"{self.zone_name}_EKF_P_trace", float(np.trace(self.P)))
                    
                    # 3. Log Critical Kalman Gains
                    logger.add(f"{self.zone_name}_EKF_K_T_in", K_k[0, 0])
                    logger.add(f"{self.zone_name}_EKF_K_W_in", K_k[2, 1])
                    logger.add(f"{self.zone_name}_EKF_K_C_in", K_k[3, 2])
                    logger.add(f"{self.zone_name}_EKF_K_N_occ_from_C_in", K_k[6, 2])
                    
                    # --- Ideal Ask Logic ---
                    T_in, T_m, W_in, C_in = self.x[0], self.x[1], self.x[2], self.x[3]
                    
                    # Target values
                    T_ref = self.T_ref
                    W_ref = (self.W_max + self.W_min) / 2.0
                    C_limit = self.C_max
                    
                    # Correction vector e
                    e_T = T_ref - T_in
                    e_W = W_ref - W_in
                    e_C = min(0.0, C_limit - C_in)
                    
                    # AHU Physical limits (see FIX note on self.W_s_min in __init__)
                    T_s_min = self.T_s_min
                    T_s_max = self.T_s_max
                    T_neutral = T_in
                    
                    W_s_min = self.W_s_min
                    W_s_max = self.W_s_max
                    W_neutral = W_in
                    
                    C_s_min = 400.0
                    C_recirc = C_in
                    
                    # Proportional Ideal Ask (replaces bang-bang for better coordination)
                    if e_T > 0.5:
                        T_s_star = T_s_max
                    elif e_T > 0.1:
                        # Proportional range: interpolate between neutral and max
                        alpha = (e_T - 0.1) / 0.4
                        T_s_star = T_neutral + alpha * (T_s_max - T_neutral)
                    elif e_T < -0.5:
                        T_s_star = T_s_min
                    elif e_T < -0.1:
                        alpha = (-e_T - 0.1) / 0.4
                        T_s_star = T_neutral - alpha * (T_neutral - T_s_min)
                    else:
                        T_s_star = T_neutral
                        
                    if e_W > 0.001:
                        W_s_star = W_s_min
                    elif e_W > 0.0005:
                        alpha = (e_W - 0.0005) / 0.0005
                        W_s_star = W_neutral - alpha * (W_neutral - W_s_min)
                    elif e_W < -0.001:
                        W_s_star = W_s_max
                    elif e_W < -0.0005:
                        alpha = (-e_W - 0.0005) / 0.0005
                        W_s_star = W_neutral + alpha * (W_s_max - W_neutral)
                    else:
                        W_s_star = W_neutral
                        
                    if not hasattr(self, 'prev_C_in'):
                        self.prev_C_in = C_in
                    dC_in = C_in - self.prev_C_in
                    self.prev_C_in = C_in
                    
                    if dC_in > 1.0:
                        C_s_star = max(400.0, C_in - 50.0)
                    else:
                        C_s_star = self.C_max
                        
                    saturation_index = u_cmd / self.u_max

                    logger.add(f"{self.zone_name}_ideal_temp", T_s_star)
                    logger.add(f"{self.zone_name}_ideal_hum", W_s_star)
                    logger.add(f"{self.zone_name}_ideal_co2", C_s_star)
                    logger.add(f"{self.zone_name}_u_cmd", u_mass_cmd)
                    logger.add(f"{self.zone_name}_saturation_index", saturation_index)
                    
                    return {
                        'ideal_temp': T_s_star,
                        'ideal_hum': W_s_star,
                        'ideal_co2': C_s_star,
                        'u_cmd': u_mass_cmd,
                        'saturation_index': saturation_index
                    }
        except Exception as e:
            import traceback
            print(f'Exception in ZoneController.step for {self.zone_name}: {e}')
            traceback.print_exc()
            raise e
