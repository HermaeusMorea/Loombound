from generate_campaign import (
    _build_user_msg,
    build_campaign_json,
    build_generation_context,
    extract_preloaded_table_b,
    validate_graph,
    validate_preloaded_table_b,
)
from generate_table_b import _build_system_prompt, _generation_context
from src.core.llm_interface.fast_core import FastCoreConfig, _build_prompt, _system_prompt
from src.core.llm_interface.types import ArbitrationOptionSeed, ArbitrationSeed


def test_generate_user_message_includes_tone_and_worldview() -> None:
    msg = _build_user_msg(
        theme="边境殖民地政变",
        node_count=6,
        lang="zh",
        tone_hint="脏、硬、压抑的政治惊悚",
        worldview_hint="近未来火星城邦冷战",
    )

    assert "Theme: 边境殖民地政变" in msg
    assert "Tone guidance: 脏、硬、压抑的政治惊悚" in msg
    assert "Worldview / setting guidance: 近未来火星城邦冷战" in msg
    assert "exactly 6 nodes" in msg
    assert "Write all narrative text" in msg


def test_fast_core_system_prompt_includes_campaign_tone() -> None:
    prompt = _system_prompt(
        FastCoreConfig(lang="zh", tone="冷峻现实主义，不要超自然，偏政治悬疑")
    )

    assert "不要默认套用固定题材" in prompt
    assert "Campaign tone: 冷峻现实主义，不要超自然，偏政治悬疑" in prompt


def test_fast_core_prompt_includes_runtime_arc_tendency() -> None:
    prompt = _build_prompt(
        ArbitrationSeed(
            scene_type="ritual",
            scene_concept="灰烬圣堂中，钟声正从裂开的穹顶坠落。",
            sanity_axis="信仰与自我磨损之间的迟疑。",
            options=[
                ArbitrationOptionSeed(
                    option_id="kneel_at_ember",
                    intent="你向残火屈膝，试图换取庇护。",
                    tags=["ritual", "submission"],
                    effects={"sanity_delta": -1},
                )
            ],
            tendency={
                "entry_id": "7",
                "arc_trajectory": "climax",
                "world_pressure": "high",
                "narrative_pacing": "accelerating",
                "pending_intent": "confrontation",
            },
        ),
        core_state=type("State", (), {"floor": 3, "act": 1})(),
    )

    assert "Runtime arc tendency:" in prompt
    assert "arc_trajectory: climax" in prompt


def test_preloaded_user_message_includes_table_a_and_mode() -> None:
    msg = _build_user_msg(
        theme="边境殖民地政变",
        node_count=6,
        lang="zh",
        tone_hint="脏、硬、压抑的政治惊悚",
        worldview_hint="近未来火星城邦冷战",
        generation_mode="preloaded",
        table_a_entries=[
            {
                "entry_id": 0,
                "arc_trajectory": "rising",
                "world_pressure": "high",
                "narrative_pacing": "steady",
                "pending_intent": "revelation",
            }
        ],
    )

    assert "Generation mode: preloaded." in msg
    assert "Table A arc-state catalogue:" in msg
    assert "every node should include preloaded_arbitrations" in msg
    assert '"entry_id":0' in msg


def test_validate_graph_rejects_wrong_node_count() -> None:
    errors = validate_graph(
        [
            {
                "node_id": "start",
                "next_nodes": ["end"],
            },
            {
                "node_id": "end",
                "next_nodes": [],
            },
        ],
        "start",
        expected_node_count=3,
    )

    assert "Expected exactly 3 unique nodes, got 2" in errors


def test_extract_preloaded_table_b_builds_rows_from_nodes() -> None:
    table_b = extract_preloaded_table_b(
        {
            "nodes": [
                {
                    "node_id": "start",
                    "node_type": "crossroads",
                    "label": "Start",
                    "map_blurb": "Map blurb",
                    "preloaded_arbitrations": [
                        {
                            "scene_type": "encounter",
                            "scene_concept": "A narrow gate beneath broken bells.",
                            "sanity_axis": "Dread under ritual order.",
                            "options": [],
                        }
                    ],
                }
            ]
        }
    )

    assert table_b == [
        {
            "node_id": "start",
            "node_type": "crossroads",
            "label": "Start",
            "map_blurb": "Map blurb",
            "arbitrations": [
                {
                    "scene_type": "encounter",
                    "scene_concept": "A narrow gate beneath broken bells.",
                    "sanity_axis": "Dread under ritual order.",
                    "options": [],
                }
            ],
        }
    ]


def test_validate_preloaded_table_b_rejects_missing_and_mismatched_rows() -> None:
    errors = validate_preloaded_table_b(
        extract_preloaded_table_b(
            {
                "nodes": [
                    {
                        "node_id": "start",
                        "node_type": "crossroads",
                        "label": "Wrong Label",
                        "map_blurb": "Map blurb",
                        "preloaded_arbitrations": [],
                    }
                ]
            }
        ),
        [
            {
                "node_id": "start",
                "node_type": "crossroads",
                "label": "Start",
                "map_blurb": "Map blurb",
                "arbitration_count": 2,
            },
            {
                "node_id": "end",
                "node_type": "ritual",
                "label": "End",
                "map_blurb": "End blurb",
                "arbitration_count": 1,
            },
        ],
    )

    assert "table_b missing node skeletons for: ['end']" in errors
    assert "table_b[start] label does not match node label" in errors
    assert "table_b[start] expected 2 arbitration skeletons, got 0" in errors


def test_campaign_json_persists_generation_context() -> None:
    generation_context = build_generation_context(
        theme="边境殖民地政变",
        lang="zh",
        provider="deepseek",
        model="deepseek-chat",
        generation_mode="preloaded",
        tone_hint="脏、硬、压抑的政治惊悚",
        worldview_hint="近未来火星城邦冷战",
        table_a_entry_count=50,
    )
    payload = build_campaign_json(
        {
            "campaign_id": "mars_coup",
            "title": "火星城邦：政变夜",
            "intro": "火星城邦的轨道阴影压了下来。",
            "tone": "冷峻、压抑、政治悬疑。",
            "initial_core_state": {
                "health": 10,
                "max_health": 10,
                "money": 3,
                "sanity": 8,
                "floor": 1,
                "act": 1,
            },
            "start_node_id": "safehouse",
        },
        generation_context=generation_context,
    )

    assert payload["generation_context"]["generation_mode"] == "preloaded"
    assert payload["generation_context"]["worldview_hint"] == "近未来火星城邦冷战"


def test_table_b_system_prompt_prefers_persisted_generation_context() -> None:
    campaign = {
        "generation_context": {
            "theme": "边境殖民地政变",
            "tone_hint": "脏、硬、压抑的政治惊悚",
            "worldview_hint": "近未来火星城邦冷战",
            "generation_mode": "preloaded",
        }
    }
    ctx = _generation_context(campaign)
    prompt = _build_system_prompt(
        title="火星城邦：政变夜",
        tone="冷峻、压抑、政治悬疑。",
        intro="火星城邦的轨道阴影压了下来。",
        source_theme=ctx["theme"],
        tone_hint=ctx["tone_hint"],
        worldview_hint=ctx["worldview_hint"],
        generation_mode=ctx["generation_mode"],
    )

    assert "Original user theme: 边境殖民地政变" in prompt
    assert "Original worldview guidance: 近未来火星城邦冷战" in prompt
    assert "treat it as the most authoritative source" in prompt
