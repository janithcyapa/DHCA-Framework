#!/usr/bin/env bash
# ============================================================
# switch_weather.sh — Switch active EnergyPlus weather data
# ============================================================
# Usage:
#   ./switch_weather.sh chicago        → Chicago O'Hare (TMY3)
#   ./switch_weather.sh colombo        → Colombo/Katunayake, Sri Lanka (SWERA)
#   ./switch_weather.sh                → show current weather + options
#
# This script does THREE things on each switch:
#   1. Copies the named .epw  → weather.epw  (used by -w flag)
#   2. Copies the named .ddy  → weather.ddy  (design-day reference)
#   3. Patches 5ZoneAutoDXVAV.idf:
#        • Site:Location        (lat/lon/timezone/elevation)
#        • SizingPeriod:DesignDay (heating + cooling design conditions)
#
# After switching, run your simulation normally:
#   energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IDF="5ZoneAutoDXVAV.idf"
ACTIVE_EPW="weather.epw"
ACTIVE_DDY="weather.ddy"
PATCHER="$SCRIPT_DIR/patch_idf.py"
HTG_TMP="/tmp/_ep_switch_htg.idf"
CLG_TMP="/tmp/_ep_switch_clg.idf"

# ── Helpers ──────────────────────────────────────────────────
show_current() {
    if [ -f "$ACTIVE_EPW" ]; then
        HEADER=$(head -1 "$ACTIVE_EPW")
        echo "  Active EPW  : $ACTIVE_EPW"
        echo "  Location    : $HEADER"
    else
        echo "  No active weather.epw found in $SCRIPT_DIR"
    fi
    if [ -f "$ACTIVE_DDY" ]; then
        echo "  Active DDY  : $ACTIVE_DDY (present)"
    else
        echo "  Active DDY  : weather.ddy (not present)"
    fi
    IDF_LOC=$(grep -A2 'Site:Location' "$IDF" 2>/dev/null | tail -1 | xargs)
    echo "  IDF Site    : ${IDF_LOC:-unknown}"
}

run_patcher() {
    local loc_name="$1" lat="$2" lon="$3" tz_off="$4" elev="$5"
    IDF_PATH="$SCRIPT_DIR/$IDF" \
    LOC_NAME="$loc_name" \
    LAT="$lat" \
    LON="$lon" \
    TZ_OFFSET="$tz_off" \
    ELEV="$elev" \
    HTG_FILE="$HTG_TMP" \
    CLG_FILE="$CLG_TMP" \
    python3 "$PATCHER"
}

# ── Weather profile: CHICAGO ─────────────────────────────────
activate_chicago() {
    local EPW="chicago_ohare.epw"
    local DDY="chicago_ohare.ddy"

    [ -f "$EPW" ] || { echo "ERROR: $EPW not found"; exit 1; }
    cp "$EPW" "$ACTIVE_EPW"
    cp "$DDY" "$ACTIVE_DDY"

    cat > "$HTG_TMP" <<'DDY'
SizingPeriod:DesignDay,
    CHICAGO_IL_USA Annual Heating 99% Design Conditions DB,  !- Name
    1,                       !- Month
    8,                       !- Day of Month
    WinterDesignDay,         !- Day Type
    -17.3,                   !- Maximum Dry-Bulb Temperature {C}
    0.0,                     !- Daily Dry-Bulb Temperature Range {deltaC}
    ,                        !- Dry-Bulb Temperature Range Modifier Type
    ,                        !- Dry-Bulb Temperature Range Modifier Day Schedule Name
    Wetbulb,                 !- Humidity Condition Type
    -17.3,                   !- Wetbulb or DewPoint at Maximum Dry-Bulb {C}
    ,                        !- Humidity Condition Day Schedule Name
    ,                        !- Humidity Ratio at Maximum Dry-Bulb {kgWater/kgDryAir}
    ,                        !- Enthalpy at Maximum Dry-Bulb {J/kg}
    ,                        !- Daily Wet-Bulb Temperature Range {deltaC}
    99063.,                  !- Barometric Pressure {Pa}
    4.9,                     !- Wind Speed {m/s}
    270,                     !- Wind Direction {deg}
    No,                      !- Rain Indicator
    No,                      !- Snow Indicator
    No,                      !- Daylight Saving Time Indicator
    ASHRAEClearSky,          !- Solar Model Indicator
    ,                        !- Beam Solar Day Schedule Name
    ,                        !- Diffuse Solar Day Schedule Name
    ,                        !- ASHRAE Clear Sky Optical Depth for Beam Irradiance (taub) {dimensionless}
    ,                        !- ASHRAE Clear Sky Optical Depth for Diffuse Irradiance (taud) {dimensionless}
    0.0;                     !- Sky Clearness
DDY

    cat > "$CLG_TMP" <<'DDY'
SizingPeriod:DesignDay,
    CHICAGO_IL_USA Annual Cooling 1% Design Conditions DB/MCWB,  !- Name
    7,                       !- Month
    3,                       !- Day of Month
    SummerDesignDay,         !- Day Type
    31.5,                    !- Maximum Dry-Bulb Temperature {C}
    10.7,                    !- Daily Dry-Bulb Temperature Range {deltaC}
    ,                        !- Dry-Bulb Temperature Range Modifier Type
    ,                        !- Dry-Bulb Temperature Range Modifier Day Schedule Name
    Wetbulb,                 !- Humidity Condition Type
    23.0,                    !- Wetbulb or DewPoint at Maximum Dry-Bulb {C}
    ,                        !- Humidity Condition Day Schedule Name
    ,                        !- Humidity Ratio at Maximum Dry-Bulb {kgWater/kgDryAir}
    ,                        !- Enthalpy at Maximum Dry-Bulb {J/kg}
    ,                        !- Daily Wet-Bulb Temperature Range {deltaC}
    99063.,                  !- Barometric Pressure {Pa}
    5.3,                     !- Wind Speed {m/s}
    230,                     !- Wind Direction {deg}
    No,                      !- Rain Indicator
    No,                      !- Snow Indicator
    No,                      !- Daylight Saving Time Indicator
    ASHRAEClearSky,          !- Solar Model Indicator
    ,                        !- Beam Solar Day Schedule Name
    ,                        !- Diffuse Solar Day Schedule Name
    ,                        !- ASHRAE Clear Sky Optical Depth for Beam Irradiance (taub) {dimensionless}
    ,                        !- ASHRAE Clear Sky Optical Depth for Diffuse Irradiance (taud) {dimensionless}
    1.0;                     !- Sky Clearness
DDY

    echo "✔  Switching to: Chicago O'Hare, IL, USA (TMY3)"
    run_patcher "CHICAGO_IL_USA TMY2-94846" "41.78" "-87.75" "-6.00" "190.00"
    echo "   EPW + DDY → $ACTIVE_EPW / $ACTIVE_DDY"
    echo ""
    echo "Run simulation:"
    echo "  energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf"
}

# ── Weather profile: COLOMBO ─────────────────────────────────
activate_colombo() {
    local EPW="colombo_katunayake.epw"
    local DDY="colombo_katunayake.ddy"

    [ -f "$EPW" ] || { echo "ERROR: $EPW not found"; exit 1; }
    cp "$EPW" "$ACTIVE_EPW"
    cp "$DDY" "$ACTIVE_DDY"

    # Heating: tropical "winter" — barely cools, 99.6% DB = 20.9°C
    cat > "$HTG_TMP" <<'DDY'
SizingPeriod:DesignDay,
    COLOMBO/KATUNAYAKE Ann Htg 99.6% Condns DB,  !- Name
    12,                      !- Month
    21,                      !- Day of Month
    WinterDesignDay,         !- Day Type
    20.9,                    !- Maximum Dry-Bulb Temperature {C}
    0.0,                     !- Daily Dry-Bulb Temperature Range {deltaC}
    DefaultMultipliers,      !- Dry-Bulb Temperature Range Modifier Type
    ,                        !- Dry-Bulb Temperature Range Modifier Day Schedule Name
    Wetbulb,                 !- Humidity Condition Type
    20.9,                    !- Wetbulb or DewPoint at Maximum Dry-Bulb {C}
    ,                        !- Humidity Condition Day Schedule Name
    ,                        !- Humidity Ratio at Maximum Dry-Bulb {kgWater/kgDryAir}
    ,                        !- Enthalpy at Maximum Dry-Bulb {J/kg}
    ,                        !- Daily Wet-Bulb Temperature Range {deltaC}
    101229.,                 !- Barometric Pressure {Pa}
    2.5,                     !- Wind Speed {m/s}
    50,                      !- Wind Direction {deg}
    No,                      !- Rain Indicator
    No,                      !- Snow Indicator
    No,                      !- Daylight Saving Time Indicator
    ASHRAEClearSky,          !- Solar Model Indicator
    ,                        !- Beam Solar Day Schedule Name
    ,                        !- Diffuse Solar Day Schedule Name
    ,                        !- ASHRAE Clear Sky Optical Depth for Beam Irradiance (taub) {dimensionless}
    ,                        !- ASHRAE Clear Sky Optical Depth for Diffuse Irradiance (taud) {dimensionless}
    0.00;                    !- Sky Clearness
DDY

    # Cooling: 1% DB/MWB — 32.6°C / 25.5°C (May peak)
    cat > "$CLG_TMP" <<'DDY'
SizingPeriod:DesignDay,
    COLOMBO/KATUNAYAKE Ann Clg 1% Condns DB/MWB,  !- Name
    5,                       !- Month
    21,                      !- Day of Month
    SummerDesignDay,         !- Day Type
    32.6,                    !- Maximum Dry-Bulb Temperature {C}
    4.9,                     !- Daily Dry-Bulb Temperature Range {deltaC}
    DefaultMultipliers,      !- Dry-Bulb Temperature Range Modifier Type
    ,                        !- Dry-Bulb Temperature Range Modifier Day Schedule Name
    Wetbulb,                 !- Humidity Condition Type
    25.5,                    !- Wetbulb or DewPoint at Maximum Dry-Bulb {C}
    ,                        !- Humidity Condition Day Schedule Name
    ,                        !- Humidity Ratio at Maximum Dry-Bulb {kgWater/kgDryAir}
    ,                        !- Enthalpy at Maximum Dry-Bulb {J/kg}
    ,                        !- Daily Wet-Bulb Temperature Range {deltaC}
    101229.,                 !- Barometric Pressure {Pa}
    5.7,                     !- Wind Speed {m/s}
    270,                     !- Wind Direction {deg}
    No,                      !- Rain Indicator
    No,                      !- Snow Indicator
    No,                      !- Daylight Saving Time Indicator
    ASHRAETau,               !- Solar Model Indicator
    ,                        !- Beam Solar Day Schedule Name
    ,                        !- Diffuse Solar Day Schedule Name
    0.537,                   !- ASHRAE Clear Sky Optical Depth for Beam Irradiance (taub) {dimensionless}
    1.91;                    !- ASHRAE Clear Sky Optical Depth for Diffuse Irradiance (taud) {dimensionless}
DDY

    echo "✔  Switching to: Colombo/Katunayake, Sri Lanka (SWERA)"
    run_patcher "COLOMBO/KATUNAYAKE_LKA Design_Conditions" "7.17" "79.88" "6.00" "8.00"
    echo "   EPW + DDY → $ACTIVE_EPW / $ACTIVE_DDY"
    echo ""
    echo "Run simulation:"
    echo "  energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf"
}

# ── Main ─────────────────────────────────────────────────────
CHOICE="${1,,}"

case "$CHOICE" in
    chicago|chi|us)
        activate_chicago
        ;;
    colombo|lka|sri|lanka|sl)
        activate_colombo
        ;;
    "")
        echo "============================================="
        echo " EnergyPlus Weather Switcher"
        echo "============================================="
        echo ""
        echo "Current active weather:"
        show_current
        echo ""
        echo "Available profiles:"
        echo "  chicago  — Chicago O'Hare, IL, USA (TMY3)"
        echo "  colombo  — Colombo/Katunayake, Sri Lanka (SWERA)"
        echo ""
        echo "Usage:"
        echo "  ./switch_weather.sh chicago"
        echo "  ./switch_weather.sh colombo"
        echo ""
        echo "Then run simulation:"
        echo "  energyplus -w weather.epw -d ./baseline_results 5ZoneAutoDXVAV.idf"
        echo "============================================="
        ;;
    *)
        echo "ERROR: Unknown weather profile '${1}'"
        echo "Use: chicago | colombo"
        exit 1
        ;;
esac
