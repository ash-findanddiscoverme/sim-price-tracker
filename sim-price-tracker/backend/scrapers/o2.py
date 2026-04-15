"""O2 scraper - uses DFE cookie to access the new React site,
then iterates contract length filters via React-compatible select changes."""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan

logger = logging.getLogger(__name__)


class O2Scraper(UnifiedScraper):
    provider_name = "O2"
    provider_slug = "o2"
    provider_type = "network"
    urls = ['https://www.o2.co.uk/shop/sim-cards/sim-only-deals']
    use_playwright = True

    async def _get_html_playwright(self, url):
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

                # Set DFE cookies to access the new React-based O2 site
                await ctx.add_cookies([
                    {'name': 'optimizely_vmo2_upper', 'value': 'dfe', 'domain': '.o2.co.uk', 'path': '/'},
                    {'name': 'optimizely_vmo2checkout', 'value': 'esales', 'domain': '.o2.co.uk', 'path': '/'},
                ])

                page = await ctx.new_page()
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
                await page.goto(self.urls[0], timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(10000)

                # Dismiss cookies
                try:
                    btn = page.locator('#onetrust-accept-btn-handler').first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass
                await page.evaluate("document.querySelectorAll('#onetrust-consent-sdk').forEach(el=>el.remove())")

                # Iterate each contract length
                contract_options = [('24', 24), ('12', 12), ('1', 1)]

                for contract_val, contract_months in contract_options:
                    self._log(f"Selecting contract: {contract_months}mo")

                    # Use React-compatible select change
                    await page.evaluate("""(val) => {
                        const sel = document.querySelector('select[name="contract-length"]');
                        if (sel) {
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
                            setter.call(sel, val);
                            sel.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""", contract_val)
                    await page.wait_for_timeout(4000)

                    # Also sort by price to get structured listing
                    await page.evaluate("""() => {
                        const sel = document.querySelector('select[name="sortby"]');
                        if (sel) {
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
                            setter.call(sel, '+monthlyPrice');
                            sel.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""")
                    await page.wait_for_timeout(3000)

                    # Click "Show next" to load all plans for this contract
                    for _ in range(10):
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await page.wait_for_timeout(800)
                        try:
                            sn = page.locator('text=/Show next/i').first
                            if await sn.is_visible(timeout=500):
                                text = await sn.text_content()
                                if '0 result' in text:
                                    break
                                await sn.click(force=True)
                                self._log(f"  Show next: {text.strip()}")
                                await page.wait_for_timeout(3000)
                            else:
                                break
                        except Exception:
                            break

                    # Parse plans from current page state
                    html = await page.content()
                    new_plans = self._parse_plans(html, contract_months)
                    self._log(f"  Found {len(new_plans)} plans for {contract_months}mo")
                    plans.extend(new_plans)

                await browser.close()
        except Exception as e:
            self._log(f'Scrape error: {e}', 'error')

        result = self._dedupe(plans)
        for plan in result:
            plan.network = 'O2'
        self._log(f'Total: {len(result)} unique plans', 'success' if result else 'warning')
        return result

    def _parse_plans(self, html, default_contract):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        for card in soup.select('[class*="plan"], [class*="card"], [class*="tariff"]'):
            text = card.get_text(' ', strip=True)
            if len(text) < 50 or len(text) > 500 or 'MONTHLY' not in text:
                continue

            pm = re.search(r'£(\d+\.\d+)\s+MONTHLY', text)
            if not pm:
                continue
            price = float(pm.group(1))
            if price < 5 or price > 80:
                continue

            dm = re.search(r'(\d+)\s*GB', text, re.I)
            data_gb = int(dm.group(1)) if dm else None
            is_unlimited = 'unlimited' in text[:80].lower() and not data_gb
            if not data_gb and not is_unlimited:
                continue

            contract = default_contract
            cm = re.search(r'(\d+)\s+month\s+contract', text, re.I)
            if cm:
                contract = int(cm.group(1))

            tier = ''
            tm = re.search(r'(MINI|CLASSIC|ALL ROUNDER)\s*PLAN', text, re.I)
            if tm:
                tier = tm.group(1).title()

            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            key = (price, data_gb, is_unlimited, contract, tier)
            if key in seen:
                continue
            seen.add(key)

            extras = []
            if 'priority' in text.lower():
                extras.append('Priority')
            if 'eu roaming' in text.lower() or 'roam' in text.lower():
                extras.append('EU Roaming')
            if 'switch up' in text.lower():
                extras.append('O2 Switch Up')

            plans.append(ScrapedPlan(
                name=f'O2 {tier} {data_label}'.strip(),
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=True,
                url=self.urls[0],
                contract_months=contract,
                network='O2',
                extras=', '.join(extras) if extras else None,
            ))

        return plans
