"""
Quest/travelogue right-panel placeholder (wk14 Persona and Presence).

Renders when MicroViewManager is in QUEST mode. Architecture only — no quest content.
Shows hero portrait + name, "Questing..." label, placeholder text, "Recall Hero" button.
"""

from __future__ import annotations

from typing import Any

import pygame

from game.ui.theme import UITheme
from game.ui.widgets import Button, TextLabel


# Class accent colors for hero portrait circle (match hero panel / building panel)
_CLASS_COLORS = {
    "warrior": (70, 130, 180),
    "ranger": (50, 160, 80),
    "rogue": (128, 128, 140),
    "wizard": (140, 90, 180),
}


class QuestViewPanel:
    """
    Right-panel placeholder for remote quest view.
    Future content plugs into this shell.
    """

    def __init__(self, theme: UITheme) -> None:
        self.theme = theme
        self._recall_btn = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="Recall Hero",
            font=theme.font_small,
            enabled=True,
        )
        self._recall_rect: pygame.Rect | None = None

    def render(
        self,
        surface: pygame.Surface,
        right_rect: pygame.Rect,
        game_state: dict[str, Any],
    ) -> None:
        hero = game_state.get("micro_view_quest_hero")
        quest_data = game_state.get("micro_view_quest_data") or {}
        pad = int(getattr(self.theme, "margin", 10))
        x, y = right_rect.x + pad, right_rect.y + pad

        if hero is None:
            TextLabel.render(
                surface,
                self.theme.font_body,
                "No hero on quest.",
                (x, y),
                (180, 180, 180),
            )
            return

        name = getattr(hero, "name", "Hero")
        hero_class = str(getattr(hero, "hero_class", "warrior")).lower()
        color = _CLASS_COLORS.get(hero_class, (120, 120, 120))

        # Portrait: class-colored circle
        r = 24
        pygame.draw.circle(surface, color, (x + r, y + r), r)
        pygame.draw.circle(surface, (40, 40, 50), (x + r, y + r), r, 2)
        x += r * 2 + pad

        # Name + "Questing..."
        TextLabel.render(surface, self.theme.font_body, name, (x, y), (255, 255, 255))
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Questing...",
            (x, y + 26),
            (180, 200, 180),
        )

        # Placeholder travelogue area
        y += 60
        travelogue_rect = pygame.Rect(
            right_rect.x + pad,
            y,
            right_rect.width - 2 * pad,
            max(120, right_rect.height - 180),
        )
        if travelogue_rect.width > 0 and travelogue_rect.height > 0:
            pygame.draw.rect(surface, (35, 38, 45), travelogue_rect)
            pygame.draw.rect(surface, (70, 70, 90), travelogue_rect, 1)
            TextLabel.render(
                surface,
                self.theme.font_small,
                "Travelogue (future content)",
                (travelogue_rect.x + 8, travelogue_rect.y + 8),
                (140, 140, 150),
            )
            if quest_data:
                beat = quest_data.get("current_beat", "Preparing for the journey...")
                TextLabel.render(
                    surface,
                    self.theme.font_small,
                    beat[:60] + ("..." if len(beat) > 60 else ""),
                    (travelogue_rect.x + 8, travelogue_rect.y + 28),
                    (200, 200, 210),
                )

        # Recall Hero button at bottom
        btn_h = 32
        btn_y = right_rect.bottom - pad - btn_h
        self._recall_btn.rect = pygame.Rect(
            right_rect.x + pad,
            btn_y,
            right_rect.width - 2 * pad,
            btn_h,
        )
        self._recall_rect = self._recall_btn.rect.copy()
        self._recall_btn.render(surface, pygame.mouse.get_pos())

    def handle_click(self, mouse_pos: tuple[int, int], right_rect: pygame.Rect) -> str | None:
        if self._recall_rect is not None and self._recall_rect.collidepoint(mouse_pos):
            return "exit_quest"
        return None
