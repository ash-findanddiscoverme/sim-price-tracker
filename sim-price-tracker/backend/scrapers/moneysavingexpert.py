"""MoneySavingExpert - editorial site, no structured SIM comparison page."""

from .unified_base import UnifiedScraper, ScrapedPlan


class MoneySavingExpertScraper(UnifiedScraper):
    provider_name = "MoneySavingExpert"
    provider_slug = "moneysavingexpert"
    provider_type = "affiliate"
    urls = []

    async def scrape(self):
        self._log("MoneySavingExpert has no structured SIM comparison page - skipping")
        return []
