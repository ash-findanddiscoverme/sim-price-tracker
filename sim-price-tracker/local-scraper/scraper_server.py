#!/usr/bin/env python3
"""
SIM Price Tracker - Local Scraper Web UI
Starts a local web server with a browser-based interface to run the scraper.
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── Configuration ──────────────────────────────────────────────────
PORT = 8765
HOST = "127.0.0.1"

# ── State ──────────────────────────────────────────────────────────
scraper_state = {
    "status": "idle",       # idle | running | done | error
    "current": 0,
    "total": 0,
    "provider": "",
    "log": [],
    "results_file": None,
    "total_plans": 0,
    "total_providers": 0,
    "elapsed": 0,
    "errors": [],
}

def reset_state():
    scraper_state.update({
        "status": "idle",
        "current": 0,
        "total": 0,
        "provider": "",
        "log": [],
        "results_file": None,
        "total_plans": 0,
        "total_providers": 0,
        "elapsed": 0,
        "errors": [],
    })


# ── Dependency check ───────────────────────────────────────────────
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
        scraper_state["log"].append(f"Installing packages: {', '.join(missing)}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        scraper_state["log"].append("Packages installed!")

    # Check Playwright browsers
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        scraper_state["log"].append("Installing Chromium browser (one-time, may take a minute)...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
        )
        scraper_state["log"].append("Chromium installed!")


# ── Scraper runner ─────────────────────────────────────────────────
def _add_backend_to_path():
    script_dir = Path(__file__).parent.resolve()
    backend_dir = script_dir / "backend"
    if not backend_dir.exists():
        backend_dir = script_dir.parent / "backend"
    if backend_dir.exists() and str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


async def _run_scrape():
    _add_backend_to_path()
    os.environ["PLAYWRIGHT_ENABLED"] = "true"

    from scrapers import SCRAPERS

    total_scrapers = len(SCRAPERS)
    scraper_state["total"] = total_scrapers
    all_results = []
    total_plans = 0
    errors = []

    for i, scraper_cls in enumerate(SCRAPERS, 1):
        scraper = scraper_cls()
        name = scraper.provider_name
        slug = scraper.provider_slug
        ptype = scraper.provider_type

        scraper_state["current"] = i
        scraper_state["provider"] = name
        scraper_state["log"].append(f"[{i}/{total_scrapers}] Scraping {name}...")

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
                scraper_state["log"].append(f"  ✓ {name}: found {plan_count} plans")
            else:
                scraper_state["log"].append(f"  ✗ {name}: no plans found")
                errors.append(f"{name}: no plans found")

        except asyncio.TimeoutError:
            scraper_state["log"].append(f"  ✗ {name}: timed out (skipped)")
            errors.append(f"{name}: timed out")
        except Exception as e:
            scraper_state["log"].append(f"  ✗ {name}: error (skipped)")
            errors.append(f"{name}: {str(e)[:80]}")

    return all_results, total_plans, errors


def run_scraper_thread():
    """Run the scraper in a background thread."""
    reset_state()
    scraper_state["status"] = "running"
    scraper_state["log"].append("Checking dependencies...")

    try:
        check_dependencies()
        scraper_state["log"].append("Starting scrape...\n")

        start = time.time()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results, total_plans, errors = loop.run_until_complete(_run_scrape())
        loop.close()

        elapsed = time.time() - start
        scraper_state["elapsed"] = round(elapsed)
        scraper_state["errors"] = errors

        if not results:
            scraper_state["status"] = "error"
            scraper_state["log"].append("\nNo plans found. Check your internet connection.")
            return

        # Save results
        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            desktop = Path.home()

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

        scraper_state["results_file"] = str(filepath)
        scraper_state["total_plans"] = total_plans
        scraper_state["total_providers"] = len(results)
        scraper_state["status"] = "done"
        scraper_state["log"].append(f"\nComplete! {total_plans} plans from {len(results)} providers in {elapsed:.0f}s")
        scraper_state["log"].append(f"Saved to: {filepath}")

    except Exception as e:
        scraper_state["status"] = "error"
        scraper_state["log"].append(f"\nError: {str(e)}")


# ── HTML UI ────────────────────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SIM Price Scraper</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8f9fa;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            max-width: 600px;
            width: 100%;
            padding: 20px;
        }
        .card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            padding: 40px;
            text-align: center;
        }
        .logo {
            font-size: 48px;
            font-weight: bold;
            color: #0050ff;
            margin-bottom: 4px;
        }
        .logo span { font-size: 28px; vertical-align: super; }
        h1 {
            font-size: 24px;
            color: #1a1a2e;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #6b7280;
            margin-bottom: 32px;
            font-size: 14px;
        }
        .btn {
            display: inline-block;
            padding: 14px 40px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            color: white;
        }
        .btn-primary { background: linear-gradient(135deg, #001687, #0050ff); }
        .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(0,80,255,0.3); }
        .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn-purple { background: #5f2878; }
        .btn-purple:hover { background: #4a1f5e; }

        .progress-area {
            margin-top: 28px;
            text-align: left;
            display: none;
        }
        .progress-bar-container {
            background: #e5e7eb;
            border-radius: 8px;
            height: 8px;
            overflow: hidden;
            margin-bottom: 12px;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #0050ff, #5f2878);
            border-radius: 8px;
            width: 0%;
            transition: width 0.4s ease;
        }
        .progress-text {
            font-size: 13px;
            color: #6b7280;
            margin-bottom: 12px;
        }
        .log-box {
            background: #1a1a2e;
            color: #e0e0e0;
            border-radius: 10px;
            padding: 16px;
            max-height: 260px;
            overflow-y: auto;
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.6;
            text-align: left;
            white-space: pre-wrap;
        }
        .log-box .success { color: #34d399; }
        .log-box .error { color: #f87171; }
        .log-box .info { color: #93c5fd; }

        .results-area {
            margin-top: 24px;
            display: none;
        }
        .results-card {
            background: linear-gradient(135deg, #001687, #0050ff);
            border-radius: 12px;
            padding: 24px;
            color: white;
            margin-bottom: 16px;
        }
        .results-card .stat-row {
            display: flex;
            justify-content: space-around;
            margin-top: 12px;
        }
        .stat { text-align: center; }
        .stat-value { font-size: 28px; font-weight: 700; }
        .stat-label { font-size: 12px; opacity: 0.8; margin-top: 2px; }

        .file-path {
            background: #f3f4f6;
            border-radius: 8px;
            padding: 12px 16px;
            font-size: 13px;
            color: #374151;
            word-break: break-all;
            margin-bottom: 16px;
            text-align: left;
        }
        .file-path strong { color: #1a1a2e; }

        .next-steps {
            background: #fefce8;
            border: 1px solid #fde68a;
            border-radius: 10px;
            padding: 16px 20px;
            text-align: left;
            font-size: 14px;
            color: #92400e;
            line-height: 1.7;
        }
        .next-steps strong { color: #78350f; }

        .spinner {
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.7s linear infinite;
            vertical-align: middle;
            margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">O<span>2</span></div>
            <h1>SIM Price Scraper</h1>
            <p class="subtitle">Scrape the latest UK SIM-only deal prices from all major providers</p>

            <button class="btn btn-primary" id="startBtn" onclick="startScrape()">
                Run Scraper
            </button>

            <div class="progress-area" id="progressArea">
                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
                <div class="progress-text" id="progressText">Starting...</div>
                <div class="log-box" id="logBox"></div>
            </div>

            <div class="results-area" id="resultsArea">
                <div class="results-card">
                    <div style="font-size:14px;opacity:0.85;">Scrape Complete</div>
                    <div class="stat-row">
                        <div class="stat">
                            <div class="stat-value" id="planCount">0</div>
                            <div class="stat-label">Plans Found</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value" id="providerCount">0</div>
                            <div class="stat-label">Providers</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value" id="elapsedTime">0s</div>
                            <div class="stat-label">Time</div>
                        </div>
                    </div>
                </div>
                <div class="file-path">
                    <strong>Saved to:</strong><br>
                    <span id="filePath"></span>
                </div>
                <div class="next-steps">
                    <strong>Next steps:</strong><br>
                    1. Open the SIM Price Tracker dashboard<br>
                    2. Click <strong>"Upload Data"</strong><br>
                    3. Select the file from your Desktop
                </div>
                <div style="margin-top:20px;">
                    <button class="btn btn-purple" onclick="runAgain()">Run Again</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let polling = null;

        function startScrape() {
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').innerHTML = '<span class="spinner"></span> Running...';
            document.getElementById('progressArea').style.display = 'block';
            document.getElementById('resultsArea').style.display = 'none';
            document.getElementById('logBox').innerHTML = '';

            fetch('/api/start', { method: 'POST' })
                .then(r => r.json())
                .then(() => { polling = setInterval(pollStatus, 800); })
                .catch(err => {
                    document.getElementById('logBox').innerHTML = '<span class="error">Failed to start: ' + err + '</span>';
                });
        }

        function pollStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    // Update progress bar
                    const pct = data.total > 0 ? (data.current / data.total) * 100 : 0;
                    document.getElementById('progressBar').style.width = pct + '%';
                    document.getElementById('progressText').textContent =
                        data.status === 'running'
                            ? `Scraping ${data.provider} (${data.current}/${data.total})...`
                            : data.status === 'done' ? 'Complete!' : data.status;

                    // Update log
                    const logBox = document.getElementById('logBox');
                    logBox.innerHTML = data.log.map(line => {
                        if (line.includes('✓')) return '<span class="success">' + escHtml(line) + '</span>';
                        if (line.includes('✗')) return '<span class="error">' + escHtml(line) + '</span>';
                        if (line.startsWith('[')) return '<span class="info">' + escHtml(line) + '</span>';
                        return escHtml(line);
                    }).join('\\n');
                    logBox.scrollTop = logBox.scrollHeight;

                    // Check if done
                    if (data.status === 'done' || data.status === 'error') {
                        clearInterval(polling);
                        polling = null;
                        document.getElementById('progressBar').style.width = '100%';

                        if (data.status === 'done') {
                            document.getElementById('resultsArea').style.display = 'block';
                            document.getElementById('planCount').textContent = data.total_plans;
                            document.getElementById('providerCount').textContent = data.total_providers;
                            document.getElementById('elapsedTime').textContent = data.elapsed + 's';
                            document.getElementById('filePath').textContent = data.results_file || '';
                        }

                        document.getElementById('startBtn').disabled = false;
                        document.getElementById('startBtn').innerHTML = 'Run Scraper';
                    }
                });
        }

        function runAgain() {
            document.getElementById('resultsArea').style.display = 'none';
            startScrape();
        }

        function escHtml(s) {
            return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }
    </script>
</body>
</html>"""


# ── HTTP Server ────────────────────────────────────────────────────
class ScraperHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console spam

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._send_html(HTML_PAGE)

        elif path == "/api/status":
            self._send_json(scraper_state)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/start":
            if scraper_state["status"] == "running":
                self._send_json({"error": "Already running"}, 409)
                return

            t = threading.Thread(target=run_scraper_thread, daemon=True)
            t.start()
            self._send_json({"ok": True})

        else:
            self.send_response(404)
            self.end_headers()


# ── Main ───────────────────────────────────────────────────────────
def main():
    print()
    print("=" * 50)
    print("  SIM Price Scraper")
    print("=" * 50)
    print()
    print(f"  Opening browser at http://{HOST}:{PORT}")
    print(f"  Close this window to stop the server.")
    print()

    server = HTTPServer((HOST, PORT), ScraperHandler)

    # Open browser after a short delay
    def open_browser():
        time.sleep(0.8)
        webbrowser.open(f"http://{HOST}:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
