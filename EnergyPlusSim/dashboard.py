import sys
import os
import datetime
import json
import pandas as pd
import numpy as np
from open_dataset_store import quick_start
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Dash imports for the web viewer dashboard
from dash import Dash, dcc, html, Input, Output

# --- 1. Initialization & Data Loading ---
sys.path.insert(0, '/home/jazz/Projects/Statistical-Learning-e20452')
store = quick_start('./ExperimentResults', backend='local')

CSV_PATH = './results/state_log.csv'
ZONES = ['SPACE1-1', 'SPACE2-1', 'SPACE3-1', 'SPACE4-1', 'SPACE5-1']
base_year = 2014

# --- Configuration Flags ---
# Change this to False if you want to see the first hour of EKF data
REMOVE_FIRST_HOUR_EKF = False

def filter_first_hour(df):
    if df is None or df.empty:
        return df
    first_time = df["Datetime"].iloc[0]
    return df[df["Datetime"] >= first_time + pd.Timedelta(hours=1)].copy()

def _ep_to_datetime(row):
    day, hour, minute = int(row['DayOfYear']), int(row['Hour']), int(row['Minute'])
    if hour >= 24:
        day += 1
        hour -= 24
    return pd.Timestamp(year=base_year, month=1, day=1) + pd.Timedelta(days=day-1, hours=hour, minutes=minute)

def append_json_ground_truths(df, json_path="./zone_thermal_params.json"):
    if os.path.exists(json_path):
        with open(json_path, 'r') as file:
            params = json.load(file)
        for i in range(1, 6):
            zone = f"SPACE{i}-1"
            if zone in params:
                zp = params[zone]
                # alpha_ext is the TOTAL conductance the EKF lumps into x[7]*(T_out - T_in).
                # It includes every heat path NOT modeled separately:
                #   exterior wall + ground + all adjacent zones
                true_alpha_ext = 1.0 / zp["R_env_ext"] + 1.0 / zp["R_env_gnd"]
                for adj in zp.get("adj_zones", []):
                    true_alpha_ext += 1.0 / adj["R_env"]
                
                true_alpha_int = 1.0 / zp["R_int"]
                true_beta_air = 1.0 / zp["C_air"]
                true_beta_mass = 1.0 / zp["C_mass"]
                
                df[f"{zone}_true_alpha_ext"] = true_alpha_ext
                df[f"{zone}_true_alpha_int"] = true_alpha_int
                df[f"{zone}_true_beta_air"] = true_beta_air
                df[f"{zone}_true_beta_mass"] = true_beta_mass
    return df

def load_data(csv_path, window=None):
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    if window is not None and window > 0:
        df = df.tail(window).copy()
    else:
        df = df.copy()
    
    if df.empty:
        return df

    df['Datetime'] = df.apply(_ep_to_datetime, axis=1)
    df['timestamp'] = df['Datetime'].astype('int64') // 10**9
    df = append_json_ground_truths(df, "./zone_thermal_params.json")
    return df

global_df = load_data(CSV_PATH)
if not global_df.empty:
    print(f'Loaded {len(global_df)} timesteps, columns: {len(global_df.columns)}')

# --- 2. Global Styles (Adjusted for Dark Mode) ---
SOURCE_STYLES = {
    "Zone":     {"color": "#3498db", "dash": "solid",   "width": 2},    # Brighter blue
    "Outside":  {"color": "#e74c3c", "dash": "dash",    "width": 1},    # Bright red/orange
    "Supply":   {"color": "#2ecc71", "dash": "dash",    "width": 1},    # Bright green
    "Other_1":  {"color": "#f1c40f", "dash": "solid",   "width": 2},    # Bright yellow
    "Setpoint": {"color": "#ecf0f1", "dash": "dot",     "width": 1},    # White/gray
    "EKF":      {"color": "#9b59b6", "dash": "dot",     "width": 1},    # Purple
}

# --- 3. Core Plotting Function ---
def build_zone_subplots(df, zone_name, subplot_config, source_styles=SOURCE_STYLES, row_height=400):
    total_rows = len(subplot_config)
    
    # Calculate exact vertical spacing in pixels
    vertical_spacing_px = 60
    plot_area_height = row_height * total_rows + vertical_spacing_px * max(0, total_rows - 1)
    safe_spacing = vertical_spacing_px / plot_area_height if total_rows > 1 else 0
    margin_t = 100
    margin_b = 50
    total_height = plot_area_height + margin_t + margin_b
    
    fig = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[panel["title"] for panel in subplot_config],
        specs=[[{"secondary_y": True}]] * total_rows,
        vertical_spacing=safe_spacing
    )
    
    for row_idx, panel in enumerate(subplot_config, start=1):
        
        # Determine the specific legend ID for this subplot
        leg_ref = f"legend{row_idx}" if row_idx > 1 else "legend"
        
        for trace_info in panel["traces"]:
            col_name = trace_info["col"]
            source_type = trace_info.get("source", "Zone")
            trace_type = trace_info.get("type", "line")
            
            if col_name in df.columns:
                display_name = trace_info.get("name", col_name)
                is_secondary = trace_info.get("secondary_y", False)
                
                if trace_type == "status":
                    fig.add_trace(
                        go.Scatter(
                            x=df["Datetime"], y=df[col_name],
                            name=display_name, mode="markers",
                            marker=dict(
                                color=df[col_name],
                                colorscale=trace_info.get("colorscale", [[0, "#2ecc71"], [0.5, "#f1c40f"], [1, "#e74c3c"]]),
                                cmin=trace_info.get("cmin", 1), cmax=trace_info.get("cmax", 7),
                                size=6, symbol="square"
                            ),
                            legend=leg_ref # Assign to specific subplot legend
                        ),
                        row=row_idx, col=1, secondary_y=is_secondary
                    )
                else:
                    base_style = source_styles.get(source_type, {"color": "white", "dash": "solid", "width": 1})
                    line_color = trace_info.get("color", base_style["color"])
                    line_dash = trace_info.get("dash", base_style["dash"])
                    line_width = trace_info.get("width", base_style["width"])
                    
                    fig.add_trace(
                        go.Scatter(
                            x=df["Datetime"], y=df[col_name], name=display_name,
                            line=dict(color=line_color, dash=line_dash, width=line_width),
                            legend=leg_ref # Assign to specific subplot legend
                        ),
                        row=row_idx, col=1, secondary_y=is_secondary
                    )

        if "expected_range" in panel:
            ymin, ymax = panel["expected_range"]
            range_label = panel.get("expected_label", "Expected Range")
            range_color = panel.get("range_color", "rgba(46, 204, 113, 0.2)") # Slightly more opaque for dark mode
            
            fig.add_hrect(
                y0=ymin, y1=ymax, fillcolor=range_color,
                line_width=0, layer="below", row=row_idx, col=1, secondary_y=False
            )
            
            # Map the expected range label to the legend as well
            if not df.empty:
                first_valid_time = str(df["Datetime"].iloc[0]) 
                fig.add_trace(
                    go.Scatter(
                        x=[first_valid_time], y=[None],
                        mode="markers",
                        marker=dict(size=10, color=range_color, symbol="square"),
                        name=f"{range_label} ({ymin}-{ymax})",
                        legend=leg_ref,
                        showlegend=True
                    ),
                    row=row_idx, col=1, secondary_y=False
                )
            
            if "eval_col" in panel and panel["eval_col"] in df.columns:
                col_to_check = panel["eval_col"]
                oob = (df[col_to_check] < ymin) | (df[col_to_check] > ymax)
                is_oob = oob.values
                
                if is_oob.any():
                    transitions = np.where(is_oob[:-1] != is_oob[1:])[0]
                    start_idx = 0
                    intervals = []
                    
                    for t in transitions:
                        if is_oob[start_idx]: 
                            intervals.append((str(df["Datetime"].iloc[start_idx]), str(df["Datetime"].iloc[t + 1])))
                        start_idx = t + 1
                        
                    if is_oob[start_idx]:
                        intervals.append((str(df["Datetime"].iloc[start_idx]), str(df["Datetime"].iloc[-1])))
                        
                    for start_t, end_t in intervals:
                        fig.add_vrect(
                            x0=start_t, x1=end_t,
                            fillcolor="rgba(231, 76, 60, 0.2)", # Redder for dark mode
                            layer="below", line_width=0, row=row_idx, col=1, secondary_y=False
                        )
                
        primary_y_kwargs = {"title_text": panel.get("y_label", "")}
        if "y_range" in panel:
            primary_y_kwargs["range"] = panel["y_range"]
        fig.update_yaxes(**primary_y_kwargs, row=row_idx, col=1, secondary_y=False)
        
        if "secondary_y_label" in panel or "secondary_y_range" in panel:
            secondary_y_kwargs = {}
            if "secondary_y_label" in panel:
                secondary_y_kwargs["title_text"] = panel["secondary_y_label"]
            if "secondary_y_range" in panel:
                secondary_y_kwargs["range"] = panel["secondary_y_range"]
            fig.update_yaxes(**secondary_y_kwargs, row=row_idx, col=1, secondary_y=True)

    # Automatically generate layout dictionaries for each independent legend
    layout_updates = {}
    for row_idx in range(1, total_rows + 1):
        leg_ref = f"legend{row_idx}" if row_idx > 1 else "legend"
        
        # Calculate the Y coordinate for the top of this specific subplot
        y_axis_key = "yaxis" if row_idx == 1 else f"yaxis{2*row_idx - 1}"
        domain_top = fig.layout[y_axis_key].domain[1]
        
        layout_updates[leg_ref] = dict(
            orientation="h",
            yanchor="bottom",
            y=domain_top + 0.015, # Position it slightly above the subplot plot area
            xanchor="right",
            x=1.0,               # Align to the right so it doesn't overlap the center title
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11, color="white")
        )
            
    fig.update_layout(
        height=total_height,
        title_text=f"<b>{zone_name} Dashboard</b>",
        hovermode="x unified",
        template="plotly_dark", # ENABLES DARK MODE FOR PLOTLY
        margin=dict(r=50, t=margin_t, l=50, b=margin_b),
        **layout_updates # Applies all the separate legends
    )
    
    # Force tick labels to show on all x-axes despite being shared
    fig.update_xaxes(showticklabels=True)
    
    return fig

# --- 4. Configurations Generator Helpers ---
def get_zone_config(zone):
    return [
        {
            "title": "MPC Solver Status",
            "y_label": "OSQP Status Code",
            "y_range": [0, 8],
            "traces": [{"col": f"{zone}_MPC_Status", "name": "Status (1=Green, 7=Red)", "type": "status", "colorscale": [[0.0, "green"], [0.5, "yellow"], [1.0, "red"]], "cmin": 1, "cmax": 7}]
        },
        {
            "title": "Temperature", "y_label": "Temperature (°C)", "y_range": [5, 35], "expected_range": [20, 24], 
            "eval_col": f"{zone}_Temp_C", "range_color": "rgba(52, 152, 219, 0.15)", "expected_label": "Comfort Zone",
            "traces": [
                {"col": f"{zone}_Temp_C", "source": "Zone", "name": "Zone Temp"},
                {"col": "Out_Temp_C", "source": "Outside", "name": "Outdoor Temp"},
                {"col": "Fan_Out_Temp_C", "source": "Supply", "name": "Supply Temp"},
                {"col": f"{zone}_EKF_x_T_in", "source": "EKF", "name": "Estimated T_in"},
            ]
        },
        {
            "title": "Humidity Ratio", "y_label": "Humidity (kg/kg)", "expected_range": [0, 0.012], "eval_col": f"{zone}_W_kg_kg", 
            "range_color": "rgba(52, 152, 219, 0.15)", "expected_label": "Target W Band",
            "traces": [
                {"col": f"{zone}_W_kg_kg", "source": "Zone", "name": "Zone W"},
                {"col": "Out_W_kg_kg", "source": "Outside", "name": "Outdoor W"},
                {"col": "Fan_Out_W_kg_kg", "source": "Supply", "name": "Supply W"},
                {"col": f"{zone}_EKF_x_W_in", "source": "EKF", "name": "Estimated Humidity"},
            ]
        },
        {
            "title": "Relative Humidity", "y_label": "Relative Humidity (%)", "y_range": [0, 100], "expected_range": [30, 60],
            "eval_col": f"{zone}_RH_pct", "range_color": "rgba(52, 152, 219, 0.15)", "expected_label": "Target RH Band",
            "traces": [
                {"col": f"{zone}_RH_pct", "source": "Zone", "name": "Zone RH"},
                {"col": "Out_RH_pct", "source": "Outside", "name": "Outdoor RH"},
                {"col": "Fan_Out_RH_pct", "source": "Supply", "name": "Supply RH"},
            ]
        },
        {
            "title": "CO2 & Occupancy", "y_label": "CO2 (ppm)", "secondary_y_label": "Occupants", "y_range": [0, 1500], "expected_range": [0, 1000],
            "eval_col": f"{zone}_CO2_ppm", "expected_label": "Acceptable CO2", "range_color": "rgba(52, 152, 219, 0.15)",
            "traces": [
                {"col": f"{zone}_CO2_ppm", "source": "Zone", "name": "Zone CO2"},
                {"col": "Out_CO2_ppm", "source": "Outside", "name": "Outdoor CO2"},
                {"col": "Fan_Out_CO2_ppm", "source": "Supply", "name": "Supply CO2"},
                {"col": f"{zone}_Occupants", "source": "Setpoint", "name": "No of Occupancy", "secondary_y": True}, 
            ]
        },
        {
            "title": "Occupancy & Humidity Disturbance (d_W)", "y_label": "Occupants", "secondary_y_label": "Hum Disturbance (d_W)",
            "traces": [
                {"col": f"{zone}_Occupants", "source": "Zone", "name": "No of Occupancy"}, 
                {"col": f"{zone}_EKF_x_N_occ", "source": "EKF", "name": "Estimated Occupancy"},
                {"col": f"{zone}_EKF_x_d_W", "source": "Setpoint", "name": "Estimated d_W", "secondary_y": True},
            ]
        },
        {
            "title": "Equipment Load & Thermal Disturbance (d_T)", "y_label": "Temp Disturbance (d_T)", "secondary_y_label": "Equipment Load (W)",
            "traces": [
                {"col": f"{zone}_EquipLoad_W", "source": "Other_1", "name": "True Equip Load (W)", "secondary_y": True},
                {"col": f"{zone}_EKF_x_d_T", "source": "EKF", "name": "Estimated d_T"},
            ]
        },
        {
            "title": "VAV Flow & Equipment Status", "y_label": "Mass Flow (kg/s)", "secondary_y_label": "Power (W) / Temp (°C)",
            "traces": [
                {"col": f"{zone}_VAV_Flow_kg_s", "source": "Zone", "name": "VAV Flow"},
                {"col": f"{zone}_Flow_SP_kg_s", "source": "Setpoint", "name": "Flow Setpoint"},
            ]
        },
    ]

def get_ekf_config(zone):
    return [
        {"title": "Temperature States: T_in", "y_label": "Indoor Air Temp (°C)", "traces": [{"col": f"{zone}_Temp_C", "source": "Setpoint", "name": "True T_in"}, {"col": f"{zone}_EKF_x_T_in", "source": "Zone", "name": "Estimated T_in"}]},
        {"title": "Temperature States: T_m", "y_label": "Mass Temp (°C)", "traces": [{"col": f"{zone}_T_m_C", "source": "Setpoint", "name": "True T_m"}, {"col": f"{zone}_EKF_x_T_m", "source": "Other_1", "name": "Estimated T_m"}]},
        {"title": "Humidity State: W_in", "y_label": "Humidity Ratio (kg/kg)", "traces": [{"col": f"{zone}_W_kg_kg", "source": "Setpoint", "name": "True Humidity"}, {"col": f"{zone}_EKF_x_W_in", "source": "Zone", "name": "Estimated Humidity"}]},
        {"title": "CO2 Concentration: C_in", "y_label": "CO2 (ppm)", "traces": [{"col": f"{zone}_CO2_ppm", "source": "Setpoint", "name": "True CO2"}, {"col": f"{zone}_EKF_x_C_in", "source": "Zone", "name": "Estimated CO2"}]},
        {"title": "Occupancy State: N_occ", "y_label": "Number of Occupants", "traces": [{"col": f"{zone}_Occupants", "source": "Setpoint", "name": "True Occupancy"}, {"col": f"{zone}_EKF_x_N_occ", "source": "Zone", "name": "Estimated Occupancy"}]},
        {"title": "Estimated Disturbances (d_T)", "y_label": "Temp Disturbance (d_T)", "traces": [{"col": f"{zone}_EKF_x_d_T", "source": "Zone", "name": "Estimated d_T"}]},
        {"title": "Estimated Disturbances (d_W)", "y_label": "Hum Disturbance (d_W)", "traces": [{"col": f"{zone}_EKF_x_d_W", "source": "Other_1", "name": "Estimated d_W"}]},
        {"title": "External Conductance (α_ext)", "y_label": "External Conductance (α_ext)", "traces": [{"col": f"{zone}_true_alpha_ext", "source": "Setpoint", "name": "True α_ext (1/R_ext)"}, {"col": f"{zone}_EKF_x_alpha_ext", "source": "Zone", "name": "Estimated α_ext"}]},
        {"title": "Internal Conductance (α_int)", "y_label": "Internal Conductance (α_int)", "traces": [{"col": f"{zone}_true_alpha_int", "source": "Setpoint", "name": "True α_int (1/R_int)"}, {"col": f"{zone}_EKF_x_alpha_int", "source": "Zone", "name": "Estimated α_int"}]},
        {"title": "Inverse Air Thermal Mass (β_air)", "y_label": "Air Mass (β_air)", "traces": [{"col": f"{zone}_true_beta_air", "source": "Setpoint", "name": "True β_air (1/C_air)"}, {"col": f"{zone}_EKF_x_beta_air", "source": "Zone", "name": "Estimated β_air"}]},
        {"title": "Inverse Structural Thermal Mass (β_mass)", "y_label": "Structural Mass (β_mass)", "traces": [{"col": f"{zone}_true_beta_mass", "source": "Setpoint", "name": "True β_mass (1/C_mass)"}, {"col": f"{zone}_EKF_x_beta_mass", "source": "Zone", "name": "Estimated β_mass"}]},
        {
            "title": "EKF Innovations (Residuals) - Temp & CO2", "y_label": "Residuals",
            "expected_range": [-0.5, 0.5], "range_color": "rgba(46, 204, 113, 0.1)", "expected_label": "Zero-Mean Band (Temp)",
            "traces": [
                {"col": f"{zone}_EKF_y_T_in", "source": "Zone", "name": "Temp Residual (y_T)"}, 
                {"col": f"{zone}_EKF_y_C_in", "source": "Other_1", "name": "CO2 Residual (y_C)"}]
        },
        {
            "title": "Normalized Innovation Squared (NIS)", "y_label": "NIS Value", "y_range": [0, 15],
            "expected_range": [0.216, 7.815], "range_color": "rgba(241, 196, 15, 0.1)", "expected_label": "95% Confidence Interval (m=3)",
            "traces": [{"col": f"{zone}_EKF_NIS", "source": "Zone", "name": "NIS (ε)"}]
        },
        {
            "title": "Covariance Convergence (Trace of P)", "y_label": "Trace(P)",
            "traces": [{"col": f"{zone}_EKF_P_trace", "source": "Zone", "name": "Total Uncertainty Trace"}, {"col": f"{zone}_EKF_P_T_in", "source": "Outside", "name": "Temp Variance P(1,1)"}]
        }
    ]

ahu_config = [
    {
        "title": "AHU Coordinator Status", "y_label": "Status (0=Off, 1=On)", "y_range": [-0.5, 1.5],
        "traces": [{"col": "AHU_Coordinator_Status", "name": "Status Indicator", "type": "status", "colorscale": [[0.0, "#e74c3c"], [1.0, "#2ecc71"]], "cmin": 0, "cmax": 1}]
    },
    {
        "title": "VAV Flow", "y_label": "Mass Flow (kg/s)", 
        "traces": [{"col": "Fan_Out_Flow_kg_s", "color": "#9b59b6", "name": "Fan Flow"}, {"col": "Outdoor_Air_Flow_kg_s", "color": "#2ecc71", "dash": "dash", "name": "OA Flow"}]
    },
    {
        "title": "Temperature", "y_label": "Temperature (°C)", "range_color": "rgba(46, 204, 113, 0.15)", "expected_label": "Target Supply Range",
        "traces": [{"col": "AHU_Supply_Temp_C", "color": "#3498db", "name": "Actual Temp"}, {"col": "Cord_Temp_SP_C", "color": "#f39c12", "dash": "dash", "name": "Coordinator SP"}]
    },
    {
        "title": "Internal AHU Temps", "y_label": "Temperature (°C)",
        "traces": [{"col": "CC_Temp_SP_Cmd_C", "color": "#3498db", "dash": "dash", "name": "Cooling Coil SP"}, {"col": "CC_Out_Temp_C", "color": "#3498db", "name": "Cooling Coil Actual"}, {"col": "HC_Temp_SP_Cmd_C", "color": "#e74c3c", "dash": "dash", "name": "Heating Coil SP"}, {"col": "HC_Out_Temp_C", "color": "#e74c3c", "name": "Heating Coil Actual"}, {"col": "Fan_dT_est_C", "color": "#f1c40f", "dash": "dot", "name": "Fan dT Est"}]
    },
    {
        "title": "Humidity", "y_label": "Humidity (kg/kg)", "range_color": "rgba(52, 152, 219, 0.15)", "expected_label": "Typical Supply W",
        "traces": [{"col": "AHU_Supply_W_kg_kg", "color": "#3498db", "name": "Actual W"}, {"col": "Cord_W_kg_kg", "color": "#f39c12", "dash": "dash", "name": "Coordinator W SP"}]
    },
    {
        "title": "CO2", "y_label": "CO2 (ppm)", "range_color": "rgba(241, 196, 15, 0.15)", "expected_label": "Acceptable CO2",
        "traces": [{"col": "AHU_Supply_CO2_ppm", "color": "#3498db", "name": "Actual CO2"}, {"col": "Cord_CO2_ppm", "color": "#f39c12", "dash": "dash", "name": "Coordinator CO2 SP"}, {"col": "Relief_Air_CO2_ppm", "color": "#95a5a6", "dash": "dot", "name": "CO2 Relief"}, {"col": "Outdoor_Air_CO2_ppm", "color": "#2ecc71", "dash": "dot", "name": "CO2 Outdoor"}]
    },
    {
        "title": "Energy Consumption", "y_label": "Energy (Joules)",
        "traces": [{"col": "Meter_Bldg_Total_J", "source": "Zone", "name": "Building Energy"}, {"col": "Meter_HVAC_Total_J", "source": "Outside", "name": "HVAC Energy"}]
    },
    {
        "title": "Component Power", "y_label": "Power (W)",
        "traces": [{"col": "CC_Power_W", "source": "Zone", "name": "Cooling Coil Power"}, {"col": "HC_Power_W", "source": "Outside", "name": "Heating Coil Power"}, {"col": "Fan_Power_W", "source": "Other_1", "name": "Fan Power"}]
    },
    {
        "title": "VAV Reheaters Power", "y_label": "Power (W)",
        "traces": [{"col": "SPACE1-1_Reheater_W", "source": "Zone", "name": "Space 1-1"}, {"col": "SPACE2-1_Reheater_W", "source": "Outside", "name": "Space 2-1"}, {"col": "SPACE3-1_Reheater_W", "source": "Other_1", "name": "Space 3-1"}, {"col": "SPACE4-1_Reheater_W", "source": "Setpoint", "name": "Space 4-1"}, {"col": "SPACE5-1_Reheater_W", "source": "Other_2", "name": "Space 5-1"}]
    }
]

import argparse

parser = argparse.ArgumentParser(description="Building Management System Dashboard")
parser.add_argument("-s", "--save", dest="save_plots", action="store_true", help="Save PNG plots to ./results")
parser.add_argument("-l", "--live", action="store_true", help="Enable live mode (polls CSV for updates)")
parser.add_argument("-w", "--window", type=int, default=1000, help="Number of latest timesteps to show in live mode")
parser.add_argument("-i", "--interval", type=int, default=5000, help="Polling interval in milliseconds")
args = parser.parse_args()

# --- 5. Auto-Download All Plots to ./results ---
if args.save_plots:
    os.makedirs("./results", exist_ok=True)

    # Save AHU
    print("Generating and saving AHU plot...")
    ahu_fig = build_zone_subplots(global_df, "AHU", ahu_config)
    try:
        ahu_fig.write_image("./results/AHU_dashboard.png", width=1200, height=1800)
    except Exception as e:
        print(f"PNG export failed for AHU: {e}")

    # Save Zone and EKF plots for all zones
    for z in ZONES:
        print(f"Generating and saving zone plot for {z}...")
        zone_fig = build_zone_subplots(global_df, z, get_zone_config(z))
        try:
            zone_fig.write_image(f"./results/{z}_zone_dashboard.png", width=1200, height=2600)
            print(f"  Saved {z} zone dashboard.")
        except Exception as e:
            print(f"  PNG export failed for {z} zone: {e}")

        print(f"Generating and saving EKF plot for {z}...")
        ekf_df = filter_first_hour(global_df) if REMOVE_FIRST_HOUR_EKF else global_df
        ekf_fig = build_zone_subplots(ekf_df, f"{z} (EKF)", get_ekf_config(z))
        try:
            ekf_fig.write_image(f"./results/{z}_ekf_dashboard.png", width=1200, height=4000)
            print(f"  Saved {z} EKF dashboard.")
        except Exception as e:
            print(f"  PNG export failed for {z} EKF: {e}")

    print("Generating unified P Matrix heatmap (Real and Log)...")
    subplot_titles = []
    for z in ZONES:
        subplot_titles.extend([f"{z} (Real)", f"{z} (Log10)"])
        
    fig_p = make_subplots(rows=5, cols=2, subplot_titles=subplot_titles, horizontal_spacing=0.1, vertical_spacing=0.08)
    state_names = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass", "d_C"]
    has_data = False
    
    for i, z in enumerate(ZONES):
        p_csv_path = f"./results/final_P_{z}.csv"
        if os.path.exists(p_csv_path):
            has_data = True
            p_matrix = np.loadtxt(p_csv_path, delimiter=",")
            p_log = np.sign(p_matrix) * np.log10(np.abs(p_matrix) + 1e-15)
            row = i + 1
            
            # Real Plot
            fig_p.add_trace(go.Heatmap(
                z=p_matrix, x=state_names, y=state_names, colorscale="Viridis",
                hovertemplate="Row: %{y}<br>Col: %{x}<br>Value: %{z:.2e}<extra></extra>",
                coloraxis="coloraxis"
            ), row=row, col=1)
            
            # Log Plot
            fig_p.add_trace(go.Heatmap(
                z=p_log, x=state_names, y=state_names, colorscale="Viridis", customdata=p_matrix,
                hovertemplate="Row: %{y}<br>Col: %{x}<br>Log10: %{z:.2f}<br>Real: %{customdata:.2e}<extra></extra>",
                coloraxis="coloraxis2"
            ), row=row, col=2)
            
            fig_p.update_yaxes(autorange="reversed", row=row, col=1)
            fig_p.update_yaxes(autorange="reversed", row=row, col=2)
            fig_p.update_xaxes(tickangle=45, row=row, col=1)
            fig_p.update_xaxes(tickangle=45, row=row, col=2)
    
    if has_data:
        fig_p.update_layout(
            title=dict(text="<b>Final Error Covariance (P) Matrices (Real vs Log10)</b>", x=0.5, xanchor="center"),
            template="plotly_dark", height=2400, width=1400,
            coloraxis=dict(colorscale="Viridis", colorbar=dict(title="Covariance", x=1.02)),
            coloraxis2=dict(colorscale="Viridis", colorbar=dict(title="Log10 Cov", x=1.12))
        )
        for j in range(1, 11):
            y_axis = f"yaxis{j}" if j > 1 else "yaxis"
            x_axis = f"x{j}" if j > 1 else "x"
            fig_p.layout[y_axis].scaleanchor = x_axis
            fig_p.layout[y_axis].scaleratio = 1
        try:
            fig_p.write_image("./results/All_P_matrices.png", width=1400, height=2400)
            print("  Saved All_P_matrices.png")
        except Exception as e:
            print(f"  PNG export failed for unified P matrix: {e}")
    else:
        print("  No P matrix CSVs found.")

    print("All plots automatically exported to ./results.")
    sys.exit(0)

# --- 6. Dash Web Viewer App (Dark Theme) ---
app = Dash(__name__)

# Dark theme wrapper
app.layout = html.Div([
    html.H2("Building Management System Dashboard Viewer", style={"textAlign": "center", "fontFamily": "sans-serif", "color": "#ecf0f1", "paddingTop": "20px"}),
    
    html.Div([
        # View Type Dropdown
        html.Div([
            html.Label("Select View Type:", style={"fontFamily": "sans-serif", "fontWeight": "bold", "color": "#ecf0f1", "marginBottom": "8px", "display": "block"}),
            dcc.Dropdown(
                id="view-dropdown",
                options=[
                    {"label": "AHU Monitor", "value": "AHU"},
                    {"label": "Zone Monitor", "value": "ZONE"},
                    {"label": "EKF Monitor", "value": "EKF"},
                    {"label": "P Matrix Heatmap", "value": "P_MATRIX"}
                ],
                value="AHU",
                clearable=False,
                style={"color": "#000000"} # Keep dropdown text black so it's readable against the white inputs
            ),
        ], style={"width": "45%", "display": "inline-block", "padding": "10px"}),
        
        # Zone Dropdown
        html.Div([
            html.Label("Select Zone (for Zone/EKF views):", style={"fontFamily": "sans-serif", "fontWeight": "bold", "color": "#ecf0f1", "marginBottom": "8px", "display": "block"}),
            dcc.Dropdown(
                id="zone-dropdown",
                options=[{"label": z, "value": z} for z in ZONES],
                value="SPACE1-1",
                clearable=False,
                style={"color": "#000000"} # Keep dropdown text black
            ),
        ], style={"width": "45%", "display": "inline-block", "padding": "10px", "float": "right"}),
        
    ], style={"width": "80%", "margin": "0 auto", "backgroundColor": "#2c3e50", "padding": "20px", "borderRadius": "8px", "boxShadow": "0 4px 8px rgba(0,0,0,0.3)"}),
    
    html.Br(),
    
    # Live polling interval
    dcc.Interval(
        id='interval-component',
        interval=args.interval, # in milliseconds
        n_intervals=0,
        disabled=not args.live
    ),

    # Graph container (Allows page scrolling)
    dcc.Loading(
        id="loading", 
        color="#3498db",
        children=html.Div(
            dcc.Graph(id="main-graph"), 
            style={"width": "95%", "margin": "0 auto"}
        )
    )
], style={"backgroundColor": "#121212", "minHeight": "100vh", "margin": "-8px"}) # Covers the whole page in dark gray

@app.callback(
    Output("main-graph", "figure"),
    [Input("view-dropdown", "value"),
     Input("zone-dropdown", "value"),
     Input("interval-component", "n_intervals")]
)
def update_dashboard(selected_view, selected_zone, n_intervals):
    current_df = global_df
    if args.live:
        current_df = load_data(CSV_PATH, window=args.window)
        
    if current_df is None or current_df.empty:
        return go.Figure()

    if selected_view == "AHU":
        return build_zone_subplots(current_df, "AHU", ahu_config)
    elif selected_view == "ZONE":
        return build_zone_subplots(current_df, selected_zone, get_zone_config(selected_zone))
    elif selected_view == "EKF":
        plot_df = filter_first_hour(current_df) if REMOVE_FIRST_HOUR_EKF else current_df
        return build_zone_subplots(plot_df, f"{selected_zone} (EKF)", get_ekf_config(selected_zone))
    elif selected_view == "P_MATRIX":
        subplot_titles = []
        for z in ZONES:
            subplot_titles.extend([f"{z} (Real)", f"{z} (Log10)"])
            
        fig = make_subplots(rows=5, cols=2, subplot_titles=subplot_titles, horizontal_spacing=0.1, vertical_spacing=0.08)
        state_names = ["T_in", "T_m", "W_in", "C_in", "d_T", "d_W", "N_occ", "alpha_ext", "alpha_int", "beta_air", "beta_mass", "d_C"]
        has_data = False
        
        for i, z in enumerate(ZONES):
            p_csv_path = f"./results/final_P_{z}.csv"
            if os.path.exists(p_csv_path):
                has_data = True
                p_matrix = np.loadtxt(p_csv_path, delimiter=",")
                p_log = np.sign(p_matrix) * np.log10(np.abs(p_matrix) + 1e-15)
                row = i + 1
                
                # Real Plot
                fig.add_trace(go.Heatmap(
                    z=p_matrix, x=state_names, y=state_names, colorscale="Viridis",
                    hovertemplate="Row: %{y}<br>Col: %{x}<br>Value: %{z:.2e}<extra></extra>",
                    coloraxis="coloraxis"
                ), row=row, col=1)
                
                # Log Plot
                fig.add_trace(go.Heatmap(
                    z=p_log, x=state_names, y=state_names, colorscale="Viridis", customdata=p_matrix,
                    hovertemplate="Row: %{y}<br>Col: %{x}<br>Log10: %{z:.2f}<br>Real: %{customdata:.2e}<extra></extra>",
                    coloraxis="coloraxis2"
                ), row=row, col=2)
                
                fig.update_yaxes(autorange="reversed", row=row, col=1)
                fig.update_yaxes(autorange="reversed", row=row, col=2)
                fig.update_xaxes(tickangle=45, row=row, col=1)
                fig.update_xaxes(tickangle=45, row=row, col=2)
                
        if not has_data:
            fig = go.Figure()
            fig.add_annotation(text="P Matrix CSV not found (Wait for simulation to run)", x=0.5, y=0.5, showarrow=False, font=dict(size=20))
            fig.update_layout(template="plotly_dark", xaxis=dict(visible=False), yaxis=dict(visible=False))
            return fig
            
        fig.update_layout(
            title=dict(text="<b>Final Error Covariance (P) Matrices (Real vs Log10)</b>", x=0.5, xanchor="center"),
            template="plotly_dark", height=2400, width=1400,
            coloraxis=dict(colorscale="Viridis", colorbar=dict(title="Covariance", x=1.02)),
            coloraxis2=dict(colorscale="Viridis", colorbar=dict(title="Log10 Cov", x=1.12))
        )
        for j in range(1, 11):
            y_axis = f"yaxis{j}" if j > 1 else "yaxis"
            x_axis = f"x{j}" if j > 1 else "x"
            fig.layout[y_axis].scaleanchor = x_axis
            fig.layout[y_axis].scaleratio = 1
            
        return fig
    return go.Figure()

if __name__ == "__main__":
    print("Starting Dash server... Open http://127.0.0.1:8050/ in your browser.")
    app.run(debug=False, port=8050)