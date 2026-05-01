"""WK49 r8: progression invariant — live XP must stay below xp_to_level (ranger exploration path)."""

from __future__ import annotations

from game.entities.hero import Hero
from game.sim.hero_profile import build_hero_profile_snapshot


def _assert_progression_invariant(h: Hero) -> None:
    assert h.xp < h.xp_to_level, (h.xp, h.xp_to_level, h.level)


def test_grant_tile_exploration_xp_many_small_grants_never_exceed_cap() -> None:
    h = Hero(0.0, 0.0, hero_class="ranger", hero_id="xpinv_small")
    h.xp_to_level = 11
    for _ in range(200):
        h.grant_tile_exploration_xp(1)
        _assert_progression_invariant(h)


def test_grant_tile_exploration_xp_large_burst_matches_single_add_xp() -> None:
    a = Hero(0.0, 0.0, hero_class="ranger", hero_id="xpinv_a")
    b = Hero(0.0, 0.0, hero_class="ranger", hero_id="xpinv_b")
    a.xp_to_level = b.xp_to_level = 47
    a.xp = b.xp = 3
    for _ in range(89):
        a.grant_tile_exploration_xp(1)
    b.add_xp(89)
    assert a.level == b.level and a.xp == b.xp and a.xp_to_level == b.xp_to_level
    _assert_progression_invariant(a)
    _assert_progression_invariant(b)


def test_profile_snapshot_progression_respects_cap_after_exploration_xp() -> None:
    h = Hero(0.0, 0.0, hero_class="ranger", hero_id="xpinv_snap")
    h.xp_to_level = 13
    h.grant_tile_exploration_xp(400)
    snap = build_hero_profile_snapshot(h, None, now_ms=12_000)
    assert snap.progression.xp == h.xp
    assert snap.progression.xp_to_level == h.xp_to_level
    assert snap.progression.xp < snap.progression.xp_to_level
