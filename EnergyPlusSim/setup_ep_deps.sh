#!/bin/bash
# Script to create and populate the ep_deps folder for EnergyPlus Python plugin

# Get the directory of this script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
DEPS_DIR="$DIR/ep_deps"

echo "Creating dependency directory at: $DEPS_DIR"
mkdir -p "$DEPS_DIR"

echo "Installing required Python packages into $DEPS_DIR..."
# The --target flag ensures the packages are installed directly into the folder
pip install --target "$DEPS_DIR" numpy scipy osqp jinja2 joblib

echo "Setup complete. The ep_deps folder is ready for the EnergyPlus simulation."
