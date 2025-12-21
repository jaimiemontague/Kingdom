"""
UI theme primitives for Build A (WK3).

Goal: a small, centralized place for UI sizing + colors so the HUD can be
Majesty-inspired and consistent without a large refactor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import pygame

from config import COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE, COLOR_GOLD


@dataclass(slots=True)
class UITheme:
    # Layout constants (computed in HUD, but these are defaults)
    top_bar_h: int = 48
    bottom_bar_h: int = 96
    right_panel_min_w: int = 320
    right_panel_max_w: int = 420

    # Spacing
    margin: int = 8
    gutter: int = 8

    # Colors
    panel_bg: tuple[int, int, int] = COLOR_UI_BG
    panel_border: tuple[int, int, int] = COLOR_UI_BORDER
    text: tuple[int, int, int] = COLOR_WHITE
    accent: tuple[int, int, int] = COLOR_GOLD

    # Alpha (panel fill)
    panel_alpha: int = 235

    # Fonts (created at init; safe because pygame font module is already initialized by engine)
    # NOTE: Must be declared fields because this dataclass uses slots=True.
    font_title: pygame.font.Font | None = field(init=False, default=None, repr=False, compare=False)
    font_body: pygame.font.Font | None = field(init=False, default=None, repr=False, compare=False)
    font_small: pygame.font.Font | None = field(init=False, default=None, repr=False, compare=False)

    def __post_init__(self):
        self.font_title = pygame.font.Font(None, 24)
        self.font_body = pygame.font.Font(None, 20)
        self.font_small = pygame.font.Font(None, 16)


