from .unified_base import UnifiedScraper, ScrapedPlan


class giffgaffScraper(UnifiedScraper):
    provider_name = "giffgaff"
    provider_slug = "giffgaff"
    provider_type = "mvno"
    urls = ['https://www.giffgaff.com/sim-only-plans']
