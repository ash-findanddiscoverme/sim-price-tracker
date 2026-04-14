# SIM Price Tracker

Compare SIM-only deals across UK networks and affiliate sites. Scrapes live pricing from 19 providers including O2, EE, Three, Vodafone, giffgaff, Sky Mobile, and comparison sites like uSwitch and MoneySupermarket.

## Quick Start

### Prerequisites

- **Python 3.9 or newer** - Download from [python.org/downloads](https://www.python.org/downloads/)
  - **Windows**: Make sure to tick **"Add Python to PATH"** during installation
  - **Mac**: Python 3 comes pre-installed on newer Macs. If not, install via the link above

### Run the App

1. **Download** this folder (or `git clone` the repo)
2. **Launch**:
   - **Windows**: Double-click `start.bat`
   - **Mac/Linux**: Open Terminal, navigate to this folder, and run `bash start.sh`
3. **Wait** - First launch takes 2-3 minutes to install packages and download a browser. Subsequent launches take ~5 seconds.
4. **Use** - The app opens automatically at [http://localhost:8000](http://localhost:8000)

### What Happens on First Run

The launcher script automatically:
- Creates an isolated Python virtual environment (`venv/`)
- Installs all required packages
- Downloads a Chromium browser for web scraping
- Starts the web server and opens your browser

### Using the App

- Click **Run Scrape** to fetch live pricing from all provider websites
- Use **Filters** to narrow by network, data amount, contract length, or source
- Click any plan row to **compare against O2** pricing
- View **Price Distribution** and **Competitor Ranking** charts
- Toggle between **Direct** and **Affiliate** sources

### Stopping the App

Press `Ctrl+C` in the terminal window to stop the server.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python is not installed" | Install from [python.org/downloads](https://www.python.org/downloads/) |
| "No module named pip" | Re-install Python and ensure pip is included |
| "Could not download Playwright Chromium" | This is normal on corporate networks. The scraper automatically uses your system Chrome or Edge instead - no action needed |
| Port 8000 already in use | Close other apps using that port, or wait and re-run |
