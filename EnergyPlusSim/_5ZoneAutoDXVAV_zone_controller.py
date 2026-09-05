"""
Zone Controller.
Encapsulates the EKF and MPC for a specific zone.
"""
import numpy as np
import scipy.sparse as sparse
import osqp
import time
import math


def w_sat(T_C, P_atm=101325.0):
    """
    Saturation humidity ratio (kg/kg dry air) at a given dry-bulb/dew-point
    temperature T_C, via the inverse of the Magnus formula used elsewhere
    in this codebase (see AHUCoordinator.T_sat). This is the coldest/driest
    air a coil can produce at temperature T_C -- the true physical floor
    for dehumidification WITHOUT reheat.
    """
    gamma = 17.625 * T_C / (243.04 + T_C)
    P_w = 610.94 * math.exp(gamma)
    return 0.62198 * P_w / (P_atm - P_w)

def get_w_from_rh(T, rh):
    p_sat = 610.94 * math.exp(17.625 * T / (243.04 + T))
    p_vapor = rh * p_sat
    return 0.62198 * p_vapor / (101325.0 - p_vapor)


class ZoneController:
    def __init__(self, zone_name):
        self.zone_name = zone_name
        self.ready = False
        
        # --- EKF Initialization ---
        # State vector x: [T_in, T_m, W_in, C_in, d_T, d_W, N_occ, alpha_ext, alpha_int, beta_air, beta_mass, d_C]
        self.x = np.zeros(12)
        
        # --- Physical States ---
        self.x[0] = 22.0    # x1: T_in (C)
        self.x[1] = 22.0    # x2: T_m (C)
        self.x[2] = 0.008   # x3: W_in (kg/kg)
        self.x[3] = 420.0   # x4: C_in (ppm)
        
        # --- Disturbances ---
        self.x[4] = 0.0     # x5: d_T
        self.x[5] = 0.0     # x6: d_W
        self.x[6] = 0.0     # x7: N_occ
        self.x[11] = 0.0    # x12: d_C (CO2 disturbance)
        
        # --- Structural Parameters ---

        self.x[7] = 1000   # x8: alpha_ext (1/R_ext)
        self.x[8] = 1000   # x9: alpha_int (1/R_int)
        self.x[9] = 0  # x10: beta_air (1/C_air)
        self.x[10] = 0  # x11: beta_mass (1/C_mass)


        # P Matrix - Error Covariance matrix (Initial Uncertainty)
        self.P = np.diag([
            1.0, 1.0, 1e-4, 100.0,          # T_in, T_m, W_in, C_in
            10.0, 1e-6, 1.0,                # d_T, d_W, N_occ
            2500.0, 2500.0, 100, 100,   # alpha_ext, alpha_int (Massive initial uncertainty!)
            10.0                            # d_C
        ])
        
        # Q Matrix - Range-Normalized Process Noise
        #
        # Each entry = time_scale_weight × σᵢ²
        # where σᵢ is the expected per-step natural variation of state xᵢ
        # at its own physical scale.  Multiplying by σᵢ² makes every entry
        # dimensionally equivalent so the EKF doesn't prefer small-unit states
        # (W in kg/kg ≈ 0.008) over large-unit states (C in ppm ≈ 400-1000).
        #
        # Typical ranges used for normalization (1-sigma natural variation):
        #   T_in       : σ ≈ 1 °C           → σ² = 1.0
        #   T_m        : σ ≈ 2 °C           → σ² = 4.0     [was frozen in plot → increased]
        #   W_in       : σ ≈ 2e-3 kg/kg     → σ² = 4e-6    [was lagging badly → increased]
        #   C_in       : σ ≈ 50 ppm         → σ² = 2500.0  [was too slow → faster time weight]
        #   d_T        : σ ≈ 200 W          → σ² = 4e4
        #   d_W        : σ ≈ 2e-4 kg/s      → σ² = 4e-8    [was over-compensating → bumped]
        #   N_occ      : σ ≈ 3 persons      → σ² = 9.0     [was exploding to 29 → tightened]
        #   alpha_ext/int : σ ≈ 500 W/K     → σ² = 2.5e5
        #   beta_air   : σ ≈ 1e-5 K/J       → σ² = 1e-10
        #   beta_mass  : σ ≈ 1e-7 K/J       → σ² = 1e-14
        #   d_C        : σ ≈ 50 ppm         → σ² = 2500.0
        #
        # time_scale_weight encodes how fast each state is ALLOWED to drift:
        #   Fast (observed physics)    : ~1e-5 to 1e-6 per second
        #   Slow disturbances          : ~1e-8 per second
        #   Very slow (param learning) : ~1e-12 to 1e-14 per second
        #
        # Tuning history (see plot entry_0006):
        #   T_m   : time weight 1e-6→1e-5   (wall temp was frozen at ceiling)
        #   W_in  : σ 5e-4→2e-3 kg/kg       (EKF lagged raw humidity by ~0.001)
        #   C_in  : time weight 1e-8→1e-7   (CO2 took 10+ min to respond to step changes)
        #   N_occ : time weight 1e-8→1e-9   (diverged to ~29 persons vs actual 0–3)
        #   d_W   : σ 5e-5→2e-4 kg/s        (latent disturbance absorbing N_occ error)
        #   d_C   : time weight 1e-8→1e-9   (absorbing CO2 error that C_in should handle)

        _q_T    = 1e-6  * 1.0       # T_in:       fast physics, σ=1°C
        _q_Tm   = 1e-5  * 4.0       # T_m:        wall mass — allowed more freedom, σ=2°C
        _q_W    = 1e-6  * 4e-6      # W_in:       fast physics, σ=2e-3 kg/kg (was lagging)
        _q_C    = 1e-7  * 2500.0    # C_in:       faster tracking needed, σ=50 ppm
        _q_dT   = 1e-8  * 4e4       # d_T:        slow disturbance, σ=200 W
        _q_dW   = 1e-8  * 4e-8      # d_W:        latent disturbance, σ=2e-4 kg/s
        _q_Nocc = 1e-9  * 9.0       # N_occ:      tightened — was exploding, σ=3 persons
        _q_aext = 1e-12 * 2.5e5     # alpha_ext:  very slow param, σ=500 W/K
        _q_aint = 1e-12 * 2.5e5     # alpha_int:  very slow param, σ=500 W/K
        _q_bair = 1e-14 * 1e-10     # beta_air:   very slow param, σ=1e-5 K/J
        _q_bmas = 1e-14 * 1e-14     # beta_mass:  frozen baseline floor, σ=1e-7 K/J
        _q_dC   = 1e-9  * 2500.0    # d_C:        tightened — C_in now handles CO2 faster

        self.Q = np.diag([
            _q_T, _q_Tm, _q_W, _q_C,       # Core Physics
            _q_dT, _q_dW, _q_Nocc,         # Slow Disturbances
            _q_aext, _q_aint, _q_bair, _q_bmas,  # Parameters (very slow)
            _q_dC                           # Slow CO2 Disturbance
        ])
        
        # Measurement Noise Covariance R
        self.R = np.diag([0.01, 1e-8, 15.0])
        
        self.H = np.zeros((3, 12))
        self.H[0, 0] = 1.0
        self.H[1, 2] = 1.0
        self.H[2, 3] = 1.0

        # Constantas
        self.rho_air = 1.204
        self.c_p = 1006.0
        self.q_person = 100.0
        self.g_w_person = 5e-5
        rho_co2 = 1.81
        # self.g_co2_person = ((3.82e-8 * 120.0) / rho_co2) * 1e6
        self.g_co2_person = 20.0
        # --- MPC Initialization ---
        self.N = 20 

        self.r = 1e-5
        self.r_delta = 1e-1 

        self.lambda_T = 1e3
        self.lambda_W = 1e8  
        self.lambda_C = 1e1

        self.mu_T = 1e1  
        self.du_max = 1.0

        # Centering weights
        self.q_T_center = 5.0
        self.q_W_center = 1e2 

        # --- Phase 2 QP (Ideal Ask) weights & reference points ---
        self.q_T_ask = 1.0
        self.q_W_ask = 1.0e6
        self.q_C_ask = 1.0e-3

        # Solver Config
        self.max_iter=50000
        self.eps_abs=1e-3
        self.eps_rel=1e-3

        # U EMA filter
        self.u_smooth_alpha = 1.0  
        self.u_prev = 0.5
        self.u_ema = 0.5
        
        T_in = self.x[0]

        # MPC Zones and Other Limits
        # Temperature
        self.T_ref = 22.0
        self.T_delta = 1.0
        self.T_max = self.T_ref + self.T_delta
        self.T_min = self.T_ref -self.T_delta
        # Humidity
        rh_min = 0.30
        rh_max = 0.60
        self.W_min = get_w_from_rh(T_in, rh_min)
        self.W_max = get_w_from_rh(T_in, rh_max)
        # CO2
        self.C_max = 1000.0
        # Flow
        self.u_min = 0.05
        self.u_max = 2.0
        # Supply Limits
        self.T_s_min = 10.0
        self.T_s_max = 40.0
        self.W_s_min = w_sat(self.T_s_min) 
        self.W_s_max = 0.015
        self.C_s_min = 420.0
        self.C_s_max = self.C_max
        
     

        
        self.setup_mpc_constants()
        
    def setup_mpc_constants(self):
        N = self.N
        
        # Differencing matrix for rate-of-change penalty
        D = np.zeros((N, N))
        np.fill_diagonal(D, 1.0)
        for i in range(1, N):
            D[i, i-1] = -1.0
        self.D = D
        
        E = np.zeros(N)
        E[0] = 1.0
        self.E = E
        
        self.I_N = np.eye(N)
        self.O_N = np.zeros((N, N))
        self.zeros_N = np.zeros(N)
        
        # Selection matrices to extract T, W, C from stacked state predictions
        self.ST = np.zeros((N, 4*N))
        self.SW = np.zeros((N, 4*N))
        self.SC = np.zeros((N, 4*N))
        for i in range(N):
            self.ST[i, i*4 + 0] = 1.0
            self.SW[i, i*4 + 2] = 1.0
            self.SC[i, i*4 + 3] = 1.0

    def _build_hessian(self, N, FT=None, FW=None):
        """Build QP Hessian with quadratic centering cost + regularization.
        
        The centering cost adds q_T * ||FT@u + gT - T_ref||^2 to the objective.
        Expanding: the u-quadratic part is q_T * u' FT'FT u, which adds
        2*q_T * FT'FT to the u-block of the Hessian. The linear part
        (involving gT - T_ref) is handled in the f vector, not here.
        """
        R = np.eye(N) * self.r
        DR = np.eye(N) * self.r_delta
        
        H_U = 2.0 * (R + self.D.T @ DR @ self.D)
        
        # Quadratic centering: add FT'FT and FW'FW to u-block
        if FT is not None:
            H_U += 2.0 * self.q_T_center * (FT.T @ FT)
        if FW is not None:
            H_U += 2.0 * self.q_W_center * (FW.T @ FW)
        
        H_eps_T = 2.0 * np.eye(N) * self.lambda_T
        H_eps_W = 2.0 * np.eye(N) * self.lambda_W
        H_eps_C = 2.0 * np.eye(N) * self.lambda_C
        
        n_vars = 4 * N
        H = np.zeros((n_vars, n_vars))
        H[0:N, 0:N] = H_U
        H[N:2*N, N:2*N] = H_eps_T
        H[2*N:3*N, 2*N:3*N] = H_eps_W
        H[3*N:4*N, 3*N:4*N] = H_eps_C
        
        # Regularization: ensure strict positive-definiteness to prevent OSQP Status 7
        H += np.eye(n_vars) * 1e-6
        
        return sparse.csc_matrix(H)

    def _fallback_control(self, state_data):
        """
        Proportional fallback controller when MPC fails to solve.
        Uses simple error-based logic rather than just returning u_prev.
        """
        T_in = state_data.get('T_in', self.x[0])
        W_in = state_data.get('W_in', self.x[2])
        C_in = state_data.get('C_in', self.x[3])
        T_s = state_data.get('T_s', 13.0)
        
        # Temperature error: positive means zone is too hot, needs more cooling flow
        e_T = T_in - self.T_ref
        
        # CO2 error: positive means zone has too much CO2, needs more fresh air
        e_C = max(0.0, C_in - self.C_max) / self.C_max
        
        # Humidity error: positive means too humid
        W_ref = (self.W_max + self.W_min) / 2.0
        e_W = max(0.0, W_in - self.W_max) / self.W_max
        
        # If zone is colder than supply air, reduce flow (don't pump cold air into cold zone)
        if T_in < T_s + 1.0:
            # Zone is cold enough — minimal flow for ventilation only
            u_fb = 0.1
        elif e_T > 0.5:
            # Zone is too hot — increase flow proportionally
            u_fb = min(self.u_max, 0.3 + e_T * 0.3)
        elif e_T < -0.5:
            # Zone is too cold — reduce flow
            u_fb = 0.1
        else:
            # In deadband — moderate flow for ventilation + humidity/CO2
            u_fb = 0.2 + e_C * 0.5 + e_W * 0.3
        
        u_fb = np.clip(u_fb, self.u_min, self.u_max)
        u_fb = np.clip(u_fb, self.u_prev - self.du_max, self.u_prev + self.du_max)  # NEW
        return u_fb

    def _fallback_ideal_ask(self, T_in, W_in, C_in, T_neutral, W_neutral):
        """
        Fallback for the Phase-2 Ideal-Ask QP when it fails to solve.
        This is the old proportional/bang-bang heuristic, kept only as a
        safety net (mirrors _fallback_control's role for the flow QP).
        """
        T_ref = self.T_ref
        W_ref = (self.W_max + self.W_min) / 2.0
        e_T = T_ref - T_in
        e_W = W_ref - W_in

        T_s_min, T_s_max = self.T_s_min, self.T_s_max
        W_s_min = self.W_s_min

        if e_T > 0.5:
            T_s_star = T_s_max
        elif e_T > 0.1:
            alpha = (e_T - 0.1) / 0.4
            T_s_star = T_neutral + alpha * (T_s_max - T_neutral)
        elif e_T < -0.5:
            T_s_star = T_s_min
        elif e_T < -0.1:
            alpha = (-e_T - 0.1) / 0.4
            T_s_star = T_neutral - alpha * (T_neutral - T_s_min)
        else:
            T_s_star = T_neutral

        if e_W < -0.001:
            W_s_star = W_s_min
        elif e_W < -0.0005:
            alpha = (-e_W - 0.0005) / 0.0005
            W_s_star = W_neutral - alpha * (W_neutral - W_s_min)
        else:
            W_s_star = W_neutral

        if not hasattr(self, 'prev_C_in'):
            self.prev_C_in = C_in
        dC_in = C_in - self.prev_C_in
        self.prev_C_in = C_in

        if dC_in > 0.5:
            if C_in < 600.0:
                C_s_star = max(self.C_s_min, C_in - 50.0)
            else:
                alpha = min(1.0, max(0.0, (C_in - 600.0) / 350.0))
                C_s_star = 800.0 - alpha * 380.0
        else:
            C_s_star = self.C_max

        return T_s_star, W_s_star, C_s_star

    def _solve_ideal_ask(self, T_out, T_s0, W_s0, C_s0, u_star, dt, logger, T_neutral, W_neutral, C_neutral):
        """
        Phase 2 of the Sequential (Alternating) Linearization scheme
        (doc "4. Controllability Maximization - The Ideal Ask").

        With the VAV flow frozen at u_star (the just-solved Phase-1
        optimum), the bilinear u*T_s term becomes linear in the AHU
        supply request Z = [T_s, W_s, C_s], so this solves a small
        secondary QP for the mathematically optimal ask -- replacing the
        proportional/bang-bang heuristic.

        Design choices made where the derivation doc under-specifies:
        - u_star is taken as u_cmd (the final, smoothed & clipped flow
          actually sent to the VAV box this step), not the raw QP output,
          so the ask is linearized about what is actually happening.
        - The ask Z is solved as ONE constant triple (not a per-step
          trajectory) held over the same N-step horizon as Phase 1, so the
          AHU coordinator receives a request that keeps the zone
          comfortable over the prediction horizon, not just next instant.
        - C_s_max / C_neutral (undefined in the doc) are taken from
          self.C_s_max / self.C_neutral -- see the note at their
          definition in __init__.
        """
        N = self.N
        x0 = self.x[0:4].copy()
        T_in, T_m, W_in, C_in = x0
        d_T, d_W = self.x[4], self.x[5]
        N_occ, alpha_ext, alpha_int, beta_air, beta_mass, d_C = self.x[6:12]
        rho, c_p = self.rho_air, self.c_p

        # --- Linearize the physics about (x0, u_star, v_s0) ---
        f_ask = np.zeros(4)
        f_ask[0] = beta_air * (alpha_ext*(T_out - T_in) + alpha_int*(T_m - T_in)
                                + N_occ*self.q_person + rho*c_p*u_star*(T_s0 - T_in) + d_T)
        f_ask[1] = beta_mass * (alpha_int*(T_in - T_m))
        f_ask[2] = beta_air*c_p*(N_occ*self.g_w_person + rho*u_star*(W_s0 - W_in) + d_W)
        f_ask[3] = beta_air*rho*c_p*(N_occ*self.g_co2_person + u_star*(C_s0 - C_in) + d_C)

        Ac_ask = np.zeros((4, 4))
        Ac_ask[0, 0] = beta_air * (-alpha_ext - alpha_int - rho*c_p*u_star)
        Ac_ask[0, 1] = beta_air * alpha_int
        Ac_ask[1, 0] = beta_mass * alpha_int
        Ac_ask[1, 1] = -beta_mass * alpha_int
        Ac_ask[2, 2] = -beta_air*c_p*rho*u_star
        Ac_ask[3, 3] = -beta_air*rho*c_p*u_star

        B_ask = np.zeros((4, 3))
        B_ask[0, 0] = beta_air * rho * c_p * u_star   # d(T_in_dot)/d(T_s)
        B_ask[2, 1] = beta_air * c_p * rho * u_star    # d(W_in_dot)/d(W_s)
        B_ask[3, 2] = beta_air * rho * c_p * u_star    # d(C_in_dot)/d(C_s)

        v_s0 = np.array([T_s0, W_s0, C_s0])
        cc_ask = f_ask - Ac_ask @ x0 - B_ask @ v_s0

        Ad_ask = np.eye(4) + Ac_ask * dt
        Bd_ask = B_ask * dt
        cd_ask = cc_ask * dt

        # --- Horizon prediction with Z held constant across N steps ---
        A_pows = [np.eye(4)]
        for i in range(1, N + 1):
            A_pows.append(A_pows[-1] @ Ad_ask)

        Psi_ask = np.zeros((4*N, 4))
        Phi_ask = np.zeros((4*N, 4))
        sum_A = np.zeros((4, 4))
        for i in range(N):
            Psi_ask[i*4:(i+1)*4, :] = A_pows[i+1]
            sum_A = sum_A + A_pows[i]
            Phi_ask[i*4:(i+1)*4, :] = sum_A

        # Since Z is constant (not a per-step trajectory), the effective
        # input map collapses to Phi_ask @ Bd_ask -- the same simplification
        # that makes Rule 4's persistent T_s_opt tractable in the coordinator.
        Theta_ask = Phi_ask @ Bd_ask               # (4N, 3)
        g_ask = Psi_ask @ x0 + Phi_ask @ cd_ask    # (4N,)

        FT = self.ST @ Theta_ask; gT = self.ST @ g_ask
        FW = self.SW @ Theta_ask; gW = self.SW @ g_ask
        FC = self.SC @ Theta_ask; gC = self.SC @ g_ask

        # --- QP assembly: z = [T_s, W_s, C_s, eps_T(N), eps_W(N), eps_C(N)] ---
        n_vars = 3 + 3*N

        H = np.zeros((n_vars, n_vars))
        H[0:3, 0:3] = 2.0 * np.diag([self.q_T_ask, self.q_W_ask, self.q_C_ask])
        H[3:3+N, 3:3+N] = 2.0 * np.eye(N) * self.lambda_T
        H[3+N:3+2*N, 3+N:3+2*N] = 2.0 * np.eye(N) * self.lambda_W
        H[3+2*N:3+3*N, 3+2*N:3+3*N] = 2.0 * np.eye(N) * self.lambda_C
        H += np.eye(n_vars) * 1e-6
        H_sparse = sparse.csc_matrix(H)

        f = np.zeros(n_vars)
        f[0] = -2.0 * self.q_T_ask * T_neutral
        f[1] = -2.0 * self.q_W_ask * W_neutral
        f[2] = -2.0 * self.q_C_ask * C_neutral

        I_N, O_N = self.I_N, self.O_N
        O_N3 = np.zeros((N, 3))
        I_3 = np.eye(3)
        O_3N = np.zeros((3, N))

        A_con = np.block([
            [FT,   -I_N,  O_N,  O_N],   # T upper (soft)
            [-FT,  -I_N,  O_N,  O_N],   # T lower (soft)
            [FW,    O_N, -I_N,  O_N],   # W upper (soft)
            [-FW,   O_N, -I_N,  O_N],   # W lower (soft)
            [FC,    O_N,  O_N, -I_N],   # C ceiling only (soft)
            [O_N3,  I_N,  O_N,  O_N],   # eps_T >= 0
            [O_N3,  O_N,  I_N,  O_N],   # eps_W >= 0
            [O_N3,  O_N,  O_N,  I_N],   # eps_C >= 0
            [I_3,  O_3N, O_3N, O_3N],   # AHU physical box bounds on Z
        ])

        n_con = 8*N + 3
        l_con = np.zeros(n_con)
        u_con = np.zeros(n_con)

        l_con[0:N] = -np.inf
        u_con[0:N] = self.T_max*np.ones(N) - gT

        l_con[N:2*N] = -np.inf
        u_con[N:2*N] = -self.T_min*np.ones(N) + gT

        l_con[2*N:3*N] = -np.inf
        u_con[2*N:3*N] = self.W_max*np.ones(N) - gW

        l_con[3*N:4*N] = -np.inf
        u_con[3*N:4*N] = -self.W_min*np.ones(N) + gW

        l_con[4*N:5*N] = -np.inf
        u_con[4*N:5*N] = self.C_max*np.ones(N) - gC

        l_con[5*N:8*N] = 0.0
        u_con[5*N:8*N] = np.inf

        l_con[8*N:8*N+3] = [self.T_s_min, self.W_s_min, self.C_s_min]
        u_con[8*N:8*N+3] = [self.T_s_max, self.W_s_max, self.C_s_max]

        A_sparse = sparse.csc_matrix(A_con)

        solver = osqp.OSQP()
        solver.setup(
            P=H_sparse, q=f, A=A_sparse, l=l_con, u=u_con,
            verbose=False, max_iter=self.max_iter,
            eps_abs=self.eps_abs, eps_rel=self.eps_rel,
            polish=True, adaptive_rho=True,
        )
        res = solver.solve()
        status = res.info.status_val

        if status in (1, 2):  # SOLVED or SOLVED_INACCURATE
            T_s_star = float(np.clip(res.x[0], self.T_s_min, self.T_s_max))
            W_s_star = float(np.clip(res.x[1], self.W_s_min, self.W_s_max))
            C_s_star = float(np.clip(res.x[2], self.C_s_min, self.C_s_max))
        else:
            T_s_star, W_s_star, C_s_star = self._fallback_ideal_ask(T_in, W_in, C_in, T_neutral, W_neutral)
            print(f"[{self.zone_name}] Ideal-Ask QP failed (status={status}), using fallback ask")

        logger.add(f"{self.zone_name}_AskQP_Status", status)
        return T_s_star, W_s_star, C_s_star

    def step(self, dt, state_data, logger):
        
        # Retrieve CO2 values
        C_out = state_data.get('C_out', 420.0)
        C_in = self.x[3] 
        C_s = max(self.C_s_min, state_data.get('C_s', 420.0))

        # Estimate Gamma 
        if abs(C_in - C_out) > 10.0: 
            gamma = (C_in - C_s) / (C_in - C_out)
            gamma = np.clip(gamma, 0.0, 1.0)  
        else:
            gamma = 0.1 

        # Calculate Mixed Air states
        T_out = state_data.get('T_out', 22.0)
        W_out = state_data.get('W_out', 0.008)
        T_in = self.x[0]
        W_in = self.x[2]

        T_mix = gamma * T_out + (1.0 - gamma) * T_in
        W_mix = gamma * W_out + (1.0 - gamma) * W_in

        # Set the Dynamic Neutral Targets for Solver 2
        T_neutral_dynamic = np.clip(T_mix, self.T_s_min, self.T_s_max)
        W_neutral_dynamic = np.clip(W_mix, self.W_s_min, self.W_s_max)
        C_neutral_dynamic = C_in  

        start_time = time.perf_counter()
        
        # Track elapsed simulation time
        self.sim_time_hours = getattr(self, 'sim_time_hours', 0.0) + (dt / 3600.0)

        
        tuneup_time_a1 = 0.0
        tuneup_time_a2 = 0.0
        tuneup_phase = self.sim_time_hours <= 0.0
        
        # # Alpha_int tuning
        # if self.sim_time_hours >= tuneup_time_a1:
        #     self.Q[8, 8] = 1e-6
        #     self.Q[9, 9] = 1e-12
        #     self.Q[10, 10] = 1e-15

        # if self.sim_time_hours >= tuneup_time_a2:
        #     self.Q[7, 7] = 1e-6


        
        T_out = state_data.get('T_out', 22.0)
        T_s = max(self.T_s_min, state_data.get('T_s', 13.0))
        W_s = max(self.W_s_min, state_data.get('W_s', 0.008))
        C_s = max(self.C_s_min, state_data.get('C_s', 420.0))

        # Dynamically update MPC references
        self.T_ref = state_data.get('temp_setpoint', self.T_ref)
        self.T_max = self.T_ref + self.T_delta
        self.T_min = self.T_ref - self.T_delta

        u_mass = state_data.get('VAV_Flow', 0.0)
        u = u_mass / self.rho_air

        z = np.array([
            state_data.get('T_in', self.x[0]),
            state_data.get('W_in', self.x[2]),
            state_data.get('C_in', self.x[3])
        ])

        # --- EKF Predict Phase ---
        n_steps = max(1, int(dt / 1.0))
        dt_sub = dt / n_steps
        try:
            x_pred = self.x.copy()
            P_pred = self.P.copy()
            
            for _ in range(n_steps):
                x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12 = x_pred

                # --- NEW: Mean-Reverting Time Constant ---
                # We must convert the disturbance models from a Random Walk to an Ornstein-Uhlenbeck (Mean-Reverting) Process. By adding a tiny "leakage" or decay factor, the disturbances will naturally bleed back to zero over time when there is no active data to sustain them.
                # tau is the relaxation time in seconds (e.g., 2 hours = 7200s)
                tau = 7200.0  # <-- FIXED: 180.0 was way too aggressive (3 minutes)

                f_x = np.zeros(12)
                f_x[0] = x10 * (x8*(T_out - x1) + x9*(x2 - x1) + x7 * self.q_person + self.rho_air * self.c_p * u * (T_s - x1) + x5)
                f_x[1] = x11 * (x9*(x1 - x2))
                f_x[2] = x10 * self.c_p * (x7 * self.g_w_person + self.rho_air * u * (W_s - x3) + x6)
                f_x[3] = x10 * self.rho_air * self.c_p * (x7 * self.g_co2_person + u * (C_s - x4) + x12)
                
                # Apply leakage to disturbances so they decay to 0 when unobserved
                f_x[4] = -(1.0 / tau) * x5
                f_x[5] = -(1.0 / tau) * x6
                f_x[6] = -(1.0 / tau) * x7
                f_x[7] = 0.0  # alpha_ext
                f_x[8] = 0.0  # alpha_int
                f_x[9] = 0.0  # beta_air
                f_x[10] = 0.0  # beta_mass
                f_x[11] = -(1.0 / tau) * x12  # d_C mean-reversion
                
                # Jacobian matrix
                F = np.zeros((12, 12))
                F[0, 0] = x10 * (-x8 - x9 - self.rho_air * self.c_p * u)
                F[0, 1] = x10 * x9
                F[0, 4] = x10
                F[0, 6] = x10 * self.q_person
                F[0, 7] = x10 * (T_out - x1)
                F[0, 8] = x10 * (x2 - x1)
                F[0, 9] = x8 * (T_out - x1) + x9 * (x2 - x1) + x7 * self.q_person + self.rho_air * self.c_p * u * (T_s - x1) + x5
                F[1, 0] = x11 * x9
                F[1, 1] = -x11 * x9
                F[1, 8] = x11 * (x1 - x2)
                F[1, 10] = x9 * (x1 - x2)
                F[2, 2] = -x10 * self.c_p * self.rho_air * u
                F[2, 5] = x10 * self.c_p
                F[2, 6] = x10 * self.c_p * self.g_w_person
                F[2, 9] = self.c_p * (x7 * self.g_w_person + self.rho_air * u * (W_s - x3) + x6)
                F[3, 3] = -x10 * self.rho_air * self.c_p * u
                F[3, 6] = x10 * self.rho_air * self.c_p * self.g_co2_person
                F[3, 9] = self.rho_air * self.c_p * (x7 * self.g_co2_person + u * (C_s - x4) + x12)
                F[3, 11] = x10 * self.rho_air * self.c_p  # ∂ẋ₄/∂d_C
                
                # Update the Jacobian to reflect the decay
                F[4, 4] = -1.0 / tau
                F[5, 5] = -1.0 / tau
                F[6, 6] = -1.0 / tau
                F[11, 11] = -1.0 / tau  # d_C mean-reversion
                
                Phi = np.eye(12) + F * dt_sub
                x_pred = x_pred + f_x * dt_sub
                # P_pred = Phi @ P_pred @ Phi.T + self.Q * (dt_sub / dt)
                P_pred = Phi @ P_pred @ Phi.T + self.Q * dt_sub
                P_pred = (P_pred + P_pred.T) / 2.0
            
            # --- EKF Update ---
            y_k = z - self.H @ x_pred
            S_k = self.H @ P_pred @ self.H.T + self.R
            try:
                S_inv = np.linalg.inv(S_k)
            except np.linalg.LinAlgError:
                S_inv = np.linalg.pinv(S_k + np.eye(3) * 1e-6)
            K_k = P_pred @ self.H.T @ S_inv
            
            self.x = x_pred + K_k @ y_k
            I_KH = np.eye(12) - K_k @ self.H
            self.P = I_KH @ P_pred @ I_KH.T + K_k @ self.R @ K_k.T
            self.P = (self.P + self.P.T) / 2.0

            # Calculate Normalized Innovation Squared (NIS)
            self.NIS = float(y_k.T @ S_inv @ y_k)

            # Prevent EKF divergence on unmeasured states by clipping to physical bounds
            self.x[1] = np.clip(self.x[1], 10.0, 40.0)      # T_m: wall temp can't be lava
            self.x[4] = np.clip(self.x[4], -5000.0, 5000.0) # d_T: unmodeled sensible heat bounds
            self.x[5] = np.clip(self.x[5], -0.01, 0.01)     # d_W: unmodeled latent heat bounds
            
            self.x[6] = max(0.0, self.x[6])
            self.x[7] = np.clip(self.x[7], 1.0, 5000.0)
            self.x[8] = np.clip(self.x[8], 1.0, 5000.0)
            self.x[9] = np.clip(self.x[9], 1e-7, 1e-6   )
            self.x[10] = np.clip(self.x[10], 1e-9, 1e-5)
            self.x[11] = np.clip(self.x[11], -500.0, 500.0) # d_C: unmodeled CO2 source bounds
    
            # --- MPC Formulation ---
            # 1. Linearization around x_0 (from updated EKF state) and u_{-1}
            x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12 = self.x
            T_in, T_m, W_in, C_in = x1, x2, x3, x4
            u0 = self.u_prev
            
            f_x = np.zeros(4)
            f_x[0] = x10 * (x8*(T_out - T_in) + x9*(T_m - T_in) + x7 * self.q_person + self.rho_air * self.c_p * u0 * (T_s - T_in) + x5)
            f_x[1] = x11 * (x9*(T_in - T_m))
            f_x[2] = x10 * self.c_p * (x7 * self.g_w_person + self.rho_air * u0 * (W_s - W_in) + x6)
            f_x[3] = x10 * self.rho_air * self.c_p * (x7 * self.g_co2_person + u0 * (C_s - C_in) + x12)
            
            Ac = np.zeros((4, 4))
            Ac[0, 0] = x10 * (-x8 - x9 - self.rho_air * self.c_p * u0)
            Ac[0, 1] = x10 * x9
            Ac[1, 0] = x11 * x9
            Ac[1, 1] = -x11 * x9
            Ac[2, 2] = -x10 * self.c_p * self.rho_air * u0
            Ac[3, 3] = -x10 * self.rho_air * self.c_p * u0
            
            Bc = np.zeros((4, 1))
            Bc[0, 0] = x10 * self.rho_air * self.c_p * (T_s - T_in)
            Bc[1, 0] = 0.0
            Bc[2, 0] = x10 * self.c_p * self.rho_air * (W_s - W_in)
            Bc[3, 0] = x10 * self.rho_air * self.c_p * (C_s - C_in)
            
            x_0_mpc = np.array([T_in, T_m, W_in, C_in])
            cc = f_x - Ac @ x_0_mpc - Bc.flatten() * u0
            
            Ad = np.eye(4) + Ac * dt
            Bd = Bc * dt
            cd = cc * dt
            
            # 2. Prediction Matrices
            N = self.N
            Psi = np.zeros((4*N, 4))
            Theta = np.zeros((4*N, N))
            Phi_pred = np.zeros((4*N, 4))
            
            A_pows = [np.eye(4)]
            for i in range(1, N + 1):
                A_pows.append(A_pows[-1] @ Ad)
                
            sum_A = np.zeros((4, 4))
            for i in range(N):
                Psi[i*4:(i+1)*4, :] = A_pows[i+1]
                sum_A = sum_A + A_pows[i]
                Phi_pred[i*4:(i+1)*4, :] = sum_A
                for j in range(i + 1):
                    Theta[i*4:(i+1)*4, j:j+1] = A_pows[i - j] @ Bd
                    
            FT = self.ST @ Theta
            gT = self.ST @ (Psi @ x_0_mpc + Phi_pred @ cd)
            
            FW = self.SW @ Theta
            gW = self.SW @ (Psi @ x_0_mpc + Phi_pred @ cd)
            
            FC = self.SC @ Theta
            gC = self.SC @ (Psi @ x_0_mpc + Phi_pred @ cd)
            
            # 3. Assemble QP using OSQP's native two-sided constraint format
            #    Decision variables: z = [u(N), eps_T(N), eps_W(N), eps_C(N)]
            #    Proper two-sided: l <= A_con @ z <= u_con
            
            # Build regularized Hessian (with centering quadratic in u-block)
            H_sparse = self._build_hessian(N, FT=FT, FW=FW)
            
            # Linear cost — rate penalty + quadratic centering gradient
            f_U = -2.0 * self.r_delta * self.D.T @ self.E * self.u_prev

            # Centering linear terms: d/du [ q * ||FT@u + gT - T_ref||^2 ]
            #   = 2*q * FT' @ (gT - T_ref_vec)   (the u-independent residual)
            T_ref_vec = np.ones(N) * self.T_ref
            W_ref_vec = np.ones(N) * (self.W_max + self.W_min) / 2.0
            f_U += 2.0 * self.q_T_center * FT.T @ (gT - T_ref_vec)
            f_U += 2.0 * self.q_W_center * FW.T @ (gW - W_ref_vec)

            f_eps_T = np.ones(N) * self.mu_T
            f = np.concatenate([f_U, f_eps_T, self.zeros_N, self.zeros_N])
            
            # --- Constraint assembly (two-sided format) ---
            
            A_con = np.block([
                # Temp soft constraints (upper, then lower)
                [FT, -self.I_N, self.O_N, self.O_N],
                [-FT, -self.I_N, self.O_N, self.O_N],
                # Humidity soft constraints (upper, then lower)
                [FW, self.O_N, -self.I_N, self.O_N],
                [-FW, self.O_N, -self.I_N, self.O_N],
                # CO2 soft constraint (upper only)
                [FC, self.O_N, self.O_N, -self.I_N],
                # Slack non-negativity: eps_T >= 0
                [self.O_N, self.I_N, self.O_N, self.O_N],
                # Slack non-negativity: eps_W >= 0
                [self.O_N, self.O_N, self.I_N, self.O_N],
                # Slack non-negativity: eps_C >= 0
                [self.O_N, self.O_N, self.O_N, self.I_N],
                # Input bounds
                [self.I_N, self.O_N, self.O_N, self.O_N],
                # NEW: rate constraint on u
                [self.D, self.O_N, self.O_N, self.O_N],   
            ])

            n_con = 10 * N
            l_con = np.zeros(n_con)
            u_con = np.zeros(n_con)

            # Block 1: FT@u - eps_T <= T_max - gT
            l_con[0:N] = -np.inf
            u_con[0:N] = np.ones(N) * self.T_max - gT

            # Block 2: -FT@u - eps_T <= -T_min + gT
            l_con[N:2*N] = -np.inf
            u_con[N:2*N] = -np.ones(N) * self.T_min + gT

            # Block 3: FW@u - eps_W <= W_max - gW
            l_con[2*N:3*N] = -np.inf
            u_con[2*N:3*N] = np.ones(N) * self.W_max - gW

            # Block 4: -FW@u - eps_W <= -W_min + gW
            l_con[3*N:4*N] = -np.inf
            u_con[3*N:4*N] = -np.ones(N) * self.W_min + gW

            # Block 5: FC@u - eps_C <= C_max - gC
            l_con[4*N:5*N] = -np.inf
            u_con[4*N:5*N] = np.ones(N) * self.C_max - gC

            # Block 6-8: 0 <= eps <= inf
            l_con[5*N:8*N] = 0.0
            u_con[5*N:8*N] = np.inf

            # Block 9: u_min <= u <= u_max
            l_con[8*N:9*N] = np.ones(N) * self.u_min
            u_con[8*N:9*N] = np.ones(N) * self.u_max

            l_con[9*N:10*N] = -self.du_max * np.ones(N) + self.E * self.u_prev
            u_con[9*N:10*N] =  self.du_max * np.ones(N) + self.E * self.u_prev

            A_sparse = sparse.csc_matrix(A_con)
            
            if tuneup_phase:
                self.tuneup_timer = getattr(self, 'tuneup_timer', 0.0) + dt
                if self.tuneup_timer > 3600.0 * 2:  # Flip excitation every 2 hours
                    self.tuneup_flip = not getattr(self, 'tuneup_flip', False)
                    self.tuneup_timer = 0.0
                
                self.tuneup_flip = getattr(self, 'tuneup_flip', False)
                
                # "maximum and then half minimum"
                u_cmd_raw = self.u_max if self.tuneup_flip else max(self.u_min, self.u_max * 0.5)
                self.T_s_star_tune = self.T_s_min if self.tuneup_flip else self.T_s_max
                self.W_s_star_tune = self.W_s_min if self.tuneup_flip else self.W_s_max
                self.C_s_star_tune = 420.0 if self.tuneup_flip else 800.0
                
                mpc_status = -1
                print(f"[{self.zone_name}] Tune-up phase: bypassing MPC, applying excitation U={u_cmd_raw}")
            else:
                solver = osqp.OSQP()
                solver.setup(
                    P=H_sparse, q=f, A=A_sparse, l=l_con, u=u_con,
                    verbose=False,
                    max_iter=self.max_iter,
                    eps_abs=self.eps_abs,
                    eps_rel=self.eps_rel,
                    polish=True,
                    adaptive_rho=True,
                )
                res = solver.solve()
                mpc_status = res.info.status_val
                print(f"[{self.zone_name}] OSQP solved, status={mpc_status}")
                
                if mpc_status in [1, 2]:  # 1: SOLVED, 2: SOLVED_INACCURATE
                    u_cmd_raw = np.clip(res.x[0], self.u_min, self.u_max)
                else:
                    # Proportional fallback instead of blindly using u_prev
                    u_cmd_raw = self._fallback_control(state_data)
                    print(f"[{self.zone_name}] MPC failed (status={mpc_status}), fallback u={u_cmd_raw:.3f}")
            
            # EMA output smoothing: absorbs high-frequency chatter
            u_cmd = self.u_smooth_alpha * u_cmd_raw + (1.0 - self.u_smooth_alpha) * self.u_ema
            u_cmd = np.clip(u_cmd, self.u_min, self.u_max)
            self.u_ema = u_cmd
            self.u_prev = u_cmd
            
            u_mass_cmd = u_cmd * self.rho_air
            
            # --- Logging ---
            exec_time_ms = (time.perf_counter() - start_time) * 1000.0
            logger.add(f"{self.zone_name}_MPC_Time_ms", exec_time_ms)
            logger.add(f"{self.zone_name}_MPC_Status", mpc_status)
            
            
            state_names = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass", "d_C"]
            for i, name in enumerate(state_names):
                logger.add(f"{self.zone_name}_EKF_x_{name}", self.x[i])
                logger.add(f"{self.zone_name}_EKF_P_{name}", self.P[i, i])
                
            # Log references
            logger.add(f"{self.zone_name}_T_ref_C", self.T_ref)
            logger.add(f"{self.zone_name}_T_max_C", self.T_max)
            logger.add(f"{self.zone_name}_T_min_C", self.T_min)
                
            # 2. Log EKF Health Diagnostics
            # Innovation/Residuals (Expected to be zero-mean white noise)
            logger.add(f"{self.zone_name}_EKF_y_T_in", y_k[0])
            logger.add(f"{self.zone_name}_EKF_y_W_in", y_k[1])
            logger.add(f"{self.zone_name}_EKF_y_C_in", y_k[2])
            
            # NIS (For 3 measurements, 95% of samples should fall between 0.216 and 7.815)
            logger.add(f"{self.zone_name}_EKF_NIS", self.NIS)
            
            # Trace of P (Expected to drop initially and then stabilize)
            logger.add(f"{self.zone_name}_EKF_P_trace", float(np.trace(self.P)))
            
            # 3. Log Critical Kalman Gains
            logger.add(f"{self.zone_name}_EKF_K_T_in", K_k[0, 0])
            logger.add(f"{self.zone_name}_EKF_K_W_in", K_k[2, 1])
            logger.add(f"{self.zone_name}_EKF_K_C_in", K_k[3, 2])
            logger.add(f"{self.zone_name}_EKF_K_N_occ_from_C_in", K_k[6, 2])
            
            # --- Ideal Ask Logic (Phase 2: Sequential Linearization) ---
            T_in, T_m, W_in, C_in = self.x[0], self.x[1], self.x[2], self.x[3]

            if tuneup_phase:
                T_s_star = getattr(self, 'T_s_star_tune', self.T_s_min)
                W_s_star = getattr(self, 'W_s_star_tune', self.W_s_min)
                C_s_star = getattr(self, 'C_s_star_tune', 420.0)
            else:
                # u_cmd is the final, smoothed & clipped Phase-1 flow that is
                # actually being sent to the VAV box this step -- freezing
                # the ask's linearization on this (rather than the raw QP
                # output) keeps the ask self-consistent with reality.
                T_s_star, W_s_star, C_s_star = self._solve_ideal_ask(
                    T_out, T_s, W_s, C_s, u_cmd, dt, logger,
                    T_neutral_dynamic, W_neutral_dynamic, C_neutral_dynamic)

            saturation_index = u_cmd / self.u_max

            logger.add(f"{self.zone_name}_ideal_temp", T_s_star)
            logger.add(f"{self.zone_name}_ideal_hum", W_s_star)
            logger.add(f"{self.zone_name}_ideal_co2", C_s_star)
            logger.add(f"{self.zone_name}_u_cmd", u_mass_cmd)
            logger.add(f"{self.zone_name}_saturation_index", saturation_index)
            
            return {
                'ideal_temp': T_s_star,
                'ideal_hum': W_s_star,
                'ideal_co2': C_s_star,
                'u_cmd': u_mass_cmd,
                'saturation_index': saturation_index
            }
        except Exception as e:
            import traceback
            print(f'Exception in ZoneController.step for {self.zone_name}: {e}')
            traceback.print_exc()
            raise e