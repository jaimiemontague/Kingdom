"""Building renderer for all building/lair/neutral entity types."""

from __future__ import annotations

import pygame

from config import COLOR_BLACK, COLOR_WHITE
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.font_cache import render_text_shadowed_cached
from game.graphics.render_context import get_render_zoom


def _normalize_building_type(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "building").lower()


class BuildingRenderer:
    """Render-only building presentation for all building families."""

    _LABELS: dict[str, tuple[str, int]] = {
        "castle": ("CASTLE", 20),
        "warrior_guild": ("WARRIORS", 16),
        "ranger_guild": ("RANGERS", 16),
        "rogue_guild": ("ROGUES", 16),
        "wizard_guild": ("WIZARDS", 16),
        "marketplace": ("MARKET", 16),
        "blacksmith": ("SMITH", 16),
        "inn": ("INN", 16),
        "trading_post": ("TRADE", 16),
        "temple_agrela": ("AGRELA", 14),
        "temple_dauros": ("DAUROS", 14),
        "temple_fervus": ("FERVUS", 14),
        "temple_krypta": ("KRYPTA", 14),
        "temple_krolm": ("KROLM", 14),
        "temple_helia": ("HELIA", 14),
        "temple_lunord": ("LUNORD", 14),
        "gnome_hovel": ("GNOMES", 14),
        "elven_bungalow": ("ELVES", 14),
        "dwarven_settlement": ("DWARVES", 14),
        "guardhouse": ("GUARDS", 14),
        "ballista_tower": ("BALLISTA", 14),
        "wizard_tower": ("WIZ TOWER", 14),
        "fairgrounds": ("FAIR", 14),
        "library": ("LIBRARY", 14),
        "royal_gardens": ("GARDENS", 14),
    }
    _GUILD_WITH_TAX: set[str] = {"warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild"}

    def _draw_base(
        self,
        surface: pygame.Surface,
        building: object,
        camera_offset: tuple[float, float],
    ) -> tuple[float, float]:
        cam_x, cam_y = float(camera_offset[0]), float(camera_offset[1])
        screen_x = float(getattr(building, "world_x", 0.0)) - cam_x
        screen_y = float(getattr(building, "world_y", 0.0)) - cam_y

        width = int(getattr(building, "width", 0))
        height = int(getattr(building, "height", 0))
        if width <= 0 or height <= 0:
            return screen_x, screen_y

        hp = float(getattr(building, "hp", 0.0))
        max_hp = max(1.0, float(getattr(building, "max_hp", 1.0)))
        is_constructed = bool(getattr(building, "is_constructed", True))
        building_type = _normalize_building_type(getattr(building, "building_type", "building"))

        if not is_constructed:
            sprite_state = "construction"
        elif hp < max_hp:
            sprite_state = "damaged"
        else:
            sprite_state = "built"

        sprite = BuildingSpriteLibrary.get(building_type, sprite_state, size_px=(width, height))
        if sprite is not None:
            surface.blit(sprite, (int(screen_x), int(screen_y)))
        else:
            color = tuple(getattr(building, "color", (128, 128, 128)))
            pygame.draw.rect(surface, color, (screen_x, screen_y, width, height))
            pygame.draw.rect(surface, COLOR_BLACK, (screen_x, screen_y, width, height), 2)

        if hp < max_hp:
            bar_width = width - 4
            bar_height = 4
            health_pct = max(0.0, min(1.0, hp / max_hp))
            pygame.draw.rect(surface, (60, 60, 60), (screen_x + 2, screen_y - 8, bar_width, bar_height))
            pygame.draw.rect(
                surface,
                (50, 205, 50) if health_pct > 0.5 else (220, 20, 60),
                (screen_x + 2, screen_y - 8, bar_width * health_pct, bar_height),
            )
        return screen_x, screen_y

    def _draw_center_label(
        self,
        surface: pygame.Surface,
        text: str,
        size: int,
        screen_x: float,
        screen_y: float,
        width: int,
        height: int,
        *,
        color: tuple[int, int, int] = COLOR_WHITE,
    ) -> None:
        label = render_text_shadowed_cached(size, text, color)
        rect = label.get_rect(center=(screen_x + width // 2, screen_y + height // 2))
        surface.blit(label, rect)

    def render(
        self,
        surface: pygame.Surface,
        building: object,
        camera_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        screen_x, screen_y = self._draw_base(surface, building, camera_offset)
        width = int(getattr(building, "width", 0))
        height = int(getattr(building, "height", 0))
        if width <= 0 or height <= 0:
            return

        building_type = _normalize_building_type(getattr(building, "building_type", "building"))
        zoom = get_render_zoom()

        if bool(getattr(building, "is_lair", False)):
            self._draw_center_label(
                surface,
                building_type.replace("_", " ").upper(),
                16,
                screen_x,
                screen_y,
                width,
                height,
            )
            if zoom >= 1.0:
                stash_gold = int(getattr(building, "stash_gold", 0))
                stash = render_text_shadowed_cached(14, f"${stash_gold}", (255, 215, 0))
                stash_rect = stash.get_rect(center=(screen_x + width // 2, screen_y + height + 8))
                surface.blit(stash, stash_rect)
            return

        if bool(getattr(building, "is_neutral", False)):
            self._draw_center_label(
                surface,
                building_type.replace("_", " ").upper(),
                14,
                screen_x,
                screen_y,
                width,
                height,
            )
            stored_tax = int(getattr(building, "stored_tax_gold", 0))
            if stored_tax > 0 and zoom >= 1.0:
                tax = render_text_shadowed_cached(12, f"Tax: ${stored_tax}", (255, 215, 0))
                tax_rect = tax.get_rect(center=(screen_x + width // 2, screen_y + height + 8))
                surface.blit(tax, tax_rect)
            return

        if building_type == "palace":
            level = int(getattr(building, "level", 1))
            self._draw_center_label(surface, f"PALACE L{level}", 20, screen_x, screen_y, width, height)
        else:
            label_meta = self._LABELS.get(building_type)
            if label_meta is not None:
                self._draw_center_label(surface, label_meta[0], label_meta[1], screen_x, screen_y, width, height)

        if building_type in self._GUILD_WITH_TAX:
            stored_tax = int(getattr(building, "stored_tax_gold", 0))
            if stored_tax > 0 and zoom >= 1.0:
                gold = render_text_shadowed_cached(14, f"Tax: ${stored_tax}", (255, 215, 0))
                gold_rect = gold.get_rect(center=(screen_x + width // 2, screen_y + height + 8))
                surface.blit(gold, gold_rect)

        if building_type == "ballista_tower" and getattr(building, "target", None):
            radius = int(getattr(building, "attack_range", 0))
            pygame.draw.circle(
                surface,
                (255, 0, 0, 50),
                (int(screen_x + width // 2), int(screen_y + height // 2)),
                radius,
                1,
            )
