#!/bin/bash
set -e

# Detect if conda is installed
if ! command -v conda &> /dev/null; then
    echo "Error: 'conda' command not found."
    echo "Please install Anaconda or Miniconda first."
    exit 1
fi

echo "=================================================="
echo "  Setting up Conda Environment for LogFilter"
echo "=================================================="

ENV_NAME="logfilter_gtk"

# Check if environment exists
if conda info --envs | grep -q "^$ENV_NAME"; then
    echo "Environment '$ENV_NAME' already exists."
else
    echo "Creating new environment '$ENV_NAME'..."
    conda create -n "$ENV_NAME" python=3.12 -y
fi

# We need to activate the environment. 
# This tricky in scripts. We rely on conda hook.
eval "$(conda shell.bash hook)"
conda activate "$ENV_NAME"

echo "--------------------------------------------------"
echo "  Installing GTK3 and PyGObject (conda-forge)"
echo "--------------------------------------------------"
# Install from conda-forge which has the correct binaries for macOS
conda install -c conda-forge gtk3 pygobject adwaita-icon-theme -y

echo "=================================================="
echo "  Setup Complete!"
echo "=================================================="
echo "To run the app, use:"
echo "  conda activate $ENV_NAME"
echo "  python app.py"
echo ""
echo "Attempting to run now..."
python app.py
