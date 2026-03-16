import re
import json
import logging
from typing import List
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class VoxiScraper(BaseScraper):
    provider_name = "VOXI"
    provider_slug = "voxi"
    provider_type = "mvno"
    base_url = "https://www.voxi.co.uk/plans"

    KNOWN_PLANS = [
        {"name": "VOXI 15GB", "price": 10.00, "data_gb": 15},
        {"name": "VOXI 45GB", "price": 15.00, "data_gb": 45},
        {"name": "VOXI 100GB", "price": 20.00, "data_gb": 100},
        {"name": "VOXI Unlimited", "price": 25.00, "data_gb": None, "unlimited": True},
    ]

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            # VOXI is JS-rendered (Vodafone youth brand), try API first
            try:
                api_resp = await self.session.get(
                    "https://www.voxi.co.uk/api/plans",
                    headers={"Accept": "application/json"},
                )
                if api_resp.status_code == 200:
                    try:
                        plans = self._extract_plans_from_json(api_resp.json())
                    except (json.JSONDecodeError, TypeError):
                        pass
            except Exception as e:
                logger.debug(f"VOXI API attempt failed: {e}")

            # Try httpx first for any embedded data
            if not plans:
                try:
                    resp = await self.session.get(self.base_url)
                    html = resp.text
                    if len(html) > 2000:
                        plans = self._parse_json_data(html)
                        if not plans:
                            plans = self._parse_html(html)
                except Exception as e:
                    logger.debug(f"VOXI httpx attempt failed: {e}")

            # Playwright for JS-rendered content
            if not plans:
                logger.info("VOXI: trying playwright for JS-rendered content")
                html = await fetch_page_content(
                    self.base_url, wait_ms=10000,
                    selector='[class*="plan"], [class*="price"], [class*="Plan"]',
                )
                if html and len(html) > 2000:
                    plans = self._parse_json_data(html)
                    if not plans:
                        plans = self._parse_html(html)

            # Known plans fallback
            if not plans:
                logger.info("VOXI: live scrape returned no plans, using known plans")
                plans = self._known_plans()

            self._deduplicate(plans)
            logger.info(f"VOXI: scraped {len(plans)} plans")
        except Exception as e:
            logger.error(f"VOXI scrape error: {e}")
            plans = self._known_plans()
        return plans

    def _parse_json_data(self, html: str) -> List[ScrapedPlan]:
        plans = []
        for pattern in [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
            r'window\.__data\s*=\s*(\{.*?\});',
            r'window\.__NUXT__\s*=\s*(\{.*?\});',
            r'<script[^>]*type="application/json"[^>]*data-drupal-selector="[^"]*"[^>]*>(.*?)</script>',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
                plans = self._extract_plans_from_json(data)
                if plans:
                    return plans
            except (json.JSONDecodeError, TypeError):
                continue
        return plans

    def _extract_plans_from_json(self, data, depth=0) -> List[ScrapedPlan]:
        if depth > 8:
            return []
        plans = []
        if isinstance(data, dict):
            has_price = "price" in data or "monthlyPrice" in data or "cost" in data
            has_ident = "data" in data or "name" in data or "dataAllowance" in data
            if has_price and has_ident:
                try:
                    price = float(data.get("price", data.get("monthlyPrice", data.get("cost", 0))))
                    if 3 < price < 100:
                        name = data.get("name", data.get("title", ""))
                        data_gb = data.get("data", data.get("dataAllowance", data.get("dataGb")))
                        if isinstance(data_gb, str):
                            m = re.search(r"(\d+)", data_gb)
                            data_gb = int(m.group(1)) if m else None
                        elif isinstance(data_gb, (int, float)):
                            data_gb = int(data_gb)
                        is_unlimited = (
                            data.get("unlimited", False)
                            or data.get("unlimitedData", False)
                            or "unlimited" in str(name).lower()
                        )
                        label = f"VOXI {data_gb}GB" if data_gb else "VOXI Plan"
                        plans.append(ScrapedPlan(
                            name=name or label, price=price,
                            data_gb=int(data_gb) if data_gb else None,
                            data_unlimited=is_unlimited, url=self.base_url,
                            is_5g=data.get("is5g", data.get("fiveG", False)),
                            external_id=f"voxi_{price}_{data_gb or 'unlimited'}",
                        ))
                except (ValueError, TypeError):
                    pass
            for v in data.values():
                plans.extend(self._extract_plans_from_json(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                plans.extend(self._extract_plans_from_json(item, depth + 1))
        return plans

    def _parse_html(self, html: str) -> List[ScrapedPlan]:
        plans = []
        seen = set()

        # Try matching data+price pairs in proximity
        price_data_pairs = re.findall(
            r"(\d+)\s*GB.*?\u00a3\s*(\d+(?:\.\d{1,2})?)|"
            r"\u00a3\s*(\d+(?:\.\d{1,2})?).*?(\d+)\s*GB",
            html, re.IGNORECASE | re.DOTALL,
        )
        for m in price_data_pairs:
            if m[0] and m[1]:
                data_gb, price = int(m[0]), float(m[1])
            elif m[2] and m[3]:
                price, data_gb = float(m[2]), int(m[3])
            else:
                continue
            if price < 3 or price > 100 or data_gb > 500:
                continue
            key = (price, data_gb)
            if key in seen:
                continue
            seen.add(key)
            plans.append(ScrapedPlan(
                name=f"VOXI {data_gb}GB", price=price, data_gb=data_gb,
                url=self.base_url,
                external_id=f"voxi_{price}_{data_gb}",
            ))

        # Check for unlimited plan
        unlimited_match = re.search(
            r"unlimited\s*data.*?\u00a3\s*(\d+(?:\.\d{1,2})?)", html, re.IGNORECASE
        )
        if not unlimited_match:
            unlimited_match = re.search(
                r"\u00a3\s*(\d+(?:\.\d{1,2})?).*?unlimited\s*data", html, re.IGNORECASE
            )
        if unlimited_match:
            price = float(unlimited_match.group(1))
            if 3 < price < 100 and (price, "unlimited") not in seen:
                plans.append(ScrapedPlan(
                    name="VOXI Unlimited", price=price, data_unlimited=True,
                    url=self.base_url,
                    external_id=f"voxi_{price}_unlimited",
                ))
        return plans

    def _known_plans(self) -> List[ScrapedPlan]:
        return [
            ScrapedPlan(
                name=p["name"], price=p["price"],
                data_gb=p.get("data_gb"),
                data_unlimited=p.get("unlimited", False),
                url=self.base_url,
                external_id=f"voxi_{p['price']}_{p.get('data_gb') or 'unlimited'}",
            )
            for p in self.KNOWN_PLANS
        ]

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
