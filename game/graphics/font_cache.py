"""
Lightweight pygame font cache.

Creating pygame.font.Font objects inside per-frame render loops is expensive and can
cause stutter/lag. This module provides lazy, global caches for fonts (by size) and
optionally for static text surfaces (by size/text/color).
"""

from __future__ import annotations

from typing import Dict, Tuple

import pygame

_FONT_CACHE: Dict[int, pygame.font.Font] = {}
_TEXT_CACHE: Dict[Tuple[int, str, Tuple[int, int, int]], pygame.Surface] = {}
_TEXT_SHADOW_CACHE: Dict[
    Tuple[int, str, Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int]],
    pygame.Surface,
] = {}
_TEXT_SHADOW_CACHE_MAX = 512


def get_font(size: int) -> pygame.font.Font:
    """Get (and cache) the default font at a given size. Safe to call after pygame.font.init()."""
    s = int(size)
    font = _FONT_CACHE.get(s)
    if font is None:
        font = pygame.font.Font(None, s)
        _FONT_CACHE[s] = font
    return font


def render_text_cached(
    size: int,
    text: str,
    color: Tuple[int, int, int],
    antialias: bool = True,
) -> pygame.Surface:
    """
    Render and cache text surfaces for static labels/icons.

    Avoid using this for rapidly-changing text (e.g. timers) as that would grow the cache.
    """
    key = (int(size), str(text), (int(color[0]), int(color[1]), int(color[2])))
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        surf = get_font(size).render(text, bool(antialias), color)
        _TEXT_CACHE[key] = surf
    return surf


def render_text_shadowed_cached(
    size: int,
    text: str,
    color: Tuple[int, int, int],
    *,
    shadow_color: Tuple[int, int, int] = (0, 0, 0),
    shadow_offset: Tuple[int, int] = (1, 1),
    antialias: bool = True,
) -> pygame.Surface:
    """
    Render a cached, shadowed text surface.

    This is intended for world-space labels where background contrast varies.
    Cache key includes the shadow styling so we avoid per-frame surface allocations.
    """
    key = (
        int(size),
        str(text),
        (int(color[0]), int(color[1]), int(color[2])),
        (int(shadow_color[0]), int(shadow_color[1]), int(shadow_color[2])),
        (int(shadow_offset[0]), int(shadow_offset[1])),
    )
    surf = _TEXT_SHADOW_CACHE.get(key)
    if surf is None:
        # Best-effort cache bound (avoid unbounded growth for frequently-changing numeric labels).
        if len(_TEXT_SHADOW_CACHE) >= _TEXT_SHADOW_CACHE_MAX:
            try:
                _TEXT_SHADOW_CACHE.pop(next(iter(_TEXT_SHADOW_CACHE)))
            except Exception:
                _TEXT_SHADOW_CACHE.clear()
        font = get_font(size)
        main = font.render(str(text), bool(antialias), color)
        shadow = font.render(str(text), bool(antialias), shadow_color)
        ox, oy = int(shadow_offset[0]), int(shadow_offset[1])
        pad_x = max(0, ox)
        pad_y = max(0, oy)
        w = int(main.get_width() + pad_x)
        h = int(main.get_height() + pad_y)
        surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        if pad_x or pad_y:
            surf.blit(shadow, (pad_x, pad_y))
        else:
            # Offset (0,0): still render shadow first for slight darkening.
            surf.blit(shadow, (0, 0))
        surf.blit(main, (0, 0))
        _TEXT_SHADOW_CACHE[key] = surf
    return surf










