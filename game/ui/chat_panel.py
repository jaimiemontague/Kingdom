"""
Chat panel for hero conversation (wk14 Persona and Presence).

Overlays the interior view when the player clicks a hero. Message history,
text input, thinking indicator, End Conversation button.
"""

from __future__ import annotations

from typing import Any

import pygame

from config import CONVERSATION_HISTORY_LIMIT
from game.ui.theme import UITheme
from game.ui.widgets import Button, TextLabel

_HERO_CLASS_COLORS = {
    "warrior": (70, 120, 255),
    "ranger": (70, 200, 120),
    "rogue": (180, 180, 200),
    "wizard": (170, 90, 230),
    "cleric": (48, 186, 178),
}

_COLOR_BG_DIM = (0, 0, 0, 100)
_COLOR_HEADER_BG = (35, 35, 45)
_COLOR_MSG_BG = (60, 55, 45)
_COLOR_INPUT_BG = (45, 45, 55)
_COLOR_TEXT = (240, 240, 240)
_COLOR_MUTED = (180, 180, 180)
_COLOR_THINKING = (160, 160, 160)
_COLOR_DIRECT_HINT = (150, 175, 155)
_COLOR_DIRECT_WARN = (200, 175, 130)

# Human-readable refusal labels (validator slugs); keep short for chat rail.
_REFUSAL_HINT_LABELS: dict[str, str] = {
    "mvp_combat_deferred": "that kind of attack is not in the game yet",
    "no_known_home": "no safe home is known yet",
    "no_safe_haven_known": "no safe haven is known yet",
    "unknown_place": "that place is not known yet",
    "no_gold": "not enough gold",
    "no_market_known": "no market is known yet",
}


def format_direct_prompt_hint(feedback: dict[str, Any] | None) -> str | None:
    """
    One-line HUD hint for WK50 direct prompts: applied vs redirected vs refused vs chat-only.
    Returns None when no extra UI is useful (pure chat replies).

    ``physical_committed`` (set by GameEngine after apply) gates any success line so we
    never imply an order was carried out when the sim did not commit an effect.
    """
    if not feedback:
        return None
    raw_tool = feedback.get("tool_action")
    tool_str = ""
    if raw_tool is not None:
        tool_str = str(raw_tool).strip().lower()
    has_action = bool(tool_str) and tool_str not in ("null", "none")

    obey = str(feedback.get("obey_defy") or "").strip().lower()
    refusal = str(feedback.get("refusal_reason") or "").strip()
    safety = str(feedback.get("safety_assessment") or "").strip().lower()
    interpreted = str(feedback.get("interpreted_intent") or "").strip().lower()
    physical = feedback.get("physical_committed")

    def _refusal_line() -> str:
        rl = refusal.lower()
        detail = _REFUSAL_HINT_LABELS.get(rl)
        if not detail:
            detail = refusal.replace("_", " ").strip() if refusal else "cannot comply yet"
            if not detail:
                detail = "cannot comply yet"
        return f"Refused — {detail}"

    # Model/schema claimed a tool, but the engine did not commit a physical effect.
    if has_action and physical is False:
        if refusal:
            return _refusal_line()
        return "Not applied — no action committed"

    if has_action and physical is not False:
        if safety == "critical_redirect":
            return "Redirected — safer option"
        return "Order applied"

    # No tool: refusal / soft redirect / chat-only
    if obey == "defy" or refusal:
        return _refusal_line()

    if safety == "critical_redirect":
        return "Redirected — safer path"

    if interpreted in ("no_action_chat_only", "status_report"):
        return None

    return None


def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels. Handles long single words."""
    if max_width <= 0:
        return [text] if text else []
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    line = ""
    for word in words:
        trial = f"{line} {word}".strip() if line else word
        if font.size(trial)[0] <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            if font.size(word)[0] > max_width:
                # Force-break a single long word
                built = ""
                for ch in word:
                    if font.size(built + ch)[0] > max_width and built:
                        lines.append(built)
                        built = ch
                    else:
                        built += ch
                line = built
            else:
                line = word
    if line:
        lines.append(line)
    return lines


class ChatPanel:
    """
    Conversation overlay: header (portrait, name, class, level), scrollable
    message area, text input, End Conversation button.
    """

    def __init__(self, theme: UITheme) -> None:
        self.theme = theme
        self.conversation_history: list[dict[str, str]] = []
        self.hero_target: Any = None
        self.waiting_for_response = False
        self._scroll_offset = 0
        self._input_text = ""
        self._pending_message: str | None = None
        self._end_button_rect: pygame.Rect | None = None
        self._input_rect: pygame.Rect | None = None
        self._message_area_rect: pygame.Rect | None = None
        self._frame_outer = (0x14, 0x14, 0x19)
        self._frame_inner = (0x50, 0x50, 0x64)
        self._accent = getattr(theme, "accent", (0xCC, 0xAA, 0x44))
        self._end_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="End Conversation",
            font=theme.font_small,
            enabled=True,
        )
        self._dim_cache: dict[tuple[int, int], pygame.Surface] = {}
        self._auto_scroll = True

    def start_conversation(self, hero: Any) -> None:
        self.hero_target = hero
        if not hasattr(hero, "conversation_history"):
            hero.conversation_history = []
        self.conversation_history = hero.conversation_history
        self.waiting_for_response = False
        self._scroll_offset = 0
        self._input_text = ""
        self._pending_message = None
        self._auto_scroll = True

    def end_conversation(self) -> None:
        self.hero_target = None
        self.conversation_history = []
        self.waiting_for_response = False
        self._scroll_offset = 0
        self._input_text = ""
        self._pending_message = None

    def send_message(self, text: str) -> None:
        if not text.strip():
            return
        self.conversation_history.append({"role": "player", "text": text.strip()})
        self._pending_message = text.strip()
        self._auto_scroll = True
        if len(self.conversation_history) > CONVERSATION_HISTORY_LIMIT:
            self.conversation_history = self.conversation_history[-CONVERSATION_HISTORY_LIMIT:]

    def get_pending_message(self) -> str | None:
        msg, self._pending_message = self._pending_message, None
        return msg

    def receive_response(self, text: str, direct_feedback: dict[str, Any] | None = None) -> None:
        entry: dict[str, str] = {"role": "hero", "text": text}
        hint = format_direct_prompt_hint(direct_feedback)
        if hint:
            entry["direct_hint"] = hint
        self.conversation_history.append(entry)
        self.waiting_for_response = False
        self._auto_scroll = True
        if len(self.conversation_history) > CONVERSATION_HISTORY_LIMIT:
            self.conversation_history = self.conversation_history[-CONVERSATION_HISTORY_LIMIT:]

    def is_active(self) -> bool:
        return self.hero_target is not None

    def _hero_class_color(self) -> tuple[int, int, int]:
        hc = (getattr(self.hero_target, "hero_class", "warrior") or "warrior").lower()
        return _HERO_CLASS_COLORS.get(hc, _HERO_CLASS_COLORS["warrior"])

    def _get_dim_surface(self, w: int, h: int) -> pygame.Surface:
        key = (w, h)
        if key not in self._dim_cache:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            s.fill(_COLOR_BG_DIM)
            self._dim_cache[key] = s
        return self._dim_cache[key]

    def render_idle_dock(self, surface: pygame.Surface, dock_rect: pygame.Rect) -> None:
        """Empty chat footprint (dock under minimap — WK52 R4)."""
        if dock_rect.width <= 0 or dock_rect.height <= 0:
            return
        pygame.draw.rect(surface, (12, 12, 18), dock_rect)
        pygame.draw.rect(surface, self._frame_outer, dock_rect, 1)

    def render_watch_band(
        self,
        surface: pygame.Surface,
        band_rect: pygame.Rect,
        game_state: dict[str, Any],
        pinned_hero_id: str,
    ) -> None:
        """
        Compact chat strip inside WK52 watch card: divider, history, input/placeholder.
        Used when the full ``render()`` chrome (header + End button) does not fit.
        """
        self._header_rect = None
        self._end_button_rect = None
        self._watch_band_close_rect = None
        if band_rect.width <= 0 or band_rect.height <= 0:
            return

        rx, ry, w, h = band_rect.x, band_rect.y, band_rect.width, band_rect.height
        pygame.draw.line(
            surface,
            self._frame_inner,
            (rx, ry),
            (rx + w - 1, ry),
            1,
        )

        pad_lr = 6
        divider_h = 1
        gap_after_divider = 1
        gap_before_input = 4
        overhead_top = divider_h + gap_after_divider
        inner_top = ry + overhead_top
        slack = max(28, h - overhead_top - gap_before_input)
        input_h = max(22, min(28, slack // 6))
        if overhead_top + gap_before_input + input_h > h - 16:
            input_h = max(18, h - overhead_top - gap_before_input - 14)
            input_h = min(input_h, 28)

        msg_h = max(16, h - overhead_top - gap_before_input - input_h)
        msg_rect = pygame.Rect(rx + pad_lr, inner_top, w - 2 * pad_lr, msg_h)

        pinned = None
        for hro in game_state.get("heroes") or []:
            if str(getattr(hro, "hero_id", "") or "") == str(pinned_hero_id):
                pinned = hro
                break

        convo_here = bool(
            pinned is not None and self.is_active() and self.hero_target is pinned
        )

        pygame.draw.rect(surface, _COLOR_MSG_BG, msg_rect)
        pygame.draw.rect(surface, self._frame_inner, msg_rect, 1)

        font = self.theme.font_small
        line_h = font.get_height() + 3
        max_text_w = max(8, msg_rect.width - 2 * pad_lr)

        def _stripe_empty_history() -> None:
            stripe = (
                min(110, int(_COLOR_MSG_BG[0]) + 14),
                min(110, int(_COLOR_MSG_BG[1]) + 14),
                min(100, int(_COLOR_MSG_BG[2]) + 12),
            )
            step = max(16, msg_rect.height // 7)
            for yy in range(msg_rect.top + step, msg_rect.bottom - 2, step):
                pygame.draw.line(surface, stripe, (msg_rect.left + 4, yy), (msg_rect.right - 5, yy), 1)

        if not convo_here:
            _stripe_empty_history()
            hint = font.render("No messages yet", True, _COLOR_MUTED)
            surface.blit(
                hint,
                (
                    msg_rect.centerx - hint.get_width() // 2,
                    msg_rect.centery - hint.get_height() // 2,
                ),
            )

        if convo_here:
            total_lines = 0
            for entry in self.conversation_history:
                wrapped = _wrap_text(font, entry.get("text", ""), max_text_w)
                block_lines = max(1, len(wrapped))
                dh = entry.get("direct_hint")
                if dh:
                    block_lines += len(_wrap_text(font, dh, max_text_w))
                total_lines += block_lines
            if self.waiting_for_response:
                total_lines += 1
            total_content_h = total_lines * line_h
            max_scroll = max(0, total_content_h - msg_rect.height + 2 * pad_lr)
            if self._auto_scroll:
                self._scroll_offset = max_scroll
                self._auto_scroll = False
            self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))

            clip_prev = surface.get_clip()
            surface.set_clip(msg_rect)
            content_y = msg_rect.y + pad_lr - self._scroll_offset
            for entry in self.conversation_history:
                role = entry.get("role", "hero")
                text = entry.get("text", "")
                color = self._accent if role == "player" else _COLOR_TEXT
                wrapped = _wrap_text(font, text, max_text_w)
                if not wrapped:
                    wrapped = [" "]
                for line_text in wrapped:
                    if content_y + line_h > msg_rect.y and content_y < msg_rect.bottom:
                        surf = font.render(line_text, True, color)
                        x_msg = (
                            msg_rect.right - pad_lr - surf.get_width()
                            if role == "player"
                            else msg_rect.x + pad_lr
                        )
                        surface.blit(surf, (x_msg, content_y))
                    content_y += line_h
                if role != "player":
                    dh = entry.get("direct_hint")
                    if dh:
                        hint_color = (
                            _COLOR_DIRECT_WARN
                            if (
                                dh.startswith("Refused")
                                or dh.startswith("Not applied")
                                or dh.startswith("Not carried")
                            )
                            else _COLOR_DIRECT_HINT
                        )
                        for hint_line in _wrap_text(font, dh, max_text_w):
                            if content_y + line_h > msg_rect.y and content_y < msg_rect.bottom:
                                hs = font.render(hint_line, True, hint_color)
                                surface.blit(hs, (msg_rect.x + pad_lr, content_y))
                            content_y += line_h
            if self.waiting_for_response:
                dots = "." * ((pygame.time.get_ticks() // 400) % 4)
                thinking = font.render(f"Thinking{dots}", True, _COLOR_THINKING)
                if content_y + line_h > msg_rect.y and content_y < msg_rect.bottom:
                    surface.blit(thinking, (msg_rect.x + pad_lr, content_y))
            surface.set_clip(clip_prev)

        input_y = msg_rect.bottom + gap_before_input
        self._input_rect = pygame.Rect(rx + pad_lr, input_y, w - 2 * pad_lr, input_h)
        pygame.draw.rect(surface, _COLOR_INPUT_BG, self._input_rect)
        pygame.draw.rect(surface, self._frame_outer, self._input_rect, 1)

        llm_available = game_state.get("llm_available", True)
        if not llm_available:
            inp_text = "LLM not available"
            inp_color = _COLOR_THINKING
        elif convo_here:
            cursor = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            inp_text = self._input_text + cursor
            inp_color = _COLOR_TEXT
        else:
            inp_text = "> Type to chat…"
            inp_color = _COLOR_MUTED

        inp_surf = font.render(inp_text or " ", True, inp_color)
        clip_prev2 = surface.get_clip()
        surface.set_clip(self._input_rect.inflate(-4, 0))
        surface.blit(
            inp_surf,
            (
                self._input_rect.x + 6,
                self._input_rect.y + (input_h - inp_surf.get_height()) // 2,
            ),
        )
        surface.set_clip(clip_prev2)
        self._message_area_rect = msg_rect

        inset = 3
        close_s = 14
        self._watch_band_close_rect = pygame.Rect(rx + w - close_s - inset, ry + inset, close_s, close_s)
        cr = self._watch_band_close_rect
        pygame.draw.rect(surface, (20, 20, 28), cr, border_radius=2)
        pygame.draw.rect(surface, (60, 60, 80), cr, width=1, border_radius=2)
        glyph = (190, 185, 210)
        pygame.draw.line(surface, glyph, (cr.left + 3, cr.top + 3), (cr.right - 4, cr.bottom - 4), 1)
        pygame.draw.line(surface, glyph, (cr.right - 4, cr.top + 3), (cr.left + 3, cr.bottom - 4), 1)

    def render(
        self,
        surface: pygame.Surface,
        target_rect: pygame.Rect,
        game_state: dict[str, Any],
    ) -> None:
        if not self.is_active() or target_rect.width <= 0 or target_rect.height <= 0:
            return
        rx, ry, w, h = target_rect.x, target_rect.y, target_rect.width, target_rect.height
        pad = 10
        header_h = 48
        input_h = 32
        end_btn_h = 28
        margin_bottom = pad + end_btn_h + pad
        msg_top = ry + header_h + pad
        msg_h = max(20, h - (header_h + pad * 2 + input_h + margin_bottom))
        self._message_area_rect = pygame.Rect(rx + pad, msg_top, w - 2 * pad, msg_h)

        surface.blit(self._get_dim_surface(w, h), (rx, ry))

        # Header (clickable: selects hero and shows left panel — wk16)
        header_rect = pygame.Rect(rx, ry, w, header_h)
        self._header_rect = header_rect
        pygame.draw.rect(surface, _COLOR_HEADER_BG, header_rect)
        pygame.draw.rect(surface, self._frame_outer, header_rect, 1)
        portrait_center = (rx + 24, ry + header_h // 2)
        pygame.draw.circle(surface, self._hero_class_color(), portrait_center, 16)
        pygame.draw.circle(surface, _COLOR_TEXT, portrait_center, 16, 1)
        name = getattr(self.hero_target, "name", "Hero")
        cls = (getattr(self.hero_target, "hero_class", "warrior") or "warrior").capitalize()
        level = getattr(self.hero_target, "level", 1)
        TextLabel.render(surface, self.theme.font_body, name, (rx + 50, ry + 6), _COLOR_TEXT)
        TextLabel.render(surface, self.theme.font_small, f"{cls} \u00b7 Lv{level}", (rx + 50, ry + 26), _COLOR_MUTED)

        # Message area
        msg_rect = self._message_area_rect
        pygame.draw.rect(surface, _COLOR_MSG_BG, msg_rect)
        pygame.draw.rect(surface, self._frame_inner, msg_rect, 1)

        font = self.theme.font_small
        line_h = font.get_height() + 4
        max_text_w = msg_rect.width - 2 * pad

        # Measure total content height first (for auto-scroll)
        total_lines = 0
        for entry in self.conversation_history:
            wrapped = _wrap_text(font, entry.get("text", ""), max_text_w)
            block_lines = max(1, len(wrapped))
            dh = entry.get("direct_hint")
            if dh:
                block_lines += len(_wrap_text(font, dh, max_text_w))
            total_lines += block_lines
        if self.waiting_for_response:
            total_lines += 1
        total_content_h = total_lines * line_h
        max_scroll = max(0, total_content_h - msg_rect.height + 2 * pad)

        if self._auto_scroll:
            self._scroll_offset = max_scroll
            self._auto_scroll = False
        self._scroll_offset = max(0, min(self._scroll_offset, max_scroll))

        # Render messages with clipping
        clip_prev = surface.get_clip()
        surface.set_clip(msg_rect)
        content_y = msg_rect.y + pad - self._scroll_offset
        for entry in self.conversation_history:
            role = entry.get("role", "hero")
            text = entry.get("text", "")
            color = self._accent if role == "player" else _COLOR_TEXT
            wrapped = _wrap_text(font, text, max_text_w)
            if not wrapped:
                wrapped = [" "]
            for line_text in wrapped:
                if content_y + line_h > msg_rect.y and content_y < msg_rect.bottom:
                    surf = font.render(line_text, True, color)
                    if role == "player":
                        x = msg_rect.right - pad - surf.get_width()
                    else:
                        x = msg_rect.x + pad
                    surface.blit(surf, (x, content_y))
                content_y += line_h
            if role != "player":
                dh = entry.get("direct_hint")
                if dh:
                    hint_color = (
                        _COLOR_DIRECT_WARN
                        if (
                            dh.startswith("Refused")
                            or dh.startswith("Not applied")
                            or dh.startswith("Not carried")
                        )
                        else _COLOR_DIRECT_HINT
                    )
                    for hint_line in _wrap_text(font, dh, max_text_w):
                        if content_y + line_h > msg_rect.y and content_y < msg_rect.bottom:
                            hs = font.render(hint_line, True, hint_color)
                            surface.blit(hs, (msg_rect.x + pad, content_y))
                        content_y += line_h
        if self.waiting_for_response:
            dots = "." * ((pygame.time.get_ticks() // 400) % 4)
            thinking = font.render(f"Thinking{dots}", True, _COLOR_THINKING)
            if content_y + line_h > msg_rect.y and content_y < msg_rect.bottom:
                surface.blit(thinking, (msg_rect.x + pad, content_y))
        surface.set_clip(clip_prev)

        # Input line (clipped to prevent overflow)
        input_y = msg_rect.bottom + pad
        self._input_rect = pygame.Rect(rx + pad, input_y, w - 2 * pad, input_h)
        pygame.draw.rect(surface, _COLOR_INPUT_BG, self._input_rect)
        pygame.draw.rect(surface, self._frame_outer, self._input_rect, 1)
        llm_available = game_state.get("llm_available", True)
        if not llm_available:
            inp_text = "LLM not available"
            inp_color = _COLOR_THINKING
        else:
            cursor = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            inp_text = self._input_text + cursor
            inp_color = _COLOR_TEXT
        inp_surf = font.render(inp_text or " ", True, inp_color)
        clip_prev2 = surface.get_clip()
        surface.set_clip(self._input_rect.inflate(-4, 0))
        surface.blit(inp_surf, (self._input_rect.x + 6, self._input_rect.y + (input_h - inp_surf.get_height()) // 2))
        surface.set_clip(clip_prev2)

        # End Conversation button
        end_y = input_y + input_h + pad
        end_w = 160
        self._end_button_rect = pygame.Rect(rx + w - end_w - pad, end_y, end_w, end_btn_h)
        self._end_button.rect = self._end_button_rect
        self._end_button.render(
            surface,
            pygame.mouse.get_pos(),
            bg_normal=(80, 50, 50),
            bg_hover=(120, 60, 60),
            bg_pressed=(100, 55, 55),
            border_outer=self._frame_outer,
            text_color=_COLOR_TEXT,
        )

    def handle_click(self, mouse_pos: tuple[int, int], chat_rect: pygame.Rect) -> str | dict | None:
        if not self.is_active() or not chat_rect.collidepoint(mouse_pos):
            return None
        if getattr(self, "_header_rect", None) and self._header_rect.collidepoint(mouse_pos):
            return {"type": "select_hero", "hero": self.hero_target}
        if self._end_button_rect and self._end_button_rect.collidepoint(mouse_pos):
            return "end_conversation"
        return None

    def handle_keydown(self, event: pygame.event.Event) -> str | None:
        if not self.is_active():
            return None
        if event.key == pygame.K_ESCAPE:
            return "end_conversation"
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self._input_text.strip():
                text = self._input_text.strip()
                self._input_text = ""
                self.send_message(text)
                return "send_message"
            return None
        if event.key == pygame.K_BACKSPACE:
            self._input_text = self._input_text[:-1]
            return None
        if hasattr(event, "unicode") and event.unicode and ord(event.unicode) >= 32:
            self._input_text += event.unicode
            if len(self._input_text) > 200:
                self._input_text = self._input_text[:200]
            return None
        return None

    def handle_generic_keydown(self, key: str | None, mods: dict | None) -> str | None:
        """Handle KEYDOWN when no pygame ``raw_event`` (e.g. Ursina InputEvent). Consumes game hotkeys."""
        if not self.is_active():
            return None
        mods = mods or {}
        k = (key or "").strip().lower()
        if k in ("esc", "escape"):
            return "end_conversation"
        if k in ("enter", "return"):
            if self._input_text.strip():
                text = self._input_text.strip()
                self._input_text = ""
                self.send_message(text)
                return "send_message"
            return None
        if k == "backspace":
            self._input_text = self._input_text[:-1]
            return None
        if k == "tab":
            return None
        if k == "space":
            self._input_text += " "
            if len(self._input_text) > 200:
                self._input_text = self._input_text[:200]
            return None
        if len(k) == 1:
            ch = k
            if ch.isalpha() and mods.get("shift"):
                ch = ch.upper()
            self._input_text += ch
            if len(self._input_text) > 200:
                self._input_text = self._input_text[:200]
            return None
        return None
