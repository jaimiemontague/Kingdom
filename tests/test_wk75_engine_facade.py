"""WK75 Round B-2c (Wave W2) — engine.py actions/console facade SEAM tests.

Sprint: wk75_round_b2_engine_actions_facade
Owner:  Agent 11 (QA_TestEngineering_Lead)

PURPOSE
-------
WK75 extracted the GameEngine player-action methods + the cheat/chat console out
of ``game/engine.py`` (1678 -> 1365 LOC) into two modules, each behind a **one-line
delegating wrapper** that keeps the original ``GameEngine`` method name working for
every caller (input_handler / hud / command_bar / ursina_app) and every test:

    game/engine_facades/actions.py   try_hire_hero(engine)
                                     place_building(engine, grid_x, grid_y)
                                     place_bounty(engine)
                                     apply_hud_pin_action(engine, action)
    game/console.py                  process_command(engine, text)

These are **seam** tests (not behavior tests — the WK68 button tests +
digest/characterization nets cover behavior). They lock the *structure* of the
split so a later refactor that deletes a module, renames a public function, or
accidentally stops a wrapper from delegating is caught immediately. For each
extracted function we assert:

  (a) the new module imports and its public free function exists + is callable;
  (b) the ``GameEngine`` wrapper actually DELEGATES to that module function — we
      monkeypatch the module function with a spy, call the wrapper on a real
      (constructed) headless ``GameEngine``, and assert the spy fired with the
      live engine as its first positional arg (and that the wrapper forwards its
      own extra args through unchanged + returns the module function's result).

The wrappers do a local ``from game.engine_facades import actions`` /
``from game import console`` then call ``<module>.<fn>(self, ...)``, so patching
the function *attribute on the module object* (what ``monkeypatch.setattr`` does)
is seen by the wrapper on the very next call — no production code is touched.

We also guard DoD §F: neither extracted module may import ``game.engine`` at
runtime (TYPE_CHECKING-only), so the split stays cycle-free.

Headless: SDL dummy drivers so the real ``GameEngine`` constructs without a
display (mirrors tests/test_wk67_ai_boundary.py + tests/test_wk69_*).
"""

from __future__ import annotations

import os

import pytest

# Headless-friendly drivers so a real engine constructs without a display/audio.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import console
from game.engine import GameEngine
from game.engine_facades import actions


# ---------------------------------------------------------------------------
# Shared headless engine (module-scoped — these are read-only seam checks; we
# monkeypatch module functions with spies, never run the real action bodies,
# so the engine's gameplay state is never mutated).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def engine():
    """A real headless ``GameEngine`` to act as the ``self`` the wrappers delegate.

    Built via ``GameEngine(headless=True)`` (same construction the WK67/69 nets
    use). Torn down with ``pygame.quit()``.
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
# Part A — each module + its public function(s) exist and are callable
# ===========================================================================
def test_modules_and_public_functions_exist():
    """Both extracted modules expose their documented public free functions."""
    for name in ("try_hire_hero", "place_building", "place_bounty", "apply_hud_pin_action"):
        assert callable(getattr(actions, name)), f"actions.{name} missing/uncallable"
    assert callable(console.process_command), "console.process_command missing/uncallable"


def test_extracted_modules_do_not_import_engine_at_module_top():
    """DoD §F guard: the new modules must not create an import cycle.

    They take ``engine`` as a duck-typed parameter; a top-level
    ``import game.engine`` / ``from game.engine import ...`` (only a
    ``TYPE_CHECKING`` one is allowed) would reintroduce the cycle the split was
    designed to avoid.
    """
    import ast
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    targets = {
        "actions": repo_root / "game" / "engine_facades" / "actions.py",
        "console": repo_root / "game" / "console.py",
    }
    for label, path in targets.items():
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
                        f"{label} module has a runtime import of '{n}' — that "
                        "reintroduces the GameEngine import cycle (DoD §F)"
                    )


# ===========================================================================
# Part B — each GameEngine wrapper DELEGATES to its module function
# ===========================================================================
#
# Pattern: replace the module's public function with a spy, call the GameEngine
# wrapper, assert the spy fired with ``engine`` (the live engine) as first arg
# and that the wrapper forwarded its own extra params unchanged + returned the
# module function's result.


def test_wrapper_try_hire_hero_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(actions, "try_hire_hero", spy)
    result = engine.try_hire_hero()
    assert spy.called, "try_hire_hero did not delegate to actions.try_hire_hero"
    assert spy.first_arg is engine
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_place_building_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(actions, "place_building", spy)
    result = engine.place_building(12, 34)
    assert spy.called, "place_building did not delegate to actions.place_building"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert (args[1], args[2]) == (12, 34), "grid_x/grid_y were not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_place_bounty_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(actions, "place_bounty", spy)
    result = engine.place_bounty()
    assert spy.called, "place_bounty did not delegate to actions.place_bounty"
    assert spy.first_arg is engine
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_apply_hud_pin_action_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(actions, "apply_hud_pin_action", spy)
    result = engine.apply_hud_pin_action("open_building_interior")
    assert spy.called, "apply_hud_pin_action did not delegate to actions.apply_hud_pin_action"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == "open_building_interior", "action was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_process_command_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(console, "process_command", spy)
    result = engine.process_command("/revealmap")
    assert spy.called, "process_command did not delegate to console.process_command"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == "/revealmap", "text was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"
