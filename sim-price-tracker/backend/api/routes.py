"""API routes with working scrape integration."""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks

from db.database import async_session
from db.models import Plan, Provider, PriceSnapshot, ScrapeRun
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["scraper"])

scrape_state = {
    "running": False,
    "current_provider": "",
    "completed": 0,
    "total": 0,
    "plans_found": 0,
    "logs": [],
    "errors": [],
    "started_at": None,
}

MAX_LOG_LINES = 200


def log_message(msg, level="info"):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    scrape_state["logs"].append(entry)
    if len(scrape_state["logs"]) > MAX_LOG_LINES:
        scrape_state["logs"] = scrape_state["logs"][-MAX_LOG_LINES:]
    logger.info(msg)


@router.get("/plans")
async def get_plans(
    network: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_price: Optional[float] = None,
):
    """Get all plans with latest prices."""
    async with async_session() as db:
        query = (
            select(Plan)
            .options(selectinload(Plan.provider))
            .where(Plan.is_active == True)
        )
        if network:
            query = query.where(Plan.network_provider.ilike(f"%{network}%"))
        if min_confidence:
            query = query.where(Plan.confidence_score >= min_confidence)

        result = await db.execute(query)
        plans = result.scalars().all()

        plan_data = []
        for p in plans:
            price_query = (
                select(PriceSnapshot)
                .where(PriceSnapshot.plan_id == p.id)
                .order_by(PriceSnapshot.scraped_at.desc())
                .limit(1)
            )
            price_result = await db.execute(price_query)
            latest_price = price_result.scalar()
            price = latest_price.price if latest_price else 0

            if max_price and price > max_price:
                continue

            plan_data.append({
                "id": p.id,
                "name": p.name or "Unknown",
                "provider_name": p.provider.name if p.provider else "Unknown",
                "network_provider": p.network_provider or (p.provider.name if p.provider else "Unknown"),
                "current_price": price,
                "price": price,
                "data_gb": p.data_gb,
                "data_unlimited": p.data_unlimited,
                "contract_months": p.contract_months or 12,
                "url": p.url or "",
                "confidence_score": p.confidence_score or 0.5,
                "needs_verification": p.needs_verification or False,
            })

        return {"plans": plan_data, "total": len(plan_data)}


@router.get("/plans/{plan_id}/history")
async def get_plan_history(plan_id: int):
    """Get price history for a plan."""
    async with async_session() as db:
        query = (
            select(PriceSnapshot)
            .where(PriceSnapshot.plan_id == plan_id)
            .order_by(PriceSnapshot.scraped_at.asc())
        )
        result = await db.execute(query)
        snapshots = result.scalars().all()
        return {
            "plan_id": plan_id,
            "history": [
                {"price": s.price, "date": s.scraped_at.isoformat()}
                for s in snapshots
            ],
        }


@router.get("/stats")
async def get_stats():
    """Get overall statistics."""
    async with async_session() as db:
        plan_count = await db.execute(
            select(func.count()).select_from(Plan).where(Plan.is_active == True)
        )
        total_plans = plan_count.scalar()

        provider_count = await db.execute(select(func.count()).select_from(Provider))
        total_providers = provider_count.scalar()

        return {
            "total_plans": total_plans,
            "total_providers": total_providers,
            "last_updated": datetime.utcnow().isoformat(),
        }


@router.get("/scrape/progress")
async def get_scrape_progress():
    """Get current scrape progress."""
    return {
        "running": scrape_state["running"],
        "current_provider": scrape_state["current_provider"],
        "completed": scrape_state["completed"],
        "total": scrape_state["total"],
        "plans_found": scrape_state["plans_found"],
        "logs": scrape_state["logs"][-50:],
        "errors": scrape_state["errors"][-20:],
        "started_at": scrape_state["started_at"],
    }


@router.post("/scrape/start")
async def start_scrape(background_tasks: BackgroundTasks):
    """Start a new scrape run."""
    if scrape_state["running"]:
        return {"message": "Scrape already in progress", "status": "already_running"}

    background_tasks.add_task(run_scrape)
    return {"message": "Scrape started!", "status": "started"}


async def run_scrape():
    """Background task that runs all scrapers and saves to DB."""
    from scrapers import SCRAPERS

    scrape_state["running"] = True
    scrape_state["current_provider"] = ""
    scrape_state["completed"] = 0
    scrape_state["total"] = len(SCRAPERS)
    scrape_state["plans_found"] = 0
    scrape_state["logs"] = []
    scrape_state["errors"] = []
    scrape_state["started_at"] = datetime.utcnow().isoformat()

    log_message(f"Starting scrape of {len(SCRAPERS)} providers")

    run_id = None
    async with async_session() as db:
        scrape_run = ScrapeRun(
            started_at=datetime.utcnow(),
            status="running",
            total_providers=len(SCRAPERS),
        )
        db.add(scrape_run)
        await db.commit()
        await db.refresh(scrape_run)
        run_id = scrape_run.id

    semaphore = asyncio.Semaphore(3)

    async def scrape_one(scraper_cls):
        async with semaphore:
            scraper = scraper_cls()
            name = scraper.provider_name
            slug = scraper.provider_slug
            ptype = scraper.provider_type

            scrape_state["current_provider"] = name
            log_message(f"Scraping {name}...")
            scraper.set_log_callback(lambda msg, lvl="info": log_message(f"  {msg}"))

            try:
                plans = await asyncio.wait_for(scraper.scrape(), timeout=60)
                plan_count = len(plans) if plans else 0
                log_message(f"{name}: found {plan_count} plans")

                if plans:
                    await save_plans(slug, name, ptype, plans)
                    scrape_state["plans_found"] += plan_count
                else:
                    scrape_state["errors"].append(f"{name}: 0 plans found")

                scrape_state["completed"] += 1
                return plan_count

            except asyncio.TimeoutError:
                err = f"{name}: timed out after 60s"
                log_message(err, "error")
                scrape_state["errors"].append(err)
                scrape_state["completed"] += 1
                return 0
            except Exception as e:
                err = f"{name}: {str(e)[:200]}"
                log_message(err, "error")
                scrape_state["errors"].append(err)
                scrape_state["completed"] += 1
                return 0

    tasks = [scrape_one(cls) for cls in SCRAPERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_found = sum(r for r in results if isinstance(r, int))

    async with async_session() as db:
        if run_id:
            result = await db.execute(select(ScrapeRun).where(ScrapeRun.id == run_id))
            scrape_run = result.scalar()
            if scrape_run:
                scrape_run.completed_at = datetime.utcnow()
                scrape_run.status = "completed"
                scrape_run.total_plans_found = total_found
                scrape_run.successful_providers = scrape_state["completed"]
                scrape_run.errors = json.dumps(scrape_state["errors"])
                await db.commit()

    log_message(f"Scrape complete! {total_found} total plans from {scrape_state['completed']} providers")
    scrape_state["running"] = False
    scrape_state["current_provider"] = "Done"


async def save_plans(slug: str, name: str, ptype: str, plans):
    """Save scraped plans to the database."""
    async with async_session() as db:
        result = await db.execute(select(Provider).where(Provider.slug == slug))
        provider = result.scalar()
        if not provider:
            provider = Provider(slug=slug, name=name, provider_type=ptype)
            db.add(provider)
            await db.commit()
            await db.refresh(provider)

        for plan_data in plans:
            ext_id = f"{plan_data.price}-{plan_data.data_gb or 'unl'}-{plan_data.contract_months}"

            result = await db.execute(
                select(Plan).where(
                    Plan.provider_id == provider.id,
                    Plan.external_id == ext_id,
                )
            )
            existing = result.scalar()

            network = plan_data.network or name
            if existing:
                existing.name = plan_data.name
                existing.url = plan_data.url or existing.url
                existing.data_gb = plan_data.data_gb
                existing.data_unlimited = plan_data.data_unlimited
                existing.contract_months = plan_data.contract_months
                existing.network_provider = network
                existing.last_seen = datetime.utcnow()
                existing.is_active = True
                plan_obj = existing
            else:
                plan_obj = Plan(
                    provider_id=provider.id,
                    external_id=ext_id,
                    name=plan_data.name,
                    url=plan_data.url or "",
                    data_gb=plan_data.data_gb,
                    data_unlimited=plan_data.data_unlimited,
                    contract_months=plan_data.contract_months,
                    network_provider=network,
                    confidence_score=0.5,
                    is_active=True,
                )
                db.add(plan_obj)

            await db.flush()

            snapshot = PriceSnapshot(
                plan_id=plan_obj.id,
                price=plan_data.price,
                scraped_at=datetime.utcnow(),
            )
            db.add(snapshot)

        await db.commit()
