"""
Pygame Surface → Ursina Texture bridge (WK21).

Caches Texture handles by pygame Surface id so TileSpriteLibrary / BuildingSpriteLibrary
deduped surfaces map to a single GPU texture.
"""
from __future__ import annotations

from typing import Any, Dict

import pygame
from PIL import Image


class TerrainTextureBridge:
    """Convert pygame surfaces to Ursina textures with stable caching."""

    _cache: Dict[int, Any] = {}

    @classmethod
    def surface_to_texture(cls, surf: pygame.Surface | None):
        """Return an Ursina Texture for this surface, or None if surf is None."""
        if surf is None:
            return None
        sid = id(surf)
        if sid in cls._cache:
            return cls._cache[sid]

        w, h = surf.get_size()
        if w <= 0 or h <= 0:
            return None

        if surf.get_flags() & pygame.SRCALPHA:
            raw = pygame.image.tobytes(surf, "RGBA")
            pil = Image.frombytes("RGBA", (w, h), raw)
        else:
            raw = pygame.image.tobytes(surf, "RGB")
            pil = Image.frombytes("RGB", (w, h), raw).convert("RGBA")

        from ursina import Texture

        # None = nearest-neighbor (pixel art); avoids blurry / "scattered" roads on the terrain sheet.
        tex = Texture(pil, filtering=None)
        cls._cache[sid] = tex
        return tex

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
