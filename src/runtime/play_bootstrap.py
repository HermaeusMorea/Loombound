"""Bootstrap helpers for the play CLI: argument parsing and prefetch setup."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from src.shared.llm_utils import REPO_ROOT
from src.t1.core import C1Config
from src.t2.core import M2DecisionEngine, M2DecisionConfig, PrefetchCache
from src.runtime.saga_loader import LoadedSagaBundle


def parse_play_args() -> argparse.Namespace:
    """Parse CLI arguments, discover saga if not provided, check API key, configure logging.

    Calls sys.exit(1) on unrecoverable startup errors.
    """
    parser = argparse.ArgumentParser(
        description="Play a Loombound saga. Requires ANTHROPIC_API_KEY and ollama (qwen2.5:7b)."
    )
    parser.add_argument("--saga", type=Path, default=None, help="Path to a saga JSON file.")
    parser.add_argument(
        "--nodes", type=int, default=None, metavar="N",
        help="Maximum number of nodes to play (default: unlimited).",
    )
    parser.add_argument(
        "--lang", choices=["en", "zh"], default="en",
        help="Generated content language (default: en).",
    )
    parser.add_argument(
        "--fast",
        dest="fast_model",
        default=None,
        metavar="MODEL",
        help="Fast Core ollama model for text expansion (default: qwen2.5:7b). "
             "Can also be set via FAST_CORE_MODEL env var.",
    )
    args = parser.parse_args()

    if args.saga is None:
        sagas_dir = REPO_ROOT / "data" / "sagas"
        candidates = sorted(
            [p for p in sagas_dir.glob("*.json")
             if not p.stem.endswith(("_toll_lexicon", "_rules", "_narration_table"))],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ) if sagas_dir.exists() else []
        if not candidates:
            print(
                "No saga found. Generate one first:\n"
                "\n"
                "  ./loombound gen \"your theme\"\n"
                "\n"
                "Requires ANTHROPIC_API_KEY in .env.\n"
                "\n"
                "  cp .env.example .env   # then fill in ANTHROPIC_API_KEY",
                file=sys.stderr,
            )
            sys.exit(1)
        args.saga = candidates[0]
        print(f"No --saga specified. Using most recent: {candidates[0].stem}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: ANTHROPIC_API_KEY is not set.\n"
            "Loombound requires a Claude API key to run.\n"
            "Set it in .env: ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="\033[2m[%(levelname)s %(name)s] %(message)s\033[0m",
    )

    return args


def build_prefetch_cache(
    bundle: LoadedSagaBundle,
    api_key: str,
    lang: str,
    fast_model: str,
    tone: str | None,
) -> PrefetchCache:
    """Assemble M2DecisionEngine (if arc catalog present) and PrefetchCache."""
    fast_cfg = C1Config(model=fast_model, lang=lang, tone=tone)

    m2_engine: M2DecisionEngine | None = None
    if bundle.tables.arc_state_catalog:
        m2_cfg = M2DecisionConfig(api_key=api_key)
        m2_engine = M2DecisionEngine(cfg=m2_cfg, **bundle.m2_engine_args())

    prefetch = PrefetchCache(fast_cfg=fast_cfg, lang=lang, m2_engine=m2_engine)
    return prefetch
