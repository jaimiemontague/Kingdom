"""Selected-hero panel renderer extracted from HUD."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_GREEN, COLOR_RED, COLOR_WHITE
from game.entities.guard import Guard
from game.entities.tax_collector import TaxCollector
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.widgets import HPBar, TextLabel


class HeroPanel:
    """Render detailed selected-hero information."""

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
        self.font_tiny = pygame.font.Font(None, 16)

    def _draw_section_divider(self, surface: pygame.Surface, x: int, y: int, width: int) -> None:
        if width <= 0:
            return
        pygame.draw.line(surface, self._frame_inner, (x, y), (x + width, y), 1)
        pygame.draw.line(surface, self._frame_highlight, (x, y + 1), (x + width, y + 1), 1)

    def _right_panel_top_pad(self, rect: pygame.Rect, right_close_rect: pygame.Rect | None) -> int:
        pad = int(self.theme.margin)
        if right_close_rect is not None and right_close_rect.colliderect(rect):
            pad = max(pad, int(right_close_rect.height) + int(self.theme.gutter))
        return pad

    def _compute_hero_intent(self, hero) -> str:
        try:
            if hasattr(hero, "get_intent_snapshot"):
                snap = hero.get_intent_snapshot(now_ms=int(sim_now_ms()))
                if isinstance(snap, dict):
                    intent = str(snap.get("intent", "") or "")
                    if intent:
                        mapping = {
                            "idle": "Idle",
                            "pursuing_bounty": "Pursuing bounty",
                            "shopping": "Shopping",
                            "returning_to_safety": "Returning to safety",
                            "engaging_enemy": "Engaging enemy",
                            "defending_building": "Defending building",
                            "attacking_lair": "Attacking lair",
                        }
                        return mapping.get(intent, intent.replace("_", " ").title())
        except Exception:
            pass

        try:
            if isinstance(getattr(hero, "target", None), dict) and hero.target.get("type") == "bounty":
                bounty_type = hero.target.get("bounty_type", "bounty")
                if bounty_type == "attack_lair":
                    return "Attacking lair (bounty)"
                if bounty_type == "defend_building":
                    return "Defending building (bounty)"
                return "Pursuing bounty"
        except Exception:
            pass

        state = str(getattr(getattr(hero, "state", None), "name", "") or "").upper()
        if state == "FIGHTING":
            return "Engaging enemy"
        if state == "SHOPPING":
            return "Shopping"
        if state == "RETREATING":
            return "Returning to safety"
        if state == "RESTING":
            return "Resting"
        if state == "MOVING":
            return "Moving"
        if state == "IDLE":
            return "Idle"
        return state.title() if state else "Idle"

    def _format_last_decision(self, hero) -> tuple[str, tuple[int, int, int]]:
        action = None
        target = ""
        reason = ""
        age_s = None

        try:
            if hasattr(hero, "get_intent_snapshot"):
                snap = hero.get_intent_snapshot(now_ms=int(sim_now_ms()))
                if isinstance(snap, dict):
                    last_decision = snap.get("last_decision", None)
                    if isinstance(last_decision, dict):
                        action = last_decision.get("action", None)
                        reason_raw = last_decision.get("reason", "")
                        reason = reason_raw if isinstance(reason_raw, str) else ""
                        age_ms = last_decision.get("age_ms", None)
                        if age_ms is not None:
                            try:
                                age_s = max(0.0, float(age_ms) / 1000.0)
                            except Exception:
                                age_s = None
        except Exception:
            pass

        try:
            legacy = getattr(hero, "last_llm_action", None) or {}
            if isinstance(legacy, dict):
                action = action or legacy.get("action", None)
                target_raw = legacy.get("target", "")
                target = target_raw if isinstance(target_raw, str) else ""
                if not reason:
                    reason_raw = legacy.get("reasoning", "")
                    reason = reason_raw if isinstance(reason_raw, str) else ""
        except Exception:
            pass

        if not action:
            return "Last decision: (none yet)", (150, 150, 150)

        if age_s is None:
            try:
                t_ms = int(getattr(hero, "last_llm_decision_time", 0) or 0)
                if t_ms > 0:
                    age_s = max(0.0, (float(sim_now_ms()) - float(t_ms)) / 1000.0)
            except Exception:
                age_s = None

        parts = [str(action)]
        if target:
            parts.append(f"-> {target}")
        if age_s is not None:
            parts.append(f"({age_s:.0f}s ago)")
        head = " ".join(parts)

        reason = (reason or "").strip().replace("\n", " ")
        if reason:
            if len(reason) > 70:
                reason = reason[:67].rstrip() + "..."
            return f"Last decision: {head} - {reason}", COLOR_WHITE
        return f"Last decision: {head}", COLOR_WHITE

    def _render_tax_collector(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        tc: TaxCollector,
        *,
        right_close_rect: pygame.Rect | None = None,
    ) -> None:
        """Render left-panel content for selected Tax Collector (wk16)."""
        panel_width = int(rect.width)
        panel_x = int(rect.x)
        panel_y = int(rect.y)
        pad = self._right_panel_top_pad(rect, right_close_rect)
        y = panel_y + pad
        bar_width = panel_width - (pad * 2)

        header_h = 28
        header_rect = pygame.Rect(panel_x + 6, panel_y + pad - 4, panel_width - 12, header_h)
        pygame.draw.rect(surface, (35, 35, 45), header_rect)
        pygame.draw.rect(surface, self._frame_inner, header_rect, 1)
        pygame.draw.line(
            surface,
            self._frame_highlight,
            (header_rect.left + 1, header_rect.top + 1),
            (header_rect.right - 2, header_rect.top + 1),
            1,
        )
        TextLabel.render(
            surface,
            self.theme.font_title,
            "Tax Collector",
            (panel_x + pad, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            COLOR_WHITE,
            shadow_color=(20, 20, 30),
        )
        y = header_rect.bottom + 6

        state_name = str(getattr(tc.state, "name", "UNKNOWN")).replace("_", " ").title()
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Status: {state_name}",
            (panel_x + pad, y),
            (200, 200, 200),
            shadow_color=(25, 25, 35),
        )
        y += self.theme.font_small.get_height() + 6

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Gold",
            (panel_x + pad, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Carried: {int(getattr(tc, 'carried_gold', 0))}",
            (panel_x + pad, y),
            COLOR_GOLD,
            shadow_color=(25, 25, 35),
        )
        y += 14
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Total collected: {int(getattr(tc, 'total_collected', 0))}",
            (panel_x + pad, y),
            (220, 220, 220),
            shadow_color=(25, 25, 35),
        )

    def _render_guard(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        guard: Guard,
        *,
        right_close_rect: pygame.Rect | None = None,
    ) -> None:
        """Render left-panel content for selected Guard."""
        panel_width = int(rect.width)
        panel_x = int(rect.x)
        panel_y = int(rect.y)
        pad = self._right_panel_top_pad(rect, right_close_rect)
        y = panel_y + pad
        bar_width = panel_width - (pad * 2)

        header_h = 28
        header_rect = pygame.Rect(panel_x + 6, panel_y + pad - 4, panel_width - 12, header_h)
        pygame.draw.rect(surface, (35, 35, 45), header_rect)
        pygame.draw.rect(surface, self._frame_inner, header_rect, 1)
        pygame.draw.line(
            surface,
            self._frame_highlight,
            (header_rect.left + 1, header_rect.top + 1),
            (header_rect.right - 2, header_rect.top + 1),
            1,
        )
        TextLabel.render(
            surface,
            self.theme.font_title,
            "Guard",
            (panel_x + pad, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            COLOR_WHITE,
            shadow_color=(20, 20, 30),
        )
        y = header_rect.bottom + 6

        post_name = "Guard"
        home = getattr(guard, "home_building", None)
        if home is not None and hasattr(home, "building_type"):
            btype = str(getattr(home, "building_type", "") or "").replace("_", " ").title()
            post_name = f"Post: {btype}" if btype else "Guard"
        TextLabel.render(
            surface,
            self.theme.font_small,
            post_name,
            (panel_x + pad, y),
            (200, 200, 200),
            shadow_color=(25, 25, 35),
        )
        y += self.theme.font_small.get_height() + 6

        state_name = str(getattr(getattr(guard, "state", None), "name", "IDLE")).replace("_", " ").title()
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"State: {state_name}",
            (panel_x + pad, y),
            (200, 200, 200),
            shadow_color=(25, 25, 35),
        )
        y += self.theme.font_small.get_height() + 6

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Vitals",
            (panel_x + pad, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4

        hp_line = f"HP: {int(getattr(guard, 'hp', 0))}/{int(getattr(guard, 'max_hp', 1))}"
        TextLabel.render(
            surface,
            self.theme.font_small,
            hp_line,
            (panel_x + pad, y),
            COLOR_WHITE,
            shadow_color=(25, 25, 35),
        )
        y += self.theme.font_small.get_height() + 6

        bar_rect = pygame.Rect(panel_x + pad, y, bar_width, 8)
        HPBar.render(
            surface,
            bar_rect,
            int(getattr(guard, "hp", 0)),
            int(max(1, getattr(guard, "max_hp", 1))),
            color_scheme={
                "bg": (60, 60, 60),
                "good": COLOR_GREEN,
                "warn": (220, 180, 90),
                "bad": COLOR_RED,
                "border": (20, 20, 25),
            },
        )
        y += bar_rect.height + 6

        atk = int(getattr(guard, "attack_power", 0))
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"ATK: {atk}",
            (panel_x + pad, y),
            (220, 220, 220),
            shadow_color=(25, 25, 35),
        )

    def render(
        self,
        surface: pygame.Surface,
        hero,
        rect: pygame.Rect,
        *,
        right_close_rect: pygame.Rect | None = None,
        debug_ui: bool = False,
    ) -> None:
        if isinstance(hero, TaxCollector):
            self._render_tax_collector(surface, rect, hero, right_close_rect=right_close_rect)
            return
        if isinstance(hero, Guard):
            self._render_guard(surface, rect, hero, right_close_rect=right_close_rect)
            return

        panel_width = int(rect.width)
        panel_x = int(rect.x)
        panel_y = int(rect.y)
        pad = self._right_panel_top_pad(rect, right_close_rect)
        y = panel_y + pad

        header_h = 28
        header_rect = pygame.Rect(panel_x + 6, panel_y + pad - 4, panel_width - 12, header_h)
        pygame.draw.rect(surface, (35, 35, 45), header_rect)
        pygame.draw.rect(surface, self._frame_inner, header_rect, 1)
        pygame.draw.line(
            surface,
            self._frame_highlight,
            (header_rect.left + 1, header_rect.top + 1),
            (header_rect.right - 2, header_rect.top + 1),
            1,
        )
        TextLabel.render(
            surface,
            self.theme.font_title,
            str(hero.name),
            (panel_x + pad, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            COLOR_WHITE,
            shadow_color=(20, 20, 30),
        )
        y = header_rect.bottom + 6

        class_line = f"{hero.hero_class.title()} Lv.{hero.level}"
        TextLabel.render(
            surface,
            self.theme.font_small,
            class_line,
            (panel_x + pad, y),
            COLOR_WHITE,
            shadow_color=(25, 25, 35),
        )
        y += self.theme.font_small.get_height() + 6

        hp_line = f"HP: {hero.hp}/{hero.max_hp}"
        TextLabel.render(
            surface,
            self.theme.font_small,
            hp_line,
            (panel_x + pad, y),
            COLOR_WHITE,
            shadow_color=(25, 25, 35),
        )
        y += self.theme.font_small.get_height() + 6

        bar_width = panel_width - (pad * 2)
        bar_rect = pygame.Rect(panel_x + pad, y, bar_width, 8)
        HPBar.render(
            surface,
            bar_rect,
            int(getattr(hero, "hp", 0)),
            int(getattr(hero, "max_hp", 1)),
            color_scheme={
                "bg": (60, 60, 60),
                "good": COLOR_GREEN,
                "warn": (220, 180, 90),
                "bad": COLOR_RED,
                "border": (20, 20, 25),
            },
        )
        y += bar_rect.height + 6

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Vitals",
            (panel_x + pad, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4

        stats_line = f"ATK: {hero.attack}  DEF: {hero.defense}"
        TextLabel.render(
            surface,
            self.theme.font_small,
            stats_line,
            (panel_x + pad, y),
            (220, 220, 220),
            shadow_color=(25, 25, 35),
        )
        y += 16

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Economy",
            (panel_x + pad, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4

        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Gold: {hero.gold}",
            (panel_x + pad, y),
            COLOR_GOLD,
            shadow_color=(25, 25, 35),
        )
        y += 14

        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Taxed: {hero.taxed_gold}",
            (panel_x + pad, y),
            (220, 180, 90),
            shadow_color=(25, 25, 35),
        )
        y += 16

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Equipment",
            (panel_x + pad, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4

        potion_count = int(getattr(hero, "potions", 0))
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Potions: {potion_count}",
            (panel_x + pad, y),
            COLOR_GREEN,
            shadow_color=(25, 25, 35),
        )
        y += 16

        weapon_name = hero.weapon["name"] if getattr(hero, "weapon", None) else "Fists"
        armor_name = hero.armor["name"] if getattr(hero, "armor", None) else "None"
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"W: {weapon_name}",
            (panel_x + pad, y),
            COLOR_WHITE,
            shadow_color=(25, 25, 35),
        )
        y += 14
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"A: {armor_name}",
            (panel_x + pad, y),
            COLOR_WHITE,
            shadow_color=(25, 25, 35),
        )
        y += 16

        self._draw_section_divider(surface, panel_x + pad, y, bar_width)
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Intent",
            (panel_x + pad, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4

        intent = self._compute_hero_intent(hero)
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"Intent: {intent}",
            (panel_x + pad, y),
            (220, 220, 220),
            shadow_color=(25, 25, 35),
        )
        y += 14

        state_name = str(getattr(getattr(hero, "state", None), "name", "IDLE"))
        TextLabel.render(
            surface,
            self.theme.font_small,
            f"State: {state_name}",
            (panel_x + pad, y),
            (200, 200, 200),
            shadow_color=(25, 25, 35),
        )
        y += 14

        decision_line, decision_color = self._format_last_decision(hero)
        if len(decision_line) > 48:
            decision_line = decision_line[:45].rstrip() + "..."
        TextLabel.render(
            surface,
            self.font_tiny,
            decision_line,
            (panel_x + pad, y),
            decision_color,
            shadow_color=(20, 20, 30),
        )
        y += 16

        try:
            if bool(getattr(hero, "is_inside_building", False)):
                inside_building = getattr(hero, "inside_building", None)
                building_name = None
                if inside_building is not None:
                    building_name = getattr(inside_building, "building_type", None) or inside_building.__class__.__name__
                inside_line = f"Inside: {str(building_name).replace('_', ' ').title()}" if building_name else "Inside: yes"
                TextLabel.render(surface, self.font_tiny, inside_line, (panel_x + pad, y), (220, 220, 255))
                y += 14
        except Exception:
            pass

        if not debug_ui:
            return

        now_ms = int(sim_now_ms())
        try:
            snapshot = hero.get_stuck_snapshot(now_ms=now_ms) if hasattr(hero, "get_stuck_snapshot") else None
            if isinstance(snapshot, dict) and bool(snapshot.get("stuck_active", False)):
                reason = str(snapshot.get("stuck_reason", "") or "stuck").strip()
                attempts = int(snapshot.get("unstuck_attempts", 0) or 0)
                stuck_since = snapshot.get("stuck_since_ms", None)
                if stuck_since is not None:
                    try:
                        stuck_s = max(0.0, (float(now_ms) - float(stuck_since)) / 1000.0)
                        stuck_line = f"STUCK: {reason} ({stuck_s:.1f}s, attempts {attempts})"
                    except Exception:
                        stuck_line = f"STUCK: {reason} (attempts {attempts})"
                else:
                    stuck_line = f"STUCK: {reason} (attempts {attempts})"
                TextLabel.render(surface, self.font_tiny, stuck_line, (panel_x + pad, y), (255, 180, 100))
                y += 14
        except Exception:
            pass

        try:
            can_attack = getattr(hero, "can_attack", None)
            if isinstance(can_attack, bool) and not can_attack:
                reason = str(getattr(hero, "attack_blocked_reason", "") or "").strip()
                line = f"ATK BLOCKED: {reason}" if reason else "ATK BLOCKED"
                TextLabel.render(surface, self.font_tiny, line[:48], (panel_x + pad, y), (255, 160, 160))
        except Exception:
            pass
