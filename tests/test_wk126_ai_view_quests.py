"""WK126 T4 (WK133 sprint) — AiGameView quest surface (Agent 03 dataclass side).

Pins the read-only quest fields on ``AiGameView``:

* ``quests: tuple = ()`` and ``quest_givers: tuple = ()`` exist on the dataclass
  and default to EMPTY tuples — so the view stays constructible without any
  quest infrastructure (fixture/test construction, and digest guard #1: an
  engine with no Herald's Posts/quests hands the AI empty tuples and the quest
  behavior no-ops, keeping the WK67 keystone digest byte-identical).
* ``SimEngine.build_ai_view()`` on a fresh headless engine (which has no quests)
  carries both fields as empty tuples.

FORWARD-COMPATIBLE NOTE: Agent 05 populates the tuples from
``sim_engine.build_ai_view`` in a parallel lane. These pins hold BOTH before and
after that lands — a no-quest engine must yield empty tuples either way (via
dataclass default now, via an empty ``tuple(self.quests)`` after).

Style mirrors ``tests/test_wk67_ai_boundary.py`` Pin 3 (``test_ai_view_purity``):
headless GameEngine + pygame.quit() in a finally.
"""

from __future__ import annotations

import os
from dataclasses import fields

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.engine import GameEngine
from game.sim.ai_view import AiGameView


def _ai_view_field(name: str):
    matches = [f for f in fields(AiGameView) if f.name == name]
    assert matches, f"AiGameView is missing the '{name}' field (WK126 T4 contract)"
    return matches[0]


def test_quest_fields_exist_and_default_empty():
    """``quests`` / ``quest_givers`` are dataclass fields defaulting to ()."""
    for name in ("quests", "quest_givers"):
        f = _ai_view_field(name)
        assert f.default == (), (
            f"AiGameView.{name} must default to an EMPTY tuple so the view is "
            "constructible without quest infrastructure (digest guard #1)"
        )


def test_view_constructible_without_quest_args():
    """The frozen dataclass constructs without quest kwargs (defaults apply).

    This is the forward-compatible half: before Agent 05's populate lands,
    ``build_ai_view`` passes no quest kwargs and must still construct.
    """
    view = AiGameView(
        world=None,
        heroes=(),
        enemies=(),
        buildings=(),
        bounties=(),
        pois=(),
        player_gold=0,
        castle=None,
        wave=0,
    )
    assert view.quests == ()
    assert view.quest_givers == ()
    assert isinstance(view.quests, tuple)
    assert isinstance(view.quest_givers, tuple)


def test_build_ai_view_carries_empty_quest_tuples_on_no_quest_engine():
    """A fresh headless engine (no Herald's Posts, no quests) yields empty tuples.

    Digest guard #1 relies on this: the AI quest behavior's first guard is
    ``if not view.quest_givers: return False`` (no RNG draw, no state change),
    so an empty surface keeps the WK67 keystone digest byte-identical.
    """
    engine = GameEngine(headless=True)
    try:
        view = engine.sim.build_ai_view()
        assert hasattr(view, "quests") and hasattr(view, "quest_givers")
        assert isinstance(view.quests, tuple), "AiGameView.quests must be a tuple"
        assert isinstance(view.quest_givers, tuple), (
            "AiGameView.quest_givers must be a tuple"
        )
        assert view.quests == (), (
            "a no-quest engine must hand the AI an EMPTY quests tuple"
        )
        assert view.quest_givers == (), (
            "a no-quest engine must hand the AI an EMPTY quest_givers tuple"
        )
    finally:
        pygame.quit()


def test_quest_fields_are_read_only():
    """The frozen dataclass rejects writes — the AI cannot mutate the surface."""
    import dataclasses

    import pytest

    view = AiGameView(
        world=None,
        heroes=(),
        enemies=(),
        buildings=(),
        bounties=(),
        pois=(),
        player_gold=0,
        castle=None,
        wave=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.quests = ("mutated",)  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.quest_givers = ("mutated",)  # type: ignore[misc]
