import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class GiffgaffScraper(BaseScraper):
    provider_name = "giffgaff"
    provider_slug = "giffgaff"
    provider_type = "mvno"
    base_url = "https://www.giffgaff.com/sim-only-plans"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            # Try goodybag API endpoint first
            try:
                api_resp = await self.session.get(
                    "https://www.giffgaff.com/api/goodybag",
                    headers={"Accept": "application/json"},
                )
                if api_resp.status_code == 200:
                    try:
                        plans = self._extract_from_api(api_resp.json())
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception as e:
                logger.debug(f"giffgaff API attempt failed: {e}")

            if not plans:
                resp = await self.session.get(self.base_url)
                html = resp.text
                plans = self._try_parse_next_data(html)
                if not plans:
                    plans = self._try_parse_json_ld(html)
                if not plans:
                    plans = self._try_parse_html_regex(html)

            if not plans:
                logger.info("giffgaff: httpx got no plans, trying playwright")
                html = await fetch_page_content(self.base_url, wait_ms=10000)
                plans = self._try_parse_next_data(html)
                if not plans:
                    plans = self._try_parse_html_regex(html)

            self._deduplicate(plans)
            logger.info(f"giffgaff: scraped {len(plans)} plans")
        except Exception as e:
            logger.error(f"giffgaff scrape error: {e}")
        return plans

    def _extract_from_api(self, data) -> List[ScrapedPlan]:
        plans = []
        items = data if isinstance(data, list) else data.get("goodybags", data.get("plans", []))
        for p in items:
            try:
                price = float(p.get("price", p.get("monthlyPrice", 0)))
                if price <= 0:
                    continue
                data_val = p.get("data", p.get("dataAllowance", p.get("dataGb")))
                is_unlimited = p.get("unlimitedData", False)
                if isinstance(data_val, str) and "unlimited" in data_val.lower():
                    is_unlimited = True
                    data_val = None
                data_gb = int(data_val) if data_val and not is_unlimited else None
                name = p.get("name", p.get("title", ""))
                if not name:
                    name = f"giffgaff {data_gb}GB" if data_gb else "giffgaff Unlimited"
                plans.append(ScrapedPlan(
                    name=name, price=price, data_gb=data_gb,
                    data_unlimited=is_unlimited, url=self.base_url,
                    is_5g=bool(p.get("is5g", p.get("fiveG", False))),
                    external_id=f"giffgaff_{price}_{data_gb or 'unlimited'}",
                ))
            except (ValueError, TypeError, KeyError):
                continue
        return plans

    def _try_parse_next_data(self, html: str) -> List[ScrapedPlan]:
        plans = []
        match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        if not match:
            return plans
        try:
            data = json.loads(match.group(1))
            page_props = data.get("props", {}).get("pageProps", {})
            plan_list = (
                page_props.get("plans")
                or page_props.get("goodybags")
                or page_props.get("simOnlyPlans")
                or []
            )
            if not plan_list:
                plan_list = self._find_plan_arrays(data)
            for p in plan_list:
                price = float(p.get("price", p.get("monthlyPrice", p.get("cost", 0))))
                if price <= 0:
                    continue
                data_val = p.get("data", p.get("dataAllowance", p.get("dataGb")))
                is_unlimited = p.get("unlimitedData", False)
                if isinstance(data_val, str) and "unlimited" in data_val.lower():
                    is_unlimited = True
                    data_val = None
                data_gb = int(data_val) if data_val and not is_unlimited else None
                name = p.get("name", p.get("title", ""))
                if not name:
                    name = f"giffgaff {data_gb}GB" if data_gb else "giffgaff Unlimited"
                plans.append(ScrapedPlan(
                    name=name, price=price, data_gb=data_gb,
                    data_unlimited=is_unlimited, url=self.base_url,
                    external_id=f"giffgaff_{price}_{data_gb or 'unlimited'}",
                ))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"giffgaff __NEXT_DATA__ parse failed: {e}")
        return plans

    def _find_plan_arrays(self, data, depth=0) -> list:
        if depth > 6:
            return []
        if isinstance(data, list) and len(data) >= 2:
            if all(isinstance(i, dict) and ("price" in i or "monthlyPrice" in i) for i in data[:3]):
                return data
        if isinstance(data, dict):
            for v in data.values():
                result = self._find_plan_arrays(v, depth + 1)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_plan_arrays(item, depth + 1)
                if result:
                    return result
        return []

    def _try_parse_json_ld(self, html: str) -> List[ScrapedPlan]:
        plans = []
        for match in re.finditer(
            r'<script[^>]*type="application/ld\\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        ):
            try:
                data = json.loads(match.group(1))
                offers = []
                if isinstance(data, dict):
                    offers = data.get("offers", [])
                    if isinstance(offers, dict):
                        offers = offers.get("itemListElement", [offers])
                    catalog = data.get("hasOfferCatalog", {})
                    if isinstance(catalog, dict) and not offers:
                        offers = catalog.get("itemListElement", [])
                for offer in offers:
                    price = float(offer.get("price", 0))
                    if price <= 0:
                        continue
                    name = offer.get("name", "giffgaff plan")
                    data_gb = None
                    gb_match = re.search(r"(\d+)\s*GB", name, re.IGNORECASE)
                    if gb_match:
                        data_gb = int(gb_match.group(1))
                    is_unlimited = "unlimited" in name.lower()
                    plans.append(ScrapedPlan(
                        name=name, price=price, data_gb=data_gb,
                        data_unlimited=is_unlimited, url=self.base_url,
                        external_id=f"giffgaff_{price}_{data_gb or 'unlimited'}",
                    ))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return plans

    def _try_parse_html_regex(self, html: str) -> List[ScrapedPlan]:
        plans = []
        seen = set()
        pound_sign = chr(163)
        for price_m in re.finditer(pound_sign + r'\s*(\d+(?:\.\d{1,2})?)', html):
            price = float(price_m.group(1))
            if price < 3 or price > 100:
                continue
            start = max(0, price_m.start() - 500)
            end = min(len(html), price_m.end() + 500)
            context = html[start:end]
            gb_m = re.search(r'(\d+)\s*GB', context, re.IGNORECASE)
            data_gb = int(gb_m.group(1)) if gb_m else None
            unlimited = bool(re.search(r'unlimited\s*data', context, re.IGNORECASE))
            key = (price, data_gb)
            if key in seen:
                continue
            seen.add(key)
            if data_gb:
                label = f"{data_gb}GB"
            elif unlimited:
                label = "Unlimited"
            else:
                continue
            plans.append(ScrapedPlan(
                name=f"giffgaff {label}", price=price, data_gb=data_gb,
                data_unlimited=unlimited and not data_gb, url=self.base_url,
                external_id=f"giffgaff_{price}_{data_gb or 'unlimited'}",
            ))
        return plans

    @staticmethod
    def _deduplicate(plans: List[ScrapedPlan]):
        seen = set()
        i = 0
        while i < len(plans):
            if plans[i].external_id in seen:
                plans.pop(i)
            else:
                seen.add(plans[i].external_id)
                i += 1

