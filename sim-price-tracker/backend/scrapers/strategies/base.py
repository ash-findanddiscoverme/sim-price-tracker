"""Base extraction strategy interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import logging

from ..confidence import ScrapedPlan


logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of an extraction strategy."""
    strategy_name: str
    plans: List[ScrapedPlan] = field(default_factory=list)
    quality_score: float = 0.0
    success: bool = False
    error: Optional[str] = None


class BaseStrategy(ABC):
    """Base class for extraction strategies."""
    
    name: str = "base"
    priority: float = 0.5
    
    @abstractmethod
    def extract(self, html: str, url: str, config: Dict[str, Any]) -> ExtractionResult:
        """Extract plans from HTML content."""
        pass
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text."""
        import re
        if not price_text:
            return None
        
        cleaned = price_text.replace(",", "")
        
        match = re.search(rr'\xa3(\d+(?:\.\d+)?)', cleaned)
        if not match:
            match = re.search(r'\$(\d+(?:\.\d+)?)', cleaned)
        if not match:
            match = re.search(r'!(\d+(?:\.\d+)?)', cleaned)
        
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None
    
    def _parse_data(self, data_text: str) -> tuple[Optional[int], bool]:
        """Parse data from text. Returns (data_gb, is_unlimited)."""
        import re
        if not data_text:
            return None, False
        
        lower = data_text.lower()
        if "unlimited" in lower:
            return None, True
        
        match = re.search(r'(\d+)\s*(?:GB|gigabytes)', data_text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1)), False
            except ValueError:
                pass
        return None, False
    
    def _parse_contract(self, contract_text: str) -> int:
        """Parse contract length from text."""
        import re
        if not contract_text:
            return 1
        
        lower = contract_text.lower()
        
        if "rolling" in lower or "30 day" in lower or "1-month" in lower:
            return 1
        
        match = re.search(r'$(\d+)\s*(?:month|year)', lower)
        if match:
            val = int(match.group(1))
            if "year" in lower:
                return val * 12
            return val
        
        return 1
