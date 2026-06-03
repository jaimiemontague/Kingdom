"""WK122 regression: selecting a Guard or the TaxCollector must not crash.

Bug (WK63 regression): clicking a Guard or the TaxCollector raised
``AttributeError: 'Guard' object has no attribute 'hero_id'`` because the
ID-based ``selected_hero`` property (added WK63) resolved every id against
``self.sim.heroes`` and the setter blindly read ``v.hero_id`` — but a Guard has
only ``entity_id`` and the TaxCollector (a singleton at ``sim.tax_collector``)
has neither. The guard / tax-collector info panels in ``game/ui/hero_panel.py``
already existed and worked pre-WK63 (when ``selected_hero`` stored a live object).

WK122 fix (Design B): the SelectionState "hero" slot now carries a ``kind``
('hero' | 'guard' | 'tax_collector'); ``GameEngine.selected_hero`` routes
Guard -> entity_id, TaxCollector -> singleton, Hero -> hero_id, and the getter
resolves the live object against the right sim collection each frame (preserving
the WK63 no-stale-reference contract for ALL kinds).

These tests exercise BOTH assignment paths the bug came in through:
  (a) the pygame click path (``engine.try_select_guard`` / ``try_select_tax_collector``)
  (b) the ursina-pick equivalent (direct ``engine.selected_hero = <entity>`` assignment,
      which is what ``try_ursina_select_unit_at_screen`` does for kind=='guard'/'tax_collector')
plus the stale/dead-reference contract and that ordinary hero selection still works.
"""

from __future__ import annotations

import os

# Headless-friendly drivers so a real engine constructs without a display/audio.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game.engine import GameEngine
from game.entities.guard import Guard
from game.entities.hero import Hero
from game.entities.tax_collector import TaxCollector


@pytest.fixture()
def engine():
    eng = GameEngine(headless=True)
    try:
        yield eng
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def _spawn_guard_at_screen(eng: GameEngine, screen_pos: tuple) -> Guard:
    """Place a fresh guard at the world position the given screen pos maps to."""
    wx, wy = eng.pointer_world_xy(screen_pos)
    g = Guard(wx, wy)
    eng.sim.guards.append(g)
    return g


# ---------------------------------------------------------------------------
# (a) pygame click path
# ---------------------------------------------------------------------------

def test_pygame_click_select_guard(engine):
    """try_select_guard must not raise and selected_hero returns the SAME Guard."""
    screen_pos = (700, 400)
    g = _spawn_guard_at_screen(engine, screen_pos)

    ok = engine.try_select_guard(screen_pos)  # the WK63-regressed click path
    assert ok is True

    sel = engine.selected_hero  # used to raise AttributeError('hero_id')
    assert sel is g
    assert isinstance(sel, Guard)


def test_pygame_click_select_tax_collector(engine):
    """try_select_tax_collector must not raise and selected_hero returns the TaxCollector."""
    screen_pos = (700, 400)
    tc = engine.tax_collector
    assert isinstance(tc, TaxCollector)
    # Position the singleton tax collector under the click.
    tc.x, tc.y = engine.pointer_world_xy(screen_pos)

    ok = engine.try_select_tax_collector(screen_pos)
    assert ok is True

    sel = engine.selected_hero
    assert sel is tc
    assert isinstance(sel, TaxCollector)


# ---------------------------------------------------------------------------
# (b) ursina-pick equivalent (direct assignment, as try_ursina_select_unit_at_screen does)
# ---------------------------------------------------------------------------

def test_ursina_pick_assign_guard(engine):
    """Direct selected_hero = <Guard> (ursina pick path) must round-trip."""
    g = Guard(123.0, 456.0)
    engine.sim.guards.append(g)

    engine.selected_hero = g  # ursina pick assigns the live entity directly
    sel = engine.selected_hero
    assert sel is g
    assert isinstance(sel, Guard)


def test_ursina_pick_assign_tax_collector(engine):
    """Direct selected_hero = <TaxCollector> (ursina pick path) must round-trip."""
    tc = engine.tax_collector
    engine.selected_hero = tc
    sel = engine.selected_hero
    assert sel is tc
    assert isinstance(sel, TaxCollector)


# ---------------------------------------------------------------------------
# Stale / dead reference contract (WK63 no-stale-ref preserved for all kinds)
# ---------------------------------------------------------------------------

def test_guard_stale_reference_clears(engine):
    """Selecting a guard then killing + removing it yields selected_hero is None (no crash)."""
    g = Guard(50.0, 60.0)
    engine.sim.guards.append(g)
    engine.selected_hero = g
    assert engine.selected_hero is g

    # Dead guard (still in list) -> not returned.
    g.hp = 0
    assert engine.selected_hero is None

    # Re-select, then remove from the sim entirely -> still None, no crash.
    g.hp = g.max_hp
    engine.selected_hero = g
    assert engine.selected_hero is g
    engine.sim.guards.remove(g)
    assert engine.selected_hero is None


def test_tax_collector_missing_clears(engine):
    """If the tax collector singleton disappears, selected_hero returns None (no crash)."""
    tc = engine.tax_collector
    engine.selected_hero = tc
    assert engine.selected_hero is tc

    engine.sim.tax_collector = None
    assert engine.selected_hero is None


# ---------------------------------------------------------------------------
# Ordinary hero selection still works (byte-identical to pre-fix hero path)
# ---------------------------------------------------------------------------

def test_normal_hero_selection_still_works(engine):
    """A real Hero still resolves via hero_id; stale hero clears as before."""
    h = Hero(400.0, 400.0, hero_class="warrior", hero_id="h_wk122_001")
    engine.sim.heroes.append(h)

    engine.selected_hero = h
    sel = engine.selected_hero
    assert sel is h
    assert isinstance(sel, Hero)

    # Stale hero (removed) -> None, no crash.
    engine.sim.heroes.remove(h)
    assert engine.selected_hero is None


def test_kind_switches_between_entity_types(engine):
    """Switching the same 'hero' slot across kinds resolves the correct live object."""
    h = Hero(10.0, 10.0, hero_class="warrior", hero_id="h_wk122_switch")
    g = Guard(20.0, 20.0)
    tc = engine.tax_collector
    engine.sim.heroes.append(h)
    engine.sim.guards.append(g)

    engine.selected_hero = h
    assert engine.selected_hero is h
    engine.selected_hero = g
    assert engine.selected_hero is g
    engine.selected_hero = tc
    assert engine.selected_hero is tc
    engine.selected_hero = None
    assert engine.selected_hero is None
