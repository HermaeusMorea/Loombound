"""C1 logic: Fast Core (gemma3)."""

__all__ = ["FastCoreExpander", "FastCoreConfig"]


def FastCoreExpander(*args, **kwargs):
    from .fast_core import FastCoreExpander as _F
    return _F(*args, **kwargs)


def FastCoreConfig(*args, **kwargs):
    from .fast_core import FastCoreConfig as _F
    return _F(*args, **kwargs)
