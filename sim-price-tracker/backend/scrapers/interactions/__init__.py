"""Page Interaction Engine for advanced web scraping."""

from .types import InteractionType, InteractionStep, InteractionError, InteractionResult
from .interactor import PageInteractor

__all__ = [
    "InteractionType",
    "InteractionStep",
    "InteractionError",
    "InteractionResult",
    "PageInteractor",
]
