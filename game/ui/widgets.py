"""
Tiny UI widgets (Build A skeleton) with caching to avoid per-frame allocations.

Notes:
- These widgets intentionally avoid any input handling beyond hover checks.
- Surfaces are cached per-size/per-text to keep runtime allocations low.
"""

from __future__ import annotations

from dataclasses import dataclass
import pygame


@dataclass
class Panel:
    rect: pygame.Rect
    bg_rgb: tuple[int, int, int]
    border_rgb: tuple[int, int, int]
    alpha: int = 235
    border_w: int = 2

    _cache_surf: pygame.Surface | None = None
    _cache_size: tuple[int, int] = (0, 0)

    def set_rect(self, rect: pygame.Rect):
        self.rect = pygame.Rect(rect)

    def render(self, surface: pygame.Surface):
        w, h = int(self.rect.width), int(self.rect.height)
        if w <= 0 or h <= 0:
            return
        if self._cache_surf is None or self._cache_size != (w, h):
            self._cache_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._cache_size = (w, h)
            self._cache_surf.fill((*self.bg_rgb, int(self.alpha)))
            pygame.draw.rect(self._cache_surf, self.border_rgb, (0, 0, w, h), int(self.border_w))
        surface.blit(self._cache_surf, (int(self.rect.x), int(self.rect.y)))


@dataclass
class Tooltip:
    """Single tooltip surface cached by last text."""

    bg_rgb: tuple[int, int, int]
    border_rgb: tuple[int, int, int]
    alpha: int = 235
    pad: int = 8

    _cache_text: str | None = None
    _cache_surf: pygame.Surface | None = None

    def set_text(self, font: pygame.font.Font, text: str, color: tuple[int, int, int]):
        text = str(text or "")
        if text == self._cache_text and self._cache_surf is not None:
            return
        self._cache_text = text
        if not text:
            self._cache_surf = None
            return
        lines = text.split("\n")
        rendered = [font.render(line, True, color) for line in lines]
        w = max(r.get_width() for r in rendered) + self.pad * 2
        h = sum(r.get_height() for r in rendered) + self.pad * 2
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((*self.bg_rgb, int(self.alpha)))
        pygame.draw.rect(panel, self.border_rgb, (0, 0, w, h), 1)
        y = self.pad
        for r in rendered:
            panel.blit(r, (self.pad, y))
            y += r.get_height()
        self._cache_surf = panel

    def render(self, surface: pygame.Surface, x: int, y: int):
        if self._cache_surf is None:
            return
        surf = self._cache_surf
        w, h = surf.get_width(), surf.get_height()
        # Clamp to screen bounds.
        sx = max(0, min(int(x), surface.get_width() - w))
        sy = max(0, min(int(y), surface.get_height() - h))
        surface.blit(surf, (sx, sy))


@dataclass
class IconButton:
    rect: pygame.Rect
    title: str
    hotkey: str
    tooltip: str

    def hit_test(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


