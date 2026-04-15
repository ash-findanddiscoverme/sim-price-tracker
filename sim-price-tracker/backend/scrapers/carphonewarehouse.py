"""Carphone Warehouse scraper with network attribution.

Carphone Warehouse is a retailer/affiliate, not an MNO or MVNO.
Plans must be attributed to the actual network.
"""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, extract_contract, extract_network, extract_5g, KNOWN_NETWORKS

logger = logging.getLogger(__name__)


class CarphoneWarehouseScraper(UnifiedScraper):
    provider_name = "Carphone Warehouse"
    provider_slug = "carphonewarehouse"
    provider_type = "affiliate"
    urls = ['https://www.carphonewarehouse.com/sim-only-deals']
    use_playwright = True

    def _extract_from_html(self, html, url):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        cards = soup.select(
            'article, [class*="deal"], [class*="result"], '
            '[class*="card"], [class*="tariff"], [class*="plan"], '
            '[class*="product"], [class*="offer"]'
        )
        self._log(f"Found {len(cards)} deal cards")

        for card in cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 30 or len(text) > 3000:
                continue

            network = extract_network(text)
            if not network:
                for img in card.select('img'):
                    alt = img.get('alt', '') or img.get('title', '')
                    network = extract_network(alt)
                    if network:
                        break

            if not network:
                continue

            price = None
            pm = re.search(r'£\s?(\d+(?:\.\d+)?)\s*(?:a month|/mo|per month|monthly|p/m|pm)', text, re.IGNORECASE)
            if pm:
                price = float(pm.group(1))
            else:
                all_prices = re.findall(r'£\s?(\d+(?:\.\d+)?)', text)
                for p_str in all_prices:
                    pv = float(p_str)
                    if 3 <= pv <= 100:
                        price = pv
                        break

            if not price or price < 3 or price > 100:
                continue

            data_gb = None
            text_lower = text.lower()
            is_unlimited = 'unlimited' in text_lower
            if not is_unlimited:
                dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
                if dm:
                    data_gb = int(dm.group(1))
            if not data_gb and not is_unlimited:
                continue

            contract_months = extract_contract(text)
            is_5g = extract_5g(text)
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            name = f'{network} {data_label}'

            key = (network, price, data_gb, is_unlimited, contract_months)
            if key in seen:
                continue
            seen.add(key)

            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract_months,
                network=network,
            ))

        if not plans:
            self._log("Card parsing yielded nothing, falling back to regex with network filter", "warning")
            all_plans = self._extract_from_regex(html, url)
            for plan in all_plans:
                if plan.network:
                    data_label = 'Unlimited' if plan.data_unlimited else f'{plan.data_gb}GB'
                    plan.name = f'{plan.network} {data_label}'
            plans = [p for p in all_plans if p.network]

        return plans
