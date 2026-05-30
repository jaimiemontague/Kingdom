"""WK78 Round B-2f (Wave W2) — engine.py per-frame lifecycle facade SEAM tests.

Sprint: wk78_round_b2_engine_lifecycle_facade
Owner:  Agent 11 (QA_TestEngineering_Lead)

PURPOSE
-------
WK78 extracted the GameEngine per-frame *lifecycle* methods out of
``game/engine.py`` (1184 -> ~1072 LOC) into one module, each behind a **one-line
delegating wrapper** that keeps the original ``GameEngine`` method name working
for every caller (``run()`` -> ``self.update()``; the ursina/pygame loop ->
``self.tick_simulation()``) and every test:

    game/engine_facades/lifecycle.py   update(engine, dt)
                                       _prepare_sim_and_camera(engine, dt) -> bool
                                       _update_render_animations(engine, dt)
                                       tick_simulation(engine, dt) -> (float, float)

These are **seam** tests (not behavior tests — the WK67 digest /
characterization nets + qa_smoke + the sanity screenshot cover behavior). They
lock the *structure* of the split so a later refactor that deletes the module,
renames a public function, or accidentally stops a wrapper from delegating is
caught immediately. For each extracted function we assert:

  (a) the new module imports and its public free function exists + is callable;
  (b) the ``GameEngine`` wrapper actually DELEGATES to that module function — we
      monkeypatch the module function with a spy, call the wrapper on a real
      (constructed) headless ``GameEngine``, and assert the spy fired with the
      live engine as its first positional arg (and that the wrapper forwards its
      own extra args through unchanged + returns the module function's result).

The wrappers do a local ``from game.engine_facades import lifecycle`` then call
``lifecycle.<fn>(self, ...)``, so patching the function *attribute on the module
object* (what ``monkeypatch.setattr`` does) is seen by the wrapper on the very
next call — no production code is touched.

We also guard DoD §E: the extracted module may not import ``game.engine`` at
runtime (TYPE_CHECKING-only), so the split stays cycle-free.

Headless: SDL dummy drivers so the real ``GameEngine`` constructs without a
display (mirrors tests/test_wk76_engine_selection_facade.py + test_wk67_ai_boundary.py).
"""

from __future__ import annotations

import os

import pytest

# Headless-friendly drivers so a real engine constructs without a display/audio.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.engine import GameEngine
from game.engine_facades import lifecycle


# The 4 public free functions extracted into game/engine_facades/lifecycle.py.
# Each is also the name of the GameEngine wrapper that must delegate to it.
LIFECYCLE_FUNCS = (
    "update",
    "_prepare_sim_and_camera",
    "_update_render_animations",
    "tick_simulation",
)


# ---------------------------------------------------------------------------
# Shared headless engine (module-scoped — these are read-only seam checks; we
# monkeypatch module functions with spies, never run the real lifecycle bodies,
# so the engine's gameplay state is never mutated/advanced).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def engine():
    """A real headless ``GameEngine`` to act as the ``self`` the wrappers delegate.

    Built via ``GameEngine(headless=True)`` (same construction the WK67/75/76
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
    """lifecycle.py exposes all 4 documented public free functions, callable."""
    for name in LIFECYCLE_FUNCS:
        assert callable(getattr(lifecycle, name, None)), (
            f"lifecycle.{name} missing/uncallable"
        )


def test_wrappers_present_on_gameengine():
    """All 4 wrapper method names still live on GameEngine (call sites unchanged)."""
    for name in LIFECYCLE_FUNCS:
        assert callable(getattr(GameEngine, name, None)), (
            f"GameEngine.{name} wrapper missing/uncallable (call sites would break)"
        )


def test_lifecycle_module_does_not_import_engine_at_runtime():
    """DoD §E guard: lifecycle.py must not create a GameEngine import cycle.

    It takes ``engine`` as a duck-typed parameter; a top-level
    ``import game.engine`` / ``from game.engine import ...`` (only a
    ``TYPE_CHECKING`` one is allowed) would reintroduce the cycle the split was
    designed to avoid.
    """
    import ast
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    path = repo_root / "game" / "engine_facades" / "lifecycle.py"
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
                    f"lifecycle module has a runtime import of '{n}' — that "
                    "reintroduces the GameEngine import cycle (DoD §E)"
                )


# ===========================================================================
# Part B — each GameEngine wrapper DELEGATES to its lifecycle module function
# ===========================================================================
#
# Pattern: replace the module's public function with a spy, call the GameEngine
# wrapper, assert the spy fired with ``engine`` (the live engine) as first arg
# and that the wrapper forwarded its own extra params unchanged + returned the
# module function's result. We monkeypatch the module fns so the real per-frame
# bodies never run — the shared engine's gameplay state is never advanced.


def test_wrapper_update_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(lifecycle, "update", spy)
    result = engine.update(0.05)
    assert spy.called, "update did not delegate to lifecycle.update"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == 0.05, "dt was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_prepare_sim_and_camera_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(lifecycle, "_prepare_sim_and_camera", spy)
    result = engine._prepare_sim_and_camera(0.016)
    assert spy.called, "_prepare_sim_and_camera did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == 0.016, "dt was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_update_render_animations_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(lifecycle, "_update_render_animations", spy)
    result = engine._update_render_animations(0.033)
    assert spy.called, "_update_render_animations did not delegate"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == 0.033, "dt was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"


def test_wrapper_tick_simulation_delegates(engine, monkeypatch):
    sentinel = object()
    spy = _Spy(return_value=sentinel)
    monkeypatch.setattr(lifecycle, "tick_simulation", spy)
    result = engine.tick_simulation(0.1)
    assert spy.called, "tick_simulation did not delegate to lifecycle.tick_simulation"
    args, _ = spy.calls[0]
    assert args[0] is engine
    assert args[1] == 0.1, "dt was not forwarded"
    assert result is sentinel, "wrapper did not return the module function's result"
