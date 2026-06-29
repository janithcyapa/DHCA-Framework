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
    # **Controllability Analysis**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## **Define Requirements**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Since there is only one control input ($u = \dot{V}_s$) acting on three states ($T_{in}, W_{in}, C_{in}$), the system cannot track arbitrary setpoints for all three simultaneously. However, it can maintain all three within defined bounded regions if their acceptable control limits overlap.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Target HVAC Design Parameters

    Based on **ASHRAE Standard 55** (Thermal Environmental Conditions for Human Occupancy) and **ASHRAE Standard 62.1** (Ventilation for Acceptable Indoor Air Quality).

    | Parameter | Recommended Comfort Range | Hard Limits / System Capacity | Standard |
    | --- | --- | --- | --- |
    | **Operative Temperature** | **23°C to 26°C** (Summer/Cooling) <br/>**20°C to 23.5°C** (Winter/Heating) | **18°C to 28°C** | ASHRAE 55 |
    | **Relative Humidity (RH)** | **30% to 60%** | **Maximum 65%** | ASHRAE 55 |
    | **Carbon Dioxide (CO2)** | **< 1000 ppm** | **Outdoor Ambient + 700 ppm** | ASHRAE 62.1 |

    * Therefore, the system should actively ventilate to keep indoor CO2 under **1000 to 1100 ppm**.

    Introducing fresh outside air inevitably brings in unconditioned, often humid air, introducing disturbances that your controller's state estimator will need to account for to maintain the thermal equilibrium of the space.

    Are you planning to control the fresh air intake dampers actively based on CO2 sensor feedback, or will the system rely on a fixed minimum ventilation rate?
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## **Viability and Control Set Invariance**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### System Dynamics
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    From previos system modeling,

    $$C_{\text{air}} \ \dot{T}_{in}=
    \frac{T_{\text{out}} - T_{in}}{R_{\text{env,external}}} +
    N_{occ}⋅q_{person}+
    \rho_{air} \dot{V}_{s} \ c_p \ (T_s - T_{in}) +
    d_{T} $$

    $$M_{air}\ \dot{W}_{in} =
    N_{occ} ⋅g_{w,person} +
    \rho_{air} \dot{V}_{s} (W_s - W_{in}) +
    d_{W} $$

    $$V_{room}  \ \dot{C}_{in} =
    N_{occ}⋅g_{co2,person} +
    \dot{V}_{s}(C_{s} - C_{in}) +
    d_{C} $$

    *Note: For numerical consistency, \(C\) is expressed as a volumetric fraction (m³ CO₂ / m³ air) in the ODE.
    Conversion: \(C_{\text{frac}} = C_{\text{ppm}} \times 10^{-6}\). The generation rate \(g_{co2,person}\) is then in m³/s·person.*
    $$u = V_{s,i} \in [0, u_{max}]$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Constraint Set
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Considering three states of the system, and the ASHRE standard define the acceptable comfort region as a polytope $X \subset \mathbb{R}^{3}$ specified by six inequalities.

    - Temperature upper bound - $T_{in} \le T_{set} + \Delta T$
    - Temperature lower bound - $T_{in} \ge T_{set} - \Delta T$
    - Humidity upper bound - $W_{in} \le W_{max}$
    - Humidity lower bound - $W_{in} \ge W_{min}$
    - $CO_2$ upper bound - $C_{in} \le C_{max}$
    - $CO_2$ lower bound - $C_{in} \ge C_{env}$

    In here, $\Delta T$ is the accetable deviation from temperature setpoint.And there is also,

    - saturation constraints of supply - $u \le u_{max}$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Apply Conditions at Constraint Boundary by Nagumo's theorem
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    REF: https://www.emergentmind.com/topics/nagumo-type-invariance-condition

    By , the set $X$ is a Control Invariant Set if and only if at every boundary face there exists an admissible $u \in [0, u_{max}]$ such that the system vector field points strictly inward.

    Therefore, Lie derivative $h_k = \nabla h_k \cdot f(x,u) \le 0$ at each constraint.


    Considering the temperature upper bound define barrier funtions,

    $$h_1 = T_{in} - ( T_{set} + \Delta T) \le 0$$

    Then,
    $$\nabla h_1 = \frac{\partial}{\partial T_{in}} (T_{in} - ( T_{set} + \Delta T)) = 1$$
    $$\dot{T}_{in} = \frac{1}{C_{air}} \left[ \frac{T_{out} - T_{in}}{R_{env}} + N_{occ} \cdot q_{person} + \rho_{air} u c_p (T_s - T_{in}) + d_T \right]$$

    Therefore by subsituting these question to Lie derivative condition at $T_{in} = ( T_{set} + \Delta T)$,
    $$\frac{1}{C_{air}} \left[ \frac{T_{out} - ( T_{set} + \Delta T)}{R_{env}} + N_{occ} \cdot q_{person} + \rho_{air} u c_p (T_s - ( T_{set} + \Delta T)) + d_T \right] \le 0$$

    $$\rho_{air} u c_p (T_s - ( T_{set} + \Delta T)) \le -\left( \frac{T_{out} - ( T_{set} + \Delta T)}{R_{env}} + N_{occ} \cdot q_{person} + d_T \right)$$

    > Assume, $T_s < ( T_{set} + \Delta T)$ (supply air is cooler than the upper setpoint), the term $(T_s - ( T_{set} + \Delta T))$ is negative
    $$u \ge \left( \frac{\frac{T_{out} - ( T_{set} + \Delta T)}{R_{env}} + N_{occ} \cdot q_{person} + d_T}{\rho_{air} c_p (( T_{set} + \Delta T)- T_s)} \right)$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    > #### Assumptions

    - Sensible Cooling Capacity ($T_s < T_{hi}$) - The supply air temperature must be colder than the upper  limit to provide effective sensible cooling.
    - Cooling Mode Operation ($T_{out} > T_{lo}$) - Assumes the building is in cooling mode, where environmental heat flux is positive (this assumption would require inversion in winter/heating-dominated climates).
    - Dehumidification Capacity ($W_s < W_{max}$) - The AHU cooling coil must be sufficiently sized to deliver supply air humidity below the indoor limit.
    - Prevention of Over-drying ($W_s > W_{min}$) - The supply air must be wetter than the 30% RH lower limit to prevent over-drying.
    - Fresh Air Assumption ($C_s < C_{max}$) - The supply air must be fresher than the maximum indoor $CO_2$ threshold.
    - Occupant Presence ($N_{occ} > 0$) - The environmental lower bound for $CO_2$ is only active when occupants are present to generate $CO_2$.
    - Actuator Physicality ($u_{max} > 0$) - The system assumes a positive, non-zero mechanical fan capacity, defining the upper physical limit for the control input.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Then we can derive other constraints for u,
    Temperature bound,
    $$u \ge u_{T,min} =  \frac{\frac{T_{out} - ( T_{set} + \Delta T)}{R_{env}} + N_{occ} \cdot q_{person} + d_T}{\rho_{air} c_p (( T_{set} + \Delta T)- T_s)} $$

    $$u \le u_{T,max} = \frac{\frac{T_{out} - (T_{set} - \Delta T)}{R_{env}} + N_{occ} \cdot q_{person} + d_T}{\rho_{air} c_p ((T_{set} - \Delta T) - T_s)}$$

    Humidity bouds,
    $$u \ge u_{W,max} = \frac{N_{occ} g_w + d_W/M_{air}}{\rho_{air} (W_{max} - W_s)}$$
    $$u \le u_{W,min} = \frac{N_{occ} g_w + d_W/M_{air}}{\rho_{air} (W_{min} - W_s)}$$

    $CO_2$ Bounds,
    $$u \ge u_{CO2} = \frac{N_{occ} g_{co2} + d_C}{C_{max} - C_s}$$

    Saturation Bound,
    $$u \le u_{max}$$

    Note: When derive the $CO_2$ lower bound is proven to be  naturally invariant regardless of  $u$,  $\frac{N_{occ} g_{co2} + d_C}{V_{room}} \ge 0$.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Collecting all barrier bounds, the system is simultaneously viable if and only if there exists $u \in [0, u_{max}]$ such that all constraints are met.

    $$u_{lo} = \max(u_{CO2}, u_{W,max}, u_{T,min})$$
    $$u_{hi} = \min(u_{T,max}, u_{W,min}, u_{max})$$

    All three quantities ($T_{in}$, $W_{in}$, $C_{in}$) can be simultaneously kept within bounds if and only if,
    $$u_{lo} \le u_{hi}$$

    When this holds, any controller that selects $u(t) \in [u_{lo}, u_{hi}]$ at each instant guarantees $X$ is positively invariant. The viability condition $u_{lo} \le u_{hi}$ can fail in two qualitatively different ways.

    1. Case A: $u_{lo} > u_{hi}$

    Ventilation + dehumidification requirement exceeds the maximum airflow permitted by the temperature lower bound.
    $$\max(u_{CO2}, u_{W,max}, u_{T,min}) > u_{T,max} \tag{22}$$

    3. Case B: $u_{lo} > u_{max}$ (System capacity exceeded)

    Tf $u_{lo}$ exceeds the physical fan capacity $u_{max}$, no control action can satisfy the constraints. This happens when the building load is extremely high for HVAC system.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## **Conditioning Both Humidity and CO2**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Assume under the condition wheere $Co_2$ and humidity distabnaces are negligibale, then both $u_{CO2}$ and $u_{W,max}$ scale linearly with $N_{occ}$. Then ratio of,

    $$\frac{u_{CO2}}{u_{W,max}} = \left( \frac{N_{occ} \cdot g_{co2}}{C_{max} - C_s} \right) \cdot \left( \frac{\rho_{air} (W_{max} - W_s)}{N_{occ} \cdot g_w} \right)$$

    $$\frac{u_{CO2}}{u_{W,max}} = \frac{g_{co2} \cdot \rho_{air} \cdot (W_{max} - W_s)}{g_w \cdot (C_{max} - C_s)}$$

    Take Supply Humidity ($W_s^*$), is the value at which the $CO_2$ ventilation requirement and the humidity dehumidification requirement are exactly equal
    $$u_{CO2} = u_{W,max}$$
    $$\frac{N_{occ} \cdot g_{co2}}{C_{max} - C_s} = \frac{N_{occ} \cdot g_w}{\rho_{air} (W_{max} - W_s^*)}$$
    $$g_{co2} \cdot \rho_{air} \cdot (W_{max} - W_s^*) = g_w \cdot (C_{max} - C_s)$$

    $$W_s^* = W_{max} - \frac{g_w \cdot (C_{max} - C_s)}{\rho_{air} \cdot g_{co2}}$$


    Similarly,
    $$C_s^* = C_{max} - \frac{(W_{max} - W_s) \cdot \rho_{air} \cdot g_{co2}}{g_w}$$

    If $C_s > C_s^*$ - The supply air has a higher $CO_2$ concentration than the critical threshold, which makes $(C_{max} - C_s)$ smaller. This increases the required airflow for $CO_2$ control ($u_{CO2}$), ensuring $CO_2$ remains the binding lower bound.

    If $C_s < C_s^*$ - The supply air is cleaner (e.g., more fresh air), which reduces the $CO_2$ airflow requirement. If the supply air is sufficiently clean, it is possible for the humidity requirement to become the binding constraint instead, depending on the performance of the cooling coil ($W_s$).

    > By enforcing an AHU supply condition where $C_s < C_s^*$, the system is reconfigured such that the humidity requirement becomes the dominant lower-bound constraint. This stabilization of $u_{lo}$ allows the controller to utilize the temperature deadband $\Delta T$ as a buffer for thermal disturbances, effectively decoupling the rapid stochastic fluctuations of $CO_2$ from the thermal regulation of the zone.
    """)
    return


@app.cell
def _():
    import numpy as np

    def verify_daytime_viability():
        # --- System Parameters (SPACE1-1) ---
        R_env, M_air, rho_air, c_p = 0.0043, 288.05, 1.2, 1006.0
        T_set, Delta_T = 24.5, 1.5
        W_max, W_min = 0.012, 0.005
        C_max, u_max = 0.001, 2.0
        q_person, g_w, g_co2 = 75.0, 0.000015, 0.000008

        # --- 10-Hour Daytime Profile (08:00 - 18:00) ---
        hours = np.arange(8, 19)
        # Peak load simulation
        T_out = 28 + 10 * np.sin(np.pi * (hours - 8) / 10) 
        N_occ = 5 * np.sin(np.pi * (hours - 8) / 10) 

        # AHU Control logic: Supply cooler air during high heat/occ
        T_s = np.where(T_out > 30, 14.0, 16.0)
        W_s = np.where(T_s == 14.0, 0.007, 0.008)
        C_s = np.full(len(hours), 0.0004)

        # --- Calculations ---
        u_T_min = ((T_out - (T_set + Delta_T)) / R_env + N_occ * q_person) / (rho_air * c_p * ((T_set + Delta_T) - T_s))
        u_T_max = ((T_out - (T_set - Delta_T)) / R_env + N_occ * q_person) / (rho_air * c_p * ((T_set - Delta_T) - T_s))
        u_W_max = (N_occ * g_w) / (rho_air * (W_max - W_s))
        u_CO2 = (N_occ * g_co2) / (C_max - C_s)

        # --- Flipped AHU Rule ---
        W_s_star = W_max - (g_w * (C_max - C_s)) / (rho_air * g_co2)
        u_W_max_calc = (N_occ * g_w) / (rho_air * (W_max - W_s_star))

        # --- Viability Check ---
        lo = np.maximum.reduce([u_T_min, u_W_max_calc, u_CO2])
        hi = np.minimum(u_T_max, u_max)

        is_viable = (lo <= hi) & (W_s_star >= 0.005)

        print(f"--- Daytime Viability (08:00 - 18:00) ---")
        print(f"Total hours: {len(hours)}")
        print(f"Viable hours: {np.sum(is_viable)} ({np.mean(is_viable)*100:.1f}%)")
        print(f"Critical Bottleneck: {'Humidity' if np.mean(u_W_max_calc > u_T_max) > 0.5 else 'Temperature'}")

    if __name__ == "__main__":
        verify_daytime_viability()
    return


if __name__ == "__main__":
    app.run()
