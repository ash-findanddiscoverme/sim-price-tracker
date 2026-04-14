"""Playwright browser pool for context reuse."""

import asyncio
from typing import Optional, Callable
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


class BrowserPool:
    """Manages a pool of Playwright browser contexts for efficient reuse."""
    
    def __init__(
        self, 
        max_contexts: int = 3,
        headless: bool = True,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.max_contexts = max_contexts
        self.headless = headless
        self._log_cb = log_callback or (lambda msg: None)
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: asyncio.Queue[BrowserContext] = asyncio.Queue(maxsize=max_contexts)
        self._initialized = False
        self._lock = asyncio.Lock()
    
    def _log(self, message: str):
        self._log_cb(f"[BrowserPool] {message}")

    async def _launch_browser(self):
        """
        Launch browser with fallback chain:
        1. Try system Edge (common on corporate Windows)
        2. Try system Chrome
        3. Fall back to Chromium (requires download)
        """
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ]

        # Try Microsoft Edge first (installed on most corporate Windows)
        try:
            browser = await self._playwright.chromium.launch(
                headless=self.headless,
                channel='msedge',
                args=launch_args,
            )
            self._log("Using system Edge browser")
            return browser
        except Exception:
            pass

        # Try Chrome next
        try:
            browser = await self._playwright.chromium.launch(
                headless=self.headless,
                channel='chrome',
                args=launch_args,
            )
            self._log("Using system Chrome browser")
            return browser
        except Exception:
            pass

        # Fall back to Chromium (requires playwright install chromium)
        try:
            browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=launch_args,
            )
            self._log("Using Playwright Chromium")
            return browser
        except Exception as e:
            self._log(f"No browser available: {e}. Try: playwright install chromium OR use system Chrome/Edge")
            raise
    
    async def initialize(self):
        """Initialize the browser and context pool."""
        async with self._lock:
            if self._initialized:
                return
            
            self._log("Initializing browser pool")
            
            self._playwright = await async_playwright().start()
            self._browser = await self._launch_browser()
            
            for i in range(self.max_contexts):
                context = await self._create_context()
                await self._contexts.put(context)
            
            self._initialized = True
            self._log(f"Browser pool ready with {self.max_contexts} contexts")
    
    async def _create_context(self) -> BrowserContext:
        """Create a new browser context with appropriate settings."""
        return await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-GB",
            timezone_id="Europe/London",
        )
    
    async def get_page(self) -> Page:
        """Get a page from an available context."""
        if not self._initialized:
            await self.initialize()
        
        context = await self._contexts.get()
        page = await context.new_page()
        return page
    
    async def release_page(self, page: Page):
        """Release a page back to the pool."""
        context = page.context
        
        try:
            await page.close()
        except Exception:
            pass
        
        await self._contexts.put(context)
    
    @asynccontextmanager
    async def page(self):
        """Context manager for getting and releasing a page."""
        page = await self.get_page()
        try:
            yield page
        finally:
            await self.release_page(page)
    
    async def close(self):
        """Close all contexts and the browser."""
        async with self._lock:
            if not self._initialized:
                return
            
            self._log("Closing browser pool")
            
            while not self._contexts.empty():
                try:
                    context = await asyncio.wait_for(self._contexts.get(), timeout=1.0)
                    await context.close()
                except asyncio.TimeoutError:
                    break
                except Exception:
                    pass
            
            if self._browser:
                await self._browser.close()
            
            if self._playwright:
                await self._playwright.stop()
            
            self._initialized = False
            self._log("Browser pool closed")
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


_pool_instance: Optional[BrowserPool] = None


async def get_browser_pool(
    max_contexts: int = 3,
    headless: bool = True,
    log_callback: Optional[Callable[[str], None]] = None
) -> BrowserPool:
    """Get or create the global browser pool instance."""
    global _pool_instance
    
    if _pool_instance is None:
        _pool_instance = BrowserPool(max_contexts, headless, log_callback)
        await _pool_instance.initialize()
    
    return _pool_instance


async def close_browser_pool():
    """Close the global browser pool."""
    global _pool_instance
    
    if _pool_instance is not None:
        await _pool_instance.close()
        _pool_instance = None
