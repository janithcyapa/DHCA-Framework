import pandas as pd
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import os

# ── Physical Constants ───────────────────────────────────────────────────
RHO_AIR   = 1.204      # kg/m³
CP_AIR    = 1006.0     # J/(kg·K)
Q_PERSON  = 100.0      # W per occupant (sensible)
G_W_OCC   = 5e-5       # kg_w/s per occupant
G_CO2_OCC = 3.82e-6    # kg_co2/s per occupant

def rh_to_w(T_celsius, RH_percent):
    """
    Converts Relative Humidity (%) to Humidity Ratio (kg/kg).
    T_celsius: Temperature in °C
    RH_percent: Relative Humidity in %
    """
    # Tetens equation for saturation vapor pressure (kPa)
    P_ws = 0.61078 * np.exp((17.27 * T_celsius) / (T_celsius + 237.3))
    # Actual vapor pressure (kPa)
    P_w = (RH_percent / 100.0) * P_ws
    # Atmospheric pressure (kPa)
    P_atm = 101.325
    # Humidity ratio (kg/kg)
    W = 0.62198 * P_w / (P_atm - P_w)
    return W

def load_and_preprocess(filepath):
    df = pd.read_parquet(filepath)
    
    # Required columns from user
    req_cols = ['indoor_t', 'indoor_h', 'indoor_c', 'outdoor_t', 'outdoor_h', 'outdoor_c', 'n_occ']
    for col in req_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
            
    # Convert units
    # 1 ppm CO2 ~= 1.8 mg/m^3 (at standard conditions)
    df['indoor_c_mg'] = df['indoor_c'] * 1.8
    df['outdoor_c_mg'] = df['outdoor_c'] * 1.8
    
    df['indoor_w'] = rh_to_w(df['indoor_t'], df['indoor_h'])
    df['outdoor_w'] = rh_to_w(df['outdoor_t'], df['outdoor_h'])
    
    # Supply air defaults (neutralized if missing)
    if 'supply_v' not in df.columns: df['supply_v'] = 0.0
    if 'supply_t' not in df.columns: df['supply_t'] = 0.0
    if 'supply_h' not in df.columns: df['supply_h'] = 0.0
    if 'supply_c' not in df.columns: df['supply_c'] = 0.0
    
    # Convert supply RH and CO2
    df['supply_w'] = rh_to_w(df['supply_t'], df['supply_h'])
    df['supply_c_mg'] = df['supply_c'] * 1.8
    
    return df

# ── Simulation Functions ────────────────────────────────────────────────
def simulate_mass_balance(params, df, dt=10.0):
    V_room, M_air, ACH = params
    
    N = len(df)
    C_in = np.zeros(N)
    W_in = np.zeros(N)
    
    C_in[0] = df['indoor_c_mg'].iloc[0]
    W_in[0] = df['indoor_w'].iloc[0]
    
    occ = df['n_occ'].values
    V_s = df['supply_v'].values
    C_s = df['supply_c_mg'].values
    W_s = df['supply_w'].values
    C_out = df['outdoor_c_mg'].values
    W_out = df['outdoor_w'].values
    
    V_inf = (ACH * V_room) / 3600.0
    
    for i in range(N - 1):
        # CO2 dynamics with infiltration
        dC_in = (occ[i] * G_CO2_OCC * 1e6 + V_inf * (C_out[i] - C_in[i]) + V_s[i] * (C_s[i] - C_in[i])) / V_room
        C_in[i+1] = C_in[i] + dC_in * dt
        
        # Humidity dynamics with infiltration
        dW_in = (occ[i] * G_W_OCC + RHO_AIR * V_inf * (W_out[i] - W_in[i]) + RHO_AIR * V_s[i] * (W_s[i] - W_in[i])) / M_air
        W_in[i+1] = W_in[i] + dW_in * dt
        
    return C_in, W_in

def simulate_thermal(params, V_room, M_air, ACH, df, dt=10.0):
    C_air, C_mass, R_ext, R_int, T_m0 = params
    
    N = len(df)
    T_in = np.zeros(N)
    T_m = np.zeros(N)
    
    T_in[0] = df['indoor_t'].iloc[0]
    T_m[0] = T_m0 # Optimize initial mass temperature
    
    occ = df['n_occ'].values
    V_s = df['supply_v'].values
    T_s = df['supply_t'].values
    T_out = df['outdoor_t'].values
    Q_equip = 0.0 # From user instruction
    
    V_inf = (ACH * V_room) / 3600.0
    
    for i in range(N - 1):
        q_env = (T_out[i] - T_in[i]) / R_ext
        q_mass = (T_m[i] - T_in[i]) / R_int
        q_int = occ[i] * Q_PERSON + Q_equip
        q_s = RHO_AIR * V_s[i] * CP_AIR * (T_s[i] - T_in[i])
        q_inf = RHO_AIR * V_inf * CP_AIR * (T_out[i] - T_in[i])
        
        dT_in = (q_env + q_mass + q_int + q_s + q_inf) / C_air
        dT_m = (T_in[i] - T_m[i]) / (C_mass * R_int)
        
        T_in[i+1] = T_in[i] + dT_in * dt
        T_m[i+1] = T_m[i] + dT_m * dt
        
    return T_in, T_m

# ── Objective Functions ────────────────────────────────────────────────
def objective_phase_a(params, df, dt):
    # Scale parameters slightly for optimizer stability if needed, but we'll use bounds.
    C_in_sim, W_in_sim = simulate_mass_balance(params, df, dt)
    
    # Calculate MSE
    mse_c = np.mean((C_in_sim - df['indoor_c_mg'].values)**2)
    mse_w = np.mean((W_in_sim - df['indoor_w'].values)**2)
    
    # Normalize errors to combine them
    var_c = np.var(df['indoor_c_mg'].values) + 1e-6
    var_w = np.var(df['indoor_w'].values) + 1e-12
    
    return (mse_c / var_c) + (mse_w / var_w)

def objective_phase_b(scaled_params, V_room, M_air, ACH, df, dt, scale_factors):
    params = scaled_params * scale_factors
    T_in_sim, _ = simulate_thermal(params, V_room, M_air, ACH, df, dt)
    mse_t = np.mean((T_in_sim - df['indoor_t'].values)**2)
    return mse_t

def run_identification(filepath):
    print(f"Loading data from {filepath}")
    df = load_and_preprocess(filepath)
    dt = 10.0 # 10s timestep as specified by user
    
    print("--- Phase A: Estimating V_room, M_air, ACH ---")
    
    # Scale factors: typical V_room = 100, M_air = 120, ACH = 0.5
    scale_a = np.array([100.0, 120.0, 1.0])
    init_scaled_a = np.array([1.0, 1.0, 0.5])
    bounds_scaled_a = [
        (20.0/scale_a[0], 500.0/scale_a[0]), 
        (24.0/scale_a[1], 1000.0/scale_a[1]),
        (0.0/scale_a[2], 5.0/scale_a[2])
    ]
    
    def obj_a_scaled(scaled_params):
        params = scaled_params * scale_a
        return objective_phase_a(params, df, dt)
        
    res_a = minimize(obj_a_scaled, init_scaled_a, bounds=bounds_scaled_a, method='L-BFGS-B')
    V_room_opt, M_air_opt, ACH_opt = res_a.x * scale_a
    print(f"Optimization Phase A Success: {res_a.success}")
    print(f"Identified V_room: {V_room_opt:.2f} m^3")
    print(f"Identified M_air:  {M_air_opt:.2f} kg (Theoretical ρ*V: {V_room_opt * RHO_AIR:.2f} kg)")
    print(f"Identified ACH:    {ACH_opt:.3f} 1/h")
    
    print("\n--- Phase B: Estimating C_air, C_mass, R_ext, R_int, T_m0 ---")
    # Scale factors: C_air = 100,000, C_mass = 4,000,000, R_ext = 0.01, R_int = 0.005, T_m0 = 25
    scale_b = np.array([100000.0, 4000000.0, 0.01, 0.005, 25.0])
    init_scaled_b = np.array([1.0, 1.0, 1.0, 1.0, df['indoor_t'].iloc[0] / 25.0])
    bounds_scaled_b = [
        (10000.0/scale_b[0], 1e6/scale_b[0]),     # C_air
        (100000.0/scale_b[1], 2e7/scale_b[1]),    # C_mass
        (0.0001/scale_b[2], 5.0/scale_b[2]),      # R_ext
        (0.0001/scale_b[3], 1.0/scale_b[3]),      # R_int
        (15.0/scale_b[4], 35.0/scale_b[4])        # T_m0 (between 15C and 35C)
    ]
    
    def obj_b_scaled(scaled_params):
        return objective_phase_b(scaled_params, V_room_opt, M_air_opt, ACH_opt, df, dt, scale_b)
        
    res_b = minimize(obj_b_scaled, init_scaled_b, bounds=bounds_scaled_b, method='L-BFGS-B')
    C_air_opt, C_mass_opt, R_ext_opt, R_int_opt, T_m0_opt = res_b.x * scale_b
    
    print(f"Optimization Phase B Success: {res_b.success}")
    print(f"Identified C_air:  {C_air_opt:.2f} J/K")
    print(f"Identified C_mass: {C_mass_opt:.2f} J/K")
    print(f"Identified R_ext:  {R_ext_opt:.5f} K/W")
    print(f"Identified R_int:  {R_int_opt:.5f} K/W")
    print(f"Identified T_m0:   {T_m0_opt:.2f} °C")
    
    # ── Simulate with optimal parameters for plotting ──
    C_sim, W_sim = simulate_mass_balance([V_room_opt, M_air_opt, ACH_opt], df, dt)
    T_sim, Tm_sim = simulate_thermal([C_air_opt, C_mass_opt, R_ext_opt, R_int_opt, T_m0_opt], V_room_opt, M_air_opt, ACH_opt, df, dt)
    
    # Create plots
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    
    time_axis = np.arange(len(df)) * dt / 60.0 # Time in minutes
    
    # Temperature
    axs[0].plot(time_axis, df['indoor_t'], label='Measured T_in', color='black')
    axs[0].plot(time_axis, T_sim, label='Simulated T_in', color='red', linestyle='--')
    axs[0].set_ylabel('Temperature (°C)')
    axs[0].legend()
    axs[0].grid(True)
    
    # Humidity
    axs[1].plot(time_axis, df['indoor_w'], label='Measured W_in', color='black')
    axs[1].plot(time_axis, W_sim, label='Simulated W_in', color='blue', linestyle='--')
    axs[1].set_ylabel('Humidity Ratio (kg/kg)')
    axs[1].legend()
    axs[1].grid(True)
    
    # CO2
    axs[2].plot(time_axis, df['indoor_c_mg'], label='Measured CO2 (mg/m3)', color='black')
    axs[2].plot(time_axis, C_sim, label='Simulated CO2 (mg/m3)', color='green', linestyle='--')
    axs[2].set_ylabel('CO2 (mg/m³)')
    axs[2].set_xlabel('Time (minutes)')
    axs[2].legend()
    axs[2].grid(True)
    
    plt.tight_layout()
    plot_path = os.path.join(os.path.dirname(filepath), 'system_id_results.png')
    plt.savefig(plot_path)
    print(f"\nSaved comparison plot to {plot_path}")
    
    # Save optimal parameters to json
    optimal_params = {
        "V_room": V_room_opt,
        "M_air": M_air_opt,
        "C_air": C_air_opt,
        "C_mass": C_mass_opt,
        "R_env_ext": R_ext_opt,
        "R_int": R_int_opt
    }
    
    import json
    params_path = os.path.join(os.path.dirname(filepath), 'identified_params.json')
    with open(params_path, 'w') as f:
        json.dump(optimal_params, f, indent=4)
    print(f"Saved optimal parameters to {params_path}")

if __name__ == "__main__":
    filepath = "/home/jazz/Projects/DHCA-Framework/Experiment/processed_data/experiments/refactored_data/entry_0002_refactored_data.parquet"
    run_identification(filepath)
