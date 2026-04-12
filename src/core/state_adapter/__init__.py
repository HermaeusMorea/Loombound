"""Adapters that normalize external inputs into deterministic kernel context."""

from .context_builder import load_arbitration, load_json_asset

__all__ = ["load_arbitration", "load_json_asset"]
