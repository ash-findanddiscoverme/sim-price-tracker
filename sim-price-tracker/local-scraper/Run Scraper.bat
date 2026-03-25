@echo off
title SIM Price Scraper
cd /d "%~dp0"

echo.
echo ============================================
echo   SIM Price Scraper
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   Python found.
    echo.
    echo   Starting scraper... your browser will open shortly.
    echo   Close this window when you're done.
    echo.
    python scraper_server.py
    goto :end
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   Python found.
    echo.
    echo   Starting scraper... your browser will open shortly.
    echo   Close this window when you're done.
    echo.
    python3 scraper_server.py
    goto :end
)

echo   Python 3 is not installed.
echo.
echo   Would you like to install it now? (Y/N)
set /p answer=
if /i "%answer%"=="y" (
    echo.
    :: Try winget first (Windows 10/11)
    winget --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo   Installing Python via Windows Package Manager...
        echo   (You may need to approve a prompt)
        echo.
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        echo.
        echo   Python installed! Please close this window and double-click
        echo   "Run Scraper.bat" again to start scraping.
        echo.
        pause
        goto :end
    )

    :: Fallback: download installer
    echo   Downloading Python installer...
    echo.
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
    if exist "%TEMP%\python-installer.exe" (
        echo   Running Python installer...
        echo   IMPORTANT: Make sure to check "Add Python to PATH" at the bottom!
        echo.
        start /wait "" "%TEMP%\python-installer.exe" /passive InstallAllUsers=0 PrependPath=1 Include_test=0
        del "%TEMP%\python-installer.exe"
        echo.
        echo   Python installed! Please close this window and double-click
        echo   "Run Scraper.bat" again to start scraping.
        echo.
        pause
        goto :end
    ) else (
        echo   Download failed. Please install Python manually:
        echo   1. Go to https://www.python.org/downloads/
        echo   2. Download and install Python 3
        echo   3. IMPORTANT: Check "Add Python to PATH" during install
        echo   4. Double-click this file again
        echo.
        pause
        goto :end
    )
) else (
    echo.
    echo   To install Python manually:
    echo   1. Go to https://www.python.org/downloads/
    echo   2. Download and install Python 3
    echo   3. IMPORTANT: Check "Add Python to PATH" during install
    echo   4. Double-click this file again
    echo.
    pause
)

:end
