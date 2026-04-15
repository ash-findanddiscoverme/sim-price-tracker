"""Mozillion scraper - parses SIM plan cards from their pay-monthly page."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class MozillionScraper(UnifiedScraper):
    provider_name = "Mozillion"
    provider_slug = "mozillion"
    provider_type = "mvno"
    urls = ['https://www.mozillion.com/sim/pay-monthly-sim']
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
                for sel in ['#onetrust-accept-btn-handler', 'button:has-text("Accept")', '[class*="cookie"] button']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        pass

                # Scroll to load all plan cards
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(800)

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
            plans = self._parse_plans(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "Mozillion"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_plans(self, html, url):
        """
        Mozillion plan cards follow this pattern:
          "[N]GB data" or "Unlimited data"
          "[N]-Month" or "[N]-Months"
          "Unlimited calls & txts"
          "EU roaming"
          "£X.XX p/m"
        """
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        # Try card-based selectors first
        cards = []
        for sel in ['[class*="product"]', '[class*="card"]', '[class*="plan"]', '[class*="item"]']:
            found = soup.select(sel)
            priced = [c for c in found if 'p/m' in c.get_text() and ('GB data' in c.get_text() or 'Unlimited data' in c.get_text()) and 'Month' in c.get_text()]
            if priced:
                cards = priced
                self._log(f"Found {len(cards)} plan cards with '{sel}'")
                break

        for card in cards:
            raw = card.get_text(' ', strip=True)
            # Collapse all whitespace to single spaces for reliable regex
            text = re.sub(r'\s+', ' ', raw).strip()
            if len(text) < 15 or len(text) > 400:
                continue

            plan = self._parse_card_text(text, url)
            if plan:
                key = (plan.price, plan.data_gb, plan.data_unlimited, plan.contract_months)
                if key not in seen:
                    seen.add(key)
                    plans.append(plan)

        # Fallback: regex on full page text
        if not plans:
            self._log("No cards found, using text patterns")
            page_text = re.sub(r'\s+', ' ', soup.get_text(' '))
            for m in re.finditer(
                r'((?:\d+GB|Unlimited)\s+data)\s+([\d]+-Months?)\s+.*?£(\d+(?:\.\d+)?)\s*p/m',
                page_text, re.I
            ):
                data_str = m.group(1)
                contract_str = m.group(2)
                price = float(m.group(3))

                dm = re.search(r'(\d+)\s*GB', data_str)
                data_gb = int(dm.group(1)) if dm else None
                is_unlimited = 'unlimited' in data_str.lower()

                cm = re.search(r'(\d+)', contract_str)
                contract = int(cm.group(1)) if cm else 1

                if not data_gb and not is_unlimited:
                    continue
                if price < 3 or price > 30:
                    continue

                key = (price, data_gb, is_unlimited, contract)
                if key not in seen:
                    seen.add(key)
                    data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
                    plans.append(ScrapedPlan(
                        name=f'Mozillion {data_label}',
                        price=price,
                        data_gb=data_gb,
                        data_unlimited=is_unlimited,
                        url=url,
                        contract_months=contract,
                        network='Mozillion',
                        extras='EU Roaming, No credit check, No price rises',
                    ))

        return plans

    def _parse_card_text(self, text, url):
        # Data
        dm = re.search(r'(\d+)\s*GB\s+data', text, re.I)
        data_gb = int(dm.group(1)) if dm else None
        is_unlimited = 'unlimited data' in text.lower() and not data_gb

        if not data_gb and not is_unlimited:
            return None

        # Price: "£X.XX p/m"
        pm = re.search(r'£(\d+(?:\.\d+)?)\s*p/m', text)
        if not pm:
            return None
        price = float(pm.group(1))
        if price < 3 or price > 30:
            return None

        # Contract: "N-Month" or "N-Months"
        contract = 1
        cm = re.search(r'(\d+)-Months?', text, re.I)
        if cm:
            contract = int(cm.group(1))

        data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'

        extras = []
        if 'EU roaming' in text:
            extras.append('EU Roaming')
        if 'No credit check' in text.lower() or 'no credit' in text.lower():
            extras.append('No credit check')

        return ScrapedPlan(
            name=f'Mozillion {data_label}',
            price=price,
            data_gb=data_gb,
            data_unlimited=is_unlimited,
            url=url,
            contract_months=contract,
            network='Mozillion',
            extras=', '.join(extras) if extras else 'EU Roaming, No price rises',
        )
