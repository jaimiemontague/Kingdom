"""
Quest/travelogue right-panel placeholder (wk14 Persona and Presence).

Renders when MicroViewManager is in QUEST mode. Architecture only — no quest content.
Shows hero portrait + name, "Questing..." label, placeholder text, "Recall Hero" button.

WK126-T9 (WK133, Agent 08): extended with an ACTIVE-QUEST readout
(:meth:`QuestViewPanel.render_active_quests`) listing the Herald's Post quests
(type, target, reward, open/accepted-by status, n/m progress for slay). The
wk14 ViewMode.QUEST right-column path has been dormant since the WK130 sidebar
overhaul removed the right column, so the live surface for this board is the
quest-create modal (``game/ui/quest_create_panel.py``), which embeds it; this
panel's own render() also shows it so the QUEST view is correct if re-wired.
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
    "cleric": (48, 186, 178),
}


# Display labels for the four WK126 quest types.
_QUEST_TYPE_LABELS = {
    "raid_lair": "Raid Lair",
    "slay_enemy_type": "Slay Enemies",
    "find_poi": "Find POI",
    "explore_far": "Explore Far",
}


def _truncate(text: str, max_px: int, font: Any) -> str:
    """Trim ``text`` to fit ``max_px`` with an ellipsis (narrow-column safe)."""
    s = str(text or "")
    if max_px <= 0 or font.size(s)[0] <= max_px:
        return s
    while s and font.size(s + "…")[0] > max_px:
        s = s[:-1]
    return s + "…"


def quest_target_label(quest: Any) -> str:
    """Short human label for a quest's target (shared with the create modal)."""
    qtype = str(getattr(quest, "quest_type", "") or "")
    target = getattr(quest, "target", None)
    if qtype == "slay_enemy_type":
        count = int(getattr(quest, "count", 1) or 1)
        return f"{count}x {str(target or 'enemy').replace('_', ' ')}"
    if qtype == "explore_far" and isinstance(target, (tuple, list)) and len(target) == 2:
        return f"tile ({int(target[0])},{int(target[1])})"
    # raid_lair / find_poi → the target building's name.
    pd = getattr(target, "poi_def", None)
    name = str(getattr(pd, "display_name", "") or "")
    if not name:
        name = str(getattr(target, "building_type", "") or "target").replace("_", " ").title()
    return name


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
            # WK126: still show the active-quest board below.
            board_rect = pygame.Rect(
                right_rect.x + pad,
                y + 28,
                right_rect.width - 2 * pad,
                max(0, right_rect.bottom - (y + 28) - pad),
            )
            self.render_active_quests(surface, board_rect, game_state)
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

        # Placeholder travelogue area (WK126: now hosts the active-quest board)
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
            if quest_data:
                beat = quest_data.get("current_beat", "Preparing for the journey...")
                TextLabel.render(
                    surface,
                    self.theme.font_small,
                    beat[:60] + ("..." if len(beat) > 60 else ""),
                    (travelogue_rect.x + 8, travelogue_rect.y + 8),
                    (200, 200, 210),
                )
            board_rect = pygame.Rect(
                travelogue_rect.x + 8,
                travelogue_rect.y + (28 if quest_data else 8),
                travelogue_rect.width - 16,
                travelogue_rect.height - (36 if quest_data else 16),
            )
            self.render_active_quests(surface, board_rect, game_state)

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

    # ------------------------------------------------------------------
    # WK126: active-quest readout (type, target, reward, status, progress)
    # ------------------------------------------------------------------
    @staticmethod
    def _active_quests_from(game_state: dict[str, Any]) -> list[Any]:
        sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        qs = getattr(sim, "quest_system", None)
        getter = getattr(qs, "get_active_quests", None)
        if not callable(getter):
            return []
        try:
            return list(getter())
        except Exception:
            return []

    def render_active_quests(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        game_state: dict[str, Any],
    ) -> list[str]:
        """Render the active-quest list into ``rect``.

        Two lines per quest: "<Type> — <target>" then "$<reward> — <status>"
        (status = Open, or the accepting hero + n/m progress for slay quests).
        Returns the rendered line strings (handy for headless assertions).
        """
        lines: list[str] = []
        if rect.width <= 0 or rect.height <= 0:
            return lines
        font = self.theme.font_small
        x, y = rect.x, rect.y
        bottom = rect.bottom

        TextLabel.render(surface, self.theme.font_body, "Active Quests", (x, y), (220, 200, 130))
        y += self.theme.font_body.get_height() + 4

        quests = self._active_quests_from(game_state)
        if not quests:
            msg = "No active quests."
            TextLabel.render(surface, font, msg, (x, y), (150, 150, 160))
            lines.append(msg)
            return lines

        row_h = font.get_height() + 2
        for quest in quests:
            if y + row_h * 2 + 6 > bottom:
                more = f"... +{len(quests) - len(lines) // 2} more"
                if y + row_h <= bottom:
                    TextLabel.render(surface, font, more, (x, y), (150, 150, 160))
                break
            qtype = str(getattr(quest, "quest_type", "") or "")
            type_label = _QUEST_TYPE_LABELS.get(qtype, qtype.replace("_", " ").title())
            line1 = f"{type_label} — {quest_target_label(quest)}"
            if getattr(quest, "is_open", False):
                status = "Open"
            else:
                who = str(getattr(quest, "accepted_by_name", "") or "Hero")
                status = f"Accepted: {who}"
                if qtype == "slay_enemy_type":
                    status += f" ({int(getattr(quest, 'progress', 0))}/{int(getattr(quest, 'count', 1))})"
            line2 = f"${int(getattr(quest, 'reward', 0))} — {status}"
            TextLabel.render(surface, font, _truncate(line1, rect.width, font), (x, y), (230, 230, 240))
            y += row_h
            TextLabel.render(surface, font, _truncate(line2, rect.width - 10, font), (x + 10, y), (180, 195, 180))
            y += row_h + 6
            lines.extend([line1, line2])
        return lines

    def handle_click(self, mouse_pos: tuple[int, int], right_rect: pygame.Rect) -> str | None:
        if self._recall_rect is not None and self._recall_rect.collidepoint(mouse_pos):
            return "exit_quest"
        return None
