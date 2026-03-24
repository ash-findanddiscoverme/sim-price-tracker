"""Affiliate network-specific scraping for accurate attribution."""

import asyncio
from typing import List, Dict, Any, Callable, Optional
from playwright.async_api import Page

from .interactions import PageInteractor, InteractionResult
from .confidence import ScrapedPlan


class AffiliateScraper:
    """Scrapes affiliate sites by iterating through network filters."""
    
    def __init__(
        self,
        page: Page,
        provider_config: Dict[str, Any],
        interaction_config: Dict[str, Any],
        extract_plans_func: Callable[[str, Dict], List[ScrapedPlan]],
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.page = page
        self.provider_config = provider_config
        self.interaction_config = interaction_config
        self.extract_plans = extract_plans_func
        self._log_cb = log_callback or (lambda msg: None)
    
    def _log(self, message: str):
        self._log_cb(f"[Affiliate] {message}")
    
    async def scrape_by_network(self) -> List[ScrapedPlan]:
        """
        Scrape affiliate site once per network filter.
        Each plan gets accurate network attribution from the filter used.
        """
        network_config = self.provider_config.get("network_filter_strategy", {})
        
        if not network_config.get("enabled", False):
            self._log("Network filter strategy not enabled, using standard scrape")
            return await self._standard_scrape()
        
        all_plans: List[ScrapedPlan] = []
        networks = network_config.get("networks_to_scrape", [])
        base_url = self.provider_config.get("base_url") or self.provider_config.get("urls", [])[0]
        
        self._log(f"Scraping {len(networks)} networks from {base_url}")
        
        for network in networks:
            network_name = network.get("name", "")
            filter_value = network.get("filter_value", network_name.lower())
            
            self._log(f"Scraping filtered by {network_name}")
            
            try:
                await self.page.goto(base_url, wait_until="networkidle", timeout=30000)
                
                interactor = PageInteractor(self.page, self.interaction_config, self._log_cb)
                
                await interactor.apply_filter(
                    network_config.get("filter_selector", "network"),
                    filter_value
                )
                
                await self.page.wait_for_timeout(2000)
                
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                
                result = await interactor.execute_sequence(self.provider_config.get("slug", ""))
                
                for context, html in result.html_snapshots:
                    plans = self.extract_plans(html, self.provider_config)
                    
                    for plan in plans:
                        plan.network = network_name
                        plan.confidence_score = min(plan.confidence_score * 1.1, 1.0)
                        if "network_from_filter" not in str(plan.confidence_reasons):
                            plan.confidence_reasons.append(f"network_from_filter:{network_name}")
                    
                    all_plans.extend(plans)
                    self._log(f"Found {len(plans)} plans for {network_name}")
                
            except Exception as e:
                self._log(f"Failed to scrape {network_name}: {e}")
                continue
        
        deduped = self._deduplicate_plans(all_plans)
        self._log(f"Total unique plans: {len(deduped)} (from {len(all_plans)} raw)")
        
        return deduped
    
    async def _standard_scrape(self) -> List[ScrapedPlan]:
        """Fallback to standard scraping without network filters."""
        urls = self.provider_config.get("urls", [])
        if not urls:
            return []
        
        all_plans = []
        for url in urls:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            
            interactor = PageInteractor(self.page, self.interaction_config, self._log_cb)
            result = await interactor.execute_sequence(self.provider_config.get("slug", ""))
            
            for context, html in result.html_snapshots:
                plans = self.extract_plans(html, self.provider_config)
                all_plans.extend(plans)
        
        return self._deduplicate_plans(all_plans)
    
    def _deduplicate_plans(self, plans: List[ScrapedPlan]) -> List[ScrapedPlan]:
        """Remove duplicate plans based on (price, data_gb, network)."""
        seen = set()
        unique = []
        
        for plan in plans:
            key = (plan.price, plan.data_gb, plan.data_unlimited, plan.network)
            if key not in seen:
                seen.add(key)
                unique.append(plan)
        
        return unique
