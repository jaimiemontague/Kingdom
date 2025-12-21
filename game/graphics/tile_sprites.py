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

    _cache: Dict[Tuple[int, int, int], pygame.Surface] = {}  # (tile_type, variant, size) -> Surface

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
            0: 6,  # grass (more low-noise variety)
            1: 3,  # water
            2: 6,  # path (more definition variants)
            3: 4,  # tree (reduce copy-paste feel)
        }
        v = cls._variant(tile_type, x, y, variant_counts.get(int(tile_type), 1))
        key = (int(tile_type), int(v), s)
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

        if tile_type == 0:  # grass
            # Milestone 1 (terrain): reduce "debug speckle" and shift to low-noise, readable variation.
            # We use only 6 deterministic variants chosen by coord hash; each variant is cached.
            speckle(pal.grass, pal.grass_dark, pal.grass_light, density=0.02 + 0.002 * variant)
            # Add 1–2 subtle clumps (macro noise) rather than heavy pixel noise.
            clumps = 1 if variant < 3 else 2
            for _ in range(clumps):
                cx = rnd.randrange(6, s - 6)
                cy = rnd.randrange(6, s - 6)
                col = pal.grass_dark if rnd.random() < 0.6 else pal.grass_light
                blob(cx, cy, col, r=rnd.randrange(2, 4))
            # Very occasional tiny prop hints per variant (kept subtle to avoid noise soup).
            if variant in (4, 5):
                # small flower/rock pixels
                for _ in range(3):
                    px = rnd.randrange(3, s - 3)
                    py = rnd.randrange(3, s - 3)
                    surf.set_at((px, py), (235, 235, 235, 255))
                    surf.set_at((px + 1, py), (60, 160, 60, 255))
            return surf

        if tile_type == 1:  # water
            speckle(pal.water, pal.water_dark, pal.water_light, density=0.05 + 0.02 * variant)
            # A couple of tiny wave streaks
            for _ in range(2 + variant):
                y = rnd.randrange(3, s - 3)
                x0 = rnd.randrange(0, s - 8)
                for dx in range(6):
                    surf.set_at((x0 + dx, y), (*pal.water_light, 220))
            return surf

        if tile_type == 2:  # path
            # Path readability: clearer edge definition + less noisy interior.
            speckle(pal.path, pal.path_dark, pal.path_light, density=0.04 + 0.01 * (variant % 3))

            # Edge darkening (gives the path a crisp boundary even without neighbor context).
            edge = pal.path_dark
            edge_w = 2
            pygame.draw.rect(surf, edge, pygame.Rect(0, 0, s, edge_w))
            pygame.draw.rect(surf, edge, pygame.Rect(0, s - edge_w, s, edge_w))
            pygame.draw.rect(surf, edge, pygame.Rect(0, 0, edge_w, s))
            pygame.draw.rect(surf, edge, pygame.Rect(s - edge_w, 0, edge_w, s))

            # Interior "track" variation (variants suggest straight/corner junctions visually).
            if variant in (1, 4):
                # light center lane
                pygame.draw.rect(surf, pal.path_light, pygame.Rect(s // 2 - 2, 2, 4, s - 4))
            elif variant in (2, 5):
                # diagonal hint
                for i in range(0, s, 2):
                    x = i
                    y = s - 1 - i
                    if 1 <= x < s - 1 and 1 <= y < s - 1:
                        surf.set_at((x, y), (*pal.path_light, 255))

            # Pebbles (kept moderate)
            for _ in range(4 + (variant % 3) * 2):
                px = rnd.randrange(1, s - 1)
                py = rnd.randrange(1, s - 1)
                surf.set_at((px, py), (*pal.path_light, 255))
            return surf

        if tile_type == 3:  # tree
            # Base: grass-ish underlay
            speckle(pal.grass, pal.grass_dark, pal.grass_light, density=0.03)
            # Trunk
            trunk_w = max(2, s // 8)
            trunk_h = max(5, s // 3)
            # More variants: shift trunk/canopy subtly to reduce copy-paste feel.
            tx = s // 2 - trunk_w // 2 + ((variant % 2) * 2 - 1)
            ty = s - trunk_h - 2
            pygame.draw.rect(surf, pal.tree_trunk, pygame.Rect(int(tx), int(ty), int(trunk_w), int(trunk_h)))
            # Canopy
            canopy_r = max(6, s // 3)
            cx = s // 2 + (1 if (variant % 2) else -1)
            cy = s // 2 + (0 if variant < 2 else 1)
            pygame.draw.circle(surf, pal.tree, (int(cx), int(cy)), int(canopy_r))
            pygame.draw.circle(surf, pal.tree_dark, (int(cx - 2), int(cy - 2)), int(max(2, canopy_r - 4)))
            # Small ground shadow for readability
            shadow = pygame.Rect(0, 0, int(canopy_r * 1.6), int(canopy_r * 0.6))
            shadow.center = (s // 2, s - 6)
            pygame.draw.ellipse(surf, (0, 0, 0, 45), shadow)
            return surf

        # Unknown tile type: fallback to a neutral checker (helps debugging).
        surf.fill((80, 80, 80, 255))
        for yy in range(0, s, 2):
            for xx in range(0, s, 2):
                surf.set_at((xx, yy), (95, 95, 95, 255))
        return surf



