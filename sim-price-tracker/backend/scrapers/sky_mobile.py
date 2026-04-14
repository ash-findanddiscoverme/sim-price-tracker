"""Sky Mobile scraper for SIM-only data plans."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class SkyMobileScraper(UnifiedScraper):
    provider_name = "Sky Mobile"
    provider_slug = "sky-mobile"
    provider_type = "mvno"
    urls = ['https://www.sky.com/shop/mobile/plans']
    use_playwright = True

    async def _get_html_playwright(self, url):
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
                await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(8000)

                # Sky uses an iframe-based cookie consent (sp_message_iframe)
                cookie_selectors = [
                    '#onetrust-accept-btn-handler',
                    'button:has-text("Accept all")',
                    'button:has-text("Accept")',
                ]
                for sel in cookie_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            self._log(f"Dismissed cookie with: {sel}")
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass

                # Try to dismiss the iframe consent dialog
                try:
                    iframe = page.frame_locator('[id*="sp_message_iframe"]')
                    for sel in ['button:has-text("Accept")', 'button:has-text("OK")', 'button:has-text("Agree")']:
                        try:
                            btn = iframe.locator(sel).first
                            await btn.click(timeout=3000)
                            self._log("Dismissed iframe consent")
                            await page.wait_for_timeout(1500)
                            break
                        except Exception:
                            continue
                except Exception:
                    pass

                # Remove any remaining overlays
                try:
                    await page.evaluate("""
                        document.querySelectorAll('[id*="sp_message"], [class*="consent"], [class*="cookie"]').forEach(el => el.remove());
                    """)
                except Exception:
                    pass

                # Click "SIM only" filter/tab if present
                for sel in ['button:has-text("SIM only")', 'a:has-text("SIM only")', '[data-testid*="sim"]']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click(force=True)
                            self._log("Clicked SIM only filter")
                            await page.wait_for_timeout(3000)
                            break
                    except Exception:
                        continue

                # Scroll to load all plans
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)

                html = await page.content()
                await browser.close()
                self._log(f'Playwright got {len(html)} chars')
                return html if len(html) > 5000 else None
        except Exception as e:
            self._log(f'Playwright error: {e}', 'error')
        return None

    async def scrape(self):
        all_plans = []
        for url in self.urls:
            html = await self._fetch_html(url)
            if not html:
                self._log(f"Failed to fetch {url}", "error")
                continue
            self._log(f"Got {len(html)} chars from {url}")
            plans = self._parse_sky_plans(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "Sky Mobile"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_sky_plans(self, html, url):
        """Parse Sky data plan cards from the plans page."""
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        # Sky plans page shows data plans like "5GB for £6 a month", "10GB for £7", "40GB for £10"
        text = soup.get_text(' ')

        # Pattern: "NGB ... £X a month" or "NGB ... £X/month" or "NGB for £X"
        for m in re.finditer(
            r'(\d+)\s*GB\s+(?:of\s+data\s+)?for\s+£(\d+(?:\.\d+)?)\s*(?:a\s+month|per\s+month|/mo)?',
            text, re.I
        ):
            data_gb = int(m.group(1))
            price = float(m.group(2))
            if data_gb < 1 or price < 3 or price > 60:
                continue
            key = (price, data_gb, 12)
            if key in seen:
                continue
            seen.add(key)
            plans.append(ScrapedPlan(
                name=f'Sky Mobile {data_gb}GB',
                price=price,
                data_gb=data_gb,
                url=url,
                contract_months=12,
                network='Sky Mobile',
            ))

        # Also try card-based extraction
        for sel in ['[class*="card"]', '[class*="plan"]', '[class*="product"]', '[class*="tariff"]']:
            cards = soup.select(sel)
            for card in cards:
                ct = card.get_text(' ', strip=True)
                if len(ct) < 20 or len(ct) > 500:
                    continue
                if '£' not in ct or ('GB' not in ct and 'Unlimited' not in ct):
                    continue
                # Must be a SIM/data plan, not a handset
                if any(phone in ct for phone in ['iPhone', 'Samsung', 'Galaxy', 'Pixel', 'MacBook', 'iPad', 'Tab ']):
                    continue

                dm = re.search(r'(\d+)\s*GB', ct)
                data_gb = int(dm.group(1)) if dm else None
                is_unlimited = 'unlimited' in ct.lower() and not data_gb
                if not data_gb and not is_unlimited:
                    continue

                pm = re.search(r'£\s*(\d+(?:\.\d+)?)\s*(?:a\s+month|per\s+month|/mo)', ct, re.I)
                if not pm:
                    pm = re.search(r'from\s+£\s*(\d+(?:\.\d+)?)', ct, re.I)
                if not pm:
                    continue
                price = float(pm.group(1))
                if price < 3 or price > 60:
                    continue

                contract = 12
                cm_match = re.search(r'(\d+)\s*-?\s*month', ct, re.I)
                if cm_match:
                    val = int(cm_match.group(1))
                    if 1 <= val <= 36:
                        contract = val

                data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
                key = (price, data_gb, is_unlimited, contract)
                if key in seen:
                    continue
                seen.add(key)
                plans.append(ScrapedPlan(
                    name=f'Sky Mobile {data_label}',
                    price=price,
                    data_gb=data_gb,
                    data_unlimited=is_unlimited,
                    url=url,
                    contract_months=contract,
                    network='Sky Mobile',
                ))

        self._log(f"Parsed {len(plans)} Sky plans")
        return plans
