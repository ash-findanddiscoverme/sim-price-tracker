"""Tests for extraction strategies."""

import pytest
from backend.scrapers.strategies import get_best_result
from backend.scrapers.strategies.json_ld import JsonLdStrategy
from backend.scrapers.strategies.html_parser import HtmlStrategy


class TestJsonLdStrategy:
    def test_extracts_product_from_json_ld(self):
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "http://schema.org",
            "@type": "Product",
            "name": "EE 50GB SIM-only Plan",
            "offers": {
                "@type": "Offer",
                "price": "29.99",
                "priceCurrency": "GBP"
            }
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        strategy = JsonLdStrategy()
        result = strategy.extract(html, "https://ee.co.uk", {})
        
        assert result.success is True
        assert len(result.plans) == 1
        assert result.plans[0].price == 29.99
        assert "EE" in result.plans[0].name


class TestHtmlStrategy:
    def test_extracts_from_plan_cards(self):
        html = """
        <html>
        <body>
        <div class="plan-card">
            <h3 class="plan-name">10GB SIM Only</h3>
            <div class="price">£15.99/mo</div>
            <div class="data">10GB Data</div>
            <div class="contract">12 month contract</div>
            <a href="/plan/1">View Deal</a>
        </div>
        <div class="plan-card">
            <h3 class="plan-name">Unlimited SIM Only</h3>
            <div class="price">£29.99/mo</div>
            <div class="data">Unlimited Data</div>
            <div class="contract">24 month contract</div>
            <a href="/plan/2">View Deal</a>
        </div>
        </body>
        </html>
        """
        strategy = HtmlStrategy()
        result = strategy.extract(html, "https://example.com", {})
        
        # Should find the plan cards
        assert result.success is True
        assert len(result.plans) >= 1


class TestGetBestResult:
    def test_prefers_json_ld_over_html(self):
        # HTML with both JSON-LD and HTML plan cards
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "http://schema.org",
            "@type": "Product",
            "name": "JSON-LD Plan",
            "offers": {
                "@type": "Offer",
                "price": "19.99"
            }
        }
        </script>
        </head>
        <body>
        <div class="plan-card">
            <h3 class="plan-name">HTML Plan</h3>
            <div class="price">£15.99/mo</div>
        </div>
        </body>
        </html>
        """
        result = get_best_result(html, "https://example.com", {})
        
        # Should prefer JSON-LD due to higher priority
        assert result.strategy_name == "json_ld"
