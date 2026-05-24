import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

df = pd.read_csv("./baseline_results/state_log.csv").iloc[::12] # Hourly
ZONES = ["SPACE1-1", "SPACE2-1", "SPACE3-1", "SPACE4-1", "SPACE5-1"]

grid_map = np.zeros((30, 30), dtype=int)
for y in range(30):
    for x in range(30):
        if 10 <= x <= 20 and 10 <= y <= 20: grid_map[y, x] = 4
        elif y < x and y < 30-x: grid_map[y, x] = 0
        elif y < x and y >= 30-x: grid_map[y, x] = 1
        elif y >= x and y >= 30-x: grid_map[y, x] = 2
        else: grid_map[y, x] = 3

def get_grid(df_row, param_suffix):
    grid = np.zeros((30, 30))
    for i, z in enumerate(ZONES):
        col = f'{z}_{param_suffix}'
        val = df_row[col] if col in df_row else 0
        grid[grid_map == i] = val
    return grid

fig = make_subplots(rows=2, cols=2, subplot_titles=("Temp", "RH", "CO2", "Occ"))
row = df.iloc[10]

fig.add_trace(go.Heatmap(z=get_grid(row, 'Temp_C'), colorscale='RdBu_r'), row=1, col=1)
fig.add_trace(go.Heatmap(z=get_grid(row, 'RH_pct'), colorscale='Blues'), row=1, col=2)
fig.add_trace(go.Heatmap(z=get_grid(row, 'CO2_ppm'), colorscale='YlOrRd'), row=2, col=1)
fig.add_trace(go.Heatmap(z=get_grid(row, 'Occupants'), colorscale='Greens'), row=2, col=2)

fig.write_html("test_bim.html")
print("OK")
