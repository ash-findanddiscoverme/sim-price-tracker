"""Lyca Mobile scraper with tab iteration for contract lengths."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class LycaMobileScraper(UnifiedScraper):
    provider_name = "Lyca Mobile"
    provider_slug = "lyca-mobile"
    provider_type = "mvno"
    urls = ['https://www.lycamobile.co.uk/en/bundles']
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
                await page.wait_for_timeout(5000)

                # Dismiss cookies
                for sel in ['#onetrust-accept-btn-handler', 'button:has-text("Accept")']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass

                collected_html = []
                tabs = [
                    ('30 day plans', 1),
                    ('12 Month Plan', 12),
                    ('24 Month Plan', 24),
                ]

                for tab_text, months in tabs:
                    try:
                        tab = page.locator(f'button:has-text("{tab_text}")').first
                        if not await tab.is_visible(timeout=1000):
                            tab = page.locator(f'a:has-text("{tab_text}")').first
                        if await tab.is_visible(timeout=1000):
                            await tab.click(force=True)
                            self._log(f"Clicked tab: {tab_text}")
                            await page.wait_for_timeout(2000)

                            for _ in range(5):
                                await page.evaluate("window.scrollBy(0, 600)")
                                await page.wait_for_timeout(500)

                            html = await page.content()
                            collected_html.append((html, months))
                    except Exception as e:
                        self._log(f"Tab error ({tab_text}): {e}")

                await browser.close()

                if not collected_html:
                    return None

                self._log(f"Collected HTML from {len(collected_html)} tabs")
                self._collected_tabs = collected_html
                return collected_html[0][0]
        except Exception as e:
            self._log(f'Playwright error: {e}', 'error')
        return None

    async def scrape(self):
        self._collected_tabs = []
        all_plans = []

        for url in self.urls:
            html = await self._fetch_html(url)
            if not html and not self._collected_tabs:
                self._log(f"Failed to fetch {url}", "error")
                continue

            if self._collected_tabs:
                for tab_html, contract_months in self._collected_tabs:
                    plans = self._parse_lyca_plans(tab_html, url, contract_months)
                    all_plans.extend(plans)
            else:
                plans = self._parse_lyca_plans(html, url, 1)
                all_plans.extend(plans)

        result = self._dedupe(all_plans)
        for p in result:
            p.network = "Lyca Mobile"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_lyca_plans(self, html, url, default_contract):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()

        plan_cards = soup.select('[class*="plan"]')
        self._log(f"Found {len(plan_cards)} plan elements (contract={default_contract}mo)")

        for card in plan_cards:
            text = card.get_text(' ', strip=True)
            if len(text) < 20 or len(text) > 500 or '£' not in text:
                continue

            # Data amount
            dm = re.search(r'(\d+)\s*GB\s+Data', text)
            if not dm:
                dm = re.search(r'(\d+)\s*GB', text)
            data_gb = int(dm.group(1)) if dm else None

            is_unlimited = 'unlimited data' in text.lower() and not data_gb
            if not data_gb and not is_unlimited:
                continue

            # Price: "£ X.XX /30 days" or "£ X.XX"
            pm = re.search(r'£\s*(\d+(?:\.\d+)?)\s*/?\s*(?:30\s*days)?', text)
            if not pm:
                continue
            price = float(pm.group(1))
            if price < 2 or price > 50:
                continue

            # Plan name
            name_match = re.search(r'(UK Plan\s+\w+(?:\s+\w+)?|National\s+Plus|Plan\s+Mega\s+Plus|Plan\s+Super\s+Extra)', text, re.I)
            plan_label = name_match.group(1).strip() if name_match else None

            contract = default_contract

            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            display = f'Lyca Mobile {data_label}'
            if plan_label:
                display = f'Lyca {plan_label} {data_label}'

            key = (price, data_gb, is_unlimited, contract)
            if key in seen:
                continue
            seen.add(key)

            extras = []
            if 'EU Roaming' in text:
                extras.append('EU Roaming')
            if 'India' in text:
                extras.append('India Roaming')
            if 'International minutes' in text:
                im = re.search(r'(\d+)\s+International\s+minutes', text)
                if im:
                    extras.append(f'{im.group(1)} intl mins')
            if 'eSIM' in text:
                extras.append('eSIM')

            plans.append(ScrapedPlan(
                name=display,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                url=url,
                contract_months=contract,
                network='Lyca Mobile',
                extras=', '.join(extras) if extras else None,
            ))

        return plans
