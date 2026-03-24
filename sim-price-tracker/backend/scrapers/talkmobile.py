from .unified_base import UnifiedScraper, ScrapedPlan


class TalkmobileScraper(UnifiedScraper):
    provider_name = "Talkmobile"
    provider_slug = "talkmobile"
    provider_type = "mvno"
    urls = ['https://www.talkmobile.co.uk/sim-only-deals']
