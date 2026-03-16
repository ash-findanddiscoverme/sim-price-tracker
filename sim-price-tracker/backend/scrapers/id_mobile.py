import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class IDMobileScraper(BaseScraper):
    provider_name = "iD Mobile"
    provider_slug = "id-mobile"
    provider_type = "mvno"
    base_url = "https://www.idmobile.co.uk/sim-only"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            # Try iD Mobile API endpoints (Three network)
            for api_url in [
                "https://www.idmobile.co.uk/api/plans/sim-only",
                "https://www.idmobile.co.uk/api/v1/deals",
            ]:
                try:
                    api_resp = await self.session.get(
                        api_url, headers={"Accept": "application/json"},
                    )
                    if api_resp.status_code == 200:
                        try:
                            plans = self._extract_plans(api_resp.json())
                            if plans:
                                break
                        except (json.JSONDecodeError, TypeError):
                            pass
                except Exception:
                    continue

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
                logger.info("iD Mobile: trying playwright")
                html = await fetch_page_content(
                    self.base_url, wait_ms=12000,
                    selector='[class*="plan"], [class*="tariff"], [class*="deal"]',
                )
                if html:
                    plans = self._try_parse_json(html)
                    if not plans:
                        plans = self._parse_html(html)

            self._deduplicate(plans)
            logger.info(f"iD Mobile: scraped {len(plans)} plans")
        except Exception as e:
            logger.error(f"iD Mobile scrape error: {e}")
        return plans

    def _try_parse_json(self, html: str) -> List[ScrapedPlan]:
        plans = []
        patterns = [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        ]
        for pat in patterns:
            for match in re.finditer(pat, html, re.DOTALL):
                raw = match.group(1).strip()
                if len(raw) < 50:
                    continue
                try:
                    data = json.loads(raw)
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
            price_val = data.get("price", data.get("monthlyPrice", data.get("monthlyCost")))
            if price_val is not None:
                try:
                    price = float(price_val)
                    if 1 <= price <= 100:
                        dv = data.get("data", data.get("dataAllowance", data.get("dataGb")))
                        data_gb = None
                        is_unlimited = False
                        if isinstance(dv, (int, float)):
                            data_gb = int(dv)
                        elif isinstance(dv, str):
                            m = re.search(r"(\d+)", dv)
                            if m:
                                data_gb = int(m.group(1))
                            if "unlimited" in dv.lower():
                                is_unlimited = True
                        name = data.get("name", data.get("title", ""))
                        if not name:
                            name = f"iD Mobile {data_gb}GB" if data_gb else "iD Mobile Plan"
                        is_5g = "5g" in str(data).lower()
                        contract = 1
                        for ck in ("contractLength", "term", "duration"):
                            if ck in data:
                                try:
                                    contract = int(data[ck])
                                except (ValueError, TypeError):
                                    pass
                                break
                        plans.append(ScrapedPlan(
                            name=name, price=price, data_gb=data_gb,
                            data_unlimited=is_unlimited, url=self.base_url,
                            is_5g=is_5g, contract_months=contract,
                            external_id=f"id-mobile_{price}_{data_gb or 'unlimited'}",
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
            if price < 2 or price > 100:
                continue
            start = max(0, price_m.start() - 600)
            end = min(len(html), price_m.end() + 600)
            ctx = html[start:end]
            gb_m = re.search(r"(\d+)\s*GB", ctx, re.IGNORECASE)
            data_gb = int(gb_m.group(1)) if gb_m else None
            unlimited = bool(re.search(r"unlimited\s*data", ctx, re.IGNORECASE))
            is_5g = bool(re.search(r"5G", ctx))
            key = (price, data_gb)
            if key in seen:
                continue
            seen.add(key)
            if not data_gb and not unlimited:
                continue
            label = f"{data_gb}GB" if data_gb else "Unlimited"
            plans.append(ScrapedPlan(
                name=f"iD Mobile {label}", price=price, data_gb=data_gb,
                data_unlimited=unlimited and not data_gb, url=self.base_url,
                is_5g=is_5g,
                external_id=f"id-mobile_{price}_{data_gb or 'unlimited'}",
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
