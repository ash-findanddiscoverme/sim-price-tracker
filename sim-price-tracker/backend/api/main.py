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


@app.get("/download-scraper")
async def download_scraper():
    """Download the local scraper as a zip file."""
    scraper_dir = os.path.join(_project_root, "local-scraper")
    backend_dir = os.path.join(_project_root, "backend")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add the main scraper script
        for fname in ["scrape_and_upload.py", "Run Scraper.command", "Run Scraper.bat"]:
            fpath = os.path.join(scraper_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, f"sim-price-scraper/{fname}")

        # Add the backend scrapers (needed by the script)
        for root, dirs, files in os.walk(os.path.join(backend_dir, "scrapers")):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".py"):
                    full = os.path.join(root, f)
                    arc = os.path.relpath(full, backend_dir)
                    zf.write(full, f"sim-price-scraper/backend/{arc}")

        # Add config files
        config_dir = os.path.join(backend_dir, "config")
        if os.path.exists(config_dir):
            for f in os.listdir(config_dir):
                fpath = os.path.join(config_dir, f)
                if os.path.isfile(fpath):
                    zf.write(fpath, f"sim-price-scraper/backend/config/{f}")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=sim-price-scraper.zip"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
