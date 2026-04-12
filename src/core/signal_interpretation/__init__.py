"""Signal extraction and theme interpretation stages."""

from .signals import build_signals
from .theme_scorer import score_themes

__all__ = ["build_signals", "score_themes"]
