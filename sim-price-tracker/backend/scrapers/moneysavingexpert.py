from .unified_base import UnifiedScraper, ScrapedPlan


class MoneySavingExpertScraper(UnifiedScraper):
    provider_name = "MoneySavingExpert"
    provider_slug = "moneysavingexpert"
    provider_type = "affiliate"
    urls = ['https://www.moneysavingexpert.com/cheap-mobile-phones/']
