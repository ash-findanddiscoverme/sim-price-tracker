"""Pytest configuration and fixtures."""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def sample_plan_data():
    """Sample plan data for tests."""
    return {
        "name": "Test 10GB Plan",
        "price": 19.99,
        "data_gb": 10,
        "contract_months": 12,
        "url": "https://example.com/plan/1"
    }


@pytest.fixture
def sample_html_with_json_ld():
    """Sample HTML with JSON-LD data."""
    return """
    <html>
    <head>
    <script type="application/ld+json">
    {
        "@context": "http://schema.org",
        "@type": "Product",
        "name": "Test Plan",
        "offers": {
            "@type": "Offer",
            "price": "19.99",
            "priceCurrency": "GBP"
        }
    }
    </script>
    </head>
    <body></body>
    </html>
    """


@pytest.fixture
def sample_html_with_plan_cards():
    """Sample HTML with plan cards."""
    return """
    <html>
    <body>
    <div class="plan-card">
        <h3 class="plan-name">Test Plan 1</h3>
        <div class="price">£15.99/mo</div>
        <div class="data">10GB</div>
    </div>
    <div class="plan-card">
        <h3 class="plan-name">Test Plan 2</h3>
        <div class="price">£25.99/mo</div>
        <div class="data">Unlimited</div>
    </div>
    </body>
    </html>
    """
