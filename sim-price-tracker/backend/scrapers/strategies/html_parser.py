"""HTML parsing extraction strategy."""

import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, Tag

from .base import BaseStrategy, ExtractionResult
from ..confidence import ScrapedPlan, calculate_confidence


class HtmlStrategy(BaseStrategy):
    """Extract plans from HTML using CSS selectors."""
    
    name = "html"
    priority = 0.7
    
    CARD_SELECTORS = [
        "[class*='plan-card']",
        "[class*='tariff-card']",
        "[class*='deal-card']",
        "[class*='product-card']",
        "[class*='pricing-card']",
        "[class*='offer-card']",
        "[data-component='plan']",
        "[data-testid*='plan']",
        "article[class*='plan']",
        "li[class*='plan']",
    ]
    
    def extract(self, html: str, url: str, config: Dict[str, Any]) -> ExtractionResult:
        """Extract plans from HTML card elements."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            custom_selector = config.get("extraction_hints", {}).get("card_selector")
            selectors = [custom_selector] if custom_selector else self.CARD_SELECTORS
            
            cards = []
            for selector in selectors:
                try:
                    found = soup.select(selector)
                    if found and len(found) > len(cards):
                        cards = found
                except Exception:
                    continue
            
            plans = []
            for card in cards:
                plan = self._parse_card(card, url)
                if plan:
                    plans.append(plan)
            
            for plan in plans:
                calculate_confidence(plan, self.name)
            
            quality = self._calculate_quality(plans)
            
            return ExtractionResult(
                strategy_name=self.name,
                plans=plans,
                quality_score=quality,
                success=len(plans) > 0
            )
        except Exception as e:
            return ExtractionResult(
                strategy_name=self.name,
                success=False,
                error=str(e)
            )
    
    def _parse_card(self, card: Tag, base_url: str) -> Optional[ScrapedPlan]:
        """Parse a card element into a ScrapedPlan."""
        
        name = None
        for sel in ["h1", "h2", "h3", "h4", "[class*='name']", "[class*='title']"]:
            elem = card.select_one(sel)
            if elem:
                name = elem.get_text(strip=True)
                if name:
                    break
        
        price = None
        for sel in ["[class*='price']", "[class*='cost']", "[data-price]"]:
            elem = card.select_one(sel)
            if elem:
                price_text = elem.get("data-price") or elem.get_text(strip=True)
                price = self._parse_price(price_text)
                if price:
                    break
        
        if not price:
            text = card.get_text()
            price = self._parse_price(text)
        
        if not name or price is None:
            return None
        
        data_gb, data_unlimited = None, False
        for sel in ["[class*='data']", "[class*='allowance']"]:
            elem = card.select_one(sel)
            if elem:
                data_gb, data_unlimited = self._parse_data(elem.get_text(strip=True))
                if data_gb or data_unlimited:
                    break
        
        if not data_gb and not data_unlimited:
            data_gb, data_unlimited = self._parse_data(card.get_text())
        
        contract = self._parse_contract(card.get_text())
        
        plan_url = base_url
        link = card.select_one("a[href]")
        if link and link.get("href"):
            href = link["href"]
            if href.startswith("http"):
                plan_url = href
            elif href.startswith("/"):
                from urllib.parse import urljoin
                plan_url = urljoin(base_url, href)
        
        return ScrapedPlan(
            name=name,
            price=price,
            data_gb=data_gb,
            data_unlimited=data_unlimited,
            contract_months=contract,
            url=plan_url
        )
    
    def _calculate_quality(self, plans: List[ScrapedPlan]) -> float:
        if not plans:
            return 0.0
        avg_score = sum(p.confidence_score for p in plans) / len(plans)
        count_bonus = min(len(plans) / 10, 1.0)
        return round(self.priority * avg_score * (0.7 + 0.3 * count_bonus), 3)
