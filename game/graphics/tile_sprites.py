from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Tuple

import pygame

from config import TILE_SIZE, COLOR_GRASS, COLOR_WATER, COLOR_PATH, COLOR_TREE


@dataclass(frozen=True)
class TilePalette:
    grass: Tuple[int, int, int] = COLOR_GRASS
    grass_dark: Tuple[int, int, int] = (26, 120, 26)
    grass_light: Tuple[int, int, int] = (60, 160, 60)

    water: Tuple[int, int, int] = COLOR_WATER
    water_dark: Tuple[int, int, int] = (45, 85, 185)
    water_light: Tuple[int, int, int] = (110, 160, 255)

    path: Tuple[int, int, int] = COLOR_PATH
    path_dark: Tuple[int, int, int] = (110, 95, 80)
    path_light: Tuple[int, int, int] = (165, 145, 120)

    tree: Tuple[int, int, int] = COLOR_TREE
    tree_dark: Tuple[int, int, int] = (0, 70, 0)
    tree_trunk: Tuple[int, int, int] = (120, 85, 50)


class TileSpriteLibrary:
    """
    Pixel-art-first tile sprites with deterministic variation.

    We don't require external PNG assets yet: this generates small procedural
    pixel tiles and caches them. Later, this can be extended to load real
    tileset art without changing the world renderer.
    """

    # Bump _CACHE_VERSION when procedural art changes so cached Surfaces refresh (WK21 path/grass fixes).
    _CACHE_VERSION = 2

    _cache: Dict[Tuple[int, int, int, int], pygame.Surface] = {}  # (tile_type, variant, size, rev) -> Surface

    @staticmethod
    def _hash32(tile_type: int, x: int, y: int) -> int:
        # Deterministic, fast integer hash for stable tile variations.
        h = (x * 73856093) ^ (y * 19349663) ^ (tile_type * 83492791)
        return h & 0xFFFFFFFF

    @classmethod
    def _variant(cls, tile_type: int, x: int, y: int, variants: int) -> int:
        if variants <= 1:
            return 0
        return int(cls._hash32(tile_type, x, y) % int(variants))

    @classmethod
    def get(cls, tile_type: int, x: int, y: int, *, size: int = TILE_SIZE) -> pygame.Surface | None:
        s = int(size)
        if s <= 0:
            return None

        # Variant counts per tile type.
        variant_counts = {
            0: 24,  # grass 
            1: 6,   # water
            2: 12,  # path 
            3: 8,   # tree 
        }
        v = cls._variant(tile_type, x, y, variant_counts.get(int(tile_type), 1))
        key = (int(tile_type), int(v), s, cls._CACHE_VERSION)
        surf = cls._cache.get(key)
        if surf is not None:
            return surf

        surf = cls._generate(tile_type=int(tile_type), variant=int(v), size=s)
        cls._cache[key] = surf
        return surf

    @classmethod
    def _generate(cls, *, tile_type: int, variant: int, size: int) -> pygame.Surface:
        pal = TilePalette()
        s = int(size)
        rnd = random.Random((tile_type << 16) + (variant << 8) + s)

        surf = pygame.Surface((s, s), pygame.SRCALPHA)

        def speckle(base: Tuple[int, int, int], a: Tuple[int, int, int], b: Tuple[int, int, int], density: float):
            surf.fill(base)
            count = int(s * s * max(0.0, min(1.0, float(density))))
            for _ in range(count):
                px = rnd.randrange(0, s)
                py = rnd.randrange(0, s)
                col = a if rnd.random() < 0.5 else b
                surf.set_at((px, py), (*col, 255))

        def blob(px: int, py: int, col: Tuple[int, int, int], r: int):
            rr = max(1, int(r))
            x0 = max(0, int(px - rr))
            x1 = min(s - 1, int(px + rr))
            y0 = max(0, int(py - rr))
            y1 = min(s - 1, int(py + rr))
            r2 = rr * rr
            for yy in range(y0, y1 + 1):
                dy = yy - py
                for xx in range(x0, x1 + 1):
                    dx = xx - px
                    if (dx * dx + dy * dy) <= r2:
                        surf.set_at((xx, yy), (*col, 255))

        def _shade(rgb: Tuple[int, int, int], delta: int) -> Tuple[int, int, int]:
            return (
                max(0, min(255, rgb[0] + delta)),
                max(0, min(255, rgb[1] + delta)),
                max(0, min(255, rgb[2] + delta)),
            )

        if tile_type == 0:  # grass
            surf.fill(pal.grass)
            # 4x Detail: Real tufts instead of full speckle
            
            # Draw 3-5 grass tufts (V shape or small strokes)
            tuft_count = 3 + (variant % 3)
            for _ in range(tuft_count):
                cx, cy = rnd.randrange(2, s - 4), rnd.randrange(4, s - 2)
                # shadow
                surf.set_at((cx, cy), (*pal.grass_dark, 255))
                surf.set_at((cx+1, cy), (*pal.grass_dark, 255))
                # blade
                surf.set_at((cx, cy-1), (*pal.grass_light, 255))
                surf.set_at((cx+2, cy-2), (*pal.grass_light, 255))
                surf.set_at((cx+1, cy-1), (*pal.grass_light, 255))

            # Larger macro patches of distinct grass shades
            if variant % 4 == 0:
                blob(rnd.randrange(6, s - 6), rnd.randrange(6, s - 6), pal.grass_light, r=rnd.randrange(4, 7))
            elif variant % 4 == 1:
                blob(rnd.randrange(6, s - 6), rnd.randrange(6, s - 6), pal.grass_dark, r=rnd.randrange(3, 6))

            # Flora / props on specific variants
            if variant % 6 == 0:
                # small flower cluster
                fx, fy = rnd.randrange(4, s - 5), rnd.randrange(4, s - 5)
                flower_color = [(240, 200, 240), (255, 255, 180), (180, 220, 255)][variant % 3]
                surf.set_at((fx, fy), (*flower_color, 255))
                surf.set_at((fx+1, fy-1), (*flower_color, 255))
                surf.set_at((fx+2, fy), (*flower_color, 255))
                surf.set_at((fx+1, fy+1), (*flower_color, 255))
                # center
                surf.set_at((fx+1, fy), (255, 255, 255, 255))
                # shadow
                surf.set_at((fx+1, fy+2), (*pal.grass_dark, 255))
            
            if variant % 8 == 7:
                # tiny pebble cluster
                px, py = rnd.randrange(4, s - 4), rnd.randrange(4, s - 4)
                surf.set_at((px, py), (160, 160, 165, 255))
                surf.set_at((px+1, py), (130, 130, 135, 255))
                surf.set_at((px, py+1), (*pal.grass_dark, 255))
            return surf

        if tile_type == 1:  # water
            surf.fill(pal.water)
            # Base water pattern
            for yy in range(0, s, 4):
                for xx in range(0, s, 4):
                    if rnd.random() < 0.3:
                        surf.set_at((xx, yy), (*pal.water_dark, 255))

            # 4x Detail: pronounced animated-looking wave crests
            wave_count = 2 + (variant % 3)
            for _ in range(wave_count):
                wy = rnd.randrange(3, s - 3)
                wx = rnd.randrange(2, s - 8)
                # wave highlight
                pygame.draw.line(surf, pal.water_light, (wx, wy), (wx + 4, wy), 1)
                pygame.draw.line(surf, pal.water_light, (wx + 1, wy + 1), (wx + 3, wy + 1), 1)
                # wave shadow
                pygame.draw.line(surf, pal.water_dark, (wx, wy + 2), (wx + 4, wy + 2), 1)
            return surf

        if tile_type == 2:  # path — deterministic cobble (WK21: no per-edge random noise; reads clean in 3D + nearest filter)
            surf.fill(pal.path)
            edge_dark = pal.path_dark
            edge_light = pal.path_light
            # Solid 1px frame (no random gaps — avoids "scattered pixel" look when mip/blur)
            for i in range(s):
                surf.set_at((i, 0), (*edge_dark, 255))
                surf.set_at((i, s - 1), (*edge_dark, 255))
                surf.set_at((0, i), (*edge_dark, 255))
                surf.set_at((s - 1, i), (*edge_dark, 255))
            # Cobble grid: variant shifts phase so tiles don't all look identical
            ox = (variant * 2) % 5
            oy = (variant * 3) % 5
            cell = max(6, s // 5)
            y = 2 + oy
            while y < s - 3:
                x = 2 + ox
                while x < s - 3:
                    rw = min(cell - 1, s - 2 - x)
                    rh = min(cell - 1, s - 2 - y)
                    if rw >= 3 and rh >= 3:
                        pygame.draw.rect(surf, edge_light, pygame.Rect(x, y, rw, rh), 0)
                        pygame.draw.rect(surf, edge_dark, pygame.Rect(x, y, rw, rh), 1)
                    x += cell
                y += cell
            # Ruts / wheel tracks (variant-based, deterministic)
            if variant % 3 == 1:
                pygame.draw.line(surf, edge_light, (s // 3, 3), (s // 3, s - 4), 1)
                pygame.draw.line(surf, edge_dark, (s // 3 + 1, 3), (s // 3 + 1, s - 4), 1)
                pygame.draw.line(surf, edge_light, (2 * s // 3, 3), (2 * s // 3, s - 4), 1)
                pygame.draw.line(surf, edge_dark, (2 * s // 3 + 1, 3), (2 * s // 3 + 1, s - 4), 1)
            elif variant % 3 == 2:
                pygame.draw.line(surf, edge_light, (3, s // 3), (s - 4, s // 3), 1)
                pygame.draw.line(surf, edge_dark, (3, s // 3 + 1), (s - 4, s // 3 + 1), 1)
                pygame.draw.line(surf, edge_light, (3, 2 * s // 3), (s - 4, 2 * s // 3), 1)
                pygame.draw.line(surf, edge_dark, (3, 2 * s // 3 + 1), (s - 4, 2 * s // 3 + 1), 1)

            return surf

        if tile_type == 3:  # tree
            # Base: grass-ish underlay with tufts
            surf.fill(pal.grass)
            for _ in range(4):
                tx, ty = rnd.randrange(2, s - 4), rnd.randrange(4, s - 2)
                surf.set_at((tx, ty), (*pal.grass_dark, 255))
                surf.set_at((tx+1, ty-1), (*pal.grass_light, 255))

            # Trunk & Roots
            trunk_w = max(3, s // 6)
            trunk_h = max(6, s // 2.5)
            # More variants: shift trunk/canopy subtly to reduce copy-paste feel.
            tx = s // 2 - trunk_w // 2 + ((variant % 3) - 1)
            ty = s - trunk_h - 2
            # shadow base
            shadow_rect = pygame.Rect(0, 0, int(trunk_w * 3), int(trunk_w * 1.5))
            shadow_rect.center = (s // 2, s - 4)
            pygame.draw.ellipse(surf, (0, 0, 0, 60), shadow_rect)

            # draw trunk
            pygame.draw.rect(surf, pal.tree_trunk, pygame.Rect(int(tx), int(ty), int(trunk_w), int(trunk_h)))
            # trunk texture (bark styling)
            trunk_dark = _shade(pal.tree_trunk, -30)
            trunk_light = _shade(pal.tree_trunk, 20)
            pygame.draw.line(surf, trunk_dark, (tx, ty), (tx, ty + trunk_h), 1)
            pygame.draw.line(surf, trunk_light, (tx + 1, ty), (tx + 1, ty + trunk_h), 1)
            # roots
            pygame.draw.line(surf, trunk_dark, (tx - 2, ty + trunk_h), (tx, ty + trunk_h - 2), 1)
            pygame.draw.line(surf, trunk_dark, (tx + trunk_w, ty + trunk_h - 2), (tx + trunk_w + 2, ty + trunk_h), 1)

            # Canopy (3-Tiered 4x detail)
            # We want volume. 
            # 3 clusters of leaves
            c1_x, c1_y = s // 2 + (variant % 2)*2 - 1, s // 2 - 2
            c2_x, c2_y = c1_x - 5, c1_y + 4
            c3_x, c3_y = c1_x + 5, c1_y + 2
            clusters = [(c1_x, c1_y, 8), (c2_x, c2_y, 6), (c3_x, c3_y, 6)]

            # Palette
            c_base = pal.tree
            c_dark = pal.tree_dark
            c_light = _shade(c_base, 25)

            # draw shadows first
            for cx, cy, cr in clusters:
                pygame.draw.circle(surf, c_dark, (int(cx), int(cy + 2)), int(cr))
            # draw base
            for cx, cy, cr in clusters:
                pygame.draw.circle(surf, c_base, (int(cx), int(cy)), int(cr))
            # draw highlights
            for cx, cy, cr in clusters:
                pygame.draw.circle(surf, c_light, (int(cx - cr//3), int(cy - cr//3)), int(cr - 2))

            # Overlapping leaves (pixel noise on canopy)
            for _ in range(8 + variant % 4):
                lx = rnd.randrange(c2_x - 4, c3_x + 4)
                ly = rnd.randrange(c1_y - 6, c2_y + 4)
                # Ensure it's inside the canopy roughly
                if surf.get_at((lx, ly))[:3] in (c_base, c_dark, c_light):
                    surf.set_at((lx, ly), (*c_light, 255))
                    surf.set_at((lx+1, ly+1), (*c_dark, 255))

            return surf

        # Unknown tile type: fallback to a neutral checker (helps debugging).
        surf.fill((80, 80, 80, 255))
        for yy in range(0, s, 2):
            for xx in range(0, s, 2):
                surf.set_at((xx, yy), (95, 95, 95, 255))
        return surf



