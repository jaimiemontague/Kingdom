"""WK124-T5 (Agent 09): builder-peasant must NOT show the "circle-with-a-P" placeholder
when attacked.

ROOT CAUSE: ``assets/sprites/workers/peasant_builder/`` ships only ``idle/ walk/ work/`` --
no ``hurt/`` or ``dead/`` PNGs. The old ``WorkerSpriteLibrary.clips_for`` built those
missing-action clips from ``_procedural_frames`` (the letter-on-circle "P" placeholder), so
a builder taking damage visibly became the P-circle for the one-shot.

FIX (worker_sprites.py::clips_for): when an action has no real PNG frames AND the unit DOES
have some real art, reuse THIS unit's real ``idle`` clip frames instead of the procedural
placeholder. The procedural fallback is kept only when the unit has NO real art at all.

These assertions are headless and GPU-free -- they exercise the pure pygame sprite-build
path, not the Ursina renderer.
"""
from __future__ import annotations

import os

import pytest

# Headless: no real display/audio device for pygame.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.graphics.worker_sprites import WorkerSpriteLibrary


@pytest.fixture(autouse=True)
def _pygame_and_clean_cache():
    """Init pygame (font/display needed by the procedural path) and clear the clip cache.

    The clip cache is keyed by (worker_type, size); clearing it before each test makes the
    assertions independent of import/load order elsewhere in the suite.
    """
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except Exception:
        pass
    WorkerSpriteLibrary._cache.clear()
    yield
    WorkerSpriteLibrary._cache.clear()


def _frames_equal(a, b) -> bool:
    """Frame lists are equal iff same length and each surface is byte-identical."""
    if len(a) != len(b):
        return False
    for fa, fb in zip(a, b):
        if fa.get_size() != fb.get_size():
            return False
        if pygame.image.tostring(fa, "RGBA") != pygame.image.tostring(fb, "RGBA"):
            return False
    return True


def test_peasant_builder_hurt_falls_back_to_idle_not_procedural():
    """peasant_builder has no hurt/dead PNGs -> hurt/dead must reuse the real idle clip,
    NOT the procedural "P-circle" placeholder."""
    clips = WorkerSpriteLibrary.clips_for("peasant_builder")
    idle_frames = clips["idle"].frames

    assert _frames_equal(clips["hurt"].frames, idle_frames), (
        "builder 'hurt' must fall back to the unit's real idle frames (not the P-circle)"
    )
    assert _frames_equal(clips["dead"].frames, idle_frames), (
        "builder 'dead' must fall back to the unit's real idle frames (not the P-circle)"
    )


def test_peasant_builder_fallback_is_not_the_procedural_placeholder():
    """Direct guard against regression: the builder's hurt frames must DIFFER from the
    procedural placeholder frames that would have been generated for the same action."""
    from game.graphics.worker_sprites import WorkerSpriteSpec

    clips = WorkerSpriteLibrary.clips_for("peasant_builder")
    spec = WorkerSpriteSpec(size=32)
    base_color = WorkerSpriteLibrary._type_color("peasant_builder")
    procedural = WorkerSpriteLibrary._procedural_frames("peasant_builder", "hurt", base_color, spec)

    assert not _frames_equal(clips["hurt"].frames, procedural), (
        "builder 'hurt' must NOT be the procedural P-circle placeholder"
    )


def test_regular_peasant_keeps_its_own_hurt_art():
    """Regular peasant HAS hurt PNGs -> its hurt clip must use its own art, distinct from
    idle (i.e. unaffected by the fallback change)."""
    clips = WorkerSpriteLibrary.clips_for("peasant")
    assert not _frames_equal(clips["hurt"].frames, clips["idle"].frames), (
        "regular peasant has real hurt art; hurt frames must NOT equal idle frames"
    )
