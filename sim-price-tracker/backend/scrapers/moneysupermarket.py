import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan

logger = logging.getLogger(__name__)

NETWORK_NAMES = [
    "EE", "Three", "O2", "Vodafone", "Sky Mobile", "iD Mobile",
    "Tesco Mobile", "VOXI", "giffgaff", "Lebara", "Smarty",
    "Lyca Mobile", "BT Mobile", "Asda Mobile", "Plusnet",
]


class MoneySupermarketScraper(BaseScraper):
    provider_name = "MoneySupermarket"
    provider_slug = "moneysupermarket"
    provider_type = "affiliate"
    base_url = "https://www.moneysupermarket.com/mobile-phones/sim-only/"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            resp = await self.session.get(self.base_url)
            html = resp.text

            plans = self._parse_json_data(html)
            if not plans:
                plans = self._parse_html(html)
            if not plans:
                plans = await self._playwright_fallback()

            plans = self._deduplicate(plans)
            logger.info(f"MoneySupermarket: Found {len(plans)} plans")
        except Exception as e:
            logger.error(f"MoneySupermarket scrape error: {e}")
        return plans

    # -- Embedded JSON parsing ------------------------------------------------

    def _parse_json_data(self, html: str) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        patterns = [
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*(.*?)\s*</script>',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>',
            r'window\.__data\s*=\s*(\{.*?\});?\s*</script>',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
                plans = self._walk_json_for_deals(data)
                if plans:
                    return plans
            except (json.JSONDecodeError, KeyError):
                continue
        return plans

    def _walk_json_for_deals(self, data, depth=0) -> List[ScrapedPlan]:
        if depth > 8:
            return []
        plans: List[ScrapedPlan] = []
        if isinstance(data, dict):
            price_keys = {"monthlyCost", "monthlyPrice", "price", "costPerMonth", "monthly_cost"}
            if price_keys & data.keys():
                plan = self._deal_to_plan(data)
                if plan:
                    plans.append(plan)
            for v in data.values():
                plans.extend(self._walk_json_for_deals(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                plans.extend(self._walk_json_for_deals(item, depth + 1))
        return plans

    def _deal_to_plan(self, obj: dict):
        try:
            price = None
            for key in ("monthlyCost", "monthlyPrice", "price", "costPerMonth", "monthly_cost"):
                if key in obj:
                    val = str(obj[key]).replace("\u00a3", "").replace("\xa3", "").strip()
                    try:
                        price = float(val)
                        if price > 0:
                            break
                    except ValueError:
                        continue
            if not price or price <= 0 or price > 200:
                return None

            data_gb = None
            data_unlimited = False
            for key in ("data", "dataAllowance", "allowance"):
                if key in obj:
                    val = str(obj[key]).lower()
                    if "unlimited" in val:
                        data_unlimited = True
                    else:
                        m = re.search(r"(\d+)", val)
                        if m:
                            data_gb = int(m.group(1))
                    break

            network = obj.get("network", obj.get("provider", obj.get("networkName", "")))
            contract = 1
            for key in ("contractLength", "term", "length"):
                if key in obj:
                    m = re.search(r"(\d+)", str(obj[key]))
                    if m:
                        contract = int(m.group(1))
                    break

            is_5g = any("5g" in str(v).lower() for v in obj.values() if isinstance(v, str))

            name = f"{network} " if network else ""
            if data_unlimited:
                name += "Unlimited Data"
            elif data_gb:
                name += f"{data_gb}GB"
            else:
                name += "SIM Only"

            data_tag = "unl" if data_unlimited else str(data_gb)
            return ScrapedPlan(
                name=name.strip(),
                price=price,
                data_gb=data_gb,
                data_unlimited=data_unlimited,
                contract_months=contract,
                url=self.base_url,
                is_5g=is_5g,
                external_id=f"msm_{price}_{data_tag}",
            )
        except Exception:
            return None

    # -- HTML regex fallback --------------------------------------------------

    def _parse_html(self, html: str) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        seen: set = set()

        card_re = r'[\xa3\u00a3](\d+(?:\.\d+)?)\s*/?\s*(?:mo|pm|p/m|per\s+month|month).*?(\d+)\s*GB'
        for m in re.finditer(card_re, html):
            price = float(m.group(1))
            data_gb = int(m.group(2))
            if price <= 0 or price > 200 or data_gb <= 0:
                continue
            key = f"{price}_{data_gb}"
            if key in seen:
                continue
            seen.add(key)

            context = html[max(0, m.start() - 500):m.end() + 300]
            network = self._find_network(context)
            is_5g = "5g" in context.lower()

            name = f"{network} {data_gb}GB" if network else f"{data_gb}GB SIM Only"
            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                url=self.base_url,
                is_5g=is_5g,
                external_id=f"msm_{price}_{data_gb}",
            ))

        unl_re = r'[\xa3\u00a3](\d+(?:\.\d+)?)\s*/?\s*(?:mo|pm|p/m|per\s+month|month).*?[Uu]nlimited\s+[Dd]ata'
        for m in re.finditer(unl_re, html):
            price = float(m.group(1))
            if price <= 0 or price > 200:
                continue
            key = f"{price}_unl"
            if key in seen:
                continue
            seen.add(key)
            context = html[max(0, m.start() - 500):m.end() + 300]
            network = self._find_network(context)
            name = f"{network} Unlimited" if network else "Unlimited Data"
            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_unlimited=True,
                url=self.base_url,
                external_id=f"msm_{price}_unlimited",
            ))

        return plans

    # -- helpers --------------------------------------------------------------

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
            html = await fetch_page_content(
                self.base_url,
                wait_ms=12000,
                selector='[class*="deal"], [class*="plan"], [class*="card"]',
            )
            if html:
                plans = self._parse_json_data(html)
                if not plans:
                    plans = self._parse_html(html)
                return plans
        except Exception as e:
            logger.warning(f"MoneySupermarket playwright fallback failed: {e}")
        return []
