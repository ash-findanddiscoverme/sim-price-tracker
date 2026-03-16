import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class LycaMobileScraper(BaseScraper):
    provider_name = "Lyca Mobile"
    provider_slug = "lyca-mobile"
    provider_type = "mvno"
    base_url = "https://www.lycamobile.co.uk/en/bundle/"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            # Try Lyca Mobile API endpoints
            for api_url in [
                "https://www.lycamobile.co.uk/api/bundles",
                "https://www.lycamobile.co.uk/wp-json/lyca/v1/bundles",
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
                logger.info("Lyca Mobile: trying playwright")
                html = await fetch_page_content(
                    self.base_url, wait_ms=10000,
                    selector='[class*="bundle"], [class*="plan"], [class*="price"]',
                )
                if html:
                    plans = self._try_parse_json(html)
                    if not plans:
                        plans = self._parse_html(html)

            self._deduplicate(plans)
            logger.info(f"Lyca Mobile: scraped {len(plans)} plans")
        except Exception as e:
            logger.error(f"Lyca Mobile scrape error: {e}")
        return plans

    def _try_parse_json(self, html: str) -> List[ScrapedPlan]:
        plans = []
        patterns = [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            r'"bundles"\s*:\s*(\[.*?\])\s*[,}]',
        ]
        for pat in patterns:
            for match in re.finditer(pat, html, re.DOTALL):
                raw = match.group(1).strip()
                if len(raw) < 30:
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
            price_val = data.get("price", data.get("monthlyPrice",
                        data.get("cost", data.get("amount"))))
            if price_val is not None:
                try:
                    price = float(price_val)
                    if 1 <= price <= 100:
                        dv = data.get("data", data.get("dataAllowance",
                             data.get("dataGb", data.get("dataVolume"))))
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
                        name = data.get("name", data.get("title",
                               data.get("bundleName", "")))
                        if not name:
                            name = f"Lyca Mobile {data_gb}GB" if data_gb else "Lyca Mobile Bundle"
                        # Parse minutes (Lyca has international call bundles)
                        mins = data.get("minutes", data.get("voice", "unlimited"))
                        if isinstance(mins, (int, float)):
                            mins = str(int(mins)) + " mins"
                        txts = data.get("texts", data.get("sms", "unlimited"))
                        if isinstance(txts, (int, float)):
                            txts = str(int(txts)) + " texts"
                        plans.append(ScrapedPlan(
                            name=name, price=price, data_gb=data_gb,
                            data_unlimited=is_unlimited, url=self.base_url,
                            contract_months=1,
                            minutes=str(mins) if mins else "unlimited",
                            texts=str(txts) if txts else "unlimited",
                            external_id=f"lyca-mobile_{price}_{data_gb or 'unlimited'}",
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
            start = max(0, price_m.start() - 800)
            end = min(len(html), price_m.end() + 800)
            ctx = html[start:end]
            gb_m = re.search(r"(\d+)\s*GB", ctx, re.IGNORECASE)
            data_gb = int(gb_m.group(1)) if gb_m else None
            unlimited = bool(re.search(r"unlimited\s*data", ctx, re.IGNORECASE))
            key = (price, data_gb)
            if key in seen:
                continue
            seen.add(key)
            if not data_gb and not unlimited:
                continue
            label = f"{data_gb}GB" if data_gb else "Unlimited"
            # Extract minutes from nearby context
            mins_m = re.search(r"(\d+)\s*min", ctx, re.IGNORECASE)
            mins = mins_m.group(1) + " mins" if mins_m else "unlimited"
            int_m = re.search(r"(\d+)\s*international", ctx, re.IGNORECASE)
            if int_m:
                mins = mins + f" + {int_m.group(1)} intl mins"
            plans.append(ScrapedPlan(
                name=f"Lyca Mobile {label}", price=price, data_gb=data_gb,
                data_unlimited=unlimited and not data_gb, url=self.base_url,
                minutes=mins,
                external_id=f"lyca-mobile_{price}_{data_gb or 'unlimited'}",
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
