"""
Extended Kalman Filter — Zone State Estimator
==============================================
7-state augmented EKF that tracks the physical zone state plus
unmodelled disturbances and occupancy.

State vector (7):
    [T_in, T_m, W_in, C_in, δT, δW, N_occ]
      0     1     2     3    4   5    6

Measurement vector (3):
    [T_in_meas, W_in_meas, C_in_meas]

Uses the same RC dynamics as the theoretical zone model,
but applies Kalman correction from sensor feedback.
"""
import numpy as np

# ── Physical Constants ───────────────────────────────────────────────────
RHO_AIR   = 1.204
CP_AIR    = 1006.0
Q_PERSON  = 100.0
G_W_OCC   = 5e-5
G_CO2_OCC = 3.82e-6        # kg_co2/s per occupant (volumetric equivalent)


class ZoneEKF:
    """7-state Extended Kalman Filter for a single thermal zone."""

    def __init__(self, zone_name):
        self.zone_name = zone_name
        self.x = None                           # (7,) state vector
        self.P = np.eye(7)                      # covariance
        self.P[6, 6] = 10.0                     # higher initial uncertainty on occupancy

        # Tuning matrices
        self.Q = np.diag([0.1, 5.0, 1e-6, 1.0, 50.0, 1e-5, 10.0])    # process noise
        self.R = np.diag([0.01, 1e-8, 25.0])                          # measurement noise

        # Observation matrix  H ∈ ℝ^{3×7}
        self.H = np.zeros((3, 7))
        self.H[0, 0] = 1.0   # observe T_in
        self.H[1, 2] = 1.0   # observe W_in
        self.H[2, 3] = 1.0   # observe C_in

    # ── Initialise from first measurement ────────────────────────────────
    def initialise(self, T_in_0, W_in_0, C_in_0):
        self.x = np.array([T_in_0, T_in_0, W_in_0, C_in_0, 0.0, 0.0, 0.0])

    # ── Predict + Update ─────────────────────────────────────────────────
    def step(self, dt, params, z_meas, V_dot_s, Q_equip, T_s, W_s, C_s, T_out, adj_data):
        """
        Parameters
        ----------
        dt       : float       – timestep (s)
        params   : dict        – zone thermal parameters
        z_meas   : np.array(3) – [T_in, W_in, C_in] sensor readings
        V_dot_s  : float       – supply volumetric flow (m³/s)
        Q_equip  : float       – equipment heat gain (W)
        T_s, W_s, C_s : float  – supply air state
        T_out    : float       – outdoor temperature (°C)
        adj_data : list[dict]  – adjacent zone info
        """
        if self.x is None:
            return

        # ── Unpack state ─────────────────────────────────────────────────
        T_in, T_m, W_in, C_in, dT, dW, N_occ = self.x

        # ── Unpack params ────────────────────────────────────────────────
        R_ext  = params.get("R_env_ext", float('inf'))
        R_int  = params.get("R_int",     0.001)
        C_air  = params.get("C_air",     100_000.0)
        C_mass = params.get("C_mass",    1_000_000.0)
        M_air  = params.get("M_air",     100.0)
        V_room = params.get("V_room",    100.0)

        # ── Adjacency coupling ───────────────────────────────────────────
        inv_R_adj = 0.0
        q_adj_sum = 0.0
        for a in adj_data:
            if a['r_env'] > 0:
                inv_R_adj += 1.0 / a['r_env']
                q_adj_sum += a['t_adj'] / a['r_env']

        # ── Compute heat flows ───────────────────────────────────────────
        q_env  = (T_out - T_in) / R_ext if R_ext < float('inf') else 0.0
        q_adj  = q_adj_sum - T_in * inv_R_adj
        q_mass = (T_m - T_in) / R_int if R_int > 0 else 0.0
        q_int  = N_occ * Q_PERSON + Q_equip
        q_s    = RHO_AIR * V_dot_s * CP_AIR * (T_s - T_in)

        # ── State derivatives ────────────────────────────────────────────
        dx = np.zeros(7)
        dx[0] = (q_env + q_adj + q_mass + q_int + q_s + dT) / C_air
        dx[1] = (T_in - T_m) / (C_mass * R_int) if R_int > 0 else 0.0
        dx[2] = (N_occ * G_W_OCC + RHO_AIR * V_dot_s * (W_s - W_in) + dW) / M_air
        dx[3] = (N_occ * G_CO2_OCC * 1e6 + V_dot_s * (C_s - C_in)) / V_room
        # dx[4..6] = 0  (random walk on disturbances & occupancy)

        # ── Predict ──────────────────────────────────────────────────────
        x_pred = self.x + dx * dt

        # ── Jacobian F = I + (∂f/∂x)·dt ─────────────────────────────────
        inv_R_ext = 1.0 / R_ext if R_ext < float('inf') else 0.0
        inv_R_int = 1.0 / R_int if R_int > 0 else 0.0

        J = np.zeros((7, 7))
        J[0, 0] = (-inv_R_ext - inv_R_adj - inv_R_int - RHO_AIR * CP_AIR * V_dot_s) / C_air
        J[0, 1] = inv_R_int / C_air
        J[0, 4] = 1.0 / C_air
        J[0, 6] = Q_PERSON / C_air
        J[1, 0] = inv_R_int / C_mass
        J[1, 1] = -inv_R_int / C_mass
        J[2, 2] = -(RHO_AIR * V_dot_s) / M_air
        J[2, 5] = 1.0 / M_air
        J[2, 6] = G_W_OCC / M_air
        J[3, 3] = -V_dot_s / V_room
        J[3, 6] = (G_CO2_OCC * 1e6) / V_room

        F = np.eye(7) + J * dt
        P_pred = F @ self.P @ F.T + self.Q

        # ── Update (Kalman correction) ───────────────────────────────────
        y = z_meas - self.H @ x_pred                   # innovation
        S = self.H @ P_pred @ self.H.T + self.R        # innovation covariance
        K = P_pred @ self.H.T @ np.linalg.inv(S)       # Kalman gain

        self.x = x_pred + K @ y
        self.P = (np.eye(7) - K @ self.H) @ P_pred
        self.x[6] = max(0.0, self.x[6])                # occupancy ≥ 0

    # ── Read current state ───────────────────────────────────────────────
    def get_state(self):
        if self.x is None:
            return {"T_in_est": 0.0, "T_m_est": 0.0, "W_in_est": 0.0, "C_in_est": 0.0, "N_occ_est": 0.0}
        return {
            "T_in_est":  self.x[0],
            "T_m_est":   self.x[1],
            "W_in_est":  self.x[2],
            "C_in_est":  self.x[3],
            "N_occ_est": self.x[6],
        }
