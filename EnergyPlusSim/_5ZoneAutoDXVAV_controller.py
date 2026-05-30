"""
MPC Controller — Zone-Level Setpoint Optimiser
================================================
Receives EKF state estimates and computes optimal
VAV flow rates and reheat temperatures per zone.

Currently a placeholder returning fixed targets.
Replace compute_optimal_control() with a real QP/NLP solver
(e.g. scipy.optimize or cvxpy) once the EKF is validated.
"""
import numpy as np


class MPCController:
    """Model Predictive Controller for multi-zone HVAC."""

    def __init__(self, zones):
        self.zones = zones

    def compute_optimal_control(self, estimations, time_info):
        """
        Compute optimal setpoints given current EKF estimates.

        Parameters
        ----------
        estimations : dict[str, dict] – per-zone EKF state estimates
        time_info   : float           – elapsed simulation hours

        Returns
        -------
        flow_targets   : dict[str, float] – VAV mass flow (kg/s) per zone
        reheat_targets : dict[str, float] – reheat temp setpoint (°C) per zone
        """
        # ── Placeholder: fixed targets ───────────────────────────────────
        flow_targets = {
            "SPACE1-1": 0.18,
            "SPACE2-1": 0.10,
            "SPACE3-1": 0.12,
            "SPACE4-1": 0.14,
            "SPACE5-1": 0.16,
        }
        reheat_targets = {z: 12.0 for z in self.zones}

        return flow_targets, reheat_targets