@echo off
title SIM Price Tracker - Local Scraper
cd /d "%~dp0"
echo.
echo Starting SIM Price Tracker scraper...
echo.
python scrape_and_upload.py
pause
