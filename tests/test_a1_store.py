from src.t1.memory.a1_store import A1Store, A1Entry


def _entry(waypoint_id: str, depth: int = 1) -> A1Entry:
    return A1Entry(
        waypoint_id=waypoint_id,
        scene_type="crossroads",
        pressure_level="moderate",
        resource_trajectory="stable",
        outcome_class="stable",
        narrative_thread="self_preservation",
        depth=depth,
    )


def test_push_appends_entry() -> None:
    store = A1Store()
    store.push(_entry("wp1"))
    assert len(store.entries) == 1


def test_push_respects_max_entries_window() -> None:
    store = A1Store(max_entries=3)
    for i in range(5):
        store.push(_entry(f"wp{i}"))
    assert len(store.entries) == 3
    assert store.entries[0].waypoint_id == "wp2"
    assert store.entries[-1].waypoint_id == "wp4"


def test_recent_returns_last_n() -> None:
    store = A1Store()
    for i in range(6):
        store.push(_entry(f"wp{i}"))
    result = store.recent(3)
    assert len(result) == 3
    assert result[-1].waypoint_id == "wp5"


def test_recent_clamps_to_available() -> None:
    store = A1Store()
    store.push(_entry("wp0"))
    result = store.recent(10)
    assert len(result) == 1


def test_to_prompt_lines_format() -> None:
    store = A1Store()
    store.push(_entry("wp1", depth=2))
    lines = store.to_prompt_lines(n=1)
    assert len(lines) == 1
    assert "[2]" in lines[0]
    assert "crossroads" in lines[0]
    assert "stable" in lines[0]
