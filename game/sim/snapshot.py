"""
Read-only simulation state snapshot for renderers and external consumers.

Built once per frame by the engine; consumed by UrsinaRenderer.update(snapshot).
Immutable so renderers cannot accidentally mutate simulation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SimStateSnapshot:
    """
    Everything a renderer needs to draw one frame.

    Entity lists are shallow copies of the engine's live lists.
    Individual entities are still mutable (the renderer reads but must
    not write to them), but the list membership is frozen.
    """

    # --- Core entity lists (shallow-copied from engine) ---
    buildings: tuple
    heroes: tuple
    enemies: tuple
    peasants: tuple
    guards: tuple
    bounties: tuple

    # --- World / map ---
    world: Any
    trees: tuple = ()
    fog_revision: int = 0

    # --- Economy / game state ---
    gold: int = 0
    wave: int = 0

    # --- Construction progress (parallel to buildings tuple) ---
    buildings_construction_progress: tuple = ()

    # --- Selection state (for UI highlights in 3D) ---
    selected_hero: Any = None
    selected_building: Any = None

    # --- Special entities ---
    castle: Any = None
    tax_collector: Any = None

    # --- VFX / projectiles ---
    vfx_projectiles: tuple = ()

    # --- Display ---
    screen_w: int = 1920
    screen_h: int = 1080

    # --- Camera (needed by UrsinaApp for coordinate mapping) ---
    camera_x: float = 0.0
    camera_y: float = 0.0
    zoom: float = 1.0
    default_zoom: float = 1.0

    # --- UI state (needed by UrsinaApp for HUD/menu gating) ---
    paused: bool = False
    running: bool = True
    pause_menu_visible: bool = False

