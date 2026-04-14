"""giffgaff scraper with goodybag-aware extraction."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class giffgaffScraper(UnifiedScraper):
    provider_name = "giffgaff"
    provider_slug = "giffgaff"
    provider_type = "mvno"
    urls = ['https://www.giffgaff.com/sim-only-plans']

    async def scrape(self):
        """Override to use only our custom extraction (base regex is too loose)."""
        all_plans = []
        for url in self.urls:
            html = await self._fetch_html(url)
            if not html:
                self._log(f"Failed to fetch {url}", "error")
                continue
            self._log(f"Got {len(html)} chars from {url}")
            plans = self._extract_giffgaff(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _extract_giffgaff(self, html, url):
        """giffgaff lists plans as goodybags with clear GB + price combos."""
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        # giffgaff uses card-like elements for each goodybag
        cards = soup.select(
            '[class*="goodybag"], [class*="plan-card"], [class*="price-card"], '
            '[class*="tariff"], [class*="product-card"], [class*="card"]'
        )
        self._log(f"Found {len(cards)} potential plan cards")

        for card in cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 15 or len(text) > 800:
                continue

            price = None
            pm = re.search(r'£(\d+(?:\.\d+)?)', text)
            if pm:
                price = float(pm.group(1))
            if not price or price < 3 or price > 60:
                continue

            data_gb = None
            is_unlimited = 'unlimited' in text.lower()
            if not is_unlimited:
                dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
                if dm:
                    val = int(dm.group(1))
                    if val >= 1 and val <= 500:
                        data_gb = val
            if not data_gb and not is_unlimited:
                continue

            contract_months = 1
            if '18' in text and 'month' in text.lower():
                contract_months = 18
            elif '12' in text and 'month' in text.lower():
                contract_months = 12

            key = (price, data_gb, is_unlimited, contract_months)
            if key in seen:
                continue
            seen.add(key)

            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            plans.append(ScrapedPlan(
                name=f'giffgaff {data_label}',
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                url=url,
                contract_months=contract_months,
                network='giffgaff',
            ))

        # Fallback: parse from page text with tight proximity
        if len(plans) < 5:
            self._log("Card extraction insufficient, using tight regex on page text")
            text = soup.get_text(' ')

            for m in re.finditer(r'(\d{1,3})\s*GB\s+(?:data\s+)?(?:for\s+)?£(\d+(?:\.\d+)?)', text):
                data_gb = int(m.group(1))
                price = float(m.group(2))
                if data_gb < 2 or data_gb > 500 or price < 3 or price > 50:
                    continue
                # Check plausibility: price-per-GB shouldn't be > £5
                if data_gb >= 5 and price / data_gb > 5:
                    continue
                window = text[max(0, m.start()-60):min(len(text), m.end()+60)]
                contract = 18 if '18' in window and 'month' in window.lower() else 1
                key = (price, data_gb, False, contract)
                if key in seen:
                    continue
                seen.add(key)
                plans.append(ScrapedPlan(
                    name=f'giffgaff {data_gb}GB',
                    price=price, data_gb=data_gb, url=url,
                    contract_months=contract, network='giffgaff',
                ))

            # Also capture "£X ... NGB" (reverse order)
            for m in re.finditer(r'£(\d+(?:\.\d+)?)\s+(?:for\s+)?(\d{1,3})\s*GB', text):
                price = float(m.group(1))
                data_gb = int(m.group(2))
                if data_gb < 2 or data_gb > 500 or price < 3 or price > 50:
                    continue
                if data_gb >= 5 and price / data_gb > 5:
                    continue
                window = text[max(0, m.start()-60):min(len(text), m.end()+60)]
                contract = 18 if '18' in window and 'month' in window.lower() else 1
                key = (price, data_gb, False, contract)
                if key in seen:
                    continue
                seen.add(key)
                plans.append(ScrapedPlan(
                    name=f'giffgaff {data_gb}GB',
                    price=price, data_gb=data_gb, url=url,
                    contract_months=contract, network='giffgaff',
                ))

            # Unlimited plans
            for m in re.finditer(r'[Uu]nlimited\s+(?:data\s+)?(?:for\s+)?£(\d+(?:\.\d+)?)', text):
                price = float(m.group(1))
                if price < 10 or price > 50:
                    continue
                window = text[max(0, m.start()-60):min(len(text), m.end()+60)]
                contract = 18 if '18' in window and 'month' in window.lower() else 1
                key = (price, None, True, contract)
                if key in seen:
                    continue
                seen.add(key)
                plans.append(ScrapedPlan(
                    name='giffgaff Unlimited',
                    price=price, data_unlimited=True, url=url,
                    contract_months=contract, network='giffgaff',
                ))

        return plans
