from .unified_base import UnifiedScraper, ScrapedPlan


class CarphoneWarehouseScraper(UnifiedScraper):
    provider_name = "Carphone Warehouse"
    provider_slug = "carphonewarehouse"
    provider_type = "affiliate"
    urls = ['https://www.carphonewarehouse.com/sim-only-deals']
