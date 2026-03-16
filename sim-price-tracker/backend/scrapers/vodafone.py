import re
import json
import logging
from typing import Optional, List
from bs4 import BeautifulSoup
from .base import BaseScraper, ScrapedPlan
from .playwright_helper import fetch_page_content

logger = logging.getLogger(__name__)


class VodafoneScraper(BaseScraper):
    provider_name = "Vodafone"
    provider_slug = "vodafone"
    provider_type = "network"
    base_url = "https://www.vodafone.co.uk/mobile/best-sim-only-deals"

    async def scrape(self) -> List[ScrapedPlan]:
        plans: List[ScrapedPlan] = []
        try:
            html = await fetch_page_content(self.base_url, wait_ms=10000)
            if not html:
                logger.warning("Vodafone: No HTML content received")
                return plans

            plans = self._try_parse_next_data(html)
            if not plans:
                plans = self._try_parse_json_ld(html)
            if not plans:
                plans = self._try_parse_inline_json(html)
            if not plans:
                plans = self._try_parse_html_cards(html)
            if not plans:
                plans = self._try_parse_regex_fallback(html)

            self._deduplicate(plans)
            logger.info(f"Vodafone: Found {len(plans)} plans")
        except Exception as e:
            logger.error(f"Vodafone scrape error: {e}")
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
                or page_props.get("tariffs")
                or page_props.get("simOnlyPlans")
                or page_props.get("deals")
                or page_props.get("offers")
                or []
            )
            if not plan_list and isinstance(page_props, dict):
                for v in page_props.values():
                    if isinstance(v, list) and len(v) > 2:
                        if isinstance(v[0], dict) and any(
                            k in v[0] for k in ("price", "monthlyPrice", "cost", "monthlyCost")
                        ):
                            plan_list = v
                            break
            for p in plan_list:
                plan = self._extract_plan_from_json(p)
                if plan:
                    plans.append(plan)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Vodafone __NEXT_DATA__ parse failed: {e}")
        return plans

    def _try_parse_json_ld(self, html: str) -> List[ScrapedPlan]:
        plans = []
        for match in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        ):
            try:
                data = json.loads(match.group(1))
                offers = self._extract_offers_from_jsonld(data)
                for offer in offers:
                    price = float(offer.get("price", 0))
                    if price <= 0 or price > 200:
                        continue
                    name = offer.get("name", "")
                    data_gb, is_unlimited = self._parse_data_from_name(name)
                    plans.append(ScrapedPlan(
                        name=name or f"Vodafone {data_gb}GB" if data_gb else "Vodafone Plan",
                        price=price,
                        data_gb=data_gb,
                        data_unlimited=is_unlimited,
                        contract_months=self._guess_contract(name),
                        url=self.base_url,
                        is_5g=bool(re.search(r"5G", name, re.IGNORECASE)),
                        external_id=f"vodafone_ld_{price}_{data_gb or 'unlimited'}",
                    ))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return plans

    def _try_parse_inline_json(self, html: str) -> List[ScrapedPlan]:
        plans = []
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*</script>',
            r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});\s*</script>',
            r'"digitalData"\s*=\s*(\{.*?\});\s*</script>',
            r'"simOnly(?:Plans|Deals)"\s*:\s*(\[\{.*?\}\])',
            r'"plans"\s*:\s*(\[\{.*?\}\])',
            r'"tariffs"\s*:\s*(\[\{.*?\}\])',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, html, re.DOTALL):
                try:
                    raw = match.group(1)
                    data = json.loads(raw)
                    items = data if isinstance(data, list) else []
                    if isinstance(data, dict):
                        for v in data.values():
                            if isinstance(v, list) and len(v) > 1 and isinstance(v[0], dict):
                                items = v
                                break
                    for p in items:
                        plan = self._extract_plan_from_json(p)
                        if plan:
                            plans.append(plan)
                    if plans:
                        return plans
                except (json.JSONDecodeError, TypeError):
                    continue
        return plans

    def _try_parse_html_cards(self, html: str) -> List[ScrapedPlan]:
        plans = []
        soup = BeautifulSoup(html, "html.parser")
        selectors = [
            '[class*="plan-card"]', '[class*="PlanCard"]',
            '[class*="tariff-card"]', '[class*="TariffCard"]',
            '[class*="price-plan"]', '[class*="PricePlan"]',
            '[class*="deal-card"]', '[class*="DealCard"]',
            '[data-testid*="plan"]', '[data-testid*="tariff"]',
            '[class*="sim-only"]', '[class*="SimOnly"]',
            'article[class*="card"]',
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break

        for card in cards:
            plan = self._parse_card_element(card)
            if plan:
                plans.append(plan)
        return plans

    def _try_parse_regex_fallback(self, html: str) -> List[ScrapedPlan]:
        plans = []
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")

        prices = re.findall(r"\xa3(\d+(?:\.\d+)?)", text)
        data_amounts = re.findall(r"(\d+)\s*GB", text, re.IGNORECASE)
        has_unlimited = bool(re.search(r"unlimited\s*data", text, re.IGNORECASE))
        has_5g = bool(re.search(r"5G", text))

        seen = set()
        data_list = list(data_amounts)
        for price_str in prices:
            price = float(price_str)
            if price < 5 or price > 80:
                continue
            if price in seen:
                continue
            seen.add(price)

            data_gb = None
            for d in data_list:
                dv = int(d)
                if 1 <= dv <= 500:
                    data_gb = dv
                    data_list.remove(d)
                    break

            is_unlimited = data_gb is None and has_unlimited
            name = f"Vodafone {data_gb}GB" if data_gb else "Vodafone Unlimited" if is_unlimited else "Vodafone Plan"
            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                contract_months=12,
                url=self.base_url,
                is_5g=has_5g,
                external_id=f"vodafone_regex_{price}_{data_gb or 'unlimited'}",
            ))
        return plans

    def _extract_plan_from_json(self, p: dict) -> Optional[ScrapedPlan]:
        try:
            price = float(
                p.get("price", p.get("monthlyPrice", p.get("monthlyCost",
                p.get("cost", p.get("monthly_price", 0)))))
            )
            if price <= 0 or price > 200:
                return None

            data_val = p.get("data", p.get("dataAllowance", p.get("dataGb",
                        p.get("data_allowance_gb"))))
            is_unlimited = p.get("unlimitedData", p.get("unlimited_data",
                           p.get("isUnlimited", False)))
            if isinstance(data_val, str):
                if "unlimited" in data_val.lower():
                    is_unlimited = True
                    data_val = None
                else:
                    gb_match = re.search(r"(\d+)", data_val)
                    data_val = int(gb_match.group(1)) if gb_match else None
            data_gb = int(data_val) if data_val and not is_unlimited else None

            contract = int(p.get("contractLength", p.get("contract_months",
                       p.get("duration", p.get("term", 12)))))
            is_5g = p.get("is5g", p.get("includes5g", "5g" in str(p).lower()))

            name = p.get("name", p.get("title", ""))
            if not name:
                name = f"Vodafone {data_gb}GB" if data_gb else "Vodafone Unlimited" if is_unlimited else "Vodafone Plan"

            return ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                contract_months=contract,
                url=self.base_url,
                is_5g=bool(is_5g),
                external_id=f"vodafone_json_{price}_{data_gb or 'unlimited'}_{contract}m",
            )
        except (ValueError, TypeError, KeyError):
            return None

    def _parse_card_element(self, card) -> Optional[ScrapedPlan]:
        try:
            card_text = card.get_text(separator=" ")
            price_match = re.search(r"[\xa3\u00a3]\s*(\d+(?:\.\d+)?)", card_text)
            if not price_match:
                return None
            price = float(price_match.group(1))
            if price < 1 or price > 200:
                return None

            data_match = re.search(r"(\d+)\s*GB", card_text, re.IGNORECASE)
            unlimited_match = re.search(r"unlimited\s*data", card_text, re.IGNORECASE)
            data_gb = int(data_match.group(1)) if data_match else None
            is_unlimited = bool(unlimited_match) or (data_gb is not None and data_gb >= 9999)
            if is_unlimited and data_gb and data_gb >= 9999:
                data_gb = None
            is_5g = bool(re.search(r"5G", card_text, re.IGNORECASE))

            contract_months = self._guess_contract(card_text)
            if is_unlimited:
                name = "Vodafone Unlimited"
            else:
                name = f"Vodafone {data_gb}GB" if data_gb else "Vodafone Plan"

            return ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                contract_months=contract_months,
                url=self.base_url,
                is_5g=is_5g,
                external_id=f"vodafone_card_{price}_{data_gb or 'unlimited'}_{contract_months}m",
            )
        except Exception:
            return None

    @staticmethod
    def _extract_offers_from_jsonld(data) -> list:
        if isinstance(data, list):
            offers = []
            for item in data:
                offers.extend(VodafoneScraper._extract_offers_from_jsonld(item))
            return offers
        if isinstance(data, dict):
            result = data.get("offers", [])
            if isinstance(result, dict):
                result = result.get("itemListElement", [result])
            catalog = data.get("hasOfferCatalog", {})
            if catalog:
                result.extend(catalog.get("itemListElement", []))
            return result if isinstance(result, list) else [result]
        return []

    @staticmethod
    def _parse_data_from_name(name: str):
        gb_match = re.search(r"(\d+)\s*GB", name, re.IGNORECASE)
        is_unlimited = bool(re.search(r"unlimited", name, re.IGNORECASE))
        data_gb = int(gb_match.group(1)) if gb_match else None
        return data_gb, is_unlimited

    @staticmethod
    def _guess_contract(text: str) -> int:
        match = re.search(r"(\d+)\s*month", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        if re.search(r"30[\s-]*day|rolling|no\s*contract", text, re.IGNORECASE):
            return 1
        return 12

    @staticmethod
    def _deduplicate(plans: List[ScrapedPlan]):
        seen: set = set()
        i = 0
        while i < len(plans):
            key = (plans[i].price, plans[i].data_gb, plans[i].contract_months)
            if key in seen:
                plans.pop(i)
            else:
                seen.add(key)
                i += 1
