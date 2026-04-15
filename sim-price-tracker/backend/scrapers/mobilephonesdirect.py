"""Mobile Phones Direct scraper with deal card parsing."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, normalize_network


class MobilePhonesDirectScraper(UnifiedScraper):
    provider_name = "Mobile Phones Direct"
    provider_slug = "mobilephonesdirect"
    provider_type = "affiliate"
    urls = ['https://www.mobilephonesdirect.co.uk/sim-only']
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
                await page.wait_for_timeout(6000)
                for _ in range(10):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await page.wait_for_timeout(400)
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
                self._log(f"Failed to fetch {url}", "error")
                continue
            self._log(f"Got {len(html)} chars from {url}")
            plans = self._parse_deals(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_deals(self, html, url):
        """
        MPD splits provider/data and price into separate elements.
        Strategy: find each 'Monthly Cost: £X' and look backwards for the
        nearest 'Contract [Provider] SIM Card' with data info.
        """
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(' ')
        seen = set()

        # Find all provider+data headers
        headers = list(re.finditer(
            r'Contract\s+(?:DATA\s+BOOST\s+)?([\w\s]+?)\s+SIM\s+Card\s+(\d+)\s+months?',
            text
        ))
        # Find all monthly costs
        costs = list(re.finditer(r'Monthly\s+Cost:\s+£(\d+(?:\.\d+)?)', text))

        self._log(f"Found {len(headers)} deal headers, {len(costs)} Monthly Cost entries")

        # Match each cost to its nearest preceding header
        for cost_match in costs:
            cost_pos = cost_match.start()
            price = float(cost_match.group(1))
            if price < 3 or price > 60:
                continue

            # Find the closest header before this cost
            best_header = None
            best_dist = float('inf')
            for h in headers:
                dist = cost_pos - h.start()
                if 0 < dist < 2000 and dist < best_dist:
                    best_dist = dist
                    best_header = h

            if not best_header:
                continue

            raw_provider = best_header.group(1).strip()
            provider = normalize_network(raw_provider) or raw_provider
            if len(provider) > 25 or len(provider) < 2:
                continue
            contract = int(best_header.group(2))
            if contract < 1 or contract > 36:
                contract = 1

            # Extract data from the region between header and cost
            region = text[best_header.start():cost_pos + 50]
            data_gb = None
            is_unlimited = False
            dm = re.search(r'(?:was\s+\d+GB\s+)?(\d+)\s*GB\s+Data', region, re.I)
            if dm:
                data_gb = int(dm.group(1))
            elif re.search(r'Unlimited\s+Data', region, re.I):
                is_unlimited = True
            if not data_gb and not is_unlimited:
                continue

            is_5g = '5G' in region
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
