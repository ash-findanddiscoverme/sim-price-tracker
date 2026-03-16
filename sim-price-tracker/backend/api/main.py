import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..db.database import init_db, async_session
from ..db.models import Provider, Plan, PriceSnapshot
from ..scrapers.base import ScrapedPlan
from ..scrapers import SCRAPERS
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SIM Price Tracker API")

import os
from fastapi.staticfiles import StaticFiles
_static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
if os.path.isdir(_static_dir):
    from fastapi.responses import FileResponse

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(_static_dir, "index.html"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeLogManager:
    def __init__(self):
        self.connections: List[WebSocket] = []
        self.is_scraping = False

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, msg: dict):
        for c in self.connections[:]:
            try:
                await c.send_json(msg)
            except:
                self.disconnect(c)


log_manager = ScrapeLogManager()


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("Database initialized")


@app.get("/api/plans")
async def get_plans(scrape_date: Optional[str] = None):
    async with async_session() as session:
        query = select(Plan).options(selectinload(Plan.provider), selectinload(Plan.price_snapshots))
        result = await session.execute(query)
        plans = result.scalars().all()
        return [{
            "id": p.id,
            "name": p.name,
            "provider_name": p.provider.name if p.provider else "Unknown",
            "data_gb": -1 if p.data_unlimited else (p.data_gb or 0),
            "price": p.current_price if p.current_price is not None else 0.0,
            "contract_length": p.contract_months or 1,
            "url": p.url,
            "last_updated": p.last_seen.isoformat() if p.last_seen else None
        } for p in plans]


@app.get("/api/scrape-runs")
async def get_scrape_runs():
    return []


@app.get("/api/price-history")
async def get_price_history(plan_id: Optional[int] = None, provider: Optional[str] = None):
    return []


@app.post("/api/scrape/trigger")
async def trigger_scrape():
    if log_manager.is_scraping:
        return {"status": "already_running"}
    asyncio.create_task(run_scrape())
    return {"status": "started"}


async def save_plans(session, provider: Provider, plans: List[ScrapedPlan]):
    for sp in plans:
        query = select(Plan).where(Plan.external_id == sp.external_id)
        result = await session.execute(query)
        plan = result.scalar()

        if not plan:
            plan = Plan(
                provider_id=provider.id,
                name=sp.name,
                url=sp.url,
                data_gb=sp.data_gb,
                data_unlimited=sp.data_unlimited,
                contract_months=sp.contract_months,
                is_5g=sp.is_5g,
                minutes=sp.minutes,
                texts=sp.texts,
                external_id=sp.external_id,
            )
            session.add(plan)
            await session.flush()
        else:
            plan.last_seen = datetime.utcnow()

        snapshot = PriceSnapshot(plan_id=plan.id, price=sp.price)
        session.add(snapshot)

    await session.commit()


async def get_or_create_provider(session, name: str, slug: str, ptype: str) -> Provider:
    query = select(Provider).where(Provider.slug == slug)
    result = await session.execute(query)
    provider = result.scalar()
    if not provider:
        provider = Provider(name=name, slug=slug, provider_type=ptype)
        session.add(provider)
        await session.flush()
    return provider


async def run_scrape():
    log_manager.is_scraping = True
    provider_names = [scl.provider_name for scl in SCRAPERS]

    await log_manager.broadcast({
        "type": "progress",
        "status": "started",
        "total": len(SCRAPERS),
        "completed": 0,
        "plans_found": 0,
        "provider_list": provider_names
    })

    total_plans = 0

    for i, ScraperClass in enumerate(SCRAPERS):
        scraper = ScraperClass()
        provider_name = scraper.provider_name

        await log_manager.broadcast({"type": "provider_start", "provider": provider_name})
        await log_manager.broadcast({"type": "log", "message": f"Scraping {provider_name}...", "level": "info"})

        try:
            async with scraper:
                plans = await scraper.scrape()

            async with async_session() as session:
                provider = await get_or_create_provider(
                    session,
                    scraper.provider_name,
                    scraper.provider_slug,
                    scraper.provider_type
                )
                await save_plans(session, provider, plans)

            plans_found = len(plans)
            total_plans += plans_found

            await log_manager.broadcast({"type": "provider_complete", "provider": provider_name, "plans_found": plans_found})
            await log_manager.broadcast({"type": "log", "message": f"{provider_name}: Found {plans_found} plans", "level": "success"})

        except Exception as e:
            logger.error(f"Error scraping {provider_name}: {e}")
            await log_manager.broadcast({"type": "provider_complete", "provider": provider_name, "error": str(e)})
            await log_manager.broadcast({"type": "log", "message": f"{provider_name}: Error - {e}", "level": "error"})

        await log_manager.broadcast({
            "type": "progress",
            "status": "running",
            "total": len(SCRAPERS),
            "completed": i + 1,
            "plans_found": total_plans
        })

    await log_manager.broadcast({
        "type": "progress",
        "status": "completed",
        "total": len(SCRAPERS),
        "completed": len(SCRAPERS),
        "plans_found": total_plans
    })

    log_manager.is_scraping = False


@app.websocket("/api/scrape/logs")
async def websocket_logs(ws: WebSocket):
    await log_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        log_manager.disconnect(ws)


if os.path.isdir(_static_dir):
    from fastapi.responses import FileResponse as _FR

    @app.get("/crawl-log.html")
    async def serve_crawl():
        return _FR(os.path.join(_static_dir, "crawl-log.html"))

    @app.get("/index.html")
    async def serve_idx():
        return _FR(os.path.join(_static_dir, "index.html"))
