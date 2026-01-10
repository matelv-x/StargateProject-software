#!/bin/bash
# Wrapper script to run main.py with sudo and debugpy for VS Code debugging
# This script starts Python with debugpy and waits for the debugger to attach

cd "$(dirname "$0")"

# Determine the virtual environment path
VENV_PATH="${VIRTUAL_ENV:-venv_dev}"
PYTHON_PATH="${VENV_PATH}/bin/python"

# Install debugpy if not already installed
"${PYTHON_PATH}" -m pip install --quiet debugpy > /dev/null 2>&1

# Start Python with debugpy and wait for debugger to attach on port 5678
exec sudo -E "${PYTHON_PATH}" 
# -m debugpy --listen 0.0.0.0:5678 --wait-for-client main.py "$@"

