#!/bin/bash

# Bootstrap script for Stargate Project development environment on macOS (Apple Silicon)
# This script sets up a Python virtual environment with development dependencies

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Virtual environment name
VENV_NAME=".venv"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "=================================================="
echo "Stargate Project - macOS Development Bootstrap"
echo "=================================================="
echo ""

# Check if we're in the project root
if [ ! -f "main.py" ] || [ ! -f "requirements_minimum.txt" ]; then
    echo -e "${RED}Error: This script must be run from the project root directory${NC}"
    echo "Please run: cd /path/to/StargateProject-software && ./bootstrap_dev_macos.sh"
    exit 1
fi

# Check for Python 3
echo "Checking for Python 3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    echo "Please install Python 3.9 or later:"
    echo "  - Using Homebrew: brew install python3"
    echo "  - Or download from: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    echo -e "${RED}Error: Python 3.9 or later is required (found Python $PYTHON_VERSION)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found Python $PYTHON_VERSION${NC}"

# Check for git
echo "Checking for git..."
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Warning: git is not installed${NC}"
    echo "Git is required for the auto-update functionality. Install with: xcode-select --install"
else
    echo -e "${GREEN}✓ Found git${NC}"
fi

# Check for pip
echo "Checking for pip..."
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${RED}Error: pip is not available${NC}"
    echo "Please install pip for Python 3"
    exit 1
fi
echo -e "${GREEN}✓ Found pip${NC}"

# Remove existing virtual environment if it exists
if [ -d "$VENV_NAME" ]; then
    echo ""
    echo -e "${YELLOW}Virtual environment '$VENV_NAME' already exists${NC}"
    read -p "Remove and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing virtual environment..."
        rm -rf "$VENV_NAME"
    else
        echo "Keeping existing virtual environment"
        SKIP_VENV_CREATE=1
    fi
fi

# Create virtual environment
if [ -z "$SKIP_VENV_CREATE" ]; then
    echo ""
    echo "Creating Python virtual environment in '$VENV_NAME'..."
    python3 -m venv "$VENV_NAME"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source "$VENV_NAME/bin/activate"

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip --quiet
echo -e "${GREEN}✓ pip upgraded${NC}"

# Install setuptools
echo ""
echo "Installing setuptools..."
pip install --upgrade setuptools --quiet
echo -e "${GREEN}✓ setuptools installed${NC}"

# Install requirements_minimum.txt (for macOS - no hardware libraries)
echo ""
echo "Installing Python dependencies from requirements_minimum.txt..."
echo "(This may take a few minutes on first run)"
pip install --upgrade -r requirements_minimum.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Optionally install pylint for development
echo ""
read -p "Install pylint for code linting? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Installing pylint..."
    pip install pylint --quiet
    echo -e "${GREEN}✓ pylint installed${NC}"
fi

# Deactivate virtual environment
deactivate

echo ""
echo "=================================================="
echo -e "${GREEN}Development environment setup complete!${NC}"
echo "=================================================="
echo ""
echo "To activate the virtual environment, run:"
echo "  source $VENV_NAME/bin/activate"
echo ""
echo "To deactivate the virtual environment, run:"
echo "  deactivate"
echo ""
echo "Note: On macOS, this project uses requirements_minimum.txt"
echo "since hardware-specific libraries (RPi.GPIO, rpi-ws281x, etc.)"
echo "are not available on macOS. The code will run in simulation mode."
echo ""
echo "To run the code (in simulation mode):"
echo "  source $VENV_NAME/bin/activate"
echo "  python3 main.py"
echo ""
echo "To run PyLint:"
echo "  source $VENV_NAME/bin/activate"
echo "  pylint --rcfile=.pylintrc-milkyway ./*"
echo ""

