"""Regex fallback extraction strategy."""

import re
from typing import List, Dict, Any, Optional

from .base import BaseStrategy, ExtractionResult
from ..confidence import ScrapedPlan, calculate_confidence


class RegexStrategy(BaseStrategy):
    name = "regex"
    priority = 0.4
    
    def extract(self, html: str, url: str, config: Dict[str, Any]) -> ExtractionResult:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ")
            
            prices = self._find_prices(text)
            data_values = self._find_data(text)
            
            plans = []
            for i, price in enumerate(prices[:20]):
                data_gb = data_values[i] if i < len(data_values) else None
                data_unlimited = data_gb is None and "unlimited" in text.lower()
                
                plan = ScrapedPlan(
                    name=f"Plan {i+1}",
                    price=price,
                    data_gb=data_gb if not data_unlimited else None,
                    data_unlimited=data_unlimited,
                    contract_months=1,
                    url=url
                )
                calculate_confidence(plan, self.name)
                plans.append(plan)
            
            quality = self._calculate_quality(plans)
            return ExtractionResult(
                strategy_name=self.name,
                plans=plans,
                quality_score=quality,
                success=len(plans) > 0
            )
        except Exception as e:
            return ExtractionResult(strategy_name=self.name, success=False, error=str(e))
    
    def _find_prices(self, text: str) -> List[float]:
        prices = []
        pattern = re.compile(r"[£](\d+(?:\.\d+)?)")
        for match in pattern.finditer(text):
            try:
                price = float(match.group(1))
                if 5 <= price <= 100 and price not in prices:
                    prices.append(price)
            except ValueError:
                continue
        return sorted(set(prices))
    
    def _find_data(self, text: str) -> List[Optional[int]]:
        data_values = []
        pattern = re.compile(r"(\d+)\s*GB", re.IGNORECASE)
        for match in pattern.finditer(text):
            try:
                val = int(match.group(1))
                if 1 <= val <= 500:
                    data_values.append(val)
            except ValueError:
                continue
        return data_values
    
    def _calculate_quality(self, plans: List[ScrapedPlan]) -> float:
        if not plans:
            return 0.0
        avg_score = sum(p.confidence_score for p in plans) / len(plans)
        count_bonus = min(len(plans) / 10, 1.0)
        return round(self.priority * avg_score * (0.7 + 0.3 * count_bonus), 3)
