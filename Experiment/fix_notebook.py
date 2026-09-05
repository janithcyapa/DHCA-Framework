import json
import os

file_path = "/home/jazz/Projects/DHCA-Framework/Experiment/Advanced Monitor Final copy.ipynb"

with open(file_path, "r") as f:
    nb = json.load(f)

for cell in nb.get("cells", []):
    if cell.get("cell_type") == "code":
        source = cell.get("source", [])
        new_source = []
        for line in source:
            if "df['avg_co2'] = (df['room_2_c'] + df['room_3_c']) / 2.0" in line:
                new_source.append(line.replace(
                    "df['avg_co2'] = (df['room_2_c'] + df['room_3_c']) / 2.0",
                    "df['avg_co2'] = df[['room_2_c', 'room_3_c']].mean(axis=1)"
                ))
            elif "C_in = (row['room_2_c'] + row['room_3_c']) / 2 if row['room_3_c'] != 0 else row['room_2_c']" in line:
                new_source.append(line.replace(
                    "C_in = (row['room_2_c'] + row['room_3_c']) / 2 if row['room_3_c'] != 0 else row['room_2_c']",
                    "C_in = row['avg_co2']"
                ))
            else:
                new_source.append(line)
        cell["source"] = new_source

with open(file_path, "w") as f:
    json.dump(nb, f, indent=1)
