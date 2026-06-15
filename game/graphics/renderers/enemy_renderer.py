from __future__ import annotations

from typing import Any, Mapping

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_WHITE
from game.graphics.font_cache import render_text_shadowed_cached
from game.graphics.enemy_sprites import EnemySpriteLibrary


def _state_get(entity_state: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(entity_state, Mapping):
        return entity_state.get(key, default)
    return getattr(entity_state, key, default)


_BOSS_CROWN_EDGE = (28, 24, 16)
_BOSS_PHASE_COLORS: dict[str, tuple[int, int, int]] = {
    "war_banner": (232, 188, 60),
    "rally": (232, 92, 78),
    "sleeping hoard": (236, 200, 76),
    "air and fire": (255, 128, 52),
    "wounded fury": (236, 92, 78),
}
_ELITE_TITLE_COLORS: dict[str, tuple[int, int, int]] = {
    "banner_bearer": (248, 220, 96),
    "ironhide": (185, 194, 205),
    "frenzied": (244, 114, 114),
}


def _normalize_phase_title(phase_title: str) -> str:
    return " ".join(str(phase_title or "").strip().lower().split())


def _boss_badge_color(phase_title: str) -> tuple[int, int, int]:
    return _BOSS_PHASE_COLORS.get(_normalize_phase_title(phase_title), (232, 188, 60))


def _elite_title_color(affixes: tuple[str, ...]) -> tuple[int, int, int]:
    affix_ids = {str(affix_id).strip().lower() for affix_id in affixes if str(affix_id).strip()}
    for key in ("banner_bearer", "ironhide", "frenzied"):
        if key in affix_ids:
            return _ELITE_TITLE_COLORS[key]
    return (220, 220, 220)


def _draw_crown_badge(
    surface: pygame.Surface,
    center_x: float,
    badge_top_y: float,
    *,
    fill_color: tuple[int, int, int],
) -> None:
    """Draw a small, readable boss crown without touching the HP bar."""
    left = int(center_x) - 9
    right = int(center_x) + 9
    top = int(badge_top_y)
    base = top + 11
    crown = [
        (left, base),
        (left + 2, top + 3),
        (left + 5, top + 6),
        (int(center_x) - 1, top),
        (int(center_x) + 1, top + 6),
        (right - 5, top + 3),
        (right - 2, base),
        (right, base + 3),
        (left, base + 3),
    ]
    pygame.draw.polygon(surface, fill_color, crown)
    pygame.draw.polygon(surface, _BOSS_CROWN_EDGE, crown, 1)
    pygame.draw.line(surface, _BOSS_CROWN_EDGE, (left + 2, base + 1), (right - 2, base + 1), 1)
    pygame.draw.circle(surface, _BOSS_CROWN_EDGE, (left + 2, top + 3), 1)
    pygame.draw.circle(surface, _BOSS_CROWN_EDGE, (int(center_x), top), 1)
    pygame.draw.circle(surface, _BOSS_CROWN_EDGE, (right - 2, top + 3), 1)


def _draw_elite_badge(
    surface: pygame.Surface,
    center_x: float,
    badge_y: float,
    *,
    title: str,
    title_color: tuple[int, int, int],
) -> None:
    """Draw a restrained elite marker and title below the sprite."""
    if not title:
        return
    badge = render_text_shadowed_cached(12, title, title_color)
    badge_rect = badge.get_rect(center=(int(center_x), int(badge_y)))
    surface.blit(badge, badge_rect)
    # Tiny color chip keeps the marker readable at normal zoom without turning
    # the world into a label forest.
    chip_x = badge_rect.left - 8
    chip_y = badge_rect.centery
    chip = [
        (chip_x, chip_y),
        (chip_x + 4, chip_y - 4),
        (chip_x + 8, chip_y),
        (chip_x + 4, chip_y + 4),
    ]
    pygame.draw.polygon(surface, title_color, chip)
    pygame.draw.polygon(surface, _BOSS_CROWN_EDGE, chip, 1)


def _draw_dragon_phase_aura(
    surface: pygame.Surface,
    center_x: float,
    center_y: float,
    *,
    phase_title: str,
    frame_w: int,
    frame_h: int,
) -> None:
    phase_key = _normalize_phase_title(phase_title)
    ring_color = _boss_badge_color(phase_key)
    if "hoard" in phase_key:
        accent = (112, 84, 26)
        phase_label = "HOARD"
    elif "fire" in phase_key:
        accent = (108, 34, 16)
        phase_label = "FIRE"
    else:
        accent = (92, 72, 30)
        phase_label = str(phase_title or "BOSS").strip().upper() or "BOSS"

    aura_w = max(int(frame_w * 1.5), frame_w + 20)
    aura_h = max(int(frame_h * 1.45), frame_h + 18)
    overlay = pygame.Surface((aura_w, aura_h), pygame.SRCALPHA)
    outer = overlay.get_rect().inflate(-4, -4)
    inner = outer.inflate(-12, -12)
    pygame.draw.ellipse(overlay, (*ring_color, 60), outer, 4)
    pygame.draw.ellipse(overlay, (*accent, 140), inner, 2)

    if "hoard" in phase_key:
        sparkle_points = [
            (outer.centerx, outer.top + 6),
            (outer.right - 9, outer.centery),
            (outer.centerx, outer.bottom - 7),
            (outer.left + 8, outer.centery),
        ]
        for px, py in sparkle_points:
            diamond = [
                (px, py - 3),
                (px + 3, py),
                (px, py + 3),
                (px - 3, py),
            ]
            pygame.draw.polygon(overlay, ring_color, diamond)
            pygame.draw.polygon(overlay, _BOSS_CROWN_EDGE, diamond, 1)
    elif "fire" in phase_key:
        flame_tips = [
            (outer.centerx, outer.top + 5),
            (outer.right - 10, outer.centery - 2),
            (outer.right - 8, outer.centery + 7),
        ]
        for px, py in flame_tips:
            flame = [
                (px - 3, py + 2),
                (px, py - 6),
                (px + 4, py + 1),
                (px + 1, py + 5),
            ]
            pygame.draw.polygon(overlay, ring_color, flame)
            pygame.draw.polygon(overlay, accent, flame, 1)

    phase_surf = render_text_shadowed_cached(11, phase_label, ring_color)
    phase_rect = phase_surf.get_rect(center=(outer.centerx, outer.bottom - 4))
    overlay.blit(phase_surf, phase_rect)

    surface.blit(overlay, (int(center_x - aura_w / 2), int(center_y - aura_h / 2)))


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
        # WK66 Move 1a: renderer-owned last-seen one-shot sequence (see HeroRenderer).
        self._last_trigger_seq: int = -1

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

        # WK66 Move 1a: consume one-shots via the sim's monotonic anim_trigger_seq
        # (no _render_anim_trigger write-back). See HeroRenderer for the rationale.
        trigger_seq = int(
            _state_get(entity_state, "anim_trigger_seq",
                       _state_get(entity_state, "_anim_trigger_seq", 0)) or 0
        )
        entity_one_shot = None
        if trigger_seq != self._last_trigger_seq:
            self._last_trigger_seq = trigger_seq
            entity_one_shot = _state_get(
                entity_state, "anim_trigger",
                _state_get(entity_state, "_render_anim_trigger", None),
            )
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
        *,
        boss_snapshot: object | None = None,
        elite_snapshot: object | None = None,
    ) -> None:
        if not bool(_state_get(entity_state, "is_alive", True)):
            return

        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        x = float(_state_get(entity_state, "x", 0.0))
        y = float(_state_get(entity_state, "y", 0.0))
        screen_x = x - cam_x
        screen_y = y - cam_y
        size = int(_state_get(entity_state, "size", 18))
        hp = float(_state_get(entity_state, "hp", 0.0))
        max_hp = max(1.0, float(_state_get(entity_state, "max_hp", 1.0)))
        health_percent = max(0.0, min(1.0, hp / max_hp))
        enemy_id = str(_state_get(entity_state, "entity_id", "") or self.enemy_id)

        boss_status = "active"
        boss_type = ""
        phase_title = ""
        if boss_snapshot is not None and str(getattr(boss_snapshot, "boss_id", "")) == enemy_id:
            boss_status = str(getattr(boss_snapshot, "status", "active") or "active")
            phase_title = str(getattr(boss_snapshot, "current_phase_title", "") or "")
            boss_type = str(getattr(boss_snapshot, "boss_type", "") or "").strip().lower()

        frame = self._anim.frame()
        display_scale = 1.0
        if boss_type == "dragon" or self.enemy_type == "dragon":
            display_scale = max(1.15, min(1.35, float(size) / 28.0))
        if display_scale != 1.0:
            fw = max(1, int(round(frame.get_width() * display_scale)))
            fh = max(1, int(round(frame.get_height() * display_scale)))
            frame = pygame.transform.scale(frame, (fw, fh))
        if int(_state_get(entity_state, "facing", self._facing)) < 0:
            frame = pygame.transform.flip(frame, True, False)
        fw, fh = frame.get_width(), frame.get_height()

        if boss_status != "defeated" and boss_type == "dragon":
            _draw_dragon_phase_aura(
                surface,
                screen_x,
                screen_y,
                phase_title=phase_title,
                frame_w=fw,
                frame_h=fh,
            )

        surface.blit(frame, (int(screen_x - fw // 2), int(screen_y - fh // 2)))

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

        if boss_snapshot is not None and str(getattr(boss_snapshot, "boss_id", "")) == enemy_id:
            if boss_status != "defeated":
                badge_color = _boss_badge_color(phase_title)
                crown_y = screen_y - size // 2 - 22
                _draw_crown_badge(surface, screen_x, crown_y, fill_color=badge_color)
                boss_name = str(getattr(boss_snapshot, "name", "") or "")
                if boss_name:
                    name_surf = render_text_shadowed_cached(12, boss_name, badge_color)
                    name_rect = name_surf.get_rect(center=(int(screen_x), int(screen_y + size // 2 + 9)))
                    surface.blit(name_surf, name_rect)
                phase_key = _normalize_phase_title(phase_title)
                if boss_type == "dragon":
                    if "hoard" in phase_key:
                        phase_label = "HOARD"
                    elif "fire" in phase_key:
                        phase_label = "FIRE"
                    else:
                        phase_label = phase_title.upper() or "BOSS"
                    phase_surf = render_text_shadowed_cached(11, phase_label, badge_color)
                    phase_rect = phase_surf.get_rect(center=(int(screen_x), int(screen_y + size // 2 + 22)))
                    surface.blit(phase_surf, phase_rect)

        if elite_snapshot is not None and str(getattr(elite_snapshot, "elite_id", "")) == enemy_id:
            elite_status = str(getattr(elite_snapshot, "status", "active") or "active")
            if elite_status != "defeated":
                title = str(getattr(elite_snapshot, "name", "") or "")
                affixes = tuple(getattr(elite_snapshot, "affixes", ()) or ())
                title_color = _elite_title_color(affixes)
                elite_y = screen_y + size // 2 + 10
                _draw_elite_badge(surface, screen_x, elite_y, title=title, title_color=title_color)
