from .unified_base import UnifiedScraper, ScrapedPlan


class ThreeScraper(UnifiedScraper):
    provider_name = "Three"
    provider_slug = "three"
    provider_type = "network"
    urls = ['https://www.three.co.uk/sim-only']
    use_playwright = True
