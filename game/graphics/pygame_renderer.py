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
from game.world import Visibility

if TYPE_CHECKING:
    from game.sim.snapshot import SimStateSnapshot


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

        world.render(target, camera_offset)

        for building in snapshot.buildings:
            ctx.renderer_registry.render_building(target, building, camera_offset)

        for enemy in snapshot.enemies:
            gx, gy = world.world_to_grid(getattr(enemy, "x", 0.0), getattr(enemy, "y", 0.0))
            if 0 <= gx < world.width and 0 <= gy < world.height:
                if world.visibility[gy][gx] != Visibility.VISIBLE:
                    continue
            else:
                continue
            ctx.renderer_registry.render_enemy(target, enemy, camera_offset)

        for hero in snapshot.heroes:
            ctx.renderer_registry.render_hero(target, hero, camera_offset)

        for guard in snapshot.guards:
            ctx.renderer_registry.render_guard(target, guard, camera_offset)

        for peasant in snapshot.peasants:
            ctx.renderer_registry.render_peasant(target, peasant, camera_offset)

        if snapshot.tax_collector:
            ctx.renderer_registry.render_tax_collector(target, snapshot.tax_collector, camera_offset)

        if place_building_ui:
            ctx.building_menu.render(target, camera_offset)

            if ctx.building_list_panel.visible:
                selected_type = getattr(ctx.building_menu, "selected_building", None)
                ctx.building_list_panel.render(
                    target,
                    ctx.economy,
                    snapshot.buildings,
                    selected_type,
                )

        if draw_vfx and ctx.vfx_system is not None and hasattr(ctx.vfx_system, "render"):
            try:
                ctx.vfx_system.render(target, camera_offset)
            except Exception:
                pass

        if draw_fog and hasattr(world, "render_fog"):
            world.render_fog(target, camera_offset)

        if bounty_pipeline:
            if hasattr(ctx.bounty_system, "update_ui_metrics"):
                try:
                    ctx.bounty_system.update_ui_metrics(
                        snapshot.heroes,
                        snapshot.enemies,
                        snapshot.buildings,
                    )
                except Exception:
                    pass
            ctx.renderer_registry.render_bounties(
                target,
                list(snapshot.bounties),
                camera_offset,
            )

    def render_world(
        self,
        screen: pygame.Surface,
        snapshot: SimStateSnapshot,
        *,
        skip_pygame_world: bool,
        window_width: int,
        window_height: int,
        scaled_surface: pygame.Surface,
    ) -> None:
        """
        Draw world layers to ``screen`` (or an offscreen ``view_surface`` then scale).

        When ``skip_pygame_world`` is True (Ursina compositing), fills are handled by
        the caller; this method only runs bounty ``update_ui_metrics`` so HUD/minimap
        stay consistent — same ordering as pre-extraction ``GameEngine.render``.
        """
        zoom = float(snapshot.zoom) if snapshot.zoom else 1.0

        # Pixel art: quantize camera to integer pixels to reduce shimmer.
        camera_offset = (int(snapshot.camera_x), int(snapshot.camera_y))

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
        else:
            ctx = self._ctx
            if hasattr(ctx.bounty_system, "update_ui_metrics"):
                try:
                    ctx.bounty_system.update_ui_metrics(
                        snapshot.heroes,
                        snapshot.enemies,
                        snapshot.buildings,
                    )
                except Exception:
                    pass

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
