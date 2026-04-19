"""Saga artifact lifecycle: resolution, enumeration, and removal."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from src.shared.llm_utils import REPO_ROOT

DATA_DIR      = REPO_ROOT / "data"
SAGAS_DIR     = DATA_DIR / "sagas"
WAYPOINTS_DIR = DATA_DIR / "waypoints"

_SAGA_SUFFIXES = ("_rules.json", "_toll_lexicon.json", "_narration_table.json")


def resolve_saga_ref(id_or_path: str) -> Path:
    """Resolve a saga ID, relative path, or absolute path to a .json Path."""
    p = Path(id_or_path)
    if p.is_absolute() or id_or_path.startswith("./"):
        return p
    if id_or_path.startswith("data/sagas/"):
        return REPO_ROOT / id_or_path
    if p.exists():
        return p.resolve()
    stem = p.stem if p.suffix == ".json" else id_or_path
    return SAGAS_DIR / f"{stem}.json"


def iter_saga_artifacts(saga_file: Path) -> Iterator[Path]:
    """Yield all artifacts related to saga_file (not saga_file itself).

    Yields related JSON sidecars and the waypoints directory if they exist.
    """
    stem = saga_file.stem
    for suffix in _SAGA_SUFFIXES:
        p = SAGAS_DIR / f"{stem}{suffix}"
        if p.exists():
            yield p
    waypoints = WAYPOINTS_DIR / stem
    if waypoints.exists():
        yield waypoints


def is_git_tracked(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def remove_saga_artifacts(saga_file: Path) -> list[str]:
    """Remove saga_file and all related artifacts. Returns display strings of what was removed."""
    removed: list[str] = []
    if saga_file.exists():
        saga_file.unlink()
        removed.append(str(saga_file))
    for artifact in iter_saga_artifacts(saga_file):
        if artifact.is_dir():
            shutil.rmtree(artifact)
            removed.append(f"{artifact}/")
        else:
            artifact.unlink()
            removed.append(str(artifact))
    return removed


def clean_all_saga_data() -> tuple[list[str], list[str]]:
    """Remove all untracked sagas and waypoint dirs. Skips git-tracked files.

    Returns (removed, skipped) as lists of display strings.
    """
    removed: list[str] = []
    skipped: list[str] = []

    if SAGAS_DIR.exists():
        for f in SAGAS_DIR.glob("*.json"):
            if is_git_tracked(f):
                skipped.append(f"{f.name} (tracked by git)")
                continue
            f.unlink()
            removed.append(str(f))

    if WAYPOINTS_DIR.exists():
        for d in WAYPOINTS_DIR.iterdir():
            if not d.is_dir():
                continue
            if any(is_git_tracked(f) for f in d.rglob("*") if f.is_file()):
                skipped.append(f"{d.name}/ (contains git-tracked files)")
                continue
            shutil.rmtree(d)
            removed.append(f"{d}/")

    return removed, skipped
