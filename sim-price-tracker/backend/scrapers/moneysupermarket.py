"""MoneySupermarket scraper with network attribution.

MoneySupermarket is a comparison/affiliate site, not an MNO or MVNO.
Plans must be attributed to the actual network (EE, Three, Vodafone, etc.)
rather than to MoneySupermarket itself.
"""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, extract_contract, extract_network, extract_5g, KNOWN_NETWORKS

logger = logging.getLogger(__name__)


class MoneySupermarketScraper(UnifiedScraper):
    provider_name = "MoneySupermarket"
    provider_slug = "moneysupermarket"
    provider_type = "affiliate"
    urls = ['https://www.moneysupermarket.com/mobile-phones/sim-only/']
    use_playwright = True

    async def _get_html_playwright(self, url):
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await self._launch_browser(p)
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-GB",
                )
                page = await ctx.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
                )
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)

                # Dismiss cookie consent
                for sel in [
                    'button:has-text("Accept")',
                    'button:has-text("Accept all")',
                    '[id*="accept"]',
                    '[class*="accept"]',
                ]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass

                # Scroll to load more deals
                for _ in range(8):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(800)

                # Click "Show more" / "Load more" buttons
                for _ in range(3):
                    clicked = False
                    for sel in [
                        'button:has-text("Show more")',
                        'button:has-text("Load more")',
                        'a:has-text("Show more")',
                        '[class*="show-more"]',
                        '[class*="load-more"]',
                    ]:
                        try:
                            btn = page.locator(sel).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(2000)
                                clicked = True
                                self._log(f"Clicked '{sel}'")
                                break
                        except Exception:
                            pass
                    if not clicked:
                        break

                html = await page.content()
                await browser.close()
                self._log(f"Playwright (stealth) got {len(html)} chars from {url}")
                return html if len(html) > 10000 else None
        except Exception as e:
            self._log(f"Playwright error: {e}", "error")
        return None

    def _extract_from_html(self, html, url):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        # MoneySupermarket uses deal cards, result items, or table rows
        cards = soup.select(
            'article, [class*="deal"], [class*="result"], '
            '[class*="card"], [class*="tariff"], [class*="plan"], '
            '[class*="product"], [class*="offer"], tr[class*="row"]'
        )
        self._log(f"Found {len(cards)} deal cards")

        for card in cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 30 or len(text) > 3000:
                continue

            # Extract the network — this is critical for affiliate sites
            network = extract_network(text)

            # Also check for network logos/images in alt text or data attributes
            if not network:
                for img in card.select('img'):
                    alt = img.get('alt', '') or img.get('title', '')
                    network = extract_network(alt)
                    if network:
                        break

            # Check data attributes for network info
            if not network:
                for attr in ('data-network', 'data-provider', 'data-brand'):
                    val = card.get(attr, '')
                    if val:
                        network = extract_network(val)
                        if network:
                            break

            # Skip plans where we can't identify the network — affiliate plans
            # without attribution are unreliable
            if not network:
                continue

            # Extract price
            price = None
            pm = re.search(r'£\s?(\d+(?:\.\d+)?)\s*(?:a month|/mo|per month|monthly|p/m|pm)', text, re.IGNORECASE)
            if pm:
                price = float(pm.group(1))
            else:
                all_prices = re.findall(r'£\s?(\d+(?:\.\d+)?)', text)
                for p_str in all_prices:
                    pv = float(p_str)
                    if 3 <= pv <= 100:
                        price = pv
                        break

            if not price or price < 3 or price > 100:
                continue

            # Extract data amount
            data_gb = None
            text_lower = text.lower()
            is_unlimited = 'unlimited' in text_lower
            if not is_unlimited:
                dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
                if dm:
                    data_gb = int(dm.group(1))
            if not data_gb and not is_unlimited:
                continue

            # Contract length
            contract_months = extract_contract(text)

            is_5g = extract_5g(text)
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            name = f'{network} {data_label}'

            key = (network, price, data_gb, is_unlimited, contract_months)
            if key in seen:
                continue
            seen.add(key)

            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract_months,
                network=network,
            ))

        if not plans:
            self._log("Card parsing yielded nothing, trying JSON extraction with network attribution", "warning")
            plans = self._extract_json_plans_with_network(html, url)

        if not plans:
            self._log("Falling back to regex with network attribution", "warning")
            plans = self._extract_from_regex_with_network(html, url)

        return plans

    def _extract_json_plans_with_network(self, html, url):
        """Extract from JSON-LD / __NEXT_DATA__ but enforce network attribution."""
        raw_plans = []

        for data in self._extract_json_ld(html):
            self._walk_json_for_plans(data, url, raw_plans)

        next_data = self._extract_next_data(html)
        if next_data:
            self._walk_json_for_plans(next_data, url, raw_plans)

        for data in self._extract_inline_json(html):
            self._walk_json_for_plans(data, url, raw_plans)

        # Only keep plans that have a valid network attribution
        attributed = []
        for plan in raw_plans:
            if plan.network and plan.network.lower() != 'moneysupermarket':
                # Update plan name to use network instead of provider
                data_label = 'Unlimited' if plan.data_unlimited else f'{plan.data_gb}GB'
                plan.name = f'{plan.network} {data_label}'
                attributed.append(plan)

        self._log(f"JSON extraction: {len(raw_plans)} raw, {len(attributed)} with network attribution")
        return attributed

    def _extract_from_regex_with_network(self, html, url):
        """Regex fallback but only keep plans with identified networks."""
        all_plans = self._extract_from_regex(html, url)
        attributed = [p for p in all_plans if p.network and p.network.lower() != 'moneysupermarket']

        # Update names to use network
        for plan in attributed:
            data_label = 'Unlimited' if plan.data_unlimited else f'{plan.data_gb}GB'
            plan.name = f'{plan.network} {data_label}'

        self._log(f"Regex extraction: {len(all_plans)} raw, {len(attributed)} with network attribution")
        return attributed
