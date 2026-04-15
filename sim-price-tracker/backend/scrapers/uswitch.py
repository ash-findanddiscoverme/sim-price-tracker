"""uSwitch scraper with article-based plan extraction and network attribution."""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, extract_contract, extract_network, KNOWN_NETWORKS

logger = logging.getLogger(__name__)


class USwitchScraper(UnifiedScraper):
    provider_name = "uSwitch"
    provider_slug = "uswitch"
    provider_type = "affiliate"
    urls = ['https://www.uswitch.com/mobiles/compare/sim_only_deals/']
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

                # Click "Show more deals" / "Load more" buttons
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

        # uSwitch uses article elements or deal cards
        cards = soup.select('article, [class*="deal-card"], [class*="result-card"]')
        self._log(f"Found {len(cards)} deal cards/articles")

        for card in cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 30 or len(text) > 3000:
                continue

            # Must mention SIM or a known network
            text_lower = text.lower()
            if 'sim' not in text_lower and not any(n.lower() in text_lower for n in KNOWN_NETWORKS):
                continue

            # Extract network from the card text (e.g. "Vodafone SIM Deal")
            network = None
            for net in KNOWN_NETWORKS:
                if re.search(r'\b' + re.escape(net) + r'\b', text, re.IGNORECASE):
                    network = net
                    break
            if not network:
                network_match = re.search(
                    r"([\w\s]+?)(?:'s\s+Network|SIM\s+Deal|SIM\s+Only)", text
                )
                if network_match:
                    candidate = network_match.group(1).strip()
                    if 3 <= len(candidate) <= 30:
                        network = candidate

            # Extract price -- look for "£X.XX a month" pattern first
            price = None
            pm = re.search(r'£\s?(\d+(?:\.\d+)?)\s*(?:a month|/mo|per month|monthly)', text, re.IGNORECASE)
            if pm:
                price = float(pm.group(1))
            else:
                # Fallback: first £ amount that looks like a monthly price
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
            is_unlimited = 'unlimited' in text_lower
            if not is_unlimited:
                dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
                if dm:
                    data_gb = int(dm.group(1))
            if not data_gb and not is_unlimited:
                continue

            # Extract contract length
            contract_months = 1
            cm = re.search(r'(\d+)\s*month', text, re.IGNORECASE)
            if cm:
                val = int(cm.group(1))
                if 1 <= val <= 36:
                    contract_months = val
            if 'no contract' in text_lower or 'rolling' in text_lower:
                contract_months = 1

            is_5g = '5g' in text_lower
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            name = f'{network or "Unknown"} {data_label}'

            # Dedup key
            key = (network, price, data_gb, is_unlimited, contract_months)
            if key in seen:
                continue
            seen.add(key)

            # Extract extras/perks
            extras = []
            if 'roam' in text_lower:
                rm = re.search(r'roam[^.]*', text, re.IGNORECASE)
                if rm:
                    extras.append(rm.group(0).strip()[:60])
            if 'price rise' in text_lower or 'no annual' in text_lower:
                extras.append('No price rise')
            if 'reward' in text_lower:
                extras.append('Rewards')
            if 'exclusive' in text_lower:
                extras.append('Exclusive')

            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract_months,
                network=network,
                extras=', '.join(extras) if extras else None,
            ))

        if not plans:
            self._log("Article parsing yielded nothing, falling back to regex", "warning")
            plans = self._extract_from_regex(html, url)

        return plans
