import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class TescoMobileScraper(BaseScraper):
    provider_name = "Tesco Mobile"
    provider_slug = "tesco-mobile"
    provider_type = "mvno"
    base_url = "https://www.tescomobile.com/sim-only"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            # Try Tesco Mobile API endpoints
            for api_url in [
                "https://www.tescomobile.com/api/plans/sim-only",
                "https://www.tescomobile.com/api/v1/tariffs",
            ]:
                try:
                    api_resp = await self.session.get(
                        api_url, headers={"Accept": "application/json"},
                    )
                    if api_resp.status_code == 200:
                        try:
                            plans = self._walk_json(api_resp.json())
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
                if len(html) > 5000:
                    plans = self._try_parse_json(html)
                    if not plans:
                        plans = self._try_parse_html(html)

            # Playwright fallback
            if not plans:
                logger.info("Tesco Mobile: trying playwright")
                html = await fetch_page_content(self.base_url, wait_ms=10000)
                if html:
                    plans = self._try_parse_json(html)
                    if not plans:
                        plans = self._try_parse_html(html)

            self._deduplicate(plans)
            logger.info(f"Tesco Mobile: scraped {len(plans)} plans")
        except Exception as e:
            logger.error(f"Tesco Mobile scrape error: {e}")
        return plans

    def _try_parse_json(self, html: str) -> List[ScrapedPlan]:
        plans = []
        json_patterns = [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'"plans"\s*:\s*(\[.*?\])\s*[,}]',
            r'"tariffs"\s*:\s*(\[.*?\])\s*[,}]',
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        ]
        for pat in json_patterns:
            for match in re.finditer(pat, html, re.DOTALL):
                try:
                    data = json.loads(match.group(1))
                    extracted = self._walk_json(data)
                    if extracted:
                        return extracted
                except (json.JSONDecodeError, TypeError):
                    continue
        return plans

    def _walk_json(self, data, depth=0) -> List[ScrapedPlan]:
        if depth > 10:
            return []
        plans = []
        if isinstance(data, dict):
            price_keys = {"price", "monthlyPrice", "monthlyCost", "cost"}
            data_keys = {"data", "dataAllowance", "dataGb", "allowance"}
            found_price = None
            found_data = None
            for k in price_keys:
                if k in data:
                    try:
                        found_price = float(data[k])
                    except (ValueError, TypeError):
                        pass
                    break
            for k in data_keys:
                if k in data:
                    found_data = data[k]
                    break
            if found_price and 3 <= found_price <= 100:
                data_gb = None
                is_unlimited = False
                if isinstance(found_data, (int, float)):
                    data_gb = int(found_data)
                elif isinstance(found_data, str):
                    m = re.search(r"(\d+)", found_data)
                    if m:
                        data_gb = int(m.group(1))
                    if "unlimited" in found_data.lower():
                        is_unlimited = True
                name = data.get("name", data.get("title", ""))
                if not name:
                    name = f"Tesco Mobile {data_gb}GB" if data_gb else "Tesco Mobile Unlimited"
                contract = 1
                for ck in ("contractLength", "term", "duration"):
                    if ck in data:
                        try:
                            contract = int(data[ck])
                        except (ValueError, TypeError):
                            pass
                        break
                plans.append(ScrapedPlan(
                    name=name, price=found_price, data_gb=data_gb,
                    data_unlimited=is_unlimited or data.get("unlimitedData", False),
                    url=self.base_url, contract_months=contract,
                    is_5g="5g" in str(data).lower(),
                    external_id=f"tesco-mobile_{found_price}_{data_gb or 'unlimited'}",
                ))
            for v in data.values():
                plans.extend(self._walk_json(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                plans.extend(self._walk_json(item, depth + 1))
        return plans

    def _try_parse_html(self, html: str) -> List[ScrapedPlan]:
        plans = []
        seen = set()
        pound = "\u00a3"
        for price_m in re.finditer(pound + r"\s*(\d+(?:\.\d{1,2})?)", html):
            price = float(price_m.group(1))
            if price < 3 or price > 100:
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
                name=f"Tesco Mobile {label}", price=price, data_gb=data_gb,
                data_unlimited=unlimited and not data_gb, url=self.base_url,
                external_id=f"tesco-mobile_{price}_{data_gb or 'unlimited'}",
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
