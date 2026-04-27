"""
WK39 Stage 4 — PygameRenderer hardening.

Avoids full ``GameEngine.render()`` / minimap pixel paths here: on Windows CI,
ordered pytest runs can trigger intermittent SDL/font access violations during
building labels when no real display is present. Integration coverage remains
``python tools/qa_smoke.py --quick`` (headless profiles).
"""

from __future__ import annotations

import pygame

from game.engine import GameEngine
from game.graphics.pygame_renderer import PygameRenderer, PygameWorldRenderContext
from game.sim.snapshot import SimStateSnapshot


def test_pygame_renderer_module_exports():
    assert issubclass(PygameRenderer, object)
    assert PygameWorldRenderContext.__dataclass_fields__


def test_headless_ui_pygame_renderer_and_snapshot():
    """Presentation stack exposes renderer + frozen snapshot without drawing a frame."""
    engine = GameEngine(headless=False, headless_ui=True)
    try:
        assert engine.pygame_renderer is not None
        assert engine.screen is not None
        snap = engine.build_snapshot()
        assert isinstance(snap, SimStateSnapshot)
        assert snap.world is engine.world
    finally:
        pygame.quit()


def test_skip_pygame_world_render_world_smoke():
    """Ursina composite branch: metrics-only path (no terrain/building raster)."""
    engine = GameEngine(headless=False, headless_ui=True)
    try:
        pr = engine.pygame_renderer
        snap = engine.build_snapshot()
        pr.render_world(
            engine.screen,
            snap,
            skip_pygame_world=True,
            window_width=int(engine.window_width),
            window_height=int(engine.window_height),
            scaled_surface=engine._scaled_surface,
        )
    finally:
        pygame.quit()
