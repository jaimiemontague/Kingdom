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
            0: 4,  # grass
            1: 3,  # water
            2: 3,  # path
            3: 2,  # tree
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

        if tile_type == 0:  # grass
            speckle(pal.grass, pal.grass_dark, pal.grass_light, density=0.06 + 0.01 * variant)
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
            speckle(pal.path, pal.path_dark, pal.path_light, density=0.08 + 0.02 * variant)
            # Add a couple of pebble dots
            for _ in range(6 + variant * 2):
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
            tx = s // 2 - trunk_w // 2 + (variant - 0.5)
            ty = s - trunk_h - 2
            pygame.draw.rect(surf, pal.tree_trunk, pygame.Rect(int(tx), int(ty), int(trunk_w), int(trunk_h)))
            # Canopy
            canopy_r = max(6, s // 3)
            cx = s // 2 + (1 if variant else -1)
            cy = s // 2
            pygame.draw.circle(surf, pal.tree, (int(cx), int(cy)), int(canopy_r))
            pygame.draw.circle(surf, pal.tree_dark, (int(cx - 2), int(cy - 2)), int(max(2, canopy_r - 4)))
            return surf

        # Unknown tile type: fallback to a neutral checker (helps debugging).
        surf.fill((80, 80, 80, 255))
        for yy in range(0, s, 2):
            for xx in range(0, s, 2):
                surf.set_at((xx, yy), (95, 95, 95, 255))
        return surf


