#!/usr/bin/env python3
"""Summarize campaign/preload/runtime token usage from logs/llm.md."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Pricing (per token)
# ---------------------------------------------------------------------------

OPUS_INPUT      = 5.0  / 1_000_000
OPUS_OUTPUT     = 25.0 / 1_000_000
OPUS_CACHE_READ = 0.50 / 1_000_000
HAIKU_INPUT     = 0.80 / 1_000_000
HAIKU_OUTPUT    = 4.0  / 1_000_000

EQUIV_HAIKU_OUTPUT = HAIKU_OUTPUT   # cost per local token if it had been remote (Haiku)
EQUIV_OPUS_OUTPUT  = OPUS_OUTPUT    # cost per local token if it had been remote (Opus)


def opus_cost(inp: int, out: int, cache_read: int = 0) -> float:
    return inp * OPUS_INPUT + out * OPUS_OUTPUT + cache_read * OPUS_CACHE_READ


def haiku_cost(inp: int, out: int, cache_read: int = 0) -> float:
    return inp * HAIKU_INPUT + out * HAIKU_OUTPUT + cache_read * OPUS_CACHE_READ


def _is_opus(model: str) -> bool:
    return "opus" in model.lower()


def _model_cost(model: str, inp: int, out: int, cache_read: int = 0) -> float:
    if _is_opus(model):
        return opus_cost(inp, out, cache_read)
    return haiku_cost(inp, out)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

RE_TIMESTAMP = re.compile(r"^## \[(?P<ts>[^\]]+)\]")

# Runtime events
RE_SLOW_REQUEST  = re.compile(r"^## \[(?P<ts>[^\]]+)\] SLOW CORE REQUEST — node `(?P<node>[^`]+)`$")
RE_SLOW_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] SLOW CORE RESPONSE — seed `[^`]+` "
    r"\((?P<idx>\d+)/(?P<total>\d+)\)$"
)
RE_FAST_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] FAST CORE RESPONSE(?: \(preloaded\))? — `(?P<arb>[^`]+)`$"
)
RE_M2_REQUEST  = re.compile(r"^## \[(?P<ts>[^\]]+)\] M2 CLASSIFIER REQUEST — node `(?P<node>[^`]+)`$")
RE_M2_RESPONSE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] M2 CLASSIFIER RESPONSE — node `(?P<node>[^`]+)` entry_id=(?P<entry_id>-?\d+)$"
)
RE_COMPLETE = re.compile(
    r"^## \[(?P<ts>[^\]]+)\] COMPLETE(?: \(preloaded\))? — `(?P<node>[^`]+)` "
    r"\((?P<count>\d+) arbitration\(s\)"
)

# Offline events
RE_CAMPAIGN_CORE = re.compile(r"^## \[(?P<ts>[^\]]+)\] CAMPAIGN CORE RESPONSE — `(?P<campaign>[^`]+)`$")
RE_TABLE_B       = re.compile(r"^## \[(?P<ts>[^\]]+)\] TABLE B RESPONSE — `(?P<campaign>[^`]+)`")
RE_TABLE_B_NODE  = re.compile(r"^## \[(?P<ts>[^\]]+)\] TABLE B NODE RESPONSE — `(?P<node>[^`]+)`")
RE_ARC_PALETTE   = re.compile(r"^## \[(?P<ts>[^\]]+)\] ARC PALETTE GENERATED$")

# Token lines
RE_SLOW_TOKENS  = re.compile(r"^tokens — input: (?P<input>\d+)  output: (?P<output>\d+)")
RE_M2_TOKENS    = re.compile(
    r"^tokens — input: (?P<input>\d+)  output: (?P<output>\d+)"
    r"(?:  cache_created: (?P<cc>\d+))?(?:  cache_read: (?P<cr>\d+))?"
)
RE_FAST_TOKENS  = re.compile(r"^tokens — prompt: (?P<prompt>\d+)  eval: (?P<eval>\d+)")
RE_COST         = re.compile(r"^cost: \$(?P<cost>[\d.]+)")
RE_ARB_COUNT    = re.compile(r"^arbitration_count: (?P<count>\d+)$")

TIME_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parent.parent
)
DEFAULT_LOG       = ROOT / "logs" / "llm.md"
DEFAULT_CAMPAIGNS = ROOT / "data" / "campaigns"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ArcPaletteEvent:
    line_no: int
    timestamp: datetime
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost(self) -> float:
        return opus_cost(self.input_tokens, self.output_tokens)


@dataclass
class CampaignCoreEvent:
    line_no: int
    timestamp: datetime
    campaign_id: str
    provider: str | None = None
    model: str | None = None
    theme: str | None = None
    title: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost(self) -> float:
        m = self.model or ""
        return _model_cost(m, self.input_tokens, self.output_tokens)


@dataclass
class TableBEvent:
    line_no: int
    timestamp: datetime
    campaign_id: str
    node_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost(self) -> float:
        return haiku_cost(self.input_tokens, self.output_tokens)


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
class M2CallUsage:
    node_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_created: int = 0

    @property
    def cost(self) -> float:
        return opus_cost(self.input_tokens, self.output_tokens, self.cache_read)

    @property
    def cache_savings(self) -> float:
        return self.cache_read * (OPUS_INPUT - OPUS_CACHE_READ)


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
    m2_cache_created: int = 0

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
    def m2_cost(self) -> float:
        return opus_cost(self.m2_input, self.m2_output, self.m2_cache_read)

    @property
    def m2_cache_savings(self) -> float:
        return self.m2_cache_read * (OPUS_INPUT - OPUS_CACHE_READ)


@dataclass
class RunReport:
    start_line: int
    end_line: int
    start_timestamp: datetime
    end_timestamp: datetime
    campaign_id: str | None
    campaign_title: str | None
    node_order: list[str]
    arc_palette: ArcPaletteEvent | None = None
    campaign_core: CampaignCoreEvent | None = None
    table_b: TableBEvent | None = None
    table_b_node_events: list[TableBEvent] = field(default_factory=list)
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
    m2_cache_created: int = 0
    node_usage: dict[str, NodeUsage] = field(default_factory=dict)

    # ── derived ──────────────────────────────────────────────────────────

    @property
    def table_b_calls(self) -> int:
        return len(self.table_b_node_events)

    @property
    def table_b_nodes(self) -> int:
        return len({e.node_id for e in self.table_b_node_events if e.node_id})

    @property
    def table_b_input(self) -> int:
        if self.table_b_node_events:
            return sum(e.input_tokens for e in self.table_b_node_events)
        return self.table_b.input_tokens if self.table_b else 0

    @property
    def table_b_output(self) -> int:
        if self.table_b_node_events:
            return sum(e.output_tokens for e in self.table_b_node_events)
        return self.table_b.output_tokens if self.table_b else 0

    @property
    def fast_total(self) -> int:
        return self.fast_prompt + self.fast_eval

    @property
    def m2_total(self) -> int:
        return self.m2_input + self.m2_output

    @property
    def m2_cost(self) -> float:
        return opus_cost(self.m2_input, self.m2_output, self.m2_cache_read)

    @property
    def m2_cache_savings(self) -> float:
        return self.m2_cache_read * (OPUS_INPUT - OPUS_CACHE_READ)

    @property
    def opus_total_input(self) -> int:
        core_in = self.campaign_core.input_tokens if self.campaign_core and _is_opus(self.campaign_core.model or "") else 0
        pal_in  = self.arc_palette.input_tokens if self.arc_palette else 0
        return core_in + pal_in + self.m2_input

    @property
    def opus_total_output(self) -> int:
        core_out = self.campaign_core.output_tokens if self.campaign_core and _is_opus(self.campaign_core.model or "") else 0
        pal_out  = self.arc_palette.output_tokens if self.arc_palette else 0
        return core_out + pal_out + self.m2_output

    @property
    def opus_total_cost(self) -> float:
        pal_cost  = self.arc_palette.cost if self.arc_palette else 0.0
        core_cost = self.campaign_core.cost if self.campaign_core and _is_opus(self.campaign_core.model or "") else 0.0
        return pal_cost + core_cost + self.m2_cost

    @property
    def haiku_total_cost(self) -> float:
        if self.table_b_node_events:
            tb_cost = sum(e.cost for e in self.table_b_node_events)
        else:
            tb_cost = self.table_b.cost if self.table_b else 0.0
        core_cost = self.campaign_core.cost if self.campaign_core and not _is_opus(self.campaign_core.model or "") else 0.0
        return tb_cost + core_cost

    @property
    def total_api_cost(self) -> float:
        return self.opus_total_cost + self.haiku_total_cost

    @property
    def local_tokens(self) -> int:
        return self.fast_total

    @property
    def saved_remote_tokens(self) -> int:
        return self.fast_total

    @property
    def local_saved_vs_haiku(self) -> float:
        return self.fast_eval * HAIKU_OUTPUT

    @property
    def local_saved_vs_opus(self) -> float:
        return self.fast_eval * OPUS_OUTPUT


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_timestamp(raw: str) -> datetime:
    return datetime.strptime(raw, TIME_FORMAT)


def load_campaign_metadata(
    campaign_dir: Path,
) -> tuple[dict[str, set[str]], dict[str, str], dict[str, set[str]]]:
    node_index: dict[str, set[str]] = {}
    titles: dict[str, str] = {}
    campaign_nodes: dict[str, set[str]] = {}
    for path in sorted(campaign_dir.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        campaign_id = data.get("campaign_id", path.stem)
        titles[campaign_id] = data.get("title", campaign_id)
        campaign_nodes[campaign_id] = set(data.get("nodes", {}))
        for node_id in data.get("nodes", {}):
            node_index.setdefault(node_id, set()).add(campaign_id)
    return node_index, titles, campaign_nodes


def parse_arc_palette_events(lines: list[str]) -> list[ArcPaletteEvent]:
    events: list[ArcPaletteEvent] = []
    pending: ArcPaletteEvent | None = None
    for idx, line in enumerate(lines, start=1):
        if RE_ARC_PALETTE.match(line):
            m = RE_ARC_PALETTE.match(line)
            pending = ArcPaletteEvent(line_no=idx, timestamp=parse_timestamp(m.group("ts")))  # type: ignore[union-attr]
            continue
        if pending is None:
            continue
        tok = RE_SLOW_TOKENS.match(line)
        if tok:
            pending.input_tokens  = int(tok.group("input"))
            pending.output_tokens = int(tok.group("output"))
            events.append(pending)
            pending = None
        elif line.startswith("## ["):
            pending = None
    return events


def parse_campaign_core_events(lines: list[str]) -> list[CampaignCoreEvent]:
    events: list[CampaignCoreEvent] = []
    pending: CampaignCoreEvent | None = None
    for idx, line in enumerate(lines, start=1):
        m = RE_CAMPAIGN_CORE.match(line)
        if m:
            pending = CampaignCoreEvent(
                line_no=idx,
                timestamp=parse_timestamp(m.group("ts")),
                campaign_id=m.group("campaign"),
            )
            events.append(pending)
            continue
        if pending is None:
            continue
        if line.startswith("provider: "):
            pending.provider = line.partition(": ")[2]
        elif line.startswith("model: "):
            pending.model = line.partition(": ")[2]
        elif line.startswith("theme: "):
            pending.theme = line.partition(": ")[2]
        elif line.startswith("title: "):
            pending.title = line.partition(": ")[2]
        else:
            tok = RE_SLOW_TOKENS.match(line)
            if tok:
                pending.input_tokens  = int(tok.group("input"))
                pending.output_tokens = int(tok.group("output"))
                pending = None
        if line.startswith("## [") and not RE_CAMPAIGN_CORE.match(line):
            pending = None
    return events


def parse_table_b_events(
    lines: list[str],
    node_index: dict[str, set[str]] | None = None,
) -> list[TableBEvent]:
    """Parse TABLE B RESPONSE (campaign-level) and TABLE B NODE RESPONSE (node-level) entries."""
    events: list[TableBEvent] = []
    pending: TableBEvent | None = None
    for idx, line in enumerate(lines, start=1):
        m = RE_TABLE_B.match(line)
        if m:
            pending = TableBEvent(
                line_no=idx,
                timestamp=parse_timestamp(m.group("ts")),
                campaign_id=m.group("campaign"),
            )
            continue
        mn = RE_TABLE_B_NODE.match(line)
        if mn:
            node = mn.group("node")
            campaign = next(iter((node_index or {}).get(node, set())), "")
            pending = TableBEvent(
                line_no=idx,
                timestamp=parse_timestamp(mn.group("ts")),
                campaign_id=campaign,
                node_id=node,
            )
            continue
        if pending is None:
            continue
        tok = RE_SLOW_TOKENS.match(line)
        if tok:
            pending.input_tokens  = int(tok.group("input"))
            pending.output_tokens = int(tok.group("output"))
            events.append(pending)
            pending = None
        elif line.startswith("## ["):
            pending = None
    return events


def parse_request_events(lines: list[str], node_index: dict[str, set[str]]) -> list[RequestEvent]:
    events: list[RequestEvent] = []
    for idx, line in enumerate(lines, start=1):
        slow_m = RE_SLOW_REQUEST.match(line)
        m2_m   = RE_M2_REQUEST.match(line)
        if slow_m:
            ts, node = parse_timestamp(slow_m.group("ts")), slow_m.group("node")
        elif m2_m:
            ts, node = parse_timestamp(m2_m.group("ts")), m2_m.group("node")
        else:
            continue
        events.append(RequestEvent(
            line_no=idx,
            timestamp=ts,
            node_id=node,
            campaign_candidates=set(node_index.get(node, set())),
        ))
    return events


def group_runs(requests: list[RequestEvent], total_lines: int) -> list[RunGroup]:
    if not requests:
        return []
    runs: list[RunGroup] = []
    current_events: list[RequestEvent] = [requests[0]]
    current_candidates = set(requests[0].campaign_candidates)

    for event in requests[1:]:
        cur = current_candidates or set()
        ev  = event.campaign_candidates or set()
        if cur and ev:
            intersection = cur & ev
            same = bool(intersection)
        else:
            intersection = cur or ev
            same = True
        if same:
            current_events.append(event)
            current_candidates = intersection
            continue
        runs.append(RunGroup(
            start_line=current_events[0].line_no,
            end_line=event.line_no - 1,
            request_events=current_events,
            campaign_candidates=current_candidates,
        ))
        current_events = [event]
        current_candidates = set(event.campaign_candidates)

    runs.append(RunGroup(
        start_line=current_events[0].line_no,
        end_line=total_lines,
        request_events=current_events,
        campaign_candidates=current_candidates,
    ))
    return runs


def _split_arb_id(arb_id: str) -> str:
    for sep in ("_tb_", "_gen_"):
        if sep in arb_id:
            return arb_id.rsplit(sep, 1)[0]
    return arb_id


# ---------------------------------------------------------------------------
# Run analysis
# ---------------------------------------------------------------------------

def analyze_run(
    lines: list[str],
    run: RunGroup,
    campaign_titles: dict[str, str],
    arc_palette_events: list[ArcPaletteEvent] | None = None,
    campaign_core_events: list[CampaignCoreEvent] | None = None,
    table_b_events: list[TableBEvent] | None = None,
    campaign_nodes: dict[str, set[str]] | None = None,
) -> RunReport:
    # Determine start timestamp from first request line
    first_line = lines[run.start_line - 1]
    ts_m = RE_TIMESTAMP.match(first_line)
    start_ts = parse_timestamp(ts_m.group("ts")) if ts_m else datetime.utcnow()
    end_ts = start_ts

    node_order: list[str] = []
    node_usage: dict[str, NodeUsage] = {}

    for event in run.request_events:
        if event.node_id not in node_order:
            node_order.append(event.node_id)

    # State machine over log lines in this run's range
    current_slow_node: str | None = None   # persists across multiple SLOW RESPONSE/token pairs
    pending_slow_node: str | None = None   # set when a token line is expected for slow core
    pending_fast_node: str | None = None
    pending_m2_node:   str | None = None
    job_arb_count: dict[str, int] = {}  # node_id → expected arb count

    for line in lines[run.start_line - 1 : run.end_line]:
        ts_m = RE_TIMESTAMP.match(line)
        if ts_m:
            end_ts = parse_timestamp(ts_m.group("ts"))

        slow_req = RE_SLOW_REQUEST.match(line)
        if slow_req:
            nid = slow_req.group("node")
            node_usage.setdefault(nid, NodeUsage())
            current_slow_node = nid
            pending_slow_node = nid
            pending_fast_node = pending_m2_node = None
            continue

        arb_cnt = RE_ARB_COUNT.match(line)
        if arb_cnt and current_slow_node:
            job_arb_count[current_slow_node] = int(arb_cnt.group("count"))
            continue

        slow_resp = RE_SLOW_RESPONSE.match(line)
        if slow_resp:
            # Re-activate pending_slow_node so the upcoming token line is attributed correctly
            pending_slow_node = current_slow_node
            pending_fast_node = pending_m2_node = None
            continue

        fast_resp = RE_FAST_RESPONSE.match(line)
        if fast_resp:
            pending_fast_node = _split_arb_id(fast_resp.group("arb"))
            node_usage.setdefault(pending_fast_node, NodeUsage())
            pending_slow_node = pending_m2_node = None
            continue

        m2_resp = RE_M2_RESPONSE.match(line)
        if m2_resp:
            pending_m2_node = m2_resp.group("node")
            node_usage.setdefault(pending_m2_node, NodeUsage())
            pending_slow_node = pending_fast_node = None
            continue

        # Token lines
        slow_tok = RE_SLOW_TOKENS.match(line)
        if slow_tok:
            if pending_m2_node is not None:
                # This is an M2 token line — try to capture cache fields
                m2_tok = RE_M2_TOKENS.match(line)
                usage = node_usage.setdefault(pending_m2_node, NodeUsage())
                usage.m2_calls   += 1
                usage.m2_input   += int(slow_tok.group("input"))
                usage.m2_output  += int(slow_tok.group("output"))
                if m2_tok:
                    usage.m2_cache_read    += int(m2_tok.group("cr") or 0)
                    usage.m2_cache_created += int(m2_tok.group("cc") or 0)
                pending_m2_node = None
            elif pending_slow_node is not None:
                usage = node_usage.setdefault(pending_slow_node, NodeUsage())
                usage.slow_calls  += 1
                usage.slow_input  += int(slow_tok.group("input"))
                usage.slow_output += int(slow_tok.group("output"))
                pending_slow_node = None
            continue

        fast_tok = RE_FAST_TOKENS.match(line)
        if fast_tok and pending_fast_node is not None:
            usage = node_usage.setdefault(pending_fast_node, NodeUsage())
            usage.fast_calls  += 1
            usage.fast_prompt += int(fast_tok.group("prompt"))
            usage.fast_eval   += int(fast_tok.group("eval"))
            pending_fast_node = None
            continue

    # Build RunReport
    campaign_id = (
        next(iter(run.campaign_candidates))
        if len(run.campaign_candidates) == 1
        else None
    )
    report = RunReport(
        start_line=run.start_line,
        end_line=run.end_line,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
        campaign_id=campaign_id,
        campaign_title=campaign_titles.get(campaign_id, campaign_id) if campaign_id else None,
        node_order=node_order,
        node_usage=node_usage,
    )

    # Associate offline events
    if arc_palette_events:
        eligible = [e for e in arc_palette_events if e.timestamp <= start_ts]
        if eligible:
            report.arc_palette = eligible[-1]

    if campaign_core_events and campaign_id:
        eligible_cc = [
            e for e in campaign_core_events
            if e.campaign_id == campaign_id and e.timestamp <= start_ts
        ]
        if eligible_cc:
            report.campaign_core = eligible_cc[-1]

    if table_b_events and campaign_id:
        eligible_tb = [
            e for e in table_b_events
            if e.campaign_id == campaign_id and e.timestamp <= start_ts
        ]
        if eligible_tb:
            node_events = [e for e in eligible_tb if e.node_id]
            if node_events:
                report.table_b_node_events = node_events
            else:
                report.table_b = eligible_tb[-1]

    # Aggregate runtime totals
    for usage in node_usage.values():
        report.slow_calls       += usage.slow_calls
        report.slow_input       += usage.slow_input
        report.slow_output      += usage.slow_output
        report.fast_calls       += usage.fast_calls
        report.fast_prompt      += usage.fast_prompt
        report.fast_eval        += usage.fast_eval
        report.m2_calls         += usage.m2_calls
        report.m2_input         += usage.m2_input
        report.m2_output        += usage.m2_output
        report.m2_cache_read    += usage.m2_cache_read
        report.m2_cache_created += usage.m2_cache_created

    return report


def _has_runtime_usage(report: RunReport) -> bool:
    return (report.slow_calls + report.fast_calls + report.m2_calls) > 0


def select_run(
    runs: list[RunGroup],
    campaign_id: str | None,
    *,
    lines: list[str] | None = None,
    campaign_titles: dict[str, str] | None = None,
    campaign_core_events: list[CampaignCoreEvent] | None = None,
) -> RunGroup:
    if not runs:
        raise SystemExit("No runtime generation requests found in the log.")
    candidates = runs if campaign_id is None else [
        r for r in runs if campaign_id in r.campaign_candidates
    ]
    if not candidates:
        raise SystemExit(f"No runs matched campaign '{campaign_id}'.")
    if lines is not None and campaign_titles is not None:
        for run in reversed(candidates):
            report = analyze_run(lines, run, campaign_titles)
            if _has_runtime_usage(report):
                return run
    return candidates[-1]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _tok(n: int) -> str:
    """Format token count with comma separator."""
    return f"{n:,}"


def _usd(amount: float) -> str:
    if amount == 0.0:
        return "$0.0000"
    if amount < 0.01:
        return f"${amount:.4f}"
    return f"${amount:.4f}"


def _row(label: str, model: str, inp: int, out: int, cost: float, extra: str = "") -> str:
    return (
        f"  {label:<18} {model:<22} in={_tok(inp):<8} out={_tok(out):<8} {_usd(cost)}"
        + (f"  {extra}" if extra else "")
    )


def render_report(report: RunReport) -> str:
    title = report.campaign_title or "(unresolved)"
    if report.campaign_id:
        title = f"{title}  [{report.campaign_id}]"
    dur = int((report.end_timestamp - report.start_timestamp).total_seconds())

    lines = [
        "─" * 66,
        "  LLM USAGE REPORT",
        f"  campaign : {title}",
        f"  run      : {report.start_timestamp.strftime(TIME_FORMAT)}"
        + (f"  (+{dur}s)" if dur > 0 else ""),
        f"  nodes    : {', '.join(report.node_order) if report.node_order else '(none)'}",
        "─" * 66,
    ]

    # ── OFFLINE ──────────────────────────────────────────────────────────
    lines.append("")
    lines.append("  OFFLINE  (one-time / per-campaign)")
    lines.append(f"  {'label':<18} {'model':<22} {'input':<13} {'output':<13} cost")
    lines.append("  " + "─" * 62)

    offline_opus_cost  = 0.0
    offline_haiku_cost = 0.0

    if report.arc_palette:
        ap = report.arc_palette
        lines.append(_row("arc palette", "claude-opus-4-6", ap.input_tokens, ap.output_tokens, ap.cost,
                          f"(one-time, {_usd(ap.cost)})"))
        offline_opus_cost += ap.cost

    if report.campaign_core:
        cc = report.campaign_core
        m = cc.model or "?"
        theme_short = (cc.theme or "")[:50]
        lines.append(_row("campaign graph", m, cc.input_tokens, cc.output_tokens, cc.cost,
                          f'"{theme_short}"'))
        if _is_opus(m):
            offline_opus_cost += cc.cost
        else:
            offline_haiku_cost += cc.cost
    else:
        lines.append("  campaign graph     (not found in log before this run)")

    if report.table_b_node_events:
        tb_in  = report.table_b_input
        tb_out = report.table_b_output
        tb_cost = sum(e.cost for e in report.table_b_node_events)
        lines.append("")
        lines.append("  preloaded assets:")
        lines.append(
            f"    table b: nodes={report.table_b_nodes} input={tb_in} output={tb_out} total={tb_in + tb_out}"
        )
        offline_haiku_cost += tb_cost
    elif report.table_b:
        tb = report.table_b
        lines.append(_row("table b", "claude-haiku-4-5", tb.input_tokens, tb.output_tokens, tb.cost))
        offline_haiku_cost += tb.cost
    else:
        lines.append("  table b            (not found in log before this run)")

    offline_remote_tokens = (
        (report.campaign_core.input_tokens + report.campaign_core.output_tokens if report.campaign_core else 0)
        + report.table_b_input + report.table_b_output
        + (report.arc_palette.input_tokens + report.arc_palette.output_tokens if report.arc_palette else 0)
    )

    lines.append("")
    if offline_remote_tokens:
        lines.append(f"  offline remote:  {offline_remote_tokens}")
    if offline_opus_cost:
        lines.append(f"  offline opus total:   {_usd(offline_opus_cost)}")
    if offline_haiku_cost:
        lines.append(f"  offline haiku total:  {_usd(offline_haiku_cost)}")

    # ── RUNTIME ──────────────────────────────────────────────────────────
    lines.append("")
    lines.append("─" * 66)
    lines.append("")
    lines.append("  RUNTIME  (per session)")
    lines.append(f"  {'label':<18} {'model':<22} {'input':<13} {'output':<13} cost")
    lines.append("  " + "─" * 62)

    if report.m2_calls:
        cr = report.m2_cache_read
        savings = report.m2_cache_savings
        cr_note = f"cache_read={_tok(cr)} saved={_usd(savings)}" if cr else ""
        lines.append(_row(
            f"m2 classifier ×{report.m2_calls}",
            "claude-opus-4-6",
            report.m2_input, report.m2_output,
            report.m2_cost,
            cr_note,
        ))

    if report.slow_calls:
        slow_cost = opus_cost(report.slow_input, report.slow_output)
        lines.append(_row(
            f"slow core ×{report.slow_calls}",
            "deepseek-chat",
            report.slow_input, report.slow_output,
            slow_cost,
        ))

    local_tok = report.fast_total
    lines.append(
        f"  {'fast core ×' + str(report.fast_calls):<18} {'gemma3:4b (local)':<22}"
        f" prompt={_tok(report.fast_prompt):<6} eval={_tok(report.fast_eval):<6}"
        f" FREE  ({_tok(local_tok)} local tokens)"
    )

    # ── TOTALS ───────────────────────────────────────────────────────────
    lines.append("")
    lines.append("─" * 66)
    lines.append("")
    lines.append("  TOTALS")
    lines.append("")

    total_opus_cost  = offline_opus_cost + report.m2_cost
    total_haiku_cost = offline_haiku_cost
    total_api_cost   = total_opus_cost + total_haiku_cost

    lines.append(f"  {'opus (all)':<28}  {_usd(total_opus_cost)}")
    if total_haiku_cost:
        lines.append(f"  {'haiku (table b)':<28}  {_usd(total_haiku_cost)}")
    lines.append(f"  {'─' * 40}")
    lines.append(f"  {'total API spend':<28}  {_usd(total_api_cost)}")

    lines.append("")
    lines.append(f"  local tokens (gemma3):    {_tok(local_tok)}")
    saved_h = report.local_saved_vs_haiku
    saved_o = report.local_saved_vs_opus
    lines.append(f"  saved vs haiku:           ~{_usd(saved_h)}  ({_tok(report.fast_eval)} eval tokens)")
    lines.append(f"  saved vs opus:            ~{_usd(saved_o)}")

    if report.m2_cache_read:
        lines.append(f"  opus cache savings:       ~{_usd(report.m2_cache_savings)}  ({_tok(report.m2_cache_read)} cache_read tokens)")

    # ── PER NODE ─────────────────────────────────────────────────────────
    if report.node_usage:
        lines.append("")
        lines.append("─" * 66)
        lines.append("")
        lines.append("  PER NODE")
        lines.append("")
        for node_id in report.node_order:
            usage = report.node_usage.get(node_id, NodeUsage())
            parts = []
            if usage.m2_calls:
                parts.append(
                    f"m2={_tok(usage.m2_total)} ({_usd(usage.m2_cost)}"
                    + (f", saved={_usd(usage.m2_cache_savings)}" if usage.m2_cache_read else "")
                    + ")"
                )
            if usage.slow_calls:
                parts.append(f"slow={_tok(usage.slow_total)} calls={usage.slow_calls}")
            if usage.fast_calls:
                parts.append(f"fast={_tok(usage.fast_total)} local (calls={usage.fast_calls})")
            lines.append(f"  {node_id}: " + "  ".join(parts))

    lines.append("")
    lines.append("─" * 66)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize token usage from logs/llm.md.")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--campaign", help="Campaign id (default: latest run).")
    parser.add_argument("--campaign-dir", type=Path, default=DEFAULT_CAMPAIGNS)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with args.log.open(encoding="utf-8") as fh:
        lines = [line.rstrip("\n") for line in fh]

    node_index, campaign_titles, campaign_nodes = load_campaign_metadata(args.campaign_dir)
    arc_palette_events   = parse_arc_palette_events(lines)
    campaign_core_events = parse_campaign_core_events(lines)
    table_b_events       = parse_table_b_events(lines, node_index)
    request_events       = parse_request_events(lines, node_index)
    runs = group_runs(request_events, len(lines))

    run = select_run(
        runs,
        args.campaign,
        lines=lines,
        campaign_titles=campaign_titles,
        campaign_core_events=campaign_core_events,
    )
    report = analyze_run(
        lines,
        run,
        campaign_titles,
        arc_palette_events=arc_palette_events,
        campaign_core_events=campaign_core_events,
        table_b_events=table_b_events,
        campaign_nodes=campaign_nodes,
    )
    print(render_report(report))


if __name__ == "__main__":
    main()
