"""Enemy info panel renderer for the left column (WK61-FEAT-006)."""

from __future__ import annotations

import pygame

from config import COLOR_RED, COLOR_WHITE
from game.ui.widgets import HPBar, TextLabel


def _camel_to_display(name: str) -> str:
    """Format 'SkeletonArcher' as 'Skeleton Archer'."""
    out: list[str] = []
    for i, c in enumerate(name):
        if c.isupper() and i > 0:
            out.append(" ")
        out.append(c)
    return "".join(out).strip()


class EnemyPanel:
    """Render enemy information in the left column (224px)."""

    def __init__(
        self,
        theme,
        *,
        frame_inner: tuple[int, int, int],
        frame_highlight: tuple[int, int, int],
    ) -> None:
        self.theme = theme
        self._frame_inner = frame_inner
        self._frame_highlight = frame_highlight

    def _draw_section_divider(self, surface: pygame.Surface, x: int, y: int, width: int) -> None:
        if width <= 0:
            return
        pygame.draw.line(surface, self._frame_inner, (x, y), (x + width, y), 1)
        pygame.draw.line(surface, self._frame_highlight, (x, y + 1), (x + width, y + 1), 1)

    def render(
        self,
        surface: pygame.Surface,
        enemy,
        rect: pygame.Rect,
    ) -> None:
        """Render enemy info panel in the given rect."""
        panel_width = int(rect.width)
        panel_x = int(rect.x)
        panel_y = int(rect.y)
        pad = int(self.theme.margin)
        y = panel_y + pad
        bar_width = panel_width - (pad * 2)

        line_skip_sm = self.theme.font_small.get_height()

        # Header bar
        header_h = 28
        header_rect = pygame.Rect(panel_x + 6, panel_y + pad - 4, panel_width - 12, header_h)
        pygame.draw.rect(surface, (45, 30, 30), header_rect)
        pygame.draw.rect(surface, self._frame_inner, header_rect, 1)
        pygame.draw.line(
            surface,
            self._frame_highlight,
            (header_rect.left + 1, header_rect.top + 1),
            (header_rect.right - 2, header_rect.top + 1),
            1,
        )

        # Enemy type name
        enemy_name = getattr(enemy, "enemy_type", "") or enemy.__class__.__name__
        display_name = _camel_to_display(enemy_name).title()
        TextLabel.render(
            surface,
            self.theme.font_title,
            display_name,
            (panel_x + pad, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            (220, 80, 80),
            shadow_color=(20, 10, 10),
        )
        y = header_rect.bottom + 6

        # HP section
        hp_v = int(getattr(enemy, "hp", 0) or 0)
        max_hp_v = max(1, int(getattr(enemy, "max_hp", 1) or 1))
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"HP: {hp_v}/{max_hp_v}",
            (panel_x + pad, y),
            COLOR_WHITE,
            shadow_color=(25, 25, 35),
        )
        y += line_skip_sm + 4

        hp_bar_rect = pygame.Rect(panel_x + pad, y, bar_width, 8)
        HPBar.render(
            surface,
            hp_bar_rect,
            hp_v,
            max_hp_v,
            color_scheme={
                "bg": (60, 30, 30),
                "good": (220, 50, 50),
                "warn": (220, 50, 50),
                "bad": (220, 50, 50),
                "border": (20, 10, 10),
            },
        )
        y += hp_bar_rect.height + 8

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6

        # Combat stats
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Combat",
            (panel_x + pad, y),
            (180, 150, 150),
            shadow_color=(20, 20, 30),
        )
        y += line_skip_sm + 4

        atk = int(getattr(enemy, "attack_power", getattr(enemy, "base_attack", 0)) or 0)
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Attack: {atk}",
            (panel_x + pad, y),
            (255, 200, 200),
            shadow_color=(25, 25, 35),
        )
        y += 14

        speed = getattr(enemy, "speed", "?")
        try:
            speed_display = f"{float(speed):.0f}"
        except (TypeError, ValueError):
            speed_display = str(speed)
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Speed: {speed_display}",
            (panel_x + pad, y),
            (200, 200, 255),
            shadow_color=(25, 25, 35),
        )
        y += 14

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6

        # State
        state = getattr(enemy, "state", None)
        state_name = getattr(state, "name", str(state) if state else "IDLE") or "IDLE"
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"State: {state_name.replace('_', ' ').title()}",
            (panel_x + pad, y),
            (200, 200, 200),
            shadow_color=(25, 25, 35),
        )
        y += 14

        # Current target
        target = getattr(enemy, "target", None)
        if target is not None:
            target_name = (
                getattr(target, "name", None)
                or getattr(target, "building_type", None)
                or target.__class__.__name__
            )
            target_name = str(target_name).replace("_", " ").title()
            TextLabel.render(
                surface,
                self.theme.font_small,
                f"Target: {target_name}",
                (panel_x + pad, y),
                (255, 180, 100),
                shadow_color=(25, 25, 35),
            )
        else:
            TextLabel.render(
                surface,
                self.theme.font_small,
                "Target: Wandering",
                (panel_x + pad, y),
                (150, 150, 150),
                shadow_color=(25, 25, 35),
            )
