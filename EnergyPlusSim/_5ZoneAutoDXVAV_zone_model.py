"""
Theoretical Zone Model — Open-Loop RC Thermal Network
======================================================
Runs a pure forward Euler integration of the 2R2C zone model
(no measurement feedback). Compares against EnergyPlus ground truth
to validate the mathematical model before feeding it into the EKF.

State vector (4):  [T_in, T_m, W_in, C_in]
"""
import numpy as np


# ── Physical Constants ───────────────────────────────────────────────────
RHO_AIR   = 1.204      # kg/m³
CP_AIR    = 1006.0      # J/(kg·K)
Q_PERSON  = 100.0       # W per occupant (sensible)
G_W_OCC   = 5e-5        # kg_w/s per occupant
G_CO2_OCC = 1e-5        # kg_co2/s per occupant


class TheoreticalZoneModel:
    """Open-loop 2R2C zone model with humidity and CO₂ tracking."""

    def __init__(self, zone_name, params):
        self.zone_name = zone_name
        self.params = params
        self.state = None                   # np.array([T_in, T_m, W_in, C_in])
        self.SUB_STEPS = 10                 # Euler sub-stepping for stiff ODEs

    # ── Initialise from first measurement ────────────────────────────────
    def initialise(self, T_in_0, W_in_0, C_in_0):
        self.state = np.array([T_in_0, T_in_0, W_in_0, C_in_0])

    # ── One-step forward integration ─────────────────────────────────────
    def step(self, dt, T_out, V_dot_s, T_s, W_s, C_s, occ, Q_equip, adj_data):
        """
        Integrate one EnergyPlus timestep (dt seconds) using sub-stepped Euler.

        Parameters
        ----------
        dt       : float  – timestep in seconds
        T_out    : float  – outdoor dry-bulb temperature (°C)
        V_dot_s  : float  – supply volumetric flow (m³/s)
        T_s, W_s, C_s : float – supply air conditions
        occ      : float  – occupant count
        Q_equip  : float  – equipment heat gain (W)
        adj_data : list[dict] – [{'t_adj': float, 'r_env': float}, ...]
        """
        if self.state is None:
            return

        p = self.params
        R_ext  = p.get("R_env_ext", float('inf'))
        R_int  = p.get("R_int",     0.001)
        C_air  = p.get("C_air",     100_000.0)
        C_mass = p.get("C_mass",    1_000_000.0)
        M_air  = p.get("M_air",     100.0)
        V_room = p.get("V_room",    100.0)

        inv_R_adj = sum(1.0 / a['r_env'] for a in adj_data if a['r_env'] > 0)
        q_int     = occ * Q_PERSON + Q_equip

        dt_sub = dt / self.SUB_STEPS
        for _ in range(self.SUB_STEPS):
            T_in, T_m, W_in, C_in = self.state

            # Heat flows
            q_env  = (T_out - T_in) / R_ext if R_ext < float('inf') else 0.0
            q_adj  = sum(a['t_adj'] / a['r_env'] for a in adj_data if a['r_env'] > 0) - T_in * inv_R_adj
            q_mass = (T_m - T_in) / R_int if R_int > 0 else 0.0
            q_s    = RHO_AIR * V_dot_s * CP_AIR * (T_s - T_in)

            # Derivatives
            dT_in = (q_env + q_adj + q_mass + q_int + q_s) / C_air
            dT_m  = (T_in - T_m) / (C_mass * R_int) if R_int > 0 else 0.0
            dW_in = (occ * G_W_OCC + RHO_AIR * V_dot_s * (W_s - W_in)) / M_air
            dC_in = (occ * G_CO2_OCC + V_dot_s * (C_s - C_in)) / V_room

            self.state += np.array([dT_in, dT_m, dW_in, dC_in]) * dt_sub

        # Safety clamp
        self.state = np.clip(self.state, [-50, -50, 0, 0], [150, 150, 0.1, 10_000])

    # ── Read current state ───────────────────────────────────────────────
    def get_state(self):
        if self.state is None:
            return {"T_in_theo": 0.0, "T_m_theo": 0.0, "W_in_theo": 0.0, "C_in_theo": 0.0}
        return {
            "T_in_theo": self.state[0],
            "T_m_theo":  self.state[1],
            "W_in_theo": self.state[2],
            "C_in_theo": self.state[3],
        }
