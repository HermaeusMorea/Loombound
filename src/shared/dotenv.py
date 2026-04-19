"""Shared .env loader used by all CLI entry points."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv() -> None:
    """Load KEY=VALUE pairs from .env at repo root into os.environ.

    Uses os.environ.setdefault so existing shell exports are never overwritten.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
