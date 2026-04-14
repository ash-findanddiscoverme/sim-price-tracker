@echo off
:: SIM Price Tracker - Windows Launcher
:: Double-click this file to start

cd /d "%~dp0"
echo.
echo =========================================
echo   SIM Price Tracker - Starting Up
echo =========================================
echo.

:: Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed.
    echo Download it from: https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

python --version

:: Create virtual environment (first run only)
if not exist "venv" (
    echo.
    echo First run - setting up environment, this takes 2-3 minutes...
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install dependencies (first run only)
if not exist "venv\.deps_installed" (
    echo Installing Python packages...
    pip install --upgrade pip -q
    pip install -r backend\requirements.txt -q
    echo Installing browser for web scraping...
    python -m playwright install chromium >nul 2>nul
    if %errorlevel% neq 0 (
        echo.
        echo NOTE: Could not download Playwright Chromium [corporate firewall?].
        echo No problem - the scraper will use your system Chrome or Edge instead.
        echo.
    ) else (
        echo Playwright Chromium installed successfully.
    )
    echo. > venv\.deps_installed
    echo.
    echo Setup complete!
)

echo.
echo Starting server...
echo The app will open at: http://localhost:8000
echo Press Ctrl+C to stop the server.
echo.

:: Open browser after a short delay
start "" http://localhost:8000

:: Start the server
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --app-dir backend
