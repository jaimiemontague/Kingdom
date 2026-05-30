"""WK69 Round B-1 (Wave W3) — SimEngine-extraction SEAM tests.

Sprint: wk69_round_b1_simengine_decomposition
Owner:  Agent 11 (QA_TestEngineering_Lead)

PURPOSE
-------
WK69 extracted six inlined services out of ``game/sim_engine.py`` (1527 -> 988
LOC) into focused ``game/sim/`` modules, each behind a **one-line delegating
wrapper** that keeps the original ``SimEngine`` method name working for every
caller/test:

    game/sim/fog.py                update_fog_of_war(sim)
    game/sim/separation.py         apply_entity_separation(sim, dt)
    game/sim/lumber.py             wood_yield_for_growth(growth)
                                   init_trees_from_world(sim)
                                   tree_growth_lookup(sim, tx, ty)
                                   remove_trees_in_footprint(sim, gx, gy, w, h)
                                   find_nearest_choppable_tree_for_builder(sim, tx, ty)
                                   chop_tree_at(sim, tx, ty)
                                   harvest_log_at(sim, tx, ty)
    game/sim/poi_discovery.py      check_poi_discovery(sim)
    game/sim/early_pacing.py       maybe_apply_early_pacing_nudge(sim, dt, castle)
                                   nearest_lair_to(sim, x, y)
    game/sim/building_lifecycle.py cleanup_destroyed_buildings(sim)

These are **seam** tests (not behavior tests — the digest/characterization nets
cover behavior). They lock the *structure* of the split so a later refactor that
deletes a module, renames a public function, or accidentally stops a wrapper from
delegating is caught immediately. For each service we assert:

  (a) the new module imports and its public free function(s) exist + are callable;
  (b) the ``SimEngine`` wrapper actually DELEGATES to that module function —
      we monkeypatch the module function with a spy, call the wrapper on a real
      (constructed) ``SimEngine``, and assert the spy fired with the live engine
      as its first positional arg (and that the wrapper forwards its own extra
      args through unchanged).

The wrappers do a local ``from game.sim import <module>`` then call
``<module>.<fn>(self, ...)``, so patching the function *attribute on the module
object* (what ``monkeypatch.setattr(module, "fn", spy)`` does) is seen by the
wrapper on the very next call — no production code is touched.

Headless: SDL dummy drivers so the real ``GameEngine``/``SimEngine`` construct
without a display (mirrors tests/test_wk67_ai_boundary.py).
"""

from __future__ import annotations

import os

import pytest

# Headless-friendly drivers so a real engine constructs without a display.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.engine import GameEngine
from game.sim import (
    building_lifecycle,
    early_pacing,
    fog,
    lumber,
    poi_discovery,
    separation,
)


# ---------------------------------------------------------------------------
# Shared headless engine (module-scoped — these are read-only seam checks; we
# monkeypatch module functions, never mutate the engine's gameplay state).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sim():
    """A real headless ``SimEngine`` to act as the ``self`` the wrappers delegate.

    Built via ``GameEngine(headless=True)`` (same construction the WK65/67 nets
    use) so ``engine.sim`` is the genuine ``SimEngine`` whose wrapper methods we
    exercise. Torn down with ``pygame.quit()``.
    """
    engine = GameEngine(headless=True)
    try:
        yield engine.sim
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


class _Spy:
    """Records the positional/keyword args of each call and returns a sentinel."""

    def __init__(self, return_value=None):
        self.calls: list[tuple[tuple, dict]] = []
        self.return_value = return_value

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.return_value

    @property
    def called(self) -> bool:
        return bool(self.calls)

    @property
    def first_arg(self):
        return self.calls[0][0][0] if self.calls and self.calls[0][0] else None


# ===========================================================================
# Part A — each module + its public function(s) exist and are callable
# ===========================================================================
def test_modules_and_public_functions_exist():
    """All six extracted modules expose their documented public free functions."""
    # fog
    assert callable(fog.update_fog_of_war)
    # separation
    assert callable(separation.apply_entity_separation)
    # lumber — the whole tree/log cluster
    for name in (
        "wood_yield_for_growth",
        "init_trees_from_world",
        "tree_growth_lookup",
        "remove_trees_in_footprint",
        "find_nearest_choppable_tree_for_builder",
        "chop_tree_at",
        "harvest_log_at",
    ):
        assert callable(getattr(lumber, name)), f"lumber.{name} missing/uncallable"
    # poi discovery
    assert callable(poi_discovery.check_poi_discovery)
    # early pacing (nudge + nearest-lair helper)
    assert callable(early_pacing.maybe_apply_early_pacing_nudge)
    assert callable(early_pacing.nearest_lair_to)
    # building lifecycle (Move 7 core)
    assert callable(building_lifecycle.cleanup_destroyed_buildings)


def test_extracted_modules_do_not_import_sim_engine_at_module_top():
    """DoD §F guard: the new modules must not create an import cycle.

    They take ``sim`` as a duck-typed parameter; a top-level
    ``import game.sim_engine`` (only a ``TYPE_CHECKING`` one is allowed) would
    reintroduce the cycle the split was designed to avoid.
    """
    import ast
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    for mod in ("fog", "separation", "lumber", "poi_discovery", "early_pacing", "building_lifecycle"):
        src = (repo_root / "game" / "sim" / f"{mod}.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Collect imports that are NOT inside an `if TYPE_CHECKING:` block.
        type_checking_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                    isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
                )
                if is_tc:
                    for child in ast.walk(node):
                        type_checking_lines.add(getattr(child, "lineno", -1))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if node.lineno in type_checking_lines:
                    continue  # TYPE_CHECKING-guarded import is allowed
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                names.extend(alias.name for alias in node.names)
                for n in names:
                    assert "sim_engine" not in n, (
                        f"game/sim/{mod}.py has a runtime import of '{n}' — that "
                        "reintroduces the SimEngine import cycle (DoD §F)"
                    )


# ===========================================================================
# Part B — each SimEngine wrapper DELEGATES to its module function
# ===========================================================================
#
# Pattern: replace the module's public function with a spy, call the SimEngine
# wrapper, assert the spy fired with ``sim`` (the live engine) as first arg and
# that the wrapper forwarded its own extra params unchanged.


def test_wrapper_update_fog_of_war_delegates(sim, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(fog, "update_fog_of_war", spy)
    sim._update_fog_of_war()
    assert spy.called, "_update_fog_of_war did not delegate to fog.update_fog_of_war"
    assert spy.first_arg is sim


def test_wrapper_apply_entity_separation_delegates(sim, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(separation, "apply_entity_separation", spy)
    sim._apply_entity_separation(0.25)
    assert spy.called, "_apply_entity_separation did not delegate to separation.apply_entity_separation"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert args[1] == 0.25, "dt was not forwarded to separation.apply_entity_separation"


def test_wrapper_check_poi_discovery_delegates(sim, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(poi_discovery, "check_poi_discovery", spy)
    sim._check_poi_discovery()
    assert spy.called, "_check_poi_discovery did not delegate to poi_discovery.check_poi_discovery"
    assert spy.first_arg is sim


def test_wrapper_maybe_apply_early_pacing_nudge_delegates(sim, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(early_pacing, "maybe_apply_early_pacing_nudge", spy)
    sentinel_castle = object()
    sim._maybe_apply_early_pacing_nudge(0.5, sentinel_castle)
    assert spy.called, "_maybe_apply_early_pacing_nudge did not delegate to early_pacing"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert args[1] == 0.5, "dt was not forwarded"
    assert args[2] is sentinel_castle, "castle was not forwarded"


def test_wrapper_nearest_lair_to_delegates(sim, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(early_pacing, "nearest_lair_to", spy)
    result = sim._nearest_lair_to(12.0, 34.0)
    assert spy.called, "_nearest_lair_to did not delegate to early_pacing.nearest_lair_to"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert (args[1], args[2]) == (12.0, 34.0), "x/y were not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_cleanup_destroyed_buildings_delegates(sim, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(building_lifecycle, "cleanup_destroyed_buildings", spy)
    sim._cleanup_destroyed_buildings()
    assert spy.called, "_cleanup_destroyed_buildings did not delegate to building_lifecycle"
    assert spy.first_arg is sim


# --- lumber cluster: the three builder-facing entry points + supporting moves ---


def test_wrapper_chop_tree_at_delegates(sim, monkeypatch):
    sentinel = 7.5
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(lumber, "chop_tree_at", spy)
    result = sim.chop_tree_at(3, 4)
    assert spy.called, "chop_tree_at did not delegate to lumber.chop_tree_at"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert (args[1], args[2]) == (3, 4), "tx/ty were not forwarded"
    assert result == sentinel, "wrapper did not return the module function's result"


def test_wrapper_harvest_log_at_delegates(sim, monkeypatch):
    spy = _Spy(return_value=11)
    monkeypatch.setattr(lumber, "harvest_log_at", spy)
    result = sim.harvest_log_at(5, 6)
    assert spy.called, "harvest_log_at did not delegate to lumber.harvest_log_at"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert (args[1], args[2]) == (5, 6), "tx/ty were not forwarded"
    assert result == 11, "wrapper did not return the module function's result"


def test_wrapper_find_nearest_choppable_tree_for_builder_delegates(sim, monkeypatch):
    sentinel = (1, 2, 3.0)
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(lumber, "find_nearest_choppable_tree_for_builder", spy)
    result = sim.find_nearest_choppable_tree_for_builder(8, 9)
    assert spy.called, "find_nearest_choppable_tree_for_builder did not delegate to lumber"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert (args[1], args[2]) == (8, 9), "from_tx/from_ty were not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_remove_trees_in_footprint_delegates(sim, monkeypatch):
    spy = _Spy(return_value=2)
    monkeypatch.setattr(lumber, "remove_trees_in_footprint", spy)
    result = sim.remove_trees_in_footprint(10, 11, 2, 3)
    assert spy.called, "remove_trees_in_footprint did not delegate to lumber"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert (args[1], args[2], args[3], args[4]) == (10, 11, 2, 3), "footprint args not forwarded"
    assert result == 2, "wrapper did not return the module function's result"


def test_wrapper_tree_growth_lookup_delegates(sim, monkeypatch):
    spy = _Spy(return_value=0.75)
    monkeypatch.setattr(lumber, "tree_growth_lookup", spy)
    result = sim._tree_growth_lookup(13, 14)
    assert spy.called, "_tree_growth_lookup did not delegate to lumber"
    args, _ = spy.calls[0]
    assert args[0] is sim
    assert (args[1], args[2]) == (13, 14), "tx/ty were not forwarded"
    assert result == 0.75, "wrapper did not return the module function's result"


def test_wrapper_init_trees_from_world_delegates(sim, monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(lumber, "init_trees_from_world", spy)
    sim._init_trees_from_world()
    assert spy.called, "_init_trees_from_world did not delegate to lumber"
    assert spy.first_arg is sim


def test_wrapper_wood_yield_for_growth_delegates(sim, monkeypatch):
    """``_wood_yield_for_growth`` is a staticmethod: it delegates ``growth`` only.

    Unlike the other wrappers it does NOT pass ``sim`` (the original was a
    ``@staticmethod``), so we assert it forwards just the growth value and
    returns the module function's result.
    """
    spy = _Spy(return_value=4)
    monkeypatch.setattr(lumber, "wood_yield_for_growth", spy)
    result = sim._wood_yield_for_growth(0.9)
    assert spy.called, "_wood_yield_for_growth did not delegate to lumber.wood_yield_for_growth"
    args, _ = spy.calls[0]
    assert args[0] == 0.9, "growth was not forwarded"
    assert result == 4, "wrapper did not return the module function's result"
