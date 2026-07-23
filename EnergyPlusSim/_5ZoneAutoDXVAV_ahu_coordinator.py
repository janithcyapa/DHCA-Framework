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
        self.T_neutral = 22.0 # Neutral or average zone temp

        self.W_s_min = w_sat(self.T_s_min)
        self.W_s_max = 0.012
        self.W_neutral = 0.008
        
        self.C_s_min = 400.0
        
        # Rule 4 state variables
        self.T_s_opt = 13.0
        self.delta_T_step = 0.2

        # Setpoint smoothing — protect equipment from rapid changes
        # EMA alpha: 0.0 = no change, 1.0 = no smoothing (instant)
        self.SMOOTH_ALPHA = 0.25   # Blend: 40% new, 60% previous
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
        Calculates central AHU setpoints based on all zones' ideal conditions.
        Implements the 4-rule arbitration logic with comprehensive logging.
        """
        
        if not zone_conditions:
            logger.add("AHU_Coordinator_Status", 0)
            return {
                'ahu_temp_sp': self.T_neutral,
                'ahu_hum_sp': self.W_neutral,
                'ahu_co2_sp': self.C_s_min
            }
        
        logger.add("AHU_Coordinator_Status", 1)
        # Parse conditions and log per-zone inputs
        zone_names = list(zone_conditions.keys())
        ideal_temps = []
        ideal_hums = []
        ideal_co2s = []
        sat_indices = []
        
        for z_name, cond in zone_conditions.items():
            t = cond.get('ideal_temp', self.T_neutral)
            w = cond.get('ideal_hum', self.W_neutral)
            c = cond.get('ideal_co2', 400.0)
            s = cond.get('saturation_index', 0.0)
            
            ideal_temps.append(t)
            ideal_hums.append(w)
            ideal_co2s.append(c)
            sat_indices.append(s)

        # Rule 1: Ventilation (CO2) Arbitration — most demanding zone wins
        C_s_AHU = min(ideal_co2s) if ideal_co2s else 400.0

        
        # Rule 2: Humidity Arbitration
        # Tighten the deadband from 0.001 to 0.0001 to catch slight nighttime drifts
        W_demands_low = [w for w in ideal_hums if w < self.W_neutral - 0.0001]
        W_demands_high = [w for w in ideal_hums if w > self.W_neutral + 0.0001]
        W_demands_neutral = [w for w in ideal_hums if abs(w - self.W_neutral) <= 0.0001]
        
        if W_demands_low:
            # At least one zone wants dehumidification — dehumidification priority
            W_demand = min(ideal_hums)  # Use the driest request
            W_rule = "DEHUMIDIFY"
        elif W_demands_high:
            W_demand = max(ideal_hums)  # Use the most humid request
            W_rule = "HUMIDIFY"
        else:
            W_demand = self.W_neutral
            W_rule = "NEUTRAL"
            
        W_s_AHU = W_demand

        
        # Rule 3: Sensible (Temperature) Arbitration & Psychrometric Coupling
        # Step 3a: Conflict Resolution — use min/max aggregation
        T_demands_cool = [t for t in ideal_temps if t < self.T_neutral - 1.0]
        T_demands_heat = [t for t in ideal_temps if t > self.T_neutral + 1.0]
        T_demands_neutral = [t for t in ideal_temps if abs(t - self.T_neutral) <= 1.0]
        
        n_cool = len(T_demands_cool)
        n_heat = len(T_demands_heat)
        n_neutral = len(T_demands_neutral)
        
        if n_cool > 0 and n_heat == 0:
            # Only cooling requested
            T_demand = min(ideal_temps)
            T_rule = "COOL_ONLY"
        elif n_heat > 0 and n_cool == 0:
            # Only heating requested — raise SAT, don't send cold air!
            T_demand = min(max(ideal_temps), self.T_s_max)
            T_rule = "HEAT_ONLY"
        elif n_cool > 0 and n_heat > 0:
            # Conflict: some zones want cooling, others want heating
            # Cooling priority (standard practice), but clamp to prevent overcooling
            T_demand = min(ideal_temps)
            T_rule = "CONFLICT_COOL_PRIO"
        else:
            # All neutral
            T_demand = self.T_neutral
            T_rule = "NEUTRAL"

        # Step 3b: Psychrometric Override
        def T_sat(W):
            if W <= 0: return 0.0
            P_atm = 101325.0
            P_w = W * P_atm / (0.62198 + W)
            if P_w <= 0: return 0.0
            val = math.log(P_w / 610.94)
            return 243.04 * val / (17.625 - val)
            
        T_sat_bound = T_sat(W_s_AHU)
        
        # Psychrometric ceiling only applies when we're COOLING (dehumidification
        # couples supply temp to dew point).  When ALL zones want HEATING,
        # forcing supply air through a cold dew-point cap is counterproductive:
        # it locks T_s_opt at ~T_sat(W) ≈ 10.7 °C even though every zone
        # needs warm air, which causes MPC to command zero flow (don't send
        # cold air to a cold room), then bang-bang oscillation every timestep
        # as stale duct air floats to ambient.
        if T_rule == "HEAT_ONLY":
            # No dew-point ceiling — let supply temp rise to meet heating demand
            T_bound = min(T_demand, self.T_s_max)
        else:
            # Cooling or conflict: enforce dew-point physics, floored by T_s_min
            T_bound = max(min(T_demand, T_sat_bound), self.T_s_min)
        

        
        # Rule 4: Global Energy Optimization
        I_max = max(sat_indices) if sat_indices else 0.0
        I_mean = sum(sat_indices) / len(sat_indices) if sat_indices else 0.0
        
        T_s_opt_prev = self.T_s_opt
        
        if T_rule == "HEAT_ONLY":
            # All zones want heating — raise supply temperature aggressively
            # Don't keep pushing supply temp down when everyone is cold
            self.T_s_opt = min(self.T_s_opt + self.delta_T_step * 2.0, T_bound)
        elif I_max > 0.95:
            self.T_s_opt = max(self.T_s_opt - self.delta_T_step, self.T_s_min)
        elif I_max < 0.85:
            self.T_s_opt = min(self.T_s_opt + self.delta_T_step, T_bound)
        else:
            self.T_s_opt = min(max(self.T_s_opt, self.T_s_min), T_bound)
            
        T_s_AHU = self.T_s_opt

        
        # Final setpoints — apply smoothing to protect equipment
        T_s_AHU = self._smooth(T_s_AHU, self._prev_T, self.SMOOTH_ALPHA, self.MAX_dT)
        W_s_AHU = self._smooth(W_s_AHU, self._prev_W, self.SMOOTH_ALPHA, self.MAX_dW)
        C_s_AHU = self._smooth(C_s_AHU, self._prev_C, self.SMOOTH_ALPHA, self.MAX_dC)
        self._prev_T = T_s_AHU
        self._prev_W = W_s_AHU
        self._prev_C = C_s_AHU

        logger.add("AHU_Temp_SP_C", round(T_s_AHU, 2))
        logger.add("AHU_W_kg_kg", round(W_s_AHU, 5))
        logger.add("AHU_CO2_ppm", round(C_s_AHU, 2))

        return {
            'ahu_temp_sp': T_s_AHU,
            'ahu_hum_sp': W_s_AHU,
            'ahu_co2_sp': C_s_AHU
        }

    def step(self, zone_conditions, system_state, current_time, logger):
        """
        Coordinates zone conditions to calculate actual actuator commands.
        Includes CO2 PI control, psychrometric coil splits, and DX/Heater toggle.
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
        # Anti-windup clamp
        self._co2_integral = max(min(self._co2_integral, (OA_MAX - OA_MIN)/Ki_oa), 0.0)
        
        oa_flow = OA_MIN + Kp_oa * co2_error + Ki_oa * self._co2_integral
        oa_flow = min(max(oa_flow, OA_MIN), OA_MAX)

        # 2. Temperature & Humidity Setpoints with compensation
        temp_sp = ahu_setpoints.get('ahu_temp_sp', 13.0)
        hum_sp  = ahu_setpoints.get('ahu_hum_sp', 0.008)

        # 2a. Fan heat rise compensation
        fan_out_T = system_state.get('fan_out_T', 0.0)
        hc_out_T = system_state.get('hc_out_T', 0.0)
        if fan_out_T > 0 and hc_out_T > 0:
            measured_dT = fan_out_T - hc_out_T
            if measured_dT > 0:
                self._fan_dT_est = 0.99 * self._fan_dT_est + 0.01 * measured_dT

        sensible_temp_sp = temp_sp - self._fan_dT_est

        # 2b. Psychrometric coupling for dehumidification
        P_w = hum_sp * 101325.0 / (0.62198 + hum_sp)
        T_dew_target = 50.0
        if P_w > 0:
            ln_ratio = math.log(P_w / 610.94)
            T_dew_target = 243.04 * ln_ratio / (17.625 - ln_ratio)

        T_s_min_coil = 5.0
        cc_temp_sp = max(min(sensible_temp_sp, T_dew_target), T_s_min_coil)
        hc_temp_sp = max(sensible_temp_sp, T_s_min_coil)
        sat_sch_sp = hc_temp_sp
        coil_temp_sp = cc_temp_sp
        
        logger.add("CC_Temp_SP_Cmd_C", round(cc_temp_sp, 2))
        logger.add("HC_Temp_SP_Cmd_C", round(hc_temp_sp, 2))
        logger.add("SAT_Sch_SP_Cmd_C", round(sat_sch_sp, 2))

        # 3. Direct ON/OFF Control (Anti-Short Cycle)
        dx_override = ahu_setpoints.get('ahu_dx_override', None)
        heater_override = ahu_setpoints.get('ahu_heater_override', None)
        
        MIN_TOGGLE_DELAY = 0.5 
        
        if dx_override is not None:
            requested = bool(dx_override)
            if requested != self._dx_state:
                if (current_time - self._dx_last_toggle_time) >= MIN_TOGGLE_DELAY:
                    self._dx_state = requested
                    self._dx_last_toggle_time = current_time
            cc_temp_sp = 0.0 if self._dx_state else 50.0

        if heater_override is not None:
            requested = bool(heater_override)
            if requested != self._heater_state:
                if (current_time - self._heater_last_toggle_time) >= MIN_TOGGLE_DELAY:
                    self._heater_state = requested
                    self._heater_last_toggle_time = current_time
            hc_temp_sp = 50.0 if self._heater_state else 0.0
            
        if dx_override is not None or heater_override is not None:
            if self._dx_state:
                sat_sch_sp = 0.0
            elif self._heater_state:
                sat_sch_sp = 50.0
            else:
                sat_sch_sp = 25.0

        logger.add("Fan_dT_est_C", round(self._fan_dT_est, 2))
        logger.add("Coil_Temp_SP_C", round(coil_temp_sp, 2))

        return {
            'oa_flow': oa_flow,
            'sat_sch_sp': sat_sch_sp,
            'cc_temp_sp': cc_temp_sp,
            'hc_temp_sp': hc_temp_sp,
            'hum_sp': hum_sp
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
