"""EE scraper with tab and contract filter iteration."""

import re
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan


class EEScraper(UnifiedScraper):
    provider_name = "EE"
    provider_slug = "ee"
    provider_type = "network"
    urls = ['https://ee.co.uk/mobile/sim-only-deals']
    use_playwright = True

    async def _get_html_playwright(self, url):
        """Override to click through tabs and contract filters, collecting all plan HTML."""
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

                collected_html = []
                tabs = ['Deals', 'Standard', 'Additional SIMs', 'EE One']
                contracts = ['24 months', '1 month']

                for tab_name in tabs:
                    try:
                        tab = page.locator(f'[role="tab"]:has-text("{tab_name}")').first
                        if await tab.is_visible(timeout=2000):
                            await tab.click(force=True)
                            self._log(f"Clicked tab: {tab_name}")
                            await page.wait_for_timeout(3000)
                        else:
                            continue
                    except Exception:
                        self._log(f"Tab '{tab_name}' not found")
                        continue

                    for contract in contracts:
                        try:
                            c_btn = page.locator(f'button:has-text("{contract}")').first
                            if await c_btn.is_visible(timeout=1000):
                                await c_btn.click(force=True)
                                self._log(f"  Contract: {contract}")
                                await page.wait_for_timeout(2000)
                        except Exception:
                            continue

                        # Scroll to load all plan cards
                        for _ in range(10):
                            await page.evaluate("window.scrollBy(0, 800)")
                            await page.wait_for_timeout(600)

                        html_chunk = await page.content()
                        collected_html.append(html_chunk)

                combos = len(collected_html)
                combined = '\n'.join(collected_html)
                self._log(f"Combined HTML from {combos} tab/contract combos: {len(combined)} chars")
                await browser.close()
                return combined if len(combined) > 10000 else None
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
            plans = self._parse_ee_plans(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        for p in result:
            p.network = "EE"
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_ee_plans(self, html, url):
        plans = []
        seen = set()

        # Fast regex-only approach for large multi-page HTML
        # Strip tags to get text, then find plan blocks
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)

        # Match plan blocks: "NGB [Name] N month contract ... £N a month"
        for m in re.finditer(
            r'(\d+GB|Unlimited)\s+([\w\s]{3,40}?)\s+(\d+)\s*month\s*contract\s+.*?£\s*(\d+)\s+£\s*\d+(?:\s*\.\s*\d+)?\s*a\s+month',
            text
        ):
            data_str = m.group(1)
            plan_name = m.group(2).strip()
            contract = int(m.group(3))
            price = float(m.group(4))

            if price < 5 or price > 80 or contract < 1 or contract > 36:
                continue
            if any(skip in plan_name for skip in ['Apple One', 'Bundles', 'Already', 'Save up']):
                continue

            dm = re.match(r'(\d+)GB', data_str)
            data_gb = int(dm.group(1)) if dm else None
            is_unlimited = data_str.lower().startswith('unlimited')

            if not data_gb and not is_unlimited:
                continue

            is_5g = True
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            display = f'EE {plan_name}' if plan_name and plan_name not in ('SIM',) else f'EE {data_label}'

            key = (display, price, data_gb, is_unlimited, contract)
            if key not in seen:
                seen.add(key)

                extras = []
                if 'Uncapped speed' in m.group(0):
                    extras.append('Uncapped speed')

                plans.append(ScrapedPlan(
                    name=display,
                    price=price,
                    data_gb=data_gb,
                    data_unlimited=is_unlimited,
                    is_5g=is_5g,
                    url=url,
                    contract_months=contract,
                    network='EE',
                    extras=', '.join(extras) if extras else None,
                ))

        return plans

    def _parse_plan_text(self, text, url):
        # Data amount
        dm = re.search(r'(\d+)\s*GB', text)
        data_gb = int(dm.group(1)) if dm else None
        is_unlimited = 'unlimited' in text.lower() and not data_gb

        if not data_gb and not is_unlimited:
            return None
        if data_gb and (data_gb < 1 or data_gb > 500):
            return None

        # Price: EE shows "£22 £ 22 a month" - two copies of the price
        # Pattern 1: "£N £ N a month" (space-separated duplicate)
        pm = re.search(r'£(\d+(?:\.\d+)?)\s+£\s*\d+(?:\s*\.\s*\d+)?\s*a\s+month', text)
        if not pm:
            # Pattern 2: "£ N a month" (with space after £)
            pm = re.search(r'£\s*(\d+(?:\.\d+)?)\s+a\s+month', text)
        if not pm:
            # Pattern 3: "£N a month"
            pm = re.search(r'£(\d+(?:\.\d+)?)\s*a\s+month', text)
        if not pm:
            # Pattern 4: first standalone £N
            pm = re.search(r'£(\d+(?:\.\d+)?)', text)
        if not pm:
            return None
        price = float(pm.group(1))
        if price < 5 or price > 80:
            return None

        # Contract: "24 month contract" or "1 month contract"
        contract = 24
        cm = re.search(r'(\d+)\s*month\s*contract', text)
        if cm:
            val = int(cm.group(1))
            if 1 <= val <= 36:
                contract = val

        is_5g = '5G' in text or '5g' in text

        # Plan name: extract from the start of text
        # Patterns like "5GB No Frills", "25GB Essentials", "Unlimited All Rounder", "Unlimited Full Works"
        plan_name = None
        name_match = re.match(
            r'^((?:Unlimited\s+)?(?:\d+GB\s+)?(?:No Frills|Essentials(?:\s+(?:Max|Plus\s+Max))?|All\s+Rounder(?:\s+for\s+iPhone)?|Full\s+Works(?:\s+for\s+iPhone)?|SIM))',
            text, re.I
        )
        if name_match:
            plan_name = name_match.group(1).strip()

        if is_unlimited and plan_name:
            data_label = plan_name
        elif is_unlimited:
            data_label = 'Unlimited'
        else:
            data_label = f'{data_gb}GB'

        if plan_name and not plan_name.startswith(('Unlimited', 'SIM')):
            display_name = f'EE {plan_name}'
        elif plan_name:
            display_name = f'EE {plan_name}'
        else:
            display_name = f'EE {data_label}'

        extras = []
        if 'Uncapped speed' in text:
            extras.append('Uncapped speed')
        if 'EU Roaming' in text:
            extras.append('EU Roaming')
        if 'Netflix' in text:
            extras.append('Netflix included')
        if 'Priority coverage' in text:
            extras.append('Priority coverage')
        # Price rise info
        rise = re.search(r'£(\d+(?:\.\d+)?)\s*from\s+\d+', text)
        if rise:
            extras.append(f'Rises to £{rise.group(1)}')

        return ScrapedPlan(
            name=display_name,
            price=price,
            data_gb=data_gb,
            data_unlimited=is_unlimited,
            is_5g=is_5g,
            url=url,
            contract_months=contract,
            network='EE',
            extras=', '.join(extras) if extras else None,
        )
