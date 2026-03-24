"""Page Interactor for executing interaction sequences on web pages."""

import asyncio
from typing import Callable, List, Tuple, Optional, Dict, Any
from playwright.async_api import Page

from .types import InteractionType, InteractionStep, InteractionError, InteractionResult


class PageInteractor:
    """Executes interaction sequences on pages to reveal dynamic content."""
    
    def __init__(
        self, 
        page: Page, 
        config: Dict[str, Any], 
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.page = page
        self.config = config
        self._log_cb = log_callback or (lambda msg: None)
        self.content_snapshots: List[Tuple[str, str]] = []
    
    def _log(self, message: str):
        """Log a message via the callback."""
        self._log_cb(f"[Interactor] {message}")
    
    def _get_sequence(self, provider_slug: str) -> List[InteractionStep]:
        """Get interaction sequence for a provider, with defaults applied."""
        default_seq = self.config.get("default_sequence", [])
        overrides = self.config.get("provider_overrides", {}).get(provider_slug, [])
        
        sequence = [InteractionStep.from_dict(s) if isinstance(s, dict) else s for s in default_seq]
        sequence.extend([InteractionStep.from_dict(s) if isinstance(s, dict) else s for s in overrides])
        
        return sequence
    
    async def execute_sequence(self, provider_slug: str) -> InteractionResult:
        """
        Execute interactions and return HTML snapshots.
        
        For filter iteration with extract_after_each=True, returns multiple snapshots
        (one per filter value) for separate extraction.
        """
        sequence = self._get_sequence(provider_slug)
        snapshots: List[Tuple[str, str]] = []
        errors: List[InteractionError] = []
        completed = 0
        
        self._log(f"Executing {len(sequence)} interaction steps for {provider_slug}")
        
        for step in sequence:
            try:
                if step.type == InteractionType.DISMISS_COOKIE:
                    await self._dismiss_cookie(step)
                elif step.type == InteractionType.WAIT_FOR_CONTENT:
                    await self._wait_for_content(step)
                elif step.type == InteractionType.CLICK_LOAD_MORE:
                    await self._click_load_more(step)
                elif step.type == InteractionType.INFINITE_SCROLL:
                    await self._infinite_scroll(step)
                elif step.type == InteractionType.CLICK_TAB:
                    await self._click_tab(step)
                elif step.type == InteractionType.SELECT_FILTER:
                    if step.extract_after_each:
                        filter_snaps = await self._iterate_filter_with_extraction(step)
                        snapshots.extend(filter_snaps)
                    else:
                        await self._select_filter(step)
                elif step.type == InteractionType.CLICK_ELEMENT:
                    await self._click_element(step)
                
                completed += 1
                
            except Exception as e:
                error = InteractionError(step.type.value, str(e), recoverable=step.optional)
                errors.append(error)
                
                if not step.optional:
                    self._log(f"Fatal error in {step.type.value}: {e}")
                    break
                else:
                    self._log(f"Optional step {step.type.value} failed: {e}")
        
        if not snapshots:
            html = await self.page.content()
            snapshots.append(("final", html))
        
        return InteractionResult(
            success=len(errors) == 0 or all(e.recoverable for e in errors),
            html_snapshots=snapshots,
            errors=errors,
            interactions_completed=completed,
            total_interactions=len(sequence)
        )
    
    async def _dismiss_cookie(self, step: InteractionStep):
        """Try multiple cookie banner selectors."""
        for selector in step.selectors:
            if not selector:
                continue
            try:
                btn = await self.page.wait_for_selector(selector, timeout=step.timeout)
                if btn:
                    await btn.click()
                    self._log("Cookie banner dismissed")
                    await self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        self._log("No cookie banner found")
    
    async def _wait_for_content(self, step: InteractionStep):
        """Wait for content to load."""
        selector = step.selectors[0] if step.selectors else "body"
        await self.page.wait_for_selector(selector, timeout=step.timeout)
        self._log(f"Content loaded: {selector}")

    async def _click_load_more(self, step: InteractionStep):
        """Click load more button until exhausted or max clicks reached."""
        clicks = 0
        
        while clicks < step.max_clicks:
            clicked = False
            for selector in step.selectors:
                if not selector:
                    continue
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        self._log(f"Clicked load more ({clicks + 1})")
                        await self.page.wait_for_timeout(step.wait_between)
                        clicks += 1
                        clicked = True
                        break
                except Exception:
                    continue
            
            if not clicked:
                self._log(f"No more load buttons after {clicks} clicks")
                break
    
    async def _infinite_scroll(self, step: InteractionStep):
        """Scroll to load lazy-loaded content."""
        last_height = 0
        scroll_count = 0
        
        while scroll_count < step.scroll_count:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.page.wait_for_timeout(step.wait_between)
            
            new_height = await self.page.evaluate("document.body.scrollHeight")
            scroll_count += 1
            
            if step.stop_when_no_new_content and new_height == last_height:
                self._log(f"Scroll stopped - no new content after {scroll_count} scrolls")
                break
            
            last_height = new_height
            self._log(f"Scrolled ({scroll_count}/{step.scroll_count})")
    
    async def _click_tab(self, step: InteractionStep):
        """Click a tab element."""
        for selector in step.selectors:
            if not selector:
                continue
            try:
                tab = await self.page.query_selector(selector)
                if tab:
                    await tab.click()
                    self._log(f"Clicked tab: {selector}")
                    await self.page.wait_for_timeout(1000)
                    return
            except Exception:
                continue
        raise InteractionError("click_tab", "No tab found")
    
    async def _select_filter(self, step: InteractionStep):
        """Select a filter value."""
        if not step.values:
            return
        
        value = step.values[0]
        await self._apply_filter_value(step.filter_name, value)
    
    async def _click_element(self, step: InteractionStep):
        """Click a generic element."""
        for selector in step.selectors:
            if not selector:
                continue
            try:
                elem = await self.page.query_selector(selector)
                if elem and await elem.is_visible():
                    await elem.click()
                    self._log(f"Clicked: {selector}")
                    await self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    async def _iterate_filter_with_extraction(self, step: InteractionStep) -> List[Tuple[str, str]]:
        """
        Iterate through filter values and extract content after each.
        Returns list of (filter_value, html_content) tuples.
        """
        snapshots: List[Tuple[str, str]] = []
        
        for value in step.values:
            self._log(f"Selecting filter: {step.filter_name} = {value}")
            
            try:
                await self._apply_filter_value(step.filter_name, value)
                
                await self.page.wait_for_timeout(2000)
                
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                
                html = await self.page.content()
                snapshots.append((value, html))
                self._log(f"Captured {len(html)} chars for filter: {value}")
                
            except Exception as e:
                self._log(f"Failed to select filter {value}: {e}")
                continue
        
        return snapshots
    
    async def _apply_filter_value(self, filter_name: str, value: str):
        """Apply a filter value using various methods."""
        
        select_selectors = [
            f"select[name*='{filter_name}']",
            f"select[data-filter='{filter_name}']",
            f"select[id*='{filter_name}']",
        ]
        
        for selector in select_selectors:
            try:
                select = await self.page.query_selector(selector)
                if select:
                    await select.select_option(label=value)
                    self._log(f"Selected {value} from dropdown")
                    return
            except Exception:
                continue
        
        click_selectors = [
            f"[data-value='{value}']",
            f"[data-value='{value.lower()}']",
            f"label:has-text('{value}')",
            f"button:has-text('{value}')",
            f"[role='option']:has-text('{value}')",
            f"[data-filter-option='{value.lower()}']",
        ]
        
        for selector in click_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn:
                    await btn.click()
                    self._log(f"Clicked filter: {value}")
                    return
            except Exception:
                continue
        
        self._log(f"Could not find filter element for: {value}")
    
    async def apply_filter(self, filter_selector: str, value: str):
        """Public method to apply a specific filter."""
        await self._apply_filter_value(filter_selector, value)
