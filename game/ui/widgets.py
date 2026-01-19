"""
Tiny UI widgets (Build A skeleton) with caching to avoid per-frame allocations.

Notes:
- These widgets intentionally avoid any input handling beyond hover checks.
- Surfaces are cached per-size/per-text to keep runtime allocations low.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pygame


_IMAGE_CACHE: dict[tuple[str, tuple[int, int] | None], pygame.Surface] = {}
_NINESLICE_CACHE: dict[tuple[str, int, int, int], pygame.Surface] = {}


def load_image_cached(path: str, size: tuple[int, int] | None = None) -> pygame.Surface | None:
    """Load and optionally scale an image once (cached)."""
    key = (str(path), size)
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        img = pygame.image.load(str(path)).convert_alpha()
        if size is not None and img.get_size() != size:
            img = pygame.transform.scale(img, size)
        _IMAGE_CACHE[key] = img
        return img
    except Exception:
        _IMAGE_CACHE[key] = None  # cache miss to avoid repeated IO
        return None


class NineSlice:
    """Nine-slice renderer with caching (no per-frame scaling)."""

    @staticmethod
    def render(surface: pygame.Surface, rect: pygame.Rect, texture_path: str, border: int = 8) -> bool:
        w, h = int(rect.width), int(rect.height)
        if w <= 0 or h <= 0:
            return False
        key = (str(texture_path), w, h, int(border))
        cached = _NINESLICE_CACHE.get(key)
        if cached is None:
            base = load_image_cached(texture_path)
            if base is None:
                return False
            bw = int(border)
            bw = max(1, min(bw, min(base.get_width(), base.get_height()) // 2))
            dst = pygame.Surface((w, h), pygame.SRCALPHA)

            # Source rects
            sw, sh = base.get_width(), base.get_height()
            s_tl = pygame.Rect(0, 0, bw, bw)
            s_tr = pygame.Rect(sw - bw, 0, bw, bw)
            s_bl = pygame.Rect(0, sh - bw, bw, bw)
            s_br = pygame.Rect(sw - bw, sh - bw, bw, bw)
            s_top = pygame.Rect(bw, 0, sw - 2 * bw, bw)
            s_bot = pygame.Rect(bw, sh - bw, sw - 2 * bw, bw)
            s_left = pygame.Rect(0, bw, bw, sh - 2 * bw)
            s_right = pygame.Rect(sw - bw, bw, bw, sh - 2 * bw)
            s_center = pygame.Rect(bw, bw, sw - 2 * bw, sh - 2 * bw)

            # Dest rects
            d_tl = pygame.Rect(0, 0, bw, bw)
            d_tr = pygame.Rect(w - bw, 0, bw, bw)
            d_bl = pygame.Rect(0, h - bw, bw, bw)
            d_br = pygame.Rect(w - bw, h - bw, bw, bw)
            d_top = pygame.Rect(bw, 0, max(0, w - 2 * bw), bw)
            d_bot = pygame.Rect(bw, h - bw, max(0, w - 2 * bw), bw)
            d_left = pygame.Rect(0, bw, bw, max(0, h - 2 * bw))
            d_right = pygame.Rect(w - bw, bw, bw, max(0, h - 2 * bw))
            d_center = pygame.Rect(bw, bw, max(0, w - 2 * bw), max(0, h - 2 * bw))

            # Blit corners
            dst.blit(base, d_tl, s_tl)
            dst.blit(base, d_tr, s_tr)
            dst.blit(base, d_bl, s_bl)
            dst.blit(base, d_br, s_br)

            # Blit scaled edges + center
            if d_top.width > 0:
                dst.blit(pygame.transform.scale(base.subsurface(s_top), d_top.size), d_top)
            if d_bot.width > 0:
                dst.blit(pygame.transform.scale(base.subsurface(s_bot), d_bot.size), d_bot)
            if d_left.height > 0:
                dst.blit(pygame.transform.scale(base.subsurface(s_left), d_left.size), d_left)
            if d_right.height > 0:
                dst.blit(pygame.transform.scale(base.subsurface(s_right), d_right.size), d_right)
            if d_center.width > 0 and d_center.height > 0:
                dst.blit(pygame.transform.scale(base.subsurface(s_center), d_center.size), d_center)

            _NINESLICE_CACHE[key] = dst
            cached = dst

        surface.blit(cached, (int(rect.x), int(rect.y)))
        return True

@dataclass
class Panel:
    rect: pygame.Rect
    bg_rgb: tuple[int, int, int]
    border_rgb: tuple[int, int, int]
    alpha: int = 235
    border_w: int = 2
    # Optional "game UI" frame language (code-only):
    # - inner border provides the 2-layer frame
    # - highlight draws subtle top/left lighting on the inner frame
    inner_border_rgb: tuple[int, int, int] | None = None
    inner_border_w: int = 1
    highlight_rgb: tuple[int, int, int] | None = None
    highlight_w: int = 1
    texture_path: str | None = None
    slice_border: int = 8

    _cache_surf: pygame.Surface | None = None
    _cache_size: tuple[int, int] = (0, 0)
    _cache_style: tuple | None = None

    def set_rect(self, rect: pygame.Rect):
        self.rect = pygame.Rect(rect)

    def render(self, surface: pygame.Surface):
        w, h = int(self.rect.width), int(self.rect.height)
        if w <= 0 or h <= 0:
            return
        if self.texture_path:
            if NineSlice.render(surface, self.rect, self.texture_path, border=int(self.slice_border)):
                return
        style = (
            int(w),
            int(h),
            tuple(self.bg_rgb),
            tuple(self.border_rgb),
            int(self.alpha),
            int(self.border_w),
            tuple(self.inner_border_rgb) if self.inner_border_rgb is not None else None,
            int(self.inner_border_w),
            tuple(self.highlight_rgb) if self.highlight_rgb is not None else None,
            int(self.highlight_w),
        )
        if self._cache_surf is None or self._cache_size != (w, h) or self._cache_style != style:
            self._cache_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._cache_size = (w, h)
            self._cache_style = style
            self._cache_surf.fill((*self.bg_rgb, int(self.alpha)))
            # Outer frame
            pygame.draw.rect(self._cache_surf, self.border_rgb, (0, 0, w, h), int(self.border_w))

            # Inner frame (2-layer border) + subtle top-left lighting highlight
            if self.inner_border_rgb is not None and int(self.inner_border_w) > 0:
                inset = int(self.border_w)
                iw = max(0, w - inset * 2)
                ih = max(0, h - inset * 2)
                if iw > 0 and ih > 0:
                    inner_rect = pygame.Rect(inset, inset, iw, ih)
                    pygame.draw.rect(self._cache_surf, self.inner_border_rgb, inner_rect, int(self.inner_border_w))

                    if self.highlight_rgb is not None and int(self.highlight_w) > 0:
                        hw = int(self.highlight_w)
                        # Top edge highlight (light direction: top-left)
                        pygame.draw.line(
                            self._cache_surf,
                            self.highlight_rgb,
                            (inner_rect.left + 1, inner_rect.top + 1),
                            (inner_rect.right - 2, inner_rect.top + 1),
                            hw,
                        )
                        # Left edge highlight
                        pygame.draw.line(
                            self._cache_surf,
                            self.highlight_rgb,
                            (inner_rect.left + 1, inner_rect.top + 1),
                            (inner_rect.left + 1, inner_rect.bottom - 2),
                            hw,
                        )
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


@dataclass
class ModalPanel:
    """Centered modal panel with backdrop (semi-transparent overlay)."""
    screen_width: int
    screen_height: int
    panel_width: int = 500
    panel_height: int = 600
    bg_rgb: tuple[int, int, int] = (40, 40, 50)
    border_rgb: tuple[int, int, int] = (100, 100, 120)
    backdrop_alpha: int = 180  # Semi-transparent backdrop
    texture_path: str | None = None
    slice_border: int = 8
    
    _backdrop_cache: pygame.Surface | None = None
    
    def get_panel_rect(self) -> pygame.Rect:
        """Get centered panel rectangle."""
        x = (self.screen_width - self.panel_width) // 2
        y = (self.screen_height - self.panel_height) // 2
        return pygame.Rect(x, y, self.panel_width, self.panel_height)
    
    def render_backdrop(self, surface: pygame.Surface):
        """Render semi-transparent backdrop covering entire screen."""
        if self._backdrop_cache is None or self._backdrop_cache.get_size() != (self.screen_width, self.screen_height):
            self._backdrop_cache = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
            self._backdrop_cache.fill((0, 0, 0, self.backdrop_alpha))
        surface.blit(self._backdrop_cache, (0, 0))
    
    def render_panel(self, surface: pygame.Surface):
        """Render the modal panel itself."""
        panel_rect = self.get_panel_rect()
        panel = Panel(
            rect=panel_rect,
            bg_rgb=self.bg_rgb,
            border_rgb=self.border_rgb,
            alpha=255,
            border_w=2,
            inner_border_rgb=(60, 60, 70),
            inner_border_w=1,
            highlight_rgb=(120, 120, 140),
            highlight_w=1,
            texture_path=self.texture_path,
            slice_border=int(self.slice_border),
        )
        panel.render(surface)


@dataclass
class Slider:
    """Horizontal slider widget for volume/values (0.0 to 1.0)."""
    rect: pygame.Rect
    value: float = 0.5  # 0.0 to 1.0
    track_color: tuple[int, int, int] = (60, 60, 70)
    fill_color: tuple[int, int, int] = (100, 150, 200)
    thumb_color: tuple[int, int, int] = (150, 200, 255)
    thumb_size: int = 12
    
    def set_value(self, value: float):
        """Set value clamped to 0.0-1.0."""
        self.value = max(0.0, min(1.0, float(value)))
    
    def hit_test_thumb(self, pos: tuple[int, int]) -> bool:
        """Check if position hits the thumb."""
        thumb_x = int(self.rect.x + self.value * (self.rect.width - self.thumb_size))
        thumb_rect = pygame.Rect(thumb_x, self.rect.y, self.thumb_size, self.rect.height)
        return thumb_rect.collidepoint(pos)
    
    def set_value_from_x(self, x: int):
        """Set value from screen X coordinate."""
        rel_x = x - self.rect.x
        self.value = max(0.0, min(1.0, rel_x / max(1, self.rect.width)))
    
    def render(self, surface: pygame.Surface):
        """Render slider track, fill, and thumb."""
        # Track (background)
        pygame.draw.rect(surface, self.track_color, self.rect)
        
        # Fill (left portion)
        fill_width = int(self.value * self.rect.width)
        if fill_width > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            pygame.draw.rect(surface, self.fill_color, fill_rect)
        
        # Thumb
        thumb_x = int(self.rect.x + self.value * (self.rect.width - self.thumb_size))
        thumb_rect = pygame.Rect(thumb_x, self.rect.y, self.thumb_size, self.rect.height)
        pygame.draw.rect(surface, self.thumb_color, thumb_rect)
        pygame.draw.rect(surface, (200, 200, 220), thumb_rect, 1)


@dataclass
class RadioGroup:
    """Radio button group for mutually exclusive options."""
    options: list[tuple[str, str]]  # [(label, value), ...]
    selected_value: str | None = None
    option_height: int = 32
    spacing: int = 8
    
    def get_option_rect(self, index: int, x: int, y: int, width: int) -> pygame.Rect:
        """Get rectangle for option at index."""
        return pygame.Rect(x, y + index * (self.option_height + self.spacing), width, self.option_height)
    
    def hit_test(self, pos: tuple[int, int], x: int, y: int, width: int) -> str | None:
        """Return selected value if position hits an option."""
        for i, (label, value) in enumerate(self.options):
            rect = self.get_option_rect(i, x, y, width)
            if rect.collidepoint(pos):
                return value
        return None
    
    def render(self, surface: pygame.Surface, font: pygame.font.Font, x: int, y: int, width: int, 
               text_color: tuple[int, int, int] = (255, 255, 255),
               selected_color: tuple[int, int, int] = (100, 150, 200),
               bg_color: tuple[int, int, int] = (50, 50, 60)):
        """Render radio group options."""
        for i, (label, value) in enumerate(self.options):
            rect = self.get_option_rect(i, x, y, width)
            is_selected = (value == self.selected_value)
            
            # Background
            if is_selected:
                pygame.draw.rect(surface, selected_color, rect)
            else:
                pygame.draw.rect(surface, bg_color, rect)
            
            # Border
            border_color = selected_color if is_selected else (100, 100, 120)
            pygame.draw.rect(surface, border_color, rect, 2)
            
            # Radio indicator (circle)
            radio_x = rect.x + 12
            radio_y = rect.y + rect.height // 2
            radio_r = 6
            pygame.draw.circle(surface, text_color, (radio_x, radio_y), radio_r, 2)
            if is_selected:
                pygame.draw.circle(surface, text_color, (radio_x, radio_y), 3)
            
            # Label text
            text_surf = font.render(label, True, text_color)
            text_x = rect.x + 28
            text_y = rect.y + (rect.height - text_surf.get_height()) // 2
            surface.blit(text_surf, (text_x, text_y))



