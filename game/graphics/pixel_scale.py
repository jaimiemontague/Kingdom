"""Nearest-neighbor surface scaling for pixel art (avoids pygame.transform.scale blur)."""

from __future__ import annotations

import pygame


def scale_surface_nearest(src: pygame.Surface, dest_w: int, dest_h: int) -> pygame.Surface:
    """Scale ``src`` to ``dest_w``×``dest_h`` using nearest-neighbor sampling."""
    sw, sh = src.get_width(), src.get_height()
    if dest_w <= 0 or dest_h <= 0:
        raise ValueError("dest dimensions must be positive")
    if sw <= 0 or sh <= 0:
        return pygame.Surface((max(1, dest_w), max(1, dest_h)), pygame.SRCALPHA)
    if sw == dest_w and sh == dest_h:
        return src.copy()
    out = pygame.Surface((dest_w, dest_h), pygame.SRCALPHA)
    for yd in range(dest_h):
        ys = min(sh - 1, (yd * sh) // dest_h)
        for xd in range(dest_w):
            xs = min(sw - 1, (xd * sw) // dest_w)
            out.set_at((xd, yd), src.get_at((xs, ys)))
    return out
