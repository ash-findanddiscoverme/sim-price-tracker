"""Carphone Warehouse - JS-heavy SPA, deals don't render in headless browsers."""

from .unified_base import UnifiedScraper, ScrapedPlan


class CarphoneWarehouseScraper(UnifiedScraper):
    provider_name = "Carphone Warehouse"
    provider_slug = "carphonewarehouse"
    provider_type = "affiliate"
    urls = []

    async def scrape(self):
        self._log("Carphone Warehouse uses heavy client-side rendering - skipping")
        return []
