"""Outcome labelling and soft sanity penalty handling."""

from .effects import apply_option_effects
from .enforcement import enforce_rule

__all__ = ["enforce_rule", "apply_option_effects"]
