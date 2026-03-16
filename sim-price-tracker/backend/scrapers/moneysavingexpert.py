import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan

logger = logging.getLogger(__name__)

NETWORK_NAMES = [
    "EE",
    "Three",
    "O2",
    "Vodafone",
    "Sky Mobile",
    "iD Mobile",
    "Tesco Mobile",
    "VOXI",
    "giffgaff",
    "Lebara",
    "Smarty",
    "Lyca Mobile",
    "BT Mobile",
    "Asda Mobile",
    "Plusnet",
]

PAT_TABLE_ROW = re.compile(r'(?s)<tr[^>]*>(.*?)</tr>')
PAT_TABLE_CELL = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
PAT_HTML_TAG = re.compile(r'<[^>]+>')
PAT_PRICE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:/\s*mo|p/?m|per\s+month|a\s+month)')
PAT_DATA_GB = re.compile(r'(\d+)\s*GB', re.IGNORECASE)
PAT_UNLIMITED = re.compile(r'unlimited\s+data', re.IGNORECASE)
PAT_MONTH = re.compile(r'(\d+)\s*month', re.IGNORECASE)
PAT_CARD = re.compile(
    r'(?s)class="[^"]*(?:deal|offer|pick|result|listing|card)[^"]*"[^>]*>'
    r'(.*?)</(?:div|section|article|li)>'
)
PAT_DATA_PRICE = re.compile(
    r'(\d+)\s*GB[^0-9]{0,80}(\d+(?:\.\d+)?)\s*(?:/?\s*(?:mo|pm|p/m|per\s+month))',
    re.IGNORECASE,
)
PAT_PRICE_DATA = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:/?\s*(?:mo|pm|p/m|per\s+month))[^0-9]{0,80}(\d+)\s*GB',
    re.IGNORECASE,
)


class MoneySavingExpertScraper(BaseScraper):
    provider_name = "MoneySavingExpert"
    provider_slug = "mse"
    provider_type = "affiliate"
    base_url = "https://www.moneysavingexpert.com/phones/cheap-sim-only-deals/"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            resp = await self.session.get(self.base_url)
            html = resp.text
            plans = self._parse_deal_tables(html)
            if not plans:
                plans = self._parse_deal_cards(html)
            if not plans:
                plans = self._parse_inline_deals(html)
            if not plans:
                plans = await self._playwright_fallback()
            plans = self._deduplicate(plans)
            logger.info(f"MoneySavingExpert: Found {len(plans)} plans")
        except Exception as e:
            logger.error(f"MoneySavingExpert scrape error: {e}")
        return plans

    def _parse_deal_tables(self, html: str) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        for row_match in PAT_TABLE_ROW.finditer(html):
            row_html = row_match.group(1)
            cells = PAT_TABLE_CELL.findall(row_html)
            if len(cells) < 2:
                continue
            row_text = PAT_HTML_TAG.sub(" ", row_html)
            price_m = PAT_PRICE.search(row_text)
            if not price_m:
                continue
            price = float(price_m.group(1))
            if price <= 0 or price > 200:
                continue
            data_gb = None
            data_unlimited = False
            if PAT_UNLIMITED.search(row_text):
                data_unlimited = True
            else:
                gb_m = PAT_DATA_GB.search(row_text)
                if gb_m:
                    data_gb = int(gb_m.group(1))
            if not data_gb and not data_unlimited:
                continue
            network = self._find_network(row_text)
            contract = 1
            month_m = PAT_MONTH.search(row_text)
            if month_m:
                contract = int(month_m.group(1))
            is_5g = "5g" in row_text.lower()
            name = f"{network} " if network else ""
            if data_unlimited:
                name += "Unlimited Data"
            elif data_gb:
                name += f"{data_gb}GB"
            data_tag = "unl" if data_unlimited else str(data_gb)
            plans.append(ScrapedPlan(
                name=name.strip(), price=price, data_gb=data_gb,
                data_unlimited=data_unlimited, contract_months=contract,
                url=self.base_url, is_5g=is_5g,
                external_id=f"mse_{price}_{data_tag}",
            ))
        return plans

    def _find_network(self, text: str) -> str:
        text_lower = text.lower()
        for net in NETWORK_NAMES:
            if net.lower() in text_lower:
                return net
        return ""

    def _deduplicate(self, plans: List[ScrapedPlan]) -> List[ScrapedPlan]:
        seen: set = set()
        unique: List[ScrapedPlan] = []
        for p in plans:
            if p.external_id and p.external_id not in seen:
                seen.add(p.external_id)
                unique.append(p)
        return unique

    async def _playwright_fallback(self) -> List[ScrapedPlan]:
        try:
            from .playwright_helper import fetch_page_content
            html = await fetch_page_content(self.base_url, wait_ms=10000)
            if html:
                plans = self._parse_deal_tables(html)
                if not plans:
                    plans = self._parse_deal_cards(html)
                if not plans:
                    plans = self._parse_inline_deals(html)
                return plans
        except Exception as e:
            logger.warning(f"MoneySavingExpert playwright fallback failed: {e}")
        return []

