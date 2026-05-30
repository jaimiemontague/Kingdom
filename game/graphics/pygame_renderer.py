"""
Pygame world-layer rendering (terrain, entities, fog, bounties, VFX, zoom).

Consumes :class:`~game.sim.snapshot.SimStateSnapshot` each frame, matching the
`UrsinaRenderer.update(snapshot)` contract.

**In-world UI** (drawn into the scrolled / zoom-correct ``view_surface``):

- ``BuildingMenu`` — placement preview and ghost cursor
- ``BuildingListPanel`` — economic building picker when visible

**Screen-space UI** (stays in :meth:`game.engine.GameEngine.render`):

- ``BuildingPanel`` — details for the selected constructed building
- ``BuildCatalogPanel``, ``PauseMenu``, ``HUD``, ``DebugPanel``, ``DevToolsPanel``,
  perf overlay, pause tint, hero-focus minimap parent blit

This split keeps world coordinates in one pipeline and window coordinates in another.

Non-snapshot dependencies used alongside each snapshot are bundled in
:class:`PygameWorldRenderContext` so call sites stay snapshot-first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pygame

from config import COLOR_BLACK
from game.graphics.render_context import set_render_zoom
from game.graphics.world_terrain_renderer import WorldTerrainRenderer
from game.logging import get_logger
from game.world import Visibility

if TYPE_CHECKING:
    from game.sim.snapshot import PresentationFrameState, SimStateSnapshot


_log = get_logger(__name__)


@dataclass
class PygameWorldRenderContext:
    """
    Stable pygame-world collaborators not duplicated on :class:`~game.sim.snapshot.SimStateSnapshot`.

    Snapshot carries entities/world/camera; this carries registry, bounty/VFX hooks,
    and in-world UI widgets.
    """

    renderer_registry: Any
    bounty_system: Any
    vfx_system: Any
    building_menu: Any
    building_list_panel: Any
    economy: Any


class PygameRenderer:
    """World/entity pygame draw pass driven by ``SimStateSnapshot``."""

    def __init__(self, ctx: PygameWorldRenderContext):
        self._ctx = ctx
        self._view_surface: pygame.Surface | None = None
        self._view_surface_size: tuple[int, int] = (0, 0)
        # WK66 L10: terrain/fog drawing moved off the sim's World onto a
        # graphics-side renderer (one instance owns the reusable fog Surfaces).
        self._world_terrain = WorldTerrainRenderer()

    def _draw_world_layers(
        self,
        target: pygame.Surface,
        snapshot: SimStateSnapshot,
        camera_offset: tuple[int, int],
        *,
        place_building_ui: bool,
        draw_vfx: bool,
        draw_fog: bool,
        bounty_pipeline: bool,
    ) -> None:
        """Shared map + units path (main window or minimap viewport)."""
        ctx = self._ctx
        world = snapshot.world

        self._world_terrain.render(world, target, camera_offset)

        for building in snapshot.building_dtos:  # WK66 Move 3: draw from frozen DTOs (no write-back)
            ctx.renderer_registry.render_building(target, building, camera_offset)

        for enemy in snapshot.enemy_dtos:  # WK66 Move 3: draw from frozen DTOs
            gx, gy = world.world_to_grid(getattr(enemy, "x", 0.0), getattr(enemy, "y", 0.0))
            if 0 <= gx < world.width and 0 <= gy < world.height:
                if world.visibility[gy][gx] != Visibility.VISIBLE:
                    continue
            else:
                continue
            ctx.renderer_registry.render_enemy(target, enemy, camera_offset)

        for hero in snapshot.hero_dtos:  # WK66 Move 3: draw from frozen DTOs
            ctx.renderer_registry.render_hero(target, hero, camera_offset)

        # WK68 R2 (Agent 09): guards/peasants/tax-collector now draw from frozen DTOs.
        # The WK68 R1/R2 UnitDTO carries every field the WorkerRenderer.render path reads
        # (is_alive/is_inside_castle/x/y/size/hp/max_hp/carried_gold and a ``state`` alias
        # == state_name for the tax "Collecting..." label). The registry's
        # ``getattr(x, "render_state", x)`` returns the DTO itself (no render_state attr),
        # exactly as the already-migrated hero/enemy draws above.
        for guard in snapshot.guard_dtos:
            ctx.renderer_registry.render_guard(target, guard, camera_offset)

        for peasant in snapshot.peasant_dtos:
            ctx.renderer_registry.render_peasant(target, peasant, camera_offset)

        if snapshot.tax_collector_dto is not None:
            ctx.renderer_registry.render_tax_collector(target, snapshot.tax_collector_dto, camera_offset)

        if place_building_ui:
            ctx.building_menu.render(target, camera_offset)

            if ctx.building_list_panel.visible:
                selected_type = getattr(ctx.building_menu, "selected_building", None)
                # WK68 R2 (Agent 09): availability check reads only building_type +
                # is_constructed; both are on BuildingDTO (building_type is the same
                # lowercase string a BuildingType str-enum compares equal to).
                ctx.building_list_panel.render(
                    target,
                    ctx.economy,
                    snapshot.building_dtos,
                    selected_type,
                )

        if draw_vfx and ctx.vfx_system is not None and hasattr(ctx.vfx_system, "render"):
            try:
                ctx.vfx_system.render(target, camera_offset)
            except Exception:
                # WK65 Round 0: behavior unchanged (still swallow) — now observable.
                _log.exception("VFX render failed")

        if draw_fog:
            self._world_terrain.render_fog(world, target, camera_offset)

        if bounty_pipeline:
            # WK68 R3 (Agent 03): bounty ``update_ui_metrics`` (a sim-state mutation
            # keyed on live-object identity, NOT a render read) was relocated to
            # ``SimEngine.build_snapshot`` — the renderer no longer touches the live
            # entity tuples (L1 killed). The bounty DRAW below is fully DTO-migrated.
            # WK68 R2 (Agent 09): bounty flags draw from frozen BountyDTOs (the renderer
            # reads only claimed/x/y/bounty_id/reward/responders/attractiveness_tier — all
            # carried by BountyDTO). Mirrors the Ursina path (_sync_snapshot_bounties).
            ctx.renderer_registry.render_bounties(
                target,
                list(snapshot.bounty_dtos),
                camera_offset,
            )

    def render_world(
        self,
        screen: pygame.Surface,
        snapshot: SimStateSnapshot,
        frame: "PresentationFrameState | None" = None,
        *,
        skip_pygame_world: bool,
        window_width: int,
        window_height: int,
        scaled_surface: pygame.Surface,
    ) -> None:
        """
        Draw world layers to ``screen`` (or an offscreen ``view_surface`` then scale).

        When ``skip_pygame_world`` is True (Ursina compositing), fills are handled by
        the caller and this method is a no-op (the pygame world layers are not drawn).
        WK68 R3: the bounty ``update_ui_metrics`` that used to run here on the Ursina
        path was relocated to ``SimEngine.build_snapshot`` so the renderer no longer
        reads the (now-deleted) live entity tuples.

        WK67 Move 4 / L6: camera/zoom are *presentation* state and now arrive on
        ``frame`` (a :class:`~game.sim.snapshot.PresentationFrameState`), not on the
        sim ``snapshot``. ``frame`` defaults to a neutral ``PresentationFrameState()``
        so smoke/metrics-only callers that don't drive a camera keep working; the real
        engine render path always passes ``ctx.frame``.
        """
        if frame is None:
            from game.sim.snapshot import PresentationFrameState

            frame = PresentationFrameState()

        zoom = float(frame.zoom) if frame.zoom else 1.0

        # Pixel art: quantize camera to integer pixels to reduce shimmer.
        camera_offset = (int(frame.camera_x), int(frame.camera_y))

        # Render-only context (do not affect simulation determinism).
        try:
            set_render_zoom(zoom)
        except Exception:
            pass

        if skip_pygame_world:
            view_surface = screen
        elif abs(zoom - 1.0) < 1e-6:
            # If not zoomed, render directly to the screen to avoid an expensive smoothscale.
            view_surface = screen
        else:
            # Render world + entities to a zoomed "camera view" surface, then scale to window.
            win_w = int(window_width)
            win_h = int(window_height)
            view_w = max(1, int(win_w / zoom))
            view_h = max(1, int(win_h / zoom))
            if self._view_surface is None or self._view_surface_size != (view_w, view_h):
                self._view_surface = pygame.Surface((view_w, view_h))
                self._view_surface_size = (view_w, view_h)
            view_surface = self._view_surface
            view_surface.fill(COLOR_BLACK)

        if not skip_pygame_world:
            self._draw_world_layers(
                view_surface,
                snapshot,
                camera_offset,
                place_building_ui=True,
                draw_vfx=True,
                draw_fog=True,
                bounty_pipeline=True,
            )

            if view_surface is not screen:
                win_w = int(window_width)
                win_h = int(window_height)
                try:
                    pygame.transform.scale(view_surface, (win_w, win_h), scaled_surface)
                    screen.blit(scaled_surface, (0, 0))
                except Exception:
                    raise
        # WK68 R3 (Agent 03): when Ursina composits the world (skip_pygame_world),
        # the bounty ``update_ui_metrics`` that used to run here was relocated to
        # ``SimEngine.build_snapshot`` (it runs once per snapshot build, before the
        # bounty DTOs), so HUD/minimap bounty metrics stay consistent without the
        # renderer touching the deleted live entity tuples.

    def render_minimap_contents(
        self,
        target: pygame.Surface,
        snapshot: SimStateSnapshot,
        camera_offset: tuple[int, int],
    ) -> None:
        """
        Hero-focus minimap: same map/unit fog rules as main view, without placement UI,
        VFX, or bounty overlays (matches legacy ``_render_hero_minimap`` composition).
        """
        self._draw_world_layers(
            target,
            snapshot,
            camera_offset,
            place_building_ui=False,
            draw_vfx=False,
            draw_fog=True,
            bounty_pipeline=False,
        )
