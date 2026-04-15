import asyncio
import logging
from datetime import datetime
from typing import List, Optional
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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

if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static_files")

@app.get("/{filename:path}")
async def serve_static_fallback(filename: str):
    """Serve static files from the root path (images, etc.)."""
    if filename.startswith("api/"):
        return {"detail": "Not found"}
    file_path = os.path.join(static_dir, filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return {"detail": "Not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
