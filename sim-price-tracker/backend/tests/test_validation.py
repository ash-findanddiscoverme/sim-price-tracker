"""Tests for validation module."""

import pytest
from backend.scrapers.confidence import ScrapedPlan
from backend.scrapers.validation import validate_plan, validate_plans, sanitize_plan


class TestValidatePlan:
    def test_valid_plan(self):
        plan = ScrapedPlan(
            name="EE 20GB Plan",
            price=19.99,
            data_gb=20,
            contract_months=12,
            url="https://ee.co.uk/plan"
        )
        result = validate_plan(plan)
        
        assert result.valid is True
        assert len(result.errors) == 0
    
    def test_missing_name(self):
        plan = ScrapedPlan(
            name="",
            price=19.99,
            data_gb=20,
            contract_months=12,
            url="https://example.com"
        )
        result = validate_plan(plan)
        
        assert result.valid is False
        assert "missing_or_generic_name" in result.errors
    
    def test_invalid_price(self):
        plan = ScrapedPlan(
            name="Test Plan",
            price=0,
            data_gb=10,
            contract_months=12,
            url="https://example.com"
        )
        result = validate_plan(plan)
        
        assert result.valid is False
        assert "invalid_price" in result.errors
    
    def test_high_price_warning(self):
        plan = ScrapedPlan(
            name="Premium Plan",
            price=99.99,
            data_gb=100,
            contract_months=24,
            url="https://example.com"
        )
        result = validate_plan(plan)
        
        assert result.valid is True  # Still valid
        assert "high_price" in result.warnings  # But warned
    
    def test_unlimited_data_valid(self):
        plan = ScrapedPlan(
            name="Unlimited Plan",
            price=29.99,
            data_unlimited=True,
            contract_months=12,
            url="https://example.com"
        )
        result = validate_plan(plan)
        
        assert result.valid is True
        assert "missing_data_info" not in result.warnings


class TestValidatePlans:
    def test_separates_valid_and_invalid(self):
        plans = [
            ScrapedPlan(name="Valid Plan", price=19.99, data_gb=10, contract_months=12, url="url"),
            ScrapedPlan(name="", price=19.99, data_gb=10, contract_months=12, url="url"),  # Invalid
            ScrapedPlan(name="Another Valid", price=25.00, data_gb=20, contract_months=24, url="url"),
        ]
        
        valid, invalid = validate_plans(plans)
        
        assert len(valid) == 2
        assert len(invalid) == 1


class TestSanitizePlan:
    def test_trims_whitespace(self):
        plan = ScrapedPlan(
            name="  Test  Plan  ",
            price=19.99,
            data_gb=10,
            contract_months=12,
            url="https://example.com"
        )
        sanitized = sanitize_plan(plan)
        
        assert sanitized.name == "Test Plan"
    
    def test_rounds_price(self):
        plan = ScrapedPlan(
            name="Test Plan",
            price=19.99999,
            data_gb=10,
            contract_months=12,
            url="https://example.com"
        )
        sanitized = sanitize_plan(plan)
        
        assert sanitized.price == 20.00
    
    def test_converts_high_data_to_unlimited(self):
        plan = ScrapedPlan(
            name="Unlimited Plan",
            price=29.99,
            data_gb=9999,  # Very high value often means unlimited
            data_unlimited=False,
            contract_months=12,
            url="https://example.com"
        )
        sanitized = sanitize_plan(plan)
        
        assert sanitized.data_unlimited is True
        assert sanitized.data_gb is None
