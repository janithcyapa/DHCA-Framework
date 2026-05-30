import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import copy

# 1. Configuration
CSV_PATH = "./baseline_results/state_log.csv"
ZONES = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]
COLOR_OUTDOOR = 'white'
COLOR_AC = '#19D3F3'

# 2. Load the Data
df = pd.read_csv(CSV_PATH)

def eplus_time_to_datetime(row, year=2026):
    base_date = datetime.datetime(year, 1, 1)
    delta = datetime.timedelta(days=int(row['DayOfYear']) - 1, 
                               hours=int(row['Hour']), 
                               minutes=int(row['Minute']))
    return base_date + delta

df['Datetime'] = df.apply(eplus_time_to_datetime, axis=1)

# 3. Create the Plotly Subplots
fig = make_subplots(
    rows=5, cols=1, 
    shared_xaxes=True,
    vertical_spacing=0.06,
    specs=[
        [{"secondary_y": False}],
        [{"secondary_y": True}],
        [{"secondary_y": False}],
        [{"secondary_y": True}],
        [{"secondary_y": True}],
    ],
    subplot_titles=("Temp", "Humidity", "CO2", "Occ", "Flow") # Placeholders
)

view_traces = {z: [] for z in ZONES}
view_traces["AHU"] = []

trace_index = 0

def add_t(trace, view_name, row, col, secondary_y=False):
    global trace_index
    trace.visible = False
    
    # Assign trace to a specific legendgroup for this row
    trace.update(legendgroup=str(row))
    
    fig.add_trace(trace, row=row, col=col, secondary_y=secondary_y)
    view_traces[view_name].append(trace_index)
    trace_index += 1

# --- ZONE TRACES ---
for z in ZONES:
    # Row 1: Temp (T_in and T_m)
    add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_Temp_C'], name=f'{z} Sim T_in', line=dict(color='#EF553B')), z, row=1, col=1)
    if f'{z}_T_in_theo' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_T_in_theo'], name=f'{z} Theo T_in', line=dict(color='#EF553B', dash='dash')), z, row=1, col=1)
    if f'{z}_T_in_est' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_T_in_est'], name=f'{z} EKF T_in', line=dict(color='yellow', dash='dot')), z, row=1, col=1)
        
    if f'{z}_T_m_C' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_T_m_C'], name=f'{z} Sim T_m', line=dict(color='#FFA15A')), z, row=1, col=1)
    if f'{z}_T_m_theo' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_T_m_theo'], name=f'{z} Theo T_m', line=dict(color='#FFA15A', dash='dash')), z, row=1, col=1)
    if f'{z}_T_m_est' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_T_m_est'], name=f'{z} EKF T_m', line=dict(color='#FFA15A', dash='dot')), z, row=1, col=1)
        
    add_t(go.Scatter(x=df['Datetime'], y=df['Out_Temp_C'], name='Outdoor Temp', line=dict(color=COLOR_OUTDOOR, dash='dot')), z, row=1, col=1)
    add_t(go.Scatter(x=df['Datetime'], y=df['Fan_Out_Temp_C'], name='AC Supply Temp', line=dict(color=COLOR_AC, dash='dashdot')), z, row=1, col=1)

    # Row 2: RH and W_in
    add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_RH_pct'], name=f'{z} Inside RH (%)', line=dict(color='#00CC96')), z, row=2, col=1, secondary_y=False)
    add_t(go.Scatter(x=df['Datetime'], y=df['Out_RH_pct'], name='Outdoor RH (%)', line=dict(color=COLOR_OUTDOOR, dash='dot')), z, row=2, col=1, secondary_y=False)
    add_t(go.Scatter(x=df['Datetime'], y=df['Fan_Out_RH_pct'], name='AC Supply RH (%)', line=dict(color=COLOR_AC, dash='dashdot')), z, row=2, col=1, secondary_y=False)
    
    if f'{z}_W_in_kg_kg' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_W_in_kg_kg'], name=f'{z} Sim W_in', line=dict(color='#19D3F3')), z, row=2, col=1, secondary_y=True)
    if f'{z}_W_in_theo' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_W_in_theo'], name=f'{z} Theo W_in', line=dict(color='#19D3F3', dash='dash')), z, row=2, col=1, secondary_y=True)
    if f'{z}_W_in_est' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_W_in_est'], name=f'{z} EKF W_in', line=dict(color='yellow', dash='dot')), z, row=2, col=1, secondary_y=True)

    # Row 3: CO2
    col_co2 = f'{z}_CO2_ppm' if f'{z}_CO2_ppm' in df.columns else 'Outdoor_Air_CO2_ppm'
    add_t(go.Scatter(x=df['Datetime'], y=df[col_co2], name=f'{z} Sim CO₂', line=dict(color='#AB63FA')), z, row=3, col=1)
    if f'{z}_C_in_theo' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_C_in_theo'], name=f'{z} Theo CO₂', line=dict(color='#AB63FA', dash='dash')), z, row=3, col=1)
    if f'{z}_C_in_est' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_C_in_est'], name=f'{z} EKF CO₂', line=dict(color='pink', dash='dot')), z, row=3, col=1)
    add_t(go.Scatter(x=df['Datetime'], y=df['Outdoor_Air_CO2_ppm'], name='Outdoor CO₂', line=dict(color=COLOR_OUTDOOR, dash='dot')), z, row=3, col=1)
    add_t(go.Scatter(x=df['Datetime'], y=df['Fan_Out_CO2_ppm'], name='AC Supply CO₂', line=dict(color=COLOR_AC, dash='dashdot')), z, row=3, col=1)

    # Row 4: Occ & Heat
    col_occ = f'{z}_Occupants' if f'{z}_Occupants' in df.columns else 'Out_Temp_C'
    col_equip = f'{z}_EquipLoad_W' if f'{z}_EquipLoad_W' in df.columns else 'Out_Temp_C'
    add_t(go.Scatter(x=df['Datetime'], y=df[col_occ], name=f'{z} Occupants', fill='tozeroy', line=dict(color='#FFA15A')), z, row=4, col=1, secondary_y=False)
    if f'{z}_Occ_est' in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{z}_Occ_est'], name=f'{z} EKF Occ Est', line=dict(color='yellow', dash='dot')), z, row=4, col=1, secondary_y=False)
    add_t(go.Scatter(x=df['Datetime'], y=df[col_equip], name=f'{z} Internal Heat (W)', line=dict(color='#FF6692')), z, row=4, col=1, secondary_y=True)

    # Row 5: VAV Flow & Reheat
    col_vav = f'{z}_VAV_Flow_kg_s'
    col_reheat = f'{z}_Reheater_W' if f'{z}_Reheater_W' in df.columns else 'Out_Temp_C'
    add_t(go.Scatter(x=df['Datetime'], y=df[col_vav], name=f'{z} VAV Flow (kg/s)', fill='tozeroy', line=dict(color='#19D3F3')), z, row=5, col=1, secondary_y=False)
    add_t(go.Scatter(x=df['Datetime'], y=df[col_reheat], name=f'{z} Reheat Actuation (W)', line=dict(color='#FF97FF')), z, row=5, col=1, secondary_y=True)

# --- AHU TRACES ---
central_nodes = [
    ('Outdoor_Air', 'Outdoor Intake', 'white'),
    ('Relief_Air', 'Relief Exhaust', 'gray'),
    ('Mixer_Inlet', 'Total Return Air', '#EF553B'),
    ('Mixed_Air', 'Mixed Air to AHU', '#636EFA'),
    ('CC_Out', 'Cooling Coil Out', '#00CC96'),
    ('HC_Out', 'Heating Coil Out', '#FFA15A'),
    ('Fan_Out', 'Supply Fan Out', '#19D3F3')
]
v_ahu = "AHU"
for prefix, label, color in central_nodes:
    dash = 'dot' if 'Outdoor' in prefix or 'Relief' in prefix else 'solid'
    
    if f"{prefix}_Temp_C" in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{prefix}_Temp_C'], name=f'{label} Temp', line=dict(color=color, dash=dash)), v_ahu, row=1, col=1)
    if f"{prefix}_RH_pct" in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{prefix}_RH_pct'], name=f'{label} RH', line=dict(color=color, dash=dash)), v_ahu, row=2, col=1)
    if f"{prefix}_CO2_ppm" in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{prefix}_CO2_ppm'], name=f'{label} CO₂', line=dict(color=color, dash=dash)), v_ahu, row=3, col=1)
    if f"{prefix}_Flow_kg_s" in df.columns:
        add_t(go.Scatter(x=df['Datetime'], y=df[f'{prefix}_Flow_kg_s'], name=f'{label} Flow', line=dict(color=color, dash=dash)), v_ahu, row=4, col=1, secondary_y=False)

if 'CC_Power_W' in df.columns:
    add_t(go.Scatter(x=df['Datetime'], y=df['CC_Power_W'], name='Cooler (W)', line=dict(color='#00CC96')), v_ahu, row=5, col=1, secondary_y=False)
if 'HC_Power_W' in df.columns:
    add_t(go.Scatter(x=df['Datetime'], y=df['HC_Power_W'], name='Heater (W)', line=dict(color='#FFA15A')), v_ahu, row=5, col=1, secondary_y=False)
if 'Fan_Power_W' in df.columns:
    add_t(go.Scatter(x=df['Datetime'], y=df['Fan_Power_W'], name='Fan (W)', line=dict(color='#19D3F3')), v_ahu, row=5, col=1, secondary_y=False)
if 'Outdoor_Air_Flow_kg_s' in df.columns:
    add_t(go.Scatter(x=df['Datetime'], y=df['Outdoor_Air_Flow_kg_s'], name='Mixer OA Actuator (kg/s)', line=dict(color='white', dash='dot')), v_ahu, row=5, col=1, secondary_y=True)

# --- Dropdown Logic ---
buttons = []
base_annotations = list(fig.layout.annotations)

for view_name in view_traces.keys():
    visible_array = [False] * trace_index
    for idx in view_traces[view_name]:
        visible_array[idx] = True
        
    if "SPACE" in view_name:
        layout_updates = {
            "title": f"Interactive Performance Dashboard - {view_name}",
            "yaxis.title.text": "Temperature (°C)",
            "yaxis2.title.text": "Relative Humidity (%)",
            "yaxis3.title.text": "CO₂ (ppm)",
            "yaxis4.title.text": "Occupants",
            "yaxis5.title.text": "Heat Load (W)",
            "yaxis6.title.text": "VAV Flow (kg/s)",
            "yaxis7.title.text": "Reheat Actuation (W)"
        }
        annots = [
            f"{view_name} Temperatures (Inside, Outside, AC Supply)",
            f"{view_name} Relative Humidities",
            f"{view_name} CO₂ Concentrations",
            f"{view_name} Occupancy & Internal Heat Load",
            f"{view_name} VAV Box Flow & Reheater Actuation"
        ]
    else:
        layout_updates = {
            "title": "Interactive Performance Dashboard - Central AHU",
            "yaxis.title.text": "Temperature (°C)",
            "yaxis2.title.text": "Relative Humidity (%)",
            "yaxis3.title.text": "CO₂ (ppm)",
            "yaxis4.title.text": "Mass Flow (kg/s)",
            "yaxis5.title.text": "",
            "yaxis6.title.text": "Equipment Power (W)",
            "yaxis7.title.text": "Mixer OA Flow (kg/s)"
        }
        annots = [
            "AHU Temperatures (°C)",
            "AHU Relative Humidities (%)",
            "AHU CO₂ Concentrations (ppm)",
            "AHU Mass Flows (kg/s)",
            "AHU Actuator Signals (Cooler, Heater, Fan, OA Mixer)"
        ]
        
    new_annotations = copy.deepcopy(base_annotations)
    for i, ann in enumerate(annots):
        if i < len(new_annotations):
            new_annotations[i]['text'] = ann
    layout_updates["annotations"] = new_annotations
        
    button = dict(
        label=view_name,
        method="update",
        args=[
            {"visible": visible_array},
            layout_updates
        ]
    )
    buttons.append(button)

# --- IAQ Comfort Zones ---
fig.add_hrect(y0=40, y1=60, row=2, col=1, fillcolor="green", opacity=0.1, line_width=0, layer="below", annotation_text="ASHRAE Comfort", annotation_position="top left")
fig.add_hrect(y0=400, y1=1000, row=3, col=1, fillcolor="green", opacity=0.1, line_width=0, layer="below", annotation_text="ASHRAE Target", annotation_position="top left")

# Turn on first view (SPACE1-1)
for idx in view_traces["SPACE1-1"]:
    fig.data[idx].visible = True

# --- Single Legend Configuration ---
legend_layout = dict(
    legend=dict(
        y=1,
        yanchor="top",
        # Push x far enough right to clear the secondary y-axis labels
        x=1.06, 
        xanchor="left",
        font=dict(size=10),
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(255,255,255,0.2)",
        borderwidth=1,
        tracegroupgap=10
    )
)

# Add Dropdown to layout
fig.update_layout(
    **legend_layout,
    margin=dict(r=200), # Make room on the right for legends
    updatemenus=[dict(
        active=0,
        buttons=buttons,
        x=0.5,
        y=1.06, 
        xanchor="center",
        yanchor="top",
        direction="down",
        showactive=True,
        bgcolor="#333",
        font=dict(color="white")
    )],
    title="Interactive Performance Dashboard - SPACE1-1",
    template="plotly_dark",
    height=1600,
    hovermode="x unified",
    showlegend=True
)

# Apply initial titles directly
fig.update_yaxes(title_text="Temperature (°C)", row=1, col=1)
fig.update_yaxes(title_text="Relative Humidity (%)", row=2, col=1)
fig.update_yaxes(title_text="CO₂ (ppm)", row=3, col=1)
fig.update_yaxes(title_text="Occupants", row=4, col=1, secondary_y=False)
fig.update_yaxes(title_text="Heat Load (W)", row=4, col=1, secondary_y=True)
fig.update_yaxes(title_text="VAV Flow (kg/s)", row=5, col=1, secondary_y=False)
fig.update_yaxes(title_text="Reheat (W)", row=5, col=1, secondary_y=True)

fig.layout.annotations[0].update(text="SPACE1-1 Temperatures (Inside, Outside, AC Supply)")
fig.layout.annotations[1].update(text="SPACE1-1 Relative Humidities")
fig.layout.annotations[2].update(text="SPACE1-1 CO₂ Concentrations")
fig.layout.annotations[3].update(text="SPACE1-1 Occupancy & Internal Heat Load")
fig.layout.annotations[4].update(text="SPACE1-1 VAV Box Flow & Reheater Actuation")

fig.show()
