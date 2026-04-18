from src.t0.memory.models import CoreStateView
from src.t2.core.collector import build_classifier_input
from src.t0.memory.types import NodeChoiceRecord, NodeMemory, RunMemory
from src.runtime.play_cli import _collect_lookahead_targets


def test_collect_lookahead_targets_returns_unique_grandchildren_in_order() -> None:
    campaign = {
        "nodes": {
            "node_b": {"next_nodes": ["node_d", "node_e"]},
            "node_c": {"next_nodes": ["node_e", "node_f"]},
        }
    }

    result = _collect_lookahead_targets(campaign, ["node_b", "node_c"])

    assert result == ["node_d", "node_e", "node_f"]


def test_build_classifier_input_includes_partial_active_node_snapshot() -> None:
    node_memory = NodeMemory(
        node_id="ruined_market:floor_02",
        node_type="market",
        floor=2,
        choices_made=[
            NodeChoiceRecord(
                context_id="arb_01",
                scene_type="market",
                player_choice="buy_ashes",
                sanity_delta=1,
                local_flags=["chose_greedy_option"],
            )
        ],
        sanity_lost_in_node=1,
        important_flags=["chose_greedy_option"],
    )

    msg = build_classifier_input(
        core_state=CoreStateView(
            health=8,
            max_health=10,
            money=3,
            sanity=6,
            floor=2,
            act=1,
            scene_type="market",
        ),
        run_memory=RunMemory(),
        node_history=[],
        current_node_memory=node_memory,
    )

    assert "## Active node so far (partial)" in msg
    assert "option=buy_ashes" in msg
    assert "active flags: chose_greedy_option" in msg
