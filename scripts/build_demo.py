#!/usr/bin/env python3
"""Build a bytecode-only Loombound demo bundle."""

from __future__ import annotations

import argparse
import compileall
import shutil
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
APP_FILES = [
    "generate_campaign.py",
    "report_llm_usage.py",
]
DOC_FILES = [
    "README.md",
    "STARTUP.md",
]
ENV_EXAMPLE = """# Optional API keys for LLM-enabled demo mode
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
DASHSCOPE_API_KEY=

# Optional runtime overrides
# SLOW_CORE_PROVIDER=deepseek
# SLOW_CORE_MODEL=deepseek-chat
# FAST_CORE_MODEL=gemma3:4b
"""


def _site_packages_dir() -> Path:
    lib_dir = ROOT / ".venv" / "lib"
    matches = sorted(lib_dir.glob("python*/site-packages"))
    if not matches:
        raise SystemExit("No site-packages directory found under .venv/lib.")
    return matches[0]


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_app(out_app: Path) -> None:
    shutil.copytree(ROOT / "src", out_app / "src")
    for name in APP_FILES:
        shutil.copy2(ROOT / name, out_app / name)

    compiled = compileall.compile_dir(
        str(out_app),
        force=True,
        legacy=True,
        quiet=1,
    )
    if not compiled:
        raise SystemExit("compileall failed for demo app bundle.")

    for py_file in out_app.rglob("*.py"):
        py_file.unlink()
    for cache_dir in out_app.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


def _copy_vendor(out_vendor: Path) -> None:
    shutil.copytree(_site_packages_dir(), out_vendor / "site-packages")


def _copy_data(out_root: Path, include_logs: bool) -> None:
    shutil.copytree(ROOT / "data", out_root / "data")
    logs_dir = out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "llm.md"
    if include_logs and (ROOT / "logs" / "llm.md").exists():
        shutil.copy2(ROOT / "logs" / "llm.md", log_file)
    else:
        log_file.write_text("", encoding="utf-8")


def _launcher(script_name: str, command: str) -> str:
    required_major = sys.version_info.major
    required_minor = sys.version_info.minor
    return f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PYTHON_BIN="${{PYTHON_BIN:-python3}}"

"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info[:2] == ({required_major}, {required_minor}) else 1)' || {{
  echo "{script_name}: requires Python {required_major}.{required_minor}." >&2
  echo "Set PYTHON_BIN=/path/to/python{required_major}.{required_minor} if needed." >&2
  exit 1
}}

export LOOMBOUND_ROOT="$SCRIPT_DIR"
export BLACK_ARCHIVE_ROOT="$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR/app:$SCRIPT_DIR/vendor/site-packages${{PYTHONPATH:+:$PYTHONPATH}}"

exec "$PYTHON_BIN" {command} "${{@}}"
"""


def _write_launchers(out_root: Path) -> None:
    launchers = {
        "run.sh": _launcher("run.sh", "-m src.core.runtime.play_cli"),
        "gen.sh": _launcher("gen.sh", '"$SCRIPT_DIR/app/generate_campaign.pyc"'),
        "report.sh": _launcher("report.sh", '"$SCRIPT_DIR/app/report_llm_usage.pyc"'),
    }
    for name, content in launchers.items():
        path = out_root / name
        _write_text(path, content)
        path.chmod(0o755)


def _write_demo_readme(out_root: Path, bundle_name: str, include_logs: bool) -> None:
    text = f"""# {bundle_name}

This is a bytecode-only Loombound demo bundle intended for tester feedback.

What is included:
- `run.sh` to play the CLI demo
- `gen.sh` to generate campaigns
- `report.sh` to inspect token usage
- `data/` with authored content and generated campaigns
- `vendor/site-packages/` with bundled Python dependencies

Important limits:
- This is best-effort closed-source packaging, not strong DRM.
- The bundle requires Python {sys.version_info.major}.{sys.version_info.minor} on the tester machine.
- LLM-enabled flows still require API keys and a local Ollama server when using Fast Core.

Quick start:
```bash
./run.sh
./run.sh --llm --slow deepseek --lang zh
./gen.sh "火星城邦政变" --tone "冷峻政治惊悚" --worldview "近未来火星城邦冷战"
./report.sh
```

Logs included: {"yes" if include_logs else "no, starts fresh"}
"""
    _write_text(out_root / "DEMO_README.md", text)


def _copy_docs(out_root: Path) -> None:
    for name in DOC_FILES:
        shutil.copy2(ROOT / name, out_root / name)
    _write_text(out_root / ".env.example", ENV_EXAMPLE)


def _make_archive(out_root: Path) -> Path:
    archive_path = out_root.with_suffix(".tar.gz")
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(out_root, arcname=out_root.name)
    return archive_path


def build_bundle(name: str, include_logs: bool, make_archive: bool) -> tuple[Path, Path | None]:
    out_root = DIST_DIR / name
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    _copy_app(out_root / "app")
    _copy_vendor(out_root / "vendor")
    _copy_data(out_root, include_logs=include_logs)
    _copy_docs(out_root)
    _write_launchers(out_root)
    _write_demo_readme(out_root, name, include_logs=include_logs)

    archive_path = _make_archive(out_root) if make_archive else None
    return out_root, archive_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bytecode-only Loombound demo bundle."
    )
    parser.add_argument(
        "--name",
        default="loombound-demo",
        help="Output bundle name under dist/ (default: loombound-demo).",
    )
    parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Include the current logs/llm.md in the demo bundle.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not create a .tar.gz archive alongside the demo directory.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    out_root, archive_path = build_bundle(
        name=args.name,
        include_logs=args.include_logs,
        make_archive=not args.no_archive,
    )

    print(f"Demo bundle written to: {out_root}")
    if archive_path:
        print(f"Archive written to: {archive_path}")
    print("Launchers:")
    print(f"  {out_root / 'run.sh'}")
    print(f"  {out_root / 'gen.sh'}")
    print(f"  {out_root / 'report.sh'}")


if __name__ == "__main__":
    main()
