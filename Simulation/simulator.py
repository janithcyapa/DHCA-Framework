# @title Setup Simulation Environment
def SetupSimulationEnv():
    """
    Initializes the simulation environment by installing necessary dependencies,
    configuring the EnergyPlus backend, and importing core utilities.
    """
    print("[SimEnv] : 🚀 Starting Environment Initialization...")

    # 1. Package Installation
    print("[SimEnv] : 📦 Installing required pip packages...")
    import subprocess as _subprocess
    import sys as _sys
    _subprocess.check_call([
        _sys.executable, "-m", "pip", "install", "-q", 
        "energy-plus-utility @ git+https://github.com/janithcyapa/energy-plus-utility.git@main", 
        "control", "simple-pid"
    ])

    # 2. Verification
    import importlib.metadata
    ver = importlib.metadata.version("energy-plus-utility")
    print(f"[SimEnv] : ✅ Verified 'energy-plus-utility' version: {ver}")


    # 3. EnergyPlus System Configuration
    print("[SimEnv] : ⚙️ Configuring EnergyPlus backend binaries...")
    from eplus import prepare_colab_eplus
    prepare_colab_eplus(silent=True)
    print("[SimEnv] : 🎉 EnergyPlus environment is ready.")


    # 4. Core Environment Imports
    print("[SimEnv] : 📚 Loading core modules into global namespace...")

    # Expose crucial libraries globally for the notebook cells
    global os, sys, shutil, Path, datetime, io, requests, urllib, subprocess, gc, traceback, types
    global pd, np, go, make_subplots, PID, EPlusUtil

    # Standard Library Imports
    import os, sys, shutil, io,datetime, requests, subprocess, gc, traceback, types
    from pathlib import Path
    import urllib.request
  
    # Data Science & Controls Infrastructure
    import pandas as pd
    import numpy as np
    import control as ct
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from simple_pid import PID

    # Domain Specific Utilities
    from eplus.core import EPlusUtil

    print("[SimEnv] : ✅ All dependencies successfully mapped and loaded.")
    print("[SimEnv] : 🌟 Environment Setup Complete! Ready for simulation.")

# @title Set Simulation Model
def SetSimulationModel(verbose=3):
    """
    Configures the EnergyPlus simulation model, fetches necessary assets,
    handles macro expansion for HVAC templates, and returns the simulator instance.
    """
    print("[SimEnv] : ⚙️ Setting up Simulation Model...")
    
    # 1. Environment and Path Initialization
    OUT_DIR = "/simulation/eplus_out"

    sim = EPlusUtil(verbose=verbose, out_dir=OUT_DIR)
    sim.reset_state()
    sim.delete_out_dir()
    sim.clear_eplus_outputs(patterns="eplusout.*")
    
    os.makedirs(OUT_DIR, exist_ok=True)
    
    home_dir = os.path.expanduser('~')
    eplus_install_dir = os.path.join(home_dir, "EnergyPlus-25-1-0")
    expand_objects_exe = os.path.join(eplus_install_dir, "ExpandObjects")
    local_template_source = os.path.join(eplus_install_dir, "ExampleFiles", "HVACTemplate-5ZonePTAC.idf")

    print(f"[SimEnv] : 📂 Using EnergyPlus structural binary path: {eplus_install_dir}")

    local_template = os.path.join(OUT_DIR, "in.idf")
    local_expanded = os.path.join(OUT_DIR, "expanded.idf")
    local_epw = os.path.join(OUT_DIR, "weather.epw")

    # 2. Asset Staging (IDF & EPW Weather Data)
    print(f"[SimEnv] : 📋 Copying baseline IDF template to workspace...")
    shutil.copy(local_template_source, local_template)

    url_epw = "https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/refs/heads/main/Simulation/System%20Models/Weather%20Files/LKA_Colombo-Katunayake.434500_SWERA.epw"
    print("[SimEnv] : 🌐 Fetching remote climatological data (EPW)...")
    urllib.request.urlretrieve(url_epw, local_epw)

    # 3. Executing ExpandObjects Macro Processing
    print("[SimEnv] : ⚡ Launching ExpandObjects to compile macro templates...")
    if not os.path.exists(expand_objects_exe):
        print(f"[SimEnv] : ❌ Processing halted. Execution binary missing at: {expand_objects_exe}")
        raise FileNotFoundError(f"Could not find ExpandObjects at {expand_objects_exe}")

    current_dir = os.getcwd()
    os.chdir(OUT_DIR)
    try:
        subprocess.run([expand_objects_exe], check=True, capture_output=True)
    finally:
        os.chdir(current_dir)

    if not os.path.exists(local_expanded):
        print("[SimEnv] : ❌ Macro compiler completed but failed to generate target output asset.")
        raise FileNotFoundError("ExpandObjects executed but failed to generate 'expanded.idf'.")
    
    print("[SimEnv] : ✅ Successfully generated expanded.idf component definitions.")

    # 4. Finalizing Simulator State
    print("[SimEnv] : 🔗 Injecting compiled model and weather runtime tracks into simulation engine...")
    sim.set_model(local_expanded, local_epw)
    
    print("[SimEnv] : 🎉 Simulation Model Environment completely configured and linked!")
    return sim

# @title Modify Simulation Model
def ModifySimulationModel(sim):
    """
    Configures the simulation engine output parameters, sets up custom target SQL outputs,
    and programmatically injects standalone humidifier sub-components into all thermal zones.
    """
    print("[SimEnv] : 🔧 Beginning Simulation Model Custom Modifications...")
    
    # 1. Output Infrastructure Configuration
    sim.ensure_output_sqlite()
    sim.prepare_run_with_co2(
        outdoor_co2_ppm=420.0,
        wipe_outputs=True,
        activate=True,
        reset=True
    )

    # 2. Variable Tracking Specification Configuration
    specs = [
        {"name": "Other Equipment Latent Heat Gain Rate", "key": "*"},
        {"name": "Site Outdoor Air Relative Humidity", "key": "*"},
        {"name": "Site Outdoor Air Humidity Ratio", "key": "*"},
        {"name": "Zone Outdoor Air Drybulb Temperature", "key": "*"},
        {"name": "Schedule Value", "key": "CO2-Outdoor-Actuated"},
        
        {"name": "Cooling Coil Total Cooling Rate", "key": "*"},
        {"name": "Heating Coil Heating Rate", "key": "*"},
        {"name": "Fan Electricity Rate", "key": "*"},

        {"name": "System Node Temperature", "key": "*"},
        {"name": "System Node Relative Humidity", "key": "*"},
        {"name": "System Node Humidity Ratio", "key": "*"},
        {"name": "System Node Mass Flow Rate", "key": "*"},
        {"name": "System Node CO2 Concentration", "key": "*"},

        {"name": "Zone Mean Air Temperature", "key": "*"},
        {"name": "Zone Air CO2 Concentration", "key": "*"},
        {"name": "Zone Air Relative Humidity", "key": "*"},
        {"name": "Zone Mean Radiant Temperature", "key": "*"},
        {"name": "Zone Mean Air Humidity Ratio", "key": "*"},
        {"name": "Zone Electric Equipment Total Heating Rate", "key": "*"},
        {"name": "Zone People Occupant Count", "key": "*"},
        
    ]
    sim.ensure_output_variables(specs, activate=True)

    # Initialize data cache vectors
    sim.sim_log_data = []
    sim.sim_current_data = []

    # 3. Reading Working IDF Workspace File
    with open(sim.idf, 'r') as f:
        idf_text = f.read()

    # 4. Programmatic Standalone Humidifier Macro Injection
    print("[SimEnv] : 💉 Injecting standalone humidification macro-blocks into all zones...")
    zones = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]
    
    for z in zones:
        humidifier_block = f"""
    Schedule:Constant,
    {z} Humidifier Cmd,       !- Name
    ,                         !- Schedule Type Limits Name (BLANK)
    0.0;                      !- Hourly Value

    OtherEquipment,
    {z} Standalone Humidifier, !- Name
    None,                     !- Fuel Type
    {z},                      !- Zone or ZoneList Name
    {z} Humidifier Cmd,       !- Schedule Name
    EquipmentLevel,           !- Design Level Calculation Method
    2500.0,                   !- Design Level {{W}}
    ,                         !- Power per Zone Floor Area
    ,                         !- Power per Person
    1.0,                      !- Fraction Latent (100% Moisture)
    0.0,                      !- Fraction Radiant
    0.0;                      !- Fraction Lost
    """
        idf_text += "\n" + humidifier_block

    # 5. Writing Modifications back to local IDF Workspace
    with open(sim.idf, 'w') as f:
        f.write(idf_text)

    print("[SimRun] : 🛑 Executing environment Dry Run...")
    sim.run_dry_run(include_ems_edd=True, reset=False, design_day=True)
    
    print("[SimEnv] : ✅ Standalone Humidifiers successfully injected globally.")
    print("[SimEnv] : 🌟 Model Modification Stage Complete!")

# @title Setup State Logger
def SetupStateLogger(sim):
    """
    Wraps the state logger definition, binds it to the simulation instance,
    and registers the EnergyPlus callback handler.
    """
    print("[SimEnv] : 📡 Initializing and binding Diagnostic State Logger...")

    def state_logger(self, state):
        try:
            if not self.exchange.api_data_fully_ready(state):
                return
            if self.exchange.warmup_flag(state):
                return

            # --- THE HEARTBEAT ---
            if not hasattr(self, '_logger_ticks'):
                self._logger_ticks = 0
                print("[Log]    : 🟢 [WOKE UP] The API successfully triggered the logger!")

            # Log once every day
            day = self.exchange.day_of_year(state)
            if getattr(self, '_last_log_date', None) != day:
                num_records = len(getattr(self, 'sim_log_data', []))
                print(f"[Log]    : 🗓️ Day {day} | Total Records: {num_records}")
                self._last_log_date = day

            # --- INITIALIZATION ---
            if not hasattr(self, '_handle_definitions'):
                print("[Log]    : 🔗 Registering output variable handles...")
                self._handle_definitions = {
                   'T_out': ("Zone Outdoor Air Drybulb Temperature", "SPACE1-1"),
                   'W_out': ("Site Outdoor Air Humidity Ratio", "Environment"),
                   'RH_out_%': ("Site Outdoor Air Relative Humidity", "Environment"),
                   'CO2_out': ("Schedule Value", "CO2-Outdoor-Actuated"),
                }

                for z in ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]:
                    # Zone States (x_i)
                    self._handle_definitions[f"{z}_T_in"] = ("Zone Mean Air Temperature", z)
                    self._handle_definitions[f"{z}_T_m"] = ("Zone Mean Radiant Temperature", z)
                    self._handle_definitions[f"{z}_W_in"] = ("Zone Mean Air Humidity Ratio", z)
                    self._handle_definitions[f"{z}_RH_%"] = ("Zone Air Relative Humidity", z)
                    self._handle_definitions[f"{z}_CO2_in"] = ("Zone Air CO2 Concentration", z)
                    # Time-Varying Parameters (p_i)
                    self._handle_definitions[f"{z}_Occ"] = ("Zone People Occupant Count", z)
                    self._handle_definitions[f"{z}_Q_equip"] = ("Zone Electric Equipment Total Heating Rate", z)

                    # PTAC Supply Parameters (S) & Hardware
                    self._handle_definitions[f"{z}_m_dot"] = ("System Node Mass Flow Rate", f"{z} PTAC SUPPLY INLET")
                    self._handle_definitions[f"{z}_T_supply"] = ("System Node Temperature", f"{z} PTAC SUPPLY INLET")
                    self._handle_definitions[f"{z}_Supply_RH_%"] = ("System Node Relative Humidity", f"{z} PTAC SUPPLY INLET")
                    self._handle_definitions[f"{z}_W_supply"] = ("System Node Humidity Ratio", f"{z} PTAC SUPPLY INLET")
                    self._handle_definitions[f"{z}_C_supply"] = ("System Node CO2 Concentration", f"{z} PTAC SUPPLY INLET")
         
                    self._handle_definitions[f"{z}_Mix_T"] = ("System Node Temperature", f"{z} PTAC MIXED AIR OUTLET")
                    self._handle_definitions[f"{z}_Mix_RH_%"] = ("System Node Relative Humidity", f"{z} PTAC MIXED AIR OUTLET")
                    self._handle_definitions[f"{z}_Mix_C"] = ("System Node CO2 Concentration", f"{z} PTAC MIXED AIR OUTLET")

                    self._handle_definitions[f"{z}_Cool_Rate"] = ("Cooling Coil Total Cooling Rate", f"{z} PTAC COOLING COIL")
                    self._handle_definitions[f"{z}_Heat_Rate"] = ("Heating Coil Heating Rate", f"{z} PTAC HEATING COIL")
                    self._handle_definitions[f"{z}_Fan_Power"] = ("Fan Electricity Rate", f"{z} PTAC SUPPLY FAN")

                self._var_handles = {key: -1 for key in self._handle_definitions.keys()}
                self._hum_act_handles = {z: -1 for z in ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]}

            # --- RUNTIME EXTRACTION ---
            day = self.exchange.day_of_year(state)
            time_now = self.exchange.current_time(state)
            hours, mins = divmod(int(time_now * 60), 60)
            BASE_YEAR = 2026
            sim_datetime = datetime.datetime(BASE_YEAR, 1, 1) + datetime.timedelta(days=day - 1, hours=hours, minutes=mins)            
            
            row = {
                # "timestamp": f"Day {day:03d} {hours:02d}:{mins:02d}",
                "timestamp" : int(sim_datetime.timestamp()),
                "day": day, "hour": hours, "minute": mins, "time_decimal": time_now
            }

            # 1. Fetch Variables
            for key, (type_name, intended_key) in self._handle_definitions.items():
                if self._var_handles[key] <= 0:
                    keys_to_test = list(dict.fromkeys([intended_key, intended_key.upper(), intended_key.title(), ""]))
                    for k in keys_to_test:
                        h = self.exchange.get_variable_handle(state, type_name, k)
                        if h > 0:
                            self._var_handles[key] = h
                            break
                handle = self._var_handles[key]
                row[key] = self.exchange.get_variable_value(state, handle) if handle > 0 else np.nan

            # 2. Fetch Humidifiers
            for z in ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]:
                if self._hum_act_handles[z] <= 0:
                    self._hum_act_handles[z] = self.exchange.get_actuator_handle(state, "Schedule:Constant", "Schedule Value", f"{z} HUMIDIFIER CMD")

                h_act = self._hum_act_handles[z]
                if h_act > 0:
                    cmd_fraction = self.exchange.get_actuator_value(state, h_act)
                    row[f"{z}_Hum_Rate"] = cmd_fraction * 2500.0
                else:
                    row[f"{z}_Hum_Rate"] = 0.0
            
            # --- INJECT PREDICTIONS FROM RC MODEL ---
            if hasattr(self, 'model_estimations'):
                for z in ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]:
                    if z in self.model_estimations:
                        est = self.model_estimations[z]
                        row[f"{z}_T_in_pred"] = est.get("T_in_pred", np.nan)
                        row[f"{z}_T_m_pred"] = est.get("T_m_pred", np.nan)
                        row[f"{z}_W_in_pred"] = est.get("W_in_pred", np.nan)
                        row[f"{z}_C_in_pred"] = est.get("C_in_pred", np.nan)
                    else:
                        # Fallback if no prediction is available for this zone yet
                        row[f"{z}_T_in_pred"] = np.nan
                        row[f"{z}_T_m_pred"]  = np.nan
                        row[f"{z}_W_in_pred"] = np.nan
                        row[f"{z}_C_in_pred"] = np.nan

            # --- SAVE DATA ---
            # Append to the historical log for post-simulation analysis
            self.sim_log_data.append(row)
            
            # Overwrite current data so controllers/EKF always pull the freshest single state
            self.sim_current_data = [row] 

        except Exception as e:
            # IF ANYTHING CRASHES, YELL ABOUT IT.
            print(f"\n[Log]     : ❌ [FATAL CRASH] {e}")
            traceback.print_exc()

    # Bind the method to the simulation instance dynamically
    sim.state_logger = types.MethodType(state_logger, sim)
    
    # Register the callback hook with EnergyPlus
    sim.register_handlers("after_zone", [{"method_name": "state_logger"}])
    print("[SimEnv] : ✅ Diagnostic Logger globally registered and armed.")

# @title Setup Occupancy Injector
def SetupOccupancyInjector(sim):
    """
    Downloads historical occupancy schedules, pre-allocates localized scaling tracking structures,
    and hooks a reactive load actuator injection callback loop into EnergyPlus.
    """
    print("[SimEnv] : 👥 Initializing and binding Occupancy Injector Engine...")
    
    csv_url="https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/refs/heads/main/Simulation/System%20Models/Weather%20Files/Occupancy_Dataset.csv"
    # 1. Fetch and Preload Temporal Occupancy Datasets
    print("[SimEnv] : 🌐 Fetching remote scheduling matrix from repository tracker...")
    try:
        resp = requests.get(csv_url)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        midnight_start = df['timestamp'].iloc[0].normalize()
        df['rel_seconds'] = (df['timestamp'] - midnight_start).dt.total_seconds()
        
        sim._occ_duration_sec = 86400.0
        df = df.set_index('rel_seconds')
        sim._preloaded_occ_df = df.drop(columns=['timestamp'])
        print(f"[SimEnv] : ✅ Occupancy data array successfully cached ({len(df)} historical rows mapped).")
    except Exception as e:
        print(f"[SimEnv] : ❌ Initialization halted. Failed to parse scheduling matrix: {e}")
        return

    # 2. Define Runtime Actuator Injection Engine Callback Loop
    def people_injector(self, state):
        try:
            if not self.exchange.api_data_fully_ready(state) or self.exchange.warmup_flag(state):
                return

            # Spatial Object-Handle Registration and Verification Step
            if not hasattr(self, '_fast_injector_ready'):
                if not hasattr(self, '_preloaded_occ_df'):
                    self._fast_injector_ready = False
                    return
                print("[Occ]    : 🔗 Processing zone occupancy maps and linking handles...")
                self._zone_occ_rules = {
                    "SPACE1-1": {"source": "SPACE1-1", "mult": 1.0,  "min": 0, "max": 5},
                    "SPACE2-1": {"source": "SPACE1-1", "mult": 1.5,  "min": 0, "max": 4},
                    "SPACE3-1": {"source": "SPACE1-1", "mult": 0.4,  "min": 0, "max": 1},
                    "SPACE4-1": {"source": "SPACE1-1", "mult": 1.2,  "min": 0, "max": 3},
                    "SPACE5-1": {"source": "SPACE1-1", "mult": 2.0,  "min": 0, "max": 6},
                }
                self._people_handles = {}
                target_zones = list(self._zone_occ_rules.keys())
                
                try:
                    ep_people_names = self.exchange.get_object_names(state, "People") or []
                except Exception:
                    ep_people_names = []

                for z in target_zones:
                    matched_people = [p for p in ep_people_names if z.replace(" ", "").lower() in p.replace(" ", "").lower()]
                    handles = [self.exchange.get_actuator_handle(state, "People", "Number of People", p) for p in matched_people if self.exchange.get_actuator_handle(state, "People", "Number of People", p) != -1]
                    if handles:
                        self._people_handles[z] = handles

                day = self.exchange.day_of_year(state)
                time_hr = self.exchange.current_time(state)
                self._sim_start_date = datetime.datetime(2002, 1, 1) + datetime.timedelta(days=day - 1, seconds=(int(time_hr * 3600)))
                self._fast_injector_ready = True
                print("[Occ]    : 🟢 [WOKE UP] Occupancy tracking actuator loops mapped cleanly into global namespace.")

            if not self._fast_injector_ready or getattr(self, '_occ_duration_sec', 0) == 0:
                return

            # Core Runtime Index Position Sync Tracking
            day = self.exchange.day_of_year(state)
            time_hr = self.exchange.current_time(state)
            current_date = datetime.datetime(2002, 1, 1) + datetime.timedelta(days=day - 1, seconds=(int(time_hr * 3600)))
            elapsed_seconds = (current_date - self._sim_start_date).total_seconds()
            loop_sec = elapsed_seconds % self._occ_duration_sec

            df = self._preloaded_occ_df
            valid_indices = df.index[df.index <= loop_sec]
            target_idx = df.index[0] if len(valid_indices) == 0 else valid_indices[-1]
            row = df.loc[target_idx]

            # Matrix Calculations & Actuator Driving Updates
            for z, handles in self._people_handles.items():
                rule = self._zone_occ_rules.get(z)
                if rule and rule["source"] in row:
                    base_val = float(row[rule["source"]])
                    val = 0.0 if base_val == 0 else float(np.clip(np.ceil(base_val * rule["mult"]), rule["min"], rule["max"]))
                    for h in handles:
                        self.exchange.set_actuator_value(state, h, val / len(handles))
                        
        except Exception as e:
            print(f"\n[Occ]     : ❌ [FATAL OCCUPANCY INJECTOR CRASH] {e}")
            traceback.print_exc()

    # Dynamic system instance method binding configuration
    sim.people_injector = types.MethodType(people_injector, sim)
    sim.register_handlers("begin", [{"method_name": "people_injector"}])
    print("[SimEnv] : ✅ Occupancy Injector globally registered and armed.")

# @title Setup Actuator Controller
def SetupActuatorController(sim):
    """
    Wraps the actuator execution block, binds it to the simulation instance,
    and hooks the runtime setpoint tracking loop into EnergyPlus before HVAC processing.
    """
    print("[SimEnv] : 🎛️ Initializing and binding Actuator Controller Engine...")

    def actuator_controller(self, state):
        try:
            if not self.exchange.api_data_fully_ready(state) or self.exchange.warmup_flag(state):
                return

            # Spatial Object-Handle Registration Step
            if not hasattr(self, 'actuators_ready'):
                print("[Ctrl]   : 🔗 Mapping HVAC actuator tracks and linking hardware handles...")
                self.actuators_setpoint = {}
                
                for z in ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]:
                    self.actuators_setpoint[f"{z}_Fan"] = self.exchange.get_actuator_handle(state, "Fan", "Fan Air Mass Flow Rate", f"{z} PTAC SUPPLY FAN")
                    self.actuators_setpoint[f"{z}_Temp"] = self.exchange.get_actuator_handle(state, "System Node Setpoint", "Temperature Setpoint", f"{z} PTAC SUPPLY INLET")
                    self.actuators_setpoint[f"{z}_OA"] = self.exchange.get_actuator_handle(state, "System Node Setpoint", "Mass Flow Rate Setpoint", f"{z} PTAC OUTSIDE AIR INLET")
                    self.actuators_setpoint[f"{z}_Tstat_Clg"] = self.exchange.get_actuator_handle(state, "Zone Temperature Control", "Cooling Setpoint", z)
                    self.actuators_setpoint[f"{z}_Tstat_Htg"] = self.exchange.get_actuator_handle(state, "Zone Temperature Control", "Heating Setpoint", z)

                    h_hum = self.exchange.get_actuator_handle(state, "Schedule:Constant", "Schedule Value", f"{z} Humidifier Cmd")
                    if h_hum > 0: 
                        self.actuators_setpoint[f"{z}_Humidifier"] = h_hum

                self.actuators_ready = True
                print("[Ctrl]   : 🟢 [WOKE UP] Actuator endpoints linked cleanly. Ready for command dispatch.")

            # Dynamic Command Dispatch Processing Loop
            if hasattr(self, 'current_mpc_commands'):
                for z in ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]:
                    cmd = self.current_mpc_commands.get(z, {})
                    
                    if self.actuators_setpoint.get(f"{z}_Fan", -1) > 0:       
                        self.exchange.set_actuator_value(state, self.actuators_setpoint[f"{z}_Fan"], cmd.get("flow", 0.0))
                    if self.actuators_setpoint.get(f"{z}_Temp", -1) > 0:      
                        self.exchange.set_actuator_value(state, self.actuators_setpoint[f"{z}_Temp"], cmd.get("temp", 24.0))
                    if self.actuators_setpoint.get(f"{z}_OA", -1) > 0:        
                        self.exchange.set_actuator_value(state, self.actuators_setpoint[f"{z}_OA"], cmd.get("oa_flow", 0.0))
                    if self.actuators_setpoint.get(f"{z}_Humidifier", -1) > 0: 
                        self.exchange.set_actuator_value(state, self.actuators_setpoint[f"{z}_Humidifier"], cmd.get("humidifier", 0.0))
                    if self.actuators_setpoint.get(f"{z}_Tstat_Clg", -1) > 0: 
                        self.exchange.set_actuator_value(state, self.actuators_setpoint[f"{z}_Tstat_Clg"], cmd.get("clg_stp", 100.0))
                    if self.actuators_setpoint.get(f"{z}_Tstat_Htg", -1) > 0: 
                        self.exchange.set_actuator_value(state, self.actuators_setpoint[f"{z}_Tstat_Htg"], cmd.get("htg_stp", -50.0))

        except Exception as e:
            print(f"\n[Ctrl]    : ❌ [FATAL ACTUATOR CONTROLLER CRASH] {e}")
            import traceback
            traceback.print_exc()

    # Dynamic system instance method binding configuration
    sim.actuator_controller = types.MethodType(actuator_controller, sim)

    # Register only the actuator execution block to the before_hvac pipeline
    sim.register_handlers("before_hvac", [
        {"method_name": "actuator_controller"}
    ])
    print("[SimEnv] : ✅ Actuator Controller globally registered and armed.")

# @title Run Simulation
def RunSimulation(sim, num_days=7, rate=1):
    """
    Inspects runtime handlers, automatically maps numerical target days to calendar 
    dates and minute intervals to hourly timesteps, then executes the EnergyPlus pipeline.
    
    Parameters:
    - num_days: Integer from 1 to 365 (e.g., 7 for 1 week, 365 for full year)
    - rate_min: Step interval frequency per hour
    """
    import datetime

    print("[SimRun] : 🔍 Inspecting registered API callback pipelines...")
    pipelines = [
        'begin', 'before_hvac', 'inside_iter', 'after_hvac', 
        'after_zone', 'after_warmup', 'after_get_input'
    ]
    for p in pipelines:
        handlers = sim.list_handlers(p)
        print(f"[SimRun] :    ↳ {p:<16} → {handlers}")

    # 1. Handle Temporal Constraints Boundary Validation
    if not (1 <= num_days <= 365):
        print(f"[SimRun] : ❌ Range Error: num_days must be between 1 and 365. Received: {num_days}")
        return

    # Map sequential days to an explicit calendar target date
    base_date = datetime.datetime(2002, 1, 1)
    end_date = base_date + datetime.timedelta(days=num_days - 1)
    end_month, end_day = end_date.month, end_date.day

    # 2. Map Minute Sampling Rate to Hourly Timesteps 
    # (e.g., 1 min interval = 60 steps/hr || 5 min interval = 12 steps/hr)


    # 3. Protective Dry Run Execution
    # print("[SimRun] : 🛑 Executing environment Dry Run...")
    # sim.run_dry_run(include_ems_edd=True, reset=False, design_day=True)

    # 4. Inject Dynamic Configuration Parameters
    print(f"[SimRun] : 🗓️ Setting runtime window: Jan 01 to {end_date.strftime('%b %d')} ({num_days} Days total)")
    print(f"[SimRun] : ⏱️ Setting execution frequency ({rate} steps/hour)")
    
    sim.set_simulation_params(
        start=(1, 1),
        end=(end_month, end_day),
        timestep_per_hour=rate,
        start_day_of_week="Sunday",
    )

    # 5. Launch Main Processing Engine
    print("[SimRun] : 🚀 Starting EnergyPlus Simulation Execution Loop...")
    res = sim.run_annual()

    # 6. Evaluate Termination Signals
    if res == 0:
        print("[SimRun] : 🎉 Simulation execution finished successfully with zero exit errors!")
    else:
        print("[SimRun] : ❌ Simulation terminated with errors. Parsing stack traces...")
        err_path = Path(sim.out_dir) / "eplusout.err"
        if err_path.exists():
            print("\n" + "="*50 + "\n--- EnergyPlus Error Log --- \n" + "="*50)
            with open(err_path, 'r') as f:
                print(f.read()[-4000:])
            print("="*50)
        else:
            print(f"[SimRun] : ⚠️ Error logging asset missing at expected destination: {err_path}")
    
# @title Extract Simulation Data
def ExtractSimulationData(sim, base_filename="Simulation_Log.csv"):
    """
    Parses cached historical telemetry matrices from the state logger, normalizes the continuous 
    simulation timeline into absolute hours, generates an epoch-timestamped filename, 
    and exports data assets to CSV.
    """
    import time
    from pathlib import Path
    
    print("[Data] : 📊 Initiating simulation trajectory data extraction...")
    
    # 1. Verify log existence and data availability
    if not hasattr(sim, 'sim_log_data') or len(sim.sim_log_data) == 0:
        print("[Data] : ❌ Processing halted: Log cache is completely empty! The state_logger callback did not fire.")
        return None

    try:
        # 2. Compile dictionary frames into a structured Pandas DataFrame
        df_log = pd.DataFrame(sim.sim_log_data)
        
        # 3. Normalize calendar frames into a relative continuous time vector (Hours)
        df_log['Time_Hours'] = (df_log['day'] - df_log['day'].iloc[0]) * 24 + df_log['time_decimal']
        df_log.set_index('Time_Hours', inplace=True)
        
        # 4. Generate Dynamic Epoch-Timestamped Filenames
        epoch_now = int(time.time())
        path_obj = Path(base_filename)
        timestamped_filename = f"{path_obj.stem}_{epoch_now}{path_obj.suffix}"
        
        # 5. Commit data coordinates to persistent drive storage
        df_log.to_csv(timestamped_filename, index=True)
        
        print(f"[Data] : ✅ Target data extracted! Saved tracking data assets to: {timestamped_filename}")
        print(f"[Data] : 💾 Total operational timesteps compiled: {len(df_log)}")
        
        # 6. Render interactive layout inside the VS Code notebook runtime
        try:
            from IPython.display import display
            display(df_log)
        except ImportError:
            print(df_log.head())
            
        return df_log, timestamped_filename

    except Exception as e:
        print(f"[Data] : ❌ Unexpected failure during dataset serialization: {e}")
        import traceback
        traceback.print_exc()
        return None

# @title Generate Simulation Plots
def GenerateSimulationPlots(df_log, target_zone="SPACE1-1", layout_config=None):
    """
    Generates dynamic, highly configurable subplots from simulation logging dataframes 
    using a flexible dictionary layout blueprint definition.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    print(f"[Plot] : 📊 Initializing modular telemetry plotting engine for: {target_zone}")
    
    # Use default layout if none is passed
    if layout_config is None:
        layout_config = GetDefaultPTACConfig()
        
    df_plot = df_log.sort_index()
    
    # 1. Synthesize timeline human-readable marker tags
    try:
        time_labels = [f"Day {int(d):02d} {int(h):02d}:{int(m):02d}"
                       for d, h, m in zip(df_plot['day'], df_plot['hour'], df_plot['minute'])]
    except KeyError:
        # Fallback if baseline timing arrays are omitted
        time_labels = [f"Step {idx}" for idx in df_plot.index]

    # 2. Dynamically extract structural configurations
    subplots_def = layout_config.get("subplots", [])
    num_rows = len(subplots_def)
    
    # Extract titles and target axis specs (handling secondary y tracks)
    subplot_titles = [sub.get("title", "").format(target_zone=target_zone) for sub in subplots_def]
    subplot_specs = [[{"secondary_y": sub.get("secondary_y", False)}] for sub in subplots_def]

    # 3. Construct Figure Pipeline Axis Layouts
    fig = make_subplots(
        rows=num_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=layout_config.get("vertical_spacing", 0.04),
        specs=subplot_specs,
        subplot_titles=subplot_titles
    )

    # 4. Programmatic Trace Mapping Execution Block
    for row_idx, sub in enumerate(subplots_def, start=1):
        for trace in sub.get("traces", []):
            col_target = trace.get("col")
            
            # Dynamic fallback list checking layout (e.g., support alternate names)
            col_candidates = [col_target] if isinstance(col_target, str) else col_target
            active_col = None
            
            for candidate in col_candidates:
                formatted_candidate = candidate.format(target_zone=target_zone)
                if formatted_candidate in df_plot.columns:
                    active_col = formatted_candidate
                    break
                    
            if active_col is None:
                print(f"[Plot] : ⚠️ Variable tracking match skipped: Trace '{trace.get('name')}' missing column vectors.")
                continue

            # Inject localized component specifications
            fig.add_trace(
                go.Scatter(
                    x=df_plot.index,
                    y=df_plot[active_col],
                    name=trace.get("name"),
                    legendgroup=sub.get("group_id", f"row_{row_idx}"),
                    line=dict(
                        color=trace.get("color"),
                        dash=trace.get("dash"),
                        width=trace.get("width", 2)
                    ),
                    fill=trace.get("fill")
                ),
                row=row_idx, col=1, 
                secondary_y=trace.get("sec_y", False)
            )

        # 5. Localized Axis Titles Styling Injection
        fig.update_yaxes(title_text=sub.get("y_title", ""), row=row_idx, col=1, secondary_y=False)
        if sub.get("secondary_y", False):
            fig.update_yaxes(
                title_text=sub.get("y_title_secondary", ""), 
                row=row_idx, col=1, 
                secondary_y=True,
                range=sub.get("secondary_range", None)
            )

    # 6. Global Layout Canvas Definitions Config
    global_title = layout_config.get("global_title", "Simulation Log Dashboard").format(target_zone=target_zone)
    fig.update_layout(
        template=layout_config.get("template", "plotly_dark"),
        height=layout_config.get("height", 300 * num_rows),
        hovermode="x unified",
        title=global_title,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1)
    )

    # 7. Adaptive Timeline Ticks Decimation Step (Prevents trace overlaps)
    sample_step = max(1, len(df_plot) // 15)  # Auto-select up to 15 uniform timeline coordinates
    tick_idx = df_plot.index[::sample_step]
    tick_lbl = [time_labels[i] for i in range(0, len(time_labels), sample_step)]
    
    fig.update_xaxes(showticklabels=True, tickmode='array', tickvals=tick_idx, ticktext=tick_lbl, tickangle=30)
    
    print("[Plot] : ✅ Canvas rendering complete. Dispatched dashboard view.")
    fig.show()
    return fig
def GetDefaultPTACConfig():
    """
    Defines the baseline 6-row comprehensive configuration dictionary for zone 
    thermodynamic analysis plots.
    """
    return {
        "global_title": "Detailed PTAC & Zone Diagnostic: {target_zone}",
        "height": 1800,
        "template": "plotly_dark",
        "vertical_spacing": 0.04,
        "subplots": [
            {
                "title": "1. Temperature Profile ({target_zone})",
                "y_title": "Temp (°C)",
                "group_id": "temp",
                "traces": [
                    {"col": "T_out", "name": "T_Ambient", "color": "white", "dash": "dash"},
                    {"col": "{target_zone}_Mix_T", "name": "T_Mixed (Pre-Coil)", "color": "gray"},
                    {"col": "{target_zone}_T_supply", "name": "T_Supply (Into Zone)", "color": "cyan"},
                    {"col": "{target_zone}_T_in", "name": "T_Zone (Room)", "color": "#FF5733"}
                ]
            },
            {
                "title": "2. Moisture Dynamics (Relative Humidity %)",
                "y_title": "RH (%)",
                "group_id": "moist",
                "traces": [
                    {"col": "RH_out_%", "name": "RH_Ambient", "color": "white", "dash": "dash"},
                    {"col": "{target_zone}_Mix_RH_%", "name": "RH_Mixed (Pre-Coil)", "color": "gray"},
                    {"col": ["{target_zone}_Supply_RH_%", "{target_zone}_RH_%_supply"], "name": "RH_Supply (Into Zone)", "color": "cyan"},
                    {"col": "{target_zone}_RH_%", "name": "RH_Zone (Room)", "color": "#33FF57"}
                ]
            },
            {
                "title": "3. IAQ & Occupancy (CO2 Concentration)",
                "y_title": "CO2 (ppm)",
                "secondary_y": True,
                "y_title_secondary": "People",
                "secondary_range": [0, 10],
                "group_id": "iaq",
                "traces": [
                    {"col": "CO2_out", "name": "CO2_Ambient", "color": "white", "dash": "dash"},
                    {"col": "{target_zone}_Mix_C", "name": "CO2_Mixed", "color": "gray"},
                    {"col": "{target_zone}_C_supply", "name": "CO2_Supply", "color": "cyan"},
                    {"col": "{target_zone}_CO2_in", "name": "CO2_Zone", "color": "#3357FF"},
                    {"col": "{target_zone}_Occ", "name": "Occupancy Count", "color": "yellow", "sec_y": True}
                ]
            },
            {
                "title": "4. Supply Air Mass Flow Rate",
                "y_title": "Flow (kg/s)",
                "group_id": "flow",
                "traces": [
                    {"col": "{target_zone}_m_dot", "name": "Mass Flow Rate", "color": "#00f2ff", "fill": "tozeroy"}
                ]
            },
            {
                "title": "5. Thermal Output (PTAC Sensible & Humidifier Latent)",
                "y_title": "Thermal (Watts)",
                "group_id": "pwr_t",
                "traces": [
                    {"col": "{target_zone}_Cool_Rate", "name": "Cooling Rate (Sensible)", "color": "blue", "fill": "tozeroy"},
                    {"col": "{target_zone}_Heat_Rate", "name": "Heating Rate (Sensible)", "color": "red", "fill": "tozeroy"},
                    {"col": "{target_zone}_Hum_Rate", "name": "Humidifier Rate (Latent)", "color": "#B200FF", "fill": "tozeroy"}
                ]
            },
            {
                "title": "6. Component Electrical Power",
                "y_title": "Electric (Watts)",
                "group_id": "pwr_e",
                "traces": [
                    {"col": "{target_zone}_Fan_Power", "name": "Fan Power", "color": "green", "fill": "tozeroy"}
                ]
            }
        ]
    }

# @title Setup Predictive RC Model (With Debugging)
def SetupPredictiveModel(sim, target_zone="SPACE1-1", debug_mode=True):

    print(f"[SimEnv] : 🧠 Initializing Predictive RC Model Engine (DEBUG: {debug_mode})...")

    def zone_model(self, state):
        try:
            # Silently exit if E+ isn't ready, but log it if we are in extreme debug mode
            if not self.exchange.api_data_fully_ready(state):
                return
            if self.exchange.warmup_flag(state):
                return
                
            zone_id = target_zone

            # Time Stamping
            day = self.exchange.day_of_year(state)
            time = self.exchange.current_time(state)
            abs_time = (day * 24.0) + time

            if not hasattr(self, 'zones'):
                self.zones = {}
            if not hasattr(self, 'model_estimations'):
                self.model_estimations = {}

            if debug_mode:
                print(f"\n--- [DEBUG-RC] Timestep Triggered | Day: {day} | Hour: {time:.2f} ---")

            # --- Initialize Zone ---
            if zone_id not in self.zones:
                if debug_mode: print(f"[DEBUG-RC] First pass detected for {zone_id}. Generating handles...")
                raw_params = self.get_zone_thermal_parameters()[zone_id]
                
                handles = {
                    "T_in": self.exchange.get_variable_handle(state, "Zone Mean Air Temperature", zone_id),
                    "T_m": self.exchange.get_variable_handle(state, "Zone Mean Radiant Temperature", zone_id),
                    "W_in": self.exchange.get_variable_handle(state, "Zone Mean Air Humidity Ratio", zone_id),
                    "CO2_in": self.exchange.get_variable_handle(state, "Zone Air CO2 Concentration", zone_id),
                    "N_occ": self.exchange.get_variable_handle(state, "Zone People Occupant Count", zone_id),
                    "T_out": self.exchange.get_variable_handle(state, "Zone Outdoor Air Drybulb Temperature", zone_id),
                    "Q_equip": self.exchange.get_variable_handle(state, "Zone Electric Equipment Total Heating Rate", zone_id),
                    "m_dot": self.exchange.get_variable_handle(state, "System Node Mass Flow Rate", f"{zone_id} PTAC SUPPLY INLET"),
                    "T_s": self.exchange.get_variable_handle(state, "System Node Temperature", f"{zone_id} PTAC SUPPLY INLET"),
                    "W_s": self.exchange.get_variable_handle(state, "System Node Humidity Ratio", f"{zone_id} PTAC SUPPLY INLET"),
                    "C_s": self.exchange.get_variable_handle(state, "System Node CO2 Concentration", f"{zone_id} PTAC SUPPLY INLET"),
                }

                # --- VALIDATE HANDLES ---
                if debug_mode:
                    missing_handles = [k for k, v in handles.items() if v <= 0] # 0 or -1 usually indicates missing
                    if missing_handles:
                        print(f"⚠️ [DEBUG-WARN] Missing IDF Outputs for {zone_id}: {missing_handles}")
                        print("    Ensure these are defined in your Output:Variable list in the IDF!")

                inv_R_env_ext = 0.0
                R_env_gnd = None
                adj_zones = []

                for b in raw_params["boundaries"]:
                    target = b["target"]
                    r_abs = float(b["R_absolute_K_W"])
                    if target == "Ground": R_env_gnd = r_abs
                    elif target == "Environment" or b["boundary_condition"] == "outdoors": inv_R_env_ext += (1.0 / r_abs)
                    else: adj_zones.append({ "zone": target, "R_env": r_abs, "handle_T_in": self.exchange.get_variable_handle( state, "Zone Mean Air Temperature", target )})
                R_env_ext = 1.0 / inv_R_env_ext if inv_R_env_ext > 0 else float('inf')

                # --- Core Dynamics ---
                def _dynamics(t, x, u, params):
                    T_in, T_m, W_in, C_in = x 
                    V_dot_s = float(u[0]) 

                    rho_air, cp_air = 1.204, 1006.0
                    q_person, g_w_person, g_co2_person = 100.0, 5e-5, 1e-5
                    R_env_ext = float(params.get('R_env_ext', float('inf')))
                    R_env_gnd = float(params.get('R_env_gnd', float('inf')))
                    R_int = float(params['R_int'])
                    C_air = float(params['C_air'])
                    C_mass = float(params['C_mass'])
                    M_air = float(params['M_air'])
                    V_room = float(params['V_room'])

                    T_s, W_s, C_s = params['T_s'], params['W_s'], params['C_s']
                    N_occ, Q_equip, T_out = params['N_occ'], params['Q_equip'], params['T_out']
                    d_T, d_W, d_C = params['d_T'], params['d_W'], params['d_C'] 
                    
                    q_env = (T_out - T_in) / R_env_ext if R_env_ext < float('inf') else 0.0
                    q_gnd = (22.0 - T_in) / R_env_gnd if R_env_gnd < float('inf') else 0.0
                    q_adj = sum([(float(adj['T_in']) - float(T_in)) / float(adj['R_env']) for adj in params['adj_zones']])
                        
                    q_mass = (T_m - T_in) / R_int
                    q_int = (N_occ * q_person) + Q_equip
                    q_s = rho_air * V_dot_s * cp_air * (T_s - T_in)
                    
                    dT_in_dt = (q_env + q_gnd + q_adj + q_mass + q_int + q_s + d_T) / C_air
                    dT_m_dt = (T_in - T_m) / ( C_mass * R_int)
                    
                    dot_m_s = rho_air * V_dot_s
                    dW_in_dt = (N_occ * g_w_person + dot_m_s * (W_s - W_in) + d_W) / M_air
                    dC_in_dt = (N_occ * g_co2_person + V_dot_s * (C_s - C_in) + d_C) / V_room

                    return np.array([dT_in_dt, dT_m_dt, dW_in_dt, dC_in_dt], dtype=float).flatten()

                def _outputs(t, x, u, params):
                    return [x[0], x[1], x[2], x[3]]

                sys_ode = ct.NonlinearIOSystem(
                    _dynamics, _outputs,
                    inputs=['V_dot_s'],
                    outputs=['T_in_obs','T_m_obs', 'W_in_obs', 'C_in_obs'],
                    states=['T_in', 'T_m', 'W_in', 'C_in'],
                    name=f'sys_{zone_id}'
                )

                self.zones[zone_id] = types.SimpleNamespace(
                    last_time=abs_time, V_room=float(raw_params['V_room']),
                    M_air=float(raw_params['M_air']), C_air=float(raw_params['C_air']),
                    C_mass=float(raw_params['C_mass']), R_int=float(raw_params['R_int']),
                    R_env_gnd=R_env_gnd, R_env_ext=R_env_ext, adj_zones=adj_zones,
                    handles=handles, sys_ode=sys_ode
                )
                print(f"[Model]  : ✅ System Dynamics initialized for {zone_id}")

            else:
                self.zones[zone_id].last_time = abs_time

            z = self.zones[zone_id]
            
            # Runtime Variable Fetching
            m_dot_current = self.exchange.get_variable_value(state, z.handles["m_dot"])
            v_dot_current = m_dot_current / 1.204 
            u_current = [v_dot_current]
            
            current_adj_zones = [{
                'T_in': self.exchange.get_variable_value(state, adj["handle_T_in"]),
                'R_env': adj["R_env"]
            } for adj in z.adj_zones]

            current_params = {
                'C_air': z.C_air, 'C_mass': z.C_mass,
                'R_env_ext': z.R_env_ext, 'R_env_gnd':z.R_env_gnd,
                'R_int': z.R_int, 'M_air': z.M_air, 'V_room': z.V_room,
                'T_out': self.exchange.get_variable_value(state, z.handles["T_out"]), 
                'N_occ': self.exchange.get_variable_value(state, z.handles["N_occ"]),
                'Q_equip': self.exchange.get_variable_value(state, z.handles["Q_equip"]),
                'T_s': self.exchange.get_variable_value(state, z.handles["T_s"]),
                'W_s': self.exchange.get_variable_value(state, z.handles["W_s"]),
                'C_s': self.exchange.get_variable_value(state, z.handles["C_s"]),
                'd_T': 0.0, 'd_W': 0.0, 'd_C': 0.0,
                'adj_zones': current_adj_zones 
            }

            x_solver = [
                self.exchange.get_variable_value(state, z.handles["T_in"]),
                self.exchange.get_variable_value(state, z.handles["T_m"]),
                self.exchange.get_variable_value(state, z.handles["W_in"]),
                self.exchange.get_variable_value(state, z.handles["CO2_in"])
            ]

            dt_hours = self.exchange.system_time_step(state)
            if dt_hours == 0: 
                dt_hours = self.exchange.zone_time_step(state)
            time_vector = [0, dt_hours * 3600.0]

            if debug_mode:
                print(f"[DEBUG-RC] dt_hours = {dt_hours:.4f} | time_vector = {time_vector}")
                print(f"[DEBUG-RC] Initial States (X0): T_in={x_solver[0]:.2f}, T_m={x_solver[1]:.2f}, W_in={x_solver[2]:.5f}, CO2={x_solver[3]:.1f}")
                print(f"[DEBUG-RC] Control Inputs (U): m_dot={m_dot_current:.4f}, V_dot={v_dot_current:.4f}")
                print(f"[DEBUG-RC] Dynamic Params: T_out={current_params['T_out']:.2f}, N_occ={current_params['N_occ']}, Q_eq={current_params['Q_equip']:.1f}")

            # Solve the ODE
            response = ct.input_output_response(z.sys_ode, time_vector, U=u_current, X0=x_solver, params=current_params)
            x_predicted_next = response.states[:, -1]

            if debug_mode:
                print(f"[DEBUG-RC] Pred Next States: T_in_pred={x_predicted_next[0]:.2f}, T_m_pred={x_predicted_next[1]:.2f}")

            # Save the estimation for the State Logger
            self.model_estimations[zone_id] = {
                "T_in_pred": x_predicted_next[0],
                "T_m_pred": x_predicted_next[1],
                "W_in_pred": x_predicted_next[2],
                "C_in_pred": x_predicted_next[3]
            }

        except Exception as e:
            print(f"\n[Model]   : ❌ [FATAL PREDICTION CRASH] {e}")
            if debug_mode:
                traceback.print_exc()

    sim.zone_model = types.MethodType(zone_model, sim)
    sim.register_handlers("begin", [{"method_name": "zone_model"}])
    print(f"[SimEnv] : ✅ Predictive RC Model registered on 'begin' hook.")

if __name__ == "__main__":

    pass