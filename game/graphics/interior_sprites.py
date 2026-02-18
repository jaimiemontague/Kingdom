"""
Interior scene sprites for building micro-views.

Provides procedural backgrounds, furniture layouts, NPC sprites, and hero
slot positions for the interior panel.  Every surface is cached by
(building_type, panel_size) and seeded deterministically via zlib.crc32.
"""
from __future__ import annotations

import random
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pygame


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FurnitureAnchor:
    """Named position + surface for a furniture element inside the interior."""
    name: str
    x: int
    y: int
    surface: pygame.Surface


@dataclass(frozen=True)
class HeroSlot:
    """Position where a hero occupant sprite should be rendered."""
    x: int
    y: int
    label: str = ""


# ---------------------------------------------------------------------------
# Palette helpers (deterministic)
# ---------------------------------------------------------------------------

def _clamp(v: int) -> int:
    return max(0, min(255, v))


def _shade(base: Tuple[int, int, int], offset: int) -> Tuple[int, int, int]:
    return (_clamp(base[0] + offset), _clamp(base[1] + offset), _clamp(base[2] + offset))


def _rgba(rgb: Tuple[int, int, int], a: int = 255) -> Tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], a)


# ---------------------------------------------------------------------------
# Interior definitions
# ---------------------------------------------------------------------------

_WOOD_BROWN = (110, 75, 45)
_STONE_GRAY = (100, 100, 105)
_WARM_AMBER = (180, 130, 60)
_COOL_GREEN = (70, 100, 80)
_BLUE_STEEL = (80, 100, 130)
_DIRT_BROWN = (90, 70, 50)


class InteriorSpriteLibrary:
    """
    Procedural interior backgrounds, NPC sprites, furniture layouts, and hero
    slot positions for the building micro-view panel.

    All surfaces are cached per (building_type, width, height).
    """

    _bg_cache: Dict[Tuple[str, int, int], pygame.Surface] = {}
    _npc_cache: Dict[str, Optional[pygame.Surface]] = {}
    _furniture_cache: Dict[Tuple[str, int, int], List[FurnitureAnchor]] = {}
    _slot_cache: Dict[Tuple[str, int, int], List[HeroSlot]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def get_background(cls, building_type: str, width: int, height: int) -> pygame.Surface:
        key = (building_type, width, height)
        cached = cls._bg_cache.get(key)
        if cached is not None:
            return cached
        surf = cls._gen_background(building_type, width, height)
        cls._bg_cache[key] = surf
        return surf

    @classmethod
    def get_npc_sprite(cls, building_type: str) -> Optional[pygame.Surface]:
        if building_type in cls._npc_cache:
            return cls._npc_cache[building_type]
        surf = cls._gen_npc(building_type)
        cls._npc_cache[building_type] = surf
        return surf

    @classmethod
    def get_furniture_layout(cls, building_type: str, width: int = 380, height: int = 600) -> List[FurnitureAnchor]:
        key = (building_type, width, height)
        cached = cls._furniture_cache.get(key)
        if cached is not None:
            return cached
        anchors = cls._gen_furniture(building_type, width, height)
        cls._furniture_cache[key] = anchors
        return anchors

    @classmethod
    def get_hero_slots(cls, building_type: str, width: int = 380, height: int = 600) -> List[HeroSlot]:
        key = (building_type, width, height)
        cached = cls._slot_cache.get(key)
        if cached is not None:
            return cached
        slots = cls._gen_hero_slots(building_type, width, height)
        cls._slot_cache[key] = slots
        return slots

    # ------------------------------------------------------------------
    # Background generation
    # ------------------------------------------------------------------

    @classmethod
    def _gen_background(cls, building_type: str, w: int, h: int) -> pygame.Surface:
        bt = building_type.lower()
        if bt == "inn":
            return cls._bg_inn(w, h)
        if bt == "marketplace":
            return cls._bg_marketplace(w, h)
        if bt == "warrior_guild":
            return cls._bg_warrior_guild(w, h)
        return cls._bg_fallback(bt, w, h)

    @staticmethod
    def _rng(tag: str, w: int, h: int) -> random.Random:
        seed = zlib.crc32(f"interior|{tag}|{w}|{h}".encode()) & 0xFFFFFFFF
        return random.Random(seed)

    # -- Inn ---------------------------------------------------------------

    @classmethod
    def _bg_inn(cls, w: int, h: int) -> pygame.Surface:
        rnd = cls._rng("inn", w, h)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        wall_h = h // 3
        floor_y = wall_h

        # Stone walls
        surf.fill(_rgba((70, 65, 60)))
        for _ in range(int(w * wall_h * 0.02)):
            px, py = rnd.randrange(w), rnd.randrange(wall_h)
            c = _shade((70, 65, 60), rnd.randint(-8, 8))
            surf.set_at((px, py), _rgba(c))

        # Horizontal mortar lines
        for y in range(0, wall_h, 12):
            pygame.draw.line(surf, _rgba((55, 50, 45)), (0, y), (w, y), 1)

        # Wood-plank floor
        floor_col = _WOOD_BROWN
        pygame.draw.rect(surf, _rgba(floor_col), pygame.Rect(0, floor_y, w, h - floor_y))
        plank_w = 28
        for x in range(0, w, plank_w):
            pygame.draw.line(surf, _rgba(_shade(floor_col, -15)), (x, floor_y), (x, h), 1)
        for y in range(floor_y, h, 8):
            for x in range(0, w, plank_w):
                if rnd.random() < 0.15:
                    knot_x = x + rnd.randint(4, plank_w - 4)
                    pygame.draw.circle(surf, _rgba(_shade(floor_col, -20)), (knot_x, y), 2)

        # Floor noise
        for _ in range(int(w * (h - floor_y) * 0.008)):
            px = rnd.randrange(w)
            py = rnd.randrange(floor_y, h)
            c = _shade(floor_col, rnd.randint(-10, 10))
            surf.set_at((px, py), _rgba(c))

        # Warm ambient glow (fireplace bottom-left)
        glow = pygame.Surface((w, h), pygame.SRCALPHA)
        glow_center = (w // 6, h - h // 6)
        for radius in range(80, 10, -5):
            alpha = max(2, 25 - radius // 4)
            pygame.draw.circle(glow, (255, 180, 80, alpha), glow_center, radius)
        surf.blit(glow, (0, 0))

        # Wall/floor divider line
        pygame.draw.line(surf, _rgba((50, 45, 40)), (0, floor_y), (w, floor_y), 2)

        return surf

    # -- Marketplace -------------------------------------------------------

    @classmethod
    def _bg_marketplace(cls, w: int, h: int) -> pygame.Surface:
        rnd = cls._rng("marketplace", w, h)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        wall_h = h // 3
        floor_y = wall_h

        # Shelving walls (wooden planks)
        wall_col = (85, 75, 65)
        surf.fill(_rgba(wall_col))
        for _ in range(int(w * wall_h * 0.015)):
            px, py = rnd.randrange(w), rnd.randrange(wall_h)
            c = _shade(wall_col, rnd.randint(-6, 6))
            surf.set_at((px, py), _rgba(c))

        # Shelf lines on walls
        for y in range(wall_h // 4, wall_h, wall_h // 4):
            pygame.draw.line(surf, _rgba(_shade(wall_col, -20)), (8, y), (w - 8, y), 2)
            # Small items on shelves
            for x in range(20, w - 20, rnd.randint(22, 36)):
                item_h = rnd.randint(6, 14)
                item_col = rnd.choice([
                    (60, 140, 80),   # green potion
                    (140, 60, 60),   # red potion
                    (80, 80, 160),   # blue potion
                    (180, 160, 80),  # gold item
                ])
                pygame.draw.rect(surf, _rgba(item_col),
                                 pygame.Rect(x, y - item_h, 6, item_h))

        # Stone floor
        floor_col = _STONE_GRAY
        pygame.draw.rect(surf, _rgba(floor_col), pygame.Rect(0, floor_y, w, h - floor_y))
        tile_sz = 24
        for tx in range(0, w, tile_sz):
            pygame.draw.line(surf, _rgba(_shade(floor_col, -12)), (tx, floor_y), (tx, h), 1)
        for ty in range(floor_y, h, tile_sz):
            pygame.draw.line(surf, _rgba(_shade(floor_col, -12)), (0, ty), (w, ty), 1)

        # Floor noise
        for _ in range(int(w * (h - floor_y) * 0.006)):
            px = rnd.randrange(w)
            py = rnd.randrange(floor_y, h)
            c = _shade(floor_col, rnd.randint(-8, 8))
            surf.set_at((px, py), _rgba(c))

        # Wall/floor divider
        pygame.draw.line(surf, _rgba(_shade(wall_col, -25)), (0, floor_y), (w, floor_y), 2)

        return surf

    # -- Warrior Guild -----------------------------------------------------

    @classmethod
    def _bg_warrior_guild(cls, w: int, h: int) -> pygame.Surface:
        rnd = cls._rng("warrior_guild", w, h)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        wall_h = h // 3
        floor_y = wall_h

        # Stone walls with blue-steel tint
        wall_col = (75, 80, 95)
        surf.fill(_rgba(wall_col))
        for _ in range(int(w * wall_h * 0.018)):
            px, py = rnd.randrange(w), rnd.randrange(wall_h)
            c = _shade(wall_col, rnd.randint(-8, 8))
            surf.set_at((px, py), _rgba(c))

        # Weapon rack outlines on walls
        rack_x_positions = [w // 5, w // 2, w * 4 // 5]
        for rx in rack_x_positions:
            # Vertical mount
            pygame.draw.line(surf, _rgba((50, 50, 60)), (rx, wall_h // 6), (rx, wall_h - 10), 2)
            # Horizontal pegs
            for py in range(wall_h // 4, wall_h - 10, wall_h // 5):
                pygame.draw.line(surf, _rgba((120, 120, 140)),
                                 (rx - 12, py), (rx + 12, py), 2)
                # Weapon silhouette
                wtype = rnd.choice(["sword", "axe", "mace"])
                if wtype == "sword":
                    pygame.draw.line(surf, _rgba((170, 170, 190)),
                                     (rx - 10, py - 2), (rx + 10, py - 2), 2)
                elif wtype == "axe":
                    pygame.draw.line(surf, _rgba((170, 170, 190)),
                                     (rx - 6, py - 2), (rx + 4, py - 2), 2)
                    pygame.draw.rect(surf, _rgba((150, 150, 170)),
                                     pygame.Rect(rx + 4, py - 5, 5, 6))
                else:
                    pygame.draw.line(surf, _rgba((170, 170, 190)),
                                     (rx - 8, py - 2), (rx + 2, py - 2), 2)
                    pygame.draw.circle(surf, _rgba((150, 150, 170)),
                                       (rx + 4, py - 2), 3)

        # Dirt/wood floor
        floor_col = _DIRT_BROWN
        pygame.draw.rect(surf, _rgba(floor_col), pygame.Rect(0, floor_y, w, h - floor_y))
        for _ in range(int(w * (h - floor_y) * 0.012)):
            px = rnd.randrange(w)
            py = rnd.randrange(floor_y, h)
            c = _shade(floor_col, rnd.randint(-12, 12))
            surf.set_at((px, py), _rgba(c))

        # Sparring ring outline (center of floor)
        ring_cx = w // 2
        ring_cy = floor_y + (h - floor_y) * 2 // 3
        ring_r = min(w // 3, (h - floor_y) // 3)
        pygame.draw.circle(surf, _rgba((120, 110, 90)), (ring_cx, ring_cy), ring_r, 2)
        pygame.draw.circle(surf, _rgba((120, 110, 90, 40)), (ring_cx, ring_cy), ring_r - 4, 1)

        # Wall/floor divider
        pygame.draw.line(surf, _rgba((55, 55, 65)), (0, floor_y), (w, floor_y), 2)

        return surf

    # -- Fallback ----------------------------------------------------------

    @classmethod
    def _bg_fallback(cls, building_type: str, w: int, h: int) -> pygame.Surface:
        rnd = cls._rng(f"fallback_{building_type}", w, h)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)

        wall_h = h // 3
        floor_y = wall_h

        wall_col = (90, 85, 80)
        surf.fill(_rgba(wall_col))
        for _ in range(int(w * wall_h * 0.01)):
            px, py = rnd.randrange(w), rnd.randrange(wall_h)
            c = _shade(wall_col, rnd.randint(-6, 6))
            surf.set_at((px, py), _rgba(c))

        floor_col = (105, 100, 95)
        pygame.draw.rect(surf, _rgba(floor_col), pygame.Rect(0, floor_y, w, h - floor_y))
        tile_sz = 20
        for tx in range(0, w, tile_sz):
            pygame.draw.line(surf, _rgba(_shade(floor_col, -10)), (tx, floor_y), (tx, h), 1)
        for ty in range(floor_y, h, tile_sz):
            pygame.draw.line(surf, _rgba(_shade(floor_col, -10)), (0, ty), (w, ty), 1)

        for _ in range(int(w * (h - floor_y) * 0.005)):
            px = rnd.randrange(w)
            py = rnd.randrange(floor_y, h)
            c = _shade(floor_col, rnd.randint(-6, 6))
            surf.set_at((px, py), _rgba(c))

        pygame.draw.line(surf, _rgba(_shade(wall_col, -20)), (0, floor_y), (w, floor_y), 2)
        return surf

    # ------------------------------------------------------------------
    # NPC generation (32x32 procedural sprites)
    # ------------------------------------------------------------------

    @classmethod
    def _gen_npc(cls, building_type: str) -> Optional[pygame.Surface]:
        bt = building_type.lower()
        if bt == "inn":
            return cls._npc_bartender()
        if bt == "marketplace":
            return cls._npc_merchant()
        if bt == "warrior_guild":
            return cls._npc_guildmaster()
        return None

    @staticmethod
    def _npc_base(body_color: Tuple[int, int, int], accent_color: Tuple[int, int, int],
                  accent_type: str = "apron") -> pygame.Surface:
        s = 32
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        cx, cy = s // 2, s // 2

        # Shadow
        shadow = pygame.Rect(0, 0, 18, 8)
        shadow.center = (cx, cy + 8)
        pygame.draw.ellipse(surf, (0, 0, 0, 50), shadow)

        # Body (oval)
        body_rect = pygame.Rect(cx - 6, cy - 4, 12, 14)
        pygame.draw.ellipse(surf, body_color, body_rect)
        pygame.draw.ellipse(surf, (30, 30, 30), body_rect, 1)

        # Head
        head_center = (cx, cy - 8)
        pygame.draw.circle(surf, _shade(body_color, 30), head_center, 5)
        pygame.draw.circle(surf, (30, 30, 30), head_center, 5, 1)

        # Eyes (2 tiny dots)
        pygame.draw.circle(surf, (20, 20, 20), (cx - 2, cy - 9), 1)
        pygame.draw.circle(surf, (20, 20, 20), (cx + 2, cy - 9), 1)

        # Accent
        if accent_type == "apron":
            apron = pygame.Rect(cx - 5, cy + 2, 10, 8)
            pygame.draw.rect(surf, accent_color, apron)
            pygame.draw.rect(surf, _shade(accent_color, -30), apron, 1)
        elif accent_type == "bag":
            pygame.draw.circle(surf, accent_color, (cx + 7, cy + 4), 4)
            pygame.draw.circle(surf, _shade(accent_color, -30), (cx + 7, cy + 4), 4, 1)
        elif accent_type == "cloak":
            # Cape draped behind body
            points = [(cx - 7, cy - 6), (cx + 7, cy - 6),
                       (cx + 9, cy + 10), (cx - 9, cy + 10)]
            pygame.draw.polygon(surf, (*accent_color, 180), points)
            pygame.draw.polygon(surf, _shade(accent_color, -30), points, 1)

        return surf

    @classmethod
    def _npc_bartender(cls) -> pygame.Surface:
        return cls._npc_base(
            body_color=(140, 100, 65),
            accent_color=(220, 200, 180),
            accent_type="apron",
        )

    @classmethod
    def _npc_merchant(cls) -> pygame.Surface:
        return cls._npc_base(
            body_color=(90, 110, 80),
            accent_color=(200, 180, 60),
            accent_type="bag",
        )

    @classmethod
    def _npc_guildmaster(cls) -> pygame.Surface:
        return cls._npc_base(
            body_color=(100, 100, 120),
            accent_color=(60, 90, 170),
            accent_type="cloak",
        )

    # ------------------------------------------------------------------
    # Furniture generation
    # ------------------------------------------------------------------

    @classmethod
    def _gen_furniture(cls, building_type: str, w: int, h: int) -> List[FurnitureAnchor]:
        bt = building_type.lower()
        if bt == "inn":
            return cls._furniture_inn(w, h)
        if bt == "marketplace":
            return cls._furniture_marketplace(w, h)
        if bt == "warrior_guild":
            return cls._furniture_warrior_guild(w, h)
        return cls._furniture_fallback(w, h)

    @classmethod
    def _furniture_inn(cls, w: int, h: int) -> List[FurnitureAnchor]:
        rnd = cls._rng("furniture_inn", w, h)
        anchors: List[FurnitureAnchor] = []
        wall_h = h // 3

        # Bar counter (top, spanning most of width)
        counter_w, counter_h = w * 3 // 4, 16
        counter_x = (w - counter_w) // 2
        counter_y = wall_h + 20
        counter_surf = pygame.Surface((counter_w, counter_h), pygame.SRCALPHA)
        pygame.draw.rect(counter_surf, _rgba((90, 60, 35)), pygame.Rect(0, 0, counter_w, counter_h))
        pygame.draw.rect(counter_surf, _rgba((70, 45, 25)), pygame.Rect(0, 0, counter_w, counter_h), 2)
        # Mugs on counter
        for mx in range(12, counter_w - 12, rnd.randint(28, 42)):
            pygame.draw.rect(counter_surf, _rgba((180, 160, 120)), pygame.Rect(mx, 2, 6, 10))
            pygame.draw.rect(counter_surf, _rgba((160, 140, 100)), pygame.Rect(mx, 2, 6, 10), 1)
        anchors.append(FurnitureAnchor("counter", counter_x, counter_y, counter_surf))

        # Tables (middle area)
        table_y_start = wall_h + 70
        for i, tx in enumerate([w // 4, w * 3 // 4]):
            ty = table_y_start + i * 80
            if ty + 40 > h - 30:
                break
            tbl_surf = pygame.Surface((48, 32), pygame.SRCALPHA)
            pygame.draw.rect(tbl_surf, _rgba((100, 70, 40)), pygame.Rect(0, 0, 48, 32), border_radius=3)
            pygame.draw.rect(tbl_surf, _rgba((80, 55, 30)), pygame.Rect(0, 0, 48, 32), 2, border_radius=3)
            anchors.append(FurnitureAnchor(f"table_{i}", tx - 24, ty, tbl_surf))

            # Stools around table
            for sx_off in [-20, 52]:
                stool_surf = pygame.Surface((12, 12), pygame.SRCALPHA)
                pygame.draw.circle(stool_surf, _rgba((80, 60, 40)), (6, 6), 6)
                pygame.draw.circle(stool_surf, _rgba((60, 45, 30)), (6, 6), 6, 1)
                anchors.append(FurnitureAnchor(f"stool_{i}_{sx_off}", tx - 24 + sx_off, ty + 10, stool_surf))

        # Fireplace (bottom-left)
        fp_x, fp_y = 10, h - 60
        fp_surf = pygame.Surface((50, 50), pygame.SRCALPHA)
        pygame.draw.rect(fp_surf, _rgba((60, 55, 50)), pygame.Rect(0, 0, 50, 50))
        pygame.draw.rect(fp_surf, _rgba((45, 40, 35)), pygame.Rect(0, 0, 50, 50), 2)
        # Fire glow
        pygame.draw.rect(fp_surf, _rgba((200, 100, 30)), pygame.Rect(10, 15, 30, 25))
        pygame.draw.rect(fp_surf, _rgba((255, 160, 50, 120)), pygame.Rect(14, 20, 22, 16))
        anchors.append(FurnitureAnchor("fireplace", fp_x, fp_y, fp_surf))

        return anchors

    @classmethod
    def _furniture_marketplace(cls, w: int, h: int) -> List[FurnitureAnchor]:
        rnd = cls._rng("furniture_marketplace", w, h)
        anchors: List[FurnitureAnchor] = []
        wall_h = h // 3

        # Central counter
        counter_w, counter_h = w // 2, 18
        counter_x = (w - counter_w) // 2
        counter_y = wall_h + 40
        counter_surf = pygame.Surface((counter_w, counter_h), pygame.SRCALPHA)
        pygame.draw.rect(counter_surf, _rgba((80, 80, 75)), pygame.Rect(0, 0, counter_w, counter_h))
        pygame.draw.rect(counter_surf, _rgba((60, 60, 55)), pygame.Rect(0, 0, counter_w, counter_h), 2)
        # Coins on counter
        for cx_off in range(10, counter_w - 10, rnd.randint(20, 32)):
            pygame.draw.circle(counter_surf, _rgba((200, 180, 60)), (cx_off, counter_h // 2), 3)
        anchors.append(FurnitureAnchor("counter", counter_x, counter_y, counter_surf))

        # Display shelves (left and right)
        for side, sx in [("left", 8), ("right", w - 38)]:
            shelf_surf = pygame.Surface((30, h - wall_h - 30), pygame.SRCALPHA)
            shelf_h = shelf_surf.get_height()
            pygame.draw.rect(shelf_surf, _rgba((75, 65, 55)), pygame.Rect(0, 0, 30, shelf_h))
            pygame.draw.rect(shelf_surf, _rgba((55, 48, 40)), pygame.Rect(0, 0, 30, shelf_h), 1)
            # Shelf rows with items
            for row_y in range(10, shelf_h - 10, 24):
                pygame.draw.line(shelf_surf, _rgba((60, 52, 45)), (2, row_y), (28, row_y), 2)
                for ix in range(6, 26, rnd.randint(8, 14)):
                    item_col = rnd.choice([
                        (60, 150, 80), (150, 50, 50), (80, 80, 170), (180, 160, 70),
                    ])
                    item_h = rnd.randint(5, 10)
                    pygame.draw.rect(shelf_surf, _rgba(item_col),
                                     pygame.Rect(ix, row_y - item_h, 5, item_h))
            anchors.append(FurnitureAnchor(f"shelf_{side}", sx, wall_h + 15, shelf_surf))

        return anchors

    @classmethod
    def _furniture_warrior_guild(cls, w: int, h: int) -> List[FurnitureAnchor]:
        rnd = cls._rng("furniture_warrior_guild", w, h)
        anchors: List[FurnitureAnchor] = []
        wall_h = h // 3
        floor_mid = wall_h + (h - wall_h) // 2

        # Training dummies
        for i, dx in enumerate([w // 4, w * 3 // 4]):
            dy = wall_h + 30
            dummy_surf = pygame.Surface((24, 48), pygame.SRCALPHA)
            # Post
            pygame.draw.line(dummy_surf, _rgba((90, 70, 50)), (12, 10), (12, 46), 3)
            # Cross-arm
            pygame.draw.line(dummy_surf, _rgba((90, 70, 50)), (3, 18), (21, 18), 3)
            # Head (straw ball)
            pygame.draw.circle(dummy_surf, _rgba((180, 160, 100)), (12, 8), 6)
            pygame.draw.circle(dummy_surf, _rgba((150, 130, 80)), (12, 8), 6, 1)
            # Base
            pygame.draw.rect(dummy_surf, _rgba((70, 55, 40)), pygame.Rect(6, 44, 12, 4))
            anchors.append(FurnitureAnchor(f"dummy_{i}", dx - 12, dy, dummy_surf))

        # Weapon rack (right wall area, floor level)
        rack_x = w - 50
        rack_y = wall_h + 15
        rack_surf = pygame.Surface((40, 60), pygame.SRCALPHA)
        pygame.draw.rect(rack_surf, _rgba((70, 60, 50)), pygame.Rect(0, 0, 40, 60))
        pygame.draw.rect(rack_surf, _rgba((55, 48, 40)), pygame.Rect(0, 0, 40, 60), 1)
        # Weapons on rack
        for wy in range(8, 55, 14):
            pygame.draw.line(rack_surf, _rgba((170, 170, 190)), (5, wy), (35, wy), 2)
            hilt_x = rnd.randint(8, 30)
            pygame.draw.rect(rack_surf, _rgba((120, 80, 40)), pygame.Rect(hilt_x, wy - 3, 4, 6))
        anchors.append(FurnitureAnchor("weapon_rack", rack_x, rack_y, rack_surf))

        return anchors

    @classmethod
    def _furniture_fallback(cls, w: int, h: int) -> List[FurnitureAnchor]:
        anchors: List[FurnitureAnchor] = []
        wall_h = h // 3

        # Simple table in center
        tbl_w, tbl_h = 60, 36
        tbl_x = (w - tbl_w) // 2
        tbl_y = wall_h + (h - wall_h) // 2 - tbl_h // 2
        tbl_surf = pygame.Surface((tbl_w, tbl_h), pygame.SRCALPHA)
        pygame.draw.rect(tbl_surf, _rgba((95, 80, 60)), pygame.Rect(0, 0, tbl_w, tbl_h), border_radius=3)
        pygame.draw.rect(tbl_surf, _rgba((75, 60, 45)), pygame.Rect(0, 0, tbl_w, tbl_h), 2, border_radius=3)
        anchors.append(FurnitureAnchor("table", tbl_x, tbl_y, tbl_surf))

        return anchors

    # ------------------------------------------------------------------
    # Hero slot positions
    # ------------------------------------------------------------------

    @classmethod
    def _gen_hero_slots(cls, building_type: str, w: int, h: int) -> List[HeroSlot]:
        bt = building_type.lower()
        if bt == "inn":
            return cls._slots_inn(w, h)
        if bt == "marketplace":
            return cls._slots_marketplace(w, h)
        if bt == "warrior_guild":
            return cls._slots_warrior_guild(w, h)
        return cls._slots_fallback(w, h)

    @staticmethod
    def _slots_inn(w: int, h: int) -> List[HeroSlot]:
        wall_h = h // 3
        counter_y = wall_h + 20
        table_y0 = wall_h + 70
        return [
            HeroSlot(w // 4 - 30, counter_y + 20, "at stool 1"),
            HeroSlot(w // 4 + 20, counter_y + 20, "at stool 2"),
            HeroSlot(w // 4 - 10, table_y0 + 36, "at table 1a"),
            HeroSlot(w // 4 + 30, table_y0 + 36, "at table 1b"),
            HeroSlot(w * 3 // 4 - 10, table_y0 + 116, "at table 2a"),
            HeroSlot(w * 3 // 4 + 30, table_y0 + 116, "at table 2b"),
        ]

    @staticmethod
    def _slots_marketplace(w: int, h: int) -> List[HeroSlot]:
        wall_h = h // 3
        counter_y = wall_h + 40
        return [
            HeroSlot(50, wall_h + 80, "browsing left shelf"),
            HeroSlot(w - 80, wall_h + 80, "browsing right shelf"),
            HeroSlot(w // 2 - 16, counter_y + 24, "at counter"),
        ]

    @staticmethod
    def _slots_warrior_guild(w: int, h: int) -> List[HeroSlot]:
        wall_h = h // 3
        ring_cy = wall_h + (h - wall_h) * 2 // 3
        return [
            HeroSlot(w // 4 + 30, wall_h + 50, "at dummy 1"),
            HeroSlot(w * 3 // 4 + 30, wall_h + 50, "at dummy 2"),
            HeroSlot(w // 2 - 40, ring_cy - 10, "sparring left"),
            HeroSlot(w // 2 + 20, ring_cy - 10, "sparring right"),
        ]

    @staticmethod
    def _slots_fallback(w: int, h: int) -> List[HeroSlot]:
        wall_h = h // 3
        mid_y = wall_h + (h - wall_h) // 2
        return [
            HeroSlot(w // 4, mid_y - 20, "standing left"),
            HeroSlot(w * 3 // 4 - 32, mid_y - 20, "standing right"),
            HeroSlot(w // 3, mid_y + 40, "standing back-left"),
            HeroSlot(w * 2 // 3 - 32, mid_y + 40, "standing back-right"),
        ]
