"""VOXI scraper using structured 'Price £XX ... Data NGB' pattern."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class VOXIScraper(UnifiedScraper):
    provider_name = "VOXI"
    provider_slug = "voxi"
    provider_type = "mvno"
    urls = ['https://www.voxi.co.uk/plans']

    async def scrape(self):
        all_plans = []
        for url in self.urls:
            html = await self._fetch_html(url)
            if not html:
                self._log(f"Failed to fetch {url}", "error")
                continue
            self._log(f"Got {len(html)} chars from {url}")
            plans = self._extract_voxi(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "VOXI"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _extract_voxi(self, html, url):
        """
        VOXI page uses 'Price £XX /month Data NGB' structure.
        Must avoid '£5 off first month' promo text.
        """
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(' ')
        seen = set()

        # Primary: match "Price £XX" followed by "Data NGB/Unlimited"
        for m in re.finditer(r'Price\s+£(\d+)\s+.{0,30}?Data\s+(\d+)\s*GB', text):
            price = float(m.group(1))
            data_gb = int(m.group(2))
            if price < 5 or price > 60 or data_gb < 1 or data_gb > 500:
                continue
            key = (price, data_gb, False)
            if key in seen:
                continue
            seen.add(key)
            plans.append(ScrapedPlan(
                name=f'VOXI {data_gb}GB',
                price=price, data_gb=data_gb,
                url=url, contract_months=1,
                network='VOXI', is_5g=True,
            ))

        # Unlimited plans
        for m in re.finditer(r'Price\s+£(\d+)\s+.{0,30}?Data\s+Unlimited', text):
            price = float(m.group(1))
            if price < 10 or price > 60:
                continue
            key = (price, None, True)
            if key in seen:
                continue
            seen.add(key)
            plans.append(ScrapedPlan(
                name='VOXI Unlimited',
                price=price, data_unlimited=True,
                url=url, contract_months=1,
                network='VOXI', is_5g=True,
            ))

        self._log(f"Extracted {len(plans)} plans from structured patterns")
        return plans
