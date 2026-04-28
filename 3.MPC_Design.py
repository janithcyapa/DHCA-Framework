import marimo

__generated_with = "0.23.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import urllib.request as req
    import plotly.io as pio
    import requests
    mo.Html(
        f"<style>{req.urlopen('https://raw.githubusercontent.com/janithcyapa/Engineering-Codex/refs/heads/main/shared_files/marimo/theme.css').read().decode()}</style>"
    )
    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    [🏠 Home](https://janithcyapa.github.io/DHCA-Framework/)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Model Pridictive Control for the Thermal Zone
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## System Dynamic
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.1 System Dynamics From Previous calculations

    To remove all the parts that are difficult to measure and to estimate define all of them as and The lumped disturbance vector ($d_i$):

    $$ d_{T,i} = Q_{solar,i} + Q_{\text{inf},i} + Q_{equip,i} + \sum \dot{m}_{ij} c_p (T_{in,j} - T_{in,i}) + \text{unmodeled conduction} \tag{6(a)}$$

    $$ d_{W,i} = \dot{m}_{inf,i}(W_{out} - W_{in,i}) + \sum \dot{m}_{mix,ij} (W_{in,j} - W_{in,i}) + \text{unmodeled moisture leaks} \tag{6(b)}$$

    $$ d_{C,i} = \dot{V}_{inf,i}(C_{out} - C_{in,i}) + \sum \dot{V}_{mix,ij} (C_{in,j} - C_{in,i}) + \text{unmodeled } CO_2 \text{ leaks} \tag{6(c)}$$


    Then our system becomes,

    $$C_{\text{air},i} \ \dot{T}_{in,i}=
    \frac{T_{\text{out}} - T_{in,i}}{R_{\text{env,external},i}} +
    \sum_{j \in \text{adj}(i)} \frac{T_{in,j} - T_{in,i}}{R_{\text{env,couple},ij}} +
    \frac{T_{m,i} - T_{in,i}}{R_{\text{int},i}} +
    N_{occ,i}⋅q_{person}+
    \rho_{air} \dot{V}_{s,i} \ c_p \ (T_s - T_{in,i}) +
    d_{T,i} \tag{7}$$

    $$C_{\text{mass},i} \ \dot{T}_{m,i}= \frac{T_{in,i} - T_{m,i}}{R_{\text{int},i}} \tag{8}$$

    $$M_{air,i}\ \dot{W}_{in,i} =
    N_{occ,i} ⋅g_{w,person} +
    \dot{m}_{s,i}(W_s - W_{in,i}) +
    d_{W,i} \tag{9}$$

    $$V_{room,i}  \ \dot{C}_{in,i} =
    N_{occ,i}⋅g_{co2,person} +
    \dot{V}_{s,i}(C_{s} - C_{in,i}) +
    d_{C,i} \tag{10}$$

    _(Note: In this calculations I have removed $X_i$ notation for simplicity.)_
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## MPC Design
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1. State and Disturbance Extraction
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    At the start of control interval k, the MPC read the optimal estimates from EKF.
    At every control interval k, the EKF provides an augmented state vector, which the MPC splits into two distinct categories,

    The System States ($\hat{x}_k$)
    $$ \hat{x}_k = \begin{bmatrix} T_{in} \\ T_{m} \\ C_{in} \\ W_{in}  \end{bmatrix} $$

    Unmeasured Disturbances ($\hat{d}_k$)
    $$ \hat{d}_k = \begin{bmatrix}  d_{T} \\ d_{W} \end{bmatrix} $$

    The Control Input ($u$)
    $$ u = \begin{bmatrix} \dot{V}_s \end{bmatrix}$$

    The MPC assumes that whatever unmodeled disturbances are happening right now will remain constant across the entire future prediction horizon ($N_p$)

    $$\dot{x}(t)=f(x(t),u(t),d(t))$$

    In Real-Time Iteration, we linearize around the current reality of the system at time step $k$. We freeze the system using the optimal estimates from the EKF ($\hat{x}_{k∣k}$ and $\hat{d}_{k∣k}$) and the previously applied control action ($u_{k-1}$).

    * $x_{op} = \hat{x}_{k|k} = [\hat{T}_{in}, \hat{T}_m, \hat{C}_{in}, \hat{W}_{in}]^T$

    * $u_{op} = u_{k-1}$

    * $d_{op} = \hat{d}_{k|k} = [\hat{d}_T, \hat{d}_W, 0]^T$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2. Successive Linearization
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Standard embedded solvers (like OSQP) only solve Quadratic Programs (QPs), which strictly require linear dynamics. So use Successive Linearization to linearize the dynamics.

    1. The State Jacobian $A_c$

    $$A_c = \left. \frac{\partial f}{\partial x} \right|_{x_{op}, u_{op}, d_{op}}$$

    $$A_c = \begin{bmatrix}
    \frac{\partial \dot{T}{in}}{\partial T{in}} & \frac{\partial \dot{T}{in}}{\partial T_m} & 0 & 0 \\
    \frac{\partial \dot{T}m}{\partial T{in}} & \frac{\partial \dot{T}m}{\partial T_m} & 0 & 0 \\
    0 & 0 & \frac{\partial \dot{C}{in}}{\partial C{in}} & 0 \\
    0 & 0 & 0 & \frac{\partial \dot{W}{in}}{\partial W{in}}
    \end{bmatrix}$$

    $$A_c = \begin{bmatrix}
    -\frac{1}{C_{air,i}} \left( \frac{1}{R_{env,ext,i}} + \sum \frac{1}{R_{env,cpl,ij}} + \frac{1}{R_{int,i}} + \rho_{air} c_p \dot{V}_{s,i,op} \right) & \frac{1}{C{air,i} R_{int,i}} & 0 & 0 \\
    \frac{1}{C_{mass,i} R_{int,i}} & -\frac{1}{C_{mass,i} R_{int,i}} & 0 & 0 \\
    0 & 0 & -\frac{\dot{V}_{s,i,op}}{V_{room,i}} & 0 \\
    0 & 0 & 0 & -\frac{\dot{m}_{s,i,op}}{M_{air,i}}
    \end{bmatrix}$$

    2. The Input Jacobian $B_c$

    $$B_c = \left. \frac{\partial f}{\partial u} \right|_{x_{op}, u_{op}, d_{op}}$$

    $$B_c = \begin{bmatrix}
    \frac{\partial \dot{T}{in}}{\partial u} \\
    0 \\
    \frac{\partial \dot{C}{in}}{\partial u} \\
    \frac{\partial \dot{W}_{in}}{\partial u}
    \end{bmatrix}$$

    $$B_c =  \begin{bmatrix}
    \frac{\rho_{air} c_p (T_s - T_{in,i,op})}{C_{air,i}} \\
    0 \\
    \frac{C_s - C_{in,i,op}}{V_{room,i}} \\
    \frac{\rho_{air} (W_s - W_{in,i,op})}{M_{air,i}}
    \end{bmatrix}$$

    3. The Affine Drift Vector $C_c$

    To complete the Taylor series, we calculate the continuous drift vector to capture the affine offset

    $$c_c = f(x_{op}, u_{op}, d_{op}) - A_c x_{op} - B_c u_{op}$$

    The locally linear continuous model is now mathematically perfectly flat at this exact millisecond

    $$\dot{x} = A_c x + B_c u + c_c$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3. Discretization
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Embedded QP solvers operate in discrete steps $i=0,1,…,N_p$ across the prediction horizon. We convert our continuous affine model ($\dot{x}$) to a discrete model ($x_{i+1}$) using your controller's sampling time $T_s$.

    Using the Forward Euler approximation:

    $$\dot{x} \approx \frac{x_{i+1} - x_i}{T_s}$$

    Substitute our affine continuous model:

    $$\frac{x_{i+1} - x_i}{T_s} = A_c x_i + B_c u_i + c_c$$

    Multiply by $T_s$ and isolate $x_{i+1}$:

    $$x_{i+1} = x_i + T_s A_c x_i + T_s B_c u_i + T_s c_c$$

    $$x_{i+1} = (I_{4 \times 4} + T_s A_c)x_i + (T_s B_c)u_i + (T_s c_c)$$

    Yielding the final discrete matrices:

    * $A_d = I_{4 \times 4} + T_s A_c$
    * $B_d = T_s B_c$
    * $c_d = T_s c_c$

    Note : $T_s$ is chosen such that $|λ_i(A_d)| < 1$ for all eigenvalues,
    Check : switch to $expm(A_c·T_s)$ (matrix exponential / ZOH) for $A_d$ and $(A_c)⁻¹(A_d - I)·B_c$ for $B_d$. ZOH is unconditionally stable for stable systems.

    At the current control interval $k$ $A_d, B_d$, and $c_d$.
    $$x_{i+1} = A_d x_i + B_d u_i + c_d$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4. Offset-Free Target Selector
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    In standard MPC, the controller minimizes a cost function to drive the system states ($x$) directly to a setpoint ($y_{ref}$). But with disturbances the optimization solver will eventually balance the penalty of being slightly off-target against the penalty of using excessive fan energy. This results in a persistent gap between the actual room temperature and the setpoint, known as **steady-state error** or **offset**.

    To eliminate this offset, the MPC must be coupled with the Extended Kalman Filter’s (EKF) Disturbance Observer. By feeding the estimated disturbances ($\hat{d}_T, \hat{d}_W$) into the MPC, we can mathematically solve for an artificial steady-state target ($x_{ss}, u_{ss}$) that inherently pre-compensates for the invisible load. The MPC then tracks this shifted target rather than the zero-state.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    1. The Steady-State

    $$x_{k+1} = A_d x_k + B_d u_k + c_d$$

    The affine drift vector $c_d$ already contains the mathematical influence of the current unmeasured disturbances ($\hat{d}_T, \hat{d}_W$) extracted from the EKF.

    To find the steady-state targets, we set the condition where the system comes to a complete rest. At steady-state, the rate of change is zero, meaning the next state is identical to the current state:

    $$x_{k+1} = x_k = x_{ss}$$

    Substitute $x_{ss}$ into the discrete dynamics equation:

    $$x_{ss} = A_d x_{ss} + B_d u_{ss} + c_d$$

    $$x_{ss} - A_d x_{ss} - B_d u_{ss} = c_d$$

    Equation 1: The physical steady-state condition
    $$(I - A_d)x_{ss} - B_d u_{ss} = c_d \quad \tag{01}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    2. The Output Tracking Requirement
    We do not need or want to track every state to a specific number. For instance, the exact temperature of the furniture ($T_m$) is irrelevant as long as the indoor air ($T_{in}$) is comfortable.

    We define an output matrix $C_y$ that extracts only the variables we want to actively track. For a 4-state system ($T_{in}, T_m, C_{in}, W_{in}$) with a priority on temperature control, we track only $T_{in}$:

    $$C_y = \begin{bmatrix} 1 & 0 & 0 & 0 \end{bmatrix}$$

    We mandate that our steady-state targets must perfectly equal our reference setpoint ($y_{ref}$):

    Equation 2: The tracking condition

    $$C_y x_{ss} = y_{ref} \quad \tag{2}$$


    3. The Augmented Linear System
    4.
    Combine Equation 1 and Equation 2 into a single block-matrix formulation:

    $$\begin{bmatrix} I - A_d & -B_d \\ C_y & 0 \end{bmatrix} \begin{bmatrix} x_{ss} \\ u_{ss} \end{bmatrix} = \begin{bmatrix} c_d \\ y_{ref} \end{bmatrix}$$

    we can solve this system of equations at every time step using standard LU decomposition

    $$\begin{bmatrix} x_{ss} \\ u_{ss} \end{bmatrix} = \begin{bmatrix} I - A_d & -B_d \\ C_y & 0 \end{bmatrix}^{-1} \begin{bmatrix} c_d \\ y_{ref} \end{bmatrix}$$

    ##### The Physical Result
    By solving this matrix, the controller identifies exactly how far open the damper must be ($u_{ss}$) to perfectly counter the human body heat currently recorded in $c_d$, while mathematically guaranteeing that $T_{in}$ settles exactly at the desired $T_{ref}$.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### **Note on Underactuation and Matrix Rank**

    With a single Variable Air Volume (VAV) damper ($\dot{V}_s$), the system is underactuated. We cannot simultaneously force the temperature, the CO2, and the humidity to setpoint  using one stream of air.

    Therefore, in the Target Selector:

    * **Priority 1 (Temperature):** Placed directly in the $C_y$ tracking matrix to determine the steady-state baseline.
    * **Priority 2 & 3 (CO2 and Humidity):** Dropped from the Target Selector entirely. Instead, they are handled in the Quadratic Program (QP) as hard or soft inequality constraints (e.g., $C_{in} \leq 1000$ ppm). The QP solver will seamlessly maintain the perfect temperature trajectory calculated by the Target Selector until a safety boundary is reached, at which point it will mathematically sacrifice the temperature setpoint to flush the room with fresh air.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 5. Formulate the Optimal Control Problem (OCP)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The predictive controller must calculate the optimal sequence of future damper positions over a prediction horizon $N_p$. It does this by solving a constrained Quadratic Program (QP).

    1. Define the Error Variables

    We want to penalize the system for deviating from the optimal steady-state targets ($x_{ss}, u_{ss}$) computed by the Target Selector.

    Define the deviation variables for the states, the input, and the input slew rate:

    $$\Delta x_i = x_i - x_{ss}$$

    $$\Delta u_i = u_i - u_{ss}$$

    $$\delta u_i = u_i - u_{i-1}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    2. The Quadratic Cost Function ($J$)

    The objective is to minimize the total cost across the entire horizon ($i = 0$ to $N_p - 1$), plus a terminal cost at the end of the horizon ($N_p$) to guarantee mathematical stability.

    To prevent the embedded solver from crashing if the air quality and humidity constraints become impossible to satisfy simultaneously (e.g., if the supply air itself is humid), we must introduce **slack variables** ($\epsilon_c$ and $\epsilon_w$) to create "soft constraints."

    $$J = \sum_{i=0}^{N_p-1} \left( \Delta x_i^T Q \Delta x_i + \Delta u_i^T R \Delta u_i + \delta u_i^T R_{\Delta} \delta u_i \right) + \Delta x_{N_p}^T P \Delta x_{N_p} + \rho_c \epsilon_c^2 + \rho_w \epsilon_w^2$$

    > The Weighting Matrices

    * $Q \in \mathbb{R}^{4 \times 4}$ **(State Penalty):** A diagonal matrix.
        * $Q_{1,1}$ (for $T_{in}$): Set very high. The controller must aggressively track the temperature target.
        * $Q_{2,2}$ (for $T_m$): Set moderately. Keeps the thermal mass stable and prevents aggressive temperature swings.
        * $Q_{3,3}$ and $Q_{4,4}$ (for $C_{in}$ and $W_{in}$): Set to exactly **zero**. We do *not* want the cost function trying to track a specific steady-state CO2 or Humidity number. We only care about their boundaries.
    * $R \in \mathbb{R}^{1 \times 1}$ **(Input Penalty):** Penalizes using excessive supply air ($\dot{V}_s$), implicitly saving fan energy and preventing overcooling.
    * $R_{\Delta} \in \mathbb{R}^{1 \times 1}$ **(Slew Rate Penalty):** Heavily penalizes rapid changes in the damper position, preventing mechanical wear and tear on the VAV box motor.
    * $\rho_c, \rho_w$ **(Slack Penalties):** Massive scalar weights (e.g., $10^6$) applied to the slack variables. This guarantees the solver will only violate the CO2 or Humidity boundaries if the mathematical problem becomes literally impossible.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    3. Define the Constraints

    The solver minimizes the cost function $J$ subject to the physical realities of the room and the mechanical system. These constraints are enforced at every step $i$ in the prediction horizon.

    **A. Initialization: **
    The starting point is explicitly locked to the current EKF estimates.

    $$x_0 = \begin{bmatrix} \hat{T}_{in} \\ \hat{T}_m \\ \hat{C}_{in} \\ \hat{W}_{in} \end{bmatrix}_{k|k}$$

    **B. System Dynamics (Equality Constraint):**
    The future states must obey the discrete, locally linear physics we derived via the Taylor series expansion.

    $$x_{i+1} = A_d x_i + B_d u_i + c_d$$

    **C. Actuator Limits (Hard Inequality Constraint):**
    The damper cannot open more than 100%, and it cannot supply negative air.

    $$0 \leq u_i \leq \dot{V}_{s,max}$$

    **D. Slew Rate Limits (Hard Inequality Constraint):**
    The physical speed of the damper motor restricts how far it can move in one sample time ($T_s$).

    $$-\Delta u_{max} \leq \delta u_i \leq \Delta u_{max}$$

    **E. Air Quality Bounds (Soft Inequality Constraint - Priority 2):**
    Ensures the room remains safe for human occupancy per ASHRAE standards. If the room hits 1000 ppm, the slack variable $\epsilon_c$ engages, forcing the solver to sacrifice the temperature tracking to flush the room with fresh air.

    $$C_{in,i} \leq 1000 + \epsilon_c$$
    $$\epsilon_c \geq 0$$

    **F. Humidity Bounds (Soft Inequality Constraint - Priority 3):**
    Ensures the room does not become uncomfortably humid.

    $$W_{in,i} \leq W_{max} + \epsilon_w$$
    $$\epsilon_w \geq 0$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 6. Dense Vectorization (Standard QP Form)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Embedded solvers only understand linear algebra arrays in a highly specific, standardized format known as the **Standard Sparse QP Formulation**.

    Every QP solver requires the problem to be formatted as,
    $$\min_{Z} \frac{1}{2} Z^T H Z + q^T Z$$
    $$\text{subject to:} \quad l \le G Z \le u_{bounds}$$

    1. Define the Global Decision Vector ($Z$)
    The solver needs a single vector containing everything it has the power to decide or predict across the entire horizon ($N_p$).

    At each time step $i$, group the state variables, the control input, and our two soft-constraint slack variables ($\epsilon_c, \epsilon_w$) into a stage vector $z_i$:
    $$z_i = \begin{bmatrix} x_i \\ u_i \\ \epsilon_{c,i} \\ \epsilon_{w,i} \end{bmatrix} \in \mathbb{R}^7$$

    Stack these stage vectors from $i=0$ to the end of the horizon $N_p$ to create the global decision vector $Z$:
    $$Z = \begin{bmatrix} z_0 \\ z_1 \\ \vdots \\ z_{N_p-1} \\ x_{N_p} \end{bmatrix}$$
    *(Note: The terminal step $N_p$ only contains states, no inputs or slacks).*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    2. Construct the Hessian Matrix ($H$)
    The Hessian matrix defines the quadratic costs (the $Q, R,$ and $\rho$ penalties). Because there is no cross-penalty between time step $i$ and time step $i+1$, $H$ is a **block-diagonal** matrix.

    For a single stage $i$, the local Hessian $H_i$ is:

    $$ H_i = \begin{bmatrix}
    Q_{4 \times 4} & 0 & 0 & 0 \\
    0 & R_{1 \times 1} & 0 & 0 \\
    0 & 0 & \rho_c & 0 \\
    0 & 0 & 0 & \rho_w
    \end{bmatrix} $$

    The global Hessian $H$ is constructed by placing these blocks along the diagonal, ending with the terminal penalty $P$:
    $$H = \text{blockdiag}(H_0, H_1, \dots, H_{N_p-1}, P)$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    3. Construct the Gradient Vector ($q$)

    The $H$ matrix penalizes deviation from *zero*. But we don't want to drive the room to zero, we want to drive it to the steady-state targets ($x_{ss}, u_{ss}$) computed by the Target Selector.

    The linear gradient vector $q$ shifts the quadratic so its minimum rests on target.

    For a single stage $i$, the local target vector is:
    $$z_{ss} = \begin{bmatrix} x_{ss} \\ u_{ss} \\ 0 \\ 0 \end{bmatrix}$$

    The local gradient $q_i$ is calculated as:
    $$q_i = -H_i z_{ss}$$

    The global gradient vector $q$ is simply stacked:
    $$q = \begin{bmatrix} q_0 \\ q_1 \\ \vdots \\ q_{N_p-1} \\ -P x_{ss} \end{bmatrix}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    4. Construct the Constraint Matrix ($G$) and Bounds ($l, u_{bounds}$)

    The matrix $G$ enforces both the physical equations (equalities) and the safety limits (inequalities) simultaneously.

    For the QP solver, an equality constraint is just an inequality where the upper and lower bounds are identical ($l = u_{bounds}$).

    **A. Initial Condition (Equality):**

    The first constraint locks the starting state to the EKF output.
    * $x_0 = \hat{x}_{k|k}$
    * Lower Bound = Upper Bound = $\hat{x}_{k|k}$

    **B. System Dynamics (Equality):**

    The solver must obey Taylor-series physics:
    $$x_{i+1} - A_d x_i - B_d u_i = c_d$$
    This creates a diagonal band of $-A_d$ and $-B_d$ blocks shifting one step to the right, enforcing the transition from step $i$ to $i+1$.

    Lower Bound = Upper Bound = $c_d$

    **C. Actuator and Slew Limits (Inequalities):**

    The matrix pulls out $u_i$ and applies the limits.
    * $0 \le u_i \le \dot{V}_{s,max}$
    * For slew rate: $-\Delta u_{max} \le u_i - u_{i-1} \le \Delta u_{max}$

    **D. The Soft Constraints (Inequalities for Priorities 2 & 3):**

    The $G$ matrix connects the states to the slack variables to enforce humidity bounds.
    * $C_{in, i} - \epsilon_{c,i} \le 1000$  (Lower bound: $-\infty$, Upper bound: $1000$)
    * $W_{in, i} - \epsilon_{w,i} \le W_{max}$ (Lower bound: $-\infty$, Upper bound: $W_{max}$)
    * $\epsilon_{c,i} \ge 0$ and $\epsilon_{w,i} \ge 0$ (Lower bound: 0, Upper bound: $+\infty$)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Final Execution Loop
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    1. Timer Interrupt ($t = k T_s$)
    2. Read sensors and run the EKF to get $\hat{x}_{k|k}$ and $\hat{d}_{k|k}$.
    3. Calculate $A_d, B_d, c_d$ (Successive Linearization).
    4. Solve the $5 \times 5$ Target Selector matrix for $x_{ss}, u_{ss}$.
    5. Update the QP
    6. Run QP Solver
    7. Extract $U[0]$
    8. Set Output
    """)
    return


if __name__ == "__main__":
    app.run()
