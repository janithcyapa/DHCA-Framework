import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# 1. Configuration
CSV_PATH = "./baseline_results/state_log.csv"
ZONES = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]
ZONE_COLORS = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A']

# 2. Load the Data
df = pd.read_csv(CSV_PATH)

# 3. Time Pre-Processing
def eplus_time_to_datetime(row, year=2026):
    base_date = datetime.datetime(year, 1, 1)
    delta = datetime.timedelta(days=int(row['DayOfYear']) - 1, 
                               hours=int(row['Hour']), 
                               minutes=int(row['Minute']))
    return base_date + delta

df['Datetime'] = df.apply(eplus_time_to_datetime, axis=1)

# 4. Create the Plotly Subplots (12 rows)
fig = make_subplots(
    rows=12, cols=1, 
    shared_xaxes=True,
    vertical_spacing=0.02,
    subplot_titles=(
        "1. Zone Temperatures vs Outdoor (°C)", 
        "2. Zone Relative Humidities vs Outdoor (%)", 
        "3. Zone CO₂ Concentrations (ppm)",
        "4. Zone Occupancy (persons)",
        "5. Zone Equipment Heat Loads (W)",
        "6. Zone VAV Supply Mass Flows (kg/s)",
        "7. Zone VAV Reheater Actuation (W)",
        "8. AHU Temperatures (°C)",
        "9. AHU CO₂ Concentrations (ppm)",
        "10. AHU Relative Humidities (%)",
        "11. AHU Mass Flows (kg/s)",
        "12. Central AHU Equipment Actuation (W)"
    )
)

# --- Row 1: Zone Temperatures ---
fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df['Out_Temp_C'],
    name='Outdoor Temp', mode='lines',
    line=dict(color='white', width=2, dash='dot')
), row=1, col=1)

for z, color in zip(ZONES, ZONE_COLORS):
    fig.add_trace(go.Scatter(
        x=df['Datetime'], y=df[f'{z}_Temp_C'],
        name=f'{z} Temp', mode='lines', line=dict(color=color, width=1.5)
    ), row=1, col=1)

# --- Row 2: Zone Humidities ---
fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df['Out_RH_pct'],
    name='Outdoor RH', mode='lines',
    line=dict(color='white', width=2, dash='dot')
), row=2, col=1)

for z, color in zip(ZONES, ZONE_COLORS):
    fig.add_trace(go.Scatter(
        x=df['Datetime'], y=df[f'{z}_RH_pct'],
        name=f'{z} RH', mode='lines', line=dict(color=color, width=1.5)
    ), row=2, col=1)

# --- Row 3: Zone CO2 ---
fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df['Outdoor_Air_CO2_ppm'],
    name='Outdoor CO₂', mode='lines',
    line=dict(color='white', width=2, dash='dot')
), row=3, col=1)

for z, color in zip(ZONES, ZONE_COLORS):
    col_name = f'{z}_CO2_ppm'
    if col_name in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{z} CO₂', mode='lines', line=dict(color=color, width=1.5)
        ), row=3, col=1)

# --- Row 4: Zone Occupancy ---
for z, color in zip(ZONES, ZONE_COLORS):
    col_name = f'{z}_Occupants'
    if col_name in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{z} Occupants', mode='lines', line=dict(color=color, width=1.5)
        ), row=4, col=1)

# --- Row 5: Zone Equipment Loads ---
for z, color in zip(ZONES, ZONE_COLORS):
    col_name = f'{z}_EquipLoad_W'
    if col_name in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{z} Equip Load', mode='lines', line=dict(color=color, width=1.5)
        ), row=5, col=1)

# --- Row 6: Zone Flows ---
for z, color in zip(ZONES, ZONE_COLORS):
    fig.add_trace(go.Scatter(
        x=df['Datetime'], y=df[f'{z}_VAV_Flow_kg_s'],
        name=f'{z} Flow', mode='lines', line=dict(color=color, width=1.5)
    ), row=6, col=1)

# --- Row 7: Zone Reheaters ---
for z, color in zip(ZONES, ZONE_COLORS):
    col_name = f'{z}_Reheater_W'
    if col_name in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{z} Reheater', mode='lines', line=dict(color=color, width=1.5),
            fill='tozeroy'
        ), row=7, col=1)


# --- Central Node Definitions ---
central_nodes = [
    ('Outdoor_Air', 'Outdoor Intake', 'white'),
    ('Relief_Air', 'Relief Exhaust', 'gray'),
    ('Mixer_Inlet', 'Total Return Air', '#EF553B'),
    ('Mixed_Air', 'Mixed Air to AHU', '#636EFA'),
    ('CC_Out', 'Cooling Coil Out', '#00CC96'),
    ('HC_Out', 'Heating Coil Out', '#FFA15A'),
    ('Fan_Out', 'Supply Fan Out', '#19D3F3')
]

# --- Row 8: AHU Temperatures ---
for prefix, label, color in central_nodes:
    col_name = f"{prefix}_Temp_C"
    if col_name in df.columns:
        dash = 'dot' if 'Outdoor' in prefix or 'Relief' in prefix else 'solid'
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{label} Temp', mode='lines', line=dict(color=color, width=1.5, dash=dash)
        ), row=8, col=1)

# --- Row 9: AHU CO2 ---
for prefix, label, color in central_nodes:
    col_name = f"{prefix}_CO2_ppm"
    if col_name in df.columns:
        dash = 'dot' if 'Outdoor' in prefix or 'Relief' in prefix else 'solid'
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{label} CO₂', mode='lines', line=dict(color=color, width=1.5, dash=dash)
        ), row=9, col=1)

# --- Row 10: AHU Humidities ---
for prefix, label, color in central_nodes:
    col_name = f"{prefix}_RH_pct"
    if col_name in df.columns:
        dash = 'dot' if 'Outdoor' in prefix or 'Relief' in prefix else 'solid'
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{label} RH', mode='lines', line=dict(color=color, width=1.5, dash=dash)
        ), row=10, col=1)

# --- Row 11: AHU Flows ---
for prefix, label, color in central_nodes:
    col_name = f"{prefix}_Flow_kg_s"
    if col_name in df.columns:
        dash = 'dot' if 'Outdoor' in prefix or 'Relief' in prefix else 'solid'
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=f'{label} Flow', mode='lines', line=dict(color=color, width=2, dash=dash)
        ), row=11, col=1)

# --- Row 12: Central AHU Equipment Actuation ---
if 'CC_Power_W' in df.columns:
    fig.add_trace(go.Scatter(
        x=df['Datetime'], y=df['CC_Power_W'],
        name='Cooler (W)', mode='lines', line=dict(color='#00CC96', width=2), fill='tozeroy'
    ), row=12, col=1)

if 'HC_Power_W' in df.columns:
    fig.add_trace(go.Scatter(
        x=df['Datetime'], y=df['HC_Power_W'],
        name='Heater (W)', mode='lines', line=dict(color='#FFA15A', width=2), fill='tozeroy'
    ), row=12, col=1)

if 'Fan_Power_W' in df.columns:
    fig.add_trace(go.Scatter(
        x=df['Datetime'], y=df['Fan_Power_W'],
        name='Fan (W)', mode='lines', line=dict(color='#19D3F3', width=2), fill='tozeroy'
    ), row=12, col=1)


# 5. Dashboard Layout & Theming
fig.update_layout(
    title="MPC Whole System Performance Dashboard",
    template="plotly_dark",
    height=3200,             
    hovermode="x unified",
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.01,
        xanchor="center",
        x=0.5
    )
)

# Update axis titles
fig.update_yaxes(title_text="Temp (°C)", row=1, col=1)
fig.update_yaxes(title_text="RH (%)", row=2, col=1)
fig.update_yaxes(title_text="CO₂ (ppm)", row=3, col=1)
fig.update_yaxes(title_text="Persons", row=4, col=1)
fig.update_yaxes(title_text="Load (W)", row=5, col=1)
fig.update_yaxes(title_text="Flow (kg/s)", row=6, col=1)
fig.update_yaxes(title_text="Power (W)", row=7, col=1)
fig.update_yaxes(title_text="AHU Temp (°C)", row=8, col=1)
fig.update_yaxes(title_text="AHU CO₂ (ppm)", row=9, col=1)
fig.update_yaxes(title_text="AHU RH (%)", row=10, col=1)
fig.update_yaxes(title_text="AHU Flow (kg/s)", row=11, col=1)
fig.update_yaxes(title_text="Power (W)", row=12, col=1)
fig.update_xaxes(title_text="Time", row=12, col=1)

# Render the plot
fig.show()
