from pathlib import Path

from report_llm_usage import (
    analyze_run,
    group_runs,
    load_campaign_index,
    parse_campaign_core_events,
    parse_request_events,
    select_run,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "logs" / "llm.md"
CAMPAIGN_DIR = REPO_ROOT / "data" / "campaigns"


def _load_runs():
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    node_index, campaign_titles = load_campaign_index(CAMPAIGN_DIR)
    requests = parse_request_events(lines, node_index)
    runs = group_runs(requests, len(lines))
    return lines, campaign_titles, runs


def _find_full_wall_street_run(runs):
    expected = [
        "midnight_trading_floor",
        "informant_bar",
        "vault_of_ledgers",
        "rooftop_rest",
        "board_ritual",
    ]
    for run in runs:
        node_order = [event.node_id for event in run.request_events]
        if node_order == expected:
            return run
    raise AssertionError("Expected full wall_street_dark_secrets run not found in logs/llm.md")


def test_wall_street_report_matches_expected_totals():
    lines, campaign_titles, runs = _load_runs()

    report = analyze_run(
        lines,
        _find_full_wall_street_run(runs),
        campaign_titles,
    )

    assert report.campaign_id == "wall_street_dark_secrets"
    assert report.slow_calls == 12
    assert report.slow_input == 21656
    assert report.slow_output == 6499
    assert report.fast_calls == 12
    assert report.fast_prompt == 10656
    assert report.fast_eval == 7505
    assert report.saved_remote_tokens == 18161


def test_wall_street_report_keeps_expected_node_order():
    lines, campaign_titles, runs = _load_runs()

    report = analyze_run(
        lines,
        _find_full_wall_street_run(runs),
        campaign_titles,
    )

    assert report.campaign_title == "华尔街：深渊账本"
    assert report.node_order == [
        "midnight_trading_floor",
        "informant_bar",
        "vault_of_ledgers",
        "rooftop_rest",
        "board_ritual",
    ]


def test_campaign_core_usage_is_tracked_separately_from_runtime_usage():
    lines = [
        "## [2026-04-15 10:00:00 UTC] CAMPAIGN CORE RESPONSE — `demo_campaign`",
        "provider: anthropic",
        "model: claude-opus-4-6",
        "theme: orbital salvage mutiny",
        "tokens — input: 1200  output: 300",
        "",
        "## [2026-04-15 10:05:00 UTC] SLOW CORE REQUEST — node `demo_node`",
        "arbitration_count: 1",
        "## [2026-04-15 10:05:05 UTC] SLOW CORE RESPONSE — seed `seed_demo` (1/1)",
        "tokens — input: 200  output: 50  cache_created: 0  cache_read: 0",
        "## [2026-04-15 10:05:06 UTC] FAST CORE RESPONSE — `demo_node_gen_00`",
        "tokens — prompt: 80  eval: 40",
        "## [2026-04-15 10:05:07 UTC] COMPLETE — `demo_node` (1 arbitration(s) ready)",
    ]
    node_index = {"demo_node": {"demo_campaign"}}
    campaign_titles = {"demo_campaign": "Demo Campaign"}
    requests = parse_request_events(lines, node_index)
    runs = group_runs(requests, len(lines))
    campaign_core_events = parse_campaign_core_events(lines)

    report = analyze_run(
        lines,
        runs[0],
        campaign_titles,
        campaign_core_events=campaign_core_events,
    )

    assert report.campaign_core is not None
    assert report.campaign_core.provider == "anthropic"
    assert report.campaign_core.input_tokens == 1200
    assert report.campaign_core.output_tokens == 300
    assert report.slow_total == 250
    assert report.fast_total == 120
    assert report.saved_remote_tokens == 120


def test_select_run_prefers_latest_run_with_actual_runtime_usage() -> None:
    lines = [
        "## [2026-04-15 10:00:00 UTC] SLOW CORE REQUEST — node `demo_node`",
        "arbitration_count: 1",
        "## [2026-04-15 10:00:02 UTC] SLOW CORE RESPONSE — seed `seed_demo` (1/1)",
        "tokens — input: 200  output: 50  cache_created: 0  cache_read: 0",
        "## [2026-04-15 10:00:03 UTC] FAST CORE RESPONSE — `demo_node_gen_00`",
        "tokens — prompt: 80  eval: 40",
        "## [2026-04-15 10:00:04 UTC] COMPLETE — `demo_node` (1 arbitration(s) ready)",
        "",
        "## [2026-04-15 10:05:00 UTC] SLOW CORE REQUEST — node `demo_node`",
        "arbitration_count: 1",
    ]
    node_index = {"demo_node": {"demo_campaign"}}
    campaign_titles = {"demo_campaign": "Demo Campaign"}
    requests = parse_request_events(lines, node_index)
    runs = group_runs(requests, len(lines))

    selected = select_run(
        runs,
        "demo_campaign",
        lines=lines,
        campaign_titles=campaign_titles,
        campaign_core_events=parse_campaign_core_events(lines),
    )

    assert selected.start_line == 1
