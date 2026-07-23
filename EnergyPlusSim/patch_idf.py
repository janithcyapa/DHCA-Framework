#!/usr/bin/env python3
"""
patch_idf.py — Patch EnergyPlus IDF Site:Location and SizingPeriod:DesignDay blocks.

Environment variables consumed:
  IDF_PATH, LOC_NAME, LAT, LON, TZ, ELEV, HTG_FILE, CLG_FILE
"""
import os, re, sys

idf_path = os.environ['IDF_PATH']
loc_name = os.environ['LOC_NAME']
lat      = os.environ['LAT']
lon      = os.environ['LON']
tz       = os.environ['TZ_OFFSET']
elev     = os.environ['ELEV']
htg_file = os.environ['HTG_FILE']
clg_file = os.environ['CLG_FILE']

with open(idf_path, 'r') as f:
    content = f.read()

# ── 1. Patch Site:Location ────────────────────────────────────────────────────
loc_pattern = re.compile(
    r'(  Site:Location,\s*\n)'         # "Site:Location,"
    r'([^\n]+\n)'                       # existing name line
    r'(\s*[\d\.\-]+,\s*![^\n]*\n)'    # latitude
    r'(\s*[\d\.\-]+,\s*![^\n]*\n)'    # longitude
    r'(\s*[\d\.\-]+,\s*![^\n]*\n)'    # time zone
    r'(\s*[\d\.\-]+;\s*![^\n]*\n)',    # elevation
    re.IGNORECASE
)

new_loc = (
    f"  Site:Location,\n"
    f"    {loc_name},  !- Name\n"
    f"    {lat},                   !- Latitude {{deg}}\n"
    f"    {lon},                  !- Longitude {{deg}}\n"
    f"    {tz},                   !- Time Zone {{hr}}\n"
    f"    {elev};                  !- Elevation {{m}}\n"
)

content, n_loc = loc_pattern.subn(new_loc, content)
if n_loc == 0:
    print("WARNING: Site:Location block not found in IDF — skipped", file=sys.stderr)
else:
    print(f"  ✔ Site:Location → {loc_name} (lat={lat}, lon={lon}, tz={tz}, elev={elev}m)")

# ── 2. Replace both SizingPeriod:DesignDay blocks ────────────────────────────
with open(htg_file, 'r') as f:
    htg_text = f.read().strip()
with open(clg_file, 'r') as f:
    clg_text = f.read().strip()

dd_pattern = re.compile(
    r'SizingPeriod:DesignDay,.*?;',
    re.DOTALL | re.IGNORECASE
)

blocks = dd_pattern.findall(content)
if len(blocks) < 2:
    print(f"WARNING: Found {len(blocks)} SizingPeriod:DesignDay block(s), expected 2 — skipping", file=sys.stderr)
else:
    count = [0]
    def replacer(m):
        count[0] += 1
        if count[0] == 1:
            return "  " + htg_text
        elif count[0] == 2:
            return "  " + clg_text
        return m.group(0)
    content = dd_pattern.sub(replacer, content)
    print(f"  ✔ SizingPeriod:DesignDay — heating + cooling design days updated")

with open(idf_path, 'w') as f:
    f.write(content)

print(f"  ✔ IDF saved: {idf_path}")
