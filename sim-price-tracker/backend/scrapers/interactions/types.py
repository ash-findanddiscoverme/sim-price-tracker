"""Interaction types and data classes for the page interaction engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Tuple


class InteractionType(Enum):
    """Types of page interactions the crawler can perform."""
    DISMISS_COOKIE = "dismiss_cookie"
    CLICK_LOAD_MORE = "click_load_more"
    INFINITE_SCROLL = "infinite_scroll"
    CLICK_TAB = "click_tab"
    SELECT_FILTER = "select_filter"
    WAIT_FOR_CONTENT = "wait_for_content"
    CLICK_ELEMENT = "click_element"


@dataclass
class InteractionStep:
    """A single interaction step in a sequence."""
    type: InteractionType
    selectors: List[str] = field(default_factory=list)
    timeout: int = 5000
    optional: bool = False
    max_clicks: int = 10
    scroll_count: int = 5
    wait_between: int = 1500
    stop_when_no_new_content: bool = True
    filter_name: str = ""
    values: List[str] = field(default_factory=list)
    iterate_all: bool = False
    extract_after_each: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionStep":
        step_type = InteractionType(data.get("type", "wait_for_content"))
        return cls(
            type=step_type,
            selectors=data.get("selectors", [data.get("selector", "")]),
            timeout=data.get("timeout", 5000),
            optional=data.get("optional", False),
            max_clicks=data.get("max_clicks", 10),
            scroll_count=data.get("scroll_count", 5),
            wait_between=data.get("wait_between", 1500),
            stop_when_no_new_content=data.get("stop_when_no_new_content", True),
            filter_name=data.get("filter_name", ""),
            values=data.get("values", []),
            iterate_all=data.get("iterate_all", False),
            extract_after_each=data.get("extract_after_each", False),
        )


class InteractionError(Exception):
    """Error during page interaction."""
    def __init__(self, interaction_type: str, message: str, recoverable: bool = True):
        self.interaction_type = interaction_type
        self.message = message
        self.recoverable = recoverable
        super().__init__(f"Interaction [{interaction_type}] failed: {message}")


@dataclass
class InteractionResult:
    """Result of executing an interaction sequence."""
    success: bool
    html_snapshots: List[Tuple[str, str]] = field(default_factory=list)
    errors: List[InteractionError] = field(default_factory=list)
    interactions_completed: int = 0
    total_interactions: int = 0
