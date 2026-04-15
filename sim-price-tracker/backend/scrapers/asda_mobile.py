"""Asda Mobile scraper."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class AsdaMobileScraper(UnifiedScraper):
    provider_name = "ASDA Mobile"
    provider_slug = "asda-mobile"
    provider_type = "mvno"
    urls = ['https://mobile.asda.com/sim-only-deals']
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
                await page.goto(url, timeout=20000, wait_until='domcontentloaded')
                await page.wait_for_timeout(8000)
                for _ in range(5):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await page.wait_for_timeout(500)
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
            plans = self._parse_asda(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "ASDA Mobile"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_asda(self, html, url):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(' ')
        seen = set()

        # Try card-based extraction first
        for sel in ['[class*="plan"]', '[class*="bundle"]', '[class*="card"]', '[class*="product"]', 'article']:
            cards = soup.select(sel)
            priced = [c for c in cards if '£' in c.get_text()[:400] and re.search(r'\d+\s*GB', c.get_text()[:400]) and 30 < len(c.get_text(' ', strip=True)) < 500]
            if priced:
                self._log(f"Found {len(priced)} plan cards with '{sel}'")
                for card in priced:
                    ct = card.get_text(' ', strip=True)
                    plan = self._parse_card_text(ct, url)
                    if plan:
                        key = (plan.price, plan.data_gb, plan.contract_months)
                        if key not in seen:
                            seen.add(key)
                            plans.append(plan)
                if plans:
                    return plans

        # Fallback: parse from page text with "£X ... NGB" or "NGB ... £X" patterns
        self._log("No cards found, using text patterns")
        for m in re.finditer(r'£(\d+(?:\.\d+)?)\s*(?:a\s+month|/mo|per\s+month).{0,40}?(\d+)\s*GB', text, re.I):
            price = float(m.group(1))
            data_gb = int(m.group(2))
            if price < 3 or price > 50 or data_gb < 1:
                continue
            key = (price, data_gb, 1)
            if key not in seen:
                seen.add(key)
                plans.append(ScrapedPlan(
                    name=f'ASDA Mobile {data_gb}GB', price=price, data_gb=data_gb,
                    url=url, contract_months=1, network='ASDA Mobile',
                ))

        for m in re.finditer(r'(\d+)\s*GB.{0,40}?£(\d+(?:\.\d+)?)\s*(?:a\s+month|/mo|per\s+month)', text, re.I):
            data_gb = int(m.group(1))
            price = float(m.group(2))
            if price < 3 or price > 50 or data_gb < 1:
                continue
            key = (price, data_gb, 1)
            if key not in seen:
                seen.add(key)
                plans.append(ScrapedPlan(
                    name=f'ASDA Mobile {data_gb}GB', price=price, data_gb=data_gb,
                    url=url, contract_months=1, network='ASDA Mobile',
                ))

        return plans

    def _parse_card_text(self, text, url):
        dm = re.search(r'(\d+)\s*GB', text, re.I)
        data_gb = int(dm.group(1)) if dm else None
        if not data_gb:
            return None

        pm = re.search(r'£(\d+(?:\.\d+)?)', text)
        if not pm:
            return None
        price = float(pm.group(1))
        if price < 3 or price > 50:
            return None

        contract = 1
        cm = re.search(r'(\d+)\s*month', text, re.I)
        if cm:
            val = int(cm.group(1))
            if 1 <= val <= 36:
                contract = val

        return ScrapedPlan(
            name=f'ASDA Mobile {data_gb}GB', price=price, data_gb=data_gb,
            url=url, contract_months=contract, network='ASDA Mobile',
        )
