"""Tests for confidence scoring."""

import pytest
from backend.scrapers.confidence import ScrapedPlan, calculate_confidence


class TestScrapedPlan:
    def test_create_plan(self):
        plan = ScrapedPlan(
            name="Test Plan",
            price=19.99,
            data_gb=10,
            contract_months=12,
            url="https://example.com"
        )
        assert plan.name == "Test Plan"
        assert plan.price == 19.99
        assert plan.data_gb == 10
        assert plan.contract_months == 12
    
    def test_unlimited_data(self):
        plan = ScrapedPlan(
            name="Unlimited Plan",
            price=29.99,
            data_unlimited=True,
            contract_months=24,
            url="https://example.com"
        )
        assert plan.data_unlimited is True
        assert plan.data_gb is None


class TestConfidenceCalculation:
    def test_high_confidence_plan(self):
        plan = ScrapedPlan(
            name="EE 20GB Plan",
            price=19.99,
            data_gb=20,
            contract_months=12,
            url="https://ee.co.uk/plan"
        )
        score = calculate_confidence(plan, "json_ld")
        
        assert score >= 0.8  # High confidence for complete data from JSON-LD
        assert plan.needs_verification is False
    
    def test_low_confidence_regex(self):
        plan = ScrapedPlan(
            name="Plan 1",
            price=15.00,
            data_gb=5,
            contract_months=1,
            url="https://example.com"
        )
        score = calculate_confidence(plan, "regex")
        
        assert score < 0.7  # Lower confidence for regex extraction
        assert plan.needs_verification is True
    
    def test_missing_data_reduces_confidence(self):
        plan = ScrapedPlan(
            name="Test Plan",
            price=20.00,
            # No data_gb or data_unlimited
            contract_months=12,
            url="https://example.com"
        )
        score = calculate_confidence(plan, "html")
        
        # Should be penalized for missing data
        assert "missing" in str(plan.confidence_reasons).lower()
    
    def test_unusual_price_reduces_confidence(self):
        plan = ScrapedPlan(
            name="Test Plan",
            price=200.00,  # Unusually high
            data_gb=100,
            contract_months=12,
            url="https://example.com"
        )
        score = calculate_confidence(plan, "html")
        
        assert "unusual_price" in str(plan.confidence_reasons).lower()
    
    def test_generic_name_reduces_confidence(self):
        plan = ScrapedPlan(
            name="Plan",  # Generic
            price=19.99,
            data_gb=10,
            contract_months=12,
            url="https://example.com"
        )
        score = calculate_confidence(plan, "html")
        
        assert "generic_name" in str(plan.confidence_reasons).lower()
