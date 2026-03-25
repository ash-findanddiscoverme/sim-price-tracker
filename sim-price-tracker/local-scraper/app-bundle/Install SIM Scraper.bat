@echo off
title SIM Price Scraper - Installer
echo.
echo ============================================
echo   SIM Price Scraper - Installer
echo ============================================
echo.

:: Set install directory
set "INSTALL_DIR=%LOCALAPPDATA%\SIM Price Scraper"

echo   Installing to: %INSTALL_DIR%
echo.

:: Create install directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Copy files
echo   Copying files...
xcopy /s /y /q "%~dp0scraper\*" "%INSTALL_DIR%\" >nul 2>&1

:: Check for Python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   Python found.
    goto :create_shortcut
)
python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo   Python found.
    goto :create_shortcut
)

echo   Python 3 is not installed.
echo   Would you like to install it now? (Y/N)
set /p answer=
if /i "%answer%"=="y" (
    echo.
    winget --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo   Installing Python via Windows Package Manager...
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        echo.
    ) else (
        echo   Downloading Python installer...
        powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
        if exist "%TEMP%\python-installer.exe" (
            echo   Running installer - check "Add Python to PATH"!
            start /wait "" "%TEMP%\python-installer.exe" /passive InstallAllUsers=0 PrependPath=1 Include_test=0
            del "%TEMP%\python-installer.exe"
        ) else (
            echo   Please install Python from https://www.python.org/downloads/
            echo   Then run this installer again.
            pause
            goto :end
        )
    )
)

:create_shortcut
echo   Creating desktop shortcut...

:: Create a launcher script in the install dir
(
echo @echo off
echo title SIM Price Scraper
echo cd /d "%INSTALL_DIR%"
echo python scraper_server.py
) > "%INSTALL_DIR%\Launch Scraper.bat"

:: Create desktop shortcut using PowerShell
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\SIM Price Scraper.lnk'); $s.TargetPath = '%INSTALL_DIR%\Launch Scraper.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Run SIM Price Scraper'; $s.Save()"

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo   A shortcut "SIM Price Scraper" has been
echo   added to your Desktop. Double-click it
echo   to run the scraper.
echo.
pause

:end
