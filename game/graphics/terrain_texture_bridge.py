"""
Pygame Surface → Ursina Texture bridge (WK21).

Caches Texture handles by pygame Surface id so TileSpriteLibrary / BuildingSpriteLibrary
deduped surfaces map to a single GPU texture.
"""
from __future__ import annotations

from typing import Any, Dict, Hashable

import pygame
from PIL import Image


class TerrainTextureBridge:
    """Convert pygame surfaces to Ursina textures with stable caching."""

    # Keys must never collide across unrelated surfaces. Using only id(surface) is unsafe:
    # the terrain bake's sheet is dropped after upload; Python may reuse that id for the fog
    # surface, causing refresh_surface_texture to overwrite the terrain GPU texture (WK22 R2).
    _cache: Dict[Hashable, Any] = {}

    @classmethod
    def surface_to_texture(cls, surf: pygame.Surface | None, *, cache_key: Hashable | None = None):
        """Return an Ursina Texture for this surface, or None if surf is None."""
        if surf is None:
            return None
        key: Hashable = cache_key if cache_key is not None else id(surf)
        if key in cls._cache:
            return cls._cache[key]

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
        cls._cache[key] = tex
        return tex

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()

    @classmethod
    def refresh_surface_texture(cls, surf: pygame.Surface, *, cache_key: Hashable):
        """
        Re-upload pixel data for a logical texture slot (stable key, not id(surface)).

        Used for dynamic overlays (e.g. fog) where the pygame Surface is mutated in place.
        """
        if surf is None:
            return None
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

        existing = cls._cache.get(cache_key)
        if existing is None:
            tex = Texture(pil, filtering=None)
            cls._cache[cache_key] = tex
            return tex

        existing._cached_image = pil
        existing.apply()
        return existing
