"""
Extended Kalman Filter — Experimental Zone State Estimator
==========================================================
7-state augmented EKF that tracks the physical zone state plus
unmodelled disturbances and occupancy, adapted for experimental
sensor data with infiltration and retuned Q/R.

State vector (7):
    [T_in, T_m, W_in, C_in, δT, δW, N_occ]
      0     1     2     3    4   5    6

Measurement vector (3):
    [T_in_meas, W_in_meas, C_in_meas]
"""
import sys
import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ── Physical Constants ───────────────────────────────────────────────────
RHO_AIR   = 1.204
CP_AIR    = 1006.0
Q_PERSON  = 100.0
G_W_OCC   = 5e-5
G_CO2_OCC = 3.82e-6        # kg_co2/s per occupant

# Psychrometric conversion function
def rh_to_w(T_celsius, RH_percent):
    P_ws = 0.61078 * np.exp((17.27 * T_celsius) / (T_celsius + 237.3))
    P_w = (RH_percent / 100.0) * P_ws
    P_atm = 101.325
    W = 0.62198 * P_w / (P_atm - P_w)
    return W

def load_data(filepath):
    df = pd.read_parquet(filepath)
    df['indoor_c_mg'] = df['indoor_c'] * 1.8
    df['outdoor_c_mg'] = df['outdoor_c'] * 1.8
    df['indoor_w'] = rh_to_w(df['indoor_t'], df['indoor_h'])
    df['outdoor_w'] = rh_to_w(df['outdoor_t'], df['outdoor_h'])
    
    # Smooth noisy CO2 signal with exponential moving average
    # This prevents sudden sensor spikes from being misinterpreted as occupancy bursts
    df['indoor_c_mg_smooth'] = df['indoor_c_mg'].ewm(span=10).mean()
    return df


class ExperimentalZoneEKF:
    """
    7-state EKF retuned for experimental sensor data.
    
    Key differences from the EnergyPlus simulation EKF:
    - Includes infiltration (ACH-based) in dynamics and Jacobian
    - Q/R tuned so occupancy is the PREFERRED explanation for CO2/humidity
      changes, rather than disturbances absorbing the signal
    - CO2 measurement trusted more (lower R) since it's the primary
      occupancy-observable channel
    """

    def __init__(self, zone_name, ACH=0.5):
        self.zone_name = zone_name
        self.x = None                           # (7,) state vector
        self.P = np.eye(7)
        self.P[6, 6] = 4.0                     # initial uncertainty on occupancy

        self.ACH = ACH

        # ── Tuning matrices (retuned for experimental data) ──────────
        # Key insight: make disturbance noise SMALL so the EKF prefers
        # to explain changes through occupancy rather than disturbances.
        self.Q = np.diag([
            0.01,     # T_in    — sensor tracks well
            0.5,      # T_m     — hidden, moderate uncertainty
            1e-8,     # W_in    — sensor tracks well
            1.0,      # C_in    — noisy sensor
            1.0,      # d_T     — LOW: don't let disturbance steal occupancy signal
            1e-8,     # d_W     — LOW: same reasoning
            0.05,     # N_occ   — TIGHT: occupancy changes slowly (persons don't teleport)
        ])

        # Measurement noise — trust CO2 more (it's the best occupancy indicator)
        self.R = np.diag([
            0.01,     # T_in    — accurate thermocouple
            1e-8,     # W_in    — derived from RH sensor
            50.0,     # C_in    — CO2 sensor is NOISY, dampen its innovation effect
        ])

        # Observation matrix  H ∈ ℝ^{3×7}
        self.H = np.zeros((3, 7))
        self.H[0, 0] = 1.0   # observe T_in
        self.H[1, 2] = 1.0   # observe W_in
        self.H[2, 3] = 1.0   # observe C_in

    def initialise(self, T_in_0, W_in_0, C_in_0):
        self.x = np.array([T_in_0, T_in_0, W_in_0, C_in_0, 0.0, 0.0, 0.0])

    def step(self, dt, params, z_meas, V_dot_s, Q_equip, T_s, W_s, C_s, T_out, C_out, W_out, adj_data):
        """
        Predict + Update with infiltration terms.
        
        Additional parameters vs simulation EKF:
            C_out : float – outdoor CO2 (mg/m³)
            W_out : float – outdoor humidity ratio (kg/kg)
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

        # ── Infiltration ────────────────────────────────────────────────
        V_inf = (self.ACH * V_room) / 3600.0   # m³/s

        # ── Adjacency coupling ──────────────────────────────────────────
        inv_R_adj = 0.0
        q_adj_sum = 0.0
        for a in adj_data:
            if a['r_env'] > 0:
                inv_R_adj += 1.0 / a['r_env']
                q_adj_sum += a['t_adj'] / a['r_env']

        # ── Compute heat flows ──────────────────────────────────────────
        q_env  = (T_out - T_in) / R_ext if R_ext < float('inf') else 0.0
        q_adj  = q_adj_sum - T_in * inv_R_adj
        q_mass = (T_m - T_in) / R_int if R_int > 0 else 0.0
        q_int  = N_occ * Q_PERSON + Q_equip
        q_s    = RHO_AIR * V_dot_s * CP_AIR * (T_s - T_in)
        q_inf  = RHO_AIR * V_inf * CP_AIR * (T_out - T_in)

        # ── State derivatives ───────────────────────────────────────────
        dx = np.zeros(7)
        dx[0] = (q_env + q_adj + q_mass + q_int + q_s + q_inf + dT) / C_air
        dx[1] = (T_in - T_m) / (C_mass * R_int) if R_int > 0 else 0.0
        dx[2] = (N_occ * G_W_OCC + RHO_AIR * V_inf * (W_out - W_in) + RHO_AIR * V_dot_s * (W_s - W_in) + dW) / M_air
        dx[3] = (N_occ * G_CO2_OCC * 1e6 + V_inf * (C_out - C_in) + V_dot_s * (C_s - C_in)) / V_room
        # dx[4..6] = 0  (random walk on disturbances & occupancy)

        # ── Predict ─────────────────────────────────────────────────────
        x_pred = self.x + dx * dt

        # ── Jacobian F = I + (∂f/∂x)·dt ────────────────────────────────
        inv_R_ext = 1.0 / R_ext if R_ext < float('inf') else 0.0
        inv_R_int = 1.0 / R_int if R_int > 0 else 0.0

        J = np.zeros((7, 7))
        J[0, 0] = (-inv_R_ext - inv_R_adj - inv_R_int - RHO_AIR * CP_AIR * (V_dot_s + V_inf)) / C_air
        J[0, 1] = inv_R_int / C_air
        J[0, 4] = 1.0 / C_air
        J[0, 6] = Q_PERSON / C_air
        J[1, 0] = inv_R_int / C_mass
        J[1, 1] = -inv_R_int / C_mass
        J[2, 2] = -(RHO_AIR * (V_dot_s + V_inf)) / M_air
        J[2, 5] = 1.0 / M_air
        J[2, 6] = G_W_OCC / M_air
        J[3, 3] = -(V_dot_s + V_inf) / V_room
        J[3, 6] = (G_CO2_OCC * 1e6) / V_room

        F = np.eye(7) + J * dt
        P_pred = F @ self.P @ F.T + self.Q

        # ── Update (Kalman correction) ──────────────────────────────────
        y = z_meas - self.H @ x_pred                   # innovation
        S = self.H @ P_pred @ self.H.T + self.R        # innovation covariance
        K = P_pred @ self.H.T @ np.linalg.inv(S)       # Kalman gain

        self.x = x_pred + K @ y
        self.P = (np.eye(7) - K @ self.H) @ P_pred
        self.x[6] = np.clip(self.x[6], 0.0, 10.0)     # clamp occupancy to [0, 10]

    def get_state(self):
        if self.x is None:
            return {"T_in_est": 0.0, "T_m_est": 0.0, "W_in_est": 0.0, "C_in_est": 0.0,
                    "N_occ_est": 0.0, "d_T_est": 0.0, "d_W_est": 0.0}
        return {
            "T_in_est":  self.x[0],
            "T_m_est":   self.x[1],
            "W_in_est":  self.x[2],
            "C_in_est":  self.x[3],
            "d_T_est":   self.x[4],
            "d_W_est":   self.x[5],
            "N_occ_est": self.x[6],
        }


def run():
    # File paths
    base_dir = os.path.dirname(__file__)
    data_path = os.path.join(base_dir, 'processed_data', 'experiments', 'refactored_data', 'entry_0002_refactored_data.parquet')
    params_path = os.path.join(base_dir, 'processed_data', 'experiments', 'refactored_data', 'identified_params.json')
    
    print(f"Loading dataset: {data_path}")
    df = load_data(data_path)
    
    print(f"Loading parameters: {params_path}")
    with open(params_path, 'r') as f:
        params = json.load(f)
        
    ACH = 0.5  # Assumed infiltration rate
    ekf = ExperimentalZoneEKF("Experiment_Zone", ACH=ACH)
    dt = 10.0
    
    # Initialize EKF
    ekf.initialise(df['indoor_t'].iloc[0], df['indoor_w'].iloc[0], df['indoor_c_mg'].iloc[0])
    
    # Result containers
    results = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Current measurements
        z_meas = np.array([row['indoor_t'], row['indoor_w'], row['indoor_c_mg_smooth']])
        
        # Supply inputs (none in this dataset, set neutrally)
        V_dot_s = 0.0
        T_s = row['outdoor_t']  
        W_s = row['indoor_w']
        C_s = row['indoor_c_mg']
        Q_equip = 0.0
        T_out = row['indoor_t']
        C_out = row['outdoor_c_mg']
        W_out = row['outdoor_w']
        adj_data = []
        
        # Step EKF
        ekf.step(dt, params, z_meas, V_dot_s, Q_equip, T_s, W_s, C_s, T_out, C_out, W_out, adj_data)
        
        # Store state
        state = ekf.get_state()
        results.append(state)
        
    res_df = pd.DataFrame(results)
    
    # Plotting
    time_min = np.arange(len(df)) * dt / 60.0
    
    fig, axs = plt.subplots(5, 1, figsize=(12, 18), sharex=True)
    fig.suptitle('EKF State Estimation — Experimental Data', fontsize=14, fontweight='bold')
    
    # Temperature
    axs[0].plot(time_min, df['indoor_t'], label='Measured T_in', color='black', linewidth=1.5)
    axs[0].plot(time_min, res_df['T_in_est'], label='Estimated T_in', color='red', linestyle='--')
    axs[0].plot(time_min, res_df['T_m_est'], label='Estimated T_m (Mass)', color='orange', linestyle=':', alpha=0.7)
    axs[0].set_ylabel('Temperature (°C)')
    axs[0].legend()
    axs[0].grid(True, alpha=0.3)
    
    # Humidity
    axs[1].plot(time_min, df['indoor_w'], label='Measured W_in', color='black', linewidth=1.5)
    axs[1].plot(time_min, res_df['W_in_est'], label='Estimated W_in', color='blue', linestyle='--')
    axs[1].set_ylabel('Humidity Ratio (kg/kg)')
    axs[1].legend()
    axs[1].grid(True, alpha=0.3)
    
    # CO2
    axs[2].plot(time_min, df['indoor_c_mg'], label='Measured CO2', color='black', linewidth=1.5)
    axs[2].plot(time_min, res_df['C_in_est'], label='Estimated CO2', color='green', linestyle='--')
    axs[2].set_ylabel('CO2 (mg/m³)')
    axs[2].legend()
    axs[2].grid(True, alpha=0.3)
    
    # Occupancy
    axs[3].step(time_min, df['n_occ'], label='True Occupancy', color='black', alpha=0.6, where='post', linewidth=1.5)
    axs[3].plot(time_min, res_df['N_occ_est'], label='Estimated Occupancy', color='purple', linewidth=1.5)
    axs[3].set_ylabel('Occupancy (persons)')
    axs[3].legend()
    axs[3].grid(True, alpha=0.3)
    
    # Disturbances
    axs[4].plot(time_min, res_df['d_T_est'], label='Thermal Disturbance (d_T) [W]', color='brown')
    axs[4].plot(time_min, res_df['d_W_est'] * 1e6, label='Moisture Disturbance (d_W × 1e6)', color='teal')
    axs[4].set_ylabel('Disturbances')
    axs[4].set_xlabel('Time (minutes)')
    axs[4].legend()
    axs[4].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_path = os.path.join(base_dir, 'processed_data', 'experiments', 'refactored_data', 'ekf_results.png')
    plt.savefig(plot_path, dpi=150)
    print(f"Saved EKF plot to {plot_path}")
    
if __name__ == '__main__':
    run()
