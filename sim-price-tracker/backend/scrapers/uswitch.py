"""uSwitch scraper with structural card parsing for accuracy."""

import re
import logging
from bs4 import BeautifulSoup
from .unified_base import UnifiedScraper, ScrapedPlan, normalize_network

logger = logging.getLogger(__name__)


class USwitchScraper(UnifiedScraper):
    provider_name = "uSwitch"
    provider_slug = "uswitch"
    provider_type = "affiliate"
    urls = ['https://www.uswitch.com/mobiles/compare/sim_only_deals/']
    use_playwright = True

    async def _get_html_playwright(self, url):
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await self._launch_browser(p)
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-GB",
                )
                page = await ctx.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
                )
                await page.goto(url, timeout=45000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)

                # Dismiss cookie/consent banners - uSwitch has multiple banners
                cookie_selectors = [
                    '#onetrust-accept-btn-handler',
                    'button:has-text("Accept all cookies")',
                    'button:has-text("Accept all")',
                    'button:has-text("Accept")',
                    '.ucb button:has-text("Accept")',
                    '.ucb-controls button',
                    '[data-include="cookie-banner"] button',
                ]
                for sel in cookie_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            self._log(f"Dismissed cookie banner with: {sel}")
                            await page.wait_for_timeout(1500)
                    except Exception:
                        pass
                
                # Also try to remove overlay via JavaScript as fallback
                try:
                    await page.evaluate("""
                        document.querySelectorAll('.ucb, .ucb-overlay, [data-include="cookie-banner"]').forEach(el => el.remove());
                        document.querySelectorAll('#onetrust-consent-sdk, .onetrust-pc-dark-filter').forEach(el => el.remove());
                    """)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass

                # uSwitch-specific button selectors (they use "Show more results", "Load more deals", etc.)
                button_selectors = [
                    'button:has-text("Show more results")',
                    'button:has-text("Show more deals")',
                    'button:has-text("Load more results")',
                    'button:has-text("Load more deals")',
                    'button:has-text("Load more")',
                    'button:has-text("Show more")',
                    'a:has-text("Show more results")',
                    'a:has-text("Load more")',
                    '[data-testid="load-more"]',
                    '[class*="load-more"] button',
                    '[class*="show-more"] button',
                ]

                async def _count_articles():
                    return await page.locator("article").count()

                # Initial scroll to load content and find the button
                self._log("Initial scroll to load content...")
                for _ in range(8):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)

                last_count = await _count_articles()
                self._log(f"Initial article count: {last_count}")

                # Keep clicking load more until no new content
                clicks = 0
                max_clicks = 50
                no_growth_rounds = 0
                max_no_growth_rounds = 3

                while clicks < max_clicks and no_growth_rounds < max_no_growth_rounds:
                    clicked = False
                    
                    # Scroll to bottom to make button visible
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
                    
                    for sel in button_selectors:
                        try:
                            loc = page.locator(sel).first
                            if await loc.is_visible(timeout=500):
                                await loc.scroll_into_view_if_needed()
                                await page.wait_for_timeout(300)
                                # Use force click to bypass any overlays
                                await loc.click(force=True, timeout=5000)
                                clicked = True
                                clicks += 1
                                self._log(f"Clicked load more ({clicks})")
                                await page.wait_for_timeout(3000)
                                break
                        except Exception as e:
                            self._log(f"Click error with {sel}: {str(e)[:50]}")
                            continue

                    if not clicked:
                        # Try scrolling more to trigger infinite scroll
                        for _ in range(3):
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await page.wait_for_timeout(2000)
                        
                        new_count = await _count_articles()
                        if new_count > last_count:
                            last_count = new_count
                            continue
                        break

                    new_count = await _count_articles()
                    self._log(f"Article count: {last_count} -> {new_count}")
                    if new_count > last_count:
                        last_count = new_count
                        no_growth_rounds = 0
                    else:
                        no_growth_rounds += 1

                # Final comprehensive scroll to trigger any remaining lazy loads
                self._log("Final scroll sweep...")
                for _ in range(15):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)
                    new_count = await _count_articles()
                    if new_count > last_count:
                        last_count = new_count
                    else:
                        break

                self._log(f"Final article count: {last_count}")
                html = await page.content()
                await browser.close()
                self._log(f"Playwright got {len(html)} chars from {url}")
                return html if len(html) > 10000 else None
        except Exception as e:
            self._log(f"Playwright error: {e}", "error")
        return None

    async def scrape(self):
        """Override base to use only structural parsing."""
        all_plans = []
        for url in self.urls:
            html = await self._fetch_html(url)
            if not html:
                self._log(f"Failed to fetch {url}", "error")
                continue
            self._log(f"Got {len(html)} chars from {url}")
            plans = self._parse_cards(html, url)
            all_plans.extend(plans)
        result = self._dedupe(all_plans)
        self._log(f"Total: {len(result)} unique plans", "success" if result else "warning")
        return result

    def _parse_cards(self, html, url):
        """
        Parse each article card as a single cohesive unit.
        
        uSwitch card text follows this exact structure:
          [Provider] SIM Deal [Uses [Network]'s Network]
          £ [price] a month [for N months, then £ [regular]]
          [N month contract | No contract]
          [N] GB of [speed] data [| Unlimited [speed] data]
          [perks...]
        """
        plans = []
        soup = BeautifulSoup(html, 'html.parser')
        seen = set()
        provider_counts = {}

        # Try multiple selectors for deal cards
        articles = soup.select('article')
        if len(articles) < 10:
            # Fallback: try other common card selectors
            articles = soup.select('[class*="deal"], [class*="product"], [class*="tariff"], [class*="offer"]')
        
        self._log(f"Found {len(articles)} article/deal cards")

        for card in articles:
            text = card.get_text(' ', strip=True)
            # More lenient filtering - just needs price and data info
            if len(text) < 30:
                continue
            # Must have a price indicator
            if '£' not in text and 'month' not in text.lower():
                continue

            parsed = self._parse_single_card(text, url)
            if not parsed:
                continue

            key = (parsed.network, parsed.price, parsed.data_gb,
                   parsed.data_unlimited, parsed.contract_months)
            if key in seen:
                continue
            seen.add(key)
            plans.append(parsed)
            
            # Track provider counts for logging
            prov = parsed.network or 'Unknown'
            provider_counts[prov] = provider_counts.get(prov, 0) + 1

        # Log breakdown by provider
        if provider_counts:
            breakdown = ', '.join(f"{k}:{v}" for k, v in sorted(provider_counts.items()))
            self._log(f"Provider breakdown: {breakdown}")

        return plans

    def _parse_single_card(self, text, url):
        """Extract all fields from a single card's text using structural patterns."""

        # 1. PROVIDER: Try multiple patterns
        provider = None
        
        # Pattern 1: "[Provider] SIM Deal"
        provider_match = re.match(r'^([\w\s]+?)\s+SIM\s+Deal', text)
        if provider_match:
            provider = provider_match.group(1).strip()
        
        # Pattern 2: "[Provider] SIM" at start
        if not provider:
            provider_match = re.match(r'^([\w\s]+?)\s+SIM\b', text)
            if provider_match:
                provider = provider_match.group(1).strip()
        
        # Pattern 3: Look for known network names anywhere in first 100 chars
        if not provider:
            from .unified_base import KNOWN_NETWORKS
            first_part = text[:100]
            for net in KNOWN_NETWORKS:
                if re.search(r'\b' + re.escape(net) + r'\b', first_part, re.IGNORECASE):
                    provider = net
                    break
        
        if not provider or len(provider) > 30:
            return None

        # 2. UNDERLYING NETWORK: "Uses [Network]'s Network"
        underlying = None
        net_match = re.search(r"Uses\s+([\w\s]+?)\s*'s\s+Network", text)
        if net_match:
            underlying = net_match.group(1).strip()

        # 3. PRICE: "£ X . YY a month" (uSwitch splits integer/decimal with spaces)
        #    Handle promo: "£ X . YY a month for N months, then £ A . BB"
        price = None
        regular_price = None

        promo_match = re.search(
            r'£\s*(\d+)\s*\.\s*(\d+)\s*a\s+month\s+for\s+(\d+)\s+months?,\s+then\s+£\s*(\d+)(?:\s*\.\s*(\d+))?',
            text
        )
        if promo_match:
            promo_price = float(promo_match.group(1) + '.' + promo_match.group(2))
            reg_int = promo_match.group(4)
            reg_dec = promo_match.group(5) or '00'
            regular_price = float(reg_int + '.' + reg_dec)
            # Use the regular (post-promo) price for fair comparison
            price = regular_price
        else:
            price_match = re.search(r'£\s*(\d+)\s*\.\s*(\d+)\s*a\s+month', text)
            if price_match:
                price = float(price_match.group(1) + '.' + price_match.group(2))
            else:
                price_match = re.search(r'£\s*(\d+)\s*a\s+month', text)
                if price_match:
                    price = float(price_match.group(1))

        if not price or price < 1 or price > 100:
            return None

        # 4. CONTRACT: "N month contract" or "No contract"
        contract_months = 1
        contract_match = re.search(r'(\d+)\s+month\s+contract', text)
        if contract_match:
            val = int(contract_match.group(1))
            if 1 <= val <= 36:
                contract_months = val
        if 'No contract' in text:
            contract_months = 1

        # 5. DATA: Multiple patterns for data extraction
        data_gb = None
        is_unlimited = False

        # Pattern 1: "N GB of [speed] data"
        data_match = re.search(r'(\d+)\s*GB\s+of\s+\w+\s+data', text)
        if data_match:
            data_gb = int(data_match.group(1))
        
        # Pattern 2: Just "N GB" anywhere
        if not data_gb:
            data_match = re.search(r'(\d+)\s*GB\b', text, re.IGNORECASE)
            if data_match:
                val = int(data_match.group(1))
                if 1 <= val <= 500:  # Reasonable data amount
                    data_gb = val
        
        # Pattern 3: Unlimited data
        if not data_gb:
            if re.search(r'Unlimited\s+\w*\s*data', text, re.IGNORECASE) or re.search(r'Unlimited\s*$', text[:200], re.IGNORECASE):
                is_unlimited = True

        if not data_gb and not is_unlimited:
            return None

        # 6. SPEED
        is_5g = '5G' in text

        # 7. PERKS
        extras = []
        if regular_price and promo_match:
            promo_months = promo_match.group(3)
            promo_price_val = float(promo_match.group(1) + '.' + promo_match.group(2))
            extras.append(f'\u00a3{promo_price_val:.2f}/mo for {promo_months} months')
        if re.search(r'No annual price rise', text):
            extras.append('No price rise')
        if re.search(r'No Credit Check', text):
            extras.append('No credit check')
        roam = re.search(r'Roam up to (\d+GB) in (\d+) destinations', text)
        if roam:
            extras.append(f'Roam {roam.group(1)} in {roam.group(2)} destinations')
        if 'eSIM' in text:
            extras.append('eSIM')

        provider = normalize_network(provider) or provider
        data_label = 'Unlimited' if is_unlimited else f'{data_gb}GB'
        name = f'{provider} {data_label}'

        return ScrapedPlan(
            name=name,
            price=price,
            data_gb=data_gb,
            data_unlimited=is_unlimited,
            is_5g=is_5g,
            url=url,
            contract_months=contract_months,
            network=provider,
            extras=', '.join(extras) if extras else None,
        )
