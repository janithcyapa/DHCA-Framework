"""
5-Zone AutoDX VAV — EnergyPlus Python Plugin
=============================================
Main entry point loaded by the EnergyPlus plugin system.
Orchestrates initialisation, flexible logging, and delegates control to Zone Controllers and AHU Coordinator.
"""
# type: ignore
from pyenergyplus.plugin import EnergyPlusPlugin
import csv, os, sys, json
import random

# ── Inject local numpy / scipy for EnergyPlus embedded Python ────────────
_DEPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ep_deps")
if _DEPS not in sys.path:
    sys.path.insert(0, _DEPS)

from _5ZoneAutoDXVAV_zone_controller import ZoneController
from _5ZoneAutoDXVAV_ahu_coordinator import AHUCoordinator

# Sensor Configuration & Globals
SIMULATE_SENSOR_NOISE = False

CENTRAL_NODES = {
    "Outdoor_Air":  "Outside Air Inlet Node 1",
    "Relief_Air":   "Relief Air Outlet Node 1",
    "Mixer_Inlet":  "VAV Sys 1 Inlet Node",
    "Mixed_Air":    "Mixed Air Node 1",
    "CC_Out":       "Main Cooling Coil 1 Outlet Node",
    "HC_Out":       "Main Heating Coil 1 Outlet Node",
    "Fan_Out":      "VAV Sys 1 Outlet Node",
}

CENTRAL_NODE_NAMES = list(CENTRAL_NODES.keys())

# Flexible Logger
class SimulationLogger:
    def __init__(self, csv_path="./results/state_log.csv"):
        self.csv_path = csv_path
        self.headers = []
        self.current_row_data = {}
        self._csv_file = None
        self._csv_writer = None
        self.is_first_write = True
        
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        self._csv_file = open(self.csv_path, 'w', newline='')
        self._csv_writer = csv.writer(self._csv_file)

    def add(self, column_name, value):
        """Add a value to the current timestep's log."""
        self.current_row_data[column_name] = value
        if column_name not in self.headers:
            self.headers.append(column_name)

    def log_timestep(self):
        """Writes the collected row data to the CSV."""
        if self.is_first_write:
            self._csv_writer.writerow(self.headers)
            self.is_first_write = False
            
        row = [self.current_row_data.get(h, "") for h in self.headers]
        self._csv_writer.writerow(row)
        self._csv_file.flush()
        
        # Clear data for the next timestep, but keep headers
        self.current_row_data = {}

# Initializer
class Initializer:
    def __init__(self, api, plugin):
        self.api = api
        self.plugin = plugin
        
    def setup(self, state):
        self.discover_zones(state)
        self.load_params()
        self.load_datasets()
        self.register_env_handles(state)
        self.register_central_handles(state)
        self.register_zone_handles(state)
        self.register_actuators(state)
        self.validate_handles()
        
    def discover_zones(self, state):
        all_zones = self.api.exchange.get_object_names(state, "Zone")
        self.plugin.zones = [z for z in all_zones if "SPACE" in z.upper()]
        print("\n" + "=" * 60)
        print(" 🚀 Python Plugin Initializing ...")
        print(f" 🏢 Tracking {len(self.plugin.zones)} Zones: {', '.join(self.plugin.zones)}")

    def load_params(self):
        path = "./zone_thermal_params.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                self.plugin.zone_params = json.load(f)

    def load_datasets(self):
        for i in range(1, 6):
            z = f"SPACE{i}-1"
            csv_file = f"./SupplementaryData/combined_Room{i}.csv"
            if not os.path.exists(csv_file):
                continue
            rows = []
            with open(csv_file, 'r') as f:
                for r in csv.DictReader(f):
                    rows.append({
                        'plug_W':   float(r['plug_load_energy [kWh]']) * 12_000.0,
                        'light_W':  float(r['lighting_energy [kWh]'])  * 12_000.0,
                        'occupant_count': float(r['occupant_count [number]']),
                        'outdoor_co2':    float(r.get('outdoor_co2 [ppm]', 420.0)),
                    })
            self.plugin.datasets[z] = rows
            print(f" 📥 Loaded {len(rows)} rows for {z}")

    def register_env_handles(self, state):
        gv = self.api.exchange.get_variable_handle
        self.plugin.handles['Out_Temp'] = gv(state, "Site Outdoor Air Drybulb Temperature", "Environment")
        self.plugin.handles['Out_RH']   = gv(state, "Site Outdoor Air Relative Humidity",   "Environment")

    def register_central_handles(self, state):
        gv = self.api.exchange.get_variable_handle
        for name, node in CENTRAL_NODES.items():
            self.plugin.handles[f"{name}_Temp"] = gv(state, "System Node Temperature",      node)
            self.plugin.handles[f"{name}_RH"]   = gv(state, "System Node Relative Humidity", node)
            self.plugin.handles[f"{name}_Flow"] = gv(state, "System Node Mass Flow Rate",    node)
            self.plugin.handles[f"{name}_CO2"]  = gv(state, "System Node CO2 Concentration", node)
            self.plugin.handles[f"{name}_W"]    = gv(state, "System Node Humidity Ratio",    node)

        self.plugin.handles["CC_Power"]  = gv(state, "Cooling Coil Electricity Rate", "Main Cooling Coil 1")
        self.plugin.handles["HC_Power"]  = gv(state, "Heating Coil NaturalGas Rate",  "Main heating Coil 1")
        self.plugin.handles["Fan_Power"] = gv(state, "Fan Electricity Rate",           "Supply Fan 1")

        self.plugin.handles["M_Elec_Fac"]  = self.api.exchange.get_meter_handle(state, "Electricity:Building")
        self.plugin.handles["M_Elec_HVAC"] = self.api.exchange.get_meter_handle(state, "Electricity:HVAC")
        self.plugin.handles["M_Elec_Fans"] = self.api.exchange.get_meter_handle(state, "Fans:Electricity")
        self.plugin.handles["M_Elec_Cool"] = self.api.exchange.get_meter_handle(state, "Cooling:Electricity")
        self.plugin.handles["M_Gas_Fac"]   = self.api.exchange.get_meter_handle(state, "NaturalGas:Facility")

    def register_zone_handles(self, state):
        gv = self.api.exchange.get_variable_handle
        for z in self.plugin.zones:
            self.plugin.handles[f"{z}_Temp"]     = gv(state, "Zone Mean Air Temperature",                z)
            self.plugin.handles[f"{z}_RH"]       = gv(state, "Zone Air Relative Humidity",               z)
            self.plugin.handles[f"{z}_VAV_Flow"] = gv(state, "System Node Mass Flow Rate",   f"{z} In Node")
            self.plugin.handles[f"{z}_Reheater"] = gv(state, "Heating Coil NaturalGas Rate", f"{z} Zone Coil")
            self.plugin.handles[f"{z}_CO2"]      = gv(state, "Zone Air CO2 Concentration",               z)
            self.plugin.handles[f"{z}_Occ"]      = gv(state, "Zone People Occupant Count",               z)
            self.plugin.handles[f"{z}_Equip"]    = gv(state, "Zone Electric Equipment Total Heating Rate",z)
            self.plugin.handles[f"{z}_W_in"]     = gv(state, "Zone Mean Air Humidity Ratio",             z)
            self.plugin.handles[f"{z}_T_m"]      = gv(state, "Zone Mean Radiant Temperature",            z)
            self.plugin.handles[f"{z}_T_s"]      = gv(state, "System Node Temperature",      f"{z} In Node")
            self.plugin.handles[f"{z}_W_s"]      = gv(state, "System Node Humidity Ratio",   f"{z} In Node")
            self.plugin.handles[f"{z}_C_s"]      = gv(state, "System Node CO2 Concentration",f"{z} In Node")

        for z, p in self.plugin.zone_params.items():
            for adj in p.get("adj_zones", []):
                key = f"{adj['zone']}_Temp"
                if key not in self.plugin.handles:
                    self.plugin.handles[key] = gv(state, "Zone Mean Air Temperature", adj['zone'])

    def register_actuators(self, state):
        ga = self.api.exchange.get_actuator_handle
        for z in self.plugin.zone_params:
            node = f"{z} ATU IN NODE"
            self.plugin.actuators[f"{z}_Flow_SP"]  = ga(state, "System Node Setpoint", "Mass Flow Rate Setpoint",                   node)
            self.plugin.actuators[f"{z}_Flow_MAX"] = ga(state, "System Node Setpoint", "Mass Flow Rate Maximum Available Setpoint",  node)
            self.plugin.actuators[f"{z}_Flow_MIN"] = ga(state, "System Node Setpoint", "Mass Flow Rate Minimum Available Setpoint",  node)
            self.plugin.actuators[f"{z}_Reheat_SP"]= ga(state, "System Node Setpoint", "Temperature Setpoint", f"{z} In Node")
            self.plugin.actuators[f"{z}_People_SP"]= ga(state, "People",               "Number of People",     f"{z} PEOPLE 1")
            self.plugin.actuators[f"{z}_Equip_SP"] = ga(state, "ElectricEquipment",    "Electricity Rate",     f"{z} ELECEQ 1")
            self.plugin.actuators[f"{z}_Lights_SP"]= ga(state, "Lights",               "Electricity Rate",     f"{z} LIGHTS 1")

        self.plugin.actuators["CC_Temp_SP"] = ga(state, "System Node Setpoint", "Temperature Setpoint", "Main Cooling Coil 1 Outlet Node")
        self.plugin.actuators["CC_Hum_SP"] = ga(state, "System Node Setpoint", "Humidity Ratio Setpoint", "Main Cooling Coil 1 Outlet Node")
        self.plugin.actuators["CC_Hum_Max_SP"] = ga(state, "System Node Setpoint", "Humidity Ratio Maximum Setpoint", "Main Cooling Coil 1 Outlet Node")
        self.plugin.actuators["HC_Temp_SP"] = ga(state, "System Node Setpoint", "Temperature Setpoint", "Main Heating Coil 1 Outlet Node")
        self.plugin.actuators["Fan_Flow"]   = ga(state, "Fan", "Fan Air Mass Flow Rate", "Supply Fan 1")
        self.plugin.actuators["CO2_Out_SP"] = ga(state, "Schedule:Constant", "Schedule Value",       "CO2-Outdoor-Schedule")
        self.plugin.actuators["OA_Flow_SP"] = ga(state, "Outdoor Air Controller", "Air Mass Flow Rate", "OA CONTROLLER 1")
        # Schedule overrides to prevent SetpointManagers from overwriting our Python setpoints
        self.plugin.actuators["SAT_Sch_SP"]  = ga(state, "Schedule:Compact", "Schedule Value", "Seasonal Reset Supply Air Temp Sch")
        self.plugin.actuators["Hum_Sch_SP"]  = ga(state, "Schedule:Constant", "Schedule Value", "Hum-Ratio-Max-Sch")

    def validate_handles(self):
        bad = [n for n, h in self.plugin.handles.items() if h == -1]
        if bad:
            for n in bad:
                print(f" ⚠️  Missing handle: {n}")
            print(" 🚨 Check Output:Variable blocks in the IDF!")
        print("=" * 60 + "\n")

# Plugin class
class HVAC_Coordinator(EnergyPlusPlugin):

    def __init__(self):
        super().__init__()
        self.ready     = False
        self.handles   = {}
        self.actuators = {}
        self.zones     = []
        self.datasets  = {}
        self.start_day = None
        self.zone_params = {}

        # Toggle for custom controllers
        self.USE_CUSTOM_CONTROLLERS = True
        
        self.logger = SimulationLogger()
        self.initializer = Initializer(self.api, self)
        
        self.zone_controllers = {}
        self.ahu_coordinator = None
        
        self.zone_ideal_conditions = {}
        self.ahu_setpoints = {}

    def _init(self, state):
        self.initializer.setup(state)
        
    
        for z in self.zones:
            self.zone_controllers[z] = ZoneController(z)
        self.ahu_coordinator = AHUCoordinator()
            
        self.ready = True

    #  HELPERS — sensor reads
    def _val(self, state, key):
        val = self.api.exchange.get_variable_value(state, self.handles[key])
        if SIMULATE_SENSOR_NOISE:
            if key.endswith("_Temp"): val += random.gauss(0, 0.1)
            elif key.endswith("_RH"): val += random.gauss(0, 1.0)
            elif key.endswith("_CO2"): val += random.gauss(0, 15.0)
        return val

    def _meter_val(self, state, key):
        handle = self.handles.get(key, -1)
        if handle == -1: return 0.0
        return self.api.exchange.get_meter_value(state, handle)

    def _act_val(self, state, key):
        handle = self.actuators.get(key, -1)
        if handle == -1: return 0.0
        return self.api.exchange.get_actuator_value(state, handle)

    def _get_dt(self, state):
        dt_h = self.api.exchange.system_time_step(state)
        if dt_h == 0:
            dt_h = self.api.exchange.zone_time_step(state)
        return dt_h * 3600.0

    #  HOOK 1 — State Estimation & Controller Update
    def on_begin_timestep_before_predictor(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state):              return 0
        if not self.ready:
            self._init(state)

        dt = self._get_dt(state)
        if dt <= 0: return 0

        # Log time
        day  = self.api.exchange.day_of_year(state)
        t    = self.api.exchange.current_time(state)
        h, m = divmod(int(t * 60), 60)
        self.logger.add("DayOfYear", day)
        self.logger.add("Hour", h)
        self.logger.add("Minute", m)

        # if not self.USE_CUSTOM_CONTROLLERS:
        #     return 0

        # Run Zone Controllers
        self.zone_ideal_conditions = {}
        for z in self.zones:
            # Build state data for the zone
            state_data = {
                'T_in': self._val(state, f"{z}_Temp"),
                'W_in': self._val(state, f"{z}_W_in"),
                'C_in': self._val(state, f"{z}_CO2"),
                'Occ': self._val(state, f"{z}_Occ"),
                'VAV_Flow': self._val(state, f"{z}_VAV_Flow"),
                'T_out': self._val(state, "Out_Temp"),
                'T_s': self._val(state, f"{z}_T_s"),
                'W_s': self._val(state, f"{z}_W_s"),
                'C_s': self._val(state, f"{z}_C_s"),
                'Equip': self._val(state, f"{z}_Equip")
            }
            # Execute zone controller step
            ideal_cond = self.zone_controllers[z].step(dt, state_data, self.logger)
            self.zone_ideal_conditions[z] = ideal_cond

        # Run AHU Coordinator
        self.ahu_setpoints = self.ahu_coordinator.calculate_setpoints(self.zone_ideal_conditions, self.logger)

        return 0

    #  HOOK 2 — Data Logger (runs after zone reporting)
    def on_end_of_zone_timestep_after_zone_reporting(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state):              return 0
        if not self.ready:                                    return 0

        # Log Default Data Readings
        self.logger.add('Out_Temp_C', round(self._val(state, 'Out_Temp'), 2))
        self.logger.add('Out_RH_pct', round(self._val(state, 'Out_RH'), 2))

        for n in CENTRAL_NODE_NAMES:
            self.logger.add(f"{n}_Temp_C", round(self._val(state, f"{n}_Temp"), 2))
            self.logger.add(f"{n}_RH_pct", round(self._val(state, f"{n}_RH"), 2))
            self.logger.add(f"{n}_Flow_kg_s", round(self._val(state, f"{n}_Flow"), 4))
            self.logger.add(f"{n}_CO2_ppm", round(self._val(state, f"{n}_CO2"), 2))

        for z in self.zones:
            self.logger.add(f"{z}_Temp_C", round(self._val(state, f"{z}_Temp"), 2))
            self.logger.add(f"{z}_T_m_C", round(self._val(state, f"{z}_T_m"), 2))
            self.logger.add(f"{z}_W_in_kg_kg", round(self._val(state, f"{z}_W_in"), 5))
            self.logger.add(f"{z}_RH_pct", round(self._val(state, f"{z}_RH"), 2))
            self.logger.add(f"{z}_VAV_Flow_kg_s", round(self._val(state, f"{z}_VAV_Flow"), 4))
            self.logger.add(f"{z}_Reheater_W", round(self._val(state, f"{z}_Reheater"), 2))
            self.logger.add(f"{z}_CO2_ppm", round(self._val(state, f"{z}_CO2"), 2))
            self.logger.add(f"{z}_Occupants", round(self._val(state, f"{z}_Occ"), 2))
            self.logger.add(f"{z}_EquipLoad_W", round(self._val(state, f"{z}_Equip"), 2))
            
            # Log Actuator values for the zone
            self.logger.add(f"Act_{z}_Flow_SP_kg_s", round(self._act_val(state, f"{z}_Flow_SP"), 4))
            self.logger.add(f"Act_{z}_Reheat_SP_C", round(self._act_val(state, f"{z}_Reheat_SP"), 2))

        self.logger.add("CC_Power_W", round(self._val(state, "CC_Power"), 2))
        self.logger.add("HC_Power_W", round(self._val(state, "HC_Power"), 2))
        self.logger.add("Fan_Power_W", round(self._val(state, "Fan_Power"), 2))
        
        # Log Central Actuator values (Cooler, Heater, Fan, Mixer/OA)
        self.logger.add("Act_CC_Temp_SP_C", round(self._act_val(state, "CC_Temp_SP"), 2))
        self.logger.add("Act_HC_Temp_SP_C", round(self._act_val(state, "HC_Temp_SP"), 2))
        self.logger.add("Act_Fan_Flow_kg_s", round(self._act_val(state, "Fan_Flow"), 4))
        self.logger.add("Act_OA_Flow_SP_kg_s", round(self._act_val(state, "OA_Flow_SP"), 4))
        
        self.logger.add("Meter_Bldg_Elec_J", round(self._meter_val(state, "M_Elec_Fac"), 2))
        self.logger.add("Meter_HVAC_Elec_J", round(self._meter_val(state, "M_Elec_HVAC"), 2))
        self.logger.add("Meter_AHU_Elec_J", round(self._meter_val(state, "M_Elec_Fans") + self._meter_val(state, "M_Elec_Cool"), 2))
        self.logger.add("Meter_Bldg_Gas_J", round(self._meter_val(state, "M_Gas_Fac"), 2))

        # Write to CSV
        self.logger.log_timestep()
        
        return 0

    #  HOOK 3 — Actuation
    def on_inside_hvac_system_iteration_loop(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state):              return 0
        if not self.ready:                                    return 0

        sa = self.api.exchange.set_actuator_value

        # Time sync for dataset schedules
        day  = self.api.exchange.day_of_year(state)
        time = self.api.exchange.current_time(state)
        if self.start_day is None:
            self.start_day = day
        elapsed = (day - self.start_day) * 24.0 + time
        idx     = int(elapsed * 12)

        # Dataset overrides
        if "SPACE1-1" in self.datasets:
            df1 = self.datasets["SPACE1-1"]
            co2 = df1[idx % len(df1)]['outdoor_co2']
            if self.actuators.get("CO2_Out_SP", -1) != -1:
                sa(state, self.actuators["CO2_Out_SP"], co2)

        for z in self.zones:
            if z in self.datasets:
                row = self.datasets[z][idx % len(self.datasets[z])]
                for suffix, key in [("People_SP", "occupant_count"), ("Equip_SP", "plug_W"), ("Lights_SP", "light_W")]:
                    h = self.actuators.get(f"{z}_{suffix}", -1)
                    if h != -1: sa(state, h, row[key])

        if not self.USE_CUSTOM_CONTROLLERS:
            return 0

        # Apply AHU Setpoints
        if self.ahu_setpoints:
            # 1. CO2 Control via Outdoor Air Flow
            co2_sp = self.ahu_setpoints.get('ahu_co2_sp', 400.0)
            max_co2 = 400.0
            for z in self.zones:
                if self.handles.get(f"{z}_CO2", -1) != -1:
                    max_co2 = max(max_co2, self._val(state, f"{z}_CO2"))
                    
            oa_flow = 0.5 # Default minimum fresh air kg/s
            if max_co2 > co2_sp:
                oa_flow = min(2.5, 0.5 + (max_co2 - co2_sp) * 0.01) # Simple P-controller to increase OA
                
            if self.actuators.get("OA_Flow_SP", -1) != -1:
                sa(state, self.actuators["OA_Flow_SP"], oa_flow)
            
            # 2. Temperature Setpoints - override both the schedule and the node
            temp_sp = self.ahu_setpoints.get('ahu_temp_sp', 13.0)
            # Override the schedule so SetpointManager:Scheduled writes our value
            if self.actuators.get("SAT_Sch_SP", -1) != -1:
                sa(state, self.actuators["SAT_Sch_SP"], temp_sp)
            # Also set node setpoints directly as backup
            if self.actuators.get("CC_Temp_SP", -1) != -1:
                sa(state, self.actuators["CC_Temp_SP"], temp_sp)
            # FIX (bug 3): this used to set the central heating coil setpoint
            # to temp_sp + 1.0 unconditionally, i.e. always asking it to add
            # heat right after the cooling coil. That directly contradicts
            # the reheat-free "Actuation-Minimizing Deadband MPC" design in
            # docs 3-5, where VAV flow (u) is meant to be the only actuator.
            # Pass the setpoint straight through -- no added heat.
            if self.actuators.get("HC_Temp_SP", -1) != -1:
                sa(state, self.actuators["HC_Temp_SP"], temp_sp)
                
            # 3. Humidity Setpoints - override the schedule so SetpointManager writes our value
            hum_sp = self.ahu_setpoints.get('ahu_hum_sp', 0.008)
            # Override the humidity max schedule so the SetpointManager:Scheduled picks it up
            if self.actuators.get("Hum_Sch_SP", -1) != -1:
                sa(state, self.actuators["Hum_Sch_SP"], hum_sp)
            # Also set node setpoints directly
            if self.actuators.get("CC_Hum_SP", -1) != -1:
                sa(state, self.actuators["CC_Hum_SP"], hum_sp)
            if self.actuators.get("CC_Hum_Max_SP", -1) != -1:
                sa(state, self.actuators["CC_Hum_Max_SP"], hum_sp)
            
            # Log AHU actuation decisions
            self.logger.add("Act_AHU_OA_Flow", round(oa_flow, 4))
            self.logger.add("Act_AHU_MaxCO2", round(max_co2, 2))
            self.logger.add("Act_AHU_Temp_SP", round(temp_sp, 2))
            self.logger.add("Act_AHU_Hum_SP", round(hum_sp, 5))

        # Apply Zone Setpoints and VAV Commands
        for z in self.zones:
            cond = self.zone_ideal_conditions.get(z, {})
            flow = cond.get('u_cmd', 0.1)
            ideal_temp = cond.get('ideal_temp', 22.0)
            
            # FIX (bug 3): this block used to command the per-zone reheat
            # coil up to T_ref (22C) whenever the zone wasn't overheating --
            # a conventional VAV-reheat sequence that (a) contradicts the
            # reheat-free "Actuation-Minimizing Deadband MPC" design in docs
            # 3-5, and (b) shrinks the zone MPC's own authority over
            # temperature, since T_s is read from this same post-reheat node
            # (Bc[0,0] ~ (T_s - T_in) collapses toward 0 whenever reheat
            # pulls T_s up near T_in). VAV flow (u_cmd, from the zone's own
            # MPC) is meant to be the only actuator -- pass supply air
            # through unmodified.
            supply_temp = self.ahu_setpoints.get('ahu_temp_sp', 13.0) if self.ahu_setpoints else 13.0
            reheat_sp = supply_temp
            
            # Clamp Flow
            h_sp  = self.actuators.get(f"{z}_Flow_SP",  -1)
            h_max = self.actuators.get(f"{z}_Flow_MAX", -1)
            h_min = self.actuators.get(f"{z}_Flow_MIN", -1)
            if h_sp != -1 and h_max != -1 and h_min != -1:
                sa(state, h_max, flow)
                sa(state, h_min, flow)
                sa(state, h_sp,  flow)
                
            # Apply reheat setpoint
            h_reheat = self.actuators.get(f"{z}_Reheat_SP", -1)
            if h_reheat != -1:
                sa(state, h_reheat, reheat_sp)
            
            # Log zone actuation
            self.logger.add(f"Act_{z}_Reheat_Applied_C", round(reheat_sp, 2))

        return 0
