# controller.py
# This module will hold the Model Predictive Controller (MPC) logic.

class MPCController:
    def __init__(self, zones):
        self.zones = zones
        
    def compute_optimal_control(self, estimations, time_info):
        """
        Takes in EKF estimations and time info, returns optimal setpoints.
        Currently a dummy implementation returning fixed targets.
        """
        # flow_targets, reheat_targets
        flow_targets = {
            "SPACE1-1": 0.18,
            "SPACE2-1": 0.10,
            "SPACE3-1": 0.12,
            "SPACE4-1": 0.14,
            "SPACE5-1": 0.16
        }
        reheat_targets = {z: 12.0 for z in self.zones}
        
        return flow_targets, reheat_targets