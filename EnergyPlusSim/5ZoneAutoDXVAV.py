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
        self.plugin.handles['Out_W']    = gv(state, "Site Outdoor Air Humidity Ratio",      "Environment")
        self.plugin.handles['Out_CO2']  = gv(state, "Site Outdoor Air CO2 Concentration",   "Environment")

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
        self._fan_dT_est = 0.5  # Running estimate of fan heat rise (°C)
        self._prev_co2_error = 0.0  # Previous CO2 error for derivative term
        
        # Direct ON/OFF override states
        self._dx_state = False
        self._dx_last_toggle_time = -999.0
        self._heater_state = False
        self._heater_last_toggle_time = -999.0

    def _init(self, state):
        self.initializer.setup(state)
        
    
        for z in self.zones:
            self.zone_controllers[z] = ZoneController(z)
        self.ahu_coordinator = AHUCoordinator()
            
        self.ready = True

    #  HELPERS — sensor reads
    def _val(self, state, key):
        handle = self.handles.get(key, -1)
        if handle == -1:
            return 0.0
        val = self.api.exchange.get_variable_value(state, handle)
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
            # Compute effective T_out as simple average of adjacent zone temps
            adj_list = self.zone_params.get(z, {}).get('adj_zones', [])
            if adj_list:
                adj_temps = [self._val(state, f"{adj['zone']}_Temp") for adj in adj_list]
                T_out_zone = sum(adj_temps) / len(adj_temps)
            else:
                T_out_zone = self._val(state, "Out_Temp")

            # Build state data for the zone
            state_data = {
                'T_in': self._val(state, f"{z}_Temp"),
                'W_in': self._val(state, f"{z}_W_in"),
                'C_in': self._val(state, f"{z}_CO2"),
                'Occ': self._val(state, f"{z}_Occ"),
                'VAV_Flow': self._val(state, f"{z}_VAV_Flow"),
                'T_out': T_out_zone,
                'T_s': self._val(state, f"{z}_T_s"),
                'W_s': self._val(state, f"{z}_W_s"),
                'C_s': self._val(state, f"{z}_C_s"),
                'Equip': self._val(state, f"{z}_Equip")
            }

            print(f"[{z}][{day}-{h}:{m}] Starting step with dt={dt}")
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
        self.logger.add('Out_W_kg_kg', round(self._val(state, 'Out_W'), 5))
        self.logger.add('Out_CO2_ppm', round(self._val(state, 'Out_CO2'), 2))

        for n in CENTRAL_NODE_NAMES:
            self.logger.add(f"{n}_Temp_C", round(self._val(state, f"{n}_Temp"), 2))
            self.logger.add(f"{n}_RH_pct", round(self._val(state, f"{n}_RH"), 2))
            self.logger.add(f"{n}_W_kg_kg", round(self._val(state, f"{n}_W"), 5))
            self.logger.add(f"{n}_Flow_kg_s", round(self._val(state, f"{n}_Flow"), 4))
            self.logger.add(f"{n}_CO2_ppm", round(self._val(state, f"{n}_CO2"), 2))

        for z in self.zones:
            self.logger.add(f"{z}_Temp_C", round(self._val(state, f"{z}_Temp"), 2))
            self.logger.add(f"{z}_T_m_C", round(self._val(state, f"{z}_T_m"), 2))
            self.logger.add(f"{z}_W_kg_kg", round(self._val(state, f"{z}_W_in"), 5))
            self.logger.add(f"{z}_RH_pct", round(self._val(state, f"{z}_RH"), 2))
            self.logger.add(f"{z}_CO2_ppm", round(self._val(state, f"{z}_CO2"), 2))

            # Log effective outside temp (avg of adjacent zones)
            adj_list = self.zone_params.get(z, {}).get('adj_zones', [])
            if adj_list:
                adj_temps = [self._val(state, f"{adj['zone']}_Temp") for adj in adj_list]
                z_out_temp = sum(adj_temps) / len(adj_temps)
            else:
                z_out_temp = self._val(state, "Out_Temp")
            self.logger.add(f"{z}_out_temp_c", round(z_out_temp, 2))

            self.logger.add(f"{z}_Occupants", round(self._val(state, f"{z}_Occ"), 2))
            self.logger.add(f"{z}_EquipLoad_W", round(self._val(state, f"{z}_Equip"), 2))

            self.logger.add(f"{z}_VAV_Flow_kg_s", round(self._val(state, f"{z}_VAV_Flow"), 4))
            self.logger.add(f"{z}_Reheater_W", round(self._val(state, f"{z}_Reheater"), 2))
            self.logger.add(f"{z}_Flow_SP_kg_s", round(self._act_val(state, f"{z}_Flow_SP"), 4))
            self.logger.add(f"{z}_Reheat_SP_C", round(self._act_val(state, f"{z}_Reheat_SP"), 2))


        # --- AHU Actual Supply (what was delivered at fan outlet) ---
        self.logger.add("AHU_Supply_Temp_C",  round(self._val(state, "Fan_Out_Temp"), 2))
        self.logger.add("AHU_Supply_W_kg_kg", round(self._val(state, "Fan_Out_W"), 5))
        self.logger.add("AHU_Supply_CO2_ppm", round(self._val(state, "Fan_Out_CO2"), 2))
        self.logger.add("AHU_Supply_Flow_kg_s", round(self._val(state, "Fan_Out_Flow"), 4))

        # --- Component Power (instantaneous W) ---
        self.logger.add("CC_Power_W", round(self._val(state, "CC_Power"), 2))
        self.logger.add("HC_Power_W", round(self._val(state, "HC_Power"), 2))
        self.logger.add("Fan_Power_W", round(self._val(state, "Fan_Power"), 2))

        # --- Energy Meters (Joules per timestep) ---
        bldg_elec = self._meter_val(state, "M_Elec_Fac")
        hvac_elec = self._meter_val(state, "M_Elec_HVAC")
        bldg_gas  = self._meter_val(state, "M_Gas_Fac")

        self.logger.add("Meter_Bldg_Elec_J", round(bldg_elec, 2))
        self.logger.add("Meter_HVAC_Elec_J", round(hvac_elec, 2))
        self.logger.add("Meter_Bldg_Gas_J",  round(bldg_gas, 2))

        self.logger.add("Meter_Bldg_Total_J", round(bldg_elec + hvac_elec + bldg_gas, 2))
        self.logger.add("Meter_HVAC_Total_J", round(hvac_elec + bldg_gas, 2))

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
            # 1. CO2 Control via Outdoor Air Flow — PD Controller
            #    Kp: proportional gain (kg/s per ppm error)
            #    Kd: derivative gain (kg/s per ppm/timestep rate of change)
            Kp = 0.008   # Aggressive proportional: 100 ppm error → +0.8 kg/s
            Kd = 0.003   # Derivative: reacts to rate of CO2 change
            OA_MIN = 0.1  # Minimum for air quality (near-zero, not blind 0.5)
            OA_MAX = 2.5  # Physical max outdoor air flow

            co2_sp = self.ahu_setpoints.get('ahu_co2_sp', 400.0)
            
            actual_co2 = self._val(state, "Fan_Out_CO2")
            if actual_co2 <= 0.0:
                actual_co2 = self._val(state, "Mixed_Air_CO2")
                
            # Fallback in case central handles are missing
            if actual_co2 <= 0.0:
                actual_co2 = 400.0
                for z in self.zones:
                    if self.handles.get(f"{z}_CO2", -1) != -1:
                        actual_co2 = max(actual_co2, self._val(state, f"{z}_CO2"))

            co2_error = actual_co2 - co2_sp
            
            if not hasattr(self, '_co2_integral'):
                self._co2_integral = 0.0
                
            co2_error = actual_co2 - co2_sp
            
            # PI controller logic (fast response + eliminates steady-state error)
            Kp_oa = 0.003  # proportional "kick"
            Ki_oa = 0.002  # integral accumulation per timestep
            
            self._co2_integral += co2_error
            # Anti-windup clamp (bound between 0 and max required integral contribution)
            self._co2_integral = max(min(self._co2_integral, (OA_MAX - OA_MIN)/Ki_oa), 0.0)
            
            oa_flow = OA_MIN + Kp_oa * co2_error + Ki_oa * self._co2_integral
            oa_flow = min(max(oa_flow, OA_MIN), OA_MAX)

            if self.actuators.get("OA_Flow_SP", -1) != -1:
                sa(state, self.actuators["OA_Flow_SP"], oa_flow)
            
            # 2. Temperature & Humidity Setpoints with compensation
            temp_sp = self.ahu_setpoints.get('ahu_temp_sp', 13.0)
            hum_sp  = self.ahu_setpoints.get('ahu_hum_sp', 0.008)

            # 2a. Fan heat rise compensation
            #     The draw-through fan adds waste heat.
            #     Measure it from last timestep's actual data and use an EMA.
            fan_out_T = self._val(state, "Fan_Out_Temp")
            hc_out_T  = self._val(state, "HC_Out_Temp")
            if fan_out_T > 0 and hc_out_T > 0:
                measured_dT = fan_out_T - hc_out_T
                if measured_dT > 0:
                    # Use a very slow EMA (alpha=0.01) so ON/OFF compressor cycles don't cause the estimate to bounce
                    self._fan_dT_est = 0.99 * self._fan_dT_est + 0.01 * measured_dT

            # Subtract fan heat rise so the POST-fan supply temperature hits temp_sp on average
            coil_temp_sp = temp_sp - self._fan_dT_est

            # 2b. Psychrometric coupling for dehumidification
            import math
            P_w = hum_sp * 101325.0 / (0.62198 + hum_sp)
            if P_w > 0:
                ln_ratio = math.log(P_w / 610.94)
                T_dew_target = 243.04 * ln_ratio / (17.625 - ln_ratio)
                # If dehumidification requires a colder coil, use the lower value
                coil_temp_sp = min(coil_temp_sp, T_dew_target)

            # Clamp to physical AHU limits
            T_s_min = 5.0   # Hard physical floor for the coil
            coil_temp_sp = max(coil_temp_sp, T_s_min)
            
            # COIL SPLIT LOGIC:
            # Cooling Coil targets the COLDER of the sensible or latent requirement
            cc_temp_sp = max(min(coil_temp_sp, T_dew_target), T_s_min)
            
            # Heating Coil targets the sensible requirement (reheats the subcooled air)
            hc_temp_sp = max(coil_temp_sp, T_s_min)
            
            # The final duct setpoint is the post-reheat sensible temperature
            sat_sch_sp = hc_temp_sp
            
            # --- Direct ON/OFF Control (Option 1 with Anti-Short Cycle) ---
            # (Keep your existing override logic here, but ensure it overrides 
            # BOTH cc_temp_sp and hc_temp_sp if forced)

            
            current_time = self.api.exchange.current_time(state) # in hours
            dx_override = self.ahu_setpoints.get('ahu_dx_override', None)
            heater_override = self.ahu_setpoints.get('ahu_heater_override', None)
            
            # 6 minutes = 0.1 hours minimum toggle delay
            MIN_TOGGLE_DELAY = 0.5 
            
            if dx_override is not None:
                requested = bool(dx_override)
                if requested != self._dx_state:
                    if (current_time - self._dx_last_toggle_time) >= MIN_TOGGLE_DELAY:
                        self._dx_state = requested
                        self._dx_last_toggle_time = current_time
                        
                # Option 1: Extreme Setpoints
                cc_temp_sp = 0.0 if self._dx_state else 50.0

            if heater_override is not None:
                requested = bool(heater_override)
                if requested != self._heater_state:
                    if (current_time - self._heater_last_toggle_time) >= MIN_TOGGLE_DELAY:
                        self._heater_state = requested
                        self._heater_last_toggle_time = current_time
                        
                # Option 1: Extreme Setpoints
                hc_temp_sp = 50.0 if self._heater_state else 0.0
                
            if dx_override is not None or heater_override is not None:
                if self._dx_state:
                    sat_sch_sp = 0.0
                elif self._heater_state:
                    sat_sch_sp = 50.0
                else:
                    sat_sch_sp = 25.0
                    
            # Prevent rapid extreme temp changes by disabling coils at low flows
            # fan_out_flow = self._val(state, "Fan_Out_Flow")
            # LOW_FLOW_THRESHOLD = 0.25 # kg/s
            # if fan_out_flow < LOW_FLOW_THRESHOLD:
            #     cc_temp_sp = 50.0  # Disable cooling
            #     hc_temp_sp = 0.0   # Disable heating
            #     sat_sch_sp = 25.0  # Neutral

            # Apply temperature setpoints
            if self.actuators.get("SAT_Sch_SP", -1) != -1:
                sa(state, self.actuators["SAT_Sch_SP"], sat_sch_sp)
            if self.actuators.get("CC_Temp_SP", -1) != -1:
                sa(state, self.actuators["CC_Temp_SP"], cc_temp_sp)
            if self.actuators.get("HC_Temp_SP", -1) != -1:
                sa(state, self.actuators["HC_Temp_SP"], hc_temp_sp)

            # Apply humidity setpoints
            if self.actuators.get("Hum_Sch_SP", -1) != -1:
                sa(state, self.actuators["Hum_Sch_SP"], hum_sp)
            if self.actuators.get("CC_Hum_SP", -1) != -1:
                sa(state, self.actuators["CC_Hum_SP"], hum_sp)
            if self.actuators.get("CC_Hum_Max_SP", -1) != -1:
                sa(state, self.actuators["CC_Hum_Max_SP"], hum_sp)

            # Log compensation values for debugging
            self.logger.add("Fan_dT_est_C", round(self._fan_dT_est, 2))
            self.logger.add("Coil_Temp_SP_C", round(coil_temp_sp, 2))
            


        # Apply Zone Setpoints and VAV Commands
        for z in self.zones:
            cond = self.zone_ideal_conditions.get(z, {})
            flow = cond.get('u_cmd', 0.1)
            
            
            # Clamp Flow
            h_sp  = self.actuators.get(f"{z}_Flow_SP",  -1)
            h_max = self.actuators.get(f"{z}_Flow_MAX", -1)
            h_min = self.actuators.get(f"{z}_Flow_MIN", -1)
            if h_sp != -1 and h_max != -1 and h_min != -1:
                sa(state, h_max, flow)
                sa(state, h_min, flow)
                sa(state, h_sp,  flow)

            reheat_sp = 0    
            # Apply reheat setpoint
            h_reheat = self.actuators.get(f"{z}_Reheat_SP", -1)
            if h_reheat != -1:
                sa(state, h_reheat, reheat_sp)


        return 0
