"""Runtime entry points and orchestration."""

__all__ = ["main", "observe_demo", "run_memory_demo"]


def main() -> None:
    # Import lazily so package import does not eagerly load the CLI module.
    from .cli import main as cli_main

    cli_main()


def run_memory_demo() -> None:
    from .run_memory_demo import main as demo_main

    demo_main()


def observe_demo() -> None:
    from .observe_demo import main as observe_main

    observe_main()
