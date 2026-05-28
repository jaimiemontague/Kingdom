"""
Per-frame context built once and shared across the render pipeline.

WK62 Wave 2 Task D: ``get_game_state()`` and ``build_snapshot()`` were called
multiple times per frame in the Pygame render path (HUD, debug panel, pause menu
each called ``get_game_state()`` independently).  ``FrameContext`` is constructed
once at the top of the render pass and threaded through consumers that need it,
eliminating redundant dict/snapshot construction.

Usage in GameEngine / EngineRenderCoordinator::

    ctx = FrameContext.build(engine)
    # ctx.snapshot  — SimStateSnapshot for world/entity rendering
    # ctx.game_state — dict for HUD / debug panel / pause menu
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.engine import GameEngine
    from game.sim.snapshot import SimStateSnapshot


@dataclass(slots=True)
class FrameContext:
    """Immutable-by-convention container for one frame's derived state."""

    snapshot: SimStateSnapshot
    game_state: dict[str, Any]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @staticmethod
    def build(engine: GameEngine) -> FrameContext:
        """Build the context once from *engine*; callers share the result."""
        return FrameContext(
            snapshot=engine.build_snapshot(),
            game_state=engine.get_game_state(),
        )
