import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import urllib.request as req
    import plotly.io as pio
    import requests
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import io

    mo.Html(
        f"<style>{req.urlopen('https://raw.githubusercontent.com/janithcyapa/Engineering-Codex/refs/heads/main/shared_files/marimo/theme.css').read().decode()}</style>"
        )
    return go, io, make_subplots, mo, np, pd, requests


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
def _(go, io, make_subplots, np, pd, requests):

    # 1. Constants and SPACE1-1 Properties
    SPACE_PROPS = {
        "V_room": 239.247,
        "rho_air": 1.2,
        "Cp_air": 1006.0,
        "R_env_total": 1 / ( (1/0.0043) + (1/0.0023) + (1/0.0081) + (1/0.0199) + (1/0.0199) + (1/0.0045) ),
        "Q_int_per_person": 100,
        "G_w_per_person": 1.5e-5,
        "G_co2_per_person": 1.0e-5
    }

    LIMITS = {
        "T_min": 22.0,  "T_max": 24.0,
        "W_min": 0.004, "W_max": 0.012,
        "C_min": 400.0, "C_max": 1000.0,
        "u_max": 1.5
    }

    def calculate_all_bounds(T_out, N_occ, Q_equip, T_sup, W_sup, C_sup):
        """Calculates all 6 raw bounds for a given condition."""
        # Temperature
        Q_env_maxT = (T_out - LIMITS["T_max"]) / SPACE_PROPS["R_env_total"]
        u_T_low = max(0.0, (Q_env_maxT + Q_equip + (N_occ * SPACE_PROPS["Q_int_per_person"])) / (SPACE_PROPS["rho_air"] * SPACE_PROPS["Cp_air"] * (LIMITS["T_max"] - T_sup))) if LIMITS["T_max"] > T_sup else float('inf')
        u_T_hi = max(0.0, ((T_out - LIMITS["T_min"]) / SPACE_PROPS["R_env_total"] + Q_equip + (N_occ * SPACE_PROPS["Q_int_per_person"])) / (SPACE_PROPS["rho_air"] * SPACE_PROPS["Cp_air"] * (LIMITS["T_min"] - T_sup))) if LIMITS["T_min"] > T_sup else float('inf')

        # Humidity
        u_W_low = (N_occ * SPACE_PROPS["G_w_per_person"]) / (SPACE_PROPS["rho_air"] * (LIMITS["W_max"] - W_sup)) if W_sup < LIMITS["W_max"] else float('inf')
        u_W_hi = (N_occ * SPACE_PROPS["G_w_per_person"]) / (SPACE_PROPS["rho_air"] * (LIMITS["W_min"] - W_sup)) if W_sup < LIMITS["W_min"] else float('inf')

        # CO2
        u_C_low = (N_occ * SPACE_PROPS["G_co2_per_person"]) / (SPACE_PROPS["rho_air"] * (LIMITS["C_max"] - C_sup) * 1e-6) if C_sup < LIMITS["C_max"] else float('inf')
        u_C_hi = (N_occ * SPACE_PROPS["G_co2_per_person"]) / (SPACE_PROPS["rho_air"] * (LIMITS["C_min"] - C_sup) * 1e-6) if C_sup < LIMITS["C_min"] else float('inf')

        return [u_T_low, u_T_hi, u_W_low, u_W_hi, u_C_low, u_C_hi]

    def plot_viability_analysis(df_results, title_suffix=""):
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=("Airflow Feasibility (Overall)", "Temperature Bounds", "Humidity Bounds", "CO2 Bounds"),
            vertical_spacing=0.15, horizontal_spacing=0.1
        )

        # 1. Feasibility (Intersection)
        u_min = df_results[['u_T_low', 'u_W_low', 'u_C_low']].max(axis=1)
        u_max = df_results[['u_T_hi', 'u_W_hi', 'u_C_hi']].min(axis=1)
        fig.add_trace(go.Scatter(y=u_min, name='Max Min-Bound', line=dict(color='#ff4757')), row=1, col=1)
        fig.add_trace(go.Scatter(y=u_max, name='Min Max-Bound', line=dict(color='#2ed573')), row=1, col=1)
        fig.add_hline(y=LIMITS["u_max"], line_dash="dash", line_color="white", row=1, col=1)

        # 2. Subplots for specific bounds
        fig.add_trace(go.Scatter(y=df_results['u_T_low'], name='T_low', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(y=df_results['u_T_hi'], name='T_hi', line=dict(color='yellow')), row=2, col=1)
        fig.add_trace(go.Scatter(y=df_results['u_W_low'], name='W_low', line=dict(color='cyan')), row=2, col=2)
        fig.add_trace(go.Scatter(y=df_results['u_W_hi'], name='W_hi', line=dict(color='blue')), row=2, col=2)
        fig.add_trace(go.Scatter(y=df_results['u_C_low'], name='C_low', line=dict(color='lightgreen')), row=1, col=2)

        fig.update_layout(height=800, template="plotly_dark", title=f"Controllability: {title_suffix}")
        fig.show()

    # 2. Main Logic to Run
    def run_analysis(mode='random', csv_url=None):
        """
        Runs analysis. If mode is 'dataset', it fetches from the provided URL.
        """
        data_list = []

        if mode == 'random':
            for _ in range(500):
                # Same random generation logic...
                bounds = calculate_all_bounds(
                    np.random.normal(30, 4), np.random.randint(0, 15), 
                    np.random.uniform(100, 1500), np.random.uniform(14, 18), 
                    0.008, np.random.normal(600, 200)
                )
                data_list.append(bounds)

        elif mode == 'dataset':
            # Fetch CSV from URL
            response = requests.get(csv_url)
            # Use io.StringIO to treat the string as a file for pandas
            df = pd.read_csv(io.StringIO(response.text))

            for i in range(len(df)):
                # Calculate equipment load
                q = (df['plug_load_energy [kWh]'].iloc[i] + df['lighting_energy [kWh]'].iloc[i]) * 12000

                # Map dataset columns
                bounds = calculate_all_bounds(
                    df['dry_bulb_temp [Celsius]'].iloc[i], 
                    df['occupant_count [number]'].iloc[i], 
                    q, 
                    df['supply_air_temperature [Celsius]'].iloc[i], 
                    0.008, 
                    df['outdoor_co2 [ppm]'].iloc[i]
                )
                data_list.append(bounds)

        # Convert results to DataFrame and plot
        df_res = pd.DataFrame(data_list, columns=['u_T_low', 'u_T_hi', 'u_W_low', 'u_W_hi', 'u_C_low', 'u_C_hi'])
        max_mech = LIMITS["u_max"]
        success_T = (df_res['u_T_low'] <= np.minimum(df_res['u_T_hi'], max_mech))
        success_W = (np.maximum(df_res['u_T_low'], df_res['u_W_low']) <= np.minimum(df_res['u_T_hi'], np.minimum(df_res['u_W_hi'], max_mech)))
        success_C = (np.maximum(df_res['u_T_low'], df_res['u_C_low']) <= np.minimum(df_res['u_T_hi'], np.minimum(df_res['u_C_hi'], max_mech)))
        success_All = (np.maximum(df_res['u_T_low'], np.maximum(df_res['u_W_low'], df_res['u_C_low'])) <= 
                       np.minimum(df_res['u_T_hi'], np.minimum(df_res['u_W_hi'], np.minimum(df_res['u_C_hi'], max_mech))))

        print(f"\n--- {mode.upper()} Analysis Success Rates ---")
        print(f"Temperature Control Viability: {success_T.mean()*100:.2f}%")
        print(f"Temp + Humidity Viability:      {success_W.mean()*100:.2f}%")
        print(f"Temp + CO2 Viability:          {success_C.mean()*100:.2f}%")
        print(f"Full System Viability (All):   {success_All.mean()*100:.2f}%")
        plot_viability_analysis(df_res, mode.upper())


    # Run it
    # run_analysis(mode='random')
    # run_analysis(mode='dataset', csv_file='combined_Room1.csv')
    return (run_analysis,)


@app.cell
def _(run_analysis):
    run_analysis(mode='random')
    return


if __name__ == "__main__":
    app.run()
