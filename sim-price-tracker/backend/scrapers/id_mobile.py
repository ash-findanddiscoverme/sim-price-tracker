"""iD Mobile scraper with deal card parsing."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class iDMobileScraper(UnifiedScraper):
    provider_name = "iD Mobile"
    provider_slug = "id-mobile"
    provider_type = "mvno"
    urls = ['https://www.idmobile.co.uk/sim-only-deals']
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

                for sel in ['#onetrust-accept-btn-handler', 'button:has-text("Accept")']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass

                for _ in range(8):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)

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
            plans = self._parse_deals(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "iD Mobile"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_deals(self, html, url):
        """
        iD Mobile deal cards have this structure:
          "Extra Data 70GB 60GB Data £10 a month 1 Month Select Plan"
          "No annual price rises Unlimited Data £16 £17 a month 24 Months Select Plan"
        
        The first GB value is the headline (with bonus), second is the base.
        We use the headline data amount as that's what the customer gets.
        """
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        # Use article or deal-card selectors
        cards = soup.select('article, [class*="deal"], [class*="card"]')
        priced_cards = []
        for card in cards:
            text = card.get_text(' ', strip=True)
            if '£' in text and ('GB' in text or 'Unlimited' in text) and 20 < len(text) < 400:
                priced_cards.append(text)

        self._log(f"Found {len(priced_cards)} deal cards")

        for text in priced_cards:
            # Data: first GB mention is the headline amount, or "Unlimited Data"
            is_unlimited = bool(re.search(r'Unlimited\s+Data', text, re.I))
            data_gb = None
            if not is_unlimited:
                # Get the FIRST GB mention (headline data including bonus)
                dm = re.search(r'(\d+)\s*GB', text)
                if dm:
                    data_gb = int(dm.group(1))
                if not data_gb:
                    continue

            # Price: "£N a month" - but skip crossed-out prices
            # iD shows "£16 £17 a month" where £16 is current and £17 is after rise
            # Take the first price
            pm = re.search(r'£(\d+(?:\.\d+)?)\s+(?:£\d+(?:\.\d+)?\s+)?a\s+month', text)
            if not pm:
                pm = re.search(r'£(\d+(?:\.\d+)?)\s+a\s+month', text)
            if not pm:
                continue
            price = float(pm.group(1))
            if price < 3 or price > 50:
                continue

            # Contract: "1 Month" or "12 Months" or "24 Months"
            contract = 1
            cm = re.search(r'(\d+)\s+Months?', text, re.I)
            if cm:
                val = int(cm.group(1))
                if 1 <= val <= 36:
                    contract = val

            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            key = (price, data_gb, is_unlimited, contract)
            if key in seen:
                continue
            seen.add(key)

            extras = []
            if 'Extra Data' in text:
                extras.append('Extra data included')
            if 'No annual price rise' in text:
                extras.append('No price rises')
            if 'EU roaming' in text.lower():
                extras.append('EU Roaming')

            plans.append(ScrapedPlan(
                name=f'iD Mobile {data_label}',
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                url=url,
                contract_months=contract,
                network='iD Mobile',
                extras=', '.join(extras) if extras else None,
            ))

        return plans
