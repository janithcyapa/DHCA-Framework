# zone_model.py

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

class EKFEstimator:
    def __init__(self, zone_name):
        self.zone_name = zone_name
        
        P_est = eye(7)
        P_est[6][6] = 10.0
        self.ekf = {
            "X_est": None,
            "X_theo": None,
            "P_est": P_est,
            "Q": diag([0.1, 5.0, 1e-6, 10.0, 50.0, 1e-5, 10.0]),
            "R": diag([0.01, 1e-8, 1.0]),
            "H": zeros(3, 7)
        }
        self.ekf["H"][0][0] = 1.0
        self.ekf["H"][1][2] = 1.0
        self.ekf["H"][2][3] = 1.0

    def predict_and_update(self, dt, params, z_meas, u_inputs, boundary_inputs):
        t_in_meas, w_in_meas, c_in_meas = z_meas
        V_dot_s, Q_equip, T_s, W_s, C_s = u_inputs
        T_out, adj_zones, occ_actual = boundary_inputs
        
        ekf = self.ekf
        
        if ekf["X_est"] is None:
            ekf["X_est"] = [t_in_meas, t_in_meas, w_in_meas, c_in_meas, 0.0, 0.0, 0.0]
            ekf["X_theo"] = [t_in_meas, t_in_meas, w_in_meas, c_in_meas]
            return
            
        T_in_e, T_m_e, W_in_e, C_in_e, d_T_e, d_W_e, N_occ_e = ekf["X_est"]
        T_in_th, T_m_th, W_in_th, C_in_th = ekf["X_theo"]

        rho_air, cp_air = 1.204, 1006.0
        q_person, g_w_person, g_co2_person = 100.0, 5e-5, 1e-5

        R_env_ext = params.get("R_env_ext", float('inf'))
        R_int = params.get("R_int", 0.001)
        C_air = params.get("C_air", 100000.0)
        C_mass = params.get("C_mass", 1000000.0)
        M_air = params.get("M_air", 100.0)
        V_room = params.get("V_room", 100.0)
        
        q_env = (T_out - T_in_e) / R_env_ext if R_env_ext < float('inf') else 0.0
        
        _q_adj, inv_R_adj = 0.0, 0.0
        for adj in adj_zones:
            if adj['r_env'] > 0:
                _q_adj += adj['t_adj'] / adj['r_env']
                inv_R_adj += 1.0 / adj['r_env']
        q_adj = _q_adj - (T_in_e * inv_R_adj)
        
        q_mass = (T_m_e - T_in_e) / R_int if R_int > 0 else 0.0
        q_int = (N_occ_e * q_person) + Q_equip
        q_s = rho_air * V_dot_s * cp_air * (T_s - T_in_e)

        dT_in_dt = (q_env + q_adj + q_mass + q_int + q_s + d_T_e) / C_air
        dT_m_dt = (T_in_e - T_m_e) / (C_mass * R_int) if R_int > 0 else 0.0
        dW_in_dt = (N_occ_e * g_w_person + rho_air * V_dot_s * (W_s - W_in_e) + d_W_e) / M_air
        dC_in_dt = (N_occ_e * g_co2_person + V_dot_s * (C_s - C_in_e)) / V_room

        X_pred = vec_add(ekf["X_est"], vec_scale([dT_in_dt, dT_m_dt, dW_in_dt, dC_in_dt, 0.0, 0.0, 0.0], dt))

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

        H = ekf["H"]
        HXp = mat_vec_mul(H, X_pred)
        y = vec_sub(z_meas, HXp)
        
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
        
        ekf["X_est"][6] = max(0.0, ekf["X_est"][6]) 

        # --- Theoretical Open-Loop ---
        q_int_base = (occ_actual * q_person) + Q_equip
        
        sub_steps = 10
        dt_sub = dt / sub_steps
        for _ in range(sub_steps):
            T_in_th, T_m_th, W_in_th, C_in_th = ekf["X_theo"]
            
            q_env_th = (T_out - T_in_th) / R_env_ext if R_env_ext < float('inf') else 0.0
            
            _q_adj_th = 0.0
            for adj in adj_zones:
                if adj['r_env'] > 0: _q_adj_th += adj['t_adj'] / adj['r_env']
            q_adj_th = _q_adj_th - (T_in_th * inv_R_adj)
            
            q_mass_th = (T_m_th - T_in_th) / R_int if R_int > 0 else 0.0
            q_s_th = rho_air * V_dot_s * cp_air * (T_s - T_in_th)

            dT_in_dt_th = (q_env_th + q_adj_th + q_mass_th + q_int_base + q_s_th) / C_air
            dT_m_dt_th = (T_in_th - T_m_th) / (C_mass * R_int) if R_int > 0 else 0.0
            dW_in_dt_th = (occ_actual * g_w_person + rho_air * V_dot_s * (W_s - W_in_th)) / M_air
            dC_in_dt_th = (occ_actual * g_co2_person + V_dot_s * (C_s - C_in_th)) / V_room

            ekf["X_theo"] = vec_add(ekf["X_theo"], vec_scale([dT_in_dt_th, dT_m_dt_th, dW_in_dt_th, dC_in_dt_th], dt_sub))
        
        ekf["X_theo"] = [
            max(-50.0, min(150.0, ekf["X_theo"][0])),
            max(-50.0, min(150.0, ekf["X_theo"][1])),
            max(0.0, min(0.1, ekf["X_theo"][2])),
            max(0.0, min(10000.0, ekf["X_theo"][3]))
        ]

    def get_estimations(self):
        if self.ekf["X_est"] is None:
            return {
                "T_in_theo": 0.0, "T_m_theo": 0.0, "W_in_theo": 0.0, "C_in_theo": 0.0,
                "T_in_est": 0.0, "T_m_est": 0.0, "W_in_est": 0.0, "C_in_est": 0.0, "N_occ_est": 0.0
            }
        return {
            "T_in_theo": self.ekf["X_theo"][0], "T_m_theo": self.ekf["X_theo"][1], 
            "W_in_theo": self.ekf["X_theo"][2], "C_in_theo": self.ekf["X_theo"][3],
            "T_in_est": self.ekf["X_est"][0], "T_m_est": self.ekf["X_est"][1], 
            "W_in_est": self.ekf["X_est"][2], "C_in_est": self.ekf["X_est"][3], "N_occ_est": self.ekf["X_est"][6]
        }
