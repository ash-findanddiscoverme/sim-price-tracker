from .unified_base import UnifiedScraper, ScrapedPlan


class TescoMobileScraper(UnifiedScraper):
    provider_name = "Tesco Mobile"
    provider_slug = "tesco-mobile"
    provider_type = "mvno"
    urls = ['https://www.tescomobile.com/shop/sim-only']
    use_playwright = True
