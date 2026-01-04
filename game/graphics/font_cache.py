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










