"""
Dev Tools overlay: real-time AI/LLM log stream (WK18).

Consumes events emitted by Agent 12's data tap (llm_request, llm_response).
Togglable via F4. Color-coded: request = blue, response = green, error = red.
"""

from __future__ import annotations

import pygame

from game.events import GameEventType


# Max lines to keep in memory; truncate display per line
MAX_LINES = 200
# Removed MAX_LINE_CHARS as we now wrap text

class DevToolsPanel:
    """Togglable overlay showing a scrolling stream of LLM request/response log entries."""

    def __init__(self, event_bus, screen_width: int, screen_height: int) -> None:
        self._event_bus = event_bus
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.visible = False
        self._raw_lines: list[dict] = []  # {"kind": "request"|"response"|"error", "text": str}
        self._wrapped_lines: list[dict] = []
        self._panel_w = 420
        self._panel_h = 280
        self._font = pygame.font.Font(None, 14)
        self._frame_outer = (0x14, 0x14, 0x19)
        self._frame_inner = (0x50, 0x50, 0x64)
        self._color_request = (120, 160, 220)
        self._color_response = (100, 200, 120)
        self._color_error = (220, 100, 100)
        self._color_info = (180, 180, 180)
        
        self._scroll_y = 0
        self._is_dragging_scrollbar = False
        self._is_dragging_resize = False
        self._hover_scrollbar = False
        
        self._subscribe(event_bus)

    def _subscribe(self, event_bus) -> None:
        def on_event(event: dict) -> None:
            kind = (event.get("type") or "").strip()
            hero_key = event.get("hero_key", "")
            prefix = f"[{hero_key}] " if hero_key else ""
            if kind == GameEventType.LLM_PROMPT_SENT.value:
                prompt = (event.get("user_prompt") or event.get("text") or "")
                self._append("request", prefix + "REQ: " + prompt.strip())
            elif kind == GameEventType.LLM_RESPONSE_RECEIVED.value:
                if event.get("error"):
                    self._append("error", prefix + "ERR: " + str(event.get("error")).strip())
                else:
                    resp = (event.get("response_text") or event.get("text") or "")
                    self._append("response", prefix + "RSP: " + resp.strip())
            else:
                return

        event_bus.subscribe(GameEventType.LLM_PROMPT_SENT.value, on_event)
        event_bus.subscribe(GameEventType.LLM_RESPONSE_RECEIVED.value, on_event)

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        # Handle manual newlines first
        raw_lines = text.split("\n")
        lines = []
        for raw in raw_lines:
            words = raw.split(" ")
            current_line = []
            for word in words:
                test_line = " ".join(current_line + [word])
                if font.size(test_line)[0] <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                        current_line = [word]
                    else:
                        # Word itself is too long, just put it on its own line (it will clip)
                        lines.append(word)
            if current_line:
                lines.append(" ".join(current_line))
        return lines

    def _rebuild_wrapped_lines(self):
        self._wrapped_lines = []
        max_w = max(50, self._panel_w - 24) # 8 left padding, 16 right scrollbar spacing
        for raw in self._raw_lines:
            wrapped = self._wrap_text(raw["text"], self._font, max_w)
            for line in wrapped:
                self._wrapped_lines.append({"kind": raw["kind"], "text": line})

    def _append(self, kind: str, text: str) -> None:
        self._raw_lines.append({"kind": kind, "text": text})
        if len(self._raw_lines) > MAX_LINES:
            self._raw_lines.pop(0)
            
        # Optional: check if we are at bottom before rebuilding
        line_h = self._font.get_height() + 2
        content_h = max(1, self._panel_h - 32)
        num_visible = max(1, content_h // line_h)
        max_scroll_before = max(0, len(self._wrapped_lines) - num_visible)
        was_at_bottom = self._scroll_y >= max_scroll_before
        
        self._rebuild_wrapped_lines()
        
        max_scroll_after = max(0, len(self._wrapped_lines) - num_visible)
        if was_at_bottom:
            self._scroll_y = max_scroll_after

    def toggle(self) -> None:
        self.visible = not self.visible
        if self.visible:
            # Rebuild in case resizing happened while closed
            self._rebuild_wrapped_lines()
            line_h = self._font.get_height() + 2
            content_h = max(1, self._panel_h - 32)
            num_visible = max(1, content_h // line_h)
            max_scroll = max(0, len(self._wrapped_lines) - num_visible)
            self._scroll_y = max_scroll

    def on_resize(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        # Re-clamp panel size if window gets too small
        self._panel_w = max(200, min(self._panel_w, self.screen_width - 24))
        self._panel_h = max(100, min(self._panel_h, self.screen_height - 100))
        self._rebuild_wrapped_lines()

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process Raw pygame events. Return True to consume the event."""
        if not self.visible:
            return False

        margin = 12
        panel_x = max(margin, self.screen_width - self._panel_w - margin)
        panel_y = max(margin, self.screen_height - self._panel_h - margin - 80)
        rect = pygame.Rect(panel_x, panel_y, self._panel_w, self._panel_h)
        
        content_top = 28
        content_h = rect.height - content_top - 4
        line_h = self._font.get_height() + 2
        num_visible = max(1, content_h // line_h)
        max_scroll = max(0, len(self._wrapped_lines) - num_visible)
        
        resize_rect = pygame.Rect(rect.right - 16, rect.bottom - 16, 16, 16)
        scrollbar_rect = pygame.Rect(rect.right - 14, rect.y + content_top, 8, content_h)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if resize_rect.collidepoint(event.pos):
                    self._is_dragging_resize = True
                    return True
                elif scrollbar_rect.collidepoint(event.pos):
                    self._is_dragging_scrollbar = True
                    # Snap scroll
                    thumb_ratio = num_visible / max(1, len(self._wrapped_lines))
                    thumb_h = max(20, content_h * thumb_ratio)
                    mouse_y = event.pos[1] - (rect.y + content_top)
                    pct = mouse_y / max(1, content_h)
                    self._scroll_y = int(pct * max_scroll)
                    self._scroll_y = max(0, min(self._scroll_y, max_scroll))
                    return True
                elif rect.collidepoint(event.pos):
                    return True  # Consume click on panel
            elif hasattr(pygame, "MOUSEWHEEL") and event.type == pygame.MOUSEWHEEL:
                pass # Handled globally via MOUSEWHEEL event below
            elif event.button == 4: # Scroll Up (older pygame)
                if rect.collidepoint(event.pos):
                    self._scroll_y = max(0, self._scroll_y - 3)
                    return True
            elif event.button == 5: # Scroll Down (older pygame)
                if rect.collidepoint(event.pos):
                    self._scroll_y = min(max_scroll, self._scroll_y + 3)
                    return True

        elif hasattr(pygame, "MOUSEWHEEL") and event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if rect.collidepoint(mouse_pos):
                if event.y > 0:
                    self._scroll_y = max(0, self._scroll_y - 3)
                elif event.y < 0:
                    self._scroll_y = min(max_scroll, self._scroll_y + 3)
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                if self._is_dragging_resize or self._is_dragging_scrollbar:
                    self._is_dragging_resize = False
                    self._is_dragging_scrollbar = False
                    return True

        elif event.type == pygame.MOUSEMOTION:
            mouse_pos = event.pos
            self._hover_scrollbar = scrollbar_rect.collidepoint(mouse_pos)
            
            if self._is_dragging_resize:
                new_w = mouse_pos[0] - panel_x + 8
                new_h = mouse_pos[1] - panel_y + 8
                self._panel_w = max(200, min(new_w, self.screen_width - 24))
                self._panel_h = max(100, min(new_h, self.screen_height - 100))
                self._rebuild_wrapped_lines()
                # Keep scroll in bounds
                content_h_new = self._panel_h - content_top - 4
                num_visible_new = max(1, content_h_new // line_h)
                max_scroll_new = max(0, len(self._wrapped_lines) - num_visible_new)
                self._scroll_y = max(0, min(self._scroll_y, max_scroll_new))
                return True
            elif self._is_dragging_scrollbar:
                pct = (mouse_pos[1] - (rect.y + content_top)) / max(1, content_h)
                self._scroll_y = int(pct * max_scroll)
                self._scroll_y = max(0, min(self._scroll_y, max_scroll))
                return True

        return False

    def render(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        
        margin = 12
        panel_x = max(margin, self.screen_width - self._panel_w - margin)
        panel_y = max(margin, self.screen_height - self._panel_h - margin - 80)
        rect = pygame.Rect(panel_x, panel_y, self._panel_w, self._panel_h)
        
        line_h = self._font.get_height() + 2
        content_top = 28
        content_h = rect.height - content_top - 4
        num_visible = max(1, content_h // line_h)
        max_scroll = max(0, len(self._wrapped_lines) - num_visible)
        self._scroll_y = max(0, min(self._scroll_y, max_scroll))

        # Backdrop
        panel_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        panel_surf.fill((30, 30, 40, 240))
        pygame.draw.rect(panel_surf, self._frame_outer, (0, 0, rect.width, rect.height), 2)
        pygame.draw.rect(panel_surf, self._frame_inner, (1, 1, rect.width - 2, rect.height - 2), 1)
        
        # Title
        title = self._font.render("AI/LLM Log (F4 to toggle | Drag corner to resize)", True, (220, 220, 220))
        panel_surf.blit(title, (8, 6))
        # Divider
        pygame.draw.line(panel_surf, self._frame_inner, (8, 24), (rect.width - 8, 24), 1)
        
        # Resize handle
        pygame.draw.line(panel_surf, (150, 150, 150), (rect.width - 12, rect.height - 4), (rect.width - 4, rect.height - 12), 2)
        pygame.draw.line(panel_surf, (150, 150, 150), (rect.width - 8, rect.height - 4), (rect.width - 4, rect.height - 8), 2)

        # Content: show visible window
        start_idx = self._scroll_y
        y_off = content_top
        
        for i in range(start_idx, min(start_idx + num_visible, len(self._wrapped_lines))):
            entry = self._wrapped_lines[i]
            k = entry.get("kind", "info")
            if k == "request":
                color = self._color_request
            elif k == "response":
                color = self._color_response
            elif k == "error":
                color = self._color_error
            else:
                color = self._color_info
                
            text = entry.get("text", "")
            surf = self._font.render(text, True, color)
            panel_surf.blit(surf, (8, y_off))
            y_off += line_h

        # Scrollbar
        if max_scroll > 0:
            thumb_ratio = num_visible / max(1, len(self._wrapped_lines))
            thumb_h = max(20, content_h * thumb_ratio)
            track_y = content_top
            track_h = content_h
            
            thumb_y = track_y + (self._scroll_y / max_scroll) * (track_h - thumb_h)
            
            scrollbar_rect = pygame.Rect(rect.width - 14, track_y, 8, track_h)
            pygame.draw.rect(panel_surf, (50, 50, 60), scrollbar_rect)
            
            thumb_rect = pygame.Rect(rect.width - 14, thumb_y, 8, thumb_h)
            thumb_color = (150, 150, 160) if self._hover_scrollbar or self._is_dragging_scrollbar else (100, 100, 110)
            pygame.draw.rect(panel_surf, thumb_color, thumb_rect)

        surface.blit(panel_surf, (rect.x, rect.y))
