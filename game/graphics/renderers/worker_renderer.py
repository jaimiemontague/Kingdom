from __future__ import annotations

from typing import Any, Mapping

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_WHITE, UNIT_SPRITE_PIXELS
from game.graphics.font_cache import get_font, render_text_cached
from game.graphics.worker_sprites import WorkerSpriteLibrary


def _state_get(entity_state: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(entity_state, Mapping):
        return entity_state.get(key, default)
    return getattr(entity_state, key, default)


class WorkerRenderer:
    """
    Render-only worker presentation.

    Handles:
    - peasant
    - tax_collector
    - guard
    """

    def __init__(self, worker_id: str, worker_type: str, *, size_px: int | None = None):
        self.worker_id = str(worker_id)
        self.worker_type = str(worker_type or "peasant")
        self.size_px = int(size_px if size_px is not None else UNIT_SPRITE_PIXELS)

        self._anim: Any | None = None
        self._anim_base = "idle"
        self._anim_lock_one_shot: str | None = None
        self._init_animation_player()

    def _init_animation_player(self) -> None:
        if self.worker_type in ("peasant", "peasant_builder", "tax_collector", "guard"):
            self._anim = WorkerSpriteLibrary.create_player(self.worker_type, size=self.size_px)
            self._anim_base = "idle"
            self._anim_lock_one_shot = None
        else:
            self._anim = None

    def _sync_worker_type(self, worker_type: str) -> None:
        wt = str(worker_type or "peasant")
        if wt == self.worker_type:
            return
        self.worker_type = wt
        self._init_animation_player()

    def update_animation(self, entity_state: Mapping[str, Any] | object, dt: float) -> None:
        self._sync_worker_type(str(_state_get(entity_state, "render_worker_type", self.worker_type)))

        if self._anim is None:
            return

        entity_one_shot = _state_get(entity_state, "_render_anim_trigger", None)
        if entity_one_shot:
            setattr(entity_state, "_render_anim_trigger", None)
        if not entity_one_shot:
            entity_one_shot = _state_get(entity_state, "_anim_lock_one_shot", None)

        if entity_one_shot:
            one_shot = str(entity_one_shot)
            if self._anim_lock_one_shot != one_shot:
                self._anim_lock_one_shot = one_shot
                self._anim.play(one_shot, restart=True)

        state = _state_get(entity_state, "state", None)
        state_name = str(getattr(state, "name", state))

        if self.worker_type == "tax_collector":
            if state_name == "COLLECTING":
                self._anim_base = "collect"
            elif state_name == "RETURNING":
                self._anim_base = "return"
            elif state_name == "MOVING_TO_GUILD":
                self._anim_base = "walk"
            elif state_name == "RESTING_AT_CASTLE":
                self._anim_base = "rest"
            else:
                self._anim_base = "idle"
        elif self.worker_type == "guard":
            if state_name == "DEAD":
                self._anim_base = "dead"
            elif state_name == "ATTACKING":
                self._anim_base = "attack"
            elif state_name == "MOVING":
                self._anim_base = "walk"
            else:
                self._anim_base = "idle"
        else:
            if state_name == "DEAD":
                self._anim_base = "dead"
            elif state_name == "WORKING":
                self._anim_base = "work"
            elif state_name == "MOVING":
                self._anim_base = "walk"
            else:
                self._anim_base = "idle"

        if self._anim_lock_one_shot:
            if self._anim.current != self._anim_lock_one_shot:
                self._anim.play(self._anim_lock_one_shot, restart=True)
            self._anim.update(float(dt))
            if self._anim.finished:
                self._anim_lock_one_shot = None
                self._anim.play(self._anim_base, restart=True)
            return

        self._anim.play(self._anim_base, restart=False)
        self._anim.update(float(dt))

    def render(
        self,
        surface: pygame.Surface,
        entity_state: Mapping[str, Any] | object,
        camera_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        if self.worker_type == "guard":
            self._render_guard(surface, entity_state, camera_offset)
            return
        if self.worker_type == "tax_collector":
            self._render_tax_collector(surface, entity_state, camera_offset)
            return
        self._render_peasant(surface, entity_state, camera_offset)

    def _render_peasant(
        self,
        surface: pygame.Surface,
        entity_state: Mapping[str, Any] | object,
        camera_offset: tuple[float, float],
    ) -> None:
        if not bool(_state_get(entity_state, "is_alive", True)):
            return
        if bool(_state_get(entity_state, "is_inside_castle", False)):
            return

        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        sx = x - cam_x
        sy = y - cam_y
        size = int(_state_get(entity_state, "size", 14))

        if self._anim is not None:
            frame = self._anim.frame()
            fw, fh = frame.get_width(), frame.get_height()
            surface.blit(frame, (int(sx - fw // 2), int(sy - fh // 2)))
        else:
            color = tuple(_state_get(entity_state, "color", (200, 180, 120)))
            pygame.draw.circle(surface, color, (int(sx), int(sy)), size // 2)
            pygame.draw.circle(surface, COLOR_WHITE, (int(sx), int(sy)), size // 2, 1)
            symbol = render_text_cached(14, "P", COLOR_WHITE)
            symbol_rect = symbol.get_rect(center=(int(sx), int(sy)))
            surface.blit(symbol, symbol_rect)

        hp = float(_state_get(entity_state, "hp", 0.0))
        max_hp = max(1.0, float(_state_get(entity_state, "max_hp", 1.0)))
        health_percent = max(0.0, min(1.0, hp / max_hp))
        bar_w = size + 8
        bar_h = 3
        bx = sx - bar_w // 2
        by = sy - size // 2 - 7
        pygame.draw.rect(surface, (60, 60, 60), (bx, by, bar_w, bar_h))
        hc = COLOR_GREEN if health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hc, (bx, by, bar_w * health_percent, bar_h))

    def _render_tax_collector(
        self,
        surface: pygame.Surface,
        entity_state: Mapping[str, Any] | object,
        camera_offset: tuple[float, float],
    ) -> None:
        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        screen_x = x - cam_x
        screen_y = y - cam_y
        size = int(_state_get(entity_state, "size", 14))

        if self._anim is not None:
            frame = self._anim.frame()
            fw, fh = frame.get_width(), frame.get_height()
            surface.blit(frame, (int(screen_x - fw // 2), int(screen_y - fh // 2)))
        else:
            points = [
                (screen_x, screen_y - size // 2),
                (screen_x + size // 2, screen_y),
                (screen_x, screen_y + size // 2),
                (screen_x - size // 2, screen_y),
            ]
            color = tuple(_state_get(entity_state, "color", (218, 165, 32)))
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, COLOR_WHITE, points, 1)
            symbol = render_text_cached(16, "$", COLOR_WHITE)
            symbol_rect = symbol.get_rect(center=(int(screen_x), int(screen_y)))
            surface.blit(symbol, symbol_rect)

        carried_gold = int(_state_get(entity_state, "carried_gold", 0))
        if carried_gold > 0:
            font = get_font(14)
            gold_text = font.render(f"${carried_gold}", True, (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(screen_x, screen_y - size))
            surface.blit(gold_text, gold_rect)

        state = _state_get(entity_state, "state", None)
        state_name = str(getattr(state, "name", state))
        if state_name == "COLLECTING":
            state_text = render_text_cached(12, "Collecting...", COLOR_WHITE)
            text_rect = state_text.get_rect(center=(screen_x, screen_y + size + 5))
            surface.blit(state_text, text_rect)

    def _render_guard(
        self,
        surface: pygame.Surface,
        entity_state: Mapping[str, Any] | object,
        camera_offset: tuple[float, float],
    ) -> None:
        if not bool(_state_get(entity_state, "is_alive", True)):
            return

        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        sx = x - cam_x
        sy = y - cam_y
        size = int(_state_get(entity_state, "size", 14))

        if self._anim is not None:
            frame = self._anim.frame()
            fw, fh = frame.get_width(), frame.get_height()
            surface.blit(frame, (int(sx - fw // 2), int(sy - fh // 2)))
        else:
            color = tuple(_state_get(entity_state, "color", (120, 120, 160)))
            pygame.draw.circle(surface, color, (int(sx), int(sy)), size // 2)
            pygame.draw.circle(surface, COLOR_WHITE, (int(sx), int(sy)), size // 2, 1)
            symbol = render_text_cached(14, "G", COLOR_WHITE)
            symbol_rect = symbol.get_rect(center=(int(sx), int(sy)))
            surface.blit(symbol, symbol_rect)

        hp = float(_state_get(entity_state, "hp", 0.0))
        max_hp = max(1.0, float(_state_get(entity_state, "max_hp", 1.0)))
        health_percent = max(0.0, min(1.0, hp / max_hp))
        bar_w = (self.size_px if self._anim else size) + 8
        bar_h = 3
        bx = sx - bar_w // 2
        by = sy - (self.size_px if self._anim else size) // 2 - 7
        pygame.draw.rect(surface, (60, 60, 60), (bx, by, bar_w, bar_h))
        hc = COLOR_GREEN if health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hc, (bx, by, bar_w * health_percent, bar_h))


class PeasantRenderer(WorkerRenderer):
    """Compatibility wrapper used by RendererRegistry."""

    def __init__(self, peasant_id: int | str, *, size_px: int | None = None):
        super().__init__(worker_id=str(peasant_id), worker_type="peasant", size_px=size_px)


class TaxCollectorRenderer(WorkerRenderer):
    """Compatibility wrapper used by RendererRegistry."""

    def __init__(self, collector_id: int | str, *, size_px: int | None = None):
        super().__init__(worker_id=str(collector_id), worker_type="tax_collector", size_px=size_px)


class GuardRenderer(WorkerRenderer):
    """Compatibility wrapper used by RendererRegistry."""

    def __init__(self, *, size_px: int | None = None):
        super().__init__(worker_id="guard", worker_type="guard", size_px=size_px)
