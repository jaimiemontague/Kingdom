"""World/HUD render path, minimap, perf overlay — mechanical facade over :class:`game.engine.GameEngine`."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame

from config import COLOR_BLACK, MAX_ALIVE_ENEMIES
from game.graphics.font_cache import get_font
from game.systems import perf_stats

if TYPE_CHECKING:
    from game.engine import GameEngine
    from game.sim.snapshot import SimStateSnapshot


class EngineRenderCoordinator:
    """Presentation-only: pygame composite render, hero minimap, perf overlay."""

    __slots__ = ("_e",)

    def __init__(self, engine: GameEngine) -> None:
        self._e = engine

    def render(self):
        e = self._e
        skip_pygame_world = bool(
            getattr(e, "headless_ui", False) and getattr(e, "_ursina_skip_world_render", False)
        )
        if skip_pygame_world:
            e.screen.fill((0, 0, 0, 0))
        else:
            e.screen.fill(COLOR_BLACK)

        snapshot = e.build_snapshot()
        pr = getattr(e, "pygame_renderer", None)
        if pr is not None and e.screen is not None and e._scaled_surface is not None:
            pr.render_world(
                e.screen,
                snapshot,
                skip_pygame_world=skip_pygame_world,
                window_width=int(e.window_width),
                window_height=int(e.window_height),
                scaled_surface=e._scaled_surface,
            )

        if not bool(getattr(e, "screenshot_hide_ui", False)):
            e.hud.render(e.screen, e.get_game_state())
            from game.ui.micro_view_manager import ViewMode

            prev = getattr(e, "_previous_micro_view_mode", None)
            now_mode = getattr(e.micro_view, "mode", None)
            if prev == ViewMode.INTERIOR and now_mode != ViewMode.INTERIOR and e.audio_system is not None:
                e.audio_system.stop_interior_ambient()
            e._previous_micro_view_mode = now_mode

            if now_mode == ViewMode.HERO_FOCUS and getattr(e.micro_view, "quest_hero", None):
                right_rect = getattr(e.hud, "_right_rect", None)
                if right_rect:
                    minimap_rect = pygame.Rect(
                        right_rect.x, right_rect.y, right_rect.width, right_rect.height // 2
                    )
                    self._render_hero_minimap(
                        e.screen,
                        minimap_rect,
                        e.micro_view.quest_hero,
                        snapshot,
                    )

            e.debug_panel.render(e.screen, e.get_game_state())
            e.dev_tools_panel.render(e.screen)
            e.building_panel.render(e.screen, e.heroes, e.economy)

            if e.build_catalog_panel.visible:
                e.build_catalog_panel.render(e.screen, e.economy, e.buildings)

            if e.pause_menu.visible:
                try:
                    sw, sh = e.screen.get_size()
                    if int(e.pause_menu.screen_width) != int(sw) or int(e.pause_menu.screen_height) != int(sh):
                        e.pause_menu.on_resize(sw, sh)
                except Exception:
                    pass
                mp = None
                if getattr(e, "input_manager", None) is not None:
                    try:
                        mp = e.input_manager.get_mouse_pos()
                    except Exception:
                        mp = None
                if mp is not None and len(mp) >= 2:
                    e._last_ui_cursor_pos = (int(mp[0]), int(mp[1]))
                    e.pause_menu.render(e.screen, mouse_pos=(int(mp[0]), int(mp[1])))
                else:
                    gs_pm = e.get_game_state()
                    ucp = gs_pm.get("ui_cursor_pos")
                    if ucp is not None and len(ucp) >= 2:
                        e.pause_menu.render(e.screen, mouse_pos=(int(ucp[0]), int(ucp[1])))
                    else:
                        e.pause_menu.render(e.screen)

            if e.show_perf:
                self.render_perf_overlay(e.screen)

            if e.paused and not e.pause_menu.visible:
                e.screen.blit(e._pause_overlay, (0, 0))
                if e._pause_font is None:
                    e._pause_font = pygame.font.Font(None, 72)
                text = e._pause_font.render("PAUSED", True, (255, 255, 255))
                win_w = int(e.window_width)
                win_h = int(e.window_height)
                text_rect = text.get_rect(center=(win_w // 2, win_h // 2))
                e.screen.blit(text, text_rect)

        if not getattr(e, "headless_ui", False):
            try:
                pygame.display.update()
            except Exception:
                raise

    def _render_hero_minimap(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        hero,
        snapshot: SimStateSnapshot,
    ):
        e = self._e
        from game.graphics.render_context import set_render_zoom
        from game.world import Visibility

        old_zoom = e.zoom if e.zoom else 1.0
        try:
            set_render_zoom(1.0)
        except Exception:
            pass

        if getattr(e, "_minimap_surface", None) is None or e._minimap_surface.get_size() != (rect.width, rect.height):
            e._minimap_surface = pygame.Surface((rect.width, rect.height))
        mini_surf = e._minimap_surface
        mini_surf.fill(COLOR_BLACK)

        cam_x = hero.x - rect.width / 2
        cam_y = hero.y - rect.height / 2
        camera_offset = (int(cam_x), int(cam_y))

        pr = getattr(e, "pygame_renderer", None)
        if pr is not None:
            pr.render_minimap_contents(mini_surf, snapshot, camera_offset)
        else:
            w = snapshot.world
            w.render(mini_surf, camera_offset)
            for b in snapshot.buildings:
                e.renderer_registry.render_building(mini_surf, b, camera_offset)
            for en in snapshot.enemies:
                gx, gy = w.world_to_grid(getattr(en, "x", 0.0), getattr(en, "y", 0.0))
                if 0 <= gx < w.width and 0 <= gy < w.height:
                    if w.visibility[gy][gx] == Visibility.VISIBLE:
                        e.renderer_registry.render_enemy(mini_surf, en, camera_offset)
            for h in snapshot.heroes:
                e.renderer_registry.render_hero(mini_surf, h, camera_offset)
            for g in snapshot.guards:
                e.renderer_registry.render_guard(mini_surf, g, camera_offset)
            for p in snapshot.peasants:
                e.renderer_registry.render_peasant(mini_surf, p, camera_offset)
            if snapshot.tax_collector:
                e.renderer_registry.render_tax_collector(mini_surf, snapshot.tax_collector, camera_offset)
            if hasattr(w, "render_fog"):
                w.render_fog(mini_surf, camera_offset)

        pygame.draw.rect(mini_surf, (100, 100, 100), mini_surf.get_rect(), 2)
        pygame.draw.rect(mini_surf, (40, 40, 40), mini_surf.get_rect().inflate(-4, -4), 1)

        surface.blit(mini_surf, (rect.x, rect.y))

        try:
            set_render_zoom(old_zoom)
        except Exception:
            pass

    def render_perf_overlay(self, surface: pygame.Surface):
        e = self._e
        now_ms = pygame.time.get_ticks()
        if e._perf_last_ms == 0:
            e._perf_last_ms = now_ms

        if e._perf_overlay_next_update_ms == 0:
            e._perf_overlay_next_update_ms = now_ms

        if now_ms >= e._perf_overlay_next_update_ms:
            e._perf_overlay_next_update_ms = now_ms + 250
            e._perf_snapshot["fps"] = float(e.clock.get_fps())
            e._perf_snapshot["heroes"] = len([h for h in e.heroes if getattr(h, "is_alive", True)])
            e._perf_snapshot["enemies"] = len([en for en in e.enemies if getattr(en, "is_alive", False)])
            e._perf_snapshot["peasants"] = len([p for p in e.peasants if getattr(p, "is_alive", True)])
            e._perf_snapshot["guards"] = len([g for g in e.guards if getattr(g, "is_alive", False)])
            e._perf_overlay_dirty = True

        if now_ms - e._perf_last_ms >= 1000:
            e._perf_last_ms = now_ms
            e._perf_pf_calls = perf_stats.pathfinding.calls
            e._perf_pf_failures = perf_stats.pathfinding.failures
            e._perf_pf_total_ms = perf_stats.pathfinding.total_ms
            perf_stats.reset_pathfinding()
            e._perf_overlay_dirty = True

        if e._perf_overlay_panel is None or e._perf_overlay_dirty:
            e._perf_overlay_dirty = False

            fps = float(e._perf_snapshot.get("fps", 0.0))
            enemies_alive = int(e._perf_snapshot.get("enemies", 0))
            heroes_alive = int(e._perf_snapshot.get("heroes", 0))
            peasants_alive = int(e._perf_snapshot.get("peasants", 0))
            guards_alive = int(e._perf_snapshot.get("guards", 0))

            ursina_ema = getattr(e, "_ursina_window_fps_ema", None)
            if getattr(e, "_ursina_viewer", False):
                lines = [
                    f"FPS (pygame/HUD path): {fps:0.1f}",
                    "3D GPU: use top-left Ursina fps counter (not this number).",
                ]
                if ursina_ema is not None:
                    lines.append(f"Ursina dt EMA ~FPS (rough): {float(ursina_ema):0.1f}")
                lines.extend(
                    [
                        f"Entities: heroes={heroes_alive} peasants={peasants_alive} guards={guards_alive} enemies={enemies_alive} (cap={MAX_ALIVE_ENEMIES})",
                        f"Loop ms (ema): events={e._perf_events_ms:0.2f} update={e._perf_update_ms:0.2f} render={e._perf_render_ms:0.2f}",
                        f"PF calls/s: {e._perf_pf_calls}  fails/s: {e._perf_pf_failures}  ms/s: {e._perf_pf_total_ms:0.1f}",
                    ]
                )
            else:
                lines = [
                    f"FPS: {fps:0.1f}",
                    f"Entities: heroes={heroes_alive} peasants={peasants_alive} guards={guards_alive} enemies={enemies_alive} (cap={MAX_ALIVE_ENEMIES})",
                    f"Loop ms (ema): events={e._perf_events_ms:0.2f} update={e._perf_update_ms:0.2f} render={e._perf_render_ms:0.2f}",
                    f"PF calls/s: {e._perf_pf_calls}  fails/s: {e._perf_pf_failures}  ms/s: {e._perf_pf_total_ms:0.1f}",
                ]

            font = get_font(16)
            pad = 6
            w = 0
            h = 0
            rendered = []
            for line in lines:
                s = font.render(line, True, (255, 255, 255))
                rendered.append(s)
                w = max(w, s.get_width())
                h += s.get_height()

            panel = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 140))
            yy = pad
            for s in rendered:
                panel.blit(s, (pad, yy))
                yy += s.get_height()

            x_surf = font.render("X", True, (255, 255, 255))
            size = 18
            close_local = pygame.Rect(panel.get_width() - size - 4, 4, size, size)
            pygame.draw.rect(panel, (45, 45, 55), close_local)
            pygame.draw.rect(panel, (120, 120, 150), close_local, 1)
            panel.blit(x_surf, (close_local.centerx - x_surf.get_width() // 2, close_local.centery - x_surf.get_height() // 2))
            e._perf_overlay_panel = panel

        win_w = int(getattr(e, "window_width", surface.get_width()))
        win_h = int(getattr(e, "window_height", surface.get_height()))
        top_h = int(getattr(e.hud, "top_bar_height", 48))
        bottom_h = int(getattr(e.hud, "bottom_bar_height", 96))

        panel = e._perf_overlay_panel
        px = 10
        py = max(top_h + 10, win_h - bottom_h - panel.get_height() - 10)
        surface.blit(panel, (px, py))

        size = 18
        e._perf_close_rect = pygame.Rect(px + panel.get_width() - size - 4, py + 4, size, size)

    def render_pygame(self) -> float:
        e = self._e
        t2 = time.perf_counter()
        self.render()
        t3 = time.perf_counter()
        return (t3 - t2) * 1000.0
