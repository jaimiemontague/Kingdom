from __future__ import annotations

import random
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygame

from config import BUILDING_COLORS, TILE_SIZE
from game.graphics.animation import load_png_frames


@dataclass(frozen=True)
class BuildingSpriteSpec:
    outline: Tuple[int, int, int] = (25, 25, 25)
    scaffold: Tuple[int, int, int] = (120, 100, 70)
    smoke: Tuple[int, int, int] = (80, 80, 80)


class BuildingSpriteLibrary:
    """
    Pixel-art-first building sprites with state variants.

    Optional assets can be supplied under:
      assets/sprites/buildings/<building_type>/<state>/*.png
    where state is one of: built, construction, damaged.
    """

    _cache: Dict[Tuple[str, str, int, int], pygame.Surface] = {}  # (type, state, w, h) -> Surface

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _assets_dir(cls) -> Path:
        return cls._repo_root() / "assets" / "sprites" / "buildings"

    @classmethod
    def get(
        cls,
        building_type: str,
        state: str,
        *,
        size_px: tuple[int, int],
    ) -> Optional[pygame.Surface]:
        bt = str(building_type or "building")
        st = str(state or "built")
        w, h = int(size_px[0]), int(size_px[1])
        if w <= 0 or h <= 0:
            return None

        key = (bt, st, w, h)
        surf = cls._cache.get(key)
        if surf is not None:
            return surf

        # Try assets first
        frames = cls._try_load_asset_frames(bt, st, size_px=(w, h))
        if frames:
            surf = frames[0]
            cls._cache[key] = surf
            return surf

        surf = cls._procedural(bt, st, w=w, h=h)
        cls._cache[key] = surf
        return surf

    @classmethod
    def _try_load_asset_frames(cls, building_type: str, state: str, *, size_px: tuple[int, int]) -> list[pygame.Surface]:
        folder = cls._assets_dir() / building_type / state
        return load_png_frames(folder, scale_to=(int(size_px[0]), int(size_px[1])))

    @staticmethod
    def _procedural(building_type: str, state: str, *, w: int, h: int) -> pygame.Surface:
        spec = BuildingSpriteSpec()
        base = BUILDING_COLORS.get(building_type, (128, 128, 128))

        # Deterministic per (type,state,size) so buildings look consistent.
        seed_s = f"{building_type}|{state}|{int(w)}|{int(h)}"
        seed = zlib.crc32(seed_s.encode("utf-8")) & 0xFFFFFFFF
        rnd = random.Random(seed)

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((*base, 255))

        # Add a simple “roof” stripe at the top to give depth.
        roof_h = max(2, min(6, h // 6))
        roof = (max(0, base[0] - 20), max(0, base[1] - 20), max(0, base[2] - 20))
        pygame.draw.rect(surf, roof, pygame.Rect(0, 0, w, roof_h))

        # Dither noise
        for _ in range(int((w * h) * 0.015)):
            px = rnd.randrange(0, w)
            py = rnd.randrange(0, h)
            c = (
                min(255, base[0] + rnd.randrange(-12, 13)),
                min(255, base[1] + rnd.randrange(-12, 13)),
                min(255, base[2] + rnd.randrange(-12, 13)),
                255,
            )
            surf.set_at((px, py), c)

        # State overlays
        st = (state or "built").lower()
        if st == "construction":
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 40))
            surf.blit(overlay, (0, 0))

            # Scaffold diagonals
            step = max(6, TILE_SIZE // 2)
            for x in range(-h, w + h, step):
                pygame.draw.line(surf, (*spec.scaffold, 200), (x, h), (x + h, 0), 2)

            # Small hammer icon
            hx, hy = w - 10, 6
            pygame.draw.line(surf, (250, 250, 250), (hx - 6, hy + 6), (hx, hy), 2)
            pygame.draw.rect(surf, (250, 250, 250), pygame.Rect(hx - 2, hy - 1, 6, 3))

        elif st == "damaged":
            # Cracks
            crack_col = (40, 40, 40)
            for _ in range(2 + (w * h) // (TILE_SIZE * TILE_SIZE * 4)):
                x0 = rnd.randrange(2, w - 2)
                y0 = rnd.randrange(roof_h + 2, h - 2)
                x1 = max(1, min(w - 2, x0 + rnd.randrange(-12, 13)))
                y1 = max(roof_h + 1, min(h - 2, y0 + rnd.randrange(8, 18)))
                pygame.draw.line(surf, crack_col, (x0, y0), (x1, y1), 1)

            # Smoke puffs (top)
            for _ in range(4):
                sx = rnd.randrange(6, w - 6)
                sy = rnd.randrange(roof_h, roof_h + 10)
                pygame.draw.circle(surf, (*spec.smoke, 120), (sx, sy), rnd.randrange(3, 6))

        # Outline (pixel border)
        pygame.draw.rect(surf, spec.outline, pygame.Rect(0, 0, w, h), 2)
        return surf


