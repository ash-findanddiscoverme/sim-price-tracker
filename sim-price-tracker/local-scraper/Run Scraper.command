#!/bin/bash
# SIM Price Tracker - Double-click to run!
cd "$(dirname "$0")"

echo ""
echo "============================================"
echo "  SIM Price Tracker - Local Scraper"
echo "============================================"
echo ""

# Check if Python 3 is installed
if command -v python3 &> /dev/null; then
    echo "  Python found: $(python3 --version)"
    echo ""
    python3 scrape_and_upload.py
else
    echo "  Python 3 is not installed."
    echo ""
    echo "  Would you like to install it now? (y/n)"
    read -r answer
    if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
        echo ""
        # Check if Homebrew is installed
        if command -v brew &> /dev/null; then
            echo "  Installing Python via Homebrew..."
            brew install python3
        else
            echo "  Installing Homebrew first (Apple's recommended package manager)..."
            echo ""
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            echo ""
            echo "  Now installing Python..."
            brew install python3
        fi

        if command -v python3 &> /dev/null; then
            echo ""
            echo "  Python installed successfully!"
            echo ""
            python3 scrape_and_upload.py
        else
            echo ""
            echo "  Installation had an issue. Please install Python manually:"
            echo "  1. Go to https://www.python.org/downloads/"
            echo "  2. Download and install Python 3"
            echo "  3. Double-click this file again"
            echo ""
            read -p "  Press Enter to exit..."
        fi
    else
        echo ""
        echo "  To install Python manually:"
        echo "  1. Go to https://www.python.org/downloads/"
        echo "  2. Download and install Python 3"
        echo "  3. Double-click this file again"
        echo ""
        read -p "  Press Enter to exit..."
    fi
fi
