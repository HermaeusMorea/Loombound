#!/usr/bin/env python3
"""Summarize Slow Core / Fast Core token usage from logs/llm.md."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


RE_REQUEST = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] SLOW CORE REQUEST — node `(?P<node>[^`]+)`$"
)
RE_TIMESTAMP = re.compile(r"^## \[(?P<ts>[^\]]+)\]")
RE_SLOW_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] SLOW CORE RESPONSE — seed `[^`]+` "
    r"\((?P<idx>\d+)/(?P<total>\d+)\)$"
)
RE_FAST_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] FAST CORE RESPONSE(?: \(preloaded\))? — `(?P<arb>[^`]+)`$"
)
RE_M2_REQUEST = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] M2 CLASSIFIER REQUEST — node `(?P<node>[^`]+)`$"
)
RE_M2_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] M2 CLASSIFIER RESPONSE — node `(?P<node>[^`]+)` entry_id=(?P<entry_id>-?\d+)$"
)
RE_SLOW_TOKENS = re.compile(r"^tokens — input: (?P<input>\d+)  output: (?P<output>\d+)")
RE_FAST_TOKENS = re.compile(r"^tokens — prompt: (?P<prompt>\d+)  eval: (?P<eval>\d+)")
RE_ARBITRATION_COUNT = re.compile(r"^arbitration_count: (?P<count>\d+)$")
RE_COMPLETE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] COMPLETE(?: \(preloaded\))? — `(?P<node>[^`]+)` "
    r"\((?P<count>\d+) arbitration\(s\)"
)
RE_CAMPAIGN_CORE_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] CAMPAIGN CORE RESPONSE — `(?P<campaign>[^`]+)`$"
)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parent
)
DEFAULT_LOG = ROOT / "logs" / "llm.md"
DEFAULT_CAMPAIGNS = ROOT / "data" / "campaigns"


@dataclass
class RequestEvent:
    line_no: int
    timestamp: datetime
    node_id: str
    campaign_candidates: set[str]


@dataclass
class RunGroup:
    start_line: int
    end_line: int
    request_events: list[RequestEvent]
    campaign_candidates: set[str]


@dataclass
class CampaignCoreEvent:
    line_no: int
    timestamp: datetime
    campaign_id: str
    provider: str | None = None
    model: str | None = None
    theme: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class JobState:
    node_id: str
    arbitration_count: int = 0
    next_slow_idx: int = 1
    completed: bool = False


@dataclass
class NodeUsage:
    slow_calls: int = 0
    slow_input: int = 0
    slow_output: int = 0
    fast_calls: int = 0
    fast_prompt: int = 0
    fast_eval: int = 0
    m2_calls: int = 0
    m2_input: int = 0
    m2_output: int = 0
    m2_cache_read: int = 0

    @property
    def slow_total(self) -> int:
        return self.slow_input + self.slow_output

    @property
    def fast_total(self) -> int:
        return self.fast_prompt + self.fast_eval

    @property
    def m2_total(self) -> int:
        return self.m2_input + self.m2_output


@dataclass
class RunReport:
    start_line: int
    end_line: int
    start_timestamp: datetime
    end_timestamp: datetime
    campaign_id: str | None
    campaign_title: str | None
    node_order: list[str]
    campaign_core: CampaignCoreEvent | None = None
    slow_calls: int = 0
    slow_input: int = 0
    slow_output: int = 0
    fast_calls: int = 0
    fast_prompt: int = 0
    fast_eval: int = 0
    m2_calls: int = 0
    m2_input: int = 0
    m2_output: int = 0
    m2_cache_read: int = 0
    node_usage: dict[str, NodeUsage] = field(default_factory=dict)

    @property
    def slow_total(self) -> int:
        return self.slow_input + self.slow_output

    @property
    def fast_total(self) -> int:
        return self.fast_prompt + self.fast_eval

    @property
    def m2_total(self) -> int:
        return self.m2_input + self.m2_output

    @property
    def hypothetical_remote_total(self) -> int:
        return self.slow_total + self.fast_total

    @property
    def saved_remote_tokens(self) -> int:
        return self.fast_total


def parse_timestamp(raw: str) -> datetime:
    return datetime.strptime(raw, TIME_FORMAT)


def load_campaign_index(campaign_dir: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    node_index: dict[str, set[str]] = {}
    titles: dict[str, str] = {}
    for path in sorted(campaign_dir.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        campaign_id = data["campaign_id"]
        titles[campaign_id] = data.get("title", campaign_id)
        for node_id in data.get("nodes", {}):
            node_index.setdefault(node_id, set()).add(campaign_id)
    return node_index, titles


def parse_request_events(lines: list[str], node_index: dict[str, set[str]]) -> list[RequestEvent]:
    events: list[RequestEvent] = []
    for idx, line in enumerate(lines, start=1):
        match = RE_REQUEST.match(line)
        if not match:
            continue
        node_id = match.group("node")
        events.append(
            RequestEvent(
                line_no=idx,
                timestamp=parse_timestamp(match.group("ts")),
                node_id=node_id,
                campaign_candidates=set(node_index.get(node_id, set())),
            )
        )
    return events


def parse_campaign_core_events(lines: list[str]) -> list[CampaignCoreEvent]:
    events: list[CampaignCoreEvent] = []
    pending: CampaignCoreEvent | None = None

    for idx, line in enumerate(lines, start=1):
        match = RE_CAMPAIGN_CORE_RESPONSE.match(line)
        if match:
            pending = CampaignCoreEvent(
                line_no=idx,
                timestamp=parse_timestamp(match.group("ts")),
                campaign_id=match.group("campaign"),
            )
            events.append(pending)
            continue

        if pending is None:
            continue

        if line.startswith("provider: "):
            pending.provider = line.partition(": ")[2]
            continue
        if line.startswith("model: "):
            pending.model = line.partition(": ")[2]
            continue
        if line.startswith("theme: "):
            pending.theme = line.partition(": ")[2]
            continue

        tokens_match = RE_SLOW_TOKENS.match(line)
        if tokens_match:
            pending.input_tokens = int(tokens_match.group("input"))
            pending.output_tokens = int(tokens_match.group("output"))
            pending = None
            continue

        if line.startswith("## ["):
            pending = None

    return events


def group_runs(requests: list[RequestEvent], total_lines: int) -> list[RunGroup]:
    if not requests:
        return []

    runs: list[RunGroup] = []
    current_events: list[RequestEvent] = [requests[0]]
    current_candidates = set(requests[0].campaign_candidates)

    for event in requests[1:]:
        current_set = current_candidates or set()
        event_set = event.campaign_candidates or set()

        if current_set and event_set:
            intersection = current_set & event_set
            same_run = bool(intersection)
        else:
            intersection = current_set or event_set
            same_run = True

        if same_run:
            current_events.append(event)
            current_candidates = intersection
            continue

        runs.append(
            RunGroup(
                start_line=current_events[0].line_no,
                end_line=event.line_no - 1,
                request_events=current_events,
                campaign_candidates=current_candidates,
            )
        )
        current_events = [event]
        current_candidates = set(event.campaign_candidates)

    runs.append(
        RunGroup(
            start_line=current_events[0].line_no,
            end_line=total_lines,
            request_events=current_events,
            campaign_candidates=current_candidates,
        )
    )
    return runs


def split_arb_id(arb_id: str) -> str:
    if "_gen_" in arb_id:
        return arb_id.rsplit("_gen_", 1)[0]
    return arb_id


def assign_slow_response(jobs: list[JobState], idx: int, total: int) -> JobState | None:
    for job in jobs:
        if job.completed:
            continue
        if job.arbitration_count == total and job.next_slow_idx == idx:
            job.next_slow_idx += 1
            return job
    for job in jobs:
        if job.completed:
            continue
        if job.next_slow_idx == idx:
            job.next_slow_idx += 1
            return job
    for job in jobs:
        if not job.completed:
            job.next_slow_idx += 1
            return job
    return None


def analyze_run(
    lines: list[str],
    run: RunGroup,
    campaign_titles: dict[str, str],
    campaign_core_events: list[CampaignCoreEvent] | None = None,
) -> RunReport:
    start_timestamp = parse_timestamp(RE_REQUEST.match(lines[run.start_line - 1]).group("ts"))  # type: ignore[union-attr]
    end_timestamp = start_timestamp
    jobs: list[JobState] = []
    current_request_job: JobState | None = None
    pending_slow_job: JobState | None = None
    pending_fast_node: str | None = None
    node_usage: dict[str, NodeUsage] = {}
    node_order: list[str] = []

    for event in run.request_events:
        if event.node_id not in node_order:
            node_order.append(event.node_id)

    pending_m2_node: str | None = None

    for line in lines[run.start_line - 1 : run.end_line]:
        ts_match = RE_TIMESTAMP.match(line)
        if ts_match:
            end_timestamp = parse_timestamp(ts_match.group("ts"))

        request_match = RE_REQUEST.match(line)
        if request_match:
            current_request_job = JobState(node_id=request_match.group("node"))
            jobs.append(current_request_job)
            node_usage.setdefault(current_request_job.node_id, NodeUsage())
            continue

        count_match = RE_ARBITRATION_COUNT.match(line)
        if count_match and current_request_job is not None:
            current_request_job.arbitration_count = int(count_match.group("count"))
            continue

        slow_resp_match = RE_SLOW_RESPONSE.match(line)
        if slow_resp_match:
            pending_slow_job = assign_slow_response(
                jobs,
                int(slow_resp_match.group("idx")),
                int(slow_resp_match.group("total")),
            )
            pending_fast_node = None
            pending_m2_node = None
            continue

        fast_resp_match = RE_FAST_RESPONSE.match(line)
        if fast_resp_match:
            pending_fast_node = split_arb_id(fast_resp_match.group("arb"))
            node_usage.setdefault(pending_fast_node, NodeUsage())
            pending_slow_job = None
            pending_m2_node = None
            continue

        m2_resp_match = RE_M2_RESPONSE.match(line)
        if m2_resp_match:
            pending_m2_node = m2_resp_match.group("node")
            node_usage.setdefault(pending_m2_node, NodeUsage())
            pending_slow_job = None
            pending_fast_node = None
            continue

        complete_match = RE_COMPLETE.match(line)
        if complete_match:
            node_id = complete_match.group("node")
            for job in jobs:
                if job.node_id == node_id and not job.completed:
                    job.completed = True
            continue

        slow_tokens_match = RE_SLOW_TOKENS.match(line)
        if slow_tokens_match:
            if pending_m2_node is not None:
                usage = node_usage.setdefault(pending_m2_node, NodeUsage())
                usage.m2_calls += 1
                usage.m2_input += int(slow_tokens_match.group("input"))
                usage.m2_output += int(slow_tokens_match.group("output"))
                # cache_read is on the same line — optional capture
                cr_match = re.search(r"cache_read: (\d+)", line)
                if cr_match:
                    usage.m2_cache_read += int(cr_match.group(1))
                pending_m2_node = None
            elif pending_slow_job is not None:
                usage = node_usage.setdefault(pending_slow_job.node_id, NodeUsage())
                usage.slow_calls += 1
                usage.slow_input += int(slow_tokens_match.group("input"))
                usage.slow_output += int(slow_tokens_match.group("output"))
                pending_slow_job = None
            continue

        fast_tokens_match = RE_FAST_TOKENS.match(line)
        if fast_tokens_match and pending_fast_node is not None:
            usage = node_usage.setdefault(pending_fast_node, NodeUsage())
            usage.fast_calls += 1
            usage.fast_prompt += int(fast_tokens_match.group("prompt"))
            usage.fast_eval += int(fast_tokens_match.group("eval"))
            pending_fast_node = None
            continue

    campaign_id = None
    campaign_title = None
    if len(run.campaign_candidates) == 1:
        campaign_id = next(iter(run.campaign_candidates))
        campaign_title = campaign_titles.get(campaign_id, campaign_id)

    report = RunReport(
        start_line=run.start_line,
        end_line=run.end_line,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        campaign_id=campaign_id,
        campaign_title=campaign_title,
        node_order=node_order,
        node_usage=node_usage,
    )

    if campaign_core_events and report.campaign_id:
        eligible = [
            event
            for event in campaign_core_events
            if event.campaign_id == report.campaign_id and event.timestamp <= report.start_timestamp
        ]
        if eligible:
            report.campaign_core = eligible[-1]

    for usage in node_usage.values():
        report.slow_calls += usage.slow_calls
        report.slow_input += usage.slow_input
        report.slow_output += usage.slow_output
        report.fast_calls += usage.fast_calls
        report.fast_prompt += usage.fast_prompt
        report.fast_eval += usage.fast_eval
        report.m2_calls += usage.m2_calls
        report.m2_input += usage.m2_input
        report.m2_output += usage.m2_output
        report.m2_cache_read += usage.m2_cache_read

    return report


def _has_runtime_usage(report: RunReport) -> bool:
    """Return True when a run contains actual Slow/Fast Core token usage."""

    return (report.slow_calls + report.fast_calls) > 0


def select_run(
    runs: list[RunGroup],
    campaign_id: str | None,
    *,
    lines: list[str] | None = None,
    campaign_titles: dict[str, str] | None = None,
    campaign_core_events: list[CampaignCoreEvent] | None = None,
) -> RunGroup:
    if not runs:
        raise SystemExit("No Slow Core requests found in the log.")

    candidates = runs if campaign_id is None else [
        run for run in runs if campaign_id in run.campaign_candidates
    ]

    if not candidates:
        raise SystemExit(f"No runs matched campaign '{campaign_id}'.")

    if lines is not None and campaign_titles is not None:
        for run in reversed(candidates):
            report = analyze_run(
                lines,
                run,
                campaign_titles,
                campaign_core_events=campaign_core_events,
            )
            if _has_runtime_usage(report):
                return run

    return candidates[-1]


def format_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.00%"
    return f"{(100 * numerator / denominator):.2f}%"


def render_report(report: RunReport) -> str:
    title = report.campaign_title or "Unresolved campaign"
    campaign_line = title
    if report.campaign_id:
        campaign_line = f"{title} ({report.campaign_id})"

    lines = [
        "LLM usage report",
        f"scope: latest run lines {report.start_line}-{report.end_line}",
        f"time: {report.start_timestamp.strftime(TIME_FORMAT)} -> {report.end_timestamp.strftime(TIME_FORMAT)}",
        f"campaign: {campaign_line}",
        f"nodes: {', '.join(report.node_order) if report.node_order else '(none)'}",
        "",
    ]

    if report.campaign_core:
        lines.extend(
            [
                "campaign core:",
                "  "
                f"provider={report.campaign_core.provider or '?'} "
                f"model={report.campaign_core.model or '?'} "
                f"input={report.campaign_core.input_tokens} "
                f"output={report.campaign_core.output_tokens} "
                f"total={report.campaign_core.input_tokens + report.campaign_core.output_tokens}",
                f"  timestamp={report.campaign_core.timestamp.strftime(TIME_FORMAT)}",
            ]
        )
    else:
        lines.extend(
            [
                "campaign core:",
                "  not found in log before this run",
            ]
        )

    # ── Runtime generation table ─────────────────────────────────────────────
    remote_total = report.slow_total + report.m2_total
    lines.extend(["", "runtime generation:"])

    if report.m2_calls:
        cache_hit_str = f"  cache_read={report.m2_cache_read}" if report.m2_cache_read else ""
        lines.append(
            f"  m2 classifier: calls={report.m2_calls}"
            f"  input={report.m2_input}  output={report.m2_output}"
            f"  total={report.m2_total}{cache_hit_str}  (arc classification, claude)"
        )

    if report.slow_calls:
        lines.append(
            f"  slow core:     calls={report.slow_calls}"
            f"  input={report.slow_input}  output={report.slow_output}"
            f"  total={report.slow_total}  (arbitration planning)"
        )

    lines.append(
        f"  fast core:     calls={report.fast_calls}"
        f"  prompt={report.fast_prompt}  eval={report.fast_eval}"
        f"  total={report.fast_total}  (text expansion, local)"
    )

    lines.extend(
        [
            "",
            f"  remote tokens:   {remote_total}  (m2 + slow core)",
            f"  local tokens:    {report.fast_total}  (fast core only)",
            f"  saved remote:    {report.saved_remote_tokens}  (would have been remote without fast core)",
            f"  saved %:         {format_pct(report.saved_remote_tokens, report.hypothetical_remote_total)} of hypothetical all-remote total",
        ]
    )

    lines.extend(["", "per node:"])

    for node_id in report.node_order:
        usage = report.node_usage.get(node_id, NodeUsage())
        parts = []
        if usage.m2_calls:
            parts.append(f"m2={usage.m2_total}(calls={usage.m2_calls},in={usage.m2_input},out={usage.m2_output})")
        if usage.slow_calls:
            parts.append(f"slow={usage.slow_total}(calls={usage.slow_calls},in={usage.slow_input},out={usage.slow_output})")
        parts.append(f"fast={usage.fast_total}(calls={usage.fast_calls},prompt={usage.fast_prompt},eval={usage.fast_eval})")
        lines.append(f"  {node_id}: " + "  ".join(parts))

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize token usage from logs/llm.md."
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help="Path to the markdown log file.",
    )
    parser.add_argument(
        "--campaign",
        help="Campaign id to report on. Defaults to the latest run in the log.",
    )
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        default=DEFAULT_CAMPAIGNS,
        help="Directory containing campaign JSON files.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with args.log.open(encoding="utf-8") as fh:
        lines = [line.rstrip("\n") for line in fh]

    node_index, campaign_titles = load_campaign_index(args.campaign_dir)
    requests = parse_request_events(lines, node_index)
    campaign_core_events = parse_campaign_core_events(lines)
    runs = group_runs(requests, len(lines))
    run = select_run(
        runs,
        args.campaign,
        lines=lines,
        campaign_titles=campaign_titles,
        campaign_core_events=campaign_core_events,
    )
    report = analyze_run(lines, run, campaign_titles, campaign_core_events=campaign_core_events)
    print(render_report(report))


if __name__ == "__main__":
    main()
