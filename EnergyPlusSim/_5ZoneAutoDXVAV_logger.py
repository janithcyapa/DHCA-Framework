# logger.py
import csv
import os

class SimulationLogger:
    def __init__(self, csv_path, zones):
        self.csv_path = csv_path
        self.zones = zones
        self.file_obj = None
        self.csv_writer = None
        
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        self.file_obj = open(self.csv_path, 'w', newline='')
        self.csv_writer = csv.writer(self.file_obj)
        
        headers = ["DayOfYear", "Hour", "Minute", "Out_Temp_C", "Out_RH_pct"]
        central_nodes = ["Outdoor_Air", "Relief_Air", "Mixer_Inlet", "Mixed_Air", "CC_Out", "HC_Out", "Fan_Out"]
        for name in central_nodes:
            headers.extend([f"{name}_Temp_C", f"{name}_RH_pct", f"{name}_Flow_kg_s", f"{name}_CO2_ppm"])
            
        for z in self.zones:
            headers.extend([f"{z}_Temp_C", f"{z}_T_m_C", f"{z}_W_in_kg_kg", f"{z}_RH_pct", 
                            f"{z}_VAV_Flow_kg_s", f"{z}_Reheater_W", f"{z}_CO2_ppm", 
                            f"{z}_Occupants", f"{z}_EquipLoad_W",
                            f"{z}_T_in_theo", f"{z}_T_m_theo", f"{z}_W_in_theo", f"{z}_C_in_theo",
                            f"{z}_T_in_est", f"{z}_T_m_est", f"{z}_W_in_est", f"{z}_C_in_est", f"{z}_Occ_est"])
                            
        headers.extend(["CC_Power_W", "HC_Power_W", "Fan_Power_W"])
        
        self.csv_writer.writerow(headers)
        self.file_obj.flush()

    def log_timestep(self, time_data, env_data, central_data, zone_data, equip_data):
        row = []
        row.extend(time_data)
        row.extend(env_data)
        row.extend(central_data)
        row.extend(zone_data)
        row.extend(equip_data)
        
        self.csv_writer.writerow(row)
        self.file_obj.flush()
