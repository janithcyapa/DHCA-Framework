import pandas as pd
import numpy as np
from open_dataset_store import quick_start
import sys
sys.path.append("/home/jazz/Projects/DHCA-Framework/EnergyPlusSim")
from _5ZoneAutoDXVAV_zone_controller import ZoneController, get_w_from_rh
import math

def calculate_actual_flow(C, M):
    if C <= 0:
        return 0.0
    velocity = (9.3 + 0.008 * M) / (1.0 + math.exp(-0.16 * (C - 49.0 + 0.01 * M)))
    diameter = 0.110
    area = math.pi * (diameter / 2) ** 2
    air_density = 1.2 
    return velocity * area * air_density

def rh_to_w(T, rh):
    # Calculate absolute humidity W (kg/kg) from Temperature (C) and RH (%)
    rh_frac = rh / 100.0 if (np.asarray(rh) > 1.0).any() else rh
    p_sat = 610.94 * np.exp(17.625 * T / (243.04 + T))
    p_vapor = rh_frac * p_sat
    return 0.62198 * p_vapor / (101325.0 - p_vapor)

entry_id='entry_0006'
store = quick_start('.', backend='local')
df = store.get_entry_raw_data(entry_type='experiments', entry_id= entry_id)
df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')

co2_cols = ['outside_c', 'room_1_c', 'room_2_c', 'room_3_c', 'supply_c']
for col in co2_cols:
    if col in df.columns:
        invalid_mask = (df[col] < 400) | (df[col] > 10000)
        df.loc[invalid_mask, col] = np.nan
        df[col] = df[col].ffill().bfill()

rh_cols = ['room_1_h', 'room_2_h', 'room_3_h', 'outside_h', 'supply_h']
for col in rh_cols:
    if col in df.columns:
        df[col] = df[col] - 10

df['room_1_w'] = rh_to_w(df['room_1_t'], df['room_1_h'])
df['avg_co2'] = df[['room_2_c', 'room_3_c']].mean(axis=1)

print("Running EKF Offline Evaluation...")
zone_controller = ZoneController("Zone_1")
ekf_data = []
prev_time = None

class DummyLogger:
    def __init__(self): self.data = {}
    def add(self, k, v): self.data[k] = v

for i, row in df.iterrows():
    curr_time = row['timestamp'].timestamp()
    dt = 5.0 if prev_time is None else max(1.0, curr_time - prev_time)
    prev_time = curr_time
    
    T_out = row['outside_t']
    RH_out = row['outside_h'] / 100.0 if row['outside_h'] > 1.0 else row['outside_h']
    W_out = get_w_from_rh(T_out, RH_out)
    C_out = row['outside_c']
    
    T_in = row['room_1_t']
    RH_in = row['room_1_h'] / 100.0 if row['room_1_h'] > 1.0 else row['room_1_h']
    W_in = get_w_from_rh(T_in, RH_in)
    
    C_in = row['avg_co2']
        
    T_s = row['supply_t']
    RH_s = row['supply_h'] / 100.0 if row['supply_h'] > 1.0 else row['supply_h']
    W_s = get_w_from_rh(T_s, RH_s)
    C_s = row['supply_c']
    
    vav_flow_real = calculate_actual_flow(row['fan'], row['mixer'])
    
    state_data = {
        'T_out': T_out, 'W_out': W_out, 'C_out': C_out,
        'T_in': T_in, 'W_in': W_in, 'C_in': C_in,
        'T_s': T_s, 'W_s': W_s, 'C_s': C_s,
        'temp_setpoint': 22.0, 
        'VAV_Flow': vav_flow_real
    }
    
    for k, v in state_data.items():
        if np.isnan(v) or np.isinf(v):
            print(f"Index {i}, Variable {k} is NaN/Inf: {v}")
    
    lg = DummyLogger()
    zone_controller.step(dt, state_data, lg)
