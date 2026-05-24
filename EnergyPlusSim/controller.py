from pyenergyplus.plugin import EnergyPlusPlugin
import csv
import os

class HVAC_Coordinator(EnergyPlusPlugin):
    def __init__(self):
        super().__init__()
        self.is_initialized = False
        
        self.csv_path = "./baseline_results/state_log.csv" 
        self.file_obj = None
        self.csv_writer = None
        self.handles = {}
        self.actuators = {}
        self.zones = []

    def initialize_system(self, state):
        """Helper method to setup handles and CSV once."""
        
        # 1. Fetch all zones, but FILTER OUT Plenums (only keep SPACE zones)
        all_zones = self.api.exchange.get_object_names(state, "Zone")
        self.zones = [z for z in all_zones if "SPACE" in z.upper()]
        
        print("\n" + "="*60)
        print(" 🚀 Python Plugin Initializing (Dual Hooks Active)...")
        print(f" 🏢 Tracking {len(self.zones)} Conditioned Zones: {', '.join(self.zones)}")
        
        # 2. Setup CSV
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        self.file_obj = open(self.csv_path, 'w', newline='')
        self.csv_writer = csv.writer(self.file_obj)

        headers = ["DayOfYear", "Hour", "Minute", "Out_Temp_C", "Out_RH_pct"]
        
        # 3. Get Environment Handles
        self.handles['Out_Temp'] = self.api.exchange.get_variable_handle(state, "Site Outdoor Air Drybulb Temperature", "Environment")
        self.handles['Out_RH'] = self.api.exchange.get_variable_handle(state, "Site Outdoor Air Relative Humidity", "Environment")

        # 3.5. Get Central Air Loop Node Handles
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
            headers.extend([f"{name}_Temp_C", f"{name}_RH_pct", f"{name}_Flow_kg_s", f"{name}_CO2_ppm"])
            self.handles[f"{name}_Temp"] = self.api.exchange.get_variable_handle(state, "System Node Temperature", node)
            self.handles[f"{name}_RH"] = self.api.exchange.get_variable_handle(state, "System Node Relative Humidity", node)
            self.handles[f"{name}_Flow"] = self.api.exchange.get_variable_handle(state, "System Node Mass Flow Rate", node)
            self.handles[f"{name}_CO2"] = self.api.exchange.get_variable_handle(state, "System Node CO2 Concentration", node)

        # 4. Get Zone & VAV Handles
        for z in self.zones:
            headers.extend([f"{z}_Temp_C", f"{z}_RH_pct", f"{z}_VAV_Flow_kg_s", f"{z}_Reheater_W",
                            f"{z}_CO2_ppm", f"{z}_Occupants", f"{z}_EquipLoad_W"])
            self.handles[f"{z}_Temp"] = self.api.exchange.get_variable_handle(state, "Zone Mean Air Temperature", z)
            self.handles[f"{z}_RH"] = self.api.exchange.get_variable_handle(state, "Zone Air Relative Humidity", z)
            self.handles[f"{z}_VAV_Flow"] = self.api.exchange.get_variable_handle(state, "System Node Mass Flow Rate", f"{z} In Node")
            self.handles[f"{z}_Reheater"] = self.api.exchange.get_variable_handle(state, "Heating Coil NaturalGas Rate", f"{z} Zone Coil")
            self.handles[f"{z}_CO2"] = self.api.exchange.get_variable_handle(state, "Zone Air CO2 Concentration", z)
            self.handles[f"{z}_Occ"] = self.api.exchange.get_variable_handle(state, "Zone People Occupant Count", z)
            self.handles[f"{z}_Equip"] = self.api.exchange.get_variable_handle(state, "Zone Electric Equipment Total Heating Rate", z)

            node_name = f"{z} ATU IN NODE"
            
            # 1. Grab the standard setpoint
            handle_sp = self.api.exchange.get_actuator_handle(
                state, "System Node Setpoint", "Mass Flow Rate Setpoint", node_name)
            
            # 2. Grab the MAXIMUM limit setpoint 
            handle_max = self.api.exchange.get_actuator_handle(
                state, "System Node Setpoint", "Mass Flow Rate Maximum Available Setpoint", node_name)
                
            # 3. Grab the MINIMUM limit setpoint (THE MISSING LINK)
            handle_min = self.api.exchange.get_actuator_handle(
                state, "System Node Setpoint", "Mass Flow Rate Minimum Available Setpoint", node_name)
            
            self.actuators[f"{z}_Flow_SP"] = handle_sp
            self.actuators[f"{z}_Flow_MAX"] = handle_max
            self.actuators[f"{z}_Flow_MIN"] = handle_min
            
            # 4. Grab Reheater Temperature Setpoint
            self.actuators[f"{z}_Reheat_SP"] = self.api.exchange.get_actuator_handle(
                state, "System Node Setpoint", "Temperature Setpoint", f"{z} In Node")

        # 4.5. Get Central Equipment Handles
        headers.extend(["CC_Power_W", "HC_Power_W", "Fan_Power_W"])
        self.handles["CC_Power"] = self.api.exchange.get_variable_handle(state, "Cooling Coil Electricity Rate", "Main Cooling Coil 1")
        self.handles["HC_Power"] = self.api.exchange.get_variable_handle(state, "Heating Coil NaturalGas Rate", "Main heating Coil 1")
        self.handles["Fan_Power"] = self.api.exchange.get_variable_handle(state, "Fan Electricity Rate", "Supply Fan 1")

        # 4.6. Central Equipment Actuators
        self.actuators["CC_Temp_SP"] = self.api.exchange.get_actuator_handle(
            state, "System Node Setpoint", "Temperature Setpoint", "Main Cooling Coil 1 Outlet Node")
        self.actuators["HC_Temp_SP"] = self.api.exchange.get_actuator_handle(
            state, "System Node Setpoint", "Temperature Setpoint", "Main Heating Coil 1 Outlet Node")
        self.actuators["Fan_Flow"] = self.api.exchange.get_actuator_handle(
            state, "Fan", "Fan Air Mass Flow Rate", "Supply Fan 1")

        self.csv_writer.writerow(headers)
        self.file_obj.flush() # Force write headers immediately!

        # 5. Validation Check
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

    # =====================================================================
    # HOOK 1: MPC BRAIN
    # =====================================================================
    def on_begin_timestep_before_predictor(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state): return 0

        if not self.is_initialized:
            self.initialize_system(state)
        
        return 0

    # =====================================================================
    # HOOK 2: DATA LOGGER (Corrected Name!)
    # =====================================================================
    def on_end_of_zone_timestep_after_zone_reporting(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state): return 0
        if not self.is_initialized: return 0

        # Extract Time
        day = self.api.exchange.day_of_year(state)
        time_now = self.api.exchange.current_time(state)
        hours, mins = divmod(int(time_now * 60), 60)

        row = [day, hours, mins]
        
        # Extract Outdoor
        row.append(round(self.api.exchange.get_variable_value(state, self.handles['Out_Temp']), 2))
        row.append(round(self.api.exchange.get_variable_value(state, self.handles['Out_RH']), 2))

        # Extract Central Nodes
        for name in ["Outdoor_Air", "Relief_Air", "Mixer_Inlet", "Mixed_Air", "CC_Out", "HC_Out", "Fan_Out"]:
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_Temp"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_RH"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_Flow"]), 4))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{name}_CO2"]), 2))


        # Extract Zones
        for z in self.zones:
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Temp"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_RH"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_VAV_Flow"]), 4))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Reheater"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_CO2"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Occ"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Equip"]), 2))

        # Extract Central Equipment
        for eq in ["CC_Power", "HC_Power", "Fan_Power"]:
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[eq]), 2))

        # Write and force save
        self.csv_writer.writerow(row)
        self.file_obj.flush()

        return 0
    
    # =====================================================================
    # HOOK 3: MPC CONTROL SIGNAL INJECTION
    # =====================================================================
    def on_inside_hvac_system_iteration_loop(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state): return 0
        if not self.is_initialized: return 0

        # Your MPC commanded airflow (different per zone)
        flow_targets = {
            "SPACE1-1": 0.18,
            "SPACE2-1": 0.10,
            "SPACE3-1": 0.12,
            "SPACE4-1": 0.14,
            "SPACE5-1": 0.16
        }

        # Dummy Reheater Temperature Targets in C
        reheat_targets = {
            "SPACE1-1": 12.0,
            "SPACE2-1": 12.0,
            "SPACE3-1": 12.0,
            "SPACE4-1": 12.0,
            "SPACE5-1": 12.0
        }

        # Override Central Cooling and Heating Coil Setpoints
        self.api.exchange.set_actuator_value(state, self.actuators["CC_Temp_SP"], 13.0)
        self.api.exchange.set_actuator_value(state, self.actuators["HC_Temp_SP"], 14.0)

        total_fan_flow = 0.0

        for z in self.zones:
            mpc_commanded_flow = flow_targets.get(z, 0.1)
            total_fan_flow += mpc_commanded_flow

            # Flow Actuation
            handle_sp = self.actuators.get(f"{z}_Flow_SP", -1)
            handle_max = self.actuators.get(f"{z}_Flow_MAX", -1)
            handle_min = self.actuators.get(f"{z}_Flow_MIN", -1)
            
            # THE TRIPLE CLAMP: Squeeze the node solver from all sides
            if handle_sp != -1 and handle_max != -1 and handle_min != -1:
                self.api.exchange.set_actuator_value(state, handle_max, mpc_commanded_flow) # Set Max first
                self.api.exchange.set_actuator_value(state, handle_min, mpc_commanded_flow) # Set Min second
                self.api.exchange.set_actuator_value(state, handle_sp, mpc_commanded_flow)  # Set SP last

            # Reheater Actuation
            handle_reheat = self.actuators.get(f"{z}_Reheat_SP", -1)
            if handle_reheat != -1:
                self.api.exchange.set_actuator_value(state, handle_reheat, reheat_targets.get(z, 22.0))

        return 0