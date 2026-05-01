"""Regression: peasants must not abandon an active scaffold for a fresher foundation."""

from game.entities import Castle, Marketplace
from game.entities.peasant import Peasant


def test_pick_build_prefers_started_site_over_unstarted_when_no_sticky() -> None:
    castle = Castle(20, 20)
    started = Marketplace(30, 20)
    started.mark_unconstructed()
    fresh = Marketplace(40, 20)
    fresh.mark_unconstructed()
    started.start_construction()

    p = Peasant(float(castle.center_x), float(castle.center_y))
    p.target_building = None
    chosen = p._pick_build_target([castle, started, fresh])
    assert chosen is started


def test_pick_build_sticky_keeps_active_target_when_valid() -> None:
    castle = Castle(20, 20)
    active = Marketplace(30, 20)
    active.mark_unconstructed()
    other = Marketplace(40, 20)
    other.mark_unconstructed()
    active.start_construction()

    p = Peasant(float(castle.center_x), float(castle.center_y))
    p.target_building = active
    chosen = p._pick_build_target([castle, active, other])
    assert chosen is active
