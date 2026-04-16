import marimo

__generated_with = "0.23.0"
app = marimo.App(width="medium", auto_download=["ipynb", "html"])


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import urllib.request as req

    mo.Html(
        f"<style>{req.urlopen('https://raw.githubusercontent.com/janithcyapa/Engineering-Codex/refs/heads/main/shared_files/marimo/theme.css').read().decode()}</style>"
    )
    return (mo,)


@app.cell
def _():
    import schemdraw
    import schemdraw.elements as elm

    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Modeling a thermal zone using an RC (Resistor-Capacitor) model
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. The Fundamental Electrical Analogy
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Before diving into the specific variables, it is crucial to understand the mapping between the physical world and the electrical RC circuit.

    - **Potential** (Voltage, $V$): The driving force (e.g., Temperature difference, Concentration difference).
    - **Flow** (Current, $I$): The rate of transfer (e.g., Heat flux, Mass flow rate).
    - **Resistance** (Resistor, $R$): Resistance to flow (e.g., Insulation, Reciprocal of ventilation rate).
    - **Storage** (Capacitor, $C$): The capacity to store energy or mass (e.g., Thermal mass, Room air volume).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.1 Modeling Room Temperature (Thermal RC Model)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    A single room or thermal zone is typically modeled using a 1R1C, 2R1C, or 2R2C (or higher-order 3R2C) resistance-capacitance network, depending on the required accuracy and the importance of thermal mass dynamics. The 2-node model (2R2C) is a good compromise, it separates the fast dynamics of the room air from the slower response of the building's thermal mass (walls, floor, furniture, etc.).

    The Analogy:
    - Voltage $T$ ($^\circ C$ or $K$). Nodes represent the outdoor air ($T_{out}$), indoor air ($T_{in}$), and wall mass ($T_{w}$).
    - Current $Q$ ($W$): Heat flow.
    - Resistance $R$ ($K/W$): Thermal resistance of walls, windows, and infiltration.
    - Capacitor $C$ ($J/K$): Thermal capacitance of the indoor air and internal mass.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.image(
                src="https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/main/Images/2R2C_Temp_Model.jpg",
                alt="2R2C Thermal RC Network"
            ),
            mo.md("<div style='text-align: center; font-style: italic;'><b>Figure 01:</b> 2R2C Grey-Box Thermal Model</div>")
        ],
        align="center"
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The Governing Equation

    If we treat the room air and light furniture as a single node, the first-order differential equation is

    $$C_{air} \frac{dT_{in}}{dt} = \sum \frac{T_{out} - T_{in}}{R_{env}} + \frac{T_{m} - T_{in}}{R_{int}} + Q_{int} + Q_{solar,conv} +  Q_{s} + Q_{vent} + Q_{inf} \tag{A}$$

    For the mass node,
    $$ C_{mass} \frac{dT_m}{dt} = \frac{T_{in} - T_m}{R_{int}} + Q_{solar,rad} \tag{B}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Notes on the Model

    - This 2-node setup captures both the quick response of room air temperature and the inertial effect of thermal mass, making it more accurate than a pure 1C lumped model for dynamic simulations, model predictive control (MPC), or overheating risk assessment.
    - In practice, parameters (R_env, R_int, C_air, C_mass) can be calculated from building geometry and material properties or identified from measured data.
    For even higher accuracy, models are extended to 3R2C or the full 5R1C from ISO 13790.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.2 Modeling Humidity
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Humidity can be modeled similarly, though it is usually treated as a mass balance. In an RC framework, it is generally a 1C model (just the room air), unless you want to model the moisture absorbed by walls and furniture (hygroscopic buffering), which would require additional R and C components.

    The Analogy:
    - Voltage $W$ ($kg_{water}/kg_{dry\_air}$): Humidity ratio (potential).
    - Current Source $G_{w}$ ($kg_{water}/s$): Internal moisture generation rate.
    - Resistance $R$ ($s/kg_{dry\_air}$): Resistance to moisture flow via advection.
    - Capacitor $M_{air}$ ($kg_{dry\_air}$): Moisture storage capacity of the room.

    $R = \frac{1}{\dot{m}_{dry\_air}}$ - So we use $\dot{m}_{dry\_air}$ in governing equation.
    $M_{air} = \rho_{dry\_air} \cdot V_{room}$ (where $V_{room}$ is the volume).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.image(
                src="https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/main/Images/Humidity_model.jpg",
                alt="1R1C Humidity RC Network"
            ),
            mo.md("<div style='text-align: center; font-style: italic;'><b>Figure 01:</b> 1R1C Humidity Model</div>")
        ],
        align="center"
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The Governing Equation (Lumped Air Node):

    $$M_{air} \frac{dW_{in}}{dt} = G_{w,int} + \dot{m}_{inf}(W_{out} - W_{in}) + \dot{m}_{s}(W_s - W_{in}) \tag{C}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1.3 Modeling $CO_2$ Concentration (Mass Transfer Model)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    $CO_2$ modeling is the most straightforward of the three. Because $CO_2$ does not absorb into walls or furniture like moisture or heat, it is almost strictly a 1C model (pure mass balance). The "capacitor" is simply the volume of the room.

    The Analogy:
    - Voltage $C$  ($mg/m^3$): $CO_2$ concentration.
    - Current $G_{co2}$ ($mg/s$): $CO_2$ generation rate.
    - Resistance $R$ : The inverse of the ventilation rate.
    - Capacitor $V_{room}$ ($m^3$) : The volume of the room.

    $R$ defined as $R = \frac{1}{\dot{V}}$. Therefore we use $\dot{V}$ in governing equation.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.image(
                src="https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/main/Images/CO2_model.jpg",
                alt="1R1C CO2 RC Network"
            ),
            mo.md("<div style='text-align: center; font-style: italic;'><b>Figure 01:</b> 1R1C CO2 Model</div>")
        ],
        align="center"
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The Governing Equation:
    $$V_{room} \frac{dC_{in}}{dt} = G_{co2,int} + \dot{V}_{inf}(C_{out} - C_{in}) + \dot{V}_{s}(C_{s} - C_{in}) \tag{D}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Dynamic System Derivation For a Zone
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2.1 Multi-Room **xR2C** Thermal Model
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    In a multizone thermal node there is a coupling effect. Which is not included in the standard 2R2C or any other static modeling method. So I propose this dynamic **xR2C** model which generated based on the building geometry.

    - **x **= number of resistances (K/W) → heat flow paths (envelope, internal partitions, convection/radiation, ventilation).


    **Per-zone core structure**

    Each thermal zone is represented by its own local RC sub-network (typically a 2R2C structure with an air node $T_{in,i}$ and a mass node $T_{m,i}$, connected by resistances $R_{\text{env},i}$ and $R_{\text{int},i}$, and capacitances $C_{\text{air},i}$ and $C_{\text{mass},i}$.

    Geometry-dependent dynamic coupling

    Additional resistances (or conductances) are introduced between zones to model inter-zone heat transfer. These coupling terms ($R_{\text{couple},ij}$) are not fixed constants but are dynamically derived from the building’s physical layout.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.image(
                src="https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/main/Images/xR2C_Temp_Model.jpg",
                alt="xR2C Thermal RC Network"
            ),
            mo.md("<div style='text-align: center; font-style: italic;'><b>Figure 01:</b> xR2C Grey-Box Thermal Model</div>")
        ],
        align="center"
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    **Governing Differential Equations**

    For each zone i = 1, 2, ..., N (where N is the number of zones),

    Air node equation (for $T_{in,i}$):

    $$C_{\text{air},i} \frac{dT_{in,i}}{dt} =
    \frac{T_{\text{out}} - T_{in,i}}{R_{\text{env,external},i}} +
    \sum_{j \in \text{adj}(i)} \frac{T_{in,j} - T_{in,i}}{R_{\text{env,couple},ij}} +
    \frac{T_{m,i} - T_{in,i}}{R_{\text{int},i}} +
    \sum_{j \in \text{adj}(i)} \dot{m}_{ij} c_p (T_{in,j}- T_{in,i}) +
    Q_{\text{int},i} + Q_{\text{solar,conv},i} + Q_{s,i} + Q_{\text{vent},i} + Q_{\text{inf},i} \tag{1}$$

    Mass node equation (for $T_{m,i}$):
    $$C_{\text{mass},i} \frac{dT_{m,i}}{dt} = \frac{T_{in,i} - T_{m,i}}{R_{\text{int},i}} + Q_{\text{solar,rad},i} + \sum_{j \in \text{adj}(i)} \frac{T_{m,j} - T_{m,i}}{R_{\text{couple,ms},ij}} \tag{2}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    In a similar way, the dynamics of humidity and $CO_2$ can be definedd using 1R1C model as follow,

    $$M_{air,i} \frac{dW_{in,i}}{dt} =
    G_{w,int,i} + \dot{m}_{inf,i}(W_{out} - W_{in,i}) +
    \sum_{j \in \text{adj}(i)} \dot{m}_{mix,ij}(W_{in,j} - W_{in,i}) +
    \dot{m}_{s,i}(W_s - W_{in,i}) \tag{3}$$

    $$V_{room,i} \frac{dC_{in,i}}{dt} = G_{co2,int,i} + \dot{V}_{inf,i}(C_{out} - C_{in,i}) +
    \sum_{j \in \text{adj}(i)} \dot{V}_{mix,ij}(C_{in,j} - C_{in,i}) +
    \dot{V}_{s,i}(C_{s} - C_{in,i}) \tag{4}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2.2 Estimations vs. Unmeasured Disturbances

    To make the equations computable, divide the non-controlble terms into two distinct groups, Heuristic Estimations (which act as feed-forward knowns) and Lumped Disturbances (which an observer algorithm will dynamically estimate).

    **Heuristic Estimations (Occupancy & Equipment)**

    If the number of occupants ($N_{occ,i}$) is known by sheduling or estimation, the internal generation terms can be calculated using standard ASHRAE metabolic rates,

    Sensible Heat:
    $$Q_{int,i} \approx N_{occ,i}⋅q_{person} + Q_{equip} \tag{5(a)}$$

    Latent Moisture:
    $$G_{w,int,i} \approx N_{occ,i} ⋅g_{w,person} \tag{5(b)}$$

    CO2 Generation:
    $$G_{co2,int,i} \approx N_{occ,i}⋅g_{co2,person} \tag{5(c)}$$

    Additionally, envelope infiltration is estimated as a constant based on the building's historical Air Changes per Hour (ACH):
    $$ \dot{m}_{inf,i} \approx \frac{ACH \ . \ V_{room,i} \ . \ \rho_{air}}{3600}$$
    But, to make model robust include them in disturbance.

    **The Lumped Disturbance Vector ($d_i$)**

    All chaotic, unmeasurable inter-zone dynamics and unpredictable environmental factors are stripped from the main equations and lumped into unified disturbance variables. A Disturbance Observer (DOB) can be use to estimate these values in real-time.

    $$ d_{T,i} = Q_{solar,i} + Q_{\text{inf},i} + \sum \dot{m}_{ij} c_p (T_{in,j} - T_{in,i}) + \text{unmodeled conduction} \tag{6(a)}$$

    $$ d_{W,i} = \dot{m}_{inf,i}(W_{out} - W_{in,i}) + \sum \dot{m}_{mix,ij} (W_{in,j} - W_{in,i}) + \text{unmodeled moisture leaks} \tag{6(b)}$$

    $$ d_{C,i} = \dot{V}_{inf,i}(C_{out} - C_{in,i}) + \sum \dot{V}_{mix,ij} (C_{in,j} - C_{in,i}) + \text{unmodeled } CO_2 \text{ leaks} \tag{6(c)}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Considering equation(1-4 and 5,6) and the AHU setup in Lab,
    - We can either include coupling effect as disturbance or for now we will keep it to check weather we can utilize it decentralized control algorithum.
    - $R_{env,ext}$, $R_{env,couple,ij}$, $R_{int}$, $C_{air}$, $C_{mass}$, $C_{m}$ and $V_{room}$ are derived constants from Derived from IDF.
    - Considering the AHU setup where air mixing is done at AHU, $Q_{vent}$ is included in $Q_s$ and that can be written based on supply sensor measurements.
    - $Q_{solar,i}$ , $Q_{\text{inf},i}$ and interzone air exchange terms are unmeasurable. So they are included as a lumped disturbance.
    - Ommit $Q_{solar,rad}$ and coupling terms from mass node, because direct mass-node disturbances and solid-to-solid conduction are unobservable with standard sensors. Ignoring them is acceptable because their physical impact is indirectly captured and compensated for by the air-node disturbance observer ($d_{T,i}).
    - $T_{m,i}$ is treated as an unobservable (hidden) state. Utilize a State Observer to estimate that. At simulation env of energy plus this is observable for validation.
    -

    $$C_{\text{air},i} \ \dot{T}_{in,i}=
    \frac{T_{\text{out}} - T_{in,i}}{R_{\text{env,external},i}} +
    \sum_{j \in \text{adj}(i)} \frac{T_{in,j} - T_{in,i}}{R_{\text{env,couple},ij}} +
    \frac{T_{m,i} - T_{in,i}}{R_{\text{int},i}} +
    (N_{occ,i}⋅q_{person} + Q_{equip})+
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
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2.2 State Reprentation
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    1. Vector Definitions For a single zone i

    State Vector ($x_i$):

    $$x_i = \begin{bmatrix}
    T_{in,i} \\
    T_{m,i} \\
    W_{in,i} \\
    C_{in,i}
    \end{bmatrix}$$


    Control Input ($u_i$): Taking the VAV box damper position to represent volumetric flow rate ($m^3/s$)
    $$u_i=\dot{V}_{s,i}$$

    Time-Varying Parameter Vector ($p_i$):

    $$p_i = \begin{bmatrix}
    N_{occ,i} \\
    Q_{equip,i}
    \end{bmatrix}$$

    Lumped Disturbance Vector ($d_i$):

    $$d_i = \begin{bmatrix}
    d_{T,i} \\
    d_{W,i} \\
    d_{C,i}
    \end{bmatrix}$$

    AHU Supply Parameters ($S$):

    $$S = \begin{bmatrix}
    T_{s} \\
    W_{s} \\
    C_{s}
    \end{bmatrix}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    2. State-Space Model

    The system dynamics can be written in the standard nonlinear form:
    $$\dot{x_i} = f(x_i,p_i,d_i) + g(x_i,S)u_i$$


    Dynamics of the system ($f(x_i, p_i, d_i)$):

    $$f(x_i, p_i, d_i) = \begin{bmatrix}
    \frac{1}{C_{air,i}} \left( \frac{T_{out} - T_{in,i}}{R_{env,external,i}} + \sum_{j \in adj(i)} \frac{T_{in,j} - T_{in,i}}{R_{env,couple,ij}} + \frac{T_{m,i} - T_{in,i}}{R_{int,i}} + p_{1,i} q_{person} + p_{2,i} + d_{T,i} \right) \\
    \frac{1}{C_{mass,i}} \left( \frac{T_{in,i} - T_{m,i}}{R_{int,i}} \right) \\
    \frac{1}{M_{air,i}} \left( p_{1,i} g_{w,person} + d_{W,i} \right) \\
    \frac{1}{V_{room,i}} \left( p_{1,i} g_{co2,person} + d_{C,i} \right)
    \end{bmatrix}$$

    The Control Authority ($g(x_i,S)$):

    $$g(x_i, S) = \begin{bmatrix}
    \frac{\rho_{air} c_p}{C_{air,i}} (T_s - T_{in,i}) \\
    0 \\
    \frac{\rho_{air}}{M_{air,i}} (W_s - W_{in,i}) \\
    \frac{1}{V_{room,i}} (C_s - C_{in,i})
    \end{bmatrix}$$

    Output Equation:

    $$y = \begin{bmatrix}
    1 & 0 & 0 & 0 \\
    0 & 0 & 1 & 0 \\
    0 & 0 & 0 & 1
    \end{bmatrix}
     x_i$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Appendix
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Appendix: Nomenclature & Variable Definitions

    **State & Output Variables**
    * $x_i$: State vector of zone $i$
    * $y_i$: Output measurement vector of zone $i$
    * $T_{in,i}$: Indoor air temperature of zone $i$ $[K]$
    * $T_{m,i}$: Temperature of the building's thermal mass in zone $i$ $[K]$
    * $W_{in,i}$: Indoor humidity ratio of zone $i$ $[kg_w/kg_{da}]$
    * $C_{in,i}$: Indoor $CO_2$ concentration of zone $i$ $[mg/m^3]$

    **Control & Supply Parameters (AHU)**
    * $u_i$: Control input for zone $i$, representing $\dot{V}_{s,i}$ $[m^3/s]$
    * $\dot{V}_{s,i}$: Volumetric flow rate of supply air from the VAV box to zone $i$ $[m^3/s]$
    * $S$: AHU supply parameter vector
    * $T_s$: Supply air temperature $[K]$
    * $W_s$: Supply air humidity ratio $[kg_w/kg_{da}]$
    * $C_s$: Supply air $CO_2$ concentration $[mg/m^3]$

    **Physical Constants & Geometric Parameters**
    * $C_{air,i}$: Thermal capacitance of the room's air volume $[J/K]$
    * $C_{mass,i}$: Thermal capacitance of the building's solid mass $[J/K]$
    * $M_{air,i}$: Total mass of dry air inside the room $[kg_{da}]$
    * $V_{room,i}$: Total volume of the room $[m^3]$
    * $R_{env,external,i}$: Thermal resistance of the external building envelope $[K/W]$
    * $R_{env,couple,ij}$: Inter-zone coupling thermal resistance between zone $i$ and $j$ $[K/W]$
    * $R_{int,i}$: Internal thermal resistance between the indoor air and building mass $[K/W]$
    * $\rho_{air}$: Density of the air $[kg/m^3]$
    * $c_p$: Specific heat capacity of the air $[J/(kg \cdot K)]$

    **Heuristic Estimations (Time-Varying Parameters)**
    * $p_i$: Time-varying parameter vector for heuristic estimations
    * $p_{1,i}$: Estimated number of occupants ($N_{occ,i}$)
    * $p_{2,i}$: Estimated equipment sensible heat gain ($Q_{equip,i}$) $[W]$
    * $q_{person}$: Standard sensible heat generation per occupant $[W/person]$
    * $g_{w,person}$: Standard moisture generation per occupant $[kg_w/(s \cdot person)]$
    * $g_{co2,person}$: Standard $CO_2$ generation per occupant $[mg/(s \cdot person)]$

    **Unmeasured Lumped Disturbances**
    * $d_i$: Lumped disturbance vector estimated by the Disturbance Observer (DOB)
    * $d_{T,i}$: Lumped thermal disturbance (includes unmeasurable solar radiation, infiltration, and unmodeled conduction) $[W]$
    * $d_{W,i}$: Lumped moisture disturbance (includes infiltration and unmodeled moisture leaks) $[kg_w/s]$
    * $d_{C,i}$: Lumped $CO_2$ disturbance (includes infiltration and unmodeled $CO_2$ leaks) $[mg/s]$
    """)
    return


if __name__ == "__main__":
    app.run()
