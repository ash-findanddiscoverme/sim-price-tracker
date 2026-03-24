from .unified_base import UnifiedScraper, ScrapedPlan


class AsdaMobileScraper(UnifiedScraper):
    provider_name = "Asda Mobile"
    provider_slug = "asda-mobile"
    provider_type = "mvno"
    urls = ['https://mobile.asda.com/sim-only']
    use_playwright = True
