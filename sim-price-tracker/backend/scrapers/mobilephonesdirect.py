from .unified_base import UnifiedScraper, ScrapedPlan


class MobilePhonesDirectScraper(UnifiedScraper):
    provider_name = "Mobile Phones Direct"
    provider_slug = "mobilephonesdirect"
    provider_type = "affiliate"
    urls = ['https://www.mobilephonesdirect.co.uk/sim-only-deals']
