#!/usr/bin/env python3
"""
SIM Price Tracker - Local Scraper
Double-click 'Run Scraper' to run!
Scrapes UK mobile provider prices and saves a data file you can upload to the dashboard.
"""

import asyncio
import json
import sys
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


def print_banner():
    print()
    print("=" * 60)
    print("  SIM Price Tracker - Local Scraper")
    print("=" * 60)
    print()


def check_dependencies():
    """Check and install missing dependencies."""
    missing = []
    for pkg, import_name in [
        ("httpx", "httpx"),
        ("beautifulsoup4", "bs4"),
        ("lxml", "lxml"),
        ("playwright", "playwright"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"  Installing required packages: {', '.join(missing)}")
        print("  (This only happens on first run)\n")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("  Packages installed!\n")

    # Check Playwright browsers
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        print("  Installing Chromium browser (one-time, may take a minute)...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
        )
        print("  Chromium installed!\n")


# Add the backend directory to path so we can import scrapers
SCRIPT_DIR = Path(__file__).parent.resolve()
# Works both from the repo (../backend) and from the downloaded zip (./backend)
BACKEND_DIR = SCRIPT_DIR / "backend"
if not BACKEND_DIR.exists():
    BACKEND_DIR = SCRIPT_DIR.parent / "backend"
if BACKEND_DIR.exists():
    sys.path.insert(0, str(BACKEND_DIR))


async def run_scrape():
    """Run all scrapers locally."""
    from scrapers import SCRAPERS

    total_scrapers = len(SCRAPERS)
    all_results = []
    total_plans = 0
    errors = []

    print(f"  Scraping {total_scrapers} providers...\n")

    for i, scraper_cls in enumerate(SCRAPERS, 1):
        scraper = scraper_cls()
        name = scraper.provider_name
        slug = scraper.provider_slug
        ptype = scraper.provider_type

        progress = f"[{i}/{total_scrapers}]"
        print(f"  {progress} {name}...", end="", flush=True)

        try:
            plans = await asyncio.wait_for(scraper.scrape(), timeout=90)
            plan_count = len(plans) if plans else 0

            if plans:
                result = {
                    "provider_slug": slug,
                    "provider_name": name,
                    "provider_type": ptype,
                    "plans": [
                        {
                            "name": p.name,
                            "price": p.price,
                            "data_gb": p.data_gb,
                            "data_unlimited": p.data_unlimited,
                            "contract_months": p.contract_months,
                            "url": p.url,
                            "network": p.network,
                        }
                        for p in plans
                    ],
                }
                all_results.append(result)
                total_plans += plan_count
                print(f" found {plan_count} plans")
            else:
                print(" no plans found")
                errors.append(f"{name}: no plans found")

        except asyncio.TimeoutError:
            print(" timed out (skipped)")
            errors.append(f"{name}: timed out")
        except Exception as e:
            print(f" error (skipped)")
            errors.append(f"{name}: {str(e)[:80]}")

    return all_results, total_plans, errors


def save_results(results, total_plans):
    """Save results as a JSON file on the user's Desktop."""
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home()  # Fallback to home directory

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"sim-prices-{timestamp}.json"
    filepath = desktop / filename

    output = {
        "version": "1.0",
        "scraped_at": datetime.utcnow().isoformat(),
        "total_plans": total_plans,
        "total_providers": len(results),
        "results": results,
    }

    with open(filepath, "w") as f:
        json.dump(output, f, indent=2)

    return filepath


async def main():
    print_banner()

    print("  Checking dependencies...")
    check_dependencies()

    # Force Playwright enabled for local runs
    os.environ["PLAYWRIGHT_ENABLED"] = "true"

    start = time.time()
    results, total_plans, errors = await run_scrape()
    elapsed = time.time() - start

    print(f"\n{'=' * 60}")
    print(f"  Scraping complete in {elapsed:.0f} seconds")
    print(f"  {total_plans} plans found from {len(results)} providers")

    if errors:
        print(f"  {len(errors)} providers had issues (this is normal)")

    if not results:
        print("\n  No plans found. Check your internet connection.")
        input("\n  Press Enter to exit...")
        return

    filepath = save_results(results, total_plans)

    print(f"\n  Data saved to: {filepath}")
    print(f"\n  Next step:")
    print(f"  1. Open the SIM Price Tracker dashboard in your browser")
    print(f"  2. Click 'Upload Data'")
    print(f"  3. Select the file from your Desktop: {filepath.name}")

    input("\n  Press Enter to exit...")


if __name__ == "__main__":
    asyncio.run(main())
