#!/bin/bash
# SIM Price Tracker - Double-click to run!
cd "$(dirname "$0")"
echo ""
echo "Starting SIM Price Tracker scraper..."
echo ""
python3 scrape_and_upload.py
