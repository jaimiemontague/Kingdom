from __future__ import annotations

from typing import Any, Mapping

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_WHITE
from game.graphics.font_cache import get_font, render_text_cached
from game.graphics.hero_sprites import HeroSpriteLibrary


def _state_get(entity_state: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(entity_state, Mapping):
        return entity_state.get(key, default)
    return getattr(entity_state, key, default)


class HeroRenderer:
    """
    Render-only hero presentation with renderer-owned animation state.

    This mirrors the current Hero.render() output so Agent 03 can swap the call site
    to renderers without changing behavior.
    """

    def __init__(self, hero_id: str, hero_class: str, *, size_px: int = 32):
        self.hero_id = str(hero_id)
        self.hero_class = str(hero_class or "warrior")
        self.size_px = int(size_px)

        self._anim = HeroSpriteLibrary.create_player(self.hero_class, size=self.size_px)
        self._anim_base = "idle"
        self._anim_lock_one_shot: str | None = None
        self._facing = 1
        self._last_pos: tuple[float, float] | None = None

        # Avoid repeated scale allocations for inside-building bubbles.
        self._bubble_cache: dict[int, pygame.Surface] = {}

    def set_one_shot(self, name: str) -> None:
        self._anim_lock_one_shot = str(name)
        self._anim.play(self._anim_lock_one_shot, restart=True)

    def _sync_class(self, hero_class: str) -> None:
        hc = str(hero_class or "warrior")
        if hc == self.hero_class:
            return
        self.hero_class = hc
        self._anim = HeroSpriteLibrary.create_player(self.hero_class, size=self.size_px)
        self._anim_base = "idle"
        self._anim_lock_one_shot = None
        self._bubble_cache.clear()

    def update_animation(self, entity_state: Mapping[str, Any] | object, dt: float) -> None:
        self._sync_class(str(_state_get(entity_state, "hero_class", self.hero_class)))

        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        if self._last_pos is not None:
            dx = x - self._last_pos[0]
            if abs(dx) > 0.01:
                self._facing = 1 if dx >= 0 else -1
        self._last_pos = (x, y)

        # Primary trigger path after WK9 sim/render split.
        entity_one_shot = _state_get(entity_state, "_render_anim_trigger", None)
        if entity_one_shot:
            setattr(entity_state, "_render_anim_trigger", None)

        # Transitional compatibility while entities still carry legacy fields.
        if not entity_one_shot:
            entity_one_shot = _state_get(entity_state, "_anim_lock_one_shot", None)
        if entity_one_shot:
            one_shot = str(entity_one_shot)
            if self._anim_lock_one_shot != one_shot:
                self._anim_lock_one_shot = one_shot
                self._anim.play(one_shot, restart=True)

        state = _state_get(entity_state, "state", None)
        state_name = str(getattr(state, "name", state))
        is_inside_building = bool(_state_get(entity_state, "is_inside_building", False))
        if is_inside_building:
            self._anim_base = "inside"
        elif state_name in ("MOVING", "RETREATING"):
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

    def _bubble_surface(self, frame: pygame.Surface) -> pygame.Surface:
        key = id(frame)
        cached = self._bubble_cache.get(key)
        if cached is not None:
            return cached
        scaled = pygame.transform.scale(frame, (16, 16))
        self._bubble_cache[key] = scaled
        return scaled

    def render(
        self,
        surface: pygame.Surface,
        entity_state: Mapping[str, Any] | object,
        camera_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        if not bool(_state_get(entity_state, "is_alive", True)):
            return

        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        screen_x = x - cam_x
        screen_y = y - cam_y

        inside_building = bool(_state_get(entity_state, "is_inside_building", False))
        building_ref = _state_get(entity_state, "inside_building", None)
        if inside_building and building_ref is not None:
            bx = float(getattr(building_ref, "center_x", x)) - cam_x
            by = float(getattr(building_ref, "center_y", y)) - cam_y
            bubble = self._anim.frame()
            bubble_small = self._bubble_surface(bubble)
            surface.blit(bubble_small, (int(bx - 8), int(by - 28)))
            return

        frame = self._anim.frame()
        if int(_state_get(entity_state, "facing", self._facing)) < 0:
            frame = pygame.transform.flip(frame, True, False)
        fw, fh = frame.get_width(), frame.get_height()
        surface.blit(frame, (int(screen_x - fw // 2), int(screen_y - fh // 2)))

        size = int(_state_get(entity_state, "size", 20))
        hp = float(_state_get(entity_state, "hp", 0.0))
        max_hp = max(1.0, float(_state_get(entity_state, "max_hp", 1.0)))
        health_percent = max(0.0, min(1.0, hp / max_hp))

        bar_width = size + 10
        bar_height = 4
        bar_x = screen_x - bar_width // 2
        bar_y = screen_y - size // 2 - 8
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height))
        health_color = COLOR_GREEN if health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(surface, health_color, (bar_x, bar_y, bar_width * health_percent, bar_height))

        font = get_font(16)
        name = str(_state_get(entity_state, "name", "Hero"))
        name_text = render_text_cached(16, name, COLOR_WHITE)
        name_rect = name_text.get_rect(center=(screen_x, screen_y + size // 2 + 10))
        surface.blit(name_text, name_rect)

        gold = int(_state_get(entity_state, "gold", 0))
        taxed_gold = int(_state_get(entity_state, "taxed_gold", 0))
        if gold + taxed_gold > 0:
            gold_text = font.render(f"${gold}(+{taxed_gold})", True, (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(screen_x, screen_y + size // 2 + 22))
            surface.blit(gold_text, gold_rect)

        state = _state_get(entity_state, "state", None)
        state_name = str(getattr(state, "name", state))
        if state_name == "RESTING":
            rest_text = render_text_cached(16, "Zzz", (150, 200, 255))
            rest_rect = rest_text.get_rect(center=(screen_x + 15, screen_y - size // 2 - 15))
            surface.blit(rest_text, rest_rect)
