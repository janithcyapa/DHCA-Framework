import os
import sys
import json
import traceback

sys.path.append(os.path.expanduser('~/EnergyPlus-25-1-0'))

def extract_model_parameters():
    print("Extracting model parameters...")
    # Initialize the utility
    from eplus.core import EPlusUtil
    
    sim = EPlusUtil(verbose=0, out_dir="./model_gen_out")
    
    idf_path = os.path.abspath("5ZoneAutoDXVAV.idf")
    epw_path = os.path.abspath("weather.epw")
    sim.set_model(idf_path, epw_path)
    
    print("Retrieving zone thermal parameters from IDF...")
    raw_params = sim.get_zone_thermal_parameters()
    
    processed_params = {}
    
    for zone_id, z_data in raw_params.items():
        inv_R_env_ext = 0.0
        R_env_gnd = None
        adj_zones = []
        
        for b in z_data.get("boundaries", []):
            target = b["target"]
            r_abs = float(b["R_absolute_K_W"])
            if target == "Ground": 
                R_env_gnd = r_abs
            elif target == "Environment" or b["boundary_condition"] == "outdoors": 
                inv_R_env_ext += (1.0 / r_abs)
            else: 
                adj_zones.append({
                    "zone": target,
                    "R_env": r_abs
                })
                
        R_env_ext = 1.0 / inv_R_env_ext if inv_R_env_ext > 0 else float('inf')
        if R_env_ext > 1000:
            R_env_ext = float('1000')
        if R_env_gnd is None:
            R_env_gnd = float('1000')
            
        processed_params[zone_id] = {
            "V_room": float(z_data['V_room']),
            "M_air": float(z_data['M_air']),
            "C_air": float(z_data['C_air']),
            "C_mass": float(z_data['C_mass']),
            "R_int": float(z_data['R_int']),
            "R_env_ext": R_env_ext,
            "R_env_gnd": R_env_gnd,
            "adj_zones": adj_zones
        }

    out_file = os.path.abspath("zone_thermal_params.json")
    with open(out_file, "w") as f:
        json.dump(processed_params, f, indent=4)
        
    print(f"Successfully processed and saved one-time calculations to {out_file}")

if __name__ == "__main__":
    try:
        extract_model_parameters()
    except Exception as e:
        traceback.print_exc()
