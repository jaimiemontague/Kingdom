"""WK126 T8 (Agent 09) — pygame Quest-Giver NPC blit + yellow "!" offer marker.

Stationary herald NPC beside its Herald's Post (``game/entities/quest_giver.py``,
modeled on the tax collector). Render contract mirrors the other renderers in
this package: ``render(surface, entity_state, camera_offset)`` where
``entity_state`` is a frozen DTO / plain-data state (or the live entity via the
registry's ``render_state`` indirection) carrying ``x``, ``y``, ``giver_id``,
``is_open`` (+ optional ``size``/``color``/``is_alive``).

The "!" marker is modeled on the hero "Zzz" block (``hero_renderer.py:197-200``):
``render_text_cached`` returns a cached Surface keyed on (size, text, color), so
the marker costs one dict lookup + one blit per frame — no per-frame font
re-raster (FPS guardrails). The body shape is the same cheap ``pygame.draw``
procedural fallback the tax collector uses (no PNG asset for the herald yet).
"""
from __future__ import annotations

from typing import Any, Mapping

import pygame

from config import COLOR_WHITE
from game.graphics.font_cache import render_text_cached

# Herald gold — matches QuestGiver.color on the sim entity.
QUEST_GIVER_COLOR = (240, 200, 60)
# Marker styling: yellow "!", drawn above the body (Zzz-block precedent).
MARKER_TEXT = "!"
MARKER_COLOR = (255, 215, 0)
MARKER_FONT_SIZE = 20


def _state_get(entity_state: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(entity_state, Mapping):
        return entity_state.get(key, default)
    return getattr(entity_state, key, default)


class QuestGiverRenderer:
    """Render-only quest-giver presentation (stateless; shared instance is fine).

    The giver is stationary and unanimated for MVP, so unlike heroes/workers
    there is no per-entity animation state — the registry keeps ONE shared
    instance (same pattern as ``GuardRenderer``).
    """

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
        size = int(_state_get(entity_state, "size", 14))

        # Body: herald-gold diamond + white outline + "H" glyph (procedural
        # fallback, exactly the tax-collector "$"-diamond pattern).
        points = [
            (screen_x, screen_y - size // 2),
            (screen_x + size // 2, screen_y),
            (screen_x, screen_y + size // 2),
            (screen_x - size // 2, screen_y),
        ]
        body_color = tuple(_state_get(entity_state, "color", QUEST_GIVER_COLOR))
        pygame.draw.polygon(surface, body_color, points)
        pygame.draw.polygon(surface, COLOR_WHITE, points, 1)
        symbol = render_text_cached(14, "H", COLOR_WHITE)
        symbol_rect = symbol.get_rect(center=(int(screen_x), int(screen_y)))
        surface.blit(symbol, symbol_rect)

        # Yellow "!" above the sprite while the giver has an open offer — cached
        # Surface via render_text_cached (the hero "Zzz" precedent; no per-frame
        # re-raster, FPS-safe).
        if bool(_state_get(entity_state, "is_open", False)):
            marker = render_text_cached(MARKER_FONT_SIZE, MARKER_TEXT, MARKER_COLOR)
            marker_rect = marker.get_rect(center=(int(screen_x), int(screen_y - size // 2 - 10)))
            surface.blit(marker, marker_rect)
