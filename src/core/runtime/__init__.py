"""Runtime entry points and lifecycle objects."""

from .session import Arbitration, Node, Run

__all__ = ["Arbitration", "Node", "Run", "play_cli"]


def play_cli() -> None:
    from .play_cli import main as play_main

    play_main()
