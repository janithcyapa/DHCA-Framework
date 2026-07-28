
**Layer 1** (per zone): EKF + two-stage QP flow command, then ideal supply ask.
**Layer 2** (central): AHU coordinator QP arbitrates all zone asks into physical setpoints.

## Layer 1: Zone Controller

### Stage 1 MPC Solver (Flow Rate)

Optimizes VAV mass flow over an N-step horizon.

**Inputs**

|Name|Description|Source|
|---|---|---|
|Zone Physical States|State estimates ($T_{in}, T_m, W_{in}, C_{in}$)|EKF|
|Zone Setpoints|References/bounds ($T_{ref}, T_{max}, T_{min}, W_{max}, W_{min}, C_{max}$)|System Definitions|
|AHU Supply States|Supply condition ($T_s, W_s, C_s$)|System State|
|Previous Input|Last commanded flow ($u_{prev}$)|Internal State|

**Outputs**

|Name|Description|Variable|
|---|---|---|
|VAV Flow Command|Smoothed, clipped mass flow to VAV damper|$u_{cmd}$|

**Constraints**

|Name|Type|Target|Description|
|---|---|---|---|
|Temperature Centering|Objective Penalty (Quadratic)|$u$|Penalizes deviation from $T_{ref}$|
|Humidity Centering|Objective Penalty (Quadratic)|$u$|Penalizes deviation from $(W_{max}+W_{min})/2$|
|Slew Rate Penalty|Objective Penalty (Quadratic)|$u$|Penalizes $\Delta u$ step-to-step|
|Temperature Comfort Band|Linear Ineq. (Soft)|$u, \epsilon_T$|Keeps $T_{in}\in[T_{min},T_{max}]$, softly|
|Humidity Comfort Band|Linear Ineq. (Soft)|$u, \epsilon_W$|Keeps $W_{in}\in[W_{min},W_{max}]$, softly|
|CO2 Safety Threshold|Linear Ineq. (Soft)|$u, \epsilon_C$|Caps $C_{in}$ at $C_{max}$, softly|
|Flow Rate Limits|Box (Hard)|$u$|$u_{min}\le u\le u_{max}$|
|Flow Slew Rate|Linear Ineq. (Hard)|$u$|$\lvert u-u_{prev}\rvert\le \Delta u_{max}$|
|Slack Non-Negativity|Box (Hard)|$\epsilon_T,\epsilon_W,\epsilon_C$|Slacks $\ge 0$|

_Fallback: if OSQP fails, a proportional controller sets flow from T/CO2/humidity error._

### Stage 2 Reverse QP Solver (Ideal Ask)

With $u_{cmd}$ fixed, solves for the mathematically optimal AHU supply ask fixing $u$ turns the bilinear $u\cdot T_s$ coupling linear.

**Inputs**

|Name|Description|Source|
|---|---|---|
|Fixed Flow|Stage 1's flow command, pre mass-conversion ($u_{cmd}$)|Stage 1 Output|
|Zone Physical States|Current estimates ($T_{in}, T_m, W_{in}, C_{in}$)|EKF|
|Dynamic Neutral Targets|Baseline to avoid over-conditioning: $T_{neutral}, W_{neutral}$ from an estimated mixed-air blend; $C_{neutral}$ = current zone CO2|System State|

**Outputs**

| Name                 | Description                                    | Variable              |
| -------------------- | ---------------------------------------------- | --------------------- |
| Ideal Supply Request | Optimal supply T/humidity/CO2 asked of the AHU | $T_s^*, W_s^*, C_s^*$ |
| Desperation Index    | Commanded flow / max flow rate ratio           | $S_i$                 |

**Constraints**

|Name|Type|Target|Description|
|---|---|---|---|
|Supply Temp Centering|Objective Penalty (Quadratic)|$T_s$|Minimizes deviation from dynamic $T_{neutral}$|
|Supply Hum Centering|Objective Penalty (Quadratic)|$W_s$|Minimizes deviation from dynamic $W_{neutral}$|
|Supply CO2 Centering|Objective Penalty (Quadratic)|$C_s$|Minimizes deviation from dynamic $C_{neutral}$|
|Projected Temp Bounds|Linear Ineq. (Soft)|$T_s, \epsilon_T$|Keeps zone temp in bounds given fixed $u_{cmd}$|
|Projected Hum Bounds|Linear Ineq. (Soft)|$W_s, \epsilon_W$|Keeps zone humidity in bounds given fixed $u_{cmd}$|
|Projected CO2 Bounds|Linear Ineq. (Soft)|$C_s, \epsilon_C$|Keeps zone CO2 below max given fixed $u_{cmd}$|
|AHU Supply Physical Limits|Box (Hard)|$T_s, W_s, C_s$|Coil capability bounds|
|Slack Non-Negativity|Box (Hard)|$\epsilon_T,\epsilon_W,\epsilon_C$|Slacks $\ge 0$|

_Fallback: proportional/bang-bang heuristic ask if this QP fails._

## Layer 2: AHU Coordinator

Arbitrates all zone asks into one set of physical AHU setpoints.

**Inputs**

| Name                     | Description                                                                                            | Source          |
| ------------------------ | ------------------------------------------------------------------------------------------------------ | --------------- |
| Aggregated Zone Requests | Per-zone dict ($T_s^*, W_s^*, C_s^*, u_{cmd}, S_i$)                                                    | Layer 1 Outputs |
| System Temperatures      | $T_{out}, T_{ret}$; fan-outlet & heating-coil-outlet temps (update an internal fan heat-rise estimate) | System State    |
| System CO2               | $C_{out}, C_{ret}$                                                                                     | System State    |
| Previous Setpoints       | Prior $T_{cc}, T_{hc}, \gamma$, for smoothed hardware transitions                                      | Internal State  |

**Outputs**

|Name|Description|Variable|
|---|---|---|
|Cooling Coil Setpoint|Target cooling coil temperature|$CC_{Temp,SP}$|
|Heating Coil Setpoint|Target heating coil temperature|$HC_{Temp,SP}$|
|Economizer Ratio|Absolute flow rate from OA fraction $\gamma$|$OA_{Flow,SP}$|
|Humidifier Setpoint|Target humidity ratio, from the saturated coil state|$Hum_{W,SP}$|

**Constraints**

| Name                   | Type                          | Target                   | Description                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------- | ----------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Zone Tracking Error    | Objective Penalty (Quadratic) | $T_{cc}, T_{hc}, \gamma$ | Each setpoint tracks a _different_ ask, weighted by zone desperation: $T_{cc}\leftrightarrow$ humidity ask ($\psi_i$, via linearized $w_{sat}$); $T_{hc}\leftrightarrow$ temperature ask ($\omega_i$, plus fan heat-rise offset); $\gamma\leftrightarrow$ CO2 ask ($\chi_i$). Cross-terms ($\phi_c,\phi_h,\phi_v$) couple the three for physical consistency |
| Cooling Coil Limit     | Box (Hard)                    | $T_{cc}$                 | $5^\circ\text{C} \le T_{cc} \le 40^\circ\text{C}$                                                                                                                                                                                                                                                                                                            |
| Heating Coil Limit     | Box (Hard)                    | $T_{hc}$                 | $5^\circ\text{C} \le T_{hc} \le 40^\circ\text{C}$                                                                                                                                                                                                                                                                                                            |
| OA Fraction Limit      | Box (Hard)                    | $\gamma$                 | $\gamma_{min} \le \gamma \le 1.0$                                                                                                                                                                                                                                                                                                                            |
| Cooling Restriction    | Linear Ineq. (Hard)           | $T_{cc}, \gamma$         | Coil can't "heat": $T_{cc}+\gamma(T_{ret}-T_{out})\le T_{ret}$                                                                                                                                                                                                                                                                                               |
| Heating Restriction    | Linear Ineq. (Hard)           | $T_{cc}, T_{hc}$         | Heating coil ≥ cooling coil output: $T_{hc}\ge T_{cc}$                                                                                                                                                                                                                                                                                                       |
| CO2 Safety Restriction | Linear Ineq. (Hard)           | $\gamma$                 | Ensures ventilation: $\gamma(C_{out}-C_{ret})\le C_{max}-C_{ret}$                                                                                                                                                                                                                                                                                            |

_No slacks here , all hard constraints. Setpoints are rate-limited (EMA + max-Δ clamp) before being written to hardware, and fall back to the previous setpoints if OSQP fails._
## Implementation Notes

- All three QP layers fall back to a safe default (proportional control, or previous setpoints) if OSQP fails to solve, so the control loop stays alive under infeasibility.
- The zone controller's own $T_{s,min}$ floor (10°C) is stricter than the coordinator's coil floor (5°C). The coordinator's capability window is therefore a superset of what any zone will request, not a functional conflict, but worth a quick check that the offset is intentional.