from .unified_base import UnifiedScraper, ScrapedPlan


class VodafoneScraper(UnifiedScraper):
    provider_name = "Vodafone"
    provider_slug = "vodafone"
    provider_type = "network"
    urls = ['https://www.vodafone.co.uk/mobile/best-sim-only-deals']
