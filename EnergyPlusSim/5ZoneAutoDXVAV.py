from pyenergyplus.plugin import EnergyPlusPlugin
import csv
import os
import json

from _5ZoneAutoDXVAV_zone_model import EKFEstimator
from _5ZoneAutoDXVAV_logger import SimulationLogger
from _5ZoneAutoDXVAV_controller import MPCController

class HVAC_Coordinator(EnergyPlusPlugin):
    def __init__(self):
        super().__init__()
        self.is_initialized = False
        
        self.csv_path = "./results/state_log.csv" 
        self.handles = {}
        self.actuators = {}
        self.zones = []
        self.datasets = {}
        self.start_day = None
        
        self.zone_params = {}
        self.estimators = {}
        self.logger = None
        self.mpc = None

    def initialize_system(self, state):
        all_zones = self.api.exchange.get_object_names(state, "Zone")
        self.zones = [z for z in all_zones if "SPACE" in z.upper()]
        
        print("\n" + "="*60)
        print(" 🚀 Python Plugin Initializing (Modular Framework)...")
        print(f" 🏢 Tracking {len(self.zones)} Conditioned Zones: {', '.join(self.zones)}")
        
        # Load Datasets
        if os.path.exists("./zone_thermal_params.json"):
            with open("./zone_thermal_params.json", "r") as f:
                self.zone_params = json.load(f)

        for i in range(1, 6):
            z_name = f"SPACE{i}-1"
            csv_file = f"./SupplementaryData/combined_Room{i}.csv"
            if os.path.exists(csv_file):
                self.datasets[z_name] = []
                with open(csv_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        plug_w = float(row['plug_load_energy [kWh]']) * 12000.0
                        light_w = float(row['lighting_energy [kWh]']) * 12000.0
                        occ = float(row['occupant_count [number]'])
                        co2 = float(row['outdoor_co2 [ppm]']) if 'outdoor_co2 [ppm]' in row else 420.0
                        self.datasets[z_name].append({
                            'plug_W': plug_w,
                            'light_W': light_w,
                            'occupant_count': occ,
                            'outdoor_co2': co2
                        })
                print(f" 📥 Loaded {len(self.datasets[z_name])} rows for {z_name}")

        # Instantiate Logger and MPC
        self.logger = SimulationLogger(self.csv_path, self.zones)
        self.mpc = MPCController(self.zones)
        
        # Instantiate Estimators
        for z in self.zones:
            self.estimators[z] = EKFEstimator(z)

        # Get Environment Handles
        self.handles['Out_Temp'] = self.api.exchange.get_variable_handle(state, "Site Outdoor Air Drybulb Temperature", "Environment")
        self.handles['Out_RH'] = self.api.exchange.get_variable_handle(state, "Site Outdoor Air Relative Humidity", "Environment")

        # Get Central Air Loop Node Handles
        central_nodes = {
            "Outdoor_Air": "Outside Air Inlet Node 1",
            "Relief_Air": "Relief Air Outlet Node 1",
            "Mixer_Inlet": "VAV Sys 1 Inlet Node",
            "Mixed_Air": "Mixed Air Node 1",
            "CC_Out": "Main Cooling Coil 1 Outlet Node",
            "HC_Out": "Main Heating Coil 1 Outlet Node",
            "Fan_Out": "VAV Sys 1 Outlet Node"
        }
        for name, node in central_nodes.items():
            self.handles[f"{name}_Temp"] = self.api.exchange.get_variable_handle(state, "System Node Temperature", node)
            self.handles[f"{name}_RH"] = self.api.exchange.get_variable_handle(state, "System Node Relative Humidity", node)
            self.handles[f"{name}_Flow"] = self.api.exchange.get_variable_handle(state, "System Node Mass Flow Rate", node)
            self.handles[f"{name}_CO2"] = self.api.exchange.get_variable_handle(state, "System Node CO2 Concentration", node)

        # Get Zone & VAV Handles
        for z in self.zones:
            self.handles[f"{z}_Temp"] = self.api.exchange.get_variable_handle(state, "Zone Mean Air Temperature", z)
            self.handles[f"{z}_RH"] = self.api.exchange.get_variable_handle(state, "Zone Air Relative Humidity", z)
            self.handles[f"{z}_VAV_Flow"] = self.api.exchange.get_variable_handle(state, "System Node Mass Flow Rate", f"{z} In Node")
            self.handles[f"{z}_Reheater"] = self.api.exchange.get_variable_handle(state, "Heating Coil NaturalGas Rate", f"{z} Zone Coil")
            self.handles[f"{z}_CO2"] = self.api.exchange.get_variable_handle(state, "Zone Air CO2 Concentration", z)
            self.handles[f"{z}_Occ"] = self.api.exchange.get_variable_handle(state, "Zone People Occupant Count", z)
            self.handles[f"{z}_Equip"] = self.api.exchange.get_variable_handle(state, "Zone Electric Equipment Total Heating Rate", z)

            # Extra handles for EKF
            self.handles[f"{z}_W_in"] = self.api.exchange.get_variable_handle(state, "Zone Mean Air Humidity Ratio", z)
            self.handles[f"{z}_T_m"] = self.api.exchange.get_variable_handle(state, "Zone Mean Radiant Temperature", z)
            self.handles[f"{z}_T_s"] = self.api.exchange.get_variable_handle(state, "System Node Temperature", f"{z} In Node")
            self.handles[f"{z}_W_s"] = self.api.exchange.get_variable_handle(state, "System Node Humidity Ratio", f"{z} In Node")
            self.handles[f"{z}_C_s"] = self.api.exchange.get_variable_handle(state, "System Node CO2 Concentration", f"{z} In Node")

        # Ensure all adjacent zones have temperature handles
        for z, params in self.zone_params.items():
            for adj in params.get("adj_zones", []):
                adj_z = adj["zone"]
                handle_key = f"{adj_z}_Temp"
                if handle_key not in self.handles:
                    self.handles[handle_key] = self.api.exchange.get_variable_handle(state, "Zone Mean Air Temperature", adj_z)

            node_name = f"{z} ATU IN NODE"
            
            self.actuators[f"{z}_Flow_SP"] = self.api.exchange.get_actuator_handle(state, "System Node Setpoint", "Mass Flow Rate Setpoint", node_name)
            self.actuators[f"{z}_Flow_MAX"] = self.api.exchange.get_actuator_handle(state, "System Node Setpoint", "Mass Flow Rate Maximum Available Setpoint", node_name)
            self.actuators[f"{z}_Flow_MIN"] = self.api.exchange.get_actuator_handle(state, "System Node Setpoint", "Mass Flow Rate Minimum Available Setpoint", node_name)
            self.actuators[f"{z}_Reheat_SP"] = self.api.exchange.get_actuator_handle(state, "System Node Setpoint", "Temperature Setpoint", f"{z} In Node")

            # Dataset Override Actuators
            self.actuators[f"{z}_People_SP"] = self.api.exchange.get_actuator_handle(state, "People", "Number of People", f"{z} PEOPLE 1")
            self.actuators[f"{z}_Equip_SP"] = self.api.exchange.get_actuator_handle(state, "ElectricEquipment", "Electricity Rate", f"{z} ELECEQ 1")
            self.actuators[f"{z}_Lights_SP"] = self.api.exchange.get_actuator_handle(state, "Lights", "Electricity Rate", f"{z} LIGHTS 1")

        # Central Equipment Handles
        self.handles["CC_Power"] = self.api.exchange.get_variable_handle(state, "Cooling Coil Electricity Rate", "Main Cooling Coil 1")
        self.handles["HC_Power"] = self.api.exchange.get_variable_handle(state, "Heating Coil NaturalGas Rate", "Main heating Coil 1")
        self.handles["Fan_Power"] = self.api.exchange.get_variable_handle(state, "Fan Electricity Rate", "Supply Fan 1")

        # Central Equipment Actuators
        self.actuators["CC_Temp_SP"] = self.api.exchange.get_actuator_handle(state, "System Node Setpoint", "Temperature Setpoint", "Main Cooling Coil 1 Outlet Node")
        self.actuators["HC_Temp_SP"] = self.api.exchange.get_actuator_handle(state, "System Node Setpoint", "Temperature Setpoint", "Main Heating Coil 1 Outlet Node")
        self.actuators["Fan_Flow"] = self.api.exchange.get_actuator_handle(state, "Fan", "Fan Air Mass Flow Rate", "Supply Fan 1")
        
        # Outdoor CO2 and OA Mixer Actuators
        self.actuators["CO2_Out_SP"] = self.api.exchange.get_actuator_handle(state, "Schedule:Constant", "Schedule Value", "CO2-Outdoor-Schedule")
        self.actuators["OA_Flow_SP"] = self.api.exchange.get_actuator_handle(state, "Outdoor Air Controller", "Air Mass Flow Rate", "OA CONTROLLER 1")

        # Validation Check
        missing_handles = False
        for name, handle in self.handles.items():
            if handle == -1:
                print(f"⚠️ WARNING: Missing handle for '{name}'! E+ will return 0.0.")
                missing_handles = True
        
        if missing_handles:
            print("🚨 Check your Output:Variable blocks in the IDF!")
        else:
            print(f" 📊 Logger Armed! Writing realtime data to: {self.csv_path}")
            
        print("="*60 + "\n")
        self.is_initialized = True

    # HOOK 1: EKF Update
    def on_begin_timestep_before_predictor(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state): return 0

        if not self.is_initialized:
            self.initialize_system(state)
            
        dt_hours = self.api.exchange.system_time_step(state)
        if dt_hours == 0: dt_hours = self.api.exchange.zone_time_step(state)
        dt = dt_hours * 3600.0
        if dt <= 0: return 0

        T_out = self.api.exchange.get_variable_value(state, self.handles["Out_Temp"])
        
        for z in self.zones:
            p = self.zone_params.get(z)
            if not p: continue
            
            t_in_meas = self.api.exchange.get_variable_value(state, self.handles[f"{z}_Temp"])
            w_in_meas = self.api.exchange.get_variable_value(state, self.handles[f"{z}_W_in"])
            c_in_meas = self.api.exchange.get_variable_value(state, self.handles[f"{z}_CO2"])
            
            m_dot = self.api.exchange.get_variable_value(state, self.handles[f"{z}_VAV_Flow"])
            V_dot_s = m_dot / 1.204
            
            Q_equip = 0.0 # Blind to equip in reality
            
            T_s = self.api.exchange.get_variable_value(state, self.handles[f"{z}_T_s"])
            W_s = self.api.exchange.get_variable_value(state, self.handles[f"{z}_W_s"])
            C_s = self.api.exchange.get_variable_value(state, self.handles[f"{z}_C_s"])
            
            occ_actual = self.api.exchange.get_variable_value(state, self.handles[f"{z}_Occ"])
            
            adj_zones_data = []
            for adj in p.get("adj_zones", []):
                t_adj = self.api.exchange.get_variable_value(state, self.handles[f"{adj['zone']}_Temp"])
                adj_zones_data.append({'t_adj': t_adj, 'r_env': float(adj["R_env"])})
            
            z_meas = [t_in_meas, w_in_meas, c_in_meas]
            u_inputs = [V_dot_s, Q_equip, T_s, W_s, C_s]
            boundary_inputs = [T_out, adj_zones_data, occ_actual]
            
            self.estimators[z].predict_and_update(dt, p, z_meas, u_inputs, boundary_inputs)
        
        return 0

    # HOOK 2: DATA LOGGER
    def on_end_of_zone_timestep_after_zone_reporting(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state): return 0
        if not self.is_initialized: return 0

        day = self.api.exchange.day_of_year(state)
        time_now = self.api.exchange.current_time(state)
        hours, mins = divmod(int(time_now * 60), 60)

        time_data = [day, hours, mins]
        env_data = [
            round(self.api.exchange.get_variable_value(state, self.handles['Out_Temp']), 2),
            round(self.api.exchange.get_variable_value(state, self.handles['Out_RH']), 2)
        ]

        central_data = []
        for name in ["Outdoor_Air", "Relief_Air", "Mixer_Inlet", "Mixed_Air", "CC_Out", "HC_Out", "Fan_Out"]:
            central_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_Temp"]), 2))
            central_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_RH"]), 2))
            central_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_Flow"]), 4))
            central_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_CO2"]), 2))

        zone_data = []
        estimations_dict = {}
        for z in self.zones:
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Temp"]), 2))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_T_m"]), 2))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_W_in"]), 5))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_RH"]), 2))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_VAV_Flow"]), 4))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Reheater"]), 2))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_CO2"]), 2))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Occ"]), 2))
            zone_data.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Equip"]), 2))
            
            est = self.estimators[z].get_estimations()
            estimations_dict[z] = est
            zone_data.append(round(est.get("T_in_theo", 0), 2))
            zone_data.append(round(est.get("T_m_theo", 0), 2))
            zone_data.append(round(est.get("W_in_theo", 0), 5))
            zone_data.append(round(est.get("C_in_theo", 0), 2))
            
            zone_data.append(round(est.get("T_in_est", 0), 2))
            zone_data.append(round(est.get("T_m_est", 0), 2))
            zone_data.append(round(est.get("W_in_est", 0), 5))
            zone_data.append(round(est.get("C_in_est", 0), 2))
            zone_data.append(round(est.get("N_occ_est", 0), 2))

        equip_data = []
        for eq in ["CC_Power", "HC_Power", "Fan_Power"]:
            equip_data.append(round(self.api.exchange.get_variable_value(state, self.handles[eq]), 2))

        self.logger.log_timestep(time_data, env_data, central_data, zone_data, equip_data)
        
        # Optional: Save estimations dict in case MPC needs it
        self.latest_estimations = estimations_dict

        return 0
    
    # HOOK 3: MPC CONTROL SIGNAL INJECTION
    def on_inside_hvac_system_iteration_loop(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state): return 0
        if not self.is_initialized: return 0

        # Time Sync for Datasets
        current_day = self.api.exchange.day_of_year(state)
        current_time = self.api.exchange.current_time(state) 
        
        if self.start_day is None:
            self.start_day = current_day

        elapsed_hours = (current_day - self.start_day) * 24.0 + current_time
        raw_idx = int(elapsed_hours * 12)

        # Dataset overrides for CO2
        if "SPACE1-1" in self.datasets:
            df1 = self.datasets["SPACE1-1"]
            idx1 = raw_idx % len(df1)
            outdoor_co2 = df1[idx1]['outdoor_co2']
            if self.actuators.get("CO2_Out_SP", -1) != -1:
                self.api.exchange.set_actuator_value(state, self.actuators["CO2_Out_SP"], outdoor_co2)

        if self.actuators.get("OA_Flow_SP", -1) != -1:
            self.api.exchange.set_actuator_value(state, self.actuators["OA_Flow_SP"], 1.0)

        self.api.exchange.set_actuator_value(state, self.actuators["CC_Temp_SP"], 13.0)
        self.api.exchange.set_actuator_value(state, self.actuators["HC_Temp_SP"], 14.0)

        # Use MPC Controller to get flow and reheat targets
        # Pass estimations down to MPC
        estimations = getattr(self, "latest_estimations", {})
        flow_targets, reheat_targets = self.mpc.compute_optimal_control(estimations, elapsed_hours)

        for z in self.zones:
            if z in self.datasets:
                df = self.datasets[z]
                idx = raw_idx % len(df)
                occ_count = df[idx]['occupant_count']
                equip_w = df[idx]['plug_W']
                light_w = df[idx]['light_W']
                
                handle_occ = self.actuators.get(f"{z}_People_SP", -1)
                handle_eq = self.actuators.get(f"{z}_Equip_SP", -1)
                handle_lt = self.actuators.get(f"{z}_Lights_SP", -1)
                
                if handle_occ != -1: self.api.exchange.set_actuator_value(state, handle_occ, occ_count)
                if handle_eq != -1: self.api.exchange.set_actuator_value(state, handle_eq, equip_w)
                if handle_lt != -1: self.api.exchange.set_actuator_value(state, handle_lt, light_w)

            mpc_commanded_flow = flow_targets.get(z, 0.1)

            handle_sp = self.actuators.get(f"{z}_Flow_SP", -1)
            handle_max = self.actuators.get(f"{z}_Flow_MAX", -1)
            handle_min = self.actuators.get(f"{z}_Flow_MIN", -1)
            
            if handle_sp != -1 and handle_max != -1 and handle_min != -1:
                self.api.exchange.set_actuator_value(state, handle_max, mpc_commanded_flow)
                self.api.exchange.set_actuator_value(state, handle_min, mpc_commanded_flow)
                self.api.exchange.set_actuator_value(state, handle_sp, mpc_commanded_flow)

            handle_reheat = self.actuators.get(f"{z}_Reheat_SP", -1)
            if handle_reheat != -1:
                self.api.exchange.set_actuator_value(state, handle_reheat, reheat_targets.get(z, 22.0))

        return 0
