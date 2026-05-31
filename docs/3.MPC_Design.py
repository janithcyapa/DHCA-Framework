import marimo

__generated_with = "0.23.4"
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
    \rho_{air} \dot{V}_{s,i} (W_s - W_{in,i}) +
    d_{W,i} \tag{9}$$

    $$V_{room,i}  \ \dot{C}_{in,i} =
    N_{occ,i}⋅g_{co2,person} +
    \dot{V}_{s,i}(C_{s} - C_{in,i}) +
    d_{C,i} \tag{10}$$

    _(Note: In this calculations I have removed $X_i$ notation for simplicity.)_

    *Note: For numerical consistency, \(C\) is expressed as a volumetric fraction (m³ CO₂ / m³ air) in the ODE.
    Conversion: \(C_{\text{frac}} = C_{\text{ppm}} \times 10^{-6}\). The generation rate \(g_{co2,person}\) is then in m³/s·person.*
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
    -\frac{1}{C_{air}} \left( \frac{1}{R_{env,ext}} + \sum \frac{1}{R_{env,cplj}} + \frac{1}{R_{int}} + \rho_{air} c_p u_{op} \right) & \frac{1}{C{air} R_{int}} & 0 & 0 \\
    \frac{1}{C_{mass} R_{int}} & -\frac{1}{C_{mass} R_{int}} & 0 & 0 \\
    0 & 0 & -\frac{\rho_{air}u_{op}}{M_{air}} & 0 \\
    0 & 0 & 0 & -\frac{u_{op}}{V_{room}}
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
    \frac{\rho_{air} c_p (T_s - T_{in,op})}{C_{air}} \\
    0 \\
    \frac{\rho_{air} (W_s - W_{in,op})}{M_{air}} \\
    \frac{C_s - C_{in,op}}{V_{room}}
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

    $$x_{i+1} = x_i +  A_c x_i T_s +  B_c u_i T_s + c_c T_s$$

    $$x_{i+1} = (I_{4 \times 4} + A_c T_s)x_i + (B_c T_s)u_i + (c_c T_s)$$

    Yielding the final discrete matrices:

    * $A_d = I_{4 \times 4} + A_c T_s$
    * $B_d = B_c T_s$
    * $c_d = c_c T_s$

    Note : $T_s$ is chosen such that $|λ_i(A_d)| < 1$ for all eigenvalues,
    Check : switch to $expm(A_c·T_s)$ (matrix exponential / ZOH) for $A_d$ and $(A_c)⁻¹(A_d - I)·B_c$ for $B_d$. ZOH is unconditionally stable for stable systems.

    At the current control interval $k$ $A_d, B_d$, and $c_d$.
    $$x_{k+1} = A_d x_k + B_d u_k + c_d$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4. Formulating the Sparse QP Problem
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We must format everything into the standard Sparse QP formulation,

    **Minimize:**
    $$\frac{1}{2} Z^T P Z + q^T Z$$

    **Subject to:**
    $$l \le G Z \le u$$


    - Global Decision Vector (Z)
    - Cost Function (Hessian P and Gradient q)
    - Constraints Matrix (G) and Bounds (l,u)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    1. The Global Decision Vector ($Z$)

    We stack the states $x$, the inputs $u$, and our slack variables $\epsilon_c$ ($CO_2$ penalty) and $\epsilon_w$ (Humidity penalty) across the entire prediction horizon $N$.

    $$Z = [x_0, x_1, \dots, x_N, \; u_0, u_1, \dots, u_{N-1}, \; \epsilon_{c,1}, \dots, \epsilon_{c,N}, \; \epsilon_{w,1}, \dots, \epsilon_{w,N}]^T$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    2. The Cost Function (Hessian $P$ and Gradient $q$)

    We heavily penalize deviating from the Temperature setpoint ($T_{ref}$), lightly penalize fan energy ($u$), and **massively** penalize the slack variables to create your exponential-style boundary shield.

    * $Q_{diag}$: Penalty for temperature. Only the first element is non-zero ($Q_{1,1} \gg 0$). We do not penalize $CO_2$ or Humidity tracking here.
    * $R$: Penalty for damper usage.
    * $\rho_c, \rho_w$: Massive penalties (e.g., $10^6$) for exceeding ASHRAE limits.

    The Hessian block matrix $P$ is structured diagonally:


    $$P = \text{blockdiag}(Q, Q, \dots, Q_N, \; R, R, \dots, R, \; \rho_c, \dots, \rho_c, \; \rho_w, \dots, \rho_w)$$

    The Gradient vector $q$ shifts the temperature quadratic bowl so its minimum rests exactly on $T_{ref}$:


    $$q = [-Q x_{ref}, \dots, -Q x_{ref}, \; 0, \dots, 0, \; 0, \dots, 0, \; 0, \dots, 0]^T$$


    *(Where $x_{ref} = [T_{ref}, 0, 0, 0]^T$)*
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    3. The Constraints Matrix ($G$) and Bounds ($l, u$)

    We build a massive, sparse matrix $G$ to enforce three physical laws simultaneously.

    **I. Constraint A: System Dynamics (Equality)**

    The solver must obey your thermodynamic equations.


    $$x_{k+1} - A_d x_k - B_d u_k = c_d$$

    * **Lower Bound ($l$) = Upper Bound ($u$) = $c_d$**

    **II. Constraint B: Actuator Limits (Hard Inequality)**
    The VAV box damper has minimum and maximum limits.


    $$0 \le u_k \le \dot{V}_{s,max}$$

    * **Lower Bound = $0$, Upper Bound = $\dot{V}_{s,max}$**

    **III. Constraint C: The ASHRAE Comfort Zone (Soft Inequality)**

    This implements your underactuated strategy. We tie the predicted $CO_2$ and Humidity states to the slack variables.


    $$C_{in, k} - \epsilon_{c, k} \le 1000$$

    $$W_{in, k} - \epsilon_{w, k} \le W_{max}$$

    * **Lower Bound = $-\infty$, Upper Bound = $1000$ (and $W_{max}$)**
    * *Note: We also mandate that slacks cannot be negative:* $0 \le \epsilon \le \infty$.
    """)
    return


if __name__ == "__main__":
    app.run()
