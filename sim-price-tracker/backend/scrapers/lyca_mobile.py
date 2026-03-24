from .unified_base import UnifiedScraper, ScrapedPlan


class LycaMobileScraper(UnifiedScraper):
    provider_name = "Lyca Mobile"
    provider_slug = "lyca-mobile"
    provider_type = "mvno"
    urls = ['https://www.lycamobile.co.uk/en/bundles']
