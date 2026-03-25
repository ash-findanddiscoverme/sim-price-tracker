#!/bin/bash
# SIM Price Scraper - Mac App Launcher

# Get the directory where this .app bundle lives
APP_DIR="$(cd "$(dirname "$0")/../.."; pwd)"
SCRAPER_DIR="$APP_DIR/Resources/scraper"

# Open Terminal and run the scraper
osascript -e "
tell application \"Terminal\"
    activate
    do script \"cd '$SCRAPER_DIR' && bash -c '
echo \\\"\\\"
echo \\\"============================================\\\"
echo \\\"  SIM Price Tracker - Local Scraper\\\"
echo \\\"============================================\\\"
echo \\\"\\\"

if command -v python3 &> /dev/null; then
    echo \\\"  Python found: \\\$(python3 --version)\\\"
    echo \\\"\\\"
    python3 scrape_and_upload.py
else
    echo \\\"  Python 3 is not installed.\\\"
    echo \\\"\\\"
    echo \\\"  Would you like to install it now? (y/n)\\\"
    read -r answer
    if [ \\\"\\\$answer\\\" = \\\"y\\\" ] || [ \\\"\\\$answer\\\" = \\\"Y\\\" ]; then
        if command -v brew &> /dev/null; then
            echo \\\"  Installing Python via Homebrew...\\\"
            brew install python3
        else
            echo \\\"  Installing Homebrew first...\\\"
            /bin/bash -c \\\"\\\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\\\"
            echo \\\"  Installing Python...\\\"
            brew install python3
        fi
        if command -v python3 &> /dev/null; then
            echo \\\"  Python installed!\\\"
            python3 scrape_and_upload.py
        else
            echo \\\"  Please install Python from https://www.python.org/downloads/\\\"
            read -p \\\"  Press Enter to exit...\\\"
        fi
    else
        echo \\\"  Install Python from https://www.python.org/downloads/\\\"
        read -p \\\"  Press Enter to exit...\\\"
    fi
fi
'\"
end tell
"
