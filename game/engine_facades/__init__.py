"""Small collaborators that own slices of :class:`game.engine.GameEngine` presentation logic."""

from game.engine_facades.camera_display import EngineCameraDisplay
from game.engine_facades.render_coordinator import EngineRenderCoordinator

__all__ = ["EngineCameraDisplay", "EngineRenderCoordinator"]
