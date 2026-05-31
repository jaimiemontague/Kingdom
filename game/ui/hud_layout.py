"""Pure-geometry HUD layout computation extracted from game.ui.hud.

HUDLayout holds the computed rectangles for all major HUD regions.
HUDLayoutManager computes a HUDLayout from screen dimensions and game state
without touching rendering, hit testing, or action routing.

Introduced in wk62 architecture cleanup (Agent 08).
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

# Re-export the layout constants so both hud.py and external callers can use them.
# These are authoritative; hud.py should import from here.

LEFT_COL_W = 224
RADAR_MINIMAP_H = 180
RADAR_MINIMAP_W = LEFT_COL_W
RECALL_BTN_W = 180
MEMORIAL_BTN_W = 90
# Left-column main-panel minimum height (relocated from hud.py in WK98; hud.py re-imports+re-exports it).
HERO_LEFT_MIN_H = 80


@dataclass(slots=True)
class HUDLayout:
    """Computed screen-space rectangles for major HUD regions.

    All values are pygame.Rect instances in screen (surface) coordinates.
    """

    top_bar: pygame.Rect
    bottom_bar: pygame.Rect
    left_panel: pygame.Rect
    right_panel: pygame.Rect
    minimap: pygame.Rect
    command_bar: pygame.Rect
    speed_control: pygame.Rect
    recall_button: pygame.Rect
    memorial_button: pygame.Rect


class HUDLayoutManager:
    """Computes HUDLayout from screen dimensions and theme values.

    This class holds no rendering state. It only does geometry.
    """

    def compute(
        self,
        screen_w: int,
        screen_h: int,
        *,
        top_bar_h: int = 48,
        bottom_bar_h: int = 96,
        margin: int = 8,
        gutter: int = 8,
    ) -> HUDLayout:
        """Compute layout rectangles from screen dimensions and theme metrics.

        Parameters
        ----------
        screen_w, screen_h:
            Current surface / framebuffer size.
        top_bar_h, bottom_bar_h, margin, gutter:
            Theme-derived spacing values.

        Returns
        -------
        HUDLayout with all rectangles populated.
        """
        # Right panel is retired (WK52 R4) -- width is always 0.
        right_w = 0

        top = pygame.Rect(0, 0, screen_w, top_bar_h)
        bottom = pygame.Rect(0, screen_h - bottom_bar_h, screen_w, bottom_bar_h)
        right = pygame.Rect(
            screen_w - right_w,
            top_bar_h,
            right_w,
            max(0, screen_h - top_bar_h - bottom_bar_h),
        )

        minimap = pygame.Rect(
            0,
            screen_h - int(RADAR_MINIMAP_H),
            int(RADAR_MINIMAP_W),
            int(RADAR_MINIMAP_H),
        )

        # Left panel spans from top bar to minimap top (actual content allocation
        # is handled by the left-column segment logic inside HUD, which depends on
        # game state like selected hero/building).  We expose the full available
        # rectangle here; HUD subdivides it.
        left = pygame.Rect(
            0,
            top_bar_h,
            LEFT_COL_W,
            max(0, minimap.y - top_bar_h),
        )

        # Speed control bar
        speed_bar_w = 200
        speed_bar_h = 50
        speed_gap_above_bar = 4
        speed_rect = pygame.Rect(
            screen_w - speed_bar_w - margin - 100,
            bottom.y - speed_bar_h - speed_gap_above_bar,
            speed_bar_w,
            speed_bar_h,
        )

        # Bottom-bar button row
        btn_h = max(32, bottom_bar_h - 2 * margin)
        btn_y = bottom.y + margin

        recall = pygame.Rect(minimap.right + gutter, btn_y, RECALL_BTN_W, btn_h)
        memorial = pygame.Rect(recall.right + gutter, btn_y, MEMORIAL_BTN_W, btn_h)

        cmd_x = memorial.right + gutter
        cmd_w = max(0, speed_rect.left - cmd_x - gutter)
        command = pygame.Rect(cmd_x, btn_y, cmd_w, btn_h)

        return HUDLayout(
            top_bar=top,
            bottom_bar=bottom,
            left_panel=left,
            right_panel=right,
            minimap=minimap,
            command_bar=command,
            speed_control=speed_rect,
            recall_button=recall,
            memorial_button=memorial,
        )
