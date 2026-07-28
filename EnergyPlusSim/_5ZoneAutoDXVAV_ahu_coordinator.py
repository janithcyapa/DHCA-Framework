"""
AHU Coordinator.
Coordinates the zone ideal conditions to determine AHU setpoints.
Implements multi-zone arbitration logic with comprehensive logging.
"""
import math
import numpy as np
import scipy.sparse as sparse
import osqp

def w_sat(T_C, P_atm=101325.0):
    """
    Saturation humidity ratio (kg/kg dry air) at a given dry-bulb/dew-point
    temperature T_C -- the inverse of T_sat() below. This is the coldest/
    driest air a coil can produce at temperature T_C: the true physical
    floor for dehumidification when no reheat is available.
    """
    gamma = 17.625 * T_C / (243.04 + T_C)
    P_w = 610.94 * math.exp(gamma)
    return 0.62198 * P_w / (P_atm - P_w)

class AHUCoordinator:
    def __init__(self):
        self.ready = False
        
        # AHU physical limits corresponding to the Ideal Ask limits
        self.T_coil_min = 5.0
        self.T_coil_max = 40.0
        self.T_neutral = 22.0 

        self.W_s_min = w_sat(self.T_coil_min)
        self.W_s_max = 0.015
        self.W_neutral = 0.015
        
        self.C_max = 1000.0
        self.gamma_min = 0.04 # (OA_MIN=0.1 / OA_MAX=2.5)

        # Setpoint smoothing — protect equipment from rapid changes
        self.SMOOTH_ALPHA = 0.4   # Blend: 40% new, 60% previous
        self.MAX_dT = 1.5         # °C per timestep
        
        # Previous smoothed setpoints
        self._prev_T_cc = 13.0
        self._prev_T_hc = 13.0
        self._prev_gamma = 0.1
        
        self._fan_dT_est = 0.5
        
        # QP Weights
        self.q_T = 1.0
        self.q_W = 1.0e8
        # self.q_C = 1.0e-3
        self.q_C = 1.0e-2
        self.phi_c = 0.1
        self.phi_h = 0.1
        self.phi_v = 10.0


    def calculate_setpoints(self, zone_conditions, logger):
        """
        Dummy calculation to satisfy the plugin loop. The real QP is solved in step().
        """
        if not zone_conditions:
            logger.add("AHU_Coordinator_Status", 0)
            return {}
        
        logger.add("AHU_Coordinator_Status", 1)
        return {'ready': True}

    def step(self, zone_conditions, system_state, current_time, logger):
        """
        Coordinates zone conditions to calculate actual actuator commands using a QP.
        Returns a dictionary of actuator commands.
        """
        if not zone_conditions:
            return {
                'oa_flow_sp': 0.1,
                'cc_temp_sp': self.T_neutral,
                'hc_temp_sp': self.T_neutral,
                'hum_w_sp': self.W_neutral
            }
            
        # Fan heat rise compensation
        fan_out_T = system_state.get('fan_out_T', 0.0)
        hc_out_T = system_state.get('hc_out_T', 0.0)
        if fan_out_T > 0 and hc_out_T > 0:
            measured_dT = fan_out_T - hc_out_T
            if measured_dT > 0:
                self._fan_dT_est = 0.99 * self._fan_dT_est + 0.01 * measured_dT

        # State Variables
        T_out = system_state.get('T_out', 22.0)
        T_ret = system_state.get('T_ret', 22.0)
        C_out = system_state.get('C_out', 400.0)
        C_ret = system_state.get('C_ret', 400.0)
        
        if C_ret <= 0.0:
            C_ret = system_state.get('actual_co2', 400.0)

        # Linearize humidity w_sat curve at previous T_cc
        # W_s \approx \kappa * T_cc + W_offset
        delta_T = 0.1
        w_plus = w_sat(self._prev_T_cc + delta_T)
        w_minus = w_sat(self._prev_T_cc - delta_T)
        kappa = (w_plus - w_minus) / (2 * delta_T)
        W_offset = w_sat(self._prev_T_cc) - kappa * self._prev_T_cc
        
        sum_psi = 0.0
        sum_omega = 0.0
        sum_chi = 0.0
        sum_psi_W_star = 0.0
        sum_omega_T_star = 0.0
        sum_chi_C_star = 0.0
        
        for z_name, cond in zone_conditions.items():
            T_s_star = cond.get('ideal_temp', self.T_neutral)
            W_s_star = cond.get('ideal_hum', self.W_neutral)
            C_s_star = cond.get('ideal_co2', 400.0)
            u_star = cond.get('u_cmd', 0.1)
            S_i = cond.get('saturation_index', 0.5)
            
            omega_i = self.q_T * (u_star ** 2) * (S_i ** 3)
            psi_i = self.q_W * (u_star ** 2) * (S_i ** 3)
            chi_i = self.q_C * (u_star ** 2) * (S_i ** 3)
            
            sum_omega += omega_i
            sum_psi += psi_i
            sum_chi += chi_i
            
            sum_omega_T_star += omega_i * T_s_star
            sum_psi_W_star += psi_i * W_s_star
            sum_chi_C_star += chi_i * C_s_star
            
        # P matrix (Hessian) for x = [T_cc, T_hc, \gamma]
        P = np.zeros((3, 3))
        P[0, 0] = 2 * sum_psi * (kappa**2) + 2 * self.phi_c + 2 * self.phi_h
        P[1, 1] = 2 * sum_omega + 2 * self.phi_h
        P[2, 2] = 2 * self.phi_c * ((T_out - T_ret)**2) + 2 * sum_chi * ((C_ret - C_out)**2) + 2 * self.phi_v
        
        P[0, 1] = -2 * self.phi_h
        P[1, 0] = -2 * self.phi_h
        
        P[0, 2] = -2 * self.phi_c * (T_out - T_ret)
        P[2, 0] = -2 * self.phi_c * (T_out - T_ret)

        # Add regularization
        P += np.eye(3) * 1e-6
        
        # q matrix (Gradient)
        q = np.zeros(3)
        q[0] = 2 * sum_psi * kappa * W_offset - 2 * kappa * sum_psi_W_star - 2 * self.phi_c * T_ret
        q[1] = 2 * sum_omega * self._fan_dT_est - 2 * sum_omega_T_star
        q[2] = 2 * self.phi_c * T_ret * (T_out - T_ret) - 2 * (C_ret - C_out) * (sum_chi * C_ret - sum_chi_C_star)
        
        # Constraints A x \le u
        A = np.zeros((6, 3))
        l_con = np.zeros(6)
        u_con = np.zeros(6)
        
        # 1. T_cc bounds
        A[0, 0] = 1.0
        l_con[0] = self.T_coil_min
        u_con[0] = self.T_coil_max
        
        # 2. T_hc bounds
        A[1, 1] = 1.0
        l_con[1] = self.T_coil_min
        u_con[1] = self.T_coil_max
        
        # 3. \gamma bounds
        A[2, 2] = 1.0
        l_con[2] = self.gamma_min
        u_con[2] = 1.0
        
        # 4. Cooling Restriction: T_cc + \gamma (T_ret - T_out) \le T_ret
        A[3, 0] = 1.0
        A[3, 2] = T_ret - T_out
        l_con[3] = -np.inf
        u_con[3] = T_ret
        
        # 5. Heating Restriction: -T_cc + T_hc \ge 0
        A[4, 0] = -1.0
        A[4, 1] = 1.0
        l_con[4] = 0.0
        u_con[4] = np.inf
        
        # 6. CO2 Safety: \gamma (C_out - C_ret) \le C_max - C_ret
        A[5, 2] = C_out - C_ret
        l_con[5] = -np.inf
        u_con[5] = self.C_max - C_ret

        # Solve QP
        solver = osqp.OSQP()
        solver.setup(P=sparse.csc_matrix(P), q=q, A=sparse.csc_matrix(A), l=l_con, u=u_con, verbose=False)
        res = solver.solve()
        
        if res.info.status_val in [1, 2]:
            T_cc_cmd = res.x[0]
            T_hc_cmd = res.x[1]
            gamma_cmd = res.x[2]
            logger.add("AHU_QP_Status", res.info.status_val)
        else:
            # Fallback
            T_cc_cmd = self._prev_T_cc
            T_hc_cmd = self._prev_T_hc
            gamma_cmd = self._prev_gamma
            logger.add("AHU_QP_Status", -1)
            
        # Smoothing
        T_cc_cmd = self._smooth(T_cc_cmd, self._prev_T_cc, self.SMOOTH_ALPHA, self.MAX_dT)
        T_hc_cmd = self._smooth(T_hc_cmd, self._prev_T_hc, self.SMOOTH_ALPHA, self.MAX_dT)
        gamma_cmd = self._smooth(gamma_cmd, self._prev_gamma, self.SMOOTH_ALPHA, 0.1) # max delta gamma = 0.1
        
        self._prev_T_cc = T_cc_cmd
        self._prev_T_hc = T_hc_cmd
        self._prev_gamma = gamma_cmd
        
        # Map gamma to OA_Flow_SP
        OA_MAX = 2.5
        oa_flow_sp = gamma_cmd * OA_MAX
        
        hum_w_sp = w_sat(T_cc_cmd)
        
        logger.add("CC_Temp_SP_Cmd_C", round(T_cc_cmd, 2))
        logger.add("HC_Temp_SP_Cmd_C", round(T_hc_cmd, 2))
        logger.add("OA_Frac_Cmd", round(gamma_cmd, 3))
        logger.add("OA_Flow_SP_kg_s", round(oa_flow_sp, 3))
        logger.add("Humidifer_W_SP_kg_kg", round(hum_w_sp, 5))
        logger.add("Fan_dT_est_C", round(self._fan_dT_est, 2))

        return {
            'oa_flow_sp': oa_flow_sp,
            'cc_temp_sp': T_cc_cmd,
            'hc_temp_sp': T_hc_cmd,
            'hum_w_sp': hum_w_sp
        }

    @staticmethod
    def _smooth(new_val, prev_val, alpha, max_delta):
        blended = alpha * new_val + (1.0 - alpha) * prev_val
        delta = blended - prev_val
        if abs(delta) > max_delta:
            blended = prev_val + max_delta * (1.0 if delta > 0 else -1.0)
        return blended
