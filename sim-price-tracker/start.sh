#!/bin/bash
# SIM Price Tracker - Mac/Linux Launcher
# Double-click this file or run: bash start.sh

set -e

cd "$(dirname "$0")"
echo ""
echo "========================================="
echo "  SIM Price Tracker - Starting Up"
echo "========================================="
echo ""

# Check Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "ERROR: Python is not installed."
    echo "Download it from: https://www.python.org/downloads/"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

VERSION=$($PYTHON --version 2>&1)
echo "Found $VERSION"

# Create virtual environment (first run only)
if [ ! -d "venv" ]; then
    echo ""
    echo "First run - setting up environment (this takes 2-3 minutes)..."
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies (first run only)
if [ ! -f "venv/.deps_installed" ]; then
    echo "Installing Python packages..."
    pip install --upgrade pip -q
    pip install -r backend/requirements.txt -q
    echo "Installing browser for web scraping..."
    if python -m playwright install chromium 2>/dev/null; then
        echo "Playwright Chromium installed successfully."
    else
        echo ""
        echo "NOTE: Could not download Playwright Chromium (corporate firewall?)."
        echo "No problem - the scraper will use your system Chrome or Edge instead."
        echo ""
    fi
    touch venv/.deps_installed
    echo ""
    echo "Setup complete!"
fi

echo ""
echo "Starting server..."
echo "The app will open at: http://localhost:8000"
echo "Press Ctrl+C to stop the server."
echo ""

# Open browser after a short delay
(sleep 3 && open "http://localhost:8000" 2>/dev/null || xdg-open "http://localhost:8000" 2>/dev/null) &

# Start the server
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend
