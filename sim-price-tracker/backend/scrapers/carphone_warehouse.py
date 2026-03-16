import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan

logger = logging.getLogger(__name__)

NETWORK_NAMES = [
    "EE", "Three", "O2", "Vodafone", "Sky Mobile", "iD Mobile",
    "Tesco Mobile", "VOXI", "giffgaff", "Lebara", "Smarty",
    "Lyca Mobile", "BT Mobile", "Plusnet",
]

URLS = [
    "https://www.carphonewarehouse.com/sim-only",
    "https://www.currys.co.uk/mobiles/sim-only-deals",
]

PAT_HTML_TAG = re.compile(r'<[^>]+>')
PAT_MONTH = re.compile(r'(\d+)\s*month', re.IGNORECASE)


class CarphoneWarehouseScraper(BaseScraper):
    provider_name = "Carphone Warehouse"
    provider_slug = "cpw"
    provider_type = "affiliate"
    base_url = "https://www.carphonewarehouse.com/sim-only"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            html = await self._fetch_html()
            if not html:
                logger.warning("Carphone Warehouse: empty response")
                return plans
            plans = self._parse_json_data(html)
            if not plans:
                plans = self._parse_html_deals(html)
            if not plans:
                plans = await self._playwright_fallback()
            plans = self._deduplicate(plans)
            logger.info(f"Carphone Warehouse: Found {len(plans)} plans")
        except Exception as e:
            logger.error(f"Carphone Warehouse scrape error: {e}")
        return plans

    async def _fetch_html(self) -> str:
        for url in URLS:
            try:
                resp = await self.session.get(url)
                if resp.status_code == 200 and len(resp.text) > 500:
                    self.base_url = str(resp.url)
                    return resp.text
            except Exception as e:
                logger.debug(f"CPW fetch {url} failed: {e}")
                continue
        return ""

    def _parse_json_data(self, html: str) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        for pattern in [
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*(.*?)\s*</script>',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*</script>',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if not match: continue
            try:
                data = json.loads(match.group(1))
                plans = self._walk_json(data)
                if plans: return plans
            except (json.JSONDecodeError, KeyError): continue
        return plans

    def _walk_json(self, data, depth=0) -> List[ScrapedPlan]:
        if depth > 8: return []
        plans: List[ScrapedPlan] = []
        if isinstance(data, dict):
            price_keys = {"monthlyCost", "monthlyPrice", "price", "costPerMonth", "monthly"}
            if price_keys & data.keys():
                plan = self._obj_to_plan(data)
                if plan: plans.append(plan)
            for v in data.values():
                plans.extend(self._walk_json(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                plans.extend(self._walk_json(item, depth + 1))
        return plans

    def _obj_to_plan(self, obj: dict):
        try:
            price = None
            for key in ("monthlyCost", "monthlyPrice", "price", "costPerMonth", "monthly"):
                if key in obj:
                    val = str(obj[key]).replace("\u00a3", "").replace("\xa3", "").strip()
                    try:
                        price = float(val)
                        if price > 0: break
                    except ValueError: continue
            if not price or price <= 0 or price > 200: return None
            data_gb = None
            data_unlimited = False
            for key in ("data", "dataAllowance", "dataGB", "allowance"):
                if key in obj:
                    val = str(obj[key]).lower()
                    if "unlimited" in val: data_unlimited = True
                    else:
                        m = re.search(r"(\d+)", val)
                        if m: data_gb = int(m.group(1))
                    break
            network = obj.get("network", obj.get("provider", obj.get("networkName", "")))
            contract = 1
            for key in ("contractLength", "months", "length"):
                if key in obj:
                    m = re.search(r"(\d+)", str(obj[key]))
                    if m: contract = int(m.group(1))
                    break
            is_5g = any("5g" in str(v).lower() for v in obj.values() if isinstance(v, str))
            name = f"{network} " if network else ""
            if data_unlimited: name += "Unlimited Data"
            elif data_gb: name += f"{data_gb}GB"
            else: name += "SIM Only"
            data_tag = "unl" if data_unlimited else str(data_gb)
            return ScrapedPlan(
                name=name.strip(), price=price, data_gb=data_gb,
                data_unlimited=data_unlimited, contract_months=contract,
                url=self.base_url, is_5g=is_5g,
                external_id=f"cpw_{price}_{data_tag}",
            )
        except Exception: return None

    def _parse_html_deals(self, html: str) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        seen: set = set()
        card_re = r'[\xa3\u00a3](\d+(?:\.\d+)?)\s*/?\s*(?:mo|pm|p/m|per\s+month|month).*?(\d+)\s*GB'
        for m in re.finditer(card_re, html):
            price = float(m.group(1))
            data_gb = int(m.group(2))
            if price <= 0 or price > 200 or data_gb <= 0: continue
            key = f"{price}_{data_gb}"
            if key in seen: continue
            seen.add(key)
            context = html[max(0, m.start() - 500):m.end() + 300]
            context_text = PAT_HTML_TAG.sub(" ", context)
            network = self._find_network(context_text)
            is_5g = "5g" in context_text.lower()
            contract = 1
            month_m = PAT_MONTH.search(context_text)
            if month_m: contract = int(month_m.group(1))
            name = f"{network} {data_gb}GB" if network else f"{data_gb}GB SIM Only"
            plans.append(ScrapedPlan(name=name, price=price, data_gb=data_gb, contract_months=contract, url=self.base_url, is_5g=is_5g, external_id=f"cpw_{price}_{data_gb}"))
        return plans

    def _find_network(self, text: str) -> str:
        text_lower = text.lower()
        for net in NETWORK_NAMES:
            if net.lower() in text_lower: return net
        return ""

    def _deduplicate(self, plans: List[ScrapedPlan]) -> List[ScrapedPlan]:
        seen: set = set()
        unique: List[ScrapedPlan] = []
        for plans_item in plans:
            if plans_item.external_id and plans_item.external_id not in seen:
                seen.add(plans_item.external_id)
                unique.append(plans_item)
        return unique

    async def _playwright_fallback(self) -> List[ScrapedPlan]:
        try:
            from .playwright_helper import fetch_page_content
            for url in URLS:
                html = await fetch_page_content(url, wait_ms=12000)
                if html and len(html) > 500:
                    plans = self._parse_json_data(html)
                    if not plans: plans = self._parse_html_deals(html)
                    if plans: return plans
        except Exception as e:
            logger.warning(f"Carphone Warehouse playwright fallback failed: {e}")
        return []

