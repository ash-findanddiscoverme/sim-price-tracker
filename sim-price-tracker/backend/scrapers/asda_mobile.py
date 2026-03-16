import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class AsdaMobileScraper(BaseScraper):
    provider_name = "Asda Mobile"
    provider_slug = "asda-mobile"
    provider_type = "mvno"
    base_url = "https://mobile.asda.com/sim-only"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            # Try ASDA mobile API
            try:
                api_resp = await self.session.get(
                    "https://mobile.asda.com/api/plans",
                    headers={"Accept": "application/json"},
                )
                if api_resp.status_code == 200:
                    try:
                        plans = self._extract_plans(api_resp.json())
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception:
                pass

            # Try httpx page fetch
            if not plans:
                resp = await self.session.get(self.base_url)
                html = resp.text
                if len(html) > 3000:
                    plans = self._try_parse_json(html)
                    if not plans:
                        plans = self._parse_html(html)

            # Playwright fallback
            if not plans:
                logger.info("Asda Mobile: trying playwright")
                html = await fetch_page_content(self.base_url, wait_ms=10000)
                if html:
                    plans = self._try_parse_json(html)
                    if not plans:
                        plans = self._parse_html(html)

            self._deduplicate(plans)
            logger.info(f"Asda Mobile: scraped {len(plans)} plans")
        except Exception as e:
            logger.error(f"Asda Mobile scrape error: {e}")
        return plans

    def _try_parse_json(self, html: str) -> List[ScrapedPlan]:
        plans = []
        patterns = [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        ]
        for pat in patterns:
            for match in re.finditer(pat, html, re.DOTALL):
                try:
                    data = json.loads(match.group(1))
                    extracted = self._extract_plans(data)
                    if extracted:
                        return extracted
                except (json.JSONDecodeError, TypeError):
                    continue
        return plans

    def _extract_plans(self, data, depth=0) -> List[ScrapedPlan]:
        if depth > 10:
            return []
        plans = []
        if isinstance(data, dict):
            price_val = data.get("price", data.get("monthlyPrice", data.get("cost")))
            if price_val is not None:
                try:
                    price = float(price_val)
                    if 1 <= price <= 100:
                        data_val = data.get("data", data.get("dataAllowance", data.get("dataGb")))
                        data_gb = None
                        is_unlimited = False
                        if isinstance(data_val, (int, float)):
                            data_gb = int(data_val)
                        elif isinstance(data_val, str):
                            m = re.search(r"(\d+)", data_val)
                            if m:
                                data_gb = int(m.group(1))
                            if "unlimited" in data_val.lower():
                                is_unlimited = True
                        name = data.get("name", data.get("title", ""))
                        if not name:
                            name = f"Asda Mobile {data_gb}GB" if data_gb else "Asda Mobile Plan"
                        plans.append(ScrapedPlan(
                            name=name, price=price, data_gb=data_gb,
                            data_unlimited=is_unlimited, url=self.base_url,
                            external_id=f"asda-mobile_{price}_{data_gb or 'unlimited'}",
                        ))
                except (ValueError, TypeError):
                    pass
            for v in data.values():
                plans.extend(self._extract_plans(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                plans.extend(self._extract_plans(item, depth + 1))
        return plans

    def _parse_html(self, html: str) -> List[ScrapedPlan]:
        plans = []
        seen = set()
        pound = "\u00a3"
        for price_m in re.finditer(pound + r"\s*(\d+(?:\.\d{1,2})?)", html):
            price = float(price_m.group(1))
            if price < 1 or price > 100:
                continue
            start = max(0, price_m.start() - 500)
            end = min(len(html), price_m.end() + 500)
            context = html[start:end]
            gb_m = re.search(r"(\d+)\s*GB", context, re.IGNORECASE)
            data_gb = int(gb_m.group(1)) if gb_m else None
            unlimited = bool(re.search(r"unlimited", context, re.IGNORECASE))
            key = (price, data_gb)
            if key in seen:
                continue
            seen.add(key)
            if not data_gb and not unlimited:
                continue
            label = f"{data_gb}GB" if data_gb else "Unlimited"
            plans.append(ScrapedPlan(
                name=f"Asda Mobile {label}", price=price, data_gb=data_gb,
                data_unlimited=unlimited and not data_gb, url=self.base_url,
                external_id=f"asda-mobile_{price}_{data_gb or 'unlimited'}",
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
