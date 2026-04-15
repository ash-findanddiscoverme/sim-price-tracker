"""Tesco Mobile scraper.

Tesco Mobile's SIM page uses heavy client-side rendering and times out
on 'networkidle'. Uses 'domcontentloaded' with a stealth browser context
and extra wait time for JS to render plan cards.

Plan cards use 'product-item simo' or 'ais-InfiniteHits-item' classes,
with pricing like '£15 a month' and data like '60GB'.
"""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, extract_contract, extract_5g

logger = logging.getLogger(__name__)


class TescoMobileScraper(UnifiedScraper):
    provider_name = "Tesco Mobile"
    provider_slug = "tesco-mobile"
    provider_type = "mvno"
    urls = ['https://www.tescomobile.com/shop/sim-only']
    use_playwright = True

    async def _get_html_playwright(self, url):
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await self._launch_browser(p)
                ctx = await browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-GB',
                )
                page = await ctx.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
                )

                await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                await page.wait_for_timeout(8000)

                # Dismiss cookie consent
                for sel in [
                    '#onetrust-accept-btn-handler',
                    'button:has-text("Accept")',
                    'button:has-text("Accept all")',
                    '[class*="accept"]',
                ]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        pass

                # Scroll to trigger lazy loading
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(1000)

                html = await page.content()
                await browser.close()
                self._log(f"Playwright got {len(html)} chars from {url}")
                return html if len(html) > 5000 else None
        except Exception as e:
            self._log(f"Playwright error: {e}", "error")
        return None

    def _extract_from_html(self, html, url):
        """Custom extraction for Tesco Mobile's card structure."""
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        # Tesco uses 'product-item simo' or 'ais-InfiniteHits-item' for plan cards
        cards = soup.select('.product-item, .ais-InfiniteHits-item, [class*="product-item"]')
        self._log(f"Found {len(cards)} product cards")

        for card in cards:
            text = card.get_text(' ', strip=True)
            text = re.sub(r'\s+', ' ', text)
            if len(text) < 30 or len(text) > 1000:
                continue

            # Data amount: "60GB" or "Unlimited"
            data_gb = None
            is_unlimited = bool(re.search(r'unlimited\s+data', text, re.I))
            if not is_unlimited:
                dm = re.search(r'(\d+)\s*GB', text, re.I)
                if dm:
                    data_gb = int(dm.group(1))
            if not data_gb and not is_unlimited:
                continue

            # Price: prefer "Clubcard Price £X a month", else "£X a month"
            price = None
            clubcard = re.search(r'Clubcard\s+Price\s+£(\d+(?:\.\d+)?)', text, re.I)
            if clubcard:
                price = float(clubcard.group(1))
            else:
                pm = re.search(r'£(\d+(?:\.\d+)?)\s*(?:a month|per month|/mo|p/m)', text, re.I)
                if pm:
                    price = float(pm.group(1))

            if not price or price < 3 or price > 60:
                continue

            # Contract length
            contract_months = extract_contract(text)

            is_5g = extract_5g(text)
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            name = f'Tesco Mobile {data_label}'

            key = (price, data_gb, is_unlimited, contract_months)
            if key in seen:
                continue
            seen.add(key)

            extras = []
            if 'clubcard' in text.lower():
                extras.append('Clubcard Price')
            if 'no eu roaming' in text.lower() or 'eu roaming' in text.lower():
                extras.append('EU Roaming')
            if 'frozen' in text.lower():
                extras.append('Price frozen')

            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract_months,
                network='Tesco Mobile',
                extras=', '.join(extras) if extras else None,
            ))

        return plans
