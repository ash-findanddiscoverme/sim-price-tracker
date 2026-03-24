"""Main scraper orchestrator."""

import asyncio
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
import time

from .browser_pool import get_browser_pool, close_browser_pool
from .interactions import PageInteractor
from .affiliate import AffiliateScraper
from .strategies import get_best_result
from .confidence import ScrapedPlan
from .validation import validate_plans, sanitize_plan


@dataclass
class ScrapeResult:
    provider_slug: str
    provider_name: str
    provider_type: str
    status: str  = "success"
    plans: List[ScrapedPlan] = field(default_factory=list)
    strategy_used: Optional[str] = None
    confidence: float = 0.0
    duration_ms: int = 0
    errors: List[str] = field(default_factory=list)


class ScraperOrchestrator:
    def __init__(self, config_dir: str, log_callback: Optional[Callable[[str], None]] = None):
        self.config_dir = Path(config_dir)
        self._log_cb = log_callback or (lambda msg: None)
        self.providers = self._load_providers()
        self.interactions = self._load_interactions()
    
    def _log(self, message: str):
        self._log_cb(f"[Orchestrator] {message}")
    
    def _load_providers(self) -> Dict[str, Dict]:
        path = self.config_dir / "providers.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _load_interactions(self) -> Dict[str, Any]:
        path = self.config_dir / "interactions.yaml"
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return {}
    
    async def scrape_provider(self, slug: str) -> ScrapeResult:
        start = time.time()
        config = self.providers.get(slug, {})
        config["slug"] = slug
        
        result = ScrapeResult(
            provider_slug=slug,
            provider_name=config.get("name", slug),
            provider_type=config.get("type", "network")
        )
        
        try:
            self._log(f"Starting scrape for {slug}")
            
            pool = await get_browser_pool(log_callback=self._log_cb)
            
            async with pool.page() as page:
                if config.get("type") == "affiliate" and config.get("network_filter_strategy", {}).get("enabled"):
                    scraper = AffiliateScraper(
                        page=page,
                        provider_config=config,
                        interaction_config=self.interactions,
                        extract_plans_func=self._extract_plans,
                        log_callback=self._log_cb
                    )
                    plans = await scraper.scrape_by_network()
                    result.strategy_used = "affiliate_network"
                else:
                    plans = await self._scrape_standard(page, config)
                
                for plan in plans:
                    sanitize_plan(plan)
                
                valid, invalid = validate_plans(plans)
                result.plans = valid
                
                if invalid:
                    result.errors.append(f"{len(invalid)} plans failed validation")
                
                if result.plans:
                    result.confidence = sum(p.confidence_score for p in result.plans) / len(result.plans)
                    result.status = "success" if result.confidence >= 0.7 else "partial"
                else:
                    result.status = "failed"
            
            self._log(f"{slug}: Found {len(result.plans)} valid plans")
            
        except Exception as e:
            result.status = "failed"
            result.errors.append(str(e))
            self._log(f"{slug}: Error - {e}")
        
        result.duration_ms = int((time.time() - start) * 1000)
        return result
    
    async def _scrape_standard(self, page, config: Dict) -> List[ScrapedPlan]:
        urls = config.get("urls", [])
        all_plans = []
        
        for url in urls:
            self._log(f"Navigating to {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            interactor = PageInteractor(page, self.interactions, self._log_cb)
            result = await interactor.execute_sequence(config.get("slug", ""))
            
            for context, html in result.html_snapshots:
                plans = self._extract_plans(html, config)
                all_plans.extend(plans)
        
        return all_plans
    
    def _extract_plans(self, html: str, config: Dict) -> List[ScrapedPlan]:
        url = config.get("urls", [""])[0] if config.get("urls") else ""
        result = get_best_result(html, url, config)
        return result.plans if result.success else []
    
    async def scrape_all(self, max_concurrent: int = 3) -> List[ScrapeResult]:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def scrape_with_sem(slug):
            async with semaphore:
                return await self.scrape_provider(slug)
        
        tasks = [scrape_with_sem(slug) for slug in self.providers.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for r in results:
            if isinstance(r, ScrapeResult):
                valid_results.append(r)
            elif isinstance(r, Exception):
                self._log(f"Exception during scrape: {r}")
        
        await close_browser_pool()
        return valid_results
