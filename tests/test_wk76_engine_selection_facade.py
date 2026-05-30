"""WK76 Round B-2d (Wave W2) — engine.py selection facade SEAM tests.

Sprint: wk76_round_b2_engine_selection_facade
Owner:  Agent 11 (QA_TestEngineering_Lead)

PURPOSE
-------
WK76 extracted the GameEngine ``try_select_*`` click/screen selection handlers
out of ``game/engine.py`` (1365 -> ~1184 LOC) into one module, each behind a
**one-line delegating wrapper** that keeps the original ``GameEngine`` method
name working for every caller (input_handler / hud) and every test:

    game/engine_facades/selection.py   try_select_hero(engine, screen_pos)
                                        try_select_hero_at_world(engine, wx, wy, radius=24.0)
                                        try_select_tax_collector(engine, screen_pos)
                                        try_select_guard(engine, screen_pos)
                                        try_select_peasant(engine, screen_pos)
                                        try_select_enemy(engine, screen_pos)
                                        try_ursina_select_unit_at_screen(engine, screen_pos)
                                        try_select_building(engine, screen_pos)

These are **seam** tests (not behavior tests — the digest/characterization nets
cover behavior). They lock the *structure* of the split so a later refactor that
deletes the module, renames a public function, or accidentally stops a wrapper
from delegating is caught immediately. For each extracted function we assert:

  (a) the new module imports and its public free function exists + is callable;
  (b) the ``GameEngine`` wrapper actually DELEGATES to that module function — we
      monkeypatch the module function with a spy, call the wrapper on a real
      (constructed) headless ``GameEngine``, and assert the spy fired with the
      live engine as its first positional arg (and that the wrapper forwards its
      own extra args through unchanged + returns the module function's result).

The wrappers do a local ``from game.engine_facades import selection`` then call
``selection.<fn>(self, ...)``, so patching the function *attribute on the module
object* (what ``monkeypatch.setattr`` does) is seen by the wrapper on the very
next call — no production code is touched.

We also guard DoD §F: the extracted module may not import ``game.engine`` at
runtime (TYPE_CHECKING-only), so the split stays cycle-free.

Headless: SDL dummy drivers so the real ``GameEngine`` constructs without a
display (mirrors tests/test_wk75_engine_facade.py + tests/test_wk67_ai_boundary.py).
"""

from __future__ import annotations

import os

import pytest

# Headless-friendly drivers so a real engine constructs without a display/audio.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.engine import GameEngine
from game.engine_facades import selection


# The 8 public free functions extracted into game/engine_facades/selection.py.
# Each is also the name of the GameEngine wrapper that must delegate to it.
SELECTION_FUNCS = (
    "try_select_hero",
    "try_select_hero_at_world",
    "try_select_tax_collector",
    "try_select_guard",
    "try_select_peasant",
    "try_select_enemy",
    "try_ursina_select_unit_at_screen",
    "try_select_building",
)


# ---------------------------------------------------------------------------
# Shared headless engine (module-scoped — these are read-only seam checks; we
# monkeypatch module functions with spies, never run the real selection bodies,
# so the engine's gameplay state is never mutated).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def engine():
    """A real headless ``GameEngine`` to act as the ``self`` the wrappers delegate.

    Built via ``GameEngine(headless=True)`` (same construction the WK67/69/75
    nets use). Torn down with ``pygame.quit()``.
    """
    eng = GameEngine(headless=True)
    try:
        yield eng
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
# Part A — the module + its public functions exist and are callable
# ===========================================================================
def test_module_and_public_functions_exist():
    """selection.py exposes all 8 documented public free functions, callable."""
    for name in SELECTION_FUNCS:
        assert callable(getattr(selection, name, None)), (
            f"selection.{name} missing/uncallable"
        )


def test_wrappers_present_on_gameengine():
    """All 8 wrapper method names still live on GameEngine (call sites unchanged)."""
    for name in SELECTION_FUNCS:
        assert callable(getattr(GameEngine, name, None)), (
            f"GameEngine.{name} wrapper missing/uncallable (call sites would break)"
        )


def test_selection_module_does_not_import_engine_at_runtime():
    """DoD §F guard: selection.py must not create a GameEngine import cycle.

    It takes ``engine`` as a duck-typed parameter; a top-level
    ``import game.engine`` / ``from game.engine import ...`` (only a
    ``TYPE_CHECKING`` one is allowed) would reintroduce the cycle the split was
    designed to avoid.
    """
    import ast
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    path = repo_root / "game" / "engine_facades" / "selection.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Collect the line numbers that live inside an `if TYPE_CHECKING:` block.
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
                assert n != "game.engine" and not n.startswith("game.engine."), (
                    f"selection module has a runtime import of '{n}' — that "
                    "reintroduces the GameEngine import cycle (DoD §F)"
                )


# ===========================================================================
# Part B — each GameEngine wrapper DELEGATES to its selection module function
# ===========================================================================
#
# Pattern: replace the module's public function with a spy, call the GameEngine
# wrapper, assert the spy fired with ``engine`` (the live engine) as first arg
# and that the wrapper forwarded its own extra params unchanged + returned the
# module function's result.


def test_wrapper_try_select_hero_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_hero", spy)
    result = engine.try_select_hero((100, 200))
    assert spy.called, "try_select_hero did not delegate to selection.try_select_hero"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (100, 200), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_select_hero_at_world_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_hero_at_world", spy)
    result = engine.try_select_hero_at_world(50.0, 60.0, 24.0)
    assert spy.called, "try_select_hero_at_world did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert (args[1], args[2], args[3]) == (50.0, 60.0, 24.0), "wx/wy/radius not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_select_tax_collector_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_tax_collector", spy)
    result = engine.try_select_tax_collector((11, 22))
    assert spy.called, "try_select_tax_collector did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (11, 22), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_select_guard_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_guard", spy)
    result = engine.try_select_guard((33, 44))
    assert spy.called, "try_select_guard did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (33, 44), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_select_peasant_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_peasant", spy)
    result = engine.try_select_peasant((55, 66))
    assert spy.called, "try_select_peasant did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (55, 66), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_select_enemy_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_enemy", spy)
    result = engine.try_select_enemy((77, 88))
    assert spy.called, "try_select_enemy did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (77, 88), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_ursina_select_unit_at_screen_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_ursina_select_unit_at_screen", spy)
    result = engine.try_ursina_select_unit_at_screen((99, 111))
    assert spy.called, "try_ursina_select_unit_at_screen did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (99, 111), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_try_select_building_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(selection, "try_select_building", spy)
    result = engine.try_select_building((123, 234))
    assert spy.called, "try_select_building did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == (123, 234), "screen_pos was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"
