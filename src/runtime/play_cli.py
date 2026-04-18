"""Interactive CLI loop for playing a small Loombound campaign."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from src.t2.core import load_rules, load_templates
from src.t0.memory import ArbitrationResult
from src.t0.core import apply_option_effects, enforce_rule
from src.t2.core import M2Classifier, M2ClassifierConfig, PrefetchCache
from src.t2.core.collector import build_classifier_input, build_m1_entry
from src.t1.core.fast_core import FastCoreConfig
from src.t0.memory import append_node_event, record_choice, update_after_node
from src.t1.core import render_narration
from src.t0.core import (
    pause,
    render_arbitration_view,
    render_choices,
    render_input_panel,
    render_map_hud,
    render_node_header,
    render_result,
    render_run_complete,
    render_run_intro,
)
from src.t0.core import build_selection_trace, evaluate_rules, select_rule
from src.runtime.campaign import (
    REPO_ROOT,
    choose_index,
    make_run,
    resolve_asset_path,
    sync_arbitration_resources,
)
from src.t0.core import build_signals, score_themes
from src.t0.core import (
    AssetValidationError,
    load_json_asset,
    validate_arbitration_asset,
)


log = logging.getLogger(__name__)

RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"
T2_CACHE_PATH = REPO_ROOT / "data" / "t2_cache_table.json"


# ---------------------------------------------------------------------------
# .env loader (no external dependency needed)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from .env at repo root into os.environ.

    Uses os.environ.setdefault so existing shell exports are never overwritten.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)



def _parse_arbitrations(node_spec: dict) -> tuple[int, list[dict]]:
    """Return (llm_count, authored_specs) from a node spec's 'arbitrations' field.

    Two formats are supported:
      int   → LLM-generated mode; llm_count = that integer, authored_specs = []
      list  → Authored mode;      llm_count = 0, authored_specs = the list
    """
    field = node_spec.get("arbitrations", [])
    if isinstance(field, int):
        return field, []
    return 0, field


def _overlay_effects(payload: dict, opus_effects: dict[str, dict]) -> None:
    """Patch Opus-assigned numeric effect values into a payload's option metadata in-place.

    Only the three stat keys are touched; add_events / add_conditions written by
    gemma3 are preserved. The payload dict is mutated directly.
    """
    for opt in payload.get("options", []):
        opt_id = opt.get("option_id", "")
        if opt_id in opus_effects:
            eff = opt.setdefault("metadata", {}).setdefault("effects", {})
            for key in ("health_delta", "money_delta", "sanity_delta"):
                eff[key] = opus_effects[opt_id].get(key, 0)
            verdict = opus_effects[opt_id].get("verdict", "")
            if verdict:
                opt["verdict"] = verdict


def _play_arbitration(
    run,
    node,
    payload: dict[str, object],
    templates: dict[str, list[str]],
    rules,
    prefetch: PrefetchCache | None,
    arb_idx: int,
    campaign_node_id: str,
    total_arbs: int,
) -> None:
    # Overlay Opus-assigned effects before loading (may be empty dict on cache miss)
    if prefetch is not None:
        opus_effects = prefetch.consume_arb_effects(campaign_node_id, arb_idx)
        if opus_effects:
            _overlay_effects(payload, opus_effects)

    arbitration = node.load_current_arbitration(payload)
    sync_arbitration_resources(run, arbitration)
    append_node_event(
        node.memory,
        "arbitration_loaded",
        arbitration_id=arbitration.arbitration_id,
        scene_type=arbitration.context.scene_type,
        context_id=arbitration.context.context_id,
    )

    signals = build_signals(arbitration)
    theme_scores = score_themes(arbitration, signals)
    evaluations = evaluate_rules(arbitration, rules, theme_scores)
    node.rule_state.reset_for_arbitration()
    node.rule_state.record_evaluations(evaluations)
    selected = select_rule(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    node.rule_state.record_selected_rule(selected.rule.id if selected else None)
    node.rule_state.record_selection_trace(
        build_selection_trace(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    )
    run.rule_system.record_selected_rule(selected.rule.id if selected else None)
    append_node_event(
        node.memory,
        "rule_selected",
        arbitration_id=arbitration.arbitration_id,
        selected_rule_id=selected.rule.id if selected else None,
        matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
    )

    option_results = enforce_rule(arbitration, selected.rule if selected else None)
    narration = render_narration(
        arbitration=arbitration,
        rule=selected.rule if selected else None,
        templates=templates,
        enabled=True,
    )

    render_arbitration_view(run, arbitration, selected.rule if selected else None)
    render_choices(option_results)
    render_input_panel("Choose an option")

    choice_index = choose_index("> ", len(option_results))
    chosen_result = option_results[choice_index]
    arbitration.select_option(chosen_result.option_id)
    selected_option = arbitration.get_option(chosen_result.option_id) or {}

    record_choice(
        node.memory,
        arbitration=arbitration,
        selected_rule_id=selected.rule.id if selected else None,
        selected_rule_theme=selected.rule.theme if selected else None,
        selected_result=chosen_result,
    )
    append_node_event(
        node.memory,
        "option_chosen",
        arbitration_id=arbitration.arbitration_id,
        option_id=chosen_result.option_id,
        verdict=chosen_result.verdict,
        sanity_delta=chosen_result.sanity_cost,
    )

    # Fire-and-forget Opus call: updates arc entry_id + assigns effects for next arb.
    # Within a node: next_node_id = campaign_node_id, next_arb_idx = arb_idx + 1.
    # Last arb of a node: pass None/None — only entry_id is updated; the main loop
    # triggers the Opus call for the first arb of the chosen next node.
    if prefetch is not None:
        _is_last = arb_idx >= total_arbs - 1
        _next_node = campaign_node_id if not _is_last else None
        _next_idx  = arb_idx + 1       if not _is_last else None
        quasi = build_classifier_input(
            run.core_state, run.memory, list(run.node_history),
            current_node_memory=node.memory,
        )
        prefetch.update_arc_state(quasi, _next_node, _next_idx)

    applied_notes = apply_option_effects(run, selected_option, chosen_result)
    arbitration.set_result(
        ArbitrationResult(
            selected_rule_id=selected.rule.id if selected else None,
            matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
            option_results=option_results,
            sanity_delta=chosen_result.sanity_cost,
            theme_scores=theme_scores,
            narration=narration,
        )
    )
    arbitration.mark_applied()
    node.close_current_arbitration()
    append_node_event(
        node.memory,
        "arbitration_finalized",
        arbitration_id=arbitration.arbitration_id,
        selected_rule_id=selected.rule.id if selected else None,
        player_choice=chosen_result.option_id,
    )

    render_result(run, chosen_result, narration, applied_notes)
    pause()


def _play_node(
    run,
    campaign: dict[str, object],
    campaign_node: dict[str, object],
    rules,
    templates: dict[str, list[str]],
    prefetch: PrefetchCache | None = None,
    campaign_node_id: str | None = None,
) -> object | None:
    floor: int = campaign_node["floor"]
    node_type: str = campaign_node["node_type"]
    node_id = f"{campaign_node_id}:floor_{floor:02d}"

    run.core_state.floor = floor
    run.core_state.scene_type = node_type

    node = run.start_node(node_id=node_id, node_type=node_type, floor=floor)
    append_node_event(node.memory, "node_entered", node_id=node.node_id, node_type=node.node_type, floor=node.floor)

    render_node_header(run, campaign_node)

    llm_count, authored_specs = _parse_arbitrations(campaign_node)
    total_arbs = llm_count or len(authored_specs)

    # Prefetch cache is keyed by campaign node ID (e.g. "night_market").
    cache_key = campaign_node_id or node_id
    if prefetch:
        prefetch.wait_for(cache_key)
    prefetched = prefetch.consume(cache_key) if prefetch else None

    if prefetched and len(prefetched) == total_arbs:
        payloads = prefetched
    elif llm_count > 0:
        payloads = []
    else:
        payloads = [
            validate_arbitration_asset(
                load_json_asset(resolve_asset_path(spec["file"])),
                source=resolve_asset_path(spec["file"]),
            )
            for spec in authored_specs
        ]

    for idx, payload in enumerate(payloads):
        _play_arbitration(
            run, node, payload, templates, rules,
            prefetch, idx, campaign_node_id or node_id, len(payloads),
        )

    node.memory.node_summary = f"{node.node_type}:{len(node.memory.choices_made)}_arbitrations:sanity={node.memory.sanity_lost_in_node}"
    append_node_event(
        node.memory,
        "node_finalized",
        node_id=node.node_id,
        arbitration_count=len(node.memory.choices_made),
        sanity_lost=node.memory.sanity_lost_in_node,
    )
    update_after_node(run.memory, node.memory)
    run.memory.m1.push(build_m1_entry(run.core_state, run.memory, node.memory))
    summary = node.build_summary(sanity_delta=node.memory.sanity_lost_in_node)
    run.close_current_node(summary=summary)
    return node.memory


def _prefetch_targets(
    *,
    prefetch: PrefetchCache | None,
    campaign: dict[str, object],
    target_ids: list[str],
    run,
    current_node_memory=None,
) -> None:
    """Trigger prefetch for a list of campaign node IDs."""

    if prefetch is None:
        return

    seen: set[str] = set()
    for target_id in target_ids:
        if target_id in seen:
            continue
        seen.add(target_id)
        next_campaign_node = campaign["nodes"].get(target_id, {})
        try:
            llm_c, authored = _parse_arbitrations(next_campaign_node)
            arb_count = llm_c or len(authored)
            if arb_count:
                prefetch.trigger(
                    target_node_id=target_id,
                    core_state=run.core_state,
                    run_memory=run.memory,
                    node_history=list(run.node_history),
                    arbitration_count=arb_count,
                    current_node_memory=current_node_memory,
                )
        except (AssetValidationError, ValueError) as exc:
            log.warning("Prefetch: skipping '%s' — node spec invalid: %s", target_id, exc)


def _collect_lookahead_targets(campaign: dict[str, object], next_nodes: list[str]) -> list[str]:
    """Return unique grandchild campaign node IDs in stable order."""

    targets: list[str] = []
    seen: set[str] = set()
    nodes = campaign.get("nodes", {})
    for next_id in next_nodes:
        next_campaign_node = nodes.get(next_id, {})
        for lookahead_id in next_campaign_node.get("next_nodes", []):
            if lookahead_id in seen:
                continue
            seen.add(lookahead_id)
            targets.append(lookahead_id)
    return targets


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Play a Loombound campaign. Requires ANTHROPIC_API_KEY and ollama (gemma3:4b).")
    parser.add_argument("--campaign", type=Path, default=None, help="Path to a campaign JSON file.")
    parser.add_argument("--nodes", type=int, default=None, metavar="N", help="Maximum number of nodes to play (default: unlimited).")
    parser.add_argument("--lang", choices=["en", "zh"], default="en", help="Generated content language (default: en).")
    parser.add_argument(
        "--fast",
        dest="fast_model",
        default=None,
        metavar="MODEL",
        help="Fast Core ollama model for text expansion (default: gemma3:4b). "
             "Can also be set via FAST_CORE_MODEL env var.",
    )
    args = parser.parse_args()

    if args.campaign is None:
        print(
            "No campaign found. Generate one first:\n"
            "\n"
            "  ./loombound gen \"your theme\"\n"
            "\n"
            "Requires ANTHROPIC_API_KEY in .env.\n"
            "\n"
            "With Haiku M2 + local gemma3 (Fast Core), a typical 5-node run costs ~$0.01.\n"
            "Replacing Fast Core with Opus alone would cost ~$0.20 — about 20× more.\n"
            "The gap widens as you generate more campaigns and play more runs.\n"
            "\n"
            "  cp .env.example .env   # then fill in ANTHROPIC_API_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Startup check: Claude API key required ---
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: ANTHROPIC_API_KEY is not set.\n"
            "Loombound requires a Claude API key to run.\n"
            "Set it in .env: ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="\033[2m[%(levelname)s %(name)s] %(message)s\033[0m",
    )

    campaign = load_json_asset(args.campaign)
    rules = load_rules(RULES_PATH)
    templates = load_templates(TEXT_PATH)
    run = make_run(campaign)
    run.rule_system.set_templates(rules)

    fast_model = (
        args.fast_model
        or os.environ.get("FAST_CORE_MODEL", "gemma3:4b")
    )
    fast_cfg = FastCoreConfig(
        model=fast_model,
        lang=args.lang,
        tone=campaign.get("tone") or None,
    )

    # Load T2 cache (arc palette) and T1 cache (node skeletons) if available
    campaign_dir = REPO_ROOT / "data" / "nodes" / campaign.get("campaign_id", "")
    t1_cache_table_path = campaign_dir / "t1_cache_table.json"

    if T2_CACHE_PATH.exists():
        run.memory.m2.load_t2_cache_table(T2_CACHE_PATH)
    if t1_cache_table_path.exists():
        run.memory.m2.load_t1_cache_table(t1_cache_table_path)

    # Build M2Classifier if T2 cache is loaded (provides the cached prefix)
    m2_classifier: M2Classifier | None = None
    if run.memory.m2.t2_cache_table:
        import json as _json
        verdict_dict_path = REPO_ROOT / "data" / "campaigns" / f"{campaign.get('campaign_id', '')}_verdict_dict.json"
        verdict_dict = _json.loads(verdict_dict_path.read_text(encoding="utf-8")) if verdict_dict_path.exists() else []
        verdict_dict_json = _json.dumps(verdict_dict, ensure_ascii=False) if verdict_dict else ""
        m2_cfg = M2ClassifierConfig(api_key=api_key)
        m2_classifier = M2Classifier(
            config=m2_cfg,
            t2_cache_table_json=run.memory.m2.t2_cache_table_prompt_json(),
            t1_cache_table_index_json=run.memory.m2.t1_cache_table_index_json() if run.memory.m2.t1_cache_table else "",
            verdict_dict_json=verdict_dict_json,
        )

    prefetch = PrefetchCache(fast_cfg=fast_cfg, lang=args.lang, m2_classifier=m2_classifier)
    prefetch.warmup()

    current_node_id = campaign["start_node_id"]

    # Prefetch the start node while the player reads the intro.
    # The main loop only prefetches next_nodes, so without this the first
    # LLM-mode node would always have empty arbitrations.
    _prefetch_targets(
        prefetch=prefetch,
        campaign=campaign,
        target_ids=[current_node_id],
        run=run,
    )

    render_run_intro(campaign)
    pause("Press Enter to step onto the road...")
    nodes_played = 0
    try:
        while current_node_id:
            campaign_node = campaign["nodes"][current_node_id]

            # Determine next nodes now so we can trigger prefetch for all of them
            next_nodes = campaign_node.get("next_nodes", [])

            # Trigger background generation for each candidate next node
            if next_nodes:
                _prefetch_targets(
                    prefetch=prefetch,
                    campaign=campaign,
                    target_ids=next_nodes,
                    run=run,
                )

            completed_node_memory = _play_node(
                run,
                campaign,
                campaign_node,
                rules,
                templates,
                prefetch=prefetch,
                campaign_node_id=current_node_id,
            )
            nodes_played += 1

            if next_nodes:
                lookahead_targets = _collect_lookahead_targets(campaign, next_nodes)
                _prefetch_targets(
                    prefetch=prefetch,
                    campaign=campaign,
                    target_ids=lookahead_targets,
                    run=run,
                    current_node_memory=completed_node_memory,
                )

            if not next_nodes:
                break
            if args.nodes is not None and nodes_played >= args.nodes:
                break

            render_map_hud(run, campaign, next_nodes)
            render_input_panel("Choose your next destination")
            next_index = choose_index("> ", len(next_nodes))
            current_node_id = next_nodes[next_index]

            # Trigger Opus for arb 0 of the chosen next node.
            # Runs in background while the player reads the node header + waits for gemma3.
            quasi = build_classifier_input(run.core_state, run.memory, list(run.node_history))
            prefetch.update_arc_state(quasi, current_node_id, 0)

    except KeyboardInterrupt:
        print("\n\nRun interrupted.")
        return
    except (AssetValidationError, ValueError) as exc:
        print(f"\n\nAsset error: {exc}")
        return

    render_run_complete(run)


if __name__ == "__main__":
    main()
