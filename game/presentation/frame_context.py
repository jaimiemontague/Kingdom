"""
Per-frame context built once and shared across the render pipeline.

WK62 Wave 2 Task D: ``get_game_state()`` and ``build_snapshot()`` were called
multiple times per frame in the Pygame render path (HUD, debug panel, pause menu
each called ``get_game_state()`` independently).  ``FrameContext`` is constructed
once at the top of the render pass and threaded through consumers that need it,
eliminating redundant dict/snapshot construction.

Usage in GameEngine / EngineRenderCoordinator::

    ctx = FrameContext.build(engine)
    # ctx.snapshot  — RenderSnapshot (sim truth) for world/entity rendering
    # ctx.frame     — PresentationFrameState (camera/zoom/paused/selection) [WK67 Move 4]
    # ctx.game_state — dict for HUD / debug panel / pause menu
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.engine import GameEngine
    from game.sim.snapshot import PresentationFrameState, RenderSnapshot


@dataclass(slots=True)
class FrameContext:
    """Immutable-by-convention container for one frame's derived state."""

    snapshot: RenderSnapshot
    game_state: dict[str, Any]
    # WK67 Move 4 / L6: per-frame presentation state, split out of the sim
    # snapshot. The renderer entry takes ``(snapshot, frame)``; callers that
    # forward to a renderer pass ``ctx.frame`` alongside ``ctx.snapshot``.
    frame: PresentationFrameState

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @staticmethod
    def build(engine: GameEngine) -> FrameContext:
        """Build the context once from *engine*; callers share the result."""
        return FrameContext(
            snapshot=engine.build_snapshot(),
            game_state=engine.get_game_state(),
            frame=engine.build_presentation_frame(),
        )
