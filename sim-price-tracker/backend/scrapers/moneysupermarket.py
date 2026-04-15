"""MoneySupermarket scraper with structural article parsing."""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, normalize_network

logger = logging.getLogger(__name__)


class MoneySupermarketScraper(UnifiedScraper):
    provider_name = "MoneySupermarket"
    provider_slug = "moneysupermarket"
    provider_type = "affiliate"
    urls = ['https://www.moneysupermarket.com/mobile-phones/sim-only/']
    use_playwright = True

    async def _get_html_playwright(self, url):
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await self._launch_browser(p)
                ctx = await browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-GB',
                )
                page = await ctx.new_page()
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false})")
                await page.goto(url, timeout=25000, wait_until='domcontentloaded')
                await page.wait_for_timeout(6000)

                # Aggressive cookie/consent dismiss for MoneySupermarket
                cookie_selectors = [
                    "#onetrust-accept-btn-handler",
                    "[data-testid='cookie-accept']",
                    "button:has-text('Accept all cookies')",
                    "button:has-text('Accept all')",
                    "button:has-text('Accept')",
                    "button:has-text('I agree')",
                    ".cookie-banner button",
                    "[class*='cookie'] button",
                    "[class*='consent'] button",
                ]
                for sel in cookie_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.is_visible(timeout=1500):
                            await loc.click()
                            self._log(f"Dismissed cookie banner with: {sel}")
                            await page.wait_for_timeout(1000)
                    except Exception:
                        continue
                
                # Remove overlays via JavaScript as fallback
                try:
                    await page.evaluate("""
                        document.querySelectorAll('#onetrust-consent-sdk, .onetrust-pc-dark-filter, [class*="cookie"], [class*="consent"]').forEach(el => {
                            if (el.querySelector('button') === null) el.remove();
                        });
                    """)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

                # Keep clicking "Show more results" until deal cards stop growing.
                deal_card_selectors = [
                    "button:has-text('Show more results')",
                    "[class*='load-more'] button",
                    "button:has-text('Load more')",
                    "button:has-text('Show more')",
                    "a:has-text('View all')",
                    "button:has-text('Show all')",
                ]

                async def _count_deal_cards():
                    # MoneySupermarket parsing uses <article> cards, so we can use that as a proxy.
                    return await page.locator("article").count()

                last_count = await _count_deal_cards()
                clicks = 0
                max_clicks = 25
                no_growth_rounds = 0
                max_no_growth_rounds = 4

                while clicks < max_clicks and no_growth_rounds < max_no_growth_rounds:
                    clicked = False
                    
                    # Scroll to bottom first
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
                    
                    for sel in deal_card_selectors:
                        try:
                            loc = page.locator(sel).first
                            if await loc.is_visible(timeout=500):
                                await loc.scroll_into_view_if_needed()
                                await page.wait_for_timeout(300)
                                await loc.click(force=True, timeout=5000)
                                clicked = True
                                clicks += 1
                                self._log(f"Clicked load more ({clicks})")
                                await page.wait_for_timeout(2500)
                            await page.evaluate("window.scrollBy(0, 800)")
                            await page.wait_for_timeout(1000)
                            break
                        except Exception:
                            continue

                    if not clicked:
                        break

                    new_count = await _count_deal_cards()
                    if new_count > last_count:
                        last_count = new_count
                        no_growth_rounds = 0
                    else:
                        no_growth_rounds += 1

                # Final scroll to trigger any remaining lazy-loaded deals.
                for _ in range(10):
                    await page.evaluate("window.scrollBy(0, 900)")
                    await page.wait_for_timeout(1200)
                    new_count = await _count_deal_cards()
                    if new_count == last_count:
                        break
                    last_count = new_count
                html = await page.content()
                await browser.close()
                self._log(f'Playwright got {len(html)} chars from {url}')
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
            plans = self._parse_articles(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_articles(self, html, url):
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()
        provider_counts = {}

        # Try multiple selectors
        articles = soup.select('article')
        if len(articles) < 10:
            articles = soup.select('[class*="deal"], [class*="product"], [class*="result"], [class*="card"]')
        
        self._log(f"Found {len(articles)} article/deal cards")

        for art in articles:
            text = art.get_text(' ', strip=True)
            if len(text) < 30:
                continue
            # Must have price indicator
            if '£' not in text:
                continue

            # Provider: Try multiple patterns
            provider = None
            
            # Pattern 1: "[Name] sim only" at start
            prov_match = re.match(r'^([\w\s]+?)\s+sim\s+only', text, re.IGNORECASE)
            if prov_match:
                provider = prov_match.group(1).strip()
            
            # Pattern 2: Look for known networks in first 80 chars
            if not provider:
                first_part = text[:80]
                for net in ["O2", "EE", "Three", "Vodafone", "giffgaff", "VOXI", "Sky Mobile", "Sky", 
                           "Tesco Mobile", "ASDA Mobile", "iD Mobile", "Lebara", "SMARTY", "Lyca Mobile"]:
                    if re.search(r'\b' + re.escape(net) + r'\b', first_part, re.IGNORECASE):
                        provider = net
                        break
            
            if not provider:
                continue
                
            # Skip header/info cards
            if len(provider) > 25 or 'deal' in provider.lower() or 'everything' in provider.lower():
                continue

            # Underlying network: "Uses [Network]'s network"
            underlying = None
            net_match = re.search(r"Uses\s+([\w\s]+?)'s\s+network", text, re.IGNORECASE)
            if net_match:
                underlying = net_match.group(1).strip()

            # Price: Multiple patterns
            price = None
            # Pattern 1: "£X.XX per month"
            pm = re.search(r'£(\d+(?:\.\d+)?)\s*per\s*month', text, re.IGNORECASE)
            if pm:
                price = float(pm.group(1))
            # Pattern 2: "£X.XX a month"
            if not price:
                pm = re.search(r'£(\d+(?:\.\d+)?)\s*a\s*month', text, re.IGNORECASE)
                if pm:
                    price = float(pm.group(1))
            # Pattern 3: "£X.XX/month" or "£X.XX /mo"
            if not price:
                pm = re.search(r'£(\d+(?:\.\d+)?)\s*/\s*mo', text, re.IGNORECASE)
                if pm:
                    price = float(pm.group(1))
            
            if not price or price < 1 or price > 100:
                continue

            # Data: Multiple patterns
            data_gb = None
            is_unlimited = False
            
            # Pattern 1: "NGB of [speed] data"
            dm = re.search(r'(\d+)\s*GB\s+of', text, re.IGNORECASE)
            if dm:
                data_gb = int(dm.group(1))
            # Pattern 2: Just "NGB" 
            if not data_gb:
                dm = re.search(r'(\d+)\s*GB\b', text, re.IGNORECASE)
                if dm:
                    val = int(dm.group(1))
                    if 1 <= val <= 500:
                        data_gb = val
            # Pattern 3: Unlimited
            if not data_gb and 'unlimited' in text.lower():
                is_unlimited = True
                
            if not data_gb and not is_unlimited:
                continue

            # Contract
            contract = 1
            cm = re.search(r'(\d+)\s*month\s*contract', text, re.IGNORECASE)
            if cm:
                val = int(cm.group(1))
                if 1 <= val <= 36:
                    contract = val

            is_5g = '5G' in text
            provider = normalize_network(provider) or provider
            data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
            name = f'{provider} {data_label}'

            key = (provider, price, data_gb, is_unlimited, contract)
            if key in seen:
                continue
            seen.add(key)

            plans.append(ScrapedPlan(
                name=name,
                price=price,
                data_gb=data_gb,
                data_unlimited=is_unlimited,
                is_5g=is_5g,
                url=url,
                contract_months=contract,
                network=provider,
            ))
            
            # Track for logging
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

        # Log breakdown by provider
        if provider_counts:
            breakdown = ', '.join(f"{k}:{v}" for k, v in sorted(provider_counts.items()))
            self._log(f"Provider breakdown: {breakdown}")

        return plans
