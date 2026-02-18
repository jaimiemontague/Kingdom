from __future__ import annotations

from typing import Any, Mapping

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_WHITE
from game.graphics.enemy_sprites import EnemySpriteLibrary


def _state_get(entity_state: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(entity_state, Mapping):
        return entity_state.get(key, default)
    return getattr(entity_state, key, default)


class EnemyRenderer:
    """Render-only enemy presentation with renderer-owned animation state."""

    def __init__(self, enemy_id: str, enemy_type: str, *, size_px: int = 32):
        self.enemy_id = str(enemy_id)
        self.enemy_type = str(enemy_type or "goblin")
        self.size_px = int(size_px)

        self._anim = EnemySpriteLibrary.create_player(self.enemy_type, size=self.size_px)
        self._anim_base = "idle"
        self._anim_lock_one_shot: str | None = None
        self._facing = 1
        self._last_pos: tuple[float, float] | None = None

    def set_one_shot(self, name: str) -> None:
        self._anim_lock_one_shot = str(name)
        self._anim.play(self._anim_lock_one_shot, restart=True)

    def _sync_type(self, enemy_type: str) -> None:
        et = str(enemy_type or "goblin")
        if et == self.enemy_type:
            return
        self.enemy_type = et
        self._anim = EnemySpriteLibrary.create_player(self.enemy_type, size=self.size_px)
        self._anim_base = "idle"
        self._anim_lock_one_shot = None

    def update_animation(self, entity_state: Mapping[str, Any] | object, dt: float) -> None:
        self._sync_type(str(_state_get(entity_state, "enemy_type", self.enemy_type)))

        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        if self._last_pos is not None:
            dx = x - self._last_pos[0]
            if abs(dx) > 0.01:
                self._facing = 1 if dx >= 0 else -1
        self._last_pos = (x, y)

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
        self._anim_base = "walk" if state_name == "MOVING" else "idle"

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
        if not bool(_state_get(entity_state, "is_alive", True)):
            return

        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        screen_x = x - cam_x
        screen_y = y - cam_y

        frame = self._anim.frame()
        if int(_state_get(entity_state, "facing", self._facing)) < 0:
            frame = pygame.transform.flip(frame, True, False)
        fw, fh = frame.get_width(), frame.get_height()
        surface.blit(frame, (int(screen_x - fw // 2), int(screen_y - fh // 2)))

        size = int(_state_get(entity_state, "size", 18))
        hp = float(_state_get(entity_state, "hp", 0.0))
        max_hp = max(1.0, float(_state_get(entity_state, "max_hp", 1.0)))
        health_percent = max(0.0, min(1.0, hp / max_hp))

        bar_width = size + 6
        bar_height = 3
        bar_x = screen_x - bar_width // 2
        bar_y = screen_y - size // 2 - 6
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height))
        health_color = COLOR_GREEN if health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(surface, health_color, (bar_x, bar_y, bar_width * health_percent, bar_height))

        if self._anim is None:
            points = [
                (screen_x, screen_y - size // 2),
                (screen_x - size // 2, screen_y + size // 2),
                (screen_x + size // 2, screen_y + size // 2),
            ]
            pygame.draw.polygon(surface, (200, 0, 0), points)
            pygame.draw.polygon(surface, COLOR_WHITE, points, 1)
