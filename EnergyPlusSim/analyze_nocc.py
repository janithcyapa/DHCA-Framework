import pandas as pd
import numpy as np

# Load the state log
df = pd.read_csv('results/state_log.csv')

# Let's extract the columns we care about
cols = ['Hour', 'Minute', 'SPACE1-1_EKF_x_N_occ', 'SPACE1-1_Occupants', 'SPACE1-1_EKF_K_N_occ_from_C_in', 'SPACE1-1_EKF_P_N_occ']
df_subset = df[cols].copy()

# Print some general stats
print("General stats for SPACE1-1 Occupancy:")
print(df_subset[['SPACE1-1_EKF_x_N_occ', 'SPACE1-1_Occupants']].describe())

# Find a time where occupancy is high and print a chunk
day = df_subset[(df_subset['Hour'] >= 8) & (df_subset['Hour'] <= 10)]
print("\nSample during morning:")
print(day.head(20).to_string(index=False))
