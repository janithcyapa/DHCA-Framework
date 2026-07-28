import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output
import warnings
import functools
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

# --- 1. Global Design System & Grammar ---
COLORS = {
    # Functional Semantics (View 1, 2, 3)
    "Temp": "#2ecc71",       # Green
    "Hum": "#3498db",        # Blue
    "CO2": "#e67e22",        # Orange
    "Occ": "#9b59b6",        # Purple
    "Default": "#e74c3c",    # Red
    "NIS_Trace": "#f1c40f",  # Yellow
    
    # AHU Decisions
    "Cool_SP": "#2ecc71",    # Green 1
    "Heat_SP": "#00bc8c",    # Green 2
    
    # Zone Categorical (View 4, 5)
    "SPACE1-1": "#ef476f",
    "SPACE2-1": "#ffd166",
    "SPACE3-1": "#06d6a0",
    "SPACE4-1": "#118ab2",
    "SPACE5-1": "#073b4c",
    
    # Monotonic Blues for Asks
    "Mono_Blues": ["#bbdefb", "#90caf9", "#64b5f6", "#42a5f5", "#2196f3"],
}

STATUS_COLORSCALE = [
    [0.0, '#2ecc71'],  # 1 = Green (Success)
    [0.5, '#f1c40f'],  # 5 = Amber (Marginal)
    [1.0, '#e74c3c']   # 9 = Red (Failed)
]

ZONES = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]
BASE_YEAR = 2014

# --- Helper Functions ---
def hex_to_rgba(hex_color, opacity=1.0):
    hex_color = hex_color.lstrip('#')
    return f"rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {opacity})"

def desaturate_hex(hex_color, factor=0.5):
    import colorsys
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, l, s * factor)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def lighten_hex(hex_color, amount=0.15):
    import colorsys
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = min(1.0, l + amount)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def add_comfort_band(fig, row, col, x_arr, ymin, ymax):
    if np.isscalar(ymin):
        ymin = [ymin] * len(x_arr)
    if np.isscalar(ymax):
        ymax = [ymax] * len(x_arr)
        
    fig.add_trace(go.Scatter(
        x=x_arr, y=ymin, line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'), 
        showlegend=False, hoverinfo='skip'
    ), row=row, col=col)
    
    fig.add_trace(go.Scatter(
        x=x_arr, y=ymax, fill='tonexty', fillcolor="rgba(255,255,255,0.05)", 
        line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'), 
        showlegend=False, hoverinfo='skip'
    ), row=row, col=col)

def add_psychrometric_comfort(fig, row, col):
    T_cz = np.linspace(20, 25, 50)
    P_atm = 101.325
    P_sat = 0.61078 * np.exp(17.27 * T_cz / (T_cz + 237.3))
    W_30 = 0.622 * (0.3 * P_sat) / (P_atm - 0.3 * P_sat)
    W_60 = 0.622 * (0.6 * P_sat) / (P_atm - 0.6 * P_sat)
    
    cz_x = np.concatenate([T_cz, T_cz[::-1]])
    cz_y = np.concatenate([W_30, W_60[::-1]])
    
    fig.add_trace(go.Scatter(
        x=cz_x, y=cz_y, fill='toself', fillcolor='rgba(255,255,255,0.05)', 
        line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'),
        showlegend=False, hoverinfo='skip'
    ), row=row, col=col)

def add_rh_co2_comfort(fig, row, col):
    cz_x = [30, 60, 60, 30, 30]
    cz_y = [0, 0, 1000, 1000, 0]
    fig.add_trace(go.Scatter(
        x=cz_x, y=cz_y, fill='toself', fillcolor='rgba(255,255,255,0.05)', 
        line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'),
        showlegend=False, hoverinfo='skip'
    ), row=row, col=col)

def ep_to_datetime(row):
    day, hour, minute = int(row['DayOfYear']), int(row['Hour']), int(row['Minute'])
    if hour >= 24:
        day += 1; hour -= 24
    return pd.Timestamp(year=BASE_YEAR, month=1, day=1) + pd.Timedelta(days=day-1, hours=hour, minutes=minute)

def configure_subplot_legends(fig):
    layout_updates = {}
    subplot_legends = {} 
    legend_counter = 1
    
    layout_updates['margin'] = dict(l=30, r=30, t=80, b=30)
    
    annotations = fig.layout.annotations
    ann_list = list(annotations) if annotations else []

    for trace in fig.data:
        if getattr(trace, 'showlegend', None) is False:
            continue
            
        x_ref = getattr(trace, 'xaxis', None)
        y_ref = getattr(trace, 'yaxis', None)
        
        if not x_ref or not y_ref:
            continue
        
        yaxis_key = 'yaxis' + (y_ref[1:] if len(y_ref) > 1 else '')
        ax = getattr(fig.layout, yaxis_key, None)
        if ax and getattr(ax, 'overlaying', None):
            y_ref = ax.overlaying
            
        subplot_key = (x_ref, y_ref)
        
        if subplot_key not in subplot_legends:
            legend_id = "legend" if legend_counter == 1 else f"legend{legend_counter}"
            subplot_legends[subplot_key] = legend_id
            legend_counter += 1
            
            xaxis_key = 'xaxis' + (x_ref[1:] if len(x_ref) > 1 else '')
            yaxis_key = 'yaxis' + (y_ref[1:] if len(y_ref) > 1 else '')
            
            try:
                y_domain = fig.layout[yaxis_key].domain
                if y_domain is None: y_domain = [0, 1]
            except:
                y_domain = [0, 1]
            try:
                x_domain = fig.layout[xaxis_key].domain
                if x_domain is None: x_domain = [0, 1]
            except:
                x_domain = [0, 1]
                
            y_title = y_domain[1] + 0.015
            for ann in ann_list:
                if getattr(ann, 'yanchor', None) == 'bottom' and getattr(ann, 'xanchor', None) == 'center':
                    if abs(ann.x - (x_domain[0] + x_domain[1])/2) < 0.02 and abs(ann.y - y_domain[1]) < 0.05:
                        y_title = ann.y
                        break
                        
            layout_updates[legend_id] = dict(
                x=x_domain[1],
                y=y_title, 
                xanchor='right',
                yanchor='bottom',
                orientation='h',
                font=dict(size=10),
                bgcolor='rgba(0,0,0,0)'
            )
            
        trace.legend = subplot_legends[subplot_key]

    if ann_list:
        for ann in ann_list:
            if getattr(ann, 'text', '') == "Solver status":
                ann.xanchor = "left"
                ann.x = 0
                continue
                
            pass

    if layout_updates:
        fig.update_layout(**layout_updates)

def extract_run_periods(idf_path):
    run_periods = []
    if not os.path.exists(idf_path):
        return run_periods
    with open(idf_path, 'r') as f:
        lines = [line.strip() for line in f.readlines()]
        
    for i, line in enumerate(lines):
        if line.lower().startswith('runperiod,'):
            try:
                name = lines[i+1].split(',')[0].strip()
                bm = int(lines[i+2].split(',')[0].strip())
                bd = int(lines[i+3].split(',')[0].strip())
                em = int(lines[i+5].split(',')[0].strip())
                ed = int(lines[i+6].split(',')[0].strip())
                run_periods.append({
                    'name': name,
                    'start_month': bm, 'start_day': bd,
                    'end_month': em, 'end_day': ed
                })
            except Exception as e:
                print(f"Error parsing RunPeriod: {e}")
    return run_periods

RUN_PERIODS = extract_run_periods('5ZoneAutoDXVAV.idf')

@functools.lru_cache(maxsize=3)
def load_csv_cached(csv_path):
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    df['Datetime'] = pd.Timestamp(year=BASE_YEAR, month=1, day=1) + \
                     pd.to_timedelta(df['DayOfYear'] - 1, unit='D') + \
                     pd.to_timedelta(df['Hour'], unit='h') + \
                     pd.to_timedelta(df['Minute'], unit='m')
    return df

@functools.lru_cache(maxsize=10)
def load_data(baseline_csv='./results/baseline_results.csv', run_plan_name=None):
    mpc_path = './results/state_log.csv'
    
    df = load_csv_cached(mpc_path)
    if df.empty:
        return pd.DataFrame()
        
    if run_plan_name:
        rp = next((r for r in RUN_PERIODS if r['name'] == run_plan_name), None)
        if rp:
            start = pd.Timestamp(year=BASE_YEAR, month=rp['start_month'], day=rp['start_day'])
            end = pd.Timestamp(year=BASE_YEAR, month=rp['end_month'], day=rp['end_day']) + pd.Timedelta(days=1)
            df = df[(df['Datetime'] >= start) & (df['Datetime'] < end)].copy()
            df = df.reset_index(drop=True)
            
    base_df = load_csv_cached(baseline_csv)
    if not base_df.empty:
        if run_plan_name and 'rp' in locals() and rp:
            base_df = base_df[(base_df['Datetime'] >= start) & (base_df['Datetime'] < end)]
            
        base_df = base_df.copy()
        base_df = base_df.add_suffix('_default')
        base_df = base_df.rename(columns={'Datetime_default': 'Datetime'})
        df = pd.merge(df, base_df, on='Datetime', how='inner')
    else:
        for col in df.columns:
            if col != 'Datetime': df[f'{col}_default'] = df[col] * 1.05 
            
    dt_sec = (df['Datetime'].iloc[1] - df['Datetime'].iloc[0]).total_seconds() if len(df) > 1 else 300
    j_to_kwh = 1.0 / 3.6e6
    
    if 'Meter_HVAC_Elec_J' in df.columns:
        df['Fan_kW'] = df['Fan_Power_W'] / 1000.0
        df['Cooling_kW'] = df['CC_Power_W'] / 1000.0
        df['Heating_kW'] = df['HC_Power_W'] / 1000.0
        df['Reheater_kW'] = sum([df.get(f"{z}_Reheater_W", pd.Series(0, index=df.index)) for z in ZONES]) / 1000.0
        df['Gas_kW'] = df['Heating_kW'] + df['Reheater_kW']
        df['Total_Energy_kWh_cum'] = ((df['Meter_HVAC_Elec_J'] + df['Meter_Bldg_Gas_J']) * j_to_kwh).cumsum()
        
        df['Fan_kW_default'] = df.get('Fan_Power_W_default', df['Fan_Power_W']) / 1000.0
        df['Cooling_kW_default'] = df.get('CC_Power_W_default', df['CC_Power_W']) / 1000.0
        df['Heating_kW_default'] = df.get('HC_Power_W_default', df['HC_Power_W']) / 1000.0
        df['Reheater_kW_default'] = sum([df.get(f"{z}_Reheater_W_default", pd.Series(0, index=df.index)) for z in ZONES]) / 1000.0
        df['Gas_kW_default'] = df['Heating_kW_default'] + df['Reheater_kW_default']
        df['Total_Energy_kWh_cum_default'] = ((df.get('Meter_HVAC_Elec_J_default', df['Meter_HVAC_Elec_J']) + df.get('Meter_Bldg_Gas_J_default', df['Meter_Bldg_Gas_J'])) * j_to_kwh).cumsum()

    return df

def add_psychrometric_background(fig, row, col):
    T_range = np.linspace(10, 35, 100)
    P_atm = 101.325 # kPa
    for rh in [0.2, 0.4, 0.6, 0.8, 1.0]:
        P_sat = 0.61078 * np.exp(17.27 * T_range / (T_range + 237.3))
        P_v = rh * P_sat
        W = 0.622 * P_v / (P_atm - P_v)
        line_color = 'rgba(255, 255, 255, 0.2)' if rh == 1.0 else 'rgba(255, 255, 255, 0.05)'
        line_width = 1.5 if rh == 1.0 else 1
        fig.add_trace(go.Scatter(x=T_range, y=W, mode='lines', line=dict(color=line_color, width=line_width), hoverinfo='skip', showlegend=False), row=row, col=col)
        
        valid_idx = np.where((W <= 0.024) & (T_range <= 34))[0]
        if len(valid_idx) > 0:
            idx = valid_idx[-1]
            text_color = 'rgba(255, 255, 255, 0.5)' if rh == 1.0 else 'rgba(255, 255, 255, 0.3)'
            fig.add_trace(go.Scatter(
                x=[T_range[idx]], y=[W[idx]],
                mode='text',
                text=[f"{int(rh*100)}% RH"],
                textposition="top left",
                textfont=dict(color=text_color, size=10),
                showlegend=False, hoverinfo='skip'
            ), row=row, col=col)

# --- View 1: EKF State Estimation ---
def build_view1_ekf(df, zone):
    specs_v1 = [
        [{"colspan": 3, "type": "xy"}, None, None],
        [{"type": "xy"}, {"type": "xy"}, {"type": "xy"}],
        [{"colspan": 3, "type": "xy"}, None, None],
        [{"colspan": 2, "type": "xy"}, None, {"type": "heatmap"}]
    ]
    titles = [
        "Occupancy Estimation", "Temperature Residual", "Absolute Humidity Residual", "CO2 Residual", 
        "Normalized Innovation Squared (NIS)", 
        "Covariance Convergence (Trace P)", "Final State Correlation Matrix"
    ]
    
    fig = make_subplots(rows=4, cols=3, subplot_titles=titles, specs=specs_v1, vertical_spacing=0.05)
    
    # 1.1 Occupancy
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df[f'{zone}_Occupants'], name="True Occ", line=dict(color=COLORS['Occ'], width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df[f'{zone}_EKF_x_N_occ'], name="Est Occ", line=dict(color=COLORS['Occ'], width=1.5, dash='dot')), row=1, col=1)
    
    if f'{zone}_EKF_P_N_occ' in df.columns:
        std_dev = np.sqrt(df[f'{zone}_EKF_P_N_occ'].clip(lower=0))
        upper = df[f'{zone}_EKF_x_N_occ'] + 2*std_dev
        lower = df[f'{zone}_EKF_x_N_occ'] - 2*std_dev
        fig.add_trace(go.Scatter(x=df['Datetime'], y=upper, mode='lines', line=dict(width=0), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Datetime'], y=lower, mode='lines', line=dict(width=0), fill='tonexty', fillcolor=hex_to_rgba(COLORS['Occ'], 0.15), name="±2σ Band"), row=1, col=1)

    # 1.2 Residuals
    res_vars = [(f'{zone}_EKF_y_T_in', 'T_in', COLORS['Temp'], 1), 
                (f'{zone}_EKF_y_W_in', 'W_in', COLORS['Hum'], 2), 
                (f'{zone}_EKF_y_C_in', 'C_in', COLORS['CO2'], 3)]
    for col_name, label, color, col_idx in res_vars:
        if col_name in df.columns:
            fig.add_trace(go.Violin(x=df[col_name], name=label, orientation='h', line_color=color, meanline_visible=True), row=2, col=col_idx)

    # 1.3 NIS
    if f'{zone}_EKF_NIS' in df.columns:
        fig.add_trace(go.Scatter(x=df['Datetime'], y=df[f'{zone}_EKF_NIS'], name="NIS", line=dict(color=COLORS['NIS_Trace'], width=1.5)), row=3, col=1)
        add_comfort_band(fig, 3, 1, df['Datetime'], 0.216, 7.815)
        fig.update_yaxes(type="log", row=3, col=1)

    # 1.4 Covariance Convergence
    if f'{zone}_EKF_P_trace' in df.columns:
        fig.add_trace(go.Scatter(x=df['Datetime'], y=df[f'{zone}_EKF_P_trace'], name="Trace(P)", line=dict(color=COLORS['NIS_Trace'], width=2)), row=4, col=1)
        fig.update_yaxes(type="log", row=4, col=1)

    # 1.5 Correlation Heatmap
    p_csv = f"./results/final_P_{zone}.csv"
    if os.path.exists(p_csv):
        try:
            p_mat = np.loadtxt(p_csv, delimiter=",")
            d = np.sqrt(np.diag(p_mat))
            corr_mat = p_mat / np.outer(d, d)
            corr_mat = np.clip(corr_mat, -1, 1)
            states = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass", "d_C"]
            
            # Reverse y and z to plot from top-left to bottom-right
            fig.add_trace(go.Heatmap(
                z=corr_mat[::-1], x=states, y=states[::-1], 
                colorscale="PuOr", zmin=-1, zmax=1, 
                colorbar=dict(title="Correlation", len=0.2, y=0.1)
            ), row=4, col=3)
            # Make the heatmap cells square
            fig.update_yaxes(scaleanchor="x", scaleratio=1, row=4, col=3)
        except: pass

    fig.update_layout(height=1600, template="plotly_dark", title_text=f"{zone} EKF Filter Diagnostics")
    configure_subplot_legends(fig)
    return fig

# --- View 2: Zone Controller ---
def build_view2_zone(df, zone):
    specs_v2 = [
        [{"colspan": 4, "type": "xy"}, None, None, None], 
        [{"colspan": 4, "type": "xy"}, None, None, None], 
        [{"colspan": 4, "type": "xy"}, None, None, None], 
        [{"colspan": 4, "type": "xy", "secondary_y": True}, None, None, None], 
        [{"colspan": 4, "type": "heatmap"}, None, None, None], 
        [{"type": "xy"}, {"type": "xy"}, {"type": "xy"}, {"type": "xy"}]
    ]
    titles = [
        "Temperature Regulation",
        "Relative Humidity Regulation",
        "Absolute Humidity Regulation",
        "CO2 & Occupancy Response",
        "Solver status",
        "Psychrometric (Zone Controller)", "Psychrometric (Default Controller)", 
        "RH vs CO2 (Zone Controller)", "RH vs CO2 (Default Controller)"
    ]
    
    specs_v2 = [
        [{"colspan": 2, "type": "xy"}, None], 
        [{"colspan": 2, "type": "xy"}, None], 
        [{"colspan": 2, "type": "xy"}, None], 
        [{"colspan": 2, "type": "xy", "secondary_y": True}, None], 
        [{"colspan": 2, "type": "heatmap"}, None], 
        [{"type": "xy"}, {"type": "xy"}],
        [{"type": "xy"}, {"type": "xy"}]
    ]
    fig = make_subplots(rows=7, cols=2, subplot_titles=titles, specs=specs_v2, vertical_spacing=0.04, row_heights=[0.13, 0.13, 0.13, 0.13, 0.03, 0.2, 0.2])
    
    c_temp, c_hum, c_co2, c_occ = COLORS['Temp'], COLORS['Hum'], COLORS['CO2'], COLORS['Occ']
    c_def = COLORS['Default']
    time_arr = df['Datetime']
    
    # 2.1 Temp
    t_min = df[f'{zone}_T_min_C'] if f'{zone}_T_min_C' in df.columns else [21.0]*len(df)
    t_max = df[f'{zone}_T_max_C'] if f'{zone}_T_max_C' in df.columns else [24.0]*len(df)
    add_comfort_band(fig, 1, 1, time_arr, t_min, t_max)
    
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_Temp_C'], name="Zone Controller", line=dict(color=c_temp, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_Temp_C_default'], name="Default Controller", line=dict(color=c_def, width=1.5, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_ideal_temp'], name="Ideal Setpoint", line=dict(color=hex_to_rgba("#48c9b0", 0.6), width=1, dash='dot')), row=1, col=1)

    # 2.2 RH
    add_comfort_band(fig, 2, 1, time_arr, 30, 60)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_RH_pct'], name="Zone Controller", line=dict(color=c_hum, width=2)), row=2, col=1)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_RH_pct_default'], name="Default Controller", line=dict(color=c_def, width=1.5, dash='dash')), row=2, col=1)

    # 2.3 Abs Hum
    add_comfort_band(fig, 3, 1, time_arr, 0, 0.012)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_W_kg_kg'], name="Zone Controller", line=dict(color=c_hum, width=2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_W_kg_kg_default'], name="Default Controller", line=dict(color=c_def, width=1.5, dash='dash')), row=3, col=1)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_ideal_hum'], name="Ideal Setpoint", line=dict(color=lighten_hex(c_hum), width=1.5, dash='dot')), row=3, col=1)

    # 2.4 CO2 & Occ
    add_comfort_band(fig, 4, 1, time_arr, 0, 1000)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_Occupants'], name="Occupancy", line=dict(color="rgba(255,255,255,0.1)", width=0), fill='tozeroy'), row=4, col=1, secondary_y=True)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_CO2_ppm'], name="Zone Controller", line=dict(color=c_co2, width=2)), row=4, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_CO2_ppm_default'], name="Default Controller", line=dict(color=c_def, width=1.5, dash='dash')), row=4, col=1, secondary_y=False)
    fig.add_trace(go.Scatter(x=time_arr, y=df[f'{zone}_ideal_co2'], name="Ideal Setpoint", line=dict(color=lighten_hex(c_co2), width=1.5, dash='dot')), row=4, col=1, secondary_y=False)

    # 2.5 Status Timeline
    if f'{zone}_MPC_Status' in df.columns and f'{zone}_AskQP_Status' in df.columns:
        z_mpc = df[f'{zone}_MPC_Status'].values
        z_ask = df[f'{zone}_AskQP_Status'].values
        
        status_colors = {
            1: "#2ecc71", 2: "#5dbb63", 3: "#8ebd55", 4: "#bed047", 
            5: "#f1c40f", 6: "#efaa1c", 7: "#ed9129", 8: "#ea7736", 9: "#e74c3c"
        }
        status_names = {
            1: "Success", 2: "Infeas", 3: "Unbound", 
            4: "MaxIter", 5: "Margin", 6: "Error", 
            7: "Stop", 8: "Except", 9: "Failed"
        }
        heatmap_scale = [[(k-1)/8.0, v] for k, v in status_colors.items()]
        
        fig.add_trace(go.Scatter(
            x=time_arr, y=["Stage 2"]*len(time_arr), mode='markers',
            marker=dict(symbol='square', color=z_ask, colorscale=heatmap_scale, cmin=1, cmax=9, size=6),
            showlegend=False, hovertemplate="Stage 2: %{text}<extra></extra>", text=z_ask
        ), row=5, col=1)
        fig.add_trace(go.Scatter(
            x=time_arr, y=["Stage 1"]*len(time_arr), mode='markers',
            marker=dict(symbol='square', color=z_mpc, colorscale=heatmap_scale, cmin=1, cmax=9, size=6),
            showlegend=False, hovertemplate="Stage 1: %{text}<extra></extra>", text=z_mpc
        ), row=5, col=1)
        fig.update_yaxes(categoryorder='array', categoryarray=['Stage 2', 'Stage 1'], row=5, col=1)
        
        for val, name in status_names.items():
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode='markers',
                marker=dict(color=status_colors[val], size=8, symbol='square'),
                name=name, showlegend=True, hoverinfo='skip'
            ), row=5, col=1)

    # 2.6 Psychrometric and RH Scatters
    add_psychrometric_background(fig, 6, 1)
    add_psychrometric_comfort(fig, 6, 1)
    fig.add_trace(go.Scatter(
        x=df[f'{zone}_Temp_C'], y=df[f'{zone}_W_kg_kg'], mode='markers',
        marker=dict(color=df[f'{zone}_CO2_ppm'], coloraxis="coloraxis1", size=3, opacity=0.6), showlegend=False
    ), row=6, col=1)

    add_psychrometric_background(fig, 6, 2)
    add_psychrometric_comfort(fig, 6, 2)
    fig.add_trace(go.Scatter(
        x=df[f'{zone}_Temp_C_default'], y=df[f'{zone}_W_kg_kg_default'], mode='markers',
        marker=dict(color=df[f'{zone}_CO2_ppm_default'], coloraxis="coloraxis3", size=3, opacity=0.6), showlegend=False
    ), row=6, col=2)

    add_rh_co2_comfort(fig, 7, 1)
    fig.add_trace(go.Scatter(
        x=df[f'{zone}_RH_pct'], y=df[f'{zone}_CO2_ppm'], mode='markers',
        marker=dict(color=df[f'{zone}_Temp_C'], coloraxis="coloraxis2", size=3, opacity=0.6), showlegend=False
    ), row=7, col=1)

    add_rh_co2_comfort(fig, 7, 2)
    fig.add_trace(go.Scatter(
        x=df[f'{zone}_RH_pct_default'], y=df[f'{zone}_CO2_ppm_default'], mode='markers',
        marker=dict(color=df[f'{zone}_Temp_C_default'], coloraxis="coloraxis4", size=3, opacity=0.6), showlegend=False
    ), row=7, col=2)

    fig.update_layout(
        height=2800, template="plotly_dark", title_text=f"{zone} Single Zone Deep Dive",
        coloraxis1=dict(colorscale='Turbo', colorbar=dict(title="CO2", orientation='v', x=0.43, y=0.27, len=0.18, thickness=8)),
        coloraxis2=dict(colorscale='Thermal', colorbar=dict(title="Temp", orientation='v', x=0.43, y=0.07, len=0.18, thickness=8)),
        coloraxis3=dict(colorscale='Turbo', colorbar=dict(title="CO2", orientation='v', x=0.95, y=0.27, len=0.18, thickness=8)),
        coloraxis4=dict(colorscale='Thermal', colorbar=dict(title="Temp", orientation='v', x=0.95, y=0.07, len=0.18, thickness=8))
    )
    
    for c in [1, 2]: 
        fig.update_xaxes(range=[10, 35], title_text="Temperature (°C)", row=6, col=c)
        fig.update_yaxes(range=[0, 0.025], title_text="Abs Hum (kg/kg)", row=6, col=c)
        fig.update_xaxes(title_text="Relative Humidity (%)", row=7, col=c)
        fig.update_yaxes(title_text="CO2 (ppm)", row=7, col=c)
        
    fig.update_yaxes(showgrid=False, row=4, col=1, secondary_y=True)
    
    configure_subplot_legends(fig)
    return fig

# --- View 3: AHU Coordinator ---
def build_view3_ahu(df):
    specs_v3 = [
        [{"type": "xy"}], [{"type": "xy"}], [{"type": "xy"}], 
        [{"type": "xy"}], [{"type": "xy"}], [{"type": "heatmap"}]
    ]
    titles = [
        "Temperature Setpoint", "Humidity Setpoint", "CO2 Setpoint", 
        "Economizer Flow", "Economizer Ratio", "AHU Optimizer"
    ]
    fig = make_subplots(rows=6, cols=1, subplot_titles=titles, specs=specs_v3, vertical_spacing=0.04, row_heights=[0.19, 0.19, 0.19, 0.19, 0.19, 0.05])
    
    def add_envelope(row, zone_col_template, result_cols, main_colors):
        mins, maxs = [], []
        for i, z in enumerate(ZONES):
            col_name = zone_col_template.format(z)
            if col_name in df.columns:
                fig.add_trace(go.Scatter(x=df['Datetime'], y=df[col_name], name=f"{z} Ask", line=dict(color=COLORS["Mono_Blues"][i], width=0.5, dash='dot'), opacity=0.4, visible='legendonly'), row=row, col=1)
                mins.append(df[col_name]); maxs.append(df[col_name])
                
        if mins:
            env_min = pd.concat(mins, axis=1).min(axis=1)
            env_max = pd.concat(maxs, axis=1).max(axis=1)
            fig.add_trace(go.Scatter(x=df['Datetime'], y=env_min, line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'), showlegend=False), row=row, col=1)
            fig.add_trace(go.Scatter(x=df['Datetime'], y=env_max, fill='tonexty', fillcolor="rgba(255,255,255,0.05)", line=dict(color='rgba(255,255,255,0.4)', width=1, dash='dot'), name="Envelope"), row=row, col=1)
            
        for r_col, m_col in zip(result_cols, main_colors):
            if r_col in df.columns:
                fig.add_trace(go.Scatter(x=df['Datetime'], y=df[r_col], name=r_col, line=dict(color=m_col, width=2.5)), row=row, col=1)

    # 3.1 Temp
    add_envelope(1, "{}_ideal_temp", ["CC_Temp_SP_Cmd_C", "HC_Temp_SP_Cmd_C"], [COLORS["Cool_SP"], COLORS["Heat_SP"]])
    
    # 3.2 Hum
    add_envelope(2, "{}_ideal_hum", ["Humidifer_W_SP_kg_kg"], [COLORS["Hum"]])
    
    # 3.3 CO2
    add_envelope(3, "{}_ideal_co2", ["AHU_Supply_CO2_ppm"], [COLORS["CO2"]])
    
    # 3.4 Economizer Flow
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['OA_Flow_SP_kg_s'], name="OA Flow", line=dict(color="#2ecc71", width=2)), row=4, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Fan_Out_Flow_kg_s'], name="Total Flow", line=dict(color="#95a5a6", width=2, dash='dash')), row=4, col=1)
    fig.update_yaxes(title_text="Flow (kg/s)", row=4, col=1)
    
    # 3.5 Economizer Ratio
    if 'OA_Frac_Cmd' in df.columns:
        gamma = df['OA_Frac_Cmd']
    elif 'OA_Flow_SP_kg_s' in df.columns and 'Fan_Out_Flow_kg_s' in df.columns:
        gamma = (df['OA_Flow_SP_kg_s'] / df['Fan_Out_Flow_kg_s'].replace(0, 1e-5)).fillna(0)
    else:
        gamma = pd.Series([0]*len(df))
        
    fig.add_trace(go.Scatter(x=df['Datetime'], y=gamma, name="Gamma (Mix Ratio)", line=dict(color="#2ecc71", width=2, dash='solid'), fill='tozeroy', fillcolor=hex_to_rgba("#2ecc71", 0.15)), row=5, col=1)
    fig.update_yaxes(title_text="Gamma (γ)", range=[0, 1.05], row=5, col=1)

    # 3.6 Status Timeline
    if 'AHU_QP_Status' in df.columns:
        z_ahu = df['AHU_QP_Status'].values
        
        status_colors = {
            1: "#2ecc71", 2: "#5dbb63", 3: "#8ebd55", 4: "#bed047", 
            5: "#f1c40f", 6: "#efaa1c", 7: "#ed9129", 8: "#ea7736", 9: "#e74c3c"
        }
        status_names = {
            1: "Success", 2: "Infeas", 3: "Unbound", 
            4: "MaxIter", 5: "Margin", 6: "Error", 
            7: "Stop", 8: "Except", 9: "Failed"
        }
        heatmap_scale = [[(k-1)/8.0, v] for k, v in status_colors.items()]
        
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=["Optimizer"]*len(df['Datetime']), mode='markers',
            marker=dict(symbol='square', color=z_ahu, colorscale=heatmap_scale, cmin=1, cmax=9, size=6),
            showlegend=False, hovertemplate="Optimizer: %{text}<extra></extra>", text=z_ahu
        ), row=6, col=1)
        fig.update_yaxes(categoryorder='array', categoryarray=['Optimizer'], row=6, col=1)
        
        for val, name in status_names.items():
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode='markers',
                marker=dict(color=status_colors[val], size=8, symbol='square'),
                name=name, showlegend=True, hoverinfo='skip'
            ), row=6, col=1)

    fig.update_layout(height=1800, template="plotly_dark", title_text="AHU Coordinator Arbitration")
    configure_subplot_legends(fig)
    return fig

# --- View 4: Whole Building Rollup ---
def build_view4_building(df):
    specs_v4 = [
        [{"type": "bar", "colspan": 4}, None, None, None, None, {"type": "bar", "colspan": 4}, None, None, None, None, {"type": "bar", "colspan": 4}, None, None, None],
        [None]*14,
        [{"type": "box", "colspan": 4}, None, None, None, None, {"type": "box", "colspan": 4}, None, None, None, None, {"type": "box", "colspan": 4}, None, None, None],
        [None]*14,
        [{"type": "xy", "colspan": 6}, None, None, None, None, None, None, None, {"type": "xy", "colspan": 6}, None, None, None, None, None],
        [None]*14,
        [{"type": "xy", "colspan": 6}, None, None, None, None, None, None, None, {"type": "xy", "colspan": 6}, None, None, None, None, None]
    ]
    titles = [
        "% Time Comfort (Temp)", "% Time Comfort (RH)", "% Time Comfort (CO2)", 
        "Temperature Distribution", "RH Distribution", "CO2 Distribution", 
        "Psychrometric (Zone Controller)", "Psychrometric (Default Controller)",
        "RH vs CO2 (Zone Controller)", "RH vs CO2 (Default Controller)"
    ]
    
    fig = make_subplots(rows=7, cols=14, subplot_titles=titles, specs=specs_v4, vertical_spacing=0.04, horizontal_spacing=0.02, row_heights=[0.15, 0.005, 0.15, 0.03, 0.28, 0.01, 0.28])
    
    def_bar_marker_t = dict(color=hex_to_rgba(COLORS['Temp'], 0.2), line=dict(color=COLORS['Default'], width=1.5))
    def_bar_marker_rh = dict(color=hex_to_rgba(COLORS['Hum'], 0.2), line=dict(color=COLORS['Default'], width=1.5))
    def_bar_marker_c = dict(color=hex_to_rgba(COLORS['CO2'], 0.2), line=dict(color=COLORS['Default'], width=1.5))
    def_box_style = dict(color=COLORS['Default'])
    
    # 4.1 Bar Charts
    p_T, d_T, p_RH, d_RH, p_CO2, d_CO2 = [], [], [], [], [], []
    for z in ZONES:
        t_min = df[f'{z}_T_min_C'] if f'{z}_T_min_C' in df else 21
        t_max = df[f'{z}_T_max_C'] if f'{z}_T_max_C' in df else 24
        p_T.append(((df[f'{z}_Temp_C'] >= t_min) & (df[f'{z}_Temp_C'] <= t_max)).mean() * 100)
        d_T.append(((df[f'{z}_Temp_C_default'] >= t_min) & (df[f'{z}_Temp_C_default'] <= t_max)).mean() * 100)
        p_RH.append(((df[f'{z}_RH_pct'] >= 30) & (df[f'{z}_RH_pct'] <= 60)).mean() * 100)
        d_RH.append(((df[f'{z}_RH_pct_default'] >= 30) & (df[f'{z}_RH_pct_default'] <= 60)).mean() * 100)
        p_CO2.append((df[f'{z}_CO2_ppm'] <= 1000).mean() * 100)
        d_CO2.append((df[f'{z}_CO2_ppm_default'] <= 1000).mean() * 100)

    fig.add_trace(go.Bar(name='Zone Controller', x=ZONES, y=p_T, marker_color=COLORS['Temp']), row=1, col=1)
    fig.add_trace(go.Bar(name='Default Controller', x=ZONES, y=d_T, marker=def_bar_marker_t), row=1, col=1)
    
    fig.add_trace(go.Bar(name='Zone Controller', x=ZONES, y=p_RH, marker_color=COLORS['Hum']), row=1, col=6)
    fig.add_trace(go.Bar(name='Default Controller', x=ZONES, y=d_RH, marker=def_bar_marker_rh), row=1, col=6)
    
    fig.add_trace(go.Bar(name='Zone Controller', x=ZONES, y=p_CO2, marker_color=COLORS['CO2']), row=1, col=11)
    fig.add_trace(go.Bar(name='Default Controller', x=ZONES, y=d_CO2, marker=def_bar_marker_c), row=1, col=11)

    # 4.2 Box Plots
    for z in ZONES:
        val_T_p, val_T_d = df[f'{z}_Temp_C'], df[f'{z}_Temp_C_default']
        fig.add_trace(go.Box(y=val_T_p, name=f"{z} (Zone Controller)", marker_color=COLORS[z], showlegend=False), row=3, col=1)
        fig.add_trace(go.Box(y=val_T_d, name=f"{z} (Default Controller)", marker=def_box_style, fillcolor=hex_to_rgba(COLORS[z], 0.2), showlegend=False), row=3, col=1)
        
        val_RH_p, val_RH_d = df[f'{z}_RH_pct'], df[f'{z}_RH_pct_default']
        fig.add_trace(go.Box(y=val_RH_p, name=f"{z} (Zone Controller)", marker_color=COLORS[z], showlegend=False), row=3, col=6)
        fig.add_trace(go.Box(y=val_RH_d, name=f"{z} (Default Controller)", marker=def_box_style, fillcolor=hex_to_rgba(COLORS[z], 0.2), showlegend=False), row=3, col=6)
        
        val_C_p, val_C_d = df[f'{z}_CO2_ppm'], df[f'{z}_CO2_ppm_default']
        fig.add_trace(go.Box(y=val_C_p, name=f"{z} (Zone Controller)", marker_color=COLORS[z], showlegend=False), row=3, col=11)
        fig.add_trace(go.Box(y=val_C_d, name=f"{z} (Default Controller)", marker=def_box_style, fillcolor=hex_to_rgba(COLORS[z], 0.2), showlegend=False), row=3, col=11)

    # 4.3 & 4.4 Aggregated Scatters
    all_T_P, all_W_P, all_C_P, all_RH_P = [], [], [], []
    all_T_D, all_W_D, all_C_D, all_RH_D = [], [], [], []
    for z in ZONES:
        all_T_P.extend(df[f'{z}_Temp_C'].values); all_W_P.extend(df[f'{z}_W_kg_kg'].values)
        all_C_P.extend(df[f'{z}_CO2_ppm'].values); all_RH_P.extend(df[f'{z}_RH_pct'].values)
        all_T_D.extend(df[f'{z}_Temp_C_default'].values); all_W_D.extend(df[f'{z}_W_kg_kg_default'].values)
        all_C_D.extend(df[f'{z}_CO2_ppm_default'].values); all_RH_D.extend(df[f'{z}_RH_pct_default'].values)

    # Row 5 (Psychrometric)
    add_psychrometric_background(fig, 5, 1)
    add_psychrometric_comfort(fig, 5, 1)
    fig.add_trace(go.Scatter(x=all_T_P, y=all_W_P, mode='markers', marker=dict(color=all_C_P, coloraxis="coloraxis1", size=3, opacity=0.6), showlegend=False), row=5, col=1)

    add_psychrometric_background(fig, 5, 9)
    add_psychrometric_comfort(fig, 5, 9)
    fig.add_trace(go.Scatter(x=all_T_D, y=all_W_D, mode='markers', marker=dict(color=all_C_D, coloraxis="coloraxis3", size=3, opacity=0.6), showlegend=False), row=5, col=9)

    # Row 7 (RH vs CO2)
    add_rh_co2_comfort(fig, 7, 1)
    fig.add_trace(go.Scatter(x=all_RH_P, y=all_C_P, mode='markers', marker=dict(color=all_T_P, coloraxis="coloraxis2", size=3, opacity=0.6), showlegend=False), row=7, col=1)

    add_rh_co2_comfort(fig, 7, 9)
    fig.add_trace(go.Scatter(x=all_RH_D, y=all_C_D, mode='markers', marker=dict(color=all_T_D, coloraxis="coloraxis4", size=3, opacity=0.6), showlegend=False), row=7, col=9)

    fig.update_layout(
        height=2200, template="plotly_dark", barmode='group', title_text="Whole Building Aggregation",
        coloraxis1=dict(colorscale='Turbo', colorbar=dict(title="CO2", orientation='v', x=0.435, y=0.50, len=0.2, thickness=8)),
        coloraxis3=dict(colorscale='Turbo', colorbar=dict(title="CO2", orientation='v', x=1.00, y=0.50, len=0.2, thickness=8)),
        coloraxis2=dict(colorscale='Thermal', colorbar=dict(title="Temp", orientation='v', x=0.435, y=0.1, len=0.2, thickness=8)),
        coloraxis4=dict(colorscale='Thermal', colorbar=dict(title="Temp", orientation='v', x=1.00, y=0.1, len=0.2, thickness=8))
    )
    
    for c in [1, 9]: 
        fig.update_xaxes(range=[10, 35], title_text="Temperature (°C)", row=5, col=c)
        fig.update_yaxes(range=[0, 0.025], title_text="Abs Hum (kg/kg)", row=5, col=c)
        fig.update_xaxes(title_text="Relative Humidity (%)", row=7, col=c)
        fig.update_yaxes(title_text="CO2 (ppm)", row=7, col=c)

    configure_subplot_legends(fig)
    return fig

# --- View 5: Energy ---
def build_view5_energy(df):
    specs_v5 = [
        [{"type": "xy", "colspan": 3}, None, None], 
        [{"type": "xy", "colspan": 3}, None, None], 
        [{"type": "xy"}, {"type": "bar"}, {"type": "domain"}]
    ]
    titles = [
        "Instantaneous Power Profile (kW)", "Cumulative Total Energy Use (kWh)", 
        "Load Duration Curve", "Energy Savings Breakdown", "Energy End-Use"
    ]
    fig = make_subplots(rows=3, cols=3, subplot_titles=titles, specs=specs_v5, vertical_spacing=0.08, horizontal_spacing=0.10)
    
    # 5.1 Instantaneous
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Fan_kW'], name="Fan (Zone Controller)", line=dict(color=COLORS['Occ'], width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Cooling_kW'], name="Cooling (Zone Controller)", line=dict(color=COLORS['Hum'], width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Gas_kW'], name="Heating (Zone Controller)", line=dict(color=COLORS['CO2'], width=1.5)), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Fan_kW_default'], name="Fan (Default Controller)", line=dict(color=COLORS['Occ'], width=1.5, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Cooling_kW_default'], name="Cooling (Default Controller)", line=dict(color=COLORS['Hum'], width=1.5, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Gas_kW_default'], name="Heating (Default Controller)", line=dict(color=COLORS['CO2'], width=1.5, dash='dash')), row=1, col=1)

    # 5.2 Cumulative
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Total_Energy_kWh_cum'], name="Zone Controller Total", line=dict(color=COLORS['Temp'], width=3)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Total_Energy_kWh_cum_default'], name="Default Controller Total", line=dict(color=COLORS['Default'], width=2, dash='solid')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['Datetime'], y=df['Total_Energy_kWh_cum'], fill='tonexty', fillcolor="rgba(255, 255, 255, 0.2)", line=dict(width=0), showlegend=False), row=2, col=1)

    # 5.3 Load Duration
    p_total = (df['Fan_kW'] + df['Cooling_kW'] + df['Gas_kW']).sort_values(ascending=False).values
    d_total = (df['Fan_kW_default'] + df['Cooling_kW_default'] + df['Gas_kW_default']).sort_values(ascending=False).values
    x_pct = np.linspace(0, 100, len(p_total))
    
    fig.add_trace(go.Scatter(x=x_pct, y=p_total, name="Zone Controller Peak", line=dict(color=COLORS['Temp'], width=2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=x_pct, y=d_total, name="Default Controller Peak", line=dict(color=COLORS['Default'], width=1.5, dash='solid')), row=3, col=1)

    # 5.4 Breakdown Bar
    prop_totals = [df['Fan_kW'].sum(), df['Cooling_kW'].sum(), df['Gas_kW'].sum()]
    def_totals = [df['Fan_kW_default'].sum(), df['Cooling_kW_default'].sum(), df['Gas_kW_default'].sum()]
    cats = ['Fan', 'Cooling', 'Heating']
    
    fig.add_trace(go.Bar(name='Zone Controller', x=cats, y=prop_totals, marker_color=COLORS['Temp']), row=3, col=2)
    fig.add_trace(go.Bar(name='Default Controller', x=cats, y=def_totals, marker_color=COLORS['Default']), row=3, col=2)

    # 5.5 Multi-layer Donut (Nested Pies)
    labels_inner = ["Zone Controller", "Default Controller"]
    values_inner = [sum(prop_totals), sum(def_totals)]
    colors_inner = [COLORS['Temp'], COLORS['Default']]
    
    labels_outer = ["Fan (Zone Controller)", "Cooling (Zone Controller)", "Heating (Zone Controller)", "Fan (Default Controller)", "Cooling (Default Controller)", "Heating (Default Controller)"]
    values_outer = [prop_totals[0], prop_totals[1], prop_totals[2], def_totals[0], def_totals[1], def_totals[2]]
    colors_outer = [COLORS['Occ'], COLORS['Hum'], COLORS['CO2'], COLORS['Occ'], COLORS['Hum'], COLORS['CO2']]
    
    fig.add_trace(go.Pie(
        labels=labels_inner, values=values_inner, hole=0.3,
        textinfo='none', sort=False, direction='clockwise',
        marker=dict(
            colors=colors_inner,
            line=dict(color=['#121212', 'rgba(0,0,0,0)'], width=1.5)
        )
    ), row=3, col=3)
    
    fig.add_trace(go.Pie(
        labels=labels_outer, values=values_outer, hole=0.7,
        textinfo='label+percent', textposition='outside',
        sort=False, direction='clockwise',
        marker=dict(
            colors=colors_outer,
            pattern=dict(shape=["-", "-", "-", "/", "/", "/"]),
            line=dict(
                color=['#121212', '#121212', '#121212', 'rgba(0,0,0,0)', 'rgba(0,0,0,0)', 'rgba(0,0,0,0)'],
                width=1.5
            )
        )
    ), row=3, col=3)

    titles_left_edges = {
        "Instantaneous Power Profile (kW)": 0.0,
        "Cumulative Total Energy Use (kWh)": 0.0,
        "Load Duration Curve": 0.0,
        "Energy Savings Breakdown": 0.3666666666666666,
        "Energy End-Use": 0.7333333333333333
    }
    for ann in fig.layout.annotations:
        if ann.text in titles_left_edges:
            ann.update(x=titles_left_edges[ann.text], xanchor="left")

    fig.update_layout(height=1400, template="plotly_dark", title_text="Energy Consumption & Efficiency", barmode='group')
    configure_subplot_legends(fig)
    return fig

# --- View 6: Numerical Summary (All Tables) ---
def build_view6_summary(df):
    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=["EKF Performance Summary", "Zone Controller Performance", "AHU Coordinator Summary", "Energy Summary"],
        specs=[[{"type": "table"}], [{"type": "table"}], [{"type": "table"}], [{"type": "table"}]],
        vertical_spacing=0.05
    )
    
    # 6.1 EKF Table
    cols_ekf = ["Metric"] + [f"{z}" for z in ZONES] + ["Building Avg"]
    vals_ekf = [["Occ. RMSE", "Occ. MAE", "Mean |Resid T|", "Mean |Resid W|", "Mean |Resid CO2|", "% NIS in Bounds", "Final Trace(P)"]]
    
    for i in range(7): vals_ekf.append([]) # Init lists for zones + avg
    for z in ZONES:
        try:
            rmse = np.sqrt(np.mean((df[f'{z}_Occupants'] - df[f'{z}_EKF_x_N_occ'])**2))
            mae = np.mean(np.abs(df[f'{z}_Occupants'] - df[f'{z}_EKF_x_N_occ']))
            res_t = np.mean(np.abs(df[f'{z}_EKF_y_T_in']))
            res_w = np.mean(np.abs(df[f'{z}_EKF_y_W_in']))
            res_c = np.mean(np.abs(df[f'{z}_EKF_y_C_in']))
            nis_pct = ((df[f'{z}_EKF_NIS'] >= 0.216) & (df[f'{z}_EKF_NIS'] <= 7.815)).mean() * 100
            trace_p = df[f'{z}_EKF_P_trace'].iloc[-1]
        except:
            rmse=mae=res_t=res_w=res_c=nis_pct=trace_p=0
            
        vals_ekf[1].append(f"{rmse:.2f}"); vals_ekf[2].append(f"{mae:.2f}"); vals_ekf[3].append(f"{res_t:.3f}")
        vals_ekf[4].append(f"{res_w:.6f}"); vals_ekf[5].append(f"{res_c:.2f}"); vals_ekf[6].append(f"{nis_pct:.1f}%")
        vals_ekf[7].append(f"{trace_p:.2e}")
        
    # Averages
    for i in range(1, 8):
        # Extract numeric values to average
        num_vals = [float(v.replace('%', '')) if type(v)==str else v for v in vals_ekf[i]]
        avg = np.mean(num_vals)
        if i == 6: vals_ekf[i].append(f"{avg:.1f}%")
        elif i == 7: vals_ekf[i].append(f"{avg:.2e}")
        else: vals_ekf[i].append(f"{avg:.2f}")

    fig.add_trace(go.Table(
        header=dict(values=cols_ekf, fill_color='#2c3e50', font=dict(color='white')),
        cells=dict(values=vals_ekf, fill_color='#1e1e1e', font=dict(color='white'))
    ), row=1, col=1)

    # 6.2 Zone Controller Table
    cols_zone = ["Metric"] + [f"{z} (P)" for z in ZONES] + [f"{z} (D)" for z in ZONES]
    metrics_z = ["MAE T (°C)", "% Time T in Range", "% Time RH in Range", "Max CO2 (ppm)", "% Time CO2 in Range"]
    vals_zone = [metrics_z]
    
    for z in ZONES:
        try:
            t_min = df[f'{z}_T_min_C'] if f'{z}_T_min_C' in df else 21
            t_max = df[f'{z}_T_max_C'] if f'{z}_T_max_C' in df else 24
            mae_t = np.mean(np.abs(df[f'{z}_Temp_C'] - 22.5)); pct_t = ((df[f'{z}_Temp_C'] >= t_min) & (df[f'{z}_Temp_C'] <= t_max)).mean() * 100
            pct_rh = ((df[f'{z}_RH_pct'] >= 30) & (df[f'{z}_RH_pct'] <= 60)).mean() * 100; max_c = df[f'{z}_CO2_ppm'].max(); pct_c = (df[f'{z}_CO2_ppm'] <= 1000).mean() * 100
        except: mae_t=pct_t=pct_rh=max_c=pct_c=0
        vals_zone.append([f"{mae_t:.2f}", f"{pct_t:.1f}%", f"{pct_rh:.1f}%", f"{max_c:.0f}", f"{pct_c:.1f}%"])

    for z in ZONES:
        try:
            t_min = df[f'{z}_T_min_C'] if f'{z}_T_min_C' in df else 21
            t_max = df[f'{z}_T_max_C'] if f'{z}_T_max_C' in df else 24
            mae_t_d = np.mean(np.abs(df[f'{z}_Temp_C_default'] - 22.5)); pct_t_d = ((df[f'{z}_Temp_C_default'] >= t_min) & (df[f'{z}_Temp_C_default'] <= t_max)).mean() * 100
            pct_rh_d = ((df[f'{z}_RH_pct_default'] >= 30) & (df[f'{z}_RH_pct_default'] <= 60)).mean() * 100; max_c_d = df[f'{z}_CO2_ppm_default'].max(); pct_c_d = (df[f'{z}_CO2_ppm_default'] <= 1000).mean() * 100
        except: mae_t_d=pct_t_d=pct_rh_d=max_c_d=pct_c_d=0
        vals_zone.append([f"{mae_t_d:.2f}", f"{pct_t_d:.1f}%", f"{pct_rh_d:.1f}%", f"{max_c_d:.0f}", f"{pct_c_d:.1f}%"])

    fig.add_trace(go.Table(
        header=dict(values=cols_zone, fill_color='#2c3e50', font=dict(color='white')),
        cells=dict(values=vals_zone, fill_color='#1e1e1e', font=dict(color='white'))
    ), row=2, col=1)

    # 6.3 AHU Table
    try:
        mean_cc = df['CC_Temp_SP_Cmd_C'].mean(); max_cc = df['CC_Temp_SP_Cmd_C'].max()
        mean_hc = df['HC_Temp_SP_Cmd_C'].mean(); max_hc = df['HC_Temp_SP_Cmd_C'].max()
    except: mean_cc = max_cc = mean_hc = max_hc = 0
        
    fig.add_trace(go.Table(
        header=dict(values=["Metric", "Value"], fill_color='#2c3e50', font=dict(color='white')),
        cells=dict(values=[
            ["Mean CC Setpoint (°C)", "Max CC Setpoint (°C)", "Mean HC Setpoint (°C)", "Max HC Setpoint (°C)"],
            [f"{mean_cc:.2f}", f"{max_cc:.2f}", f"{mean_hc:.2f}", f"{max_hc:.2f}"]
        ], fill_color='#1e1e1e', font=dict(color='white'))
    ), row=3, col=1)

    # 6.4 Energy Table
    prop_totals = [df['Fan_kW'].sum(), df['Cooling_kW'].sum(), df['Gas_kW'].sum()]
    def_totals = [df['Fan_kW_default'].sum(), df['Cooling_kW_default'].sum(), df['Gas_kW_default'].sum()]
    cats = ['Fan', 'Cooling', 'Gas']
    
    fig.add_trace(go.Table(
        header=dict(values=["End-Use", "Proposed (kWh)", "Default (kWh)", "Δ (kWh)"], fill_color='#2c3e50', font=dict(color='white')),
        cells=dict(values=[
            cats + ["Total"],
            [f"{p:.1f}" for p in prop_totals] + [f"{sum(prop_totals):.1f}"],
            [f"{d:.1f}" for d in def_totals] + [f"{sum(def_totals):.1f}"],
            [f"{p-d:.1f}" for p, d in zip(prop_totals, def_totals)] + [f"{sum(prop_totals)-sum(def_totals):.1f}"]
        ], fill_color='#1e1e1e', font=dict(color='white'))
    ), row=4, col=1)

    fig.update_layout(height=1800, template="plotly_dark", title_text="Detailed Numerical Summary")
    return fig


# --- Dash App ---
app = Dash(__name__)

app.layout = html.Div([
    html.H2("Decentralized HVAC Control Dashboard", style={"textAlign": "center", "color": "#ecf0f1", "paddingTop": "20px", "fontFamily": "sans-serif"}),
    html.Div([
        html.Div([
            html.Label("Select View:", style={"color": "#ecf0f1", "fontWeight": "bold"}),
            dcc.Dropdown(
                id="view-dropdown",
                options=[
                    {"label": "1. EKF State Estimation", "value": "VIEW_1"},
                    {"label": "2. Zone MPC vs Default", "value": "VIEW_2"},
                    {"label": "3. AHU Coordinator", "value": "VIEW_3"},
                    {"label": "4. Building Managment System", "value": "VIEW_4"},
                    {"label": "5. Energy Consumption", "value": "VIEW_5"},
                    {"label": "6. Numerical Summary Tables", "value": "VIEW_6"}
                ], value="VIEW_2", clearable=False, style={"color": "#000"}
            ),
        ], style={"width": "18%", "display": "inline-block", "padding": "10px"}),
        html.Div([
            html.Label("Select Zone:", style={"color": "#ecf0f1", "fontWeight": "bold"}),
            dcc.Dropdown(
                id="zone-dropdown", options=[{"label": z, "value": z} for z in ZONES],
                value="SPACE1-1", clearable=False, style={"color": "#000"}
            ),
        ], style={"width": "14%", "display": "inline-block", "padding": "10px"}),
        html.Div([
            html.Label("Run Plan:", style={"color": "#ecf0f1", "fontWeight": "bold"}),
            dcc.Dropdown(
                id="run-plan-dropdown",
                options=[{"label": rp["name"], "value": rp["name"]} for rp in RUN_PERIODS],
                value=None,
                placeholder="Select a Run Plan...",
                clearable=True, style={"color": "#000"}
            ),
        ], style={"width": "22%", "display": "inline-block", "padding": "10px"}),
        html.Div([
            html.Label("Baseline Data:", style={"color": "#ecf0f1", "fontWeight": "bold"}),
            dcc.Dropdown(
                id="baseline-dropdown",
                options=[
                    {"label": "Standard Default", "value": "./results/baseline_results.csv"},
                    {"label": "VAV with Reheaters", "value": "./results/baseline_results_vav.csv"}
                ],
                value="./results/baseline_results.csv",
                clearable=False, style={"color": "#000"}
            ),
        ], style={"width": "22%", "display": "inline-block", "padding": "10px"}),
        html.Div([
            html.Label("Time Range:", style={"color": "#ecf0f1", "fontWeight": "bold"}),
            dcc.Dropdown(
                id="time-dropdown", options=[{"label": "Plot All", "value": "ALL"}], value="ALL",
                clearable=False, style={"color": "#000"}
            ),
        ], style={"width": "14%", "display": "inline-block", "padding": "10px"}),
    ], style={"width": "95%", "margin": "0 auto", "backgroundColor": "#2c3e50", "padding": "20px", "borderRadius": "8px", "boxShadow": "0 4px 8px rgba(0,0,0,0.3)"}),
    html.Br(),
    dcc.Loading(id="loading", color="#3498db", children=html.Div(dcc.Graph(id="main-graph"), style={"width": "95%", "margin": "0 auto"}))
], style={"backgroundColor": "#121212", "minHeight": "100vh", "margin": "-8px"})

@app.callback(
    Output("time-dropdown", "options"),
    [Input("run-plan-dropdown", "value"), Input("baseline-dropdown", "value")]
)
def update_time_options(run_plan, baseline):
    if not run_plan:
        return [{"label": "Select a Run Plan First", "value": "ALL"}]
    df = load_data(baseline, run_plan)
    options = [{"label": "Plot All", "value": "ALL"}]
    if not df.empty:
        min_t = df['Datetime'].min()
        max_t = df['Datetime'].max()
        total_days = (max_t - min_t).days + 1
        for w in range(1, ((total_days + 6) // 7) + 1):
            options.append({"label": f"Week {w}", "value": f"WEEK_{w}"})
        for d in range(1, total_days + 1):
            options.append({"label": f"Day {d}", "value": f"DAY_{d}"})
    return options

@app.callback(
    [Output("main-graph", "figure"), Output("zone-dropdown", "disabled")],
    [Input("view-dropdown", "value"), Input("zone-dropdown", "value"), Input("time-dropdown", "value"), Input("run-plan-dropdown", "value"), Input("baseline-dropdown", "value")]
)
def update_dashboard(view, zone, time_range, run_plan, baseline):
    if not run_plan:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark", 
            title_text="Please select a Run Plan to view data.",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False)
        )
        return fig, True

    df = load_data(baseline, run_plan).copy()
    if df.empty: return go.Figure(), False
        
    if time_range != "ALL":
        min_t = df['Datetime'].min()
        if time_range.startswith("WEEK_"):
            w = int(time_range.split("_")[1])
            start, end = min_t + pd.Timedelta(days=(w-1)*7), min_t + pd.Timedelta(days=w*7)
            df = df[(df['Datetime'] >= start) & (df['Datetime'] < end)]
        elif time_range.startswith("DAY_"):
            d = int(time_range.split("_")[1])
            start, end = min_t + pd.Timedelta(days=d-1), min_t + pd.Timedelta(days=d)
            df = df[(df['Datetime'] >= start) & (df['Datetime'] < end)]
            
        if not df.empty and 'Total_Energy_kWh_cum' in df.columns:
            df['Total_Energy_kWh_cum'] -= df['Total_Energy_kWh_cum'].iloc[0]
            if 'Total_Energy_kWh_cum_default' in df.columns:
                df['Total_Energy_kWh_cum_default'] -= df['Total_Energy_kWh_cum_default'].iloc[0]
    
    zone_disabled = view not in ["VIEW_1", "VIEW_2"]
    
    if view == "VIEW_1": fig = build_view1_ekf(df, zone)
    elif view == "VIEW_2": fig = build_view2_zone(df, zone)
    elif view == "VIEW_3": fig = build_view3_ahu(df)
    elif view == "VIEW_4": fig = build_view4_building(df)
    elif view == "VIEW_5": fig = build_view5_energy(df)
    elif view == "VIEW_6": fig = build_view6_summary(df)
    else: fig = go.Figure()
        
    return fig, zone_disabled

if __name__ == "__main__":
    app.run(debug=True, port=8050)