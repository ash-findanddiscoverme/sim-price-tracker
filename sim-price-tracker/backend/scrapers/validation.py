"""Validation pipeline for core plan fields."""

from typing import List, Tuple, Optional
from dataclasses import dataclass

from .confidence import ScrapedPlan


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]
    

def validate_plan(plan: ScrapedPlan) -> ValidationResult:
    """Validate a single plan for data quality."""
    errors = []
    warnings = []
    
    if not plan.name or plan.name.lower() in ["unknown", "", "plan"]:
        errors.append("missing_or_generic_name")
    elif len(plan.name) < 3:
        warnings.append("short_name")
    
    if plan.price is None or plan.price <= 0:
        errors.append("invalid_price")
    elif plan.price < 5:
        warnings.append("very_low_price")
    elif plan.price > 80:
        warnings.append("high_price")
    
    if plan.data_gb is None and not plan.data_unlimited:
        warnings.append("missing_data")
    elif plan.data_gb is not None:
        if plan.data_gb < 1:
            errors.append("invalid_data")
        elif plan.data_gb > 300:
            warnings.append("unusually_high_data")
    
    if plan.contract_months <= 0:
        errors.append("invalid_contract")
    elif plan.contract_months not in [1, 12, 18, 24, 36]:
        warnings.append("unusual_contract_length")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_plans(plans: List[ScrapedPlan]) -> Tuple[List[ScrapedPlan], List[ScrapedPlan]]:
    """Validate a list of plans. Returns (valid_plans, invalid_plans)."""
    valid = []
    invalid = []
    
    for plan in plans:
        result = validate_plan(plan)
        if result.valid:
            if result.warnings:
                plan.confidence_reasons.extend([f"warning:{w}" for w in result.warnings])
                plan.confidence_score *= 0.9
            valid.append(plan)
        else:
            plan.confidence_reasons.extend([f"error:{e}" for e in result.errors])
            plan.confidence_score = 0.0
            plan.needs_verification = True
            invalid.append(plan)
    
    return valid, invalid


def sanitize_plan(plan: ScrapedPlan) -> ScrapedPlan:
    """Sanitize plan fields to ensure consistency."""
    plan.name = (" ".join(plan.name.split())).strip()
    
    if plan.price:
        plan.price = round(plan.price, 2)
    
    if plan.data_gb and plan.data_gb >= 999 and not plan.data_unlimited:
        plan.data_unlimited = True
        plan.data_gb = None
    
    if plan.contract_months <= 0:
        plan.contract_months = 1
    
    return plan
