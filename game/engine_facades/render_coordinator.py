"""World/HUD render path, minimap, perf overlay — mechanical facade over :class:`game.engine.GameEngine`."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

import pygame

from config import COLOR_BLACK, MAX_ALIVE_ENEMIES
from game.graphics.font_cache import get_font
from game.presentation.frame_context import FrameContext
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

        # WK62 Task D: build FrameContext ONCE and reuse across the entire
        # render pass.  Previously get_game_state() was called up to 3 times
        # per frame (HUD, debug panel, pause menu) and build_snapshot() once.
        ctx = FrameContext.build(e)
        snapshot = ctx.snapshot
        game_state = ctx.game_state

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
            e.hud.render(e.screen, game_state)

            watch_map_rect = getattr(e.hud, "watch_card_map_rect", None)
            if watch_map_rect is not None:
                pin_slot = getattr(e.hud, "_pin_slot", None)
                pinned_id = getattr(pin_slot, "hero_id", None) if pin_slot else None
                if pinned_id:
                    pinned_hero = next(
                        (
                            h
                            for h in snapshot.heroes
                            if str(getattr(h, "hero_id", "")) == pinned_id
                            and int(getattr(h, "hp", 0)) > 0
                        ),
                        None,
                    )
                    if pinned_hero is not None:
                        self._render_hero_minimap(e.screen, watch_map_rect, pinned_hero, snapshot)

            from game.ui.micro_view_manager import ViewMode

            prev = getattr(e, "_previous_micro_view_mode", None)
            now_mode = getattr(e.micro_view, "mode", None)
            if prev == ViewMode.INTERIOR and now_mode != ViewMode.INTERIOR and e.audio_system is not None:
                e.audio_system.stop_interior_ambient()
            e._previous_micro_view_mode = now_mode

            if now_mode == ViewMode.HERO_FOCUS and getattr(e.micro_view, "quest_hero", None):
                right_rect = getattr(e.hud, "_right_rect", None)
                if right_rect is not None and right_rect.width > 0:
                    minimap_rect = pygame.Rect(
                        right_rect.x, right_rect.y, right_rect.width, right_rect.height // 2
                    )
                    self._render_hero_minimap(
                        e.screen,
                        minimap_rect,
                        e.micro_view.quest_hero,
                        snapshot,
                    )

            e.debug_panel.render(e.screen, game_state)
            e.dev_tools_panel.render(e.screen)
            lr_bp = getattr(e.hud, "_last_left_rect", None)
            if lr_bp is not None:
                e.building_panel.render(e.screen, e.heroes, e.economy, left_rect=pygame.Rect(lr_bp))
            else:
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
                    ucp = game_state.get("ui_cursor_pos")
                    if ucp is not None and len(ucp) >= 2:
                        e.pause_menu.render(e.screen, mouse_pos=(int(ucp[0]), int(ucp[1])))
                    else:
                        e.pause_menu.render(e.screen)

            if e.show_perf:
                self.render_perf_overlay(e.screen)

            if e.paused and not e.pause_menu.visible:
                mc = getattr(e.hud, "memorial_card", None)
                bio = getattr(e.hud, "building_interior_overlay", None)
                modal = (mc is not None and getattr(mc, "visible", False)) or (
                    bio is not None and getattr(bio, "visible", False)
                )
                if not modal:
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

        dest = pygame.Rect(rect.x, rect.y, mini_surf.get_width(), mini_surf.get_height())
        prev_clip = surface.get_clip()
        try:
            surface.set_clip(dest.clip(surface.get_clip()))
            surface.blit(mini_surf, dest.topleft)
        finally:
            surface.set_clip(prev_clip)

        hud = getattr(e, "hud", None)
        if hud is not None:
            hud.watch_card_map_world_center = (float(hero.x), float(hero.y))
            hud.watch_card_map_world_wh = (float(rect.width), float(rect.height))

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

        # --- Collect frame time every frame (not throttled) ---
        ursina_dt = getattr(e, "_last_frame_dt_ms", 0.0)
        if ursina_dt > 0.1:
            frame_ms = ursina_dt
        else:
            frame_ms = float(e.clock.get_rawtime())
        ft = e._smoothness_frame_times
        ft.append(frame_ms)
        if len(ft) > e._smoothness_max_frames:
            del ft[: len(ft) - e._smoothness_max_frames]

        if now_ms >= e._perf_overlay_next_update_ms:
            e._perf_overlay_next_update_ms = now_ms + 250
            e._perf_snapshot["fps"] = float(e.clock.get_fps())
            e._perf_snapshot["heroes"] = sum(1 for h in e.heroes if getattr(h, "is_alive", True))
            e._perf_snapshot["enemies"] = sum(1 for en in e.enemies if getattr(en, "is_alive", False))
            e._perf_snapshot["peasants"] = sum(1 for p in e.peasants if getattr(p, "is_alive", True))
            e._perf_snapshot["guards"] = sum(1 for g in e.guards if getattr(g, "is_alive", False))
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
            e._perf_overlay_panel = self._build_perf_panel()

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

    # ------------------------------------------------------------------
    # Smoothness monitor panel builder
    # ------------------------------------------------------------------

    def _build_perf_panel(self) -> pygame.Surface:
        e = self._e
        font = get_font(16)
        small_font = get_font(13)
        pad = 6
        graph_w = 302
        graph_h = 60

        fps = float(e._perf_snapshot.get("fps", 0.0))
        enemies_alive = int(e._perf_snapshot.get("enemies", 0))
        heroes_alive = int(e._perf_snapshot.get("heroes", 0))
        peasants_alive = int(e._perf_snapshot.get("peasants", 0))
        guards_alive = int(e._perf_snapshot.get("guards", 0))

        # --- Compute smoothness metrics from ring buffer ---
        ft = e._smoothness_frame_times
        n = len(ft)
        p50 = p95 = p99 = jitter = low_1pct_fps = 0.0
        if n >= 10:
            sorted_ft = sorted(ft)
            p50 = sorted_ft[n // 2]
            p95 = sorted_ft[min(int(n * 0.95), n - 1)]
            p99 = sorted_ft[min(int(n * 0.99), n - 1)]
            worst_count = max(1, n // 100)
            worst_slice = sorted_ft[-worst_count:]
            avg_worst = sum(worst_slice) / len(worst_slice)
            low_1pct_fps = 1000.0 / avg_worst if avg_worst > 0.01 else 0.0
            if n >= 2:
                mean_ft = sum(ft) / n
                variance = sum((x - mean_ft) ** 2 for x in ft) / (n - 1)
                jitter = math.sqrt(variance)

        # --- Build frame time bar graph ---
        graph_surf = pygame.Surface((graph_w, graph_h), pygame.SRCALPHA)
        graph_surf.fill((20, 20, 30, 200))

        display_ft = ft[-150:] if len(ft) > 150 else ft
        max_ft = max(50.0, max(display_ft) if display_ft else 50.0)
        max_ft = math.ceil(max_ft / 10.0) * 10.0

        bar_w = 2
        for i, ms in enumerate(display_ft):
            bar_h = max(1, int((ms / max_ft) * (graph_h - 2)))
            x = i * bar_w
            y = graph_h - bar_h
            if ms < 16.67:
                bar_color = (80, 200, 80)
            elif ms < 33.33:
                bar_color = (220, 200, 60)
            else:
                bar_color = (220, 70, 70)
            pygame.draw.rect(graph_surf, bar_color, (x, y, bar_w - 1, bar_h))

        # Reference lines
        for ref_ms, ref_label in [(16.67, "60"), (33.33, "30")]:
            ref_y = graph_h - int((ref_ms / max_ft) * (graph_h - 2))
            if 4 < ref_y < graph_h - 4:
                pygame.draw.line(graph_surf, (120, 120, 140), (0, ref_y), (graph_w, ref_y), 1)
                lbl = small_font.render(ref_label, True, (140, 140, 160))
                graph_surf.blit(lbl, (graph_w - lbl.get_width() - 2, ref_y - lbl.get_height()))

        # --- Assemble text lines ---
        ursina_ema = getattr(e, "_ursina_window_fps_ema", None)
        is_ursina = getattr(e, "_ursina_viewer", False)

        text_lines = []
        if is_ursina:
            fps_str = f"FPS (HUD): {fps:0.1f}"
            if ursina_ema is not None:
                fps_str += f"  3D: ~{float(ursina_ema):0.1f}"
            text_lines.append(fps_str)
        else:
            text_lines.append(f"FPS: {fps:0.1f}")

        if n >= 10:
            text_lines.append(
                f"P50: {p50:0.1f}ms  P95: {p95:0.1f}ms  P99: {p99:0.1f}ms"
            )
            text_lines.append(
                f"1% Low: {low_1pct_fps:0.0f} FPS   Jitter: {jitter:0.1f}ms"
            )
        text_lines.append(
            f"Entities: H={heroes_alive} P={peasants_alive} G={guards_alive} E={enemies_alive} (cap={MAX_ALIVE_ENEMIES})"
        )
        text_lines.append(
            f"Loop (ema): evt={e._perf_events_ms:0.1f} upd={e._perf_update_ms:0.1f} rnd={e._perf_render_ms:0.1f}ms"
        )
        text_lines.append(
            f"PF/s: {e._perf_pf_calls} calls  {e._perf_pf_failures} fails  {e._perf_pf_total_ms:0.1f}ms"
        )

        # --- Render text ---
        rendered = []
        text_w = 0
        text_h = 0
        for line in text_lines:
            s = font.render(line, True, (255, 255, 255))
            rendered.append(s)
            text_w = max(text_w, s.get_width())
            text_h += s.get_height()

        # --- Compose panel ---
        title_surf = small_font.render("Frame Time (ms) — last 2.5s", True, (180, 180, 200))
        panel_w = max(graph_w, text_w) + pad * 2
        panel_h = pad + title_surf.get_height() + 2 + graph_h + 4 + text_h + pad
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 140))

        yy = pad
        panel.blit(title_surf, (pad, yy))
        yy += title_surf.get_height() + 2
        panel.blit(graph_surf, (pad, yy))
        yy += graph_h + 4
        for s in rendered:
            panel.blit(s, (pad, yy))
            yy += s.get_height()

        # Close button
        x_surf = font.render("X", True, (255, 255, 255))
        size = 18
        close_local = pygame.Rect(panel.get_width() - size - 4, 4, size, size)
        pygame.draw.rect(panel, (45, 45, 55), close_local)
        pygame.draw.rect(panel, (120, 120, 150), close_local, 1)
        panel.blit(x_surf, (close_local.centerx - x_surf.get_width() // 2, close_local.centery - x_surf.get_height() // 2))

        return panel

    def render_pygame(self) -> float:
        e = self._e
        t2 = time.perf_counter()
        self.render()
        t3 = time.perf_counter()
        return (t3 - t2) * 1000.0
