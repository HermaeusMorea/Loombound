from report_llm_usage import (
    analyze_run,
    group_runs,
    parse_campaign_core_events,
    parse_request_events,
    parse_t1_cache_table_events,
    render_report,
    select_run,
)


def test_dynamic_run_report_matches_expected_totals() -> None:
    lines = [
        "## [2026-04-15 10:00:00 UTC] SLOW CORE REQUEST — node `demo_node`",
        "encounter_count: 2",
        "## [2026-04-15 10:00:02 UTC] SLOW CORE RESPONSE — seed `seed_demo_00` (1/2)",
        "tokens — input: 200  output: 50  cache_created: 0  cache_read: 0",
        "## [2026-04-15 10:00:03 UTC] FAST CORE RESPONSE — `demo_node_gen_00`",
        "tokens — prompt: 80  eval: 40",
        "## [2026-04-15 10:00:04 UTC] SLOW CORE RESPONSE — seed `seed_demo_01` (2/2)",
        "tokens — input: 120  output: 30  cache_created: 0  cache_read: 0",
        "## [2026-04-15 10:00:05 UTC] FAST CORE RESPONSE — `demo_node_gen_01`",
        "tokens — prompt: 50  eval: 25",
        "## [2026-04-15 10:00:06 UTC] COMPLETE — `demo_node` (2 encounter(s) ready)",
    ]
    node_index = {"demo_node": {"demo_campaign"}}
    campaign_titles = {"demo_campaign": "Demo Campaign"}

    requests = parse_request_events(lines, node_index)
    runs = group_runs(requests, len(lines))
    report = analyze_run(lines, runs[0], campaign_titles)

    assert report.saga_id == "demo_campaign"
    assert report.node_order == ["demo_node"]
    assert report.slow_calls == 2
    assert report.slow_input == 320
    assert report.slow_output == 80
    assert report.fast_calls == 2
    assert report.fast_prompt == 130
    assert report.fast_eval == 65
    assert report.saved_remote_tokens == 195


def test_campaign_core_and_table_b_usage_are_tracked_separately() -> None:
    lines = [
        "## [2026-04-15 09:58:00 UTC] CAMPAIGN CORE RESPONSE — `demo_campaign`",
        "provider: anthropic",
        "model: claude-opus-4-6",
        "theme: orbital salvage mutiny",
        "tokens — input: 1200  output: 300",
        "",
        "## [2026-04-15 09:59:00 UTC] T1 CACHE NODE RESPONSE — `demo_node_a`",
        "tokens — input: 150  output: 60",
        "## [2026-04-15 09:59:02 UTC] T1 CACHE NODE RESPONSE — `demo_node_b`",
        "tokens — input: 170  output: 50",
        "",
        "## [2026-04-15 10:05:00 UTC] M2 CLASSIFIER REQUEST — node `demo_node_a`",
        "## [2026-04-15 10:05:01 UTC] M2 CLASSIFIER RESPONSE — node `demo_node_a` entry_id=7",
        "tokens — input: 200  output: 20  cache_created: 0  cache_read: 180",
        "## [2026-04-15 10:05:02 UTC] FAST CORE RESPONSE (preloaded) — `demo_node_a_tb_00`",
        "tokens — prompt: 80  eval: 40",
        "## [2026-04-15 10:05:03 UTC] COMPLETE (preloaded) — `demo_node_a` (1 encounter(s), entry_id=7)",
    ]
    node_index = {
        "demo_node_a": {"demo_campaign"},
        "demo_node_b": {"demo_campaign"},
    }
    campaign_titles = {"demo_campaign": "Demo Campaign"}
    campaign_nodes = {"demo_campaign": {"demo_node_a", "demo_node_b"}}

    requests = parse_request_events(lines, node_index)
    runs = group_runs(requests, len(lines))
    campaign_core_events = parse_campaign_core_events(lines)
    t1_cache_table_events = parse_t1_cache_table_events(lines, node_index)
    report = analyze_run(
        lines,
        runs[0],
        campaign_titles,
        campaign_core_events=campaign_core_events,
        t1_cache_table_events=t1_cache_table_events,
        campaign_nodes=campaign_nodes,
    )

    assert report.campaign_core is not None
    assert report.campaign_core.provider == "anthropic"
    assert report.campaign_core.input_tokens == 1200
    assert report.campaign_core.output_tokens == 300
    assert report.t1_cache_table_calls == 2
    assert report.t1_cache_table_nodes == 2
    assert report.t1_cache_table_input == 320
    assert report.t1_cache_table_output == 110
    assert report.m2_calls == 1
    assert report.m2_input == 200
    assert report.m2_output == 20
    assert report.fast_total == 120

    rendered = render_report(report)
    assert "preloaded assets:" in rendered
    assert "t1 cache: nodes=2 input=320 output=110 total=430" in rendered
    assert "offline remote:  1930" in rendered


def test_select_run_prefers_latest_run_with_actual_runtime_usage() -> None:
    lines = [
        "## [2026-04-15 10:00:00 UTC] M2 CLASSIFIER REQUEST — node `demo_node`",
        "## [2026-04-15 10:00:01 UTC] M2 CLASSIFIER RESPONSE — node `demo_node` entry_id=4",
        "tokens — input: 200  output: 50  cache_created: 0  cache_read: 0",
        "## [2026-04-15 10:00:02 UTC] FAST CORE RESPONSE (preloaded) — `demo_node_tb_00`",
        "tokens — prompt: 80  eval: 40",
        "## [2026-04-15 10:00:03 UTC] COMPLETE (preloaded) — `demo_node` (1 encounter(s), entry_id=4)",
        "",
        "## [2026-04-15 10:05:00 UTC] M2 CLASSIFIER REQUEST — node `demo_node`",
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
