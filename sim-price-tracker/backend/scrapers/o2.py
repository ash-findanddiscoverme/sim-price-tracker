"""O2 scraper with anti-bot evasion and tariff card parsing."""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, extract_contract, extract_network

logger = logging.getLogger(__name__)


class O2Scraper(UnifiedScraper):
    provider_name = "O2"
    provider_slug = "o2"
    provider_type = "network"
    urls = ['https://www.o2.co.uk/shop/sim-cards/sim-only-deals']
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
                await page.wait_for_timeout(6000)

                # Scroll to load all tariff cards
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, 800)")
                    await page.wait_for_timeout(1000)

                # Click any "show more" or tab buttons
                for selector in [
                    'button:has-text("Show more")',
                    'button:has-text("Load more")',
                    '[class*="show-more"]',
                    '[class*="load-more"]',
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                            await page.wait_for_timeout(2000)
                            self._log(f"Clicked '{selector}'")
                    except Exception:
                        pass

                # Click through data filter tabs to reveal all plans
                for tab_text in ['All', 'SIM only']:
                    try:
                        tab = page.locator(f'button:has-text("{tab_text}")').first
                        if await tab.is_visible(timeout=1000):
                            await tab.click()
                            await page.wait_for_timeout(2000)
                    except Exception:
                        pass

                html = await page.content()
                await browser.close()
                self._log(f"Playwright (stealth) got {len(html)} chars from {url}")
                return html if len(html) > 5000 else None
        except Exception as e:
            self._log(f"Playwright error: {e}", "error")
        return None

    def _extract_from_html(self, html, url):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')

        tariff_cards = soup.select('.tariff-card, [class*="tariff-card"]')
        self._log(f"Found {len(tariff_cards)} tariff-card elements")

        for card in tariff_cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 20:
                continue

            price = None
            pm = re.search(r'£\s?(\d+(?:\.\d+)?)\s*(?:monthly|/mo|per month|a month)', text, re.IGNORECASE)
            if not pm:
                pm = re.search(r'£\s?(\d+(?:\.\d+)?)', text)
            if pm:
                price = float(pm.group(1))

            if not price or price < 5 or price > 100:
                continue

            data_gb = None
            dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
            if dm:
                data_gb = int(dm.group(1))
                if data_gb > 500:
                    data_gb = None
            is_unlimited = not data_gb and 'unlimited' in text.lower()
            if not data_gb and not is_unlimited:
                continue

            contract_months = 1
            cm = re.search(r'(\d+)\s*month\s*contract', text, re.IGNORECASE)
            if cm:
                val = int(cm.group(1))
                if 1 <= val <= 36:
                    contract_months = val

            is_5g = '5g' in text.lower()
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'

            # Extract plan tier (Mini Plan, Classic Plan, etc.)
            tier = ''
            tier_match = re.search(r'(MINI|CLASSIC|ALL ROUNDER|UNLIMITED)\s*PLAN', text, re.IGNORECASE)
            if tier_match:
                tier = ' ' + tier_match.group(1).title()

            name = f'O2{tier} {data_label}'

            extras = []
            if 'priority' in text.lower():
                extras.append('Priority')
            if 'eu roaming' in text.lower() or 'roam' in text.lower():
                extras.append('EU Roaming')

            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract_months,
                network='O2',
                extras=', '.join(extras) if extras else None,
            ))

        if not plans:
            self._log("Tariff cards yielded nothing, falling back to regex", "warning")
            plans = self._extract_from_regex(html, url)
            for p in plans:
                p.network = 'O2'

        return plans
