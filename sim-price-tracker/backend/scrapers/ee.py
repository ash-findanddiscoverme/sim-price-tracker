from .unified_base import UnifiedScraper, ScrapedPlan


class EEScraper(UnifiedScraper):
    provider_name = "EE"
    provider_slug = "ee"
    provider_type = "network"
    urls = ['https://ee.co.uk/mobile/sim-only-deals']
    use_playwright = True
