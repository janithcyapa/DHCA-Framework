"""
AHU Coordinator.
Coordinates the zone ideal conditions to determine AHU setpoints.
Implements multi-zone arbitration logic with comprehensive logging.
"""
import math

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
        self.T_s_min = 10.0
        self.T_s_max = 40.0
        self.T_neutral = 22.0 

        self.W_s_min = w_sat(self.T_s_min)
        self.W_s_max = 0.015
        self.W_neutral = 0.015
        
        self.C_s_min = 400.0
        
        # Rule 4 state variables
        self.T_s_opt = 13.0
        self.delta_T_step = 0.2

        # Setpoint smoothing — protect equipment from rapid changes
        # EMA alpha: 0.0 = no change, 1.0 = no smoothing (instant)
        self.SMOOTH_ALPHA = 0.1   # Blend: 40% new, 60% previous
        # Max change per timestep (rate limiter, on top of EMA)
        self.MAX_dT = 1.5         # °C per timestep
        self.MAX_dW = 0.001       # kg/kg per timestep
        self.MAX_dC = 50.0        # ppm per timestep
        # Previous smoothed setpoints
        self._prev_T = self.T_neutral
        self._prev_W = self.W_neutral
        self._prev_C = self.C_s_min
        
        # State variables for control logic moved from 5ZoneAutoDXVAV.py
        self._fan_dT_est = 0.5
        self._co2_integral = 0.0
        self._dx_state = False
        self._dx_last_toggle_time = -999.0
        self._heater_state = False
        self._heater_last_toggle_time = -999.0

    def calculate_setpoints(self, zone_conditions, logger):
        """
        Calculates central AHU setpoints based on worst-case logic.
        """
        if not zone_conditions:
            logger.add("AHU_Coordinator_Status", 0)
            return {
                'ahu_temp_sp': self.T_neutral,
                'ahu_hum_sp': self.W_neutral,
                'ahu_co2_sp': self.C_s_min
            }
        
        logger.add("AHU_Coordinator_Status", 1)
        
        ideal_temps = []
        ideal_hums = []
        ideal_co2s = []
        
        for z_name, cond in zone_conditions.items():
            ideal_temps.append(cond.get('ideal_temp', self.T_neutral))
            ideal_hums.append(cond.get('ideal_hum', self.W_neutral))
            ideal_co2s.append(cond.get('ideal_co2', 400.0))

        # CO2: min requested (most fresh air)
        C_s_AHU = min(ideal_co2s) if ideal_co2s else 400.0
        
        # Humidity: min requested (most dehumidification)
        W_s_AHU = min(ideal_hums) if ideal_hums else self.W_neutral
        
        # Temperature: if any zone wants cooling, provide max cooling requested.
        # Otherwise, if any zone wants heating, provide max heating requested.
        T_demands_cool = [t for t in ideal_temps if t < self.T_neutral - 0.5]
        T_demands_heat = [t for t in ideal_temps if t > self.T_neutral + 0.5]
        
        if T_demands_cool:
            T_s_AHU = min(T_demands_cool)
        elif T_demands_heat:
            T_s_AHU = max(T_demands_heat)
        else:
            T_s_AHU = self.T_neutral
            
        # Final setpoints — apply smoothing to protect equipment
        T_s_AHU = self._smooth(T_s_AHU, self._prev_T, self.SMOOTH_ALPHA, self.MAX_dT)
        W_s_AHU = self._smooth(W_s_AHU, self._prev_W, self.SMOOTH_ALPHA, self.MAX_dW)
        C_s_AHU = self._smooth(C_s_AHU, self._prev_C, self.SMOOTH_ALPHA, self.MAX_dC)
        self._prev_T = T_s_AHU
        self._prev_W = W_s_AHU
        self._prev_C = C_s_AHU

        logger.add("Cord_Temp_SP_C", round(T_s_AHU, 2))
        logger.add("Cord_W_kg_kg", round(W_s_AHU, 5))
        logger.add("Cord_CO2_ppm", round(C_s_AHU, 2))

        return {
            'ahu_temp_sp': T_s_AHU,
            'ahu_hum_sp': W_s_AHU,
            'ahu_co2_sp': C_s_AHU
        }

    def step(self, zone_conditions, system_state, current_time, logger):
        """
        Coordinates zone conditions to calculate actual actuator commands.
        Includes CO2 PI control, psychrometric coil splits, and heating/cooling.
        Returns a dictionary of actuator commands.
        """
        # Calculate raw setpoints from rules
        ahu_setpoints = self.calculate_setpoints(zone_conditions, logger)

        # 1. CO2 Control via Outdoor Air Flow — PI Controller
        Kp_oa = 0.003
        Ki_oa = 0.002
        OA_MIN = 0.1
        OA_MAX = 2.5

        co2_sp = ahu_setpoints.get('ahu_co2_sp', 400.0)
        actual_co2 = system_state.get('actual_co2', 400.0)
        
        co2_error = actual_co2 - co2_sp
        self._co2_integral += co2_error
        self._co2_integral = max(min(self._co2_integral, (OA_MAX - OA_MIN)/Ki_oa), 0.0)
        
        oa_flow_sp = OA_MIN + Kp_oa * co2_error + Ki_oa * self._co2_integral
        oa_flow_sp = min(max(oa_flow_sp, OA_MIN), OA_MAX)

        # 2. Temperature & Humidity Setpoints with compensation
        temp_sp = ahu_setpoints.get('ahu_temp_sp', 13.0)
        hum_w_sp  = ahu_setpoints.get('ahu_hum_sp', 0.015)

        # 2a. Fan heat rise compensation
        fan_out_T = system_state.get('fan_out_T', 0.0)
        hc_out_T = system_state.get('hc_out_T', 0.0)
        if fan_out_T > 0 and hc_out_T > 0:
            measured_dT = fan_out_T - hc_out_T
            if measured_dT > 0:
                self._fan_dT_est = 0.99 * self._fan_dT_est + 0.01 * measured_dT

        temp_sp = temp_sp - self._fan_dT_est

        # 2b. Psychrometric coupling for dehumidification
        P_w = hum_w_sp * 101325.0 / (0.62198 + hum_w_sp)
        T_dew_target = 50.0
        if P_w > 0:
            ln_ratio = math.log(P_w / 610.94)
            T_dew_target = 243.04 * ln_ratio / (17.625 - ln_ratio)

        T_s_min_coil = 5.0
        cc_temp_sp = max(min(temp_sp, T_dew_target), T_s_min_coil)
        hc_temp_sp = max(temp_sp, T_s_min_coil)
        
        logger.add("CC_Temp_SP_Cmd_C", round(cc_temp_sp, 2))
        logger.add("HC_Temp_SP_Cmd_C", round(hc_temp_sp, 2))
        logger.add("Fan_dT_est_C", round(self._fan_dT_est, 2))
        logger.add("Humidifer_W_SP_kg_kg", round(hum_w_sp, 5))


        return {
            'oa_flow_sp': oa_flow_sp,
            'cc_temp_sp': cc_temp_sp,
            'hc_temp_sp': hc_temp_sp,
            'hum_w_sp': hum_w_sp
        }

    @staticmethod
    def _smooth(new_val, prev_val, alpha, max_delta):
        """
        Smooth a setpoint with EMA + rate limiter.
        alpha: blend weight for new value (0..1)
        max_delta: maximum allowed change per timestep
        """
        # EMA blend
        blended = alpha * new_val + (1.0 - alpha) * prev_val
        # Rate limiter
        delta = blended - prev_val
        if abs(delta) > max_delta:
            blended = prev_val + max_delta * (1.0 if delta > 0 else -1.0)
        return blended