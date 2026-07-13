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
    return mo, pio, requests


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    [🏠 Home](https://janithcyapa.github.io/DHCA-Framework/)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # State Estimation Using Extended Kalman Filter (EKF)
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
    ## EKF Derivation
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 1. Define the Augmented State Vector
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    To allows the filter to estimate the core dynamics, the thermal/moisture disturbances, and the occupancy simultaneously a 7-state augmented vector was defined as follow. Note that it's assumed that unmodeled $CO_2$ leaks $d_C \approx 0$ so the filter can use the $CO_2$ residual entirely to estimate $N_{occ,i}$.

    Augmented state vector:

    $$ x = \begin{bmatrix} x_1 \\ x_2 \\ x_3 \\ x_4 \\ x_5 \\ x_6 \\ x_7 \end{bmatrix} = \begin{bmatrix} T_{in} \\ T_{m} \\ W_{in} \\ C_{in} \\ d_{T} \\ d_{W} \\ N_{occ} \end{bmatrix} $$

    Control input:

    $$u = \dot{V}_{s,i}$$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2. The Continuous Non-Linear Dynamics ($f(x,u)$)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    We can re-write the dynamic equations in terms of $x$. Assume the augmented states ($x_5,x_6,x_7$) have zero derivatives (they are constants driven by process noise)

    $$ f_1 = \dot{x}_1 = \frac{1}{C_{air}} \left( \frac{T_{out} - x_1}{R_{ext}} + \sum \frac{T_{in,j} - x_1}{R_{couple}} + \frac{x_2 - x_1}{R_{int}} + x_7 \cdot q_{person} + \rho_{air} c_p u(T_s - x_1) + x_5 \right) $$

    $$ f_2 = \dot{x}_2 = \frac{x_1 - x_2}{C_{mass} R_{int}} $$

    $$ f_3 = \dot{x}_3 = \frac{1}{M_{air}} (x_7 \cdot g_{w,person} + \rho_{air} u(W_s - x_3) + x_6) $$

    $$ f_4 = \dot{x}_4 = \frac{1}{V_{room}} (x_7 \cdot g_{co2,person} + u(C_s - x_4)) $$

    $$ f_5 = \dot{x}_5 = 0 $$

    $$ f_6 = \dot{x}_6 = 0 $$

    $$ f_7 = \dot{x}_7 = 0 $$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 3. Calculate the Continuous Jacobian Matrix (F)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Since there are only bilinear non-linearities in the simplified model Jacobian matrix $F =\frac{\partial f}{\partial x}$ are quite simple. That is one of the reasons to choose EKF over UKF.

    $$ F = \begin{bmatrix}
    \frac{1}{C_{air}} \left( -\frac{1}{R_{ext}} - \sum \frac{1}{R_{couple}} - \frac{1}{R_{int}} - \rho_{air} c_p u \right) & \frac{1}{C_{air} R_{int}} & 0 & 0 & \frac{1}{C_{air}} & 0 & \frac{q_{person}}{C_{air}} \\[1.5ex]
    \frac{1}{C_{mass} R_{int}} & -\frac{1}{C_{mass} R_{int}} & 0 & 0 & 0 & 0 & 0 \\[1.5ex]
    0 & 0 & -\frac{\rho_{air} u}{M_{air}} & 0 & 0 & \frac{1}{M_{air}} & \frac{g_{w,person}}{M_{air}} \\[1.5ex]
    0 & 0 & 0 & -\frac{u}{V_{room}} & 0 & 0 & \frac{g_{co2,person}}{V_{room,i}} \\[1.5ex]
    0 & 0 & 0 & 0 & 0 & 0 & 0 \\[1.5ex]
    0 & 0 & 0 & 0 & 0 & 0 & 0 \\[1.5ex]
    0 & 0 & 0 & 0 & 0 & 0 & 0
    \end{bmatrix} $$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 4. Discretization
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    To move from continuous time ($\dot{x}$) to the discrete time steps of digital control implementation where loop runs at specific step time ($\Delta t$) use the first-order Euler approximation.

    Discrete State Transition Matrix :

    $$\Phi_k = I + F_k \ \Delta t$$

    $$ \Phi_k = \begin{bmatrix}
    1 + F_{1,1}\Delta t & F_{1,2}\Delta t & 0 & 0 & \frac{\Delta t}{C_{air}} & 0 & F_{1,7}\Delta t \\
    F_{2,1}\Delta t & 1 + F_{2,2}\Delta t & 0 & 0 & 0 & 0 & 0 \\
    0 & 0 & 1 + F_{3,3}\Delta t & 0 & 0 & \frac{\Delta t}{M_{air}} & F_{3,7}\Delta t \\
    0 & 0 & 0 & 1 + F_{4,4}\Delta t & 0 & 0 & F_{4,7}\Delta t \\
    0 & 0 & 0 & 0 & 1 & 0 & 0 \\
    0 & 0 & 0 & 0 & 0 & 1 & 0 \\
    0 & 0 & 0 & 0 & 0 & 0 & 1
    \end{bmatrix} $$

    $$ \ $$

    $$ \Phi_k = \begin{bmatrix}
    1 + \frac{\Delta t}{C_{air}} \left( -\frac{1}{R_{ext}} - \sum \frac{1}{R_{couple}} - \frac{1}{R_{int}} - \rho_{air} c_p u \right) & \frac{\Delta t}{C_{air} R_{int}} & 0 & 0 & \frac{\Delta t}{C_{air}} & 0 & \frac{q_{person} \Delta t}{C_{air}} \\[1.5ex]
    \frac{\Delta t}{C_{mass} R_{int}} & 1 - \frac{\Delta t}{C_{mass} R_{int}} & 0 & 0 & 0 & 0 & 0 \\[1.5ex]
    0 & 0 & 1 - \frac{\rho_{air} u \Delta t}{M_{air}} & 0 & 0 & \frac{\Delta t}{M_{air}} & \frac{g_{w,person} \Delta t}{M_{air}} \\[1.5ex]
    0 & 0 & 0 & 1 - \frac{u \Delta t}{V_{room}} & 0 & 0 & \frac{g_{co2,person} \Delta t}{V_{room,i}} \\[1.5ex]
    0 & 0 & 0 & 0 & 1 & 0 & 0 \\[1.5ex]
    0 & 0 & 0 & 0 & 0 & 1 & 0 \\[1.5ex]
    0 & 0 & 0 & 0 & 0 & 0 & 1
    \end{bmatrix} $$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 5. Defining the Noise Matrices (Q and R)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The covariance matrices are used to tune the Filter.

    **Process Noise Covariance (Q)**

    This 7×7 matrix represents how much we "trust" the mathematical model. Since cross-correlation is considerably negligible, this is a defined as a diagonal matrix for simplicity.

    $$ Q = \mathrm{diag}([q_{T_{in}}, q_{T_m}, q_{W_{in}}, q_{C_{in}}, q_{d_T}, q_{d_W}, q_{N_{occ}}]) $$

    Intuition:
    * Make $q_{T_{in}}$ and $q_{C_{in}}$ very small since the physics model is good.
    * Make $q_{d_T}$ and $q_{N_{occ}}$ relatively larger.


    **Measurement Noise Covariance (R)**
    This 3×3 matrix represents how much we trust sensors. You can get these directly from the variance of your sensor datasheets.

    $$ R = \begin{bmatrix} r_T & 0 & 0 \\ 0 & r_W & 0 \\ 0 & 0 & r_C \end{bmatrix} $$

    Based on sensor datasheets,
    static version for CO2 -> 1000ppm
    $$ R = \begin{bmatrix} 0.09 & 0 & 0 \\ 0 & 4.0 & 0 \\ 0 & 0 & 14,400\end{bmatrix} $$

    Our measurement vector,
    $$z_k =  \begin{bmatrix} T_{in,mes} & W_{in,mes} & C_{in,mes} \end{bmatrix}^T$$
    Therefore, measurement matrix H is,
    $$H = \begin{bmatrix} 1&0&0&0&0&0&0 \\0&0&1&0&0&0&0\\0&0&0&1&0&0&0 \end{bmatrix} $$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 6. The EKF Algorithm
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ###### **Phase 1**: Predict (A Priori)

    1.1 Predict the State ($\hat{x}_{k∣k−1}$)

    $$ \hat{x}_{1,k|k-1} = \hat{x}_{1,k-1|k-1} + f_1(\hat{x}_{k-1|k-1}, u_{k-1}) \cdot \Delta t $$

    $$ \hat{x}_{2,k|k-1} = \hat{x}_{2,k-1|k-1} + f_2(\hat{x}_{k-1|k-1}, u_{k-1}) \cdot \Delta t $$

    $$ \hat{x}_{3,k|k-1} = \hat{x}_{3,k-1|k-1} + f_3(\hat{x}_{k-1|k-1}, u_{k-1}) \cdot \Delta t $$

    $$ \hat{x}_{4,k|k-1} = \hat{x}_{4,k-1|k-1} + f_4(\hat{x}_{k-1|k-1}, u_{k-1}) \cdot \Delta t $$

    $$ \hat{x}_{5,k|k-1} = \hat{x}_{5,k-1|k-1} $$

    $$ \hat{x}_{6,k|k-1} = \hat{x}_{6,k-1|k-1} $$

    $$ \hat{x}_{7,k|k-1} = \hat{x}_{7,k-1|k-1} $$

    1.2  Predict the Covariance ($P_{k|k-1}$)
    $$ P_{k|k-1} = \Phi_k P_{k-1|k-1} \Phi_k^T + Q $$
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ###### **Phase 2**: Update (A Posteriori)

    2.1 Calculate the Innovation ($y_k$)
    $$ y_k = Z - H \hat{x}_{k|k-1}  $$
    $$ y_k = \begin{bmatrix} T_{in,mes} - \hat{x}_{1,k|k-1} \\ W_{in,mes} - \hat{x}_{3,k|k-1} \\ C_{in,mes} - \hat{x}_{4,k|k-1} \end{bmatrix} $$

    2.2 Calculate the Innovation Covariance ($S_k$)

    $$ S_k = H P_{k|k-1} H^T +R$$

    Because $H$ is just extracting specific states, $HPH^T$ simply extracts the intersection of rows 1, 3, 4 and columns 1, 3, 4 from your 7×7 $P$ matrix.

    $$ S_k = \begin{bmatrix}
    P_{1,1} + r_T & P_{1,3} & P_{1,4} \\
    P_{3,1} & P_{3,3} + r_W & P_{3,4} \\
    P_{4,1} & P_{4,3} & P_{4,4} + r_C
    \end{bmatrix}_{k|k-1} $$

    2.3 Calculate the Kalman Gain ($K_k$)

    $$ K_k = P_{k|k-1} H^T S_k^{-1}$$

    $P_{k|k-1} H^T$ simply extracts columns 1, 3, and 4 from your 7×7 $P$ matrix.

    $$ K_k = \begin{bmatrix} P_{1,1} & P_{1,3} & P_{1,4} \\ P_{2,1} & P_{2,3} & P_{2,4} \\ \vdots & \vdots & \vdots \\ P_{7,1} & P_{7,3} & P_{7,4} \end{bmatrix}_{k|k-1} \times S_k^{-1} $$

    2.4 Update the State ($\hat{x}_{k∣k}$)

    $$ \hat{x}_{k|k} = \hat{x}_{k|k-1} + K_k y_k $$

    2.5 Update the Covariance ($P_{k|k}$)

    $$P_{k|k} = (I - K_k H) P_{k|k-1}$$

    $$ P_{k|k} = P_{k|k-1} - K_k (H P_{k|k-1}) $$

    Where $H P_{k|k-1}$ is just the $3 \times 7$ matrix formed by extracting rows **1**, **3**, and **4** from $P_{k|k-1}$.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Validation Using EnergyPlus
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### EKF State and Disturbance Estimation Results

    To enable real-time decentralized control, an Extended Kalman Filter (EKF) was implemented to estimate hidden structural states ($T_m$), unmeasured disturbances, and dynamic occupancy levels ($N_{occ}$) based on available sensor data.

    | State / Parameter | Unit | MAE | Max Error | RMSE | Final Step Error |
    | :--- | :---: | ---: | ---: | ---: | ---: |
    | Zone Air Temp ($T_{in}$) | °C | 0.0005 | 0.0057 | 0.0007 | 0.0000 |
    | Thermal Mass Temp ($T_m$) | °C | 0.8608 | 2.6883 | 1.0261 | -0.2892 |
    | Humidity Ratio ($W_{in}$) | kg/kg | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
    | CO$_2$ Concentration ($C_{in}$) | ppm | 41.2183 | 170.6253 | 50.3283 | 3.6997 |
    | Occupancy ($N_{occ}$) | count | 1.5425 | 6.5058 | 1.8686 | 2.8551 |

    **Commentary on Estimation Performance:**

    The EKF successfully reconstructs the full system state and hidden parameters, providing a reliable foundation for feedback control.

    * **Observable States:** The filter tightly bounds the measured states, driving the estimation errors for zone air temperature ($T_{in}$) and humidity ratio ($W_{in}$) to near zero.
    * **Hidden Parameters ($T_m$):** The thermal mass temperature estimate shows a Mean Absolute Error (MAE) of 0.86°C. The slight increase in error compared to the open-loop model is expected; in the EKF formulation, $T_m$ often absorbs the structural thermal unmodeled dynamics and external heat disturbances ($d_T$) to keep the primary observable state ($T_{in}$) highly accurate.
    * **Occupancy Estimation ($N_{occ}$):** The EKF demonstrates excellent performance in estimating the unmeasured occupancy, maintaining an MAE of ~1.5 people. Accurately tracking a discrete human presence using continuous environmental data (primarily $C_{in}$ and $T_{in}$ generation) is a strong validation of the filter's tuning and covariance matrices.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### EnergyPlus simulation (with sensor noice) vs EKF Estimation
    """)
    return


@app.cell(hide_code=True)
def _(pio, requests):
    url = "https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/refs/heads/main/Results/Basic/EKF_Validation.json"
    response = requests.get(url)
    fig = pio.from_json(response.text)
    fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### General System Data
    """)
    return


@app.cell(hide_code=True)
def _(pio, requests):
    url_1 = "https://raw.githubusercontent.com/janithcyapa/DHCA-Framework/refs/heads/main/Results/Basic/System_Data.json"
    response_1 = requests.get(url_1)
    fig_1 = pio.from_json(response_1.text)
    fig_1
    return


if __name__ == "__main__":
    app.run()
