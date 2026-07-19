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

        # FIX (bug 2): W_s_min used to be a hardcoded 0.005 kg/kg, which is
        # colder/drier than saturation at T_s_min (10C) can ever deliver
        # without reheat (~0.0076 kg/kg). Requesting it caused Rule 3b's
        # psychrometric override to compute a T_bound below T_s_min, which
        # then got silently accepted by the Rule 4 clip -- commanding the
        # coil to reach an unphysical dew point it can never hit and never
        # actually dehumidifying enough. Derive the true floor instead.
        self.W_s_min = w_sat(self.T_s_min)
        self.W_s_max = 0.015
        self.W_neutral = 0.008
        
        self.C_s_min = 400.0
        
        # Rule 4 state variables
        self.T_s_opt = 13.0
        self.delta_T_step = 0.2

    def calculate_setpoints(self, zone_conditions, logger):
        """
        Calculates central AHU setpoints based on all zones' ideal conditions.
        Implements the 4-rule arbitration logic with comprehensive logging.
        """
        logger.add("AHU_Coordinator_Status", 1)
        
        if not zone_conditions:
            logger.add("AHU_Arbitration_Decision", "NO_ZONES")
            return {
                'ahu_temp_sp': self.T_neutral,
                'ahu_hum_sp': self.W_neutral,
                'ahu_co2_sp': self.C_s_min
            }
        
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
            
            # Log per-zone ideal conditions received by coordinator
            logger.add(f"AHU_in_{z_name}_ideal_T", round(t, 2))
            logger.add(f"AHU_in_{z_name}_ideal_W", round(w, 5))
            logger.add(f"AHU_in_{z_name}_ideal_CO2", round(c, 2))
            logger.add(f"AHU_in_{z_name}_sat_idx", round(s, 3))

        # Rule 1: Ventilation (CO2) Arbitration — most demanding zone wins
        C_s_AHU = min(ideal_co2s) if ideal_co2s else 400.0
        logger.add("AHU_R1_CO2_demand", round(C_s_AHU, 2))
        
        # Rule 2: Humidity Arbitration — use min/max aggregation, not exact equality
        # Dehumidification requests (low W) take priority over humidification
        W_demands_low = [w for w in ideal_hums if w < self.W_neutral - 0.001]
        W_demands_high = [w for w in ideal_hums if w > self.W_neutral + 0.001]
        W_demands_neutral = [w for w in ideal_hums if abs(w - self.W_neutral) <= 0.001]
        
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
        logger.add("AHU_R2_W_demand", round(W_s_AHU, 5))
        logger.add("AHU_R2_W_rule", W_rule)
        logger.add("AHU_R2_n_dehumid", len(W_demands_low))
        logger.add("AHU_R2_n_humid", len(W_demands_high))
        logger.add("AHU_R2_n_neutral", len(W_demands_neutral))
        
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
        
        logger.add("AHU_R3a_T_demand", round(T_demand, 2))
        logger.add("AHU_R3a_T_rule", T_rule)
        logger.add("AHU_R3a_n_cool", n_cool)
        logger.add("AHU_R3a_n_heat", n_heat)
        logger.add("AHU_R3a_n_neutral", n_neutral)
            
        # Step 3b: Psychrometric Override
        def T_sat(W):
            if W <= 0: return 0.0
            P_atm = 101325.0
            P_w = W * P_atm / (0.62198 + W)
            if P_w <= 0: return 0.0
            val = math.log(P_w / 610.94)
            return 243.04 * val / (17.625 - val)
            
        T_sat_bound = T_sat(W_s_AHU)
        # FIX (bug 2): T_sat_bound can fall below T_s_min when a zone's Ideal
        # Ask requests a W_s_AHU the coil physically can't reach at T_s_min.
        # Previously this uncapped T_bound flowed straight into Rule 4's
        # clip(..., T_s_min, T_bound), which -- because T_bound < T_s_min --
        # always collapsed to T_bound, silently commanding supply air colder
        # than the AHU's own declared floor (observed at exactly 3.92C for
        # >25% of a logged run). Since W_s_min is now itself derived from
        # T_s_min (see __init__), this clamp should rarely bind, but it stays
        # as a hard physical guarantee: never ask the coil for a dew point
        # colder than it can deliver without reheat.
        T_bound = max(min(T_demand, T_sat_bound), self.T_s_min)
        
        logger.add("AHU_R3b_T_sat_bound", round(T_sat_bound, 2))
        logger.add("AHU_R3b_T_bound", round(T_bound, 2))
        
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
        
        logger.add("AHU_R4_I_max", round(I_max, 3))
        logger.add("AHU_R4_I_mean", round(I_mean, 3))
        logger.add("AHU_R4_T_s_opt_prev", round(T_s_opt_prev, 2))
        logger.add("AHU_R4_T_s_opt_new", round(self.T_s_opt, 2))
        
        # Final setpoints
        logger.add("ahu_temp_sp", round(T_s_AHU, 2))
        logger.add("ahu_hum_sp", round(W_s_AHU, 5))
        logger.add("ahu_co2_sp", round(C_s_AHU, 2))
        logger.add("ahu_T_bound", round(T_bound, 2))
        logger.add("ahu_I_max", round(I_max, 3))
        
        return {
            'ahu_temp_sp': T_s_AHU,
            'ahu_hum_sp': W_s_AHU,
            'ahu_co2_sp': C_s_AHU
        }
