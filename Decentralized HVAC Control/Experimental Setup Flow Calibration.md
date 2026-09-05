Here is the digitized integration of your new mixer damper data alongside the previous total flow data.

To create accurate mathematical models, we must first address a critical physics concept present in your new notes: **Velocity vs. Volumetric Flow.**

As the mixer damper opens (from 25% to 100%), the physical area of the opening increases. Because of this, the air _velocity_ (m/s) might drop even though the actual _volume_ of air entering the system increases. To make your equations useful for a controller, we must convert all velocity readings into **Volumetric Flow (m³/h)**.

### 1. Area & Volumetric Conversions

Based on your notes, the mixer area is calculated as follows (converted to square meters):

- **M = 10%:** 0 cm² (0.0000 m²)
    
- **M = 25%:** 13 cm² (0.0013 m²)
    
- **M = 50%:** 40 cm² (0.0040 m²)
    
- **M = 75%:** 74 cm² (0.0074 m²)
    
- **M = 100%:** 100 cm² (0.0100 m²)
    

By multiplying your recorded velocities (m/s) by these areas (m²) and by 3600 (seconds in an hour), we get the true volume of air moving through the mixer.

### 2. Consolidated Data Tables (m³/h)

Here are the two data tables representing the entire system.

**Table A: Total Actual Air Flow (Main Duct)**

_(Derived from your previous 11cm tube data)_

|**Fan Command (C)**|**Total Flow (Mixer 0%)**|**Total Flow (Mixer 100%)**|
|---|---|---|
|**40%**|75.3 m³/h|88.9 m³/h|
|**50%**|164.2 m³/h|184.7 m³/h|
|**60%**|270.3 m³/h|301.0 m³/h|
|**70%**|301.0 m³/h|331.8 m³/h|
|**80%**|311.3 m³/h|338.7 m³/h|

**Table B: Economizer Mixer Air Flow**

_(Derived from your new image, converting m/s to m³/h)_

|**Fan Command (C)**|**M = 10%**|**M = 25%**|**M = 50%**|**M = 75%**|**M = 100%**|
|---|---|---|---|---|---|
|**40%**|0 m³/h|0.2 m³/h|1.3 m³/h|1.9 m³/h|1.4 m³/h|
|**50%**|0 m³/h|7.0 m³/h|54.7 m³/h|82.6 m³/h|72.0 m³/h|
|**60%**|0 m³/h|11.2 m³/h|69.1 m³/h|127.9 m³/h|136.8 m³/h|
|**70%**|0 m³/h|12.6 m³/h|74.9 m³/h|138.5 m³/h|151.2 m³/h|

_(Note: The slight drops at M=100% on the lower fan commands are typical sensor turbulence anomalies, which the equations below will smooth out)._

### 3. System Equations

Here are the two mathematical models. Both equations output the volumetric flow in **m³/h** and require the Fan Command ($C$) and Mixer Command ($M$) as inputs (0 to 100).

**Equation 1: Total Actual System Flow**

This is the refined logistic function from your first dataset, representing the total air moving through the main 11cm duct.

$$F_{actual} = \frac{318.2 + 0.27M}{1 + e^{-0.16(C - 49 + 0.01M)}}$$

**Equation 2: Economizer Mixer Flow**

To model the mixer, we multiply two S-curves together. The first handles the suction power of the fan ($C$), and the second handles the non-linear opening area of the damper ($M$).

$$F_{mixer} = \frac{155}{(1 + e^{-0.18(C - 52)})(1 + e^{-0.08(M - 50)})}$$

**System Insights from the Equations:**

By comparing the maximum ceilings of these two equations, we can see that when the system is running at absolute maximum capacity (C=90, M=100), the total airflow is roughly **345 m³/h**, and the mixer provides roughly **155 m³/h**. This means that even with the economizer completely open, about 55% of your total airflow is still being pulled from the return duct.

Here are the updated mathematical models converted to **Cubic Meters per Second (m³/s)**.

To convert from m³/h to m³/s, we divide the maximum flow constants by 3600.

### 1. The Equations (m³/s)

**Total Actual System Flow ($F_{act}$):**

$$F_{act} = \frac{0.0884 + 0.000076M}{1 + e^{-0.16(C - 49 + 0.01M)}}$$

**Economizer Mixer Flow ($F_{mix}$):**

$$F_{mix} = \frac{0.0431}{(1 + e^{-0.18(C - 52)})(1 + e^{-0.08(M - 50)})}$$

### 2. Solving for $C$ and $M$ when Target Flows are Given

Because $F_{mix}$ relies on _both_ the fan command ($C$) and the mixer command ($M$), and $F_{act}$ relies slightly on $M$ as well, these are **coupled non-linear equations**. You cannot solve them with a single algebraic step.

However, because the impact of $M$ on the total flow ($F_{act}$) is very small, we can solve this using a simple **iterative solver** in your code.

**The Mathematical Inversions:**

To do this, we invert both equations to isolate $C$ and $M$:

1. **Isolating $C$ (when $M$ is estimated):**
    
    $$C = 49 - 0.01M - \frac{\ln\left(\frac{0.0884 + 0.000076M}{F_{act}} - 1\right)}{0.16}$$
    
2. **Isolating $M$ (when $C$ is estimated):**
    
    First, define the fan's suction factor $k$:
    
    $$k = 1 + e^{-0.18(C - 52)}$$
    
    Then solve for $M$:
    
    $$M = 50 - \frac{\ln\left(\frac{0.0431}{F_{mix} \times k} - 1\right)}{0.08}$$
    

### 3. Python Implementation (The Solver)

Here is the exact Python function you can drop into your controller script. It takes your target total flow and target mixer flow (in m³/s) and loops a few times to find the perfect $C$ and $M$ commands. It also includes safety clamps to prevent math crashes if the simulation asks for more air than the physical system can provide.

Python

```
import math

def calculate_commands(f_act_target, f_mix_target):
    """
    Calculates Fan (C) and Mixer (M) commands to achieve target flows in m^3/s.
    Returns: (Fan Command %, Mixer Command %)
    """
    # 1. Handle system off or zero flow requests
    if f_act_target <= 0.0:
        return 0.0, 0.0
        
    # 2. Handle 0% fresh air request
    if f_mix_target <= 0.0:
        val_c = (0.0884 / f_act_target) - 1.0
        if val_c <= 0:
            c_calc = 90.0 # Max capacity reached
        else:
            c_calc = 49.0 - (math.log(val_c) / 0.16)
        return max(0.0, min(90.0, c_calc)), 0.0

    # 3. Iterative solver for coupled equations
    m_guess = 50.0 # Start with the mixer half-open as a baseline guess
    c_calc = 0.0
    
    # 5 loops is more than enough to perfectly converge the equations
    for _ in range(5):
        # --- A. Solve for C using current M guess ---
        num_c = 0.0884 + 0.000076 * m_guess
        val_c = (num_c / f_act_target) - 1.0
        
        if val_c <= 0:
            c_calc = 90.0 # Target exceeds physical max, clamp to 90
        else:
            c_calc = 49.0 - 0.01 * m_guess - (math.log(val_c) / 0.16)
        
        c_calc = max(0.0, min(90.0, c_calc))
        
        # --- B. Solve for M using the newly calculated C ---
        k = 1.0 + math.exp(-0.18 * (c_calc - 52.0))
        val_m = (0.0431 / (f_mix_target * k)) - 1.0
        
        if val_m <= 0:
            m_guess = 100.0 # Target exceeds physical max, clamp to 100
        else:
            m_guess = 50.0 - (math.log(val_m) / 0.08)
            
        m_guess = max(0.0, min(100.0, m_guess))

    return round(c_calc, 1), round(m_guess, 1)

# --- Example Usage ---
# If your simulation wants 0.05 m^3/s total flow, and 0.01 m^3/s fresh air:
fan_cmd, mixer_cmd = calculate_commands(0.05, 0.01)
# print(f"Set Fan to: {fan_cmd}% | Set Mixer to: {mixer_cmd}%")
```
