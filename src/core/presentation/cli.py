"""Terminal rendering helpers for the interactive CLI loop."""

from __future__ import annotations

import re
import unicodedata
from shutil import get_terminal_size
from typing import Any


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

FG_CYAN = "\033[36m"
FG_BLUE = "\033[34m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_RED = "\033[31m"
FG_MAGENTA = "\033[35m"
FG_WHITE = "\033[37m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ANSI_TOKEN_RE = re.compile(r"(\x1b\[[0-9;]*m)")


def _hud_bar(run: Any, title: str, subtitle: str = "") -> str:
    """Render a fixed top HUD bar shared by major gameplay screens."""

    width = _screen_width()
    health = f"{FG_GREEN}HP{RESET} {run.core_state.health}/{run.core_state.max_health}"
    money = f"{FG_YELLOW}$ {run.core_state.money}{RESET}"
    sanity = f"{FG_MAGENTA}SAN {run.core_state.sanity}{RESET}"
    scene = f"{FG_BLUE}{title}{RESET}"
    line = f"{BOLD}LOOMBOUND{RESET}  |  {scene}  |  {health}  |  {money}  |  {sanity}"
    if subtitle:
        line = f"{line}  |  {DIM}{subtitle}{RESET}"
    if _visible_len(line) > width:
        line = _truncate_visible(line, width)
    padding = max(0, width - _visible_len(line))
    padded = f"{line}{' ' * padding}"
    return f"{FG_WHITE}{'═' * width}{RESET}\n{padded}\n{FG_WHITE}{'═' * width}{RESET}"


def _screen_width() -> int:
    """Return a stable terminal width for boxed layouts."""

    return max(72, min(get_terminal_size((100, 24)).columns, 140))


def _clear_screen() -> None:
    """Clear the terminal so each step feels like one game screen."""

    print("\033[2J\033[H", end="")


def _wrap(text: str, width: int) -> list[str]:
    """Wrap one text block into fixed-width lines."""

    if not text:
        return [""]
    if width <= 0:
        return [text]

    stripped = _strip_ansi(text)
    if " " not in stripped:
        return _hard_wrap(text, width)

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if _visible_len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.extend(_hard_wrap(word, width))
            continue
        candidate = word if not current else f"{current} {word}"
        if _visible_len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _box(title: str, lines: list[str], *, width: int, color: str = FG_CYAN) -> str:
    """Render a titled box with wrapped lines."""

    inner = max(1, width - 4)
    wrapped: list[str] = []
    for line in lines or [""]:
        wrapped.extend(_wrap(str(line), inner))

    top = f"{color}┌{'─' * (width - 2)}┐{RESET}"
    max_header_width = max(0, width - 2)
    header_text = f" {title} "
    if _visible_len(header_text) > max_header_width:
        header_text = _truncate_visible(header_text, max_header_width)
    header_fill = max(0, width - 2 - _visible_len(header_text))
    header = f"{color}│{BOLD}{header_text}{RESET}{color}{'─' * header_fill}│{RESET}"
    body = [f"{color}│{RESET} {_pad_visible(line, inner)} {color}│{RESET}" for line in wrapped]
    bottom = f"{color}└{'─' * (width - 2)}┘{RESET}"
    return "\n".join([top, header, *body, bottom])


def _columns(left: str, right: str, *, gap: int = 2) -> str:
    """Render two boxed panels side by side."""

    left_lines = left.splitlines()
    right_lines = right.splitlines()
    height = max(len(left_lines), len(right_lines))
    left_width = max((_visible_len(line) for line in left_lines), default=0)
    padded_left = left_lines + [" " * left_width] * (height - len(left_lines))
    padded_right = right_lines + [""] * (height - len(right_lines))
    rows: list[str] = []
    for index in range(height):
        rows.append(f"{_pad_visible(padded_left[index], left_width)}{' ' * gap}{padded_right[index]}")
    return "\n".join(rows)


def _columns_or_stack(
    left: str,
    right: str,
    *,
    width: int,
    gap: int = 2,
    min_two_column_width: int = 96,
) -> str:
    """Render two panels side by side when wide enough, else stack them vertically."""

    if width < min_two_column_width:
        return f"{left}\n\n{right}"
    return _columns(left, right, gap=gap)


def _strip_ansi(text: str) -> str:
    """Remove ANSI color codes for visible-width calculation."""

    return ANSI_RE.sub("", text)


def _visible_len(text: str) -> int:
    """Return the printable width of one ANSI-colored string."""

    return sum(_char_width(ch) for ch in _strip_ansi(text))


def _pad_visible(text: str, width: int) -> str:
    """Pad one ANSI-colored string to a target visible width."""

    return f"{text}{' ' * max(0, width - _visible_len(text))}"


def _char_width(ch: str) -> int:
    """Approximate terminal cell width for one Unicode character."""

    if not ch:
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in {"W", "F"}:
        return 2
    return 1


def _hard_wrap(text: str, width: int) -> list[str]:
    """Wrap text by display cells, preserving ANSI escapes."""

    if not text:
        return [""]

    lines: list[str] = []
    current = ""
    current_width = 0
    active_codes: list[str] = []

    for token in ANSI_TOKEN_RE.split(text):
        if not token:
            continue
        if ANSI_RE.fullmatch(token):
            current += token
            if token == RESET:
                active_codes = []
            else:
                active_codes.append(token)
            continue

        for ch in token:
            ch_width = _char_width(ch)
            if current_width > 0 and current_width + ch_width > width:
                if active_codes and not current.endswith(RESET):
                    current += RESET
                lines.append(current)
                current = "".join(active_codes) + ch
                current_width = ch_width
                continue
            current += ch
            current_width += ch_width

    if current:
        if active_codes and not current.endswith(RESET):
            current += RESET
        lines.append(current)
    return lines or [""]


def _truncate_visible(text: str, width: int, suffix: str = "…") -> str:
    """Trim one ANSI-colored string to a target visible width."""

    if width <= 0:
        return ""
    if _visible_len(text) <= width:
        return text

    suffix_width = _visible_len(suffix)
    budget = max(0, width - suffix_width)
    current = ""
    current_width = 0
    active_codes: list[str] = []

    for token in ANSI_TOKEN_RE.split(text):
        if not token:
            continue
        if ANSI_RE.fullmatch(token):
            current += token
            if token == RESET:
                active_codes = []
            else:
                active_codes.append(token)
            continue

        for ch in token:
            ch_width = _char_width(ch)
            if current_width + ch_width > budget:
                trimmed = current + suffix
                if active_codes and not trimmed.endswith(RESET):
                    trimmed += RESET
                return trimmed
            current += ch
            current_width += ch_width

    return current


def pause(message: str = "Press Enter to continue...") -> None:
    """Pause between major screens so the player can read them."""

    input(f"\n{DIM}{message}{RESET}")


def render_input_panel(prompt: str, hint: str = "Type a number, or q to quit.") -> None:
    """Render a fixed bottom input box before reading player input."""

    width = min(_screen_width(), 110)
    print()
    print(
        _box(
            "Input",
            [
                prompt,
                "",
                f"{DIM}{hint}{RESET}",
            ],
            width=width,
            color=FG_WHITE,
        )
    )


def render_run_intro(campaign: dict[str, Any]) -> None:
    """Render the campaign intro shown at the start of a run."""

    _clear_screen()
    width = min(_screen_width(), 96)
    print(
        _box(
            "Loombound",
            [f"{BOLD}{campaign['title']}{RESET}", "", campaign["intro"]],
            width=width,
            color=FG_MAGENTA,
        )
    )


def render_node_header(run: Any, campaign_node: dict[str, Any]) -> None:
    """Render the active node header and map blurb."""

    _clear_screen()
    width = min(_screen_width(), 110)
    print(_hud_bar(run, "Entering Node", campaign_node["label"]))
    print()
    print(_box(campaign_node["label"], [campaign_node["map_blurb"]], width=width, color=FG_BLUE))


def render_state_panel(run: Any) -> None:
    """Render the current visible state block for the player."""

    width = min(44, max(34, _screen_width() // 3))
    conditions = ", ".join(run.meta_state.active_conditions) or "none"
    major_events = run.meta_state.metadata.get("major_events", [])
    lines = [
        f"{FG_GREEN}Health{RESET}: {run.core_state.health}/{run.core_state.max_health}",
        f"{FG_YELLOW}Money{RESET}: {run.core_state.money}",
        f"{FG_MAGENTA}Sanity{RESET}: {run.core_state.sanity}",
        "",
        f"{FG_CYAN}Conditions{RESET}: {conditions}",
    ]
    if major_events:
        lines.extend(["", f"{FG_WHITE}Recent Events{RESET}:"])
        lines.extend(f"- {item}" for item in major_events[-3:])
    print(_box("State", lines, width=width, color=FG_CYAN))


def render_arbitration_view(run: Any, arbitration: Any, selected_rule: Any) -> None:
    """Render the current arbitration scene and the state panel."""

    _clear_screen()
    width = _screen_width()
    is_narrow = width < 96
    state_width = min(44, max(34, width - 2 if is_narrow else width // 3))
    scene_width = min(width - 2 if is_narrow else width - state_width - 2, 88)
    print(_hud_bar(run, "Arbitration", arbitration.context.scene_type))
    print()

    state_lines = [
        f"{FG_GREEN}Health{RESET}: {run.core_state.health}/{run.core_state.max_health}",
        f"{FG_YELLOW}Money{RESET}: {run.core_state.money}",
        f"{FG_MAGENTA}Sanity{RESET}: {run.core_state.sanity}",
        "",
        f"{FG_CYAN}Conditions{RESET}: {', '.join(run.meta_state.active_conditions) or 'none'}",
    ]
    major_events = run.meta_state.metadata.get("major_events", [])
    if major_events:
        state_lines.extend(["", f"{FG_WHITE}Recent Events{RESET}:"])
        state_lines.extend(f"- {item}" for item in major_events[-3:])

    scene_lines = [
        arbitration.context.metadata.get("scene_summary", arbitration.context.context_id),
        "",
        arbitration.context.metadata.get("sanity_question", ""),
        "",
        f"{FG_BLUE}Scene Type{RESET}: {arbitration.context.scene_type}",
        f"{FG_RED}Pressure Rule{RESET}: {selected_rule.name if selected_rule else 'none'}",
    ]
    print(
        _columns_or_stack(
            _box("State", state_lines, width=state_width, color=FG_CYAN),
            _box("Arbitration", scene_lines, width=scene_width, color=FG_BLUE),
            width=width,
        )
    )


def render_choices(option_results: list[Any]) -> None:
    """Render numbered option results for the current arbitration."""

    width = min(_screen_width(), 110)
    lines: list[str] = []
    for idx, result in enumerate(option_results, start=1):
        verdict_color = FG_GREEN if result.verdict == "stable" else FG_RED
        lines.append(f"{BOLD}{idx}.{RESET} {result.label}")
        lines.append(
            f"   {verdict_color}{result.verdict}{RESET} | "
            f"{FG_MAGENTA}sanity cost{RESET}: {result.sanity_cost}"
        )
        if result.reasons:
            lines.append(f"   {DIM}{'; '.join(result.reasons)}{RESET}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    print("\n" + _box("Choices", lines, width=width, color=FG_YELLOW))


def render_result(run: Any, chosen_result: Any, narration: Any, applied_notes: list[str]) -> None:
    """Render the post-choice result block and refreshed state."""

    _clear_screen()
    width = _screen_width()
    is_narrow = width < 96
    state_width = min(44, max(34, width - 2 if is_narrow else width // 3))
    result_width = min(width - 2 if is_narrow else width - state_width - 2, 88)
    print(_hud_bar(run, "Result", chosen_result.verdict))
    print()

    state_lines = [
        f"{FG_GREEN}Health{RESET}: {run.core_state.health}/{run.core_state.max_health}",
        f"{FG_YELLOW}Money{RESET}: {run.core_state.money}",
        f"{FG_MAGENTA}Sanity{RESET}: {run.core_state.sanity}",
        "",
        f"{FG_CYAN}Conditions{RESET}: {', '.join(run.meta_state.active_conditions) or 'none'}",
    ]

    result_lines = [
        f"{FG_WHITE}Chosen{RESET}: {chosen_result.label}",
        f"{FG_RED if chosen_result.verdict == 'destabilizing' else FG_GREEN}Verdict{RESET}: {chosen_result.verdict}",
    ]
    if narration.opening:
        result_lines.extend(["", narration.opening])
    if narration.judgement:
        result_lines.extend(["", narration.judgement])
    if narration.warning:
        result_lines.extend(["", narration.warning])
    if applied_notes:
        result_lines.extend(["", f"{FG_YELLOW}Applied Changes{RESET}:"])
        result_lines.extend(f"- {note}" for note in applied_notes)

    print(
        _columns_or_stack(
            _box("State", state_lines, width=state_width, color=FG_CYAN),
            _box(
                "Result",
                result_lines,
                width=result_width,
                color=FG_GREEN if chosen_result.verdict == "stable" else FG_RED,
            ),
            width=width,
        )
    )


def render_run_complete(run: Any) -> None:
    """Render the final run summary after the campaign ends."""

    _clear_screen()
    width = min(_screen_width(), 110)
    print(_hud_bar(run, "Run Complete"))
    print()
    lines = [
        f"{FG_GREEN}Health{RESET}: {run.core_state.health}/{run.core_state.max_health}",
        f"{FG_YELLOW}Money{RESET}: {run.core_state.money}",
        f"{FG_MAGENTA}Sanity{RESET}: {run.core_state.sanity}",
        "",
        f"{FG_CYAN}Final Conditions{RESET}: {', '.join(run.meta_state.active_conditions) or 'none'}",
    ]
    major_events = run.meta_state.metadata.get("major_events", [])
    if major_events:
        lines.extend(["", f"{FG_WHITE}Archive Log{RESET}:"])
        lines.extend(f"- {item}" for item in major_events[-5:])
    print(_box("Run Complete", lines, width=width, color=FG_MAGENTA))


def render_map_hud(run: Any, campaign: dict[str, Any], next_nodes: list[str]) -> None:
    """Render the map screen with the shared HUD at the top."""

    _clear_screen()
    width = min(_screen_width(), 110)
    subtitle = f"{len(next_nodes)} path{'s' if len(next_nodes) != 1 else ''} available"
    print(_hud_bar(run, "Map", subtitle))
    print()
    lines = ["Where do you go next?", ""]
    for idx, next_node_id in enumerate(next_nodes, start=1):
        next_node = campaign["nodes"][next_node_id]
        lines.append(f"{BOLD}{idx}.{RESET} {next_node['label']}")
        lines.append(f"   {next_node['map_blurb']}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    print(_box("Map", lines, width=width, color=FG_BLUE))
