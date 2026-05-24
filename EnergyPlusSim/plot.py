import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# 1. Configuration
CSV_PATH = "./baseline_results/state_log.csv"
TARGET_ZONE = "SPACE1-1" # Make sure to define the TARGET_ZONE

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

# 4. Create the Plotly Subplots
# Now using 4 rows to keep Central Loop Flow and Zone Flow on separate axes
fig = make_subplots(
    rows=4, cols=1, 
    shared_xaxes=True,
    vertical_spacing=0.06,
    subplot_titles=(
        f"Temperature Dynamics (°C)", 
        f"Relative Humidity (%)", 
        f"Zone VAV Supply Mass Flow (kg/s)",
        f"Central Air Loop Mass Flow (kg/s)"
    )
)

# --- Row 1: Temperature (Zone vs. Outdoor) ---
fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df['Out_Temp_C'],
    name='Outdoor Temp',
    mode='lines',
    line=dict(color='#FFA15A', width=2)
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df[f'{TARGET_ZONE}_Temp_C'],
    name=f'{TARGET_ZONE} Temp',
    mode='lines',
    line=dict(color='#00CC96', width=2)
), row=1, col=1)


# --- Row 2: Relative Humidity (Zone vs. Outdoor) ---
fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df['Out_RH_pct'],
    name='Outdoor RH',
    mode='lines',
    line=dict(color='#FFA15A', width=2, dash='dot')
), row=2, col=1)

fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df[f'{TARGET_ZONE}_RH_pct'],
    name=f'{TARGET_ZONE} RH',
    mode='lines',
    line=dict(color='#00CC96', width=2)
), row=2, col=1)


# --- Row 3: VAV Mass Flow Rate (Target Zone) ---
fig.add_trace(go.Scatter(
    x=df['Datetime'], y=df[f'{TARGET_ZONE}_VAV_Flow_kg_s'],
    name=f'{TARGET_ZONE} VAV Flow',
    mode='lines',
    fill='tozeroy',
    line=dict(color='#AB63FA', width=2)
), row=3, col=1)


# --- Row 4: Central Air Loop Mass Flow Rates ---
# We overlay the central node flows to verify mass conservation across the loop
central_nodes = [
    ('Mixer_Inlet_Flow_kg_s', 'Return Air (Mixer Inlet)', '#EF553B'),
    ('Mixed_Air_Flow_kg_s', 'Mixed Air (Cooling Coil Inlet)', '#636EFA'),
    ('CC_Out_Flow_kg_s', 'Cooling Coil Out', '#00CC96'),
    ('HC_Out_Flow_kg_s', 'Heating Coil Out', '#FFA15A'),
    ('Fan_Out_Flow_kg_s', 'Supply Fan Out', '#19D3F3')
]

for col_name, label, color in central_nodes:
    if col_name in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Datetime'], y=df[col_name],
            name=label,
            mode='lines',
            line=dict(color=color, width=1.5, dash='dash' if 'Mixer' in col_name else 'solid')
        ), row=4, col=1)

# 5. Dashboard Layout & Theming
fig.update_layout(
    title=f"MPC Zone Performance Dashboard: {TARGET_ZONE}",
    template="plotly_dark",
    height=1100,             # Increased height to accommodate the 4th row
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    )
)

# Update axis titles
fig.update_yaxes(title_text="Temp (°C)", row=1, col=1)
fig.update_yaxes(title_text="RH (%)", row=2, col=1)
fig.update_yaxes(title_text="Zone Flow (kg/s)", row=3, col=1)
fig.update_yaxes(title_text="Loop Flow (kg/s)", row=4, col=1)
fig.update_xaxes(title_text="Time", row=4, col=1)

# Render the plot
fig.show()
