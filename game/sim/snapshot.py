"""
Read-only render snapshot for renderers and external consumers.

WK67 Round A-2 (Move 4 / L6 — presentation split): split into two frozen
value objects so the **sim snapshot carries only sim truth**:

- :class:`RenderSnapshot` — sim truth (live entity tuples + WK66 frozen DTO
  tuples + world/fog/economy/effects). Built by ``SimEngine.build_snapshot``.
  It carries NO camera/zoom/screen/pause/selection/blend/tick state — those are
  *presentation*, not sim, and now live on ``PresentationFrameState``.
- :class:`PresentationFrameState` — engine-built per-frame presentation state
  (camera, zoom, screen size, paused/running, pause-menu visibility, selection,
  and the interpolation blend/tick). Built by ``GameEngine.build_presentation_frame``.

Both are passed to the renderer entry: ``renderer.update(render_snapshot, frame)``.

``SimStateSnapshot`` is kept as a **thin back-compat alias** for ``RenderSnapshot``
so existing non-renderer consumers (tests, FrameContext type hints) that reference
the old name keep working. New code should reference ``RenderSnapshot``.

Built once per frame by the engine; consumed by renderers. Immutable so renderers
cannot accidentally mutate simulation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderSnapshot:
    """
    Sim truth for one rendered frame — NO presentation state.

    WK67 Move 4: presentation fields (camera/zoom/screen/paused/running/
    pause_menu_visible/selected_*/sim_blend_fraction/sim_tick_id) were removed
    from this object and moved to :class:`PresentationFrameState`.

    WK68 R3 (Agent 03) — L1 killer: the seven live entity tuples
    (``buildings/heroes/enemies/peasants/guards/bounties`` + the single
    ``tax_collector``) have been DELETED. They were the last render-boundary leak
    of live, mutable sim objects. Every renderer now reads the frozen value-type
    DTO tuples below (``*_dtos`` / ``tax_collector_dto``); the world/effects
    fields that are NOT live entities (``world``/``trees``/``log_stacks``/
    ``castle``/``vfx_projectiles``/``underground_areas``/``rubble_records``)
    deliberately remain — they are out of scope for the DTO migration. A
    repo-wide grep for ``snapshot.{heroes,enemies,…}`` now returns zero
    production hits (gate D).
    """

    # --- World / map ---
    world: Any
    trees: tuple = ()
    pois: tuple = ()  # WK54: POI subset for renderer discovery checks
    log_stacks: tuple = ()
    fog_revision: int = 0

    # --- Economy / game state ---
    gold: int = 0
    wave: int = 0

    # --- Construction progress (parallel to buildings tuple) ---
    buildings_construction_progress: tuple = ()

    # --- Special entities ---
    castle: Any = None

    # --- VFX / projectiles (sim-effect data; stays sim truth) ---
    vfx_projectiles: tuple = ()

    # --- WK57: Underground areas (dict[str, UndergroundArea]) ---
    underground_areas: Any = None

    # --- WK61: Rubble records for destroyed buildings ---
    rubble_records: tuple = ()

    # --- WK66 Round A-1: frozen render DTOs (ADDITIVE) ---
    # Built alongside the live entity tuples above. The render last-mile (Round B)
    # migrates the renderers to read these instead of the live entities, then
    # removes the live tuples. Value-type only (see game/sim/render_dto.py) so the
    # renderer cannot mutate sim state through them.
    hero_dtos: tuple = ()
    enemy_dtos: tuple = ()
    peasant_dtos: tuple = ()
    guard_dtos: tuple = ()
    tax_collector_dto: Any = None
    building_dtos: tuple = ()
    bounty_dtos: tuple = ()
    # WK138 (adventure ledger foundation): read-only quest-chain snapshot tuples
    # for render/UI consumers. Empty default keeps no-chain builds as a fast
    # no-op and preserves the WK67 digest path.
    quest_chains: tuple = ()


@dataclass(frozen=True)
class PresentationFrameState:
    """
    Engine-built per-frame presentation state — NOT sim truth.

    WK67 Move 4 / L6: these fields used to be stuffed into the sim snapshot via
    ``SimEngine.build_snapshot``'s presentation kwargs. The sim does not know
    about cameras, zoom, screen size, pause, selection, or render interpolation,
    so they now live here, built by ``GameEngine.build_presentation_frame`` from
    engine-owned state, and are passed to the renderer alongside the
    :class:`RenderSnapshot`.
    """

    # --- Camera (needed by renderers for coordinate mapping) ---
    camera_x: float = 0.0
    camera_y: float = 0.0
    zoom: float = 1.0
    default_zoom: float = 1.0

    # --- Display ---
    screen_w: int = 1920
    screen_h: int = 1080

    # --- UI/run state (HUD/menu gating) ---
    paused: bool = False
    running: bool = True
    pause_menu_visible: bool = False

    # --- Interpolation (R4: blend fraction + tick counter for smooth rendering) ---
    sim_blend_fraction: float = 0.0
    sim_tick_id: int = 0

    # --- Selection (for UI highlights in 3D) ---
    selected_hero: Any = None
    selected_building: Any = None


# --- Back-compat alias -------------------------------------------------------
# WK67 Move 4: ``RenderSnapshot`` is the canonical sim-truth render snapshot.
# Pre-WK67 code/tests reference ``SimStateSnapshot``; it is now exactly the same
# class. New code should use ``RenderSnapshot``. (The presentation fields that
# used to live on ``SimStateSnapshot`` now live on ``PresentationFrameState``.)
SimStateSnapshot = RenderSnapshot
