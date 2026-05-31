"""
5-Zone AutoDX VAV — EnergyPlus Python Plugin
=============================================
Main entry point loaded by the EnergyPlus plugin system.
Orchestrates initialisation, logging, state estimation, and control.

File layout
-----------
  5ZoneAutoDXVAV.py                 ← you are here (plugin + logger)
  _5ZoneAutoDXVAV_zone_model.py     ← open-loop theoretical RC model
  _5ZoneAutoDXVAV_ekf.py            ← closed-loop EKF state estimator
  _5ZoneAutoDXVAV_controller.py     ← MPC controller
"""
from pyenergyplus.plugin import EnergyPlusPlugin
import csv, os, sys, json

# ── Inject local numpy / scipy for EnergyPlus embedded Python ────────────
_DEPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ep_deps")
if _DEPS not in sys.path:
    sys.path.insert(0, _DEPS)

import numpy as np

from _5ZoneAutoDXVAV_zone_model import TheoreticalZoneModel
from _5ZoneAutoDXVAV_ekf import ZoneEKF
from _5ZoneAutoDXVAV_controller import MPCController


# ─────────────────────────────────────────────────────────────────────────
# Node / handle definitions (declared once, used in init)
# ─────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────
# CSV header builder
# ─────────────────────────────────────────────────────────────────────────
def _build_csv_headers(zones):
    """Return the full header list for state_log.csv."""
    h = ["DayOfYear", "Hour", "Minute", "Out_Temp_C", "Out_RH_pct"]

    for n in CENTRAL_NODE_NAMES:
        h += [f"{n}_Temp_C", f"{n}_RH_pct", f"{n}_Flow_kg_s", f"{n}_CO2_ppm"]

    for z in zones:
        # Simulation (ground truth)
        h += [f"{z}_Temp_C", f"{z}_T_m_C", f"{z}_W_in_kg_kg", f"{z}_RH_pct",
              f"{z}_VAV_Flow_kg_s", f"{z}_Reheater_W", f"{z}_CO2_ppm",
              f"{z}_Occupants", f"{z}_EquipLoad_W"]
        # Theoretical model
        h += [f"{z}_T_in_theo", f"{z}_T_m_theo", f"{z}_W_in_theo", f"{z}_C_in_theo"]
        # EKF estimates
        h += [f"{z}_T_in_est", f"{z}_T_m_est", f"{z}_W_in_est", f"{z}_C_in_est", f"{z}_Occ_est"]

    h += ["CC_Power_W", "HC_Power_W", "Fan_Power_W"]
    return h


# ─────────────────────────────────────────────────────────────────────────
# Plugin class
# ─────────────────────────────────────────────────────────────────────────
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
        self.zone_models = {}       # TheoreticalZoneModel per zone
        self.zone_ekfs   = {}       # ZoneEKF per zone
        self.mpc         = None     # MPCController
        self.estimations = {}       # latest per-zone EKF + model state

        self.csv_path   = "./results/state_log.csv"
        self._csv_file  = None
        self._csv_writer = None

    # ═════════════════════════════════════════════════════════════════════
    #  INITIALISATION
    # ═════════════════════════════════════════════════════════════════════
    def _init(self, state):
        """One-time setup: discover zones, register handles, open CSV."""
        self._discover_zones(state)
        self._load_params()
        self._load_datasets()
        self._register_env_handles(state)
        self._register_central_handles(state)
        self._register_zone_handles(state)
        self._register_actuators(state)
        self._init_estimators()
        self._open_csv()
        self._validate_handles()
        self.ready = True

    # ── Zone discovery ───────────────────────────────────────────────────
    def _discover_zones(self, state):
        all_zones = self.api.exchange.get_object_names(state, "Zone")
        self.zones = [z for z in all_zones if "SPACE" in z.upper()]
        print("\n" + "=" * 60)
        print(" 🚀 Python Plugin Initializing ...")
        print(f" 🏢 Tracking {len(self.zones)} Zones: {', '.join(self.zones)}")

    # ── Load thermal parameters ──────────────────────────────────────────
    def _load_params(self):
        path = "./zone_thermal_params.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                self.zone_params = json.load(f)

    # ── Load supplementary datasets ──────────────────────────────────────
    def _load_datasets(self):
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
            self.datasets[z] = rows
            print(f" 📥 Loaded {len(rows)} rows for {z}")

    # ── Environment handles ──────────────────────────────────────────────
    def _register_env_handles(self, state):
        gv = self.api.exchange.get_variable_handle
        self.handles['Out_Temp'] = gv(state, "Site Outdoor Air Drybulb Temperature", "Environment")
        self.handles['Out_RH']   = gv(state, "Site Outdoor Air Relative Humidity",   "Environment")

    # ── Central air-loop handles ─────────────────────────────────────────
    def _register_central_handles(self, state):
        gv = self.api.exchange.get_variable_handle
        for name, node in CENTRAL_NODES.items():
            self.handles[f"{name}_Temp"] = gv(state, "System Node Temperature",      node)
            self.handles[f"{name}_RH"]   = gv(state, "System Node Relative Humidity", node)
            self.handles[f"{name}_Flow"] = gv(state, "System Node Mass Flow Rate",    node)
            self.handles[f"{name}_CO2"]  = gv(state, "System Node CO2 Concentration", node)

        self.handles["CC_Power"]  = gv(state, "Cooling Coil Electricity Rate", "Main Cooling Coil 1")
        self.handles["HC_Power"]  = gv(state, "Heating Coil NaturalGas Rate",  "Main heating Coil 1")
        self.handles["Fan_Power"] = gv(state, "Fan Electricity Rate",           "Supply Fan 1")

    # ── Zone-level handles ───────────────────────────────────────────────
    def _register_zone_handles(self, state):
        gv = self.api.exchange.get_variable_handle
        for z in self.zones:
            self.handles[f"{z}_Temp"]     = gv(state, "Zone Mean Air Temperature",                z)
            self.handles[f"{z}_RH"]       = gv(state, "Zone Air Relative Humidity",               z)
            self.handles[f"{z}_VAV_Flow"] = gv(state, "System Node Mass Flow Rate",   f"{z} In Node")
            self.handles[f"{z}_Reheater"] = gv(state, "Heating Coil NaturalGas Rate", f"{z} Zone Coil")
            self.handles[f"{z}_CO2"]      = gv(state, "Zone Air CO2 Concentration",               z)
            self.handles[f"{z}_Occ"]      = gv(state, "Zone People Occupant Count",               z)
            self.handles[f"{z}_Equip"]    = gv(state, "Zone Electric Equipment Total Heating Rate",z)
            self.handles[f"{z}_W_in"]     = gv(state, "Zone Mean Air Humidity Ratio",             z)
            self.handles[f"{z}_T_m"]      = gv(state, "Zone Mean Radiant Temperature",            z)
            self.handles[f"{z}_T_s"]      = gv(state, "System Node Temperature",      f"{z} In Node")
            self.handles[f"{z}_W_s"]      = gv(state, "System Node Humidity Ratio",   f"{z} In Node")
            self.handles[f"{z}_C_s"]      = gv(state, "System Node CO2 Concentration",f"{z} In Node")

        # Adjacent zone temps (may include PLENUM)
        for z, p in self.zone_params.items():
            for adj in p.get("adj_zones", []):
                key = f"{adj['zone']}_Temp"
                if key not in self.handles:
                    self.handles[key] = gv(state, "Zone Mean Air Temperature", adj['zone'])

    # ── Actuator handles ─────────────────────────────────────────────────
    def _register_actuators(self, state):
        ga = self.api.exchange.get_actuator_handle
        for z in self.zone_params:
            node = f"{z} ATU IN NODE"
            self.actuators[f"{z}_Flow_SP"]  = ga(state, "System Node Setpoint", "Mass Flow Rate Setpoint",                   node)
            self.actuators[f"{z}_Flow_MAX"] = ga(state, "System Node Setpoint", "Mass Flow Rate Maximum Available Setpoint",  node)
            self.actuators[f"{z}_Flow_MIN"] = ga(state, "System Node Setpoint", "Mass Flow Rate Minimum Available Setpoint",  node)
            self.actuators[f"{z}_Reheat_SP"]= ga(state, "System Node Setpoint", "Temperature Setpoint", f"{z} In Node")
            self.actuators[f"{z}_People_SP"]= ga(state, "People",               "Number of People",     f"{z} PEOPLE 1")
            self.actuators[f"{z}_Equip_SP"] = ga(state, "ElectricEquipment",    "Electricity Rate",     f"{z} ELECEQ 1")
            self.actuators[f"{z}_Lights_SP"]= ga(state, "Lights",               "Electricity Rate",     f"{z} LIGHTS 1")

        self.actuators["CC_Temp_SP"] = ga(state, "System Node Setpoint", "Temperature Setpoint", "Main Cooling Coil 1 Outlet Node")
        self.actuators["HC_Temp_SP"] = ga(state, "System Node Setpoint", "Temperature Setpoint", "Main Heating Coil 1 Outlet Node")
        self.actuators["Fan_Flow"]   = ga(state, "Fan", "Fan Air Mass Flow Rate", "Supply Fan 1")
        self.actuators["CO2_Out_SP"] = ga(state, "Schedule:Constant", "Schedule Value",       "CO2-Outdoor-Schedule")
        self.actuators["OA_Flow_SP"] = ga(state, "Outdoor Air Controller", "Air Mass Flow Rate", "OA CONTROLLER 1")

    # ── Estimators & controller ──────────────────────────────────────────
    def _init_estimators(self):
        for z in self.zones:
            p = self.zone_params.get(z, {})
            self.zone_models[z] = TheoreticalZoneModel(z, p)
            self.zone_ekfs[z]   = ZoneEKF(z)
        self.mpc = MPCController(self.zones, self.zone_params)

    # ── CSV logger ───────────────────────────────────────────────────────
    def _open_csv(self):
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        self._csv_file   = open(self.csv_path, 'w', newline='')
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(_build_csv_headers(self.zones))
        self._csv_file.flush()

    # ── Validation ───────────────────────────────────────────────────────
    def _validate_handles(self):
        bad = [n for n, h in self.handles.items() if h == -1]
        if bad:
            for n in bad:
                print(f" ⚠️  Missing handle: {n}")
            print(" 🚨 Check Output:Variable blocks in the IDF!")
        else:
            print(f" 📊 Logger Armed → {self.csv_path}")
        print("=" * 60 + "\n")

    # ═════════════════════════════════════════════════════════════════════
    #  HELPERS — sensor reads
    # ═════════════════════════════════════════════════════════════════════
    def _val(self, state, key):
        return self.api.exchange.get_variable_value(state, self.handles[key])

    def _get_dt(self, state):
        dt_h = self.api.exchange.system_time_step(state)
        if dt_h == 0:
            dt_h = self.api.exchange.zone_time_step(state)
        return dt_h * 3600.0

    def _get_adj_data(self, state, zone_name):
        """Build adjacency list for a given zone."""
        p = self.zone_params.get(zone_name, {})
        result = []
        for adj in p.get("adj_zones", []):
            t_adj = self._val(state, f"{adj['zone']}_Temp")
            result.append({'t_adj': t_adj, 'r_env': float(adj["R_env"])})
        return result

    # ═════════════════════════════════════════════════════════════════════
    #  HOOK 1 — State Estimation (runs before predictor)
    # ═════════════════════════════════════════════════════════════════════
    def on_begin_timestep_before_predictor(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state):              return 0
        if not self.ready:
            self._init(state)

        dt = self._get_dt(state)
        if dt <= 0:
            return 0

        T_out = self._val(state, "Out_Temp")

        for z in self.zones:
            p = self.zone_params.get(z)
            if not p:
                continue

            # Sensor readings
            T_in = self._val(state, f"{z}_Temp")
            W_in = self._val(state, f"{z}_W_in")
            C_in = self._val(state, f"{z}_CO2")
            occ  = self._val(state, f"{z}_Occ")

            # Supply air
            m_dot   = self._val(state, f"{z}_VAV_Flow")
            V_dot_s = m_dot / 1.204
            T_s = self._val(state, f"{z}_T_s")
            W_s = self._val(state, f"{z}_W_s")
            C_s = self._val(state, f"{z}_C_s")

            adj = self._get_adj_data(state, z)
            Q_equip = 0.0

            # ── Initialise on first call ─────────────────────────────────
            model = self.zone_models[z]
            ekf   = self.zone_ekfs[z]
            if model.state is None:
                model.initialise(T_in, W_in, C_in)
                ekf.initialise(T_in, W_in, C_in)
                continue

            # ── Theoretical model step ───────────────────────────────────
            model.step(dt, T_out, V_dot_s, T_s, W_s, C_s, occ, Q_equip, adj)

            # ── EKF step ─────────────────────────────────────────────────
            z_meas = np.array([T_in, W_in, C_in])
            ekf.step(dt, p, z_meas, V_dot_s, Q_equip, T_s, W_s, C_s, T_out, adj)

            # ── Cache latest estimations ─────────────────────────────────
            self.estimations[z] = {**model.get_state(), **ekf.get_state()}

        return 0

    # ═════════════════════════════════════════════════════════════════════
    #  HOOK 2 — Data Logger (runs after zone reporting)
    # ═════════════════════════════════════════════════════════════════════
    def on_end_of_zone_timestep_after_zone_reporting(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state):              return 0
        if not self.ready:                                    return 0

        day  = self.api.exchange.day_of_year(state)
        t    = self.api.exchange.current_time(state)
        h, m = divmod(int(t * 60), 60)

        row = [day, h, m]

        # Outdoor
        row += [round(self._val(state, 'Out_Temp'), 2),
                round(self._val(state, 'Out_RH'),   2)]

        # Central nodes
        for n in CENTRAL_NODE_NAMES:
            row += [round(self._val(state, f"{n}_Temp"), 2),
                    round(self._val(state, f"{n}_RH"),   2),
                    round(self._val(state, f"{n}_Flow"), 4),
                    round(self._val(state, f"{n}_CO2"),  2)]

        # Zones
        for z in self.zones:
            row += [round(self._val(state, f"{z}_Temp"),     2),
                    round(self._val(state, f"{z}_T_m"),      2),
                    round(self._val(state, f"{z}_W_in"),     5),
                    round(self._val(state, f"{z}_RH"),       2),
                    round(self._val(state, f"{z}_VAV_Flow"), 4),
                    round(self._val(state, f"{z}_Reheater"), 2),
                    round(self._val(state, f"{z}_CO2"),      2),
                    round(self._val(state, f"{z}_Occ"),      2),
                    round(self._val(state, f"{z}_Equip"),    2)]

            est = self.estimations.get(z, {})
            row += [round(est.get("T_in_theo", 0), 2),
                    round(est.get("T_m_theo",  0), 2),
                    round(est.get("W_in_theo", 0), 5),
                    round(est.get("C_in_theo", 0), 2)]
            row += [round(est.get("T_in_est",  0), 2),
                    round(est.get("T_m_est",   0), 2),
                    round(est.get("W_in_est",  0), 5),
                    round(est.get("C_in_est",  0), 2),
                    round(est.get("N_occ_est", 0), 2)]

        # Central equipment
        row += [round(self._val(state, "CC_Power"),  2),
                round(self._val(state, "HC_Power"),  2),
                round(self._val(state, "Fan_Power"), 2)]

        self._csv_writer.writerow(row)
        self._csv_file.flush()
        return 0

    # ═════════════════════════════════════════════════════════════════════
    #  HOOK 3 — MPC Control Signal Injection (inside HVAC loop)
    # ═════════════════════════════════════════════════════════════════════
    def on_inside_hvac_system_iteration_loop(self, state) -> int:
        if not self.api.exchange.api_data_fully_ready(state): return 0
        if self.api.exchange.warmup_flag(state):              return 0
        if not self.ready:                                    return 0

        sa = self.api.exchange.set_actuator_value      # shorthand

        # ── Time sync ────────────────────────────────────────────────────
        day  = self.api.exchange.day_of_year(state)
        time = self.api.exchange.current_time(state)
        if self.start_day is None:
            self.start_day = day
        elapsed = (day - self.start_day) * 24.0 + time
        idx     = int(elapsed * 12)

        # ── Outdoor CO₂ override ─────────────────────────────────────────
        if "SPACE1-1" in self.datasets:
            df1 = self.datasets["SPACE1-1"]
            co2 = df1[idx % len(df1)]['outdoor_co2']
            if self.actuators.get("CO2_Out_SP", -1) != -1:
                sa(state, self.actuators["CO2_Out_SP"], co2)

        # ── Central AHU setpoints ────────────────────────────────────────
        if self.actuators.get("OA_Flow_SP", -1) != -1:
            sa(state, self.actuators["OA_Flow_SP"], 1.0)
        sa(state, self.actuators["CC_Temp_SP"], 13.0)
        sa(state, self.actuators["HC_Temp_SP"], 14.0)

        # ── MPC targets ─────────────────────────────────────────────────
        flows, reheats = self.mpc.compute_optimal_control(self.estimations, elapsed)

        # ── Per-zone actuation ───────────────────────────────────────────
        for z in self.zones:
            self._inject_dataset_overrides(state, z, idx)
            self._inject_flow_setpoint(state, z, flows.get(z, 0.1))
            self._inject_reheat_setpoint(state, z, reheats.get(z, 22.0))

        return 0

    # ── Dataset overrides (occupancy / equipment / lights) ───────────────
    def _inject_dataset_overrides(self, state, z, idx):
        if z not in self.datasets:
            return
        sa = self.api.exchange.set_actuator_value
        row = self.datasets[z][idx % len(self.datasets[z])]
        for suffix, key in [("People_SP", "occupant_count"),
                            ("Equip_SP",  "plug_W"),
                            ("Lights_SP", "light_W")]:
            h = self.actuators.get(f"{z}_{suffix}", -1)
            if h != -1:
                sa(state, h, row[key])

    # ── VAV flow triple-clamp ────────────────────────────────────────────
    def _inject_flow_setpoint(self, state, z, flow):
        sa = self.api.exchange.set_actuator_value
        h_sp  = self.actuators.get(f"{z}_Flow_SP",  -1)
        h_max = self.actuators.get(f"{z}_Flow_MAX", -1)
        h_min = self.actuators.get(f"{z}_Flow_MIN", -1)
        if h_sp != -1 and h_max != -1 and h_min != -1:
            sa(state, h_max, flow)
            sa(state, h_min, flow)
            sa(state, h_sp,  flow)

    # ── Reheat setpoint ──────────────────────────────────────────────────
    def _inject_reheat_setpoint(self, state, z, temp):
        h = self.actuators.get(f"{z}_Reheat_SP", -1)
        if h != -1:
            self.api.exchange.set_actuator_value(state, h, temp)
