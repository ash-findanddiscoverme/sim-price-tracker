from .unified_base import UnifiedScraper, ScrapedPlan


class MoneySupermarketScraper(UnifiedScraper):
    provider_name = "MoneySupermarket"
    provider_slug = "moneysupermarket"
    provider_type = "affiliate"
    urls = ['https://www.moneysupermarket.com/mobile-phones/sim-only/']
