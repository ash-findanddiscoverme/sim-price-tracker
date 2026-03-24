from .unified_base import UnifiedScraper, ScrapedPlan


class VOXIScraper(UnifiedScraper):
    provider_name = "VOXI"
    provider_slug = "voxi"
    provider_type = "mvno"
    urls = ['https://www.voxi.co.uk/plans']
