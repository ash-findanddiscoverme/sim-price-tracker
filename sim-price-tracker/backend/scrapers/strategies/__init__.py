from .base import BaseStrategy, ExtractionResult
from .json_ld import JsonLdStrategy
from .next_data import NextDataStrategy
from .html_parser import HtmlStrategy
from .regex_fallback import RegexStrategy

ALL_STRATEGIES = [
    JsonLdStrategy(),
    NextDataStrategy(),
    HtmlStrategy(),
    RegexStrategy(),
]

def get_best_result(html, url, config):
    best_result = None
    for strategy in ALL_STRATEGIES:
        result = strategy.extract(html, url, config)
        if result.success and (best_result is None or result.quality_score > best_result.quality_score):
            best_result = result
    if best_result is None:
        return ExtractionResult(strategy_name="none", success=False, error="All strategies failed")
    return best_result
