"""Next.js __NEXT_DATA__ extraction strategy."""

import json
import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from .base import BaseStrategy, ExtractionResult
from ..confidence import ScrapedPlan, calculate_confidence


class NextDataStrategy(BaseStrategy):
    """Extract data from Next.js __NEXT_DATA__ script."""
    
    name = "next_data"
    priority = 0.9
    
    def extract(self, html: str, url: str, config: Dict[str, Any]) -> ExtractionResult:
        """Extract plans from Next.js data."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            
            if not script or not script.string:
                return ExtractionResult(
                    strategy_name=self.name,
                    success=False,
                    error="No __NEXT_DATA__ found"
                )
            
            data = json.loads(script.string)
            plans = self._find_plans_in_data(data, url, config)
            
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
    
    def _find_plans_in_data(self, data: Any, url: str, config: Dict) -> List[ScrapedPlan]:
        """Recursively find plan data in Next.js structure."""
        plans = []
        
        if isinstance(data, dict):
            if "props" in data:
                plans.extend(self._find_plans_in_data(data["props"], url, config))
            
            if "pageProps" in data:
                plans.extend(self._find_plans_in_data(data["pageProps"], url, config))
            
            json_path = config.get("extraction_hints", {}).get("json_path", "")
            if json_path:
                plan_list = self._get_by_path(data, json_path)
                if isinstance(plan_list, list):
                    for item in plan_list:
                        plan = self._parse_plan_object(item, url)
                        if plan:
                            plans.append(plan)
            
            for key in ["plans", "tariffs", "deals", "products", "offers", "items"]:
                if key in data:
                    items = data[key]
                    if isinstance(items, list):
                        for item in items:
                            plan = self._parse_plan_object(item, url)
                            if plan:
                                plans.append(plan)
            
            if not plans:
                for value in data.values():
                    if isinstance(value, (dict, list)):
                        plans.extend(self._find_plans_in_data(value, url, config))
                        if len(plans) > 5:
                            break
        
        elif isinstance(data, list):
            for item in data:
                plans.extend(self._find_plans_in_data(item, url, config))
        
        return plans
    
    def _get_by_path(self, data: Dict, path: str) -> Any:
        """Get value by dot notation path."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
    
    def _parse_plan_object(self, obj: Dict, url: str) -> ScrapedPlan or None:
        """Parse a plan object into ScrapedPlan."""
        if not isinstance(obj, dict):
            return None
        
        name = obj.get("name") or obj.get("title") or obj.get("planName") or ""
        
        price = None
        for key in ["price", "monthlyPrice", "pricePerMonth", "cost"]:
            if key in obj:
                try:
                    price = float(obj[key])
                    break
                except (ValueError, TypeError):
                    price = self._parse_price(str(obj[key]))
                    if price:
                        break
        
        if not name or price is None:
            return None
        
        data_gb = None
        data_unlimited = False
        for key in ["data", "dataGB", "dataAllowance", "dataAmount"]:
            if key in obj:
                data_val = obj[key]
                if isinstance(data_val, (int, float)):
                    data_gb = int(data_val)
                elif isinstance(data_val, str):
                    data_gb, data_unlimited = self._parse_data(data_val)
                break
        
        contract = 1
        for key in ["contractLength", "contractMonths", "duration", "term"]:
            if key in obj:
                try:
                    contract = int(obj[key])
                    break
                except (ValueError, TypeError):
                    contract = self._parse_contract(str(obj[key]))
                    break
        
        return ScrapedPlan(
            name=name,
            price=price,
            data_gb=data_gb,
            data_unlimited=data_unlimited,
            contract_months=contract,
            url=obj.get("url", url)
        )
    
    def _calculate_quality(self, plans: List[ScrapedPlan]) -> float:
        if not plans:
            return 0.0
        avg_score = sum(p.confidence_score for p in plans) / len(plans)
        count_bonus = min(len(plans) / 10, 1.0)
        return round(self.priority * avg_score * (0.7 + 0.3 * count_bonus), 3)
