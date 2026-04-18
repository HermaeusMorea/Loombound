"""C1 core: local qwen2.5:7b scene expansion via ollama."""

from .ollama import C1Config
from .expander import C1Expander

__all__ = ["C1Config", "C1Expander"]
