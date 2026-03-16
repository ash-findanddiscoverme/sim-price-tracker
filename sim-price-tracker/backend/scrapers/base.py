from dataclasses import dataclass
from typing import List, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

@dataclass
class ScrapedPlan:
    name: str
    price: float
    data_gb: Optional[int] = None
    data_unlimited: bool = False
    contract_months: int = 1
    url: str = ""
    is_5g: bool = False
    minutes: str = "unlimited"
    texts: str = "unlimited"
    external_id: Optional[str] = None


class BaseScraper:
    provider_name: str = "Unknown"
    provider_slug: str = "unknown"
    provider_type: str = "network"
    base_url: str = ""

    def __init__(self):
        self.session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            },
            timeout=30.0,
            follow_redirects=True,
            verify=False,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()

    async def scrape(self) -> List[ScrapedPlan]:
        raise NotImplementedError("Subclasses must implement scrape()")
