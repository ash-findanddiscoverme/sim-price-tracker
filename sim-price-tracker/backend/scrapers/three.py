"""Three scraper - clicks through the Build Your Own Plan configurator."""

import re
import logging
from .unified_base import UnifiedScraper, ScrapedPlan

logger = logging.getLogger(__name__)


class ThreeScraper(UnifiedScraper):
    provider_name = "Three"
    provider_slug = "three"
    provider_type = "network"
    urls = ['https://www.three.co.uk/store/sim/sim-only']
    use_playwright = True

    async def _get_html_playwright(self, url):
        # Not used directly - scrape() handles everything via Playwright
        return None

    async def scrape(self):
        plans = []
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await self._launch_browser(p)
                ctx = await browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}, locale='en-GB',
                )
                page = await ctx.new_page()
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
                await page.goto(self.urls[0], timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(8000)

                # Dismiss cookies
                try:
                    btn = page.locator('#onetrust-accept-btn-handler').first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass
                try:
                    await page.evaluate("document.querySelectorAll('#onetrust-consent-sdk').forEach(el=>el.remove())")
                except Exception:
                    pass

                # Scroll to the configurator
                for _ in range(10):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(500)

                contracts = [('24 Months', 24), ('12 Months', 12), ('1 Month', 1)]
                data_amounts = [
                    ('Unlimited', None, True),
                    ('250GB', 250, False),
                    ('150GB', 150, False),
                    ('120GB', 120, False),
                    ('40GB', 40, False),
                    ('25GB', 25, False),
                    ('4GB', 4, False),
                ]
                plan_types = ['Lite', 'Value', 'Complete']
                seen = set()

                for contract_text, contract_months in contracts:
                    try:
                        btn = page.locator(f'button:has-text("{contract_text}")').first
                        await btn.click(force=True)
                        await page.wait_for_timeout(500)
                    except Exception:
                        continue

                    for data_label, data_gb, is_unlimited in data_amounts:
                        try:
                            btn = page.locator(f'button:has-text("{data_label}")').first
                            await btn.click(force=True)
                            await page.wait_for_timeout(500)
                        except Exception:
                            continue

                        for plan_type in plan_types:
                            try:
                                btn = page.locator(f'button:has-text("{plan_type}")').first
                                await btn.click(force=True)
                                await page.wait_for_timeout(700)
                            except Exception:
                                continue

                            # Read price from the configurator's output
                            visible = await page.evaluate("document.body.innerText")
                            price = self._extract_config_price(visible, data_label)

                            if price and 5 <= price <= 80:
                                key = (price, data_gb, is_unlimited, contract_months, plan_type)
                                if key not in seen:
                                    seen.add(key)
                                    name = f'Three {plan_type} {data_label}'
                                    extras = []
                                    if '5G' in visible:
                                        extras.append('5G')
                                    if 'Three+ Rewards' in visible:
                                        extras.append('Three+ Rewards')

                                    # Check for price rise info
                                    rise = re.search(
                                        r'increasing to:\s*£(\d+\.\d+)',
                                        visible
                                    )
                                    if rise:
                                        extras.append(f'Rises to £{rise.group(1)}')

                                    plans.append(ScrapedPlan(
                                        name=name,
                                        price=price,
                                        data_gb=data_gb,
                                        data_unlimited=is_unlimited,
                                        is_5g=True,
                                        url=self.urls[0],
                                        contract_months=contract_months,
                                        network='Three',
                                        extras=', '.join(extras) if extras else None,
                                    ))

                self._log(f"Extracted {len(plans)} plans from configurator")
                await browser.close()
        except Exception as e:
            self._log(f'Scrape error: {e}', 'error')

        result = self._dedupe(plans)
        self._log(f'Total: {len(result)} unique plans', 'success' if result else 'warning')
        return result

    def _extract_config_price(self, visible_text, data_label):
        """Extract the price shown for the current configurator selection."""
        # The price appears as "£XX.00 [1] a month" in the data description section
        # Look for pattern near the data amount description
        escaped = re.escape(data_label).replace(r'\ ', r'\s+')
        pattern = rf'{escaped}\s+data.*?£(\d+\.\d+)\s*(?:\[\d+\])?\s*a\s*month'
        m = re.search(pattern, visible_text, re.I | re.DOTALL)
        if m:
            return float(m.group(1))

        # Fallback: look for any "£XX.00 a month" near "data"
        for m in re.finditer(r'£(\d+\.\d+)\s*(?:\[\d+\])?\s*a\s*month', visible_text):
            price = float(m.group(1))
            if 5 <= price <= 80:
                return price

        return None
