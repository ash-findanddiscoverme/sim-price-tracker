import os
import re
import json
import logging
import httpx
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ScrapedPlan:
    name: str
    price: float
    data_gb: Optional[int] = None
    data_unlimited: bool = False
    contract_months: int = 1
    url: str = ""
    is_5g: bool = False
    minutes: str = "unlimited"
    texts: str = "unlimited"
    external_id: Optional[str] = None
    extras: Optional[str] = None
    network: Optional[str] = None


KNOWN_NETWORKS = [
    "EE", "Three", "Vodafone", "O2",
    "giffgaff", "VOXI", "Tesco Mobile", "ASDA Mobile",
    "iD Mobile", "Lyca Mobile", "Talkmobile",
    "Sky Mobile", "BT", "Lebara", "SMARTY", "spusu Mobile",
    "Mozillion",
]

NETWORK_ALIASES = {
    "three mobile": "Three",
    "three": "Three",
    "3": "Three",
    "smarty": "SMARTY",
    "lebara mobile": "Lebara",
    "lebara": "Lebara",
    "asda mobile": "ASDA Mobile",
    "asda": "ASDA Mobile",
    "id mobile": "iD Mobile",
    "id": "iD Mobile",
    "i.d mobile": "iD Mobile",
    "i.d": "iD Mobile",
    "sky mobile": "Sky Mobile",
    "sky": "Sky Mobile",
    "spusu": "spusu Mobile",
    "spusu mobile": "spusu Mobile",
    "voxi": "VOXI",
    "giffgaff": "giffgaff",
    "lyca mobile": "Lyca Mobile",
    "lyca": "Lyca Mobile",
    "talkmobile": "Talkmobile",
    "talk mobile": "Talkmobile",
    "tesco mobile": "Tesco Mobile",
    "tesco": "Tesco Mobile",
    "ee": "EE",
    "vodafone": "Vodafone",
    "o2": "O2",
    "bt": "BT",
    "bt mobile": "BT",
    "mozillion": "Mozillion",
}


def normalize_network(name):
    """Normalize network name to canonical form."""
    if not name:
        return name
    canonical = NETWORK_ALIASES.get(name.lower().strip())
    if canonical:
        return canonical
    return name


def extract_contract(text):
    patterns = [
        (r"(\d{1,2})\s.?month", lambda m: int(m.group(1))),
        (r"(\d{1,2})\s.?mth", lambda m: int(m.group(1))),
        (r"(\d)\s.?year", lambda m: int(m.group(1)) * 12),
        (r"monthly.rolling", lambda m: 1),
        (r"30.?day", lambda m: 1),
        (r"rolling", lambda m: 1),
    ]
    for pat, fn in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = fn(m)
            if 1 <= val <= 36:
                return val
    return 1


def extract_network(text):
    for net in KNOWN_NETWORKS:
        if re.search(r"\b" + re.escape(net) + r"\b", text, re.IGNORECASE):
            return net
    return None


def extract_5g(text):
    return bool(re.search(r"5G", text))


class UnifiedScraper:
    provider_name = "Unknown"
    provider_slug = "unknown"
    provider_type = "network"
    urls = []
    use_playwright = False

    def __init__(self):
        self._log_cb = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def set_log_callback(self, cb: Callable):
        self._log_cb = cb

    def _log(self, msg: str, level: str = "info"):
        full_msg = f"{self.provider_name}: {msg}"
        if level == "error":
            logger.error(full_msg)
        elif level == "warning":
            logger.warning(full_msg)
        else:
            logger.info(full_msg)
        if self._log_cb:
            try:
                self._log_cb(full_msg, level)
            except Exception:
                pass

    async def _get_html_httpx(self, url):
        try:
            hdrs = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            }
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, verify=False) as client:
                resp = await client.get(url, headers=hdrs)
                self._log(f"httpx {resp.status_code} ({len(resp.text)} chars) from {resp.url}")
                if resp.status_code == 200 and len(resp.text) > 2000:
                    return resp.text
                self._log(f"httpx unusable: status={resp.status_code} size={len(resp.text)}", "warning")
        except Exception as e:
            self._log(f"httpx error: {e}", "error")
        return None

    async def _get_html_playwright(self, url):
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await self._launch_browser(p)
                page = await browser.new_page()
                await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                resp = await page.goto(url, timeout=45000, wait_until="networkidle")
                await page.wait_for_timeout(4000)
                html = await page.content()
                await browser.close()
                self._log(f"Playwright got {len(html)} chars from {url}")
                return html if len(html) > 2000 else None
        except Exception as e:
            self._log(f"Playwright error: {e}", "error")
        return None

    async def _launch_browser(self, playwright):
        """
        Launch browser with fallback chain:
        1. Try system Edge (common on corporate Windows)
        2. Try system Chrome
        3. Fall back to Chromium (requires download)
        """
        launch_args = ['--disable-blink-features=AutomationControlled', '--no-sandbox']

        # Try Microsoft Edge first (installed on most corporate Windows)
        try:
            browser = await playwright.chromium.launch(
                headless=True,
                channel='msedge',
                args=launch_args,
            )
            self._log("Using system Edge browser")
            return browser
        except Exception:
            pass

        # Try Chrome next
        try:
            browser = await playwright.chromium.launch(
                headless=True,
                channel='chrome',
                args=launch_args,
            )
            self._log("Using system Chrome browser")
            return browser
        except Exception:
            pass

        # Fall back to Chromium (requires playwright install chromium)
        try:
            browser = await playwright.chromium.launch(
                headless=True,
                args=launch_args,
            )
            self._log("Using Playwright Chromium")
            return browser
        except Exception as e:
            self._log(f"No browser available: {e}. Try: playwright install chromium OR use system Chrome/Edge", "error")
            raise

    def _looks_like_real_page(self, html):
        if not html or len(html) < 15000:
            return False
        import re as _re
        price_hits = len(_re.findall(r'[\xa3$]\s?\d', html))
        return price_hits >= 2

    async def _fetch_html(self, url):
        self._log(f"Fetching {url}")
        if self.use_playwright:
            self._log("Using Playwright (configured)")
            return await self._get_html_playwright(url)
        html = await self._get_html_httpx(url)
        if not self._looks_like_real_page(html):
            reason = "no response" if not html else f"only {len(html)} chars or no prices found"
            self._log(f"httpx insufficient ({reason}), trying Playwright", "warning")
            html = await self._get_html_playwright(url)
        return html

    def _extract_json_ld(self, html):
        results = []
        pat = r'<script[^>]*type=.application.ld.json.[^>]*>(.*?)</script>'
        for m in re.finditer(pat, html, re.DOTALL | re.IGNORECASE):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except Exception as e:
                self._log(f"JSON-LD parse error: {e}", "warning")
        return results

    def _extract_next_data(self, html):
        pat = r'<script[^>]*id=.__NEXT_DATA__.[^>]*>(.*?)</script>'
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception as e:
                self._log(f"__NEXT_DATA__ parse error: {e}", "warning")
        return None

    def _extract_inline_json(self, html):
        results = []
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?(?=</script>)',
            r'window\.__DATA__\s*=\s*(\{.*?\});?(?=</script>)',
        ]
        for pat in patterns:
            for m in re.finditer(pat, html, re.DOTALL):
                try:
                    results.append(json.loads(m.group(1)))
                except Exception as e:
                    self._log(f"Inline JSON parse error: {e}", "warning")
        return results

    def _walk_json_for_plans(self, obj, url, plans, depth=0):
        if depth > 15:
            return
        if isinstance(obj, dict):
            has_price = False
            price = 0.0
            data_gb = None
            name = None
            is_unlimited = False
            is_5g = False
            contract_months = 1
            network_name = None

            all_text = " ".join(str(v) for v in obj.values() if isinstance(v, str))

            for k, v in obj.items():
                kl = k.lower() if isinstance(k, str) else ""
                if kl in ("price", "monthlyprice", "monthly_price", "monthlycost", "cost", "amount", "recurringprice", "monthly_cost"):
                    try:
                        if isinstance(v, (int, float)):
                            price, has_price = float(v), True
                        elif isinstance(v, str):
                            pm = re.search(r"[\d,]+(\.\d+)?", v.replace(",", ""))
                            if pm:
                                price, has_price = float(pm.group()), True
                    except Exception:
                        pass
                if kl in ("data", "datagb", "data_gb", "dataallowance", "allowance", "data_allowance"):
                    if isinstance(v, (int, float)):
                        data_gb = int(v)
                    elif isinstance(v, str):
                        if "unlimited" in v.lower():
                            is_unlimited = True
                        else:
                            dm = re.search(r"(\d+)", v)
                            if dm:
                                data_gb = int(dm.group(1))
                if kl in ("contractlength", "contract_length", "contractmonths", "term", "duration", "contract", "contractperiod"):
                    if isinstance(v, (int, float)) and 1 <= v <= 36:
                        contract_months = int(v)
                    elif isinstance(v, str):
                        contract_months = extract_contract(v)
                if kl in ("network", "networkname", "network_name", "carrier", "operator", "provider"):
                    if isinstance(v, str) and len(v) < 40:
                        network_name = v
                if kl in ("name", "title", "planname", "productname"):
                    if isinstance(v, str) and len(v) < 80:
                        name = v
                if isinstance(v, str) and "unlimited" in v.lower():
                    is_unlimited = True
                if (isinstance(v, str) and "5g" in v.lower()) or kl in ("is5g", "is_5g"):
                    is_5g = True

            if not network_name:
                network_name = extract_network(all_text)

            if has_price and 5 <= price <= 100 and (data_gb or is_unlimited):
                plan_name = name or f"{self.provider_name} {data_gb or 'Unlimited'}GB"
                plans.append(ScrapedPlan(
                    name=plan_name, price=price, data_gb=data_gb,
                    data_unlimited=is_unlimited, is_5g=is_5g, url=url,
                    contract_months=contract_months, network=network_name,
                ))
                return

            for v in obj.values():
                self._walk_json_for_plans(v, url, plans, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_json_for_plans(item, url, plans, depth + 1)

    def _extract_from_html(self, html, url):
        plans = []
        soup = BeautifulSoup(html, "html.parser")
        sels = [
            "[class*=price]", "[class*=plan]", "[class*=card]",
            "[class*=tariff]", "[class*=offer]", "[class*=deal]",
            ".product", ".item", "article",
        ]
        cards = []
        for s in sels:
            cards.extend(soup.select(s))
        seen = set()
        for card in cards:
            if id(card) in seen:
                continue
            seen.add(id(card))
            text = card.get_text(" ", strip=True)
            if len(text) < 20 or len(text) > 2000:
                continue

            pm = re.search(r"[{char}$]\s?(\d+(?:\.\d+)?)".format(char="\xa3"), text)
            if not pm:
                pm = re.search(r"(\d+(?:\.\d+)?)\s*(?:/mo|pm|per month)", text, re.IGNORECASE)
            if not pm:
                continue

            price = float(pm.group(1))
            if price < 5 or price > 100:
                continue

            is_unlimited = "unlimited" in text.lower()
            data_gb = None
            if not is_unlimited:
                dm = re.search(r"(\d+)(?:\.\d+)?\s*?GB", text, re.IGNORECASE)
                if dm:
                    data_gb = int(dm.group(1))
            if not data_gb and not is_unlimited:
                continue

            is_5g = extract_5g(text)
            contract_months = extract_contract(text)
            network = extract_network(text)
            data_label = "Unlimited" if is_unlimited else f"{data_gb}GB"
            name = f"{self.provider_name} {data_label}"

            plans.append(ScrapedPlan(
                name=name, price=price, data_gb=data_gb,
                data_unlimited=is_unlimited, is_5g=is_5g, url=url,
                contract_months=contract_months, network=network,
            ))
        return plans

    def _extract_from_regex(self, html, url):
        plans = []
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ")

        pat = r"(\d{1,3})\s*GB.{0,50}?[\xa3$]\s?(\d+(?:\.\d+)?)|[\xa3$]\s?(\d+(?:\.\d+)?).{0,50}?(\d{1,4})\s*GB"
        combo = [(m, m.start()) for m in re.finditer(pat, text, re.IGNORECASE)]

        seen = set()
        for m, pos in combo:
            groups = m.groups()
            if groups[0] and groups[1]:
                data_gb, price = int(groups[0]), float(groups[1])
            elif groups[2] and groups[3]:
                price, data_gb = float(groups[2]), int(groups[3])
            else:
                continue

            if price < 5 or price > 100 or data_gb < 1 or data_gb > 999:
                continue
            key = (data_gb, price)
            if key in seen:
                continue
            seen.add(key)

            window = text[max(0, pos - 200):min(len(text), pos + 200)]
            is_5g = extract_5g(window)
            contract = extract_contract(window)
            network = extract_network(window)

            plans.append(ScrapedPlan(
                name=f"{self.provider_name} {data_gb}GB",
                price=price, data_gb=data_gb, url=url,
                is_5g=is_5g, contract_months=contract, network=network,
            ))

        unlpat = r'unlimited.{0,50}?[\xa3$]\s?(\d+(?:\.\d+)?)|[\xa3$]\s?(\d+(?:\.\d+)?).{0,50}?unlimited'
        for m in re.finditer(unlpat, text, re.IGNORECASE):
            pv = m.group(1) or m.group(2)
            if not pv:
                continue
            price = float(pv)
            if 5 <= price <= 100 and (999, price) not in seen:
                seen.add((999, price))
                window = text[max(0, m.start() - 200):min(len(text), m.end() + 200)]
                plans.append(ScrapedPlan(
                    name=f"{self.provider_name} Unlimited",
                    price=price, data_unlimited=True, url=url,
                    is_5g=extract_5g(window),
                    contract_months=extract_contract(window),
                    network=extract_network(window),
                ))
        return plans

    def _dedupe(self, plans):
        seen = {}
        unique = []
        for p in plans:
            key = (p.network, p.price, p.data_gb, p.data_unlimited, p.contract_months)
            if key not in seen:
                seen[key] = True
                unique.append(p)
        return unique

    async def scrape(self):
        all_plans = []
        for url in self.urls:
            self._log(f"Fetching {url}")
            html = await self._fetch_html(url)
            if not html:
                self._log(f"Failed to fetch {url}", "error")
                continue

            self._log(f"Got {len(html)} chars from {url}")
            candidates = {}

            json_ld_plans = []
            for data in self._extract_json_ld(html):
                self._walk_json_for_plans(data, url, json_ld_plans)
            if json_ld_plans:
                candidates['JSON-LD'] = json_ld_plans

            next_data_plans = []
            next_data = self._extract_next_data(html)
            if next_data:
                self._walk_json_for_plans(next_data, url, next_data_plans)
                if next_data_plans:
                    candidates['__NEXT_DATA__'] = next_data_plans

            inline_plans = []
            for data in self._extract_inline_json(html):
                self._walk_json_for_plans(data, url, inline_plans)
            if inline_plans:
                candidates['inline JSON'] = inline_plans

            html_plans = self._extract_from_html(html, url)
            if html_plans:
                candidates['HTML parsing'] = html_plans

            regex_plans = self._extract_from_regex(html, url)
            if regex_plans:
                candidates['regex'] = regex_plans

            if candidates:
                for strategy, plans in candidates.items():
                    self._log(f"{strategy} found {len(plans)} plans")
                best_strategy = max(candidates, key=lambda k: len(candidates[k]))
                best_plans = candidates[best_strategy]
                self._log(f"Using {best_strategy} ({len(best_plans)} plans)", "success")
                all_plans.extend(best_plans)
            else:
                self._log(f"No plans found on {url}", "warning")

        result = self._dedupe(all_plans)

        # For direct provider scrapers, pin network to provider name
        if self.provider_type in ("network", "mvno"):
            for p in result:
                p.network = self.provider_name

        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result


BaseScraper = UnifiedScraper
