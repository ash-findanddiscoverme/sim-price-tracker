"""Confidence scoring for extracted plans."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict


STRATEGY_SCORES = {
    "json_ld": 1.0,
    "next_data": 0.9,
    "html": 0.7,
    "regex": 0.4,
    "mixed": 0.5,
}


@dataclass
class ScrapedPlan:
    """Core plan data with confidence scoring."""
    name: str
    price: float
    data_gb: Optional[int] = None
    data_unlimited: bool = False
    contract_months: int = 1
    url: str = ""
    network: Optional[str] = None
    
    confidence_score: float = 0.0
    confidence_reasons: List[str] = field(default_factory=list)
    extraction_strategy: str = ""
    needs_verification: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "price": self.price,
            "data_gb": self.data_gb,
            "data_unlimited": self.data_unlimited,
            "contract_months": self.contract_months,
            "url": self.url,
            "network": self.network,
            "confidence_score": self.confidence_score,
            "confidence_reasons": self.confidence_reasons,
            "extraction_strategy": self.extraction_strategy,
            "needs_verification": self.needs_verification,
        }


def calculate_confidence(
    plan: ScrapedPlan,
    strategy_name: str,
    field_sources: Optional[Dict[str, str]] = None
) -> float:
    """Calculate confidence score based on extraction quality."""
    score = 1.0
    reasons = []
    
    base = STRATEGY_SCORES.get(strategy_name, 0.5)
    score *= base
    reasons.append(f"strategy:{strategy_name}={base}")
    
    missing = []
    if not plan.name or plan.name == "Unknown":
        missing.append("name")
    if plan.price <= 0:
        missing.append("price")
    if plan.data_gb is None and not plan.data_unlimited:
        missing.append("data")
    if plan.contract_months <= 0:
        missing.append("contract")
    
    completeness = (4 - len(missing)) / 4
    score *= completeness
    if missing:
        reasons.append(f"missing:{missing}")
    
    plausibility = 1.0
    if plan.price < 5 or plan.price > 100:
        plausibility *= 0.7
        reasons.append(f"unusual_price:{plan.price}")
    if plan.data_gb and (plan.data_gb < 1 or plan.data_gb > 500):
        plausibility *= 0.7
        reasons.append(f"unusual_data:{plan.data_gb}GB")
    if plan.contract_months not in [1, 12, 18, 24, 36]:
        plausibility *= 0.8
        reasons.append(f"unusual_contract:{plan.contract_months}mo")
    score *= plausibility
    
    generic_names = ["plan", "sim", "deal", "offer", "unknown", ""]
    if plan.name.lower().strip() in generic_names:
        score *= 0.6
        reasons.append("generic_name")
    
    plan.confidence_score = round(min(score, 1.0), 2)
    plan.confidence_reasons = reasons
    plan.extraction_strategy = strategy_name
    plan.needs_verification = plan.confidence_score < 0.7
    
    return plan.confidence_score


def calculate_quality_factor(plans: List[ScrapedPlan]) -> float:
    """Calculate quality factor for a set of plans."""
    if not plans:
        return 0.0
    
    score = 1.0
    
    prices = [p.price for p in plans]
    unique_prices = len(set(prices))
    if len(prices) > 1 and unique_prices == 1:
        score *= 0.5
    
    with_network = sum(1 for p in plans if p.network)
    network_ratio = with_network / len(plans)
    score *= (0.7 + 0.3 * network_ratio)
    
    keys = [(p.price, p.data_gb, p.data_unlimited) for p in plans]
    unique_ratio = len(set(keys)) / len(keys)
    score *= (0.5 + 0.5 * unique_ratio)
    
    return round(score, 3)
