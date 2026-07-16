"""
Zone Controller skeleton.
Will eventually encapsulate the EKF and MPC for a specific zone.
"""
import numpy as np

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

        # Covariance Matrix P (scaled to state magnitudes)
        self.P = np.diag([
            1.0, 1.0, 1e-4, 100.0,   # T_in, T_m, W_in, C_in
            1.0, 1e-4, 1.0,          # d_T, d_W, N_occ
            10.0, 10.0,              # alpha_ext, alpha_int
            1e-12, 1e-14             # beta_air, beta_mass
        ])

        # Process Noise Covariance Q
        self.Q = np.diag([
            1e-7, 1e-4, 1e-7, 1e-7,  # Tier 1 & 3: T_in, T_m, W_in, C_in
            1e-2, 1e-2, 1e-2,        # Tier 2: Fast Disturbances (d_T, d_W, N_occ)
            1e-4, 1e-4,              # Tier 3: Slow Parameters (alpha_ext, alpha_int)
            1e-9, 1e-9               # Tier 4: Geologic (beta_air, beta_mass)
        ])
        
        # Measurement Noise Covariance R
        self.R = np.diag([0.01, 1e-8, 25.0])  # T_in, W_in, C_in

        # Measurement Matrix H (maps state to measurements: T_in, W_in, C_in)
        self.H = np.zeros((3, 11))
        self.H[0, 0] = 1.0
        self.H[1, 2] = 1.0
        self.H[2, 3] = 1.0

        # Physical Constants
        self.rho_air = 1.204
        self.c_p = 1006.0
        self.q_person = 100.0
        self.g_w_person = 5e-5
        self.g_co2_person = 3.82e-6 * 1e6
        
    def step(self, dt, state_data, logger):
        """
        Executes the zone-level control logic (EKF + MPC).
        
        :param dt: Time step in seconds.
        :param state_data: Dictionary containing current sensor/state readings for this zone.
        :param logger: The SimulationLogger instance to log internal variables.
        :return: A dictionary of ideal supply conditions and control commands.
        """
        # 1. Parse Inputs
        T_out = state_data.get('T_out', 22.0)
        T_s = state_data.get('T_s', 13.0)
        W_s = state_data.get('W_s', 0.008)
        C_s = state_data.get('C_s', 400.0)
        u_mass = state_data.get('VAV_Flow', 0.0)
        u = u_mass / self.rho_air  # Convert mass flow to volumetric flow

        # Measurements
        z = np.array([
            state_data.get('T_in', self.x[0]),
            state_data.get('W_in', self.x[2]),
            state_data.get('C_in', self.x[3])
        ])

        # 2 & 3 & 4 & 5. Sub-stepped Predict Phase
        n_steps = max(1, int(dt / 5.0))  # 5-second sub-steps for extreme stability
        dt_sub = dt / n_steps
        
        x_pred = self.x.copy()
        P_pred = self.P.copy()
        
        for _ in range(n_steps):
            x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11 = x_pred
            
            # Continuous state derivatives
            f_x = np.zeros(11)
            f_x[0] = x10 * (x8*(T_out - x1) + x9*(x2 - x1) + x7 * self.q_person + self.rho_air * self.c_p * u * (T_s - x1) + x5)
            f_x[1] = x11 * (x9*(x1 - x2))
            f_x[2] = x10 * self.c_p * (x7 * self.g_w_person + self.rho_air * u * (W_s - x3) + x6)
            f_x[3] = x10 * self.rho_air * self.c_p * (x7 * self.g_co2_person + u * (C_s - x4))
            
            # Jacobians
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
            
            # Ensure symmetry and positive semi-definiteness
            P_pred = (P_pred + P_pred.T) / 2.0
        
        # 6. EKF Update (Joseph Form for numerical stability)
        y_k = z - self.H @ x_pred
        S_k = self.H @ P_pred @ self.H.T + self.R
        
        # Pseudo-inverse or regular inverse with small damping
        try:
            S_inv = np.linalg.inv(S_k)
        except np.linalg.LinAlgError:
            S_inv = np.linalg.pinv(S_k + np.eye(3) * 1e-6)
            
        K_k = P_pred @ self.H.T @ S_inv
        
        self.x = x_pred + K_k @ y_k
        
        I_KH = np.eye(11) - K_k @ self.H
        self.P = I_KH @ P_pred @ I_KH.T + K_k @ self.R @ K_k.T
        self.P = (self.P + self.P.T) / 2.0
        
        # Physical parameter clipping to prevent divergence
        self.x[6] = max(0.0, self.x[6])                # Occupancy >= 0
        self.x[7] = np.clip(self.x[7], 1.0, 5000.0)    # alpha_ext
        self.x[8] = np.clip(self.x[8], 1.0, 5000.0)    # alpha_int
        self.x[9] = np.clip(self.x[9], 1e-7, 1e-4)     # beta_air
        self.x[10] = np.clip(self.x[10], 1e-9, 1e-5)   # beta_mass

        # 7. Logging State, Covariance and Gain
        state_names = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass"]
        for i, name in enumerate(state_names):
            logger.add(f"{self.zone_name}_EKF_x_{name}", self.x[i])
            logger.add(f"{self.zone_name}_EKF_P_{name}", self.P[i, i])
            
        logger.add(f"{self.zone_name}_EKF_K_T_in", K_k[0, 0])
        logger.add(f"{self.zone_name}_EKF_K_W_in", K_k[2, 1])
        logger.add(f"{self.zone_name}_EKF_K_C_in", K_k[3, 2])
        logger.add(f"{self.zone_name}_EKF_K_N_occ_from_C_in", K_k[6, 2])
        
        # Skeleton implementation. Log a dummy variable to demonstrate flexible logging.
        logger.add(f"{self.zone_name}_EKF_Status", 1)
        ideal_temp = 13.0
        ideal_hum = 0.008
        ideal_co2 = 400.0
        u_cmd = 0.5

        logger.add(f"{self.zone_name}_ideal_temp", ideal_temp)
        logger.add(f"{self.zone_name}_ideal_hum", ideal_hum)
        logger.add(f"{self.zone_name}_ideal_co2", ideal_co2)
        logger.add(f"{self.zone_name}_u_cmd", u_cmd)
        
        return {
            'ideal_temp': ideal_temp,
            'ideal_hum': ideal_hum,
            'ideal_co2': ideal_co2,
            'u_cmd': u_cmd
        }
