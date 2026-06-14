"""
Quest/travelogue right-panel placeholder (wk14 Persona and Presence).

Renders when MicroViewManager is in QUEST mode. Architecture only - no quest content.
Shows hero portrait + name, "Questing..." label, placeholder text, "Recall Hero" button.

WK126-T9 (WK133, Agent 08): extended with an ACTIVE-QUEST readout
(:meth:`QuestViewPanel.render_active_quests`) listing the Herald's Post quests
(type, target, reward, open/accepted-by status, n/m progress for slay). The
wk14 ViewMode.QUEST right-column path has been dormant since the WK130 sidebar
overhaul removed the right column, so the live surface for this board is the
quest-create modal (``game/ui/quest_create_panel.py``), which embeds it; this
panel's own render() also shows it so the QUEST view is correct if re-wired.

WK138: the same board now also renders active multi-phase quest chains as a
compact "Adventure Ledger" card with current objective, assigned hero, reward,
status, and a completed/current/upcoming timeline.
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

_CHAIN_STATUS_LABELS = {
    "offered": "Offered",
    "active": "Active",
    "completed": "Completed",
    "failed": "Failed",
}

_PHASE_STATUS_LABELS = {
    "offered": "OFFERED",
    "active": "NOW",
    "completed": "DONE",
    "upcoming": "NEXT",
    "failed": "FAIL",
}

_PHASE_STATUS_COLORS = {
    "offered": (180, 180, 170),
    "active": (220, 190, 90),
    "completed": (110, 200, 110),
    "upcoming": (160, 160, 170),
    "failed": (230, 120, 120),
}


def _truncate(text: str, max_px: int, font: Any) -> str:
    """Trim ``text`` to fit ``max_px`` with an ellipsis (narrow-column safe)."""
    s = str(text or "")
    if max_px <= 0 or font.size(s)[0] <= max_px:
        return s
    while s and font.size(s + "...")[0] > max_px:
        s = s[:-1]
    return s + "..."


def quest_target_label(quest: Any) -> str:
    """Short human label for a quest's target (shared with the create modal)."""
    qtype = str(getattr(quest, "quest_type", "") or "")
    target = getattr(quest, "target", None)
    if qtype == "slay_enemy_type":
        count = int(getattr(quest, "count", 1) or 1)
        return f"{count}x {str(target or 'enemy').replace('_', ' ')}"
    if qtype == "explore_far" and isinstance(target, (tuple, list)) and len(target) == 2:
        return f"tile ({int(target[0])},{int(target[1])})"
    # raid_lair / find_poi -> the target building's name.
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
    # WK126 / WK138: active-quest readout (type, target, reward, status, progress)
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

    @staticmethod
    def _active_chain_snapshots_from(game_state: dict[str, Any]) -> list[Any]:
        if "quest_chains" in game_state and game_state.get("quest_chains") is not None:
            try:
                return list(game_state.get("quest_chains") or [])
            except TypeError:
                return [game_state["quest_chains"]]
        sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        chain_system = getattr(sim, "quest_chain_system", None)
        if chain_system is None:
            return []
        for getter_name in ("get_active_chain_snapshots", "get_active_chain_views", "get_active_chains"):
            getter = getattr(chain_system, getter_name, None)
            if not callable(getter):
                continue
            try:
                chains = getter()
            except Exception:
                return []
            try:
                return list(chains or [])
            except TypeError:
                return [chains]
        return []

    @staticmethod
    def _hero_name_from_id(game_state: dict[str, Any], hero_id: str | None) -> str:
        if not hero_id:
            return ""
        sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        heroes = game_state.get("heroes") or getattr(sim, "heroes", ()) or ()
        for hero in heroes:
            if str(getattr(hero, "hero_id", "") or "") != str(hero_id):
                continue
            name = str(getattr(hero, "name", "") or "").strip()
            if name:
                return name
        return ""

    @staticmethod
    def _chain_reward_gold(game_state: dict[str, Any], chain: Any) -> int:
        reward = getattr(chain, "reward_gold", None)
        if reward is not None:
            try:
                return int(reward)
            except Exception:
                pass
        sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        chain_system = getattr(sim, "quest_chain_system", None)
        if chain_system is not None:
            getter = getattr(chain_system, "get_chain", None)
            if callable(getter):
                try:
                    live_chain = getter(getattr(chain, "chain_id", None))
                except Exception:
                    live_chain = None
                if live_chain is not None:
                    live_reward = getattr(live_chain, "reward_gold", None)
                    if live_reward is not None:
                        try:
                            return int(live_reward)
                        except Exception:
                            pass
            definition_getter = getattr(chain_system, "get_definition", None)
            if callable(definition_getter):
                try:
                    definition = definition_getter(str(getattr(chain, "chain_type", "") or ""))
                    return int(getattr(getattr(definition, "reward_profile", None), "gold", 0) or 0)
                except Exception:
                    pass
        return 0

    @staticmethod
    def _chain_current_phase(chain: Any) -> tuple[Any | None, int]:
        phases = tuple(getattr(chain, "phases", ()) or ())
        if not phases:
            return None, 0
        for idx, phase in enumerate(phases):
            if str(getattr(phase, "status", "") or "") == "active":
                return phase, idx
        chain_status = str(getattr(chain, "status", "") or "")
        if chain_status == "offered":
            return phases[0], 0
        if chain_status == "completed":
            for idx in range(len(phases) - 1, -1, -1):
                if str(getattr(phases[idx], "status", "") or "") == "completed":
                    return phases[idx], idx
            return phases[-1], len(phases) - 1
        if chain_status == "failed":
            for idx in range(len(phases) - 1, -1, -1):
                if str(getattr(phases[idx], "status", "") or "") == "failed":
                    return phases[idx], idx
            for idx in range(len(phases) - 1, -1, -1):
                if str(getattr(phases[idx], "status", "") or "") in {"completed", "offered"}:
                    return phases[idx], idx
            return phases[0], 0
        return phases[0], 0

    def _render_active_chain_section(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        game_state: dict[str, Any],
    ) -> tuple[list[str], int]:
        chains = self._active_chain_snapshots_from(game_state)
        if not chains:
            return [], rect.y

        lines: list[str] = []
        x = int(rect.x)
        y = int(rect.y)
        bottom = int(rect.bottom)
        title_font = self.theme.font_body
        body_font = self.theme.font_small
        title_h = title_font.get_height()
        body_h = body_font.get_height()
        pad_x = 8
        pad_y = 6
        gap = 4

        board_title = "Adventure Ledger"

        if rect.height < 140:
            chain = chains[0]
            phase_rows = tuple(getattr(chain, "phases", ()) or ())
            current_phase, current_index = self._chain_current_phase(chain)
            status_key = str(getattr(chain, "status", "") or "")
            status_label = _CHAIN_STATUS_LABELS.get(status_key, status_key.title() or "Unknown")
            hero_name = self._hero_name_from_id(game_state, getattr(chain, "assigned_hero_id", None))
            reward_gold = self._chain_reward_gold(game_state, chain)
            current_target = str(getattr(current_phase, "target_name", "") or "").strip() if current_phase is not None else ""
            current_title = str(getattr(current_phase, "title", "") or "").strip() if current_phase is not None else ""

            compact_title_font = pygame.font.Font(None, 14)
            compact_font = pygame.font.Font(None, 11)
            title_h = compact_title_font.get_height()
            compact_h = compact_font.get_height()
            compact_gap = 0
            compact_title_gap = 1
            compact_pad_x = 5
            compact_pad_y = 3

            timeline_bits = []
            for phase in phase_rows:
                phase_status = str(getattr(phase, "status", "") or "upcoming")
                phase_label = _PHASE_STATUS_LABELS.get(phase_status, phase_status.upper() or "NEXT")
                phase_title = str(getattr(phase, "title", "") or getattr(phase, "phase_id", "") or "Phase")
                timeline_bits.append(f"{phase_label} {phase_title}")

            summary_bits = [str(getattr(chain, "name", "") or "Quest Chain"), f"Status: {status_label}"]
            summary_bits.append(f"Hero: {hero_name}" if hero_name else "Hero: Unassigned")
            if reward_gold:
                summary_bits.append(f"Reward: ${reward_gold}")
            if phase_rows:
                summary_bits.append(f"Phase: {min(current_index + 1, len(phase_rows))}/{len(phase_rows)}")
            summary_line = " | ".join(summary_bits)

            detail_lines: list[str] = []
            if status_key in {"active", "offered"} and current_title:
                detail_lines.append(f"Current objective: {current_title}")
            elif status_key in {"completed", "failed"}:
                detail_lines.append(f"Outcome: {status_label}")

            if timeline_bits:
                detail_lines.append(" | ".join(timeline_bits))

            candidate_lines = [summary_line, *detail_lines]
            chosen_lines = candidate_lines[:1]
            base_h = compact_pad_y * 2 + 2
            for count in range(len(candidate_lines), 0, -1):
                card_h = base_h + (count * compact_h) + max(0, count - 1) * compact_gap
                if card_h <= max(0, bottom - (y + title_h + compact_title_gap)):
                    chosen_lines = candidate_lines[:count]
                    break

            card_h = base_h + (len(chosen_lines) * compact_h) + max(0, len(chosen_lines) - 1) * compact_gap
            compact_bottom = bottom - (title_h + compact_title_gap)
            card_rect = pygame.Rect(x, y + title_h + compact_title_gap, rect.width, min(card_h, max(0, compact_bottom - y)))
            if card_rect.bottom <= bottom:
                TextLabel.render(surface, compact_title_font, board_title, (x, y), (220, 200, 130))
                lines.append(board_title)
                y += title_h + compact_title_gap
                pygame.draw.rect(surface, (35, 38, 45), card_rect)
                pygame.draw.rect(surface, (70, 70, 90), card_rect, 1)
                inner_x = card_rect.x + compact_pad_x
                inner_y = card_rect.y + compact_pad_y
                inner_w = max(0, card_rect.width - compact_pad_x * 2)
                for idx, line in enumerate(chosen_lines):
                    line_color = (200, 200, 210) if idx == 0 else (185, 195, 205)
                    TextLabel.render(
                        surface,
                        compact_font,
                        _truncate(line, inner_w, compact_font),
                        (inner_x, inner_y),
                        line_color,
                    )
                    lines.append(line)
                    inner_y += compact_h + compact_gap
                y = inner_y
                if len(chains) > 1 and y + compact_h <= bottom:
                    more = f"... +{len(chains) - 1} more"
                    TextLabel.render(surface, compact_font, more, (x, y), (150, 150, 160))
                    lines.append(more)
                    y += compact_h + 2
            return lines, y

        TextLabel.render(surface, title_font, board_title, (x, y), (220, 200, 130))
        lines.append(board_title)
        y += title_h + 4

        for chain_idx, chain in enumerate(chains):
            phase_rows = tuple(getattr(chain, "phases", ()) or ())
            if not phase_rows:
                continue

            current_phase, current_index = self._chain_current_phase(chain)
            status_key = str(getattr(chain, "status", "") or "")
            status_label = _CHAIN_STATUS_LABELS.get(status_key, status_key.title() or "Unknown")
            hero_name = self._hero_name_from_id(game_state, getattr(chain, "assigned_hero_id", None))
            reward_gold = self._chain_reward_gold(game_state, chain)
            current_target = str(getattr(current_phase, "target_name", "") or "").strip() if current_phase is not None else ""
            current_title = str(getattr(current_phase, "title", "") or "").strip() if current_phase is not None else ""

            card_lines: list[str] = []
            card_lines.append(str(getattr(chain, "name", "") or "Quest Chain"))
            meta_bits = [f"Status: {status_label}"]
            meta_bits.append(f"Hero: {hero_name}" if hero_name else "Hero: Unassigned")
            if reward_gold:
                meta_bits.append(f"Reward: ${reward_gold}")
            if phase_rows:
                meta_bits.append(f"Phase: {min(current_index + 1, len(phase_rows))}/{len(phase_rows)}")
            card_lines.append(" | ".join(meta_bits))
            if status_key in {"active", "offered"} and current_title:
                objective_bits = [f"Current objective: {current_title}"]
                if current_target:
                    objective_bits.append(f"Target: {current_target}")
                card_lines.append(" | ".join(objective_bits))

            for phase in phase_rows:
                phase_status = str(getattr(phase, "status", "") or "upcoming")
                phase_label = _PHASE_STATUS_LABELS.get(phase_status, phase_status.upper() or "NEXT")
                phase_title = str(getattr(phase, "title", "") or getattr(phase, "phase_id", "") or "Phase")
                card_lines.append(f"{phase_label} {phase_title}")

            has_objective_line = status_key in {"active", "offered"} and current_title
            card_h = pad_y * 2
            card_h += title_h
            card_h += gap + body_h
            if has_objective_line:
                card_h += gap + body_h
            card_h += len(phase_rows) * (body_h + 4)
            if status_key in {"completed", "failed"}:
                card_h += gap + body_h
            card_h += 2

            card_rect = pygame.Rect(x, y, rect.width, card_h)
            if card_rect.bottom > bottom:
                break

            pygame.draw.rect(surface, (35, 38, 45), card_rect)
            pygame.draw.rect(surface, (70, 70, 90), card_rect, 1)

            inner_x = card_rect.x + pad_x
            inner_y = card_rect.y + pad_y
            inner_w = max(0, card_rect.width - pad_x * 2)
            TextLabel.render(
                surface,
                title_font,
                _truncate(card_lines[0], inner_w, title_font),
                (inner_x, inner_y),
                (230, 220, 170),
            )
            lines.append(card_lines[0])
            inner_y += title_h + gap

            TextLabel.render(
                surface,
                body_font,
                _truncate(card_lines[1], inner_w, body_font),
                (inner_x, inner_y),
                (200, 200, 210),
            )
            lines.append(card_lines[1])
            inner_y += body_h + gap

            if len(card_lines) > 2 and status_key not in {"completed", "failed"}:
                objective_color = (200, 210, 200) if status_key in {"active", "offered"} else (210, 180, 180)
                TextLabel.render(
                    surface,
                    body_font,
                    _truncate(card_lines[2], inner_w, body_font),
                    (inner_x, inner_y),
                    objective_color,
                )
                lines.append(card_lines[2])
                inner_y += body_h + gap

            start_index = 3 if len(card_lines) > 2 and status_key not in {"completed", "failed"} else 2
            for phase_line in card_lines[start_index:]:
                phase_status = "upcoming"
                if phase_line.startswith("OFFERED "):
                    phase_status = "offered"
                elif phase_line.startswith("NOW "):
                    phase_status = "active"
                elif phase_line.startswith("DONE "):
                    phase_status = "completed"
                elif phase_line.startswith("FAIL "):
                    phase_status = "failed"
                phase_color = _PHASE_STATUS_COLORS.get(phase_status, (160, 160, 170))
                TextLabel.render(
                    surface,
                    body_font,
                    _truncate(phase_line, inner_w, body_font),
                    (inner_x, inner_y),
                    phase_color,
                )
                lines.append(phase_line)
                inner_y += body_h + 4

            if status_key in {"completed", "failed"}:
                footer_line = f"Outcome: {status_label}"
                TextLabel.render(
                    surface,
                    body_font,
                    _truncate(footer_line, inner_w, body_font),
                    (inner_x, inner_y),
                    (230, 120, 120) if status_key == "failed" else (110, 200, 110),
                )
                lines.append(footer_line)
                inner_y += body_h + gap

            y = inner_y + 4
            if chain_idx < len(chains) - 1 and y < bottom:
                pygame.draw.line(surface, (70, 70, 90), (x + 4, y - 2), (x + rect.width - 4, y - 2), 1)

            if y >= bottom:
                break

        return lines, y

    def render_active_quests(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        game_state: dict[str, Any],
    ) -> list[str]:
        """Render the active-quest list into ``rect``.

        Two lines per quest: "<Type> â€” <target>" then "$<reward> â€” <status>"
        (status = Open, or the accepting hero + n/m progress for slay quests).
        Returns the rendered line strings (handy for headless assertions).
        """
        lines: list[str] = []
        if rect.width <= 0 or rect.height <= 0:
            return lines
        font = self.theme.font_small
        x, y = rect.x, rect.y
        bottom = rect.bottom
        clip_before = surface.get_clip()
        surface.set_clip(rect)
        try:
            chain_lines, y = self._render_active_chain_section(surface, rect, game_state)
            lines.extend(chain_lines)

            quests = self._active_quests_from(game_state)
            if chain_lines:
                if quests and y + self.theme.font_body.get_height() + 4 <= bottom:
                    TextLabel.render(surface, self.theme.font_body, "Active Quests", (x, y), (220, 200, 130))
                    lines.append("Active Quests")
                    y += self.theme.font_body.get_height() + 4
            else:
                TextLabel.render(surface, self.theme.font_body, "Active Quests", (x, y), (220, 200, 130))
                y += self.theme.font_body.get_height() + 4

            if not quests:
                if not chain_lines:
                    msg = "No active quests."
                    TextLabel.render(surface, font, msg, (x, y), (150, 150, 160))
                    lines.append(msg)
                return lines

            row_h = font.get_height() + 2
            quest_lines_rendered = 0
            for quest in quests:
                if y + row_h * 2 + 6 > bottom:
                    more = f"... +{len(quests) - quest_lines_rendered // 2} more"
                    if y + row_h <= bottom:
                        TextLabel.render(surface, font, more, (x, y), (150, 150, 160))
                    break
                qtype = str(getattr(quest, "quest_type", "") or "")
                type_label = _QUEST_TYPE_LABELS.get(qtype, qtype.replace("_", " ").title())
                line1 = f"{type_label} â€” {quest_target_label(quest)}"
                if getattr(quest, "is_open", False):
                    status = "Open"
                else:
                    who = str(getattr(quest, "accepted_by_name", "") or "Hero")
                    status = f"Accepted: {who}"
                    if qtype == "slay_enemy_type":
                        status += f" ({int(getattr(quest, 'progress', 0))}/{int(getattr(quest, 'count', 1))})"
                line2 = f"${int(getattr(quest, 'reward', 0))} â€” {status}"
                TextLabel.render(surface, font, _truncate(line1, rect.width, font), (x, y), (230, 230, 240))
                y += row_h
                TextLabel.render(surface, font, _truncate(line2, rect.width - 10, font), (x + 10, y), (180, 195, 180))
                y += row_h + 6
                lines.extend([line1, line2])
                quest_lines_rendered += 2
            return lines
        finally:
            surface.set_clip(clip_before)

    def handle_click(self, mouse_pos: tuple[int, int], right_rect: pygame.Rect) -> str | None:
        if self._recall_rect is not None and self._recall_rect.collidepoint(mouse_pos):
            return "exit_quest"
        return None
