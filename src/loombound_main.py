"""Python entry point for the loombound CLI (installed via pip as `loombound`)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.shared.dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
_SAGAS_DIR = DATA_DIR / "sagas"

_USAGE = """\
loombound — Loombound saga CLI

SUBCOMMANDS
  arc-palette  [--count N] [--output PATH]
      Generate the A2 cache (global arc-state palette). One-time setup.

  gen "theme" [--nodes N] [--lang zh] [--tone "..."] [--worldview "..."] [--skip-t1-cache]
      Generate a saga graph (Opus) + A1 cache skeletons (Haiku).

  run [--saga ID_OR_PATH] [--fast MODEL] [--lang zh] [--nodes N]
      Launch the game. Requires ANTHROPIC_API_KEY.

  report [--saga ID]
      Print LLM usage / cost report.

  clean [--saga ID_OR_PATH] [--all]
      Remove saga files. --all removes everything in data/sagas/ and data/waypoints/.

  clean-palette
      Delete data/a2_cache_table.json.

  clean-logs
      Truncate logs/llm.md to empty.

EXAMPLES
  loombound arc-palette
  loombound gen "亚南猎人之夜" --nodes 4 --lang zh --tone "哥特克苏鲁"
  loombound run --lang zh
  loombound report
  loombound clean --saga deep_mine_cult_act1
  loombound clean --all
"""


def main() -> None:
    load_dotenv()

    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h", "help"):
        print(_USAGE)
        return

    subcmd, *rest = args

    if subcmd == "arc-palette":
        _run_module("src.t3.core.gen_a2_cache_table", rest)

    elif subcmd == "gen":
        _run_module("src.t3.core.generate_saga", rest)

    elif subcmd == "run":
        new_args: list[str] = []
        i = 0
        while i < len(rest):
            if rest[i] == "--saga" and i + 1 < len(rest):
                new_args += ["--saga", _resolve_saga(rest[i + 1])]
                i += 2
            else:
                new_args.append(rest[i])
                i += 1
        _run_module("src.runtime.play_cli", new_args)

    elif subcmd == "report":
        _run_script("scripts/report_llm_usage.py", rest)

    elif subcmd == "clean-palette":
        target = DATA_DIR / "a2_cache_table.json"
        if target.exists():
            target.unlink()
            print(f"Deleted {target}")
        else:
            print(f"Nothing to clean — {target} does not exist.")

    elif subcmd == "clean-logs":
        log_file = REPO_ROOT / "logs" / "llm.md"
        if log_file.exists():
            log_file.write_text("", encoding="utf-8")
            print(f"Cleared {log_file}")
        else:
            print(f"Nothing to clean — {log_file} does not exist.")

    elif subcmd == "clean":
        _cmd_clean(rest)

    else:
        print(f"loombound: unknown subcommand '{subcmd}'", file=sys.stderr)
        print("Run 'loombound --help' for usage.", file=sys.stderr)
        sys.exit(1)


def _resolve_saga(id_or_path: str) -> str:
    p = Path(id_or_path)
    if p.is_absolute() or id_or_path.startswith("./"):
        return str(p)
    if id_or_path.startswith("data/sagas/"):
        return str(REPO_ROOT / id_or_path)
    stem = p.stem if p.suffix == ".json" else id_or_path
    return str(_SAGAS_DIR / f"{stem}.json")


def _run_module(module: str, extra: list[str]) -> None:
    os.chdir(REPO_ROOT)
    os.execvp(sys.executable, [sys.executable, "-m", module, *extra])


def _run_script(script: str, extra: list[str]) -> None:
    os.chdir(REPO_ROOT)
    os.execvp(sys.executable, [sys.executable, str(REPO_ROOT / script), *extra])


def _cmd_clean(args: list[str]) -> None:
    saga_id = ""
    i = 0
    while i < len(args):
        if args[i] == "--saga" and i + 1 < len(args):
            saga_id = args[i + 1]
            i += 2
        elif args[i] == "--all":
            i += 1
        else:
            print(f"loombound clean: unknown flag '{args[i]}'", file=sys.stderr)
            sys.exit(1)

    if saga_id:
        saga_file = Path(_resolve_saga(saga_id))
        stem = saga_file.stem
        nodes_dir = DATA_DIR / "waypoints" / stem
        removed = False

        if saga_file.exists():
            saga_file.unlink()
            print(f"Removed {saga_file}")
            removed = True
        for suffix in ("_rules.json", "_toll_lexicon.json", "_narration_table.json"):
            related = _SAGAS_DIR / f"{stem}{suffix}"
            if related.exists():
                related.unlink()
                print(f"Removed {related}")
                removed = True
        if nodes_dir.exists():
            shutil.rmtree(nodes_dir)
            print(f"Removed {nodes_dir}/")
            removed = True
        if not removed:
            print(f"Nothing to clean for saga '{stem}'.")
    else:
        print("Cleaning all saga data (keeping data/a2_cache_table.json)...")
        removed = False
        if _SAGAS_DIR.exists():
            for f in _SAGAS_DIR.glob("*.json"):
                if _is_git_tracked(f):
                    print(f"  Skipped {f.name} (tracked by git)")
                    continue
                f.unlink()
                print(f"  Removed {f}")
                removed = True
        waypoints_dir = DATA_DIR / "waypoints"
        if waypoints_dir.exists():
            for d in waypoints_dir.iterdir():
                if d.is_dir():
                    shutil.rmtree(d)
                    print(f"  Removed {d}/")
                    removed = True
        if not removed:
            print("Nothing to clean.")
        else:
            print("Done.")


def _is_git_tracked(path: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=REPO_ROOT, capture_output=True,
    )
    return result.returncode == 0


if __name__ == "__main__":
    main()
