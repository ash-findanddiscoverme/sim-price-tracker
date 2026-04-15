"""mobiles.co.uk scraper with deal card parsing."""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, normalize_network

logger = logging.getLogger(__name__)


class MobilesCoUkScraper(UnifiedScraper):
    provider_name = "mobiles.co.uk"
    provider_slug = "mobilescouk"
    provider_type = "affiliate"
    urls = ['https://www.mobiles.co.uk/sim-only']
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
                await page.goto(url, timeout=25000, wait_until='domcontentloaded')
                await page.wait_for_timeout(6000)
                for _ in range(8):
                    await page.evaluate('window.scrollBy(0, 600)')
                    await page.wait_for_timeout(500)
                html = await page.content()
                await browser.close()
                self._log(f'Playwright got {len(html)} chars')
                return html if len(html) > 10000 else None
        except Exception as e:
            self._log(f'Playwright error: {e}', 'error')
        return None

    async def scrape(self):
        all_plans = []
        for url in self.urls:
            html = await self._fetch_html(url)
            if not html:
                self._log(f'Failed to fetch {url}', 'error')
                continue
            self._log(f'Got {len(html)} chars from {url}')
            plans = self._parse_deals(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        self._log(f'Total: {len(result)} unique plans', 'success' if result else 'warning')
        return result

    def _parse_deals(self, html, url):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        deals = soup.select('[class*="deal"]')
        self._log(f'Found {len(deals)} deal elements')

        for card in deals:
            text = card.get_text(' ', strip=True)
            if len(text) < 30 or len(text) > 600 or '£' not in text:
                continue

            # Provider at start
            prov_match = re.match(r'^([\w\s]+?)\s+\d', text)
            if not prov_match:
                continue
            provider = prov_match.group(1).strip()
            if len(provider) > 25:
                continue

            # Price: "Monthly Cost £X.XX" or "£X.XX"
            pm = re.search(r'Monthly\s+Cost\s+£(\d+(?:\.\d+)?)', text)
            if not pm:
                pm = re.search(r'£(\d+(?:\.\d+)?)', text)
            if not pm:
                continue
            price = float(pm.group(1))
            if price < 1 or price > 100:
                continue

            # Data
            dm = re.search(r'(\d+)\s*GB\s+Data', text, re.IGNORECASE)
            if not dm:
                dm = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
            data_gb = int(dm.group(1)) if dm else None
            is_unlimited = 'unlimited' in text.lower() and not data_gb
            if not data_gb and not is_unlimited:
                continue

            # Contract
            cm = re.search(r'(\d+)\s*months?', text, re.IGNORECASE)
            contract = int(cm.group(1)) if cm and 1 <= int(cm.group(1)) <= 36 else 1

            is_5g = '5G' in text
            provider = normalize_network(provider) or provider
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            name = f'{provider} {data_label}'

            key = (provider, price, data_gb, is_unlimited, contract)
            if key in seen:
                continue
            seen.add(key)

            plans.append(ScrapedPlan(
                name=name, price=price, data_gb=data_gb,
                data_unlimited=is_unlimited, is_5g=is_5g,
                url=url, contract_months=contract,
                network=provider,
            ))

        return plans
