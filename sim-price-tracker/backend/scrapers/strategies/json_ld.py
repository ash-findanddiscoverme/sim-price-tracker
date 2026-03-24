"""JSON-LD extraction strategy - highest reliability."""

import json
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from .base import BaseStrategy, ExtractionResult
from ..confidence import ScrapedPlan, calculate_confidence


class JsonLdStrategy(BaseStrategy):
    """Extract data from JSON-LD script tags."""
    
    name = "json_ld"
    priority = 1.0
    
    def extract(self, html: str, url: str, config: Dict[str, Any]) -> ExtractionResult:
        """Extract plans from JSON-LD data."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            scripts = soup.find_all("script", type="application/ld+json")
            
            plans = []
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    plans.extend(self._parse_json_ld(data, url))
                except json.JSONDecodeError:
                    continue
            
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
    
    def _parse_json_ld(self, data: Dict, url: str) -> List[ScrapedPlan]:
        """Parse plans from JSON-LD data."""
        plans = []
        
        if isinstance(data, list):
            for item in data:
                plans.extend(self._parse_json_ld(item, url))
            return plans
        
        if not isinstance(data, dict):
            return plans
        
        item_type = data.get("@type", "")
        
        if item_type in ["Product", "Offer", "Service"]:
            plan = self._parse_product(data, url)
            if plan:
                plans.append(plan)
        
        if "@graph" in data:
            for item in data["@graph"]:
                plans.extend(self._parse_json_ld(item, url))
        
        if "itemListElement" in data:
            for item in data["itemListElement"]:
                plans.extend(self._parse_json_ld(item, url))
        
        return plans
    
    def _parse_product(self, data: Dict, url: str) -> ScrapedPlan or None:
        """Parse a single product into a ScrapedPlan."""
        name = data.get("name", "")
        
        price = None
        offers = data.get("offers", {})
        if isinstance(offers, list) and offers:
            offers = offers[0]
        
        if isinstance(offers, dict):
            price_val = offers.get("price") or offers.get("lowPrice")
            if price_val:
                try:
                    price = float(price_val)
                except (ValueError, TypeError):
                    price = self._parse_price(str(price_val))
        
        if not name or price is None:
            return None
        
        data_gb, data_unlimited = self._parse_data(name)
        contract = self._parse_contract(name)
        
        return ScrapedPlan(
            name=name,
            price=price,
            data_gb=data_gb,
            data_unlimited=data_unlimited,
            contract_months=contract,
            url=data.get("url", url)
        )
    
    def _calculate_quality(self, plans: List[ScrapedPlan]) -> float:
        """Calculate overall quality score."""
        if not plans:
            return 0.0
        
        avg_score = sum(p.confidence_score for p in plans) / len(plans)
        count_bonus = min(len(plans) / 10, 1.0)
        
        return round(self.priority * avg_score * (0.7 + 0.3 * count_bonus), 3)
