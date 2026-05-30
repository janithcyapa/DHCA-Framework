from pyenergyplus.plugin import EnergyPlusPlugin
import csv
import os
import sys
import json




def mat_add(A, B):
    return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
def mat_sub(A, B):
    return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
def mat_mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]
def mat_transpose(A):
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]
def vec_add(a, b):
    return [a[i] + b[i] for i in range(len(a))]
def vec_sub(a, b):
    return [a[i] - b[i] for i in range(len(a))]
def vec_scale(a, scalar):
    return [a[i] * scalar for i in range(len(a))]
def mat_vec_mul(M, v):
    return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]
def mat_inv_3x3(m):
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
           m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
           m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    if det == 0: return [[1.0 if i==j else 0 for j in range(3)] for i in range(3)]
    inv_det = 1.0 / det
    res = [[0]*3 for _ in range(3)]
    res[0][0] = (m[1][1] * m[2][2] - m[2][1] * m[1][2]) * inv_det
    res[0][1] = (m[0][2] * m[2][1] - m[0][1] * m[2][2]) * inv_det
    res[0][2] = (m[0][1] * m[1][2] - m[0][2] * m[1][1]) * inv_det
    res[1][0] = (m[1][2] * m[2][0] - m[1][0] * m[2][2]) * inv_det
    res[1][1] = (m[0][0] * m[2][2] - m[0][2] * m[2][0]) * inv_det
    res[1][2] = (m[1][0] * m[0][2] - m[0][0] * m[1][2]) * inv_det
    res[2][0] = (m[1][0] * m[2][1] - m[2][0] * m[1][1]) * inv_det
    res[2][1] = (m[2][0] * m[0][1] - m[0][0] * m[2][1]) * inv_det
    res[2][2] = (m[0][0] * m[1][1] - m[1][0] * m[0][1]) * inv_det
    return res
def eye(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
def zeros(r, c):
    return [[0.0]*c for _ in range(r)]
def diag(v):
    n = len(v)
    return [[v[i] if i == j else 0.0 for j in range(n)] for i in range(n)]

class HVAC_Coordinator(EnergyPlusPlugin):
    def __init__(self):
        super().__init__()
        self.is_initialized = False
        
        self.csv_path = "./baseline_results/state_log.csv" 
        self.file_obj = None
        self.csv_writer = None
        self.handles = {}
        self.handles = {}
        self.actuators = {}
        self.zones = {}
        self.datasets = {}
        self.start_day = None
        self.ekf_data = {}
        self.model_estimations = {}
        self.zone_params = {}

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

        # 2.5 Load Datasets
        if os.path.exists("./zone_thermal_params.json"):
            with open("./zone_thermal_params.json", "r") as f:
                self.zone_params = json.load(f)

        # 2.5 Load Datasets
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
            headers.extend([f"{z}_Temp_C", f"{z}_T_m_C", f"{z}_W_in_kg_kg", f"{z}_RH_pct", 
                            f"{z}_VAV_Flow_kg_s", f"{z}_Reheater_W", f"{z}_CO2_ppm", 
                            f"{z}_Occupants", f"{z}_EquipLoad_W",
                            f"{z}_T_in_theo", f"{z}_T_m_theo", f"{z}_W_in_theo", f"{z}_C_in_theo",
                            f"{z}_T_in_est", f"{z}_T_m_est", f"{z}_W_in_est", f"{z}_C_in_est", f"{z}_Occ_est"])
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
            
            # Init EKF variables
            P_est = eye(7)
            P_est[6][6] = 10.0
            self.ekf_data[z] = {
                "X_est": None,
                "X_theo": None,
                "P_est": P_est,
                "Q": diag([0.1, 5.0, 1e-6, 10.0, 50.0, 1e-5, 10]),
                "R": diag([0.01, 1e-8, 1.0]),
                "H": zeros(3, 7)
            }
            self.ekf_data[z]["H"][0][0] = 1.0
            self.ekf_data[z]["H"][1][2] = 1.0
            self.ekf_data[z]["H"][2][3] = 1.0
            
            self.model_estimations[z] = {
                "T_in_theo": 0.0, "T_m_theo": 0.0, "W_in_theo": 0.0, "C_in_theo": 0.0,
                "T_in_est": 0.0, "T_m_est": 0.0, "W_in_est": 0.0, "C_in_est": 0.0, "N_occ_est": 0.0
            }

        # Ensure all adjacent zones have temperature handles
        for z, params in self.zone_params.items():
            for adj in params.get("adj_zones", []):
                adj_z = adj["zone"]
                handle_key = f"{adj_z}_Temp"
                if handle_key not in self.handles:
                    self.handles[handle_key] = self.api.exchange.get_variable_handle(state, "Zone Mean Air Temperature", adj_z)

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

            # 5. Grab Dataset Override Actuators
            self.actuators[f"{z}_People_SP"] = self.api.exchange.get_actuator_handle(
                state, "People", "Number of People", f"{z} PEOPLE 1")
            self.actuators[f"{z}_Equip_SP"] = self.api.exchange.get_actuator_handle(
                state, "ElectricEquipment", "Electricity Rate", f"{z} ELECEQ 1")
            self.actuators[f"{z}_Lights_SP"] = self.api.exchange.get_actuator_handle(
                state, "Lights", "Electricity Rate", f"{z} LIGHTS 1")

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
        
        # 4.7 Outdoor CO2 and OA Mixer Actuators
        self.actuators["CO2_Out_SP"] = self.api.exchange.get_actuator_handle(
            state, "Schedule:Constant", "Schedule Value", "CO2-Outdoor-Schedule")
        self.actuators["OA_Flow_SP"] = self.api.exchange.get_actuator_handle(
            state, "Outdoor Air Controller", "Air Mass Flow Rate", "OA CONTROLLER 1")

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
            
        self.run_ekf(state)
        
        return 0
    def run_ekf(self, state):
        dt_hours = self.api.exchange.system_time_step(state)
        if dt_hours == 0: dt_hours = self.api.exchange.zone_time_step(state)
        dt = dt_hours * 3600.0
        if dt <= 0: return

        rho_air, cp_air = 1.204, 1006.0
        q_person, g_w_person, g_co2_person = 100.0, 5e-5, 1e-5

        for z in self.zones:
            p = self.zone_params.get(z)
            if not p: continue
            
            ekf = self.ekf_data[z]
            
            t_in_meas = self.api.exchange.get_variable_value(state, self.handles[f"{z}_Temp"])
            w_in_meas = self.api.exchange.get_variable_value(state, self.handles[f"{z}_W_in"])
            c_in_meas = self.api.exchange.get_variable_value(state, self.handles[f"{z}_CO2"])
            
            m_dot = self.api.exchange.get_variable_value(state, self.handles[f"{z}_VAV_Flow"])
            V_dot_s = m_dot / 1.204
            
            T_out = self.api.exchange.get_variable_value(state, self.handles["Out_Temp"])
            Q_equip = 0.0 # Blind to equip in reality
            
            T_s = self.api.exchange.get_variable_value(state, self.handles[f"{z}_T_s"])
            W_s = self.api.exchange.get_variable_value(state, self.handles[f"{z}_W_s"])
            C_s = self.api.exchange.get_variable_value(state, self.handles[f"{z}_C_s"])
            
            Z_meas = [t_in_meas, w_in_meas, c_in_meas]
            
            if ekf["X_est"] is None:
                ekf["X_est"] = [t_in_meas, t_in_meas, w_in_meas, c_in_meas, 0.0, 0.0, 0.0]
                ekf["X_theo"] = [t_in_meas, t_in_meas, w_in_meas, c_in_meas]
                continue

            T_in_e, T_m_e, W_in_e, C_in_e, d_T_e, d_W_e, N_occ_e = ekf["X_est"]
            T_in_th, T_m_th, W_in_th, C_in_th = ekf["X_theo"]

            # --- Prediction ---
            R_env_ext = p.get("R_env_ext", float('inf'))
            R_int = p.get("R_int", 0.001)
            C_air = p.get("C_air", 100000.0)
            C_mass = p.get("C_mass", 1000000.0)
            M_air = p.get("M_air", 100.0)
            V_room = p.get("V_room", 100.0)
            
            q_env = (T_out - T_in_e) / R_env_ext if R_env_ext < float('inf') else 0.0
            
            _q_adj, inv_R_adj = 0.0, 0.0
            for adj in p.get("adj_zones", []):
                t_adj = self.api.exchange.get_variable_value(state, self.handles[f"{adj['zone']}_Temp"])
                r_env = float(adj["R_env"])
                if r_env > 0:
                    _q_adj += t_adj / r_env
                    inv_R_adj += 1.0 / r_env
            q_adj = _q_adj - (T_in_e * inv_R_adj)
            
            q_mass = (T_m_e - T_in_e) / R_int if R_int > 0 else 0.0
            q_int = (N_occ_e * q_person) + Q_equip
            q_s = rho_air * V_dot_s * cp_air * (T_s - T_in_e)

            dT_in_dt = (q_env + q_adj + q_mass + q_int + q_s + d_T_e) / C_air
            dT_m_dt = (T_in_e - T_m_e) / (C_mass * R_int) if R_int > 0 else 0.0
            dW_in_dt = (N_occ_e * g_w_person + rho_air * V_dot_s * (W_s - W_in_e) + d_W_e) / M_air
            dC_in_dt = (N_occ_e * g_co2_person + V_dot_s * (C_s - C_in_e)) / V_room

            X_pred = vec_add(ekf["X_est"], vec_scale([dT_in_dt, dT_m_dt, dW_in_dt, dC_in_dt, 0.0, 0.0, 0.0], dt))

            # --- Covariance Prediction ---
            df_dX = zeros(7, 7)
            inv_R_ext = 1.0 / R_env_ext if R_env_ext < float('inf') else 0.0
            inv_R_int = 1.0 / R_int if R_int > 0 else 0.0

            df_dX[0][0] = (-inv_R_ext - inv_R_adj - inv_R_int - (rho_air * cp_air * V_dot_s)) / C_air
            df_dX[0][1] = 1.0 / (C_air * R_int) if R_int > 0 else 0.0
            df_dX[0][4] = 1.0 / C_air
            df_dX[0][6] = q_person / C_air

            df_dX[1][0] = 1.0 / (C_mass * R_int) if R_int > 0 else 0.0
            df_dX[1][1] = -1.0 / (C_mass * R_int) if R_int > 0 else 0.0

            df_dX[2][2] = -(rho_air * V_dot_s) / M_air
            df_dX[2][5] = 1.0 / M_air
            df_dX[2][6] = g_w_person / M_air

            df_dX[3][3] = -V_dot_s / V_room
            df_dX[3][6] = g_co2_person / V_room

            F = mat_add(eye(7), [[df_dX[i][j]*dt for j in range(7)] for i in range(7)])
            FP = mat_mul(F, ekf["P_est"])
            FPFt = mat_mul(FP, mat_transpose(F))
            P_pred = mat_add(FPFt, ekf["Q"])

            # --- Update ---
            H = ekf["H"]
            HXp = mat_vec_mul(H, X_pred)
            y = vec_sub(Z_meas, HXp)
            
            HP = mat_mul(H, P_pred)
            HPHt = mat_mul(HP, mat_transpose(H))
            S = mat_add(HPHt, ekf["R"])
            
            S_inv = mat_inv_3x3(S)
            P_Ht = mat_mul(P_pred, mat_transpose(H))
            K = mat_mul(P_Ht, S_inv)
            
            Ky = mat_vec_mul(K, y)
            ekf["X_est"] = vec_add(X_pred, Ky)
            
            KH = mat_mul(K, H)
            I_KH = mat_sub(eye(7), KH)
            ekf["P_est"] = mat_mul(I_KH, P_pred)
            
            ekf["X_est"][6] = max(0.0, ekf["X_est"][6]) # Ensure positive occ

            # --- Theoretical Open-Loop ---
            occ_actual = self.api.exchange.get_variable_value(state, self.handles[f"{z}_Occ"])
            q_int_base = (occ_actual * q_person) + Q_equip
            
            # Sub-stepping for Euler stability on stiff RC nodes
            sub_steps = 10
            dt_sub = dt / sub_steps
            for _ in range(sub_steps):
                T_in_th, T_m_th, W_in_th, C_in_th = ekf["X_theo"]
                
                q_env_th = (T_out - T_in_th) / R_env_ext if R_env_ext < float('inf') else 0.0
                
                _q_adj_th = 0.0
                for adj in p.get("adj_zones", []):
                    t_adj = self.api.exchange.get_variable_value(state, self.handles[f"{adj['zone']}_Temp"])
                    r_env = float(adj["R_env"])
                    if r_env > 0: _q_adj_th += t_adj / r_env
                q_adj_th = _q_adj_th - (T_in_th * inv_R_adj)
                
                q_mass_th = (T_m_th - T_in_th) / R_int if R_int > 0 else 0.0
                q_s_th = rho_air * V_dot_s * cp_air * (T_s - T_in_th)

                dT_in_dt_th = (q_env_th + q_adj_th + q_mass_th + q_int_base + q_s_th) / C_air
                dT_m_dt_th = (T_in_th - T_m_th) / (C_mass * R_int) if R_int > 0 else 0.0
                dW_in_dt_th = (occ_actual * g_w_person + rho_air * V_dot_s * (W_s - W_in_th)) / M_air
                dC_in_dt_th = (occ_actual * g_co2_person + V_dot_s * (C_s - C_in_th)) / V_room

                ekf["X_theo"] = vec_add(ekf["X_theo"], vec_scale([dT_in_dt_th, dT_m_dt_th, dW_in_dt_th, dC_in_dt_th], dt_sub))
            
            # Safety clip to avoid plotting NaNs/Infs
            ekf["X_theo"] = [
                max(-50.0, min(150.0, ekf["X_theo"][0])),
                max(-50.0, min(150.0, ekf["X_theo"][1])),
                max(0.0, min(0.1, ekf["X_theo"][2])),
                max(0.0, min(10000.0, ekf["X_theo"][3]))
            ]

            self.model_estimations[z] = {
                "T_in_theo": ekf["X_theo"][0], "T_m_theo": ekf["X_theo"][1], 
                "W_in_theo": ekf["X_theo"][2], "C_in_theo": ekf["X_theo"][3],
                "T_in_est": ekf["X_est"][0], "T_m_est": ekf["X_est"][1], 
                "W_in_est": ekf["X_est"][2], "C_in_est": ekf["X_est"][3], "N_occ_est": ekf["X_est"][6]
            }


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
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_T_m"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_W_in"]), 5))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_RH"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_VAV_Flow"]), 4))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Reheater"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_CO2"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Occ"]), 2))
            row.append(round(self.api.exchange.get_variable_value(state, self.handles[f"{z}_Equip"]), 2))
            
            est = self.model_estimations.get(z, {})
            row.append(round(est.get("T_in_theo", 0), 2))
            row.append(round(est.get("T_m_theo", 0), 2))
            row.append(round(est.get("W_in_theo", 0), 5))
            row.append(round(est.get("C_in_theo", 0), 2))
            
            row.append(round(est.get("T_in_est", 0), 2))
            row.append(round(est.get("T_m_est", 0), 2))
            row.append(round(est.get("W_in_est", 0), 5))
            row.append(round(est.get("C_in_est", 0), 2))
            row.append(round(est.get("N_occ_est", 0), 2))

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

        # Time Sync for Datasets
        current_day = self.api.exchange.day_of_year(state)
        current_time = self.api.exchange.current_time(state) # 0.0 to 24.0
        
        if self.start_day is None:
            self.start_day = current_day

        # 12 rows per hour for 5-min intervals
        elapsed_hours = (current_day - self.start_day) * 24.0 + current_time
        raw_idx = int(elapsed_hours * 12)

        # Actuate Outdoor CO2 using Room1 dataset as baseline
        if "SPACE1-1" in self.datasets:
            df1 = self.datasets["SPACE1-1"]
            idx1 = raw_idx % len(df1)
            outdoor_co2 = df1[idx1]['outdoor_co2']
            if self.actuators.get("CO2_Out_SP", -1) != -1:
                self.api.exchange.set_actuator_value(state, self.actuators["CO2_Out_SP"], outdoor_co2)

        # Actuate OA Controller Mass Flow Rate (dummy value for now, e.g. 0.2 kg/s)
        # You can replace 0.2 with an MPC target for fresh air!
        if self.actuators.get("OA_Flow_SP", -1) != -1:
            self.api.exchange.set_actuator_value(state, self.actuators["OA_Flow_SP"], 1.0)

        # Override Central Cooling and Heating Coil Setpoints
        self.api.exchange.set_actuator_value(state, self.actuators["CC_Temp_SP"], 13.0)
        self.api.exchange.set_actuator_value(state, self.actuators["HC_Temp_SP"], 14.0)

        total_fan_flow = 0.0

        for z in self.zones:
            # Inject Dataset Overrides
            if z in self.datasets:
                df = self.datasets[z]
                idx = raw_idx % len(df)
                
                # Extract values
                occ_count = df[idx]['occupant_count']
                equip_w = df[idx]['plug_W']
                light_w = df[idx]['light_W']
                
                # Set Actuators
                handle_occ = self.actuators.get(f"{z}_People_SP", -1)
                handle_eq = self.actuators.get(f"{z}_Equip_SP", -1)
                handle_lt = self.actuators.get(f"{z}_Lights_SP", -1)
                
                if handle_occ != -1: self.api.exchange.set_actuator_value(state, handle_occ, occ_count)
                if handle_eq != -1: self.api.exchange.set_actuator_value(state, handle_eq, equip_w)
                if handle_lt != -1: self.api.exchange.set_actuator_value(state, handle_lt, light_w)

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