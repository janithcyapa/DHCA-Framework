"""
MPC Controller — Zone-Level Setpoint Optimiser
================================================
Receives EKF state estimates and computes optimal
VAV flow rates and reheat temperatures per zone.

Implements the Sparse QP formulation from docs/3.MPC_Design.html:
  1. Extract states & disturbances from EKF augmented vector
  2. Successive linearization  → Ac, Bc, cc
  3. Forward-Euler discretization → Ad, Bd, cd
  4. Sparse QP via OSQP         → optimal V_dot_s per zone

State vector (4):  [T_in, T_m, C_in, W_in]
Control input (1): [V_dot_s]  (supply volumetric flow, m³/s)
Disturbances  (2): [d_T, d_W] from EKF augmented states
"""
import logging
import numpy as np

try:
    import scipy.sparse as sp
    import scipy.linalg as sla
    import osqp
    _HAS_OSQP = True
except ImportError:
    _HAS_OSQP = False
except ImportError:
    _HAS_OSQP = False

# ── Logger ───────────────────────────────────────────────────────────────
log = logging.getLogger("MPC")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s/%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    log.addHandler(_h)
log.setLevel(logging.DEBUG)

# ── Physical constants (must match EKF / zone model) ─────────────────────
RHO_AIR   = 1.204       # kg/m³
CP_AIR    = 1006.0       # J/(kg·K)
Q_PERSON  = 100.0        # W per occupant (sensible)
G_W_OCC   = 5e-5         # kg_w/s per occupant
G_CO2_OCC = 3.82e-6      # m³_co2/s per occupant (volumetric)


class MPCController:
    """Model Predictive Controller for multi-zone HVAC.

    Solves one independent QP per zone at each control interval.
    """

    # ── Tuning knobs ─────────────────────────────────────────────────────
    N_HORIZON   = 10          # prediction horizon steps
    DT_CTRL     = 900.0       # control sampling time (s) — 15 min
    T_REF       = 20.0       # temperature setpoint (°C)
    Q_TEMP      = 100.0       # penalty on |T_in − T_ref|²
    Q_TM        = 0.0         # penalty on T_m (not tracked)
    Q_CO2       = 0.0         # CO₂ handled via soft constraint
    Q_HUM       = 0.0         # humidity handled via soft constraint
    R_INPUT     = 0.01        # penalty on V_dot_s (fan energy)
    RHO_CO2     = 1e6         # slack penalty for CO₂ > 1000 ppm
    RHO_W       = 1e6         # slack penalty for humidity > W_max
    CO2_MAX     = 1000.0      # ppm  ASHRAE limit
    W_MAX       = 0.012       # kg/kg max humidity ratio
    V_DOT_MIN   = 0.0         # m³/s  actuator lower bound
    V_DOT_MAX   = 2.5         # m³/s  actuator upper bound

    # Supply air conditions (AHU delivers these)
    T_SUPPLY    = 14.0        # °C   post-heating-coil temp
    W_SUPPLY    = 0.008       # kg/kg
    C_SUPPLY    = 400.0       # ppm

    def __init__(self, zones, zone_params=None):
        self.zones = zones
        self.zone_params = zone_params or {}
        self._prev_u = {z: 0.5 for z in zones}   # previous control action
        self._call_count = 0
        
        self.T_SUPPLY = self.__class__.T_SUPPLY
        self.W_SUPPLY = self.__class__.W_SUPPLY
        self.C_SUPPLY = self.__class__.C_SUPPLY
        
        log.info("MPC initialised  |  zones=%s  horizon=%d  dt=%.0fs  "
                 "OSQP=%s", zones, self.N_HORIZON, self.DT_CTRL, _HAS_OSQP)

    # =====================================================================
    #  PUBLIC API
    # =====================================================================
    def compute_optimal_control(self, estimations, time_info, ahu_conditions=None):
        """Compute optimal setpoints given current EKF estimates.

        Parameters
        ----------
        estimations : dict[str, dict] – per-zone EKF state estimates
        time_info   : float           – elapsed simulation hours
        ahu_conditions : dict         - optional dynamic supply conditions

        Returns
        -------
        flow_targets   : dict[str, float] – VAV mass flow (kg/s) per zone
        reheat_targets : dict[str, float] – reheat temp setpoint (°C)
        """
        if ahu_conditions:
            self.T_SUPPLY = ahu_conditions.get('T_SUPPLY', self.T_SUPPLY)
            self.W_SUPPLY = ahu_conditions.get('W_SUPPLY', self.W_SUPPLY)
            self.C_SUPPLY = ahu_conditions.get('C_SUPPLY', self.C_SUPPLY)

        self._call_count += 1
        flow_targets = {}
        reheat_targets = {}

        for z in self.zones:
            est = estimations.get(z)
            if est is None:
                log.debug("[%s] t=%.2fh  No EKF data yet → default flow", z, time_info)
                flow_targets[z] = 0.15
                reheat_targets[z] = self.T_SUPPLY
                continue

            p = self.zone_params.get(z, {})
            u_opt = self._solve_zone_qp(z, est, p, time_info)

            # Convert volumetric flow (m³/s) → mass flow (kg/s)
            m_dot = RHO_AIR * u_opt
            flow_targets[z] = m_dot
            reheat_targets[z] = self.T_SUPPLY
            self._prev_u[z] = u_opt

        if self._call_count % 60 == 1:
            log.info("t=%.2fh  MPC targets: %s",
                     time_info,
                     {z: f"{v:.3f} kg/s" for z, v in flow_targets.items()})

        return flow_targets, reheat_targets

    # =====================================================================
    #  STEP 1 — Extract state & disturbance from EKF
    # =====================================================================
    @staticmethod
    def _extract_state(est):
        """Return (x_op[4], d_op[2]) from the EKF estimation dict.

        x = [T_in, T_m, C_in, W_in]
        d = [d_T,  d_W]

        The EKF augmented state is [T_in, T_m, W_in, C_in, dT, dW, N_occ]
        but get_state() returns named keys.
        """
        T_in = est.get("T_in_est", 23.0)
        T_m  = est.get("T_m_est",  23.0)
        W_in = est.get("W_in_est", 0.008)
        C_in = est.get("C_in_est", 400.0)

        # Disturbances come from EKF augmented states idx 4,5
        d_T = est.get("d_T_est", 0.0)
        d_W = est.get("d_W_est", 0.0)

        x_op = np.array([T_in, T_m, C_in, W_in])
        d_op = np.array([d_T, d_W])
        return x_op, d_op

    # =====================================================================
    #  STEP 2 — Successive Linearization  (Ac, Bc, cc)
    # =====================================================================
    def _linearize(self, z, x_op, u_op, d_op, p):
        """Compute continuous Jacobians Ac, Bc and affine drift cc.

        From docs/3.MPC_Design.html §2 Successive Linearization.
        """
        nx = 4  # [T_in, T_m, C_in, W_in]
        nu = 1  # [V_dot_s]

        T_in_op, T_m_op, C_in_op, W_in_op = x_op
        d_T, d_W = d_op

        # Unpack zone thermal params
        R_ext  = p.get("R_env_ext", float('inf'))
        R_int  = p.get("R_int",     0.001)
        C_air  = p.get("C_air",     100_000.0)
        C_mass = p.get("C_mass",    1_000_000.0)
        M_air  = p.get("M_air",     100.0)
        V_room = p.get("V_room",    100.0)

        inv_R_ext = 1.0 / R_ext if R_ext < float('inf') else 0.0
        inv_R_int = 1.0 / R_int if R_int > 0 else 0.0

        # Sum of 1/R for adjacent zone couplings
        inv_R_adj_sum = 0.0
        for adj in p.get("adj_zones", []):
            r = adj.get("R_env", 0)
            if r > 0:
                inv_R_adj_sum += 1.0 / r

        T_s = self.T_SUPPLY
        W_s = self.W_SUPPLY
        C_s = self.C_SUPPLY

        # ── A_c  (4×4 state Jacobian) ────────────────────────────────────
        Ac = np.zeros((nx, nx))
        a00 = -(inv_R_ext + inv_R_adj_sum + inv_R_int
                + RHO_AIR * CP_AIR * u_op) / C_air
        Ac[0, 0] = a00
        Ac[0, 1] = inv_R_int / C_air
        Ac[1, 0] = inv_R_int / C_mass
        Ac[1, 1] = -inv_R_int / C_mass
        Ac[2, 2] = -u_op / V_room              # dĊ_in/dC_in
        Ac[3, 3] = -(RHO_AIR * u_op) / M_air   # dẆ_in/dW_in

        # ── B_c  (4×1 input Jacobian) ────────────────────────────────────
        Bc = np.zeros((nx, nu))
        Bc[0, 0] = RHO_AIR * CP_AIR * (T_s - T_in_op) / C_air
        Bc[2, 0] = (C_s - C_in_op) / V_room
        Bc[3, 0] = RHO_AIR * (W_s - W_in_op) / M_air

        # ── f(x_op, u_op, d_op)  — full nonlinear RHS ───────────────────
        f_op = self._dynamics_rhs(x_op, u_op, d_op, p)

        # ── c_c  (affine drift) ─────────────────────────────────────────
        cc = f_op - Ac @ x_op - Bc @ np.array([u_op])

        log.debug("[%s] Ac diag=[%.4e,%.4e,%.4e,%.4e]  "
                  "Bc=[%.4e,0,%.4e,%.4e]",
                  z, Ac[0,0], Ac[1,1], Ac[2,2], Ac[3,3],
                  Bc[0,0], Bc[2,0], Bc[3,0])

        return Ac, Bc, cc

    def _dynamics_rhs(self, x, u, d, p):
        """Evaluate f(x,u,d) — the continuous nonlinear ODE RHS."""
        T_in, T_m, C_in, W_in = x
        d_T, d_W = d

        R_ext  = p.get("R_env_ext", float('inf'))
        R_int  = p.get("R_int",     0.001)
        C_air  = p.get("C_air",     100_000.0)
        C_mass = p.get("C_mass",    1_000_000.0)
        M_air  = p.get("M_air",     100.0)
        V_room = p.get("V_room",    100.0)

        T_s = self.T_SUPPLY
        W_s = self.W_SUPPLY
        C_s = self.C_SUPPLY

        # Envelope heat exchange (outdoor) — use T_out ≈ T_in as
        # operating-point approximation since MPC cannot control it
        q_env = 0.0
        if R_ext < float('inf'):
            q_env = (T_in - T_in) / R_ext  # zero at op-point; captured by Ac

        # Adjacent coupling — use T_adj ≈ T_in at operating point
        q_adj = 0.0  # linearized around zero coupling at op-point

        # Thermal mass exchange
        q_mass = (T_m - T_in) / R_int if R_int > 0 else 0.0

        # Supply air
        q_s = RHO_AIR * u * CP_AIR * (T_s - T_in)

        # ── ODE RHS ──────────────────────────────────────────────────────
        f = np.zeros(4)
        f[0] = (q_env + q_adj + q_mass + q_s + d_T) / C_air
        f[1] = (T_in - T_m) / (C_mass * R_int) if R_int > 0 else 0.0
        f[2] = (u * (C_s - C_in)) / V_room             # CO₂ (ppm)
        f[3] = (RHO_AIR * u * (W_s - W_in) + d_W) / M_air
        return f

    # =====================================================================
    #  STEP 3 — ZOH Discretization (matrix exponential)
    # =====================================================================
    @staticmethod
    def _discretize(Ac, Bc, cc, Ts):
        """Zero-Order Hold discretization via matrix exponential.

        Builds the augmented matrix:
            M = [[Ac, Bc, I], [0, 0, 0], [0, 0, 0]] * Ts
        then  Ad = expm(M)[:nx,:nx],  Bd = expm(M)[:nx,nx:nx+nu],
              Fd = expm(M)[:nx,nx+nu:]  and  cd = Fd @ cc.

        Falls back to Forward Euler if scipy is unavailable.
        """
        nx = Ac.shape[0]
        nu = Bc.shape[1]

        try:
            # Build (nx+nu+nx) × (nx+nu+nx) augmented matrix
            na = nx + nu + nx
            M = np.zeros((na, na))
            M[:nx, :nx]          = Ac * Ts
            M[:nx, nx:nx+nu]     = Bc * Ts
            M[:nx, nx+nu:nx+nu+nx] = np.eye(nx) * Ts   # for affine term

            eM = sla.expm(M)
            Ad = eM[:nx, :nx]
            Bd = eM[:nx, nx:nx+nu]
            Fd = eM[:nx, nx+nu:nx+nu+nx]
            cd = Fd @ cc
        except Exception:
            # Fallback to Forward Euler
            Ad = np.eye(nx) + Ac * Ts
            Bd = Bc * Ts
            cd = cc * Ts

        return Ad, Bd, cd

    # =====================================================================
    #  STEP 4 — Sparse QP  (OSQP)
    # =====================================================================
    def _solve_zone_qp(self, z, est, p, time_info):
        """Solve a single-zone MPC QP and return optimal V_dot_s."""
        x_op, d_op = self._extract_state(est)
        u_op = self._prev_u.get(z, 0.5)

        log.debug("[%s] t=%.2fh  x_op=[T=%.1f T_m=%.1f CO2=%.0f W=%.5f]  "
                  "u_prev=%.3f  d=[%.1f, %.2e]",
                  z, time_info, x_op[0], x_op[1], x_op[2], x_op[3],
                  u_op, d_op[0], d_op[1])

        Ac, Bc, cc = self._linearize(z, x_op, u_op, d_op, p)
        Ad, Bd, cd = self._discretize(Ac, Bc, cc, self.DT_CTRL)

        # Check discrete stability
        eigs = np.linalg.eigvals(Ad)
        max_eig = np.max(np.abs(eigs))
        if max_eig > 1.0 + 1e-4:
            log.warning("[%s] UNSTABLE Ad!  max|λ|=%.4f — clamping to "
                        "fallback", z, max_eig)
            return np.clip(u_op, self.V_DOT_MIN, self.V_DOT_MAX)

        if not _HAS_OSQP:
            log.debug("[%s] OSQP unavailable → analytical fallback", z)
            return self._fallback_control(z, x_op, d_op, p)

        return self._build_and_solve_qp(z, Ad, Bd, cd, x_op, time_info)

    # ── QP construction ──────────────────────────────────────────────────
    def _build_and_solve_qp(self, z, Ad, Bd, cd, x0, time_info):
        """Assemble and solve the sparse QP per §4 of the design doc."""
        N  = self.N_HORIZON
        nx = 4
        nu = 1

        # Decision variable layout:
        #   Z = [x_0..x_N | u_0..u_{N-1} | ε_c_1..ε_c_N | ε_w_1..ε_w_N]
        n_x_vars = (N + 1) * nx          # state variables
        n_u_vars = N * nu                 # input variables
        n_slack  = N                      # CO₂ slacks
        n_slack2 = N                      # humidity slacks
        n_z = n_x_vars + n_u_vars + n_slack + n_slack2

        # Offsets into Z
        off_x = 0
        off_u = n_x_vars
        off_ec = off_u + n_u_vars
        off_ew = off_ec + n_slack

        # ── Build P (Hessian) ────────────────────────────────────────────
        Q_diag = np.array([self.Q_TEMP, self.Q_TM, self.Q_CO2, self.Q_HUM])
        x_ref  = np.array([self.T_REF, 0.0, 0.0, 0.0])

        P_diag = np.zeros(n_z)
        for i in range(N + 1):
            P_diag[off_x + i*nx : off_x + i*nx + nx] = Q_diag
        for i in range(N):
            P_diag[off_u + i] = self.R_INPUT
        P_diag[off_ec : off_ec + N] = self.RHO_CO2
        P_diag[off_ew : off_ew + N] = self.RHO_W

        P = sp.diags(P_diag, format='csc')

        # ── Build q (gradient) ───────────────────────────────────────────
        q = np.zeros(n_z)
        q_ref = -Q_diag * x_ref
        for i in range(N + 1):
            q[off_x + i*nx : off_x + i*nx + nx] = q_ref

        # ── Build constraints G, l, u ────────────────────────────────────
        # Rows: (A) dynamics equality  N*nx
        #       (B) initial state      nx
        #       (C) actuator bounds    N
        #       (D) CO₂ soft constr    N
        #       (E) humidity soft      N
        #       (F) slack ≥ 0          2N
        n_dyn   = N * nx
        n_init  = nx
        n_act   = N
        n_co2   = N
        n_hum   = N
        n_spos  = 2 * N
        n_rows  = n_dyn + n_init + n_act + n_co2 + n_hum + n_spos

        rows, cols, vals = [], [], []

        def _add(r, c, v):
            rows.append(r); cols.append(c); vals.append(v)

        row_off = 0

        # (A) Dynamics: x_{i+1} − Ad·x_i − Bd·u_i = cd
        for i in range(N):
            for s in range(nx):
                r = row_off + i * nx + s
                # x_{i+1}
                _add(r, off_x + (i+1)*nx + s, 1.0)
                # −Ad·x_i
                for j in range(nx):
                    if Ad[s, j] != 0:
                        _add(r, off_x + i*nx + j, -Ad[s, j])
                # −Bd·u_i
                for j in range(nu):
                    if Bd[s, j] != 0:
                        _add(r, off_u + i*nu + j, -Bd[s, j])
        row_off += n_dyn

        # (B) Initial state: x_0 = x0
        for s in range(nx):
            _add(row_off + s, off_x + s, 1.0)
        row_off += n_init

        # (C) Actuator bounds: V_DOT_MIN ≤ u_i ≤ V_DOT_MAX
        for i in range(N):
            _add(row_off + i, off_u + i, 1.0)
        row_off += n_act

        # (D) CO₂ soft: C_in_{i+1} − ε_c_i ≤ CO2_MAX
        for i in range(N):
            _add(row_off + i, off_x + (i+1)*nx + 2, 1.0)   # C_in state
            _add(row_off + i, off_ec + i, -1.0)             # −ε_c
        row_off += n_co2

        # (E) Humidity soft: W_in_{i+1} − ε_w_i ≤ W_MAX
        for i in range(N):
            _add(row_off + i, off_x + (i+1)*nx + 3, 1.0)   # W_in state
            _add(row_off + i, off_ew + i, -1.0)             # −ε_w
        row_off += n_hum

        # (F) Slack ≥ 0
        for i in range(N):
            _add(row_off + i, off_ec + i, 1.0)
        row_off += N
        for i in range(N):
            _add(row_off + i, off_ew + i, 1.0)

        G = sp.csc_matrix((vals, (rows, cols)), shape=(n_rows, n_z))

        # ── Bounds l, u ──────────────────────────────────────────────────
        l_vec = np.zeros(n_rows)
        u_vec = np.zeros(n_rows)
        row_off = 0

        # (A) dynamics equality l = u = cd
        for i in range(N):
            l_vec[row_off + i*nx : row_off + i*nx + nx] = cd
            u_vec[row_off + i*nx : row_off + i*nx + nx] = cd
        row_off += n_dyn

        # (B) initial state
        l_vec[row_off : row_off + nx] = x0
        u_vec[row_off : row_off + nx] = x0
        row_off += n_init

        # (C) actuator
        l_vec[row_off : row_off + n_act] = self.V_DOT_MIN
        u_vec[row_off : row_off + n_act] = self.V_DOT_MAX
        row_off += n_act

        # (D) CO₂ soft
        l_vec[row_off : row_off + n_co2] = -1e10
        u_vec[row_off : row_off + n_co2] = self.CO2_MAX
        row_off += n_co2

        # (E) humidity soft
        l_vec[row_off : row_off + n_hum] = -1e10
        u_vec[row_off : row_off + n_hum] = self.W_MAX
        row_off += n_hum

        # (F) slack ≥ 0
        l_vec[row_off : row_off + 2*N] = 0.0
        u_vec[row_off : row_off + 2*N] = 1e10

        # ── Solve ────────────────────────────────────────────────────────
        solver = osqp.OSQP()
        solver.setup(P, q, G, l_vec, u_vec,
                     warm_start=True, verbose=False,
                     eps_abs=1e-4, eps_rel=1e-4,
                     max_iter=4000, polish=True)
        result = solver.solve()

        if result.info.status not in ('solved', 'solved inaccurate', 'solved_inaccurate'):
            log.warning("[%s] QP status=%s — using fallback",
                        z, result.info.status)
            return np.clip(self._prev_u.get(z, 0.5),
                           self.V_DOT_MIN, self.V_DOT_MAX)

        u_star = result.x[off_u]  # first control action
        u_star = np.clip(u_star, self.V_DOT_MIN, self.V_DOT_MAX)

        # Log predicted trajectory
        x_pred = result.x[off_x : off_x + (N+1)*nx].reshape(N+1, nx)
        log.debug("[%s] QP solved  u*=%.4f m³/s  "
                  "T_pred=[%.1f→%.1f]  CO2_pred=[%.0f→%.0f]  "
                  "iter=%d  status=%s",
                  z, u_star,
                  x_pred[0, 0], x_pred[-1, 0],
                  x_pred[0, 2], x_pred[-1, 2],
                  result.info.iter, result.info.status)

        return float(u_star)

    # ── Analytical fallback (no OSQP) ────────────────────────────────────
    def _fallback_control(self, z, x_op, d_op, p):
        """Simple proportional fallback when OSQP is unavailable.

        Uses a P-controller on temperature error plus a feed-forward
        term for CO₂ dilution.
        """
        T_in = x_op[0]
        C_in = x_op[2]

        C_air  = p.get("C_air", 100_000.0)
        V_room = p.get("V_room", 100.0)

        T_err = T_in - self.T_REF
        # Proportional: more flow when too warm (supply is cool)
        Kp_T = 0.05
        u_temp = Kp_T * max(T_err, 0.0)

        # CO₂ dilution feed-forward
        co2_excess = max(C_in - self.CO2_MAX, 0.0)
        Kp_co2 = 0.001
        u_co2 = Kp_co2 * co2_excess

        u = max(u_temp, u_co2, 0.05)  # minimum ventilation
        u = np.clip(u, self.V_DOT_MIN, self.V_DOT_MAX)

        log.debug("[%s] Fallback  T_err=%.2f  CO2=%.0f  u=%.4f m³/s",
                  z, T_err, C_in, u)
        return float(u)