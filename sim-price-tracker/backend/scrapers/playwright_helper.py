import logging
import asyncio
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

_browser = None
_playwright = None


async def get_browser():
    global _browser, _playwright
    if _browser is None or not _browser.is_connected():
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
    return _browser


async def fetch_page_content(url, wait_ms=8000, selector=None):
    """Fetch a page with Playwright and return HTML content."""
    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if selector:
            try:
                await page.wait_for_selector(selector, timeout=15000)
            except:
                pass
        await page.wait_for_timeout(wait_ms)
        # Try to accept cookies
        for btn_text in ["Accept all", "Accept All", "Accept cookies", "Accept Cookies", "Allow all"]:
            try:
                btn = page.locator(f'button:has-text("{btn_text}")')
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(2000)
                    break
            except:
                pass
        # Scroll to load lazy content
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
        html = await page.content()
        return html
    except Exception as e:
        logger.error(f"Playwright fetch error for {url}: {e}")
        return ""
    finally:
        await page.close()


async def fetch_page_text(url, wait_ms=8000):
    """Fetch a page and return its visible text content."""
    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(wait_ms)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        text = await page.evaluate("() => document.body.innerText || ''")
        return text
    except Exception as e:
        logger.error(f"Playwright text fetch error for {url}: {e}")
        return ""
    finally:
        await page.close()


async def close_browser():
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
