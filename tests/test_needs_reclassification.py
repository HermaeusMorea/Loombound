"""Tests for Step 3: RunStateSnapshot + needs_reclassification."""

from src.t0.memory import CoreStateView, MetaStateView
from src.runtime.session import Run
from src.t2.core.arc_state import RunStateSnapshot, needs_reclassification


def _make_run(health=10, max_health=10, money=5, sanity=50, marks=None, traumas=None):
    run = Run(
        run_id="r",
        core_state=CoreStateView(depth=1, act=1, health=health, max_health=max_health,
                                  money=money, sanity=sanity),
        meta_state=MetaStateView(),
    )
    if marks:
        run.meta_state.active_marks = list(marks)
    if traumas:
        run.meta_state.metadata.setdefault("traumas", []).extend(traumas)
    return run


def test_needs_reclassification_false_when_nothing_changed() -> None:
    run_a = _make_run(health=10, sanity=50)
    snap_a = RunStateSnapshot.from_run(run_a)
    snap_b = RunStateSnapshot.from_run(run_a)
    assert needs_reclassification(snap_a, snap_b) is False


def test_needs_reclassification_true_on_health_band_crossing() -> None:
    # health=10 (max 10) → very_high; after health=4 → moderate-ish, definitely a crossing.
    run = _make_run(health=10, max_health=10)
    prev = RunStateSnapshot.from_run(run)
    run.core_state.health = 4
    curr = RunStateSnapshot.from_run(run)
    assert prev.health_band != curr.health_band
    assert needs_reclassification(prev, curr) is True


def test_needs_reclassification_true_on_sanity_band_crossing() -> None:
    run = _make_run(sanity=90)
    prev = RunStateSnapshot.from_run(run)
    run.core_state.sanity = 10
    curr = RunStateSnapshot.from_run(run)
    assert prev.sanity_band != curr.sanity_band
    assert needs_reclassification(prev, curr) is True


def test_needs_reclassification_false_when_same_band() -> None:
    # Both values inside moderate band
    run = _make_run(sanity=50)
    prev = RunStateSnapshot.from_run(run)
    run.core_state.sanity = 55  # still moderate
    curr = RunStateSnapshot.from_run(run)
    assert prev.sanity_band == curr.sanity_band
    assert needs_reclassification(prev, curr) is False


def test_needs_reclassification_true_on_new_mark() -> None:
    run = _make_run()
    prev = RunStateSnapshot.from_run(run)
    run.meta_state.active_marks = ["cursed"]
    curr = RunStateSnapshot.from_run(run)
    assert needs_reclassification(prev, curr) is True


def test_needs_reclassification_true_on_mark_removed() -> None:
    run = _make_run(marks=["bloodborne"])
    prev = RunStateSnapshot.from_run(run)
    run.meta_state.active_marks = []
    curr = RunStateSnapshot.from_run(run)
    assert needs_reclassification(prev, curr) is True


def test_needs_reclassification_true_on_new_trauma() -> None:
    run = _make_run()
    prev = RunStateSnapshot.from_run(run)
    run.meta_state.metadata.setdefault("traumas", []).append("loss")
    curr = RunStateSnapshot.from_run(run)
    assert needs_reclassification(prev, curr) is True


def test_needs_reclassification_false_when_trauma_count_unchanged() -> None:
    run = _make_run(traumas=["loss"])
    prev = RunStateSnapshot.from_run(run)
    # no new trauma added
    curr = RunStateSnapshot.from_run(run)
    assert needs_reclassification(prev, curr) is False
