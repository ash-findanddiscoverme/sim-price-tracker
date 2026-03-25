import asyncio
import logging
import zipfile
import io
from datetime import datetime
from typing import List, Optional
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from db.database import init_db, async_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SIM Price Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from api.routes import router
    app.include_router(router)
    logger.info("Included API routes")
except ImportError as e:
    logger.warning(f"Could not import API routes: {e}")

# Go up from api/main.py -> api -> backend -> project_root static
_file_dir = os.path.dirname(os.path.abspath(__file__))  # backend/api
_backend_dir = os.path.dirname(_file_dir)  # backend
_project_root = os.path.dirname(_backend_dir)  # project root
static_dir = os.path.join(_project_root, "static")
logger.info(f"Static dir: {static_dir}")

@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("Database initialized")


@app.get("/")
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"message": "SIM Price Tracker API", "version": "2.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}


def _add_scraper_files(zf, prefix, backend_dir, scraper_dir):
    """Add the Python scraper and backend files to a zip."""
    # Main scraper script
    main_script = os.path.join(scraper_dir, "scrape_and_upload.py")
    if os.path.exists(main_script):
        zf.write(main_script, f"{prefix}/scrape_and_upload.py")

    # Backend scrapers
    for root, dirs, files in os.walk(os.path.join(backend_dir, "scrapers")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                full = os.path.join(root, f)
                arc = os.path.relpath(full, backend_dir)
                zf.write(full, f"{prefix}/backend/{arc}")

    # Config files
    config_dir = os.path.join(backend_dir, "config")
    if os.path.exists(config_dir):
        for f in os.listdir(config_dir):
            fpath = os.path.join(config_dir, f)
            if os.path.isfile(fpath):
                zf.write(fpath, f"{prefix}/backend/config/{f}")


@app.get("/download-scraper")
async def download_scraper():
    """Download page for scraper installers."""
    return FileResponse(
        os.path.join(static_dir, "download.html"),
        media_type="text/html",
    )


@app.get("/download-scraper/mac")
async def download_scraper_mac():
    """Download Mac .app bundle as a zip."""
    scraper_dir = os.path.join(_project_root, "local-scraper")
    bundle_dir = os.path.join(scraper_dir, "app-bundle")
    backend_dir = os.path.join(_project_root, "backend")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        app_base = "SIM Price Scraper.app/Contents"

        # Info.plist
        plist = os.path.join(bundle_dir, "Info.plist")
        if os.path.exists(plist):
            zf.write(plist, f"{app_base}/Info.plist")

        # Launcher script
        run_sh = os.path.join(bundle_dir, "run.sh")
        if os.path.exists(run_sh):
            zf.write(run_sh, f"{app_base}/MacOS/run")

        # Add scraper files into Resources/scraper
        _add_scraper_files(zf, f"{app_base}/Resources/scraper", backend_dir, scraper_dir)

        # Set executable permissions via external_attr
        for info in zf.infolist():
            if info.filename.endswith("/MacOS/run"):
                info.external_attr = 0o755 << 16

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=SIM-Price-Scraper-Mac.zip"},
    )


@app.get("/download-scraper/windows")
async def download_scraper_windows():
    """Download Windows installer as a zip."""
    scraper_dir = os.path.join(_project_root, "local-scraper")
    bundle_dir = os.path.join(scraper_dir, "app-bundle")
    backend_dir = os.path.join(_project_root, "backend")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        base = "SIM Price Scraper"

        # Installer
        installer = os.path.join(bundle_dir, "Install SIM Scraper.bat")
        if os.path.exists(installer):
            zf.write(installer, f"{base}/Install SIM Scraper.bat")

        # Add scraper files into scraper subfolder
        _add_scraper_files(zf, f"{base}/scraper", backend_dir, scraper_dir)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=SIM-Price-Scraper-Windows.zip"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
