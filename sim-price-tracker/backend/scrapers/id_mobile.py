from .unified_base import UnifiedScraper, ScrapedPlan


class iDMobileScraper(UnifiedScraper):
    provider_name = "iD Mobile"
    provider_slug = "id-mobile"
    provider_type = "mvno"
    urls = ['https://www.idmobile.co.uk/sim-only']
