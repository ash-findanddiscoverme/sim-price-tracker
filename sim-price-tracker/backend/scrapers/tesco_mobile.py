"""Tesco Mobile scraper with product card parsing."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


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
                    viewport={'width': 1920, 'height': 1080}, locale='en-GB',
                )
                page = await ctx.new_page()
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
                await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(8000)

                # Dismiss cookies
                for sel in ['#onetrust-accept-btn-handler', 'button:has-text("Accept all")', 'button:has-text("Accept")']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass

                # Remove overlays
                try:
                    await page.evaluate("document.querySelectorAll('#onetrust-consent-sdk').forEach(el=>el.remove())")
                except Exception:
                    pass

                # Scroll and click "Show more" to load all plans
                initial = await page.locator('[class*="product"]').count()
                self._log(f"Initial product count: {initial}")

                for i in range(15):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
                    try:
                        btn = page.locator('button:has-text("Show more")').first
                        if await btn.is_visible(timeout=1000):
                            await btn.scroll_into_view_if_needed()
                            await btn.click(force=True, timeout=5000)
                            self._log(f"Clicked Show more ({i+1})")
                            await page.wait_for_timeout(3000)
                        else:
                            break
                    except Exception:
                        break

                # Final scroll
                for _ in range(5):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)

                final = await page.locator('[class*="product"]').count()
                self._log(f"Final product count: {final}")

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
            plans = self._parse_products(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "Tesco Mobile"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_products(self, html, url):
        """
        Tesco product cards: '[data]GB ... £[price] a month [N]-month contract
        Clubcard Price £[clubcard_price] a month'
        """
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        cards = soup.select('[class*="product"]')
        self._log(f"Found {len(cards)} product elements")

        for card in cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 40 or len(text) > 500 or '£' not in text:
                continue
            if 'GB' not in text and 'Unlimited' not in text:
                continue

            # Data: starts with "NGB"
            dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
            data_gb = int(dm.group(1)) if dm else None
            is_unlimited = 'unlimited data' in text.lower() and not data_gb
            if not data_gb and not is_unlimited:
                continue

            # Price: "£X a month" (first one is regular price)
            pm = re.search(r'£(\d+(?:\.\d+)?)\s*a\s*month', text)
            if not pm:
                continue
            price = float(pm.group(1))
            if price < 3 or price > 50:
                continue

            # Clubcard price (lower price for Clubcard holders)
            clubcard_price = None
            cm = re.search(r'Clubcard\s+Price\s+£(\d+(?:\.\d+)?)', text)
            if cm:
                clubcard_price = float(cm.group(1))

            # Contract
            contract = 1
            ct = re.search(r'(\d+)-month\s+contract', text)
            if ct:
                contract = int(ct.group(1))

            is_5g = '5G' in text
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'

            # Store the Clubcard price as the main price since it's the best available
            best_price = clubcard_price if clubcard_price else price
            key = (best_price, data_gb, is_unlimited, contract)
            if key in seen:
                continue
            seen.add(key)

            extras = []
            if clubcard_price:
                extras.append(f'Clubcard: \u00a3{clubcard_price:.2f}')
                extras.append(f'Non-Clubcard: \u00a3{price:.2f}')

            plans.append(ScrapedPlan(
                name=f'Tesco Mobile {data_label}',
                price=best_price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract,
                network='Tesco Mobile',
                extras=', '.join(extras) if extras else None,
            ))

        return plans
