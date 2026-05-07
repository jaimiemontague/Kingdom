"""Heads-up display for game information."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.command_bar import CommandBar
from game.ui.hero_panel import HeroPanel
from game.ui.chat_panel import ChatPanel
from game.ui.interior_view_panel import InteriorViewPanel
from game.ui.micro_view_manager import MicroViewManager, ViewMode
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.speed_control import SpeedControlBar
from game.ui.theme import UITheme
from game.ui.top_bar import TopBar
from game.ui.hero_panel import truncate_panel_line
from game.ui.pin_slot import PinSlot
from game.ui.widgets import Button, HPBar, NineSlice, Panel, TextLabel

COLOR_PIN_GOLD = (220, 180, 50)
RECALL_BTN_W = 180
MEMORIAL_BTN_W = 90
WATCH_CARD_HEADER_H = 18
WATCH_CARD_MAP_H = 160
WATCH_CARD_STATS_H = 110
WATCH_CARD_FULL_H = WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H
LEFT_COL_W = 224
WATCH_MINIMAP_SIZE = LEFT_COL_W


def world_to_radar(
    wx: float, wy: float, inner: pygame.Rect, world_w: int, world_h: int
) -> tuple[int, int]:
    """Map a world-pixel coordinate to a radar minimap pixel coordinate (WK52)."""
    mx = inner.x + int(wx / world_w * inner.width)
    my = inner.y + int(wy / world_h * inner.height)
    mx = max(inner.left, min(inner.right - 1, mx))
    my = max(inner.top, min(inner.bottom - 1, my))
    return (mx, my)


class HUD:
    """Displays game information to the player."""

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.theme = UITheme()

        self._frame_outer = (0x14, 0x14, 0x19)
        self._frame_inner = (0x50, 0x50, 0x64)
        self._frame_highlight = (0x6B, 0x6B, 0x84)

        self.top_bar_height = int(getattr(self.theme, "top_bar_h", 48))
        self.bottom_bar_height = int(getattr(self.theme, "bottom_bar_h", 96))
        self.side_panel_width = 360

        self.font_large = pygame.font.Font(None, 32)
        self.font_medium = pygame.font.Font(None, 24)
        self.font_small = pygame.font.Font(None, 18)
        self.font_tiny = pygame.font.Font(None, 16)

        self.show_help = False
        self._help_panel_cache: pygame.Surface | None = None
        self._help_hint_cache = self.font_small.render("F3: Help", True, (180, 180, 180))
        self.right_panel_visible = False
        self._panel_hint_cache = self.font_small.render("Tab: Panel", True, (180, 180, 180))

        self._session_start_ms = int(sim_now_ms())
        self._bounty_hint_cache: pygame.Surface | None = None
        self._last_placing = None
        self._placing_banner_cache: pygame.Surface | None = None

        self._panel_tex_top = "assets/ui/kingdomsim_ui_cc0/panels/panel_top.png"
        self._panel_tex_bottom = "assets/ui/kingdomsim_ui_cc0/panels/panel_bottom.png"
        self._panel_tex_right = "assets/ui/kingdomsim_ui_cc0/panels/panel_right.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_tex_pressed = "assets/ui/kingdomsim_ui_cc0/buttons/button_pressed.png"
        self._panel_slice_border = 8
        self._button_slice_border = 6
        self._topbar_sep_color = (70, 70, 90)

        self._panel_top = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_top,
            slice_border=self._panel_slice_border,
        )
        self._panel_bottom = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_bottom,
            slice_border=self._panel_slice_border,
        )
        self._panel_right = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_right,
            slice_border=self._panel_slice_border,
        )
        self._panel_left = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_top,  # Top panel texture serves fine for blocky 9-slices
            slice_border=self._panel_slice_border,
        )
        self._panel_minimap = Panel(
            pygame.Rect(0, 0, 1, 1),
            self.theme.panel_bg,
            self._frame_outer,
            alpha=int(self.theme.panel_alpha),
            border_w=2,
            inner_border_rgb=self._frame_inner,
            inner_border_w=1,
            highlight_rgb=self._frame_highlight,
            highlight_w=1,
            texture_path=self._panel_tex_bottom,
            slice_border=self._panel_slice_border,
        )

        self._top_bar = TopBar(
            self.theme,
            frame_outer=self._frame_outer,
            sep_color=self._topbar_sep_color,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            button_slice_border=self._button_slice_border,
        )
        self._command_bar = CommandBar(
            self.theme,
            frame_inner=self._frame_inner,
            frame_outer=self._frame_outer,
            frame_highlight=self._frame_highlight,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            button_slice_border=self._button_slice_border,
        )
        self._speed_bar = SpeedControlBar(
            self.theme,
            frame_outer=self._frame_outer,
            frame_inner=self._frame_inner,
            frame_highlight=self._frame_highlight,
        )
        self._hero_panel = HeroPanel(
            self.theme,
            frame_inner=self._frame_inner,
            frame_highlight=self._frame_highlight,
        )
        self._interior_panel = InteriorViewPanel(
            self.theme,
            frame_outer=self._frame_outer,
            frame_highlight=self._frame_highlight,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
        )
        self._quest_panel = QuestViewPanel(self.theme)
        self._chat_panel = ChatPanel(self.theme)
        self._right_close_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="X",
            font=self.theme.font_small,
            enabled=True,
        )

        self.quit_rect: pygame.Rect | None = None
        self.right_close_rect: pygame.Rect | None = None
        self.left_close_rect: pygame.Rect | None = None
        self._right_rect: pygame.Rect | None = None
        self._micro_view = MicroViewManager()
        self._speed_rect: pygame.Rect | None = None
        self.messages: list[dict] = []
        self.message_duration = 3000

        self._pin_slot = PinSlot()
        self.pin_button_rect: pygame.Rect | None = None
        self.recall_rect: pygame.Rect | None = None
        self._recall_label_sig: tuple[str, bool] | None = None
        self._recall_label_surf: pygame.Surface | None = None

        self._watch_card_expanded: bool = False
        self.watch_card_map_rect: pygame.Rect | None = None
        self._watch_card_rect: pygame.Rect | None = None
        self._recall_flash_end_ms: int = 0
        self.memorial_btn_rect: pygame.Rect | None = None

        self._watch_name_sig: tuple[str, int] | None = None
        self._watch_name_surf: pygame.Surface | None = None
        self._watch_chevron_surf: dict[str, pygame.Surface] = {}
        self._watch_stats_sig: tuple | None = None
        self._watch_hp_label_surf: pygame.Surface | None = None
        self._watch_xp_label_surf: pygame.Surface | None = None
        self._watch_lv_label_surf: pygame.Surface | None = None
        self._watch_mana_label_surf: pygame.Surface | None = None
        self._recall_fallen_overlay: pygame.Surface | None = None
        self._recall_flash_overlay: pygame.Surface | None = None
        self._recall_overlay_size: tuple[int, int] | None = None

        from game.ui.memorial_card import MemorialCard

        self.memorial_card = MemorialCard()
        self._pending_memorial = None
        self._memorial_shown_for: str = ""

        from game.ui.pin_alert_watcher import PinAlertWatcher

        self._alert_watcher = PinAlertWatcher(self._pin_slot, self)

    def _layout_rects_for_screen(
        self, w: int, h: int, *, show_right_panel: bool
    ) -> tuple[
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
    ]:
        """Geometry only — shared by _compute_layout and Ursina pointer routing."""
        top_h = int(getattr(self.theme, "top_bar_h", 48))
        bottom_h = int(getattr(self.theme, "bottom_bar_h", 96))
        margin = int(getattr(self.theme, "margin", 8))
        gutter = int(getattr(self.theme, "gutter", 8))

        if not show_right_panel:
            right_w = 0
        else:
            min_w = getattr(self.theme, "right_panel_min_w", LEFT_COL_W)
            max_w = getattr(self.theme, "right_panel_max_w", LEFT_COL_W + 16)
            right_w = int(max(min_w, min(max_w, int(w * 0.24))))
            right_w = int(max(min_w, min(right_w, w - 2 * margin)))

        top = pygame.Rect(0, 0, w, top_h)
        bottom = pygame.Rect(0, h - bottom_h, w, bottom_h)
        right = pygame.Rect(w - right_w, top_h, right_w, max(0, h - top_h - bottom_h))

        left_w = LEFT_COL_W
        minimap_size = WATCH_MINIMAP_SIZE
        minimap = pygame.Rect(0, h - minimap_size, minimap_size, minimap_size)

        cap_y = minimap.y
        if self._pin_slot.hero_id is not None:
            card_top = minimap.y - (
                WATCH_CARD_FULL_H if self._watch_card_expanded else WATCH_CARD_HEADER_H
            )
            cap_y = min(cap_y, card_top)
        left_h = max(0, cap_y - top_h)
        left = pygame.Rect(0, top_h, left_w, left_h)

        speed_bar_w = 200
        speed_bar_h = 50
        speed_gap_above_bar = 4
        speed_rect = pygame.Rect(
            (w - right_w) - speed_bar_w - margin - 100,
            bottom.y - speed_bar_h - speed_gap_above_bar,
            speed_bar_w,
            speed_bar_h,
        )

        btn_h = max(32, bottom_h - 2 * margin)
        btn_y = bottom.y + margin
        recall = pygame.Rect(minimap.right + gutter, btn_y, RECALL_BTN_W, btn_h)
        memorial = pygame.Rect(recall.right + gutter, btn_y, MEMORIAL_BTN_W, btn_h)
        cmd_x = memorial.right + gutter
        cmd_w = max(0, speed_rect.left - cmd_x - gutter)
        command = pygame.Rect(cmd_x, btn_y, cmd_w, btn_h)
        return top, bottom, left, right, minimap, command, speed_rect, recall, memorial

    def _compute_layout(
        self, surface: pygame.Surface
    ) -> tuple[
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
    ]:
        """Compute UI rects from current surface size. Returns top, bottom, left, right, minimap, command, speed_rect."""
        w, h = surface.get_width(), surface.get_height()
        self.screen_width = int(w)
        self.screen_height = int(h)
        show_right = getattr(self, "_show_right_panel", self.right_panel_visible)
        top, bottom, left, right, minimap, command, speed_rect, recall, memorial = self._layout_rects_for_screen(
            w, h, show_right_panel=show_right
        )
        self.side_panel_width = right.width
        return top, bottom, left, right, minimap, command, speed_rect, recall, memorial

    def virtual_pointer_in_hud_chrome(
        self, pos: tuple[int, int], surface: pygame.Surface, game_state: dict
    ) -> bool:
        """True if virtual-screen coords lie over HUD chrome (use UI pixel coords, not world raycast).

        Anti-aliased or icon pixels can have alpha < 24; alpha-only hit tests miss command buttons (e.g. Bounty).
        """
        x, y = int(pos[0]), int(pos[1])
        w, h = surface.get_width(), surface.get_height()
        if w <= 0 or h <= 0 or not (0 <= x < w and 0 <= y < h):
            return False
        has_right_content = self._micro_view.mode != ViewMode.OVERVIEW
        show_right = self.right_panel_visible and has_right_content
        top, bottom, left, right, minimap, command, speed_rect, recall, memorial = self._layout_rects_for_screen(
            w, h, show_right_panel=show_right
        )
        profiles = game_state.get("hero_profiles_by_id") or {}
        pin = self._pin_slot
        if pin.hero_id is not None:
            hero_alive = pin.hero_id in profiles
            pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))
        regions = [top, bottom, minimap, command, speed_rect]
        if pin.hero_id is not None:
            regions.append(recall)
            regions.append(memorial)
            ct = minimap.y - (WATCH_CARD_FULL_H if self._watch_card_expanded else WATCH_CARD_HEADER_H)
            regions.append(pygame.Rect(minimap.x, ct, minimap.width, WATCH_CARD_HEADER_H))
        if show_right and right.width > 0:
            regions.append(right)
        if game_state.get("selected_hero") is not None or game_state.get("selected_peasant") is not None:
            regions.append(left)
        for r in regions:
            if r.collidepoint(x, y):
                return True
        if self.show_help:
            help_r = pygame.Rect(max(0, w - 320), 0, min(320, w), min(520, h))
            if help_r.collidepoint(x, y):
                return True
        return False

    def _build_placing_banner(self, text_surf: pygame.Surface) -> pygame.Surface:
        pad_x = 14
        pad_y = 8
        width = text_surf.get_width() + pad_x * 2
        height = text_surf.get_height() + pad_y * 2
        banner = pygame.Surface((width, height), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, width, height)
        if not NineSlice.render(banner, rect, self._button_tex_hover, border=self._button_slice_border):
            banner.fill((40, 40, 55, 220))
            pygame.draw.rect(banner, self._frame_outer, rect, 2)
            inner = rect.inflate(-4, -4)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(banner, self._frame_inner, inner, 1)
        pygame.draw.line(banner, COLOR_GOLD, (4, 4), (width - 5, 4), 2)
        banner.blit(text_surf, (pad_x, pad_y))
        return banner

    def _draw_section_divider(self, surface: pygame.Surface, x: int, y: int, width: int) -> None:
        if width <= 0:
            return
        pygame.draw.line(surface, self._frame_inner, (x, y), (x + width, y), 1)
        pygame.draw.line(surface, self._frame_highlight, (x, y + 1), (x + width, y + 1), 1)

    def _peasant_action_label(self, peasant) -> str:
        """Return a short player-facing label for the peasant's current action."""
        if not getattr(peasant, "is_alive", True):
            return "Dead"
        state = getattr(peasant, "state", None)
        state_name = getattr(state, "name", str(state) if state else "") or ""
        target = getattr(peasant, "target_building", None)
        btype = ""
        if target is not None:
            btype = str(getattr(target, "building_type", getattr(target, "__class__", "").__name__) or "").replace("_", " ").title()
        if state_name == "DEAD":
            return "Dead"
        if state_name == "IN_CASTLE":
            return "Resting in castle"
        if state_name == "WORKING":
            if target is None:
                return "Working"
            constructed = getattr(target, "is_constructed", True)
            if not constructed:
                return f"Building ({btype})" if btype else "Building"
            return f"Repairing ({btype})" if btype else "Repairing"
        if state_name == "MOVING":
            if target is not None:
                return f"Going to {btype}" if btype else "Walking"
            return "Walking"
        return "Working" if state_name else "Idle"

    def _render_peasant_summary(self, surface: pygame.Surface, peasant, left_rect: pygame.Rect) -> None:
        """Render a compact peasant info block in the left panel (wk17)."""
        x = left_rect.x + int(self.theme.margin)
        y = left_rect.y + int(self.theme.margin)
        header_h = 26
        header_rect = pygame.Rect(left_rect.x + 4, y, left_rect.width - 8, header_h)
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
            "Peasant",
            (x, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            COLOR_WHITE,
            shadow_color=(20, 20, 30),
        )
        y = header_rect.bottom + 8
        self._draw_section_divider(surface, x, y, max(0, left_rect.width - int(self.theme.margin) * 2))
        y += 8
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Action",
            (x, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4
        action = self._peasant_action_label(peasant)
        TextLabel.render(
            surface,
            self.theme.font_body,
            action,
            (x, y),
            (220, 220, 220),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_body.get_height() + 8
        hp = int(getattr(peasant, "hp", 0) or 0)
        max_hp = max(1, int(getattr(peasant, "max_hp", 1) or 1))
        HPBar.render(
            surface,
            pygame.Rect(x, y, max(0, left_rect.width - int(self.theme.margin) * 2), 8),
            hp,
            max_hp,
            color_scheme={
                "bg": (60, 60, 60),
                "good": (80, 200, 100),
                "warn": (220, 180, 90),
                "bad": (220, 80, 80),
                "border": (20, 20, 25),
            },
        )

        # WK46 Stage 3: BuilderPeasant wood inventory (per-peasant, not a player resource).
        wood = getattr(peasant, "wood_inventory", None)
        req = getattr(peasant, "required_wood", None)
        if wood is not None or req is not None:
            y += 14
            TextLabel.render(
                surface,
                self.theme.font_small,
                "Wood",
                (x, y),
                (180, 180, 200),
                shadow_color=(20, 20, 30),
            )
            y += self.theme.font_small.get_height() + 4
            if wood is None:
                wood = 0
            if req is None:
                TextLabel.render(
                    surface,
                    self.theme.font_body,
                    f"{int(wood)}",
                    (x, y),
                    (220, 220, 220),
                    shadow_color=(20, 20, 30),
                )
            else:
                TextLabel.render(
                    surface,
                    self.theme.font_body,
                    f"{int(wood)} / {int(req)}",
                    (x, y),
                    (220, 220, 220),
                    shadow_color=(20, 20, 30),
                )

    def _render_right_panel_overview(
        self, surface: pygame.Surface, right: pygame.Rect, game_state: dict
    ) -> None:
        """Render OVERVIEW mode content: building summary, or empty hint (wk13 delegate from MicroViewManager)."""
        selected_building = game_state.get("selected_building")
        if selected_building is not None:
            self._render_building_summary(surface, selected_building, right)
        else:
            pad = self._right_panel_top_pad(right)
            TextLabel.render(
                surface,
                self.theme.font_body,
                "Select a building",
                (right.x + int(self.theme.margin), right.y + pad),
                (180, 180, 180),
            )

    def _right_panel_top_pad(self, rect: pygame.Rect) -> int:
        pad = int(self.theme.margin)
        if self.right_close_rect is not None and self.right_close_rect.colliderect(rect):
            pad = max(pad, int(self.right_close_rect.height) + int(self.theme.gutter))
        return pad

    def _render_right_close_button(self, surface: pygame.Surface, right_rect: pygame.Rect) -> None:
        x_surf = TextLabel.get_surface(self.theme.font_small, "X", (240, 240, 240))
        size = max(18, x_surf.get_height() + 6)
        self._right_close_button.rect = pygame.Rect(
            int(right_rect.right - size - 6),
            int(right_rect.y + 6),
            int(size),
            int(size),
        )
        self._right_close_button.text = "X"
        self._right_close_button.render(
            surface,
            pygame.mouse.get_pos(),
            texture_normal=self._button_tex_normal,
            texture_hover=self._button_tex_hover,
            texture_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
            bg_normal=(45, 45, 55),
            bg_hover=(60, 60, 70),
            bg_pressed=(70, 70, 85),
            border_outer=self._frame_outer,
            border_inner=self._frame_inner,
            border_highlight=self._frame_highlight,
            text_color=(240, 240, 240),
            text_shadow_color=(20, 20, 30),
        )
        self.right_close_rect = pygame.Rect(self._right_close_button.rect)

    def _render_left_close_button(self, surface: pygame.Surface, left_rect: pygame.Rect) -> None:
        if getattr(self, "_left_close_button", None) is None:
            self._left_close_button = Button(
                rect=pygame.Rect(0, 0, 1, 1),
                text="X",
                font=self.theme.font_small,
                enabled=True,
            )
        x_surf = TextLabel.get_surface(self.theme.font_small, "X", (240, 240, 240))
        size = max(18, x_surf.get_height() + 6)
        self._left_close_button.rect = pygame.Rect(
            int(left_rect.right - size - 6),
            int(left_rect.y + 6),
            int(size),
            int(size),
        )
        self._left_close_button.text = "X"
        self._left_close_button.render(
            surface,
            pygame.mouse.get_pos(),
            texture_normal=self._button_tex_normal,
            texture_hover=self._button_tex_hover,
            texture_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
            bg_normal=(45, 45, 55),
            bg_hover=(60, 60, 70),
            bg_pressed=(70, 70, 85),
            border_outer=self._frame_outer,
            border_inner=self._frame_inner,
            border_highlight=self._frame_highlight,
            text_color=(240, 240, 240),
            text_shadow_color=(20, 20, 30),
        )
        self.left_close_rect = pygame.Rect(self._left_close_button.rect)

    def _render_pin_button(self, surface: pygame.Surface, left_rect: pygame.Rect, game_state: dict) -> None:
        """WK51: small pin toggle to the left of the panel close button."""
        sel = game_state.get("selected_hero")
        if sel is None:
            self.pin_button_rect = None
            return
        pin_size = 20
        gap = 6
        x_surf = TextLabel.get_surface(self.theme.font_small, "X", (240, 240, 240))
        close_size = max(18, x_surf.get_height() + 6)
        close_x = int(left_rect.right - close_size - 6)
        pin_x = int(close_x - gap - pin_size)
        pin_y = int(left_rect.y + 6)
        self.pin_button_rect = pygame.Rect(pin_x, pin_y, pin_size, pin_size)
        pr = self.pin_button_rect
        sel_id = str(getattr(sel, "hero_id", "") or "")
        pinned = bool(sel_id and self._pin_slot.hero_id == sel_id)
        cx, cy = pr.centerx, pr.centery

        if not hasattr(self, "_pin_emoji_font") or getattr(self, "_pin_emoji_font_size", 0) != pin_size:
            try:
                self._pin_emoji_font = pygame.font.SysFont(
                    "segoeuiemoji,segoeui,noto color emoji,arial", pin_size
                )
            except Exception:
                self._pin_emoji_font = None
            self._pin_emoji_font_size = pin_size

        emoji_surf = None
        if self._pin_emoji_font is not None:
            try:
                emoji_surf = self._pin_emoji_font.render("\U0001f4cc", True, (255, 255, 255))
            except Exception:
                emoji_surf = None

        if emoji_surf is None or emoji_surf.get_width() <= 4:
            if pinned:
                pygame.draw.circle(surface, COLOR_PIN_GOLD, (cx, cy), pin_size // 2 - 1)
                pygame.draw.circle(surface, self._frame_outer, (cx, cy), pin_size // 2 - 1, 2)
                col = (255, 255, 255)
            else:
                pygame.draw.circle(surface, self._frame_inner, (cx, cy), pin_size // 2 - 1, 2)
                col = (150, 150, 160)
            p_surf = TextLabel.get_surface(self.theme.font_small, "P", col)
            surface.blit(p_surf, (cx - p_surf.get_width() // 2, cy - p_surf.get_height() // 2))
            return

        dest_pos = (
            cx - emoji_surf.get_width() // 2,
            cy - emoji_surf.get_height() // 2,
        )
        if pinned:
            surface.blit(emoji_surf, dest_pos)
        else:
            s = emoji_surf.copy()
            s.set_alpha(128)
            surface.blit(s, dest_pos)

    def trigger_recall_flash(self) -> None:
        """Flash the Recall button red (WK52). Called by PinAlertWatcher."""
        self._recall_flash_end_ms = int(sim_now_ms()) + 750

    def _render_watch_card_chrome(
        self,
        surface: pygame.Surface,
        minimap_rect: pygame.Rect,
        game_state: dict,
    ) -> None:
        """Watch card above minimap: header, optional map slot + stats (WK52)."""
        self.watch_card_map_rect = None
        self._watch_card_rect = None
        pin = self._pin_slot
        if pin.hero_id is None:
            return

        profiles = game_state.get("hero_profiles_by_id") or {}
        prof = profiles.get(pin.hero_id)

        cw = minimap_rect.width
        ch = WATCH_CARD_FULL_H if self._watch_card_expanded else WATCH_CARD_HEADER_H
        cx = minimap_rect.x
        cy = minimap_rect.y - ch
        card_rect = pygame.Rect(cx, cy, cw, ch)
        self._watch_card_rect = card_rect

        pygame.draw.rect(surface, (18, 18, 28), card_rect, border_radius=4)
        pygame.draw.rect(surface, (70, 65, 90), card_rect, width=1, border_radius=4)

        header_rect = pygame.Rect(cx, cy, cw, WATCH_CARD_HEADER_H)
        pygame.draw.rect(surface, (35, 30, 50), header_rect, border_radius=4)
        pygame.draw.line(
            surface,
            (70, 65, 90),
            (cx, cy + WATCH_CARD_HEADER_H - 1),
            (cx + cw, cy + WATCH_CARD_HEADER_H - 1),
        )

        chevron = "▲" if self._watch_card_expanded else "▼"
        chevron_surf = self._watch_chevron_surf.get(chevron)
        if chevron_surf is None:
            chevron_surf = self.font_tiny.render(chevron, True, (160, 155, 180))
            self._watch_chevron_surf[chevron] = chevron_surf

        raw_name = pin.pinned_name or "Hero"
        name_max_w = cw - chevron_surf.get_width() - 6
        name_sig = (raw_name, name_max_w)
        if self._watch_name_sig != name_sig or self._watch_name_surf is None:
            name = raw_name
            name_surf = self.font_tiny.render(name, True, (200, 195, 220))
            while name_surf.get_width() > name_max_w and len(name) > 2:
                name = name[:-1]
                name_surf = self.font_tiny.render(name + "…", True, (200, 195, 220))
            self._watch_name_sig = name_sig
            self._watch_name_surf = name_surf
        name_surf = self._watch_name_surf
        surface.blit(name_surf, (cx + 3, cy + (WATCH_CARD_HEADER_H - name_surf.get_height()) // 2))
        surface.blit(
            chevron_surf,
            (cx + cw - chevron_surf.get_width() - 2, cy + (WATCH_CARD_HEADER_H - chevron_surf.get_height()) // 2),
        )

        if not self._watch_card_expanded:
            return

        map_rect = pygame.Rect(cx + 2, cy + WATCH_CARD_HEADER_H, cw - 4, WATCH_CARD_MAP_H)
        pygame.draw.rect(surface, (8, 10, 16), map_rect)
        self.watch_card_map_rect = map_rect

        sy = cy + WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + 4
        bar_w = cw - 10
        bar_h = 6

        if prof is not None:
            vitals = getattr(prof, "vitals", None)
            prog = getattr(prof, "progression", None)
            idn = getattr(prof, "identity", None)

            hp = int(getattr(vitals, "hp", 0) if vitals else 0)
            max_hp = int(getattr(vitals, "max_hp", 1) if vitals else 1)
            xp = int(getattr(prog, "xp", 0) if prog else 0)
            xp_to_lv = int(getattr(prog, "xp_to_level", 100) if prog else 100)
            level = int(getattr(idn, "level", 1) if idn else 1)

            stats_sig = (hp, max_hp, xp, xp_to_lv, level)
            if self._watch_stats_sig != stats_sig or self._watch_hp_label_surf is None:
                self._watch_stats_sig = stats_sig
                self._watch_hp_label_surf = self.font_tiny.render(
                    f"HP {hp}/{max_hp}", True, (190, 190, 190)
                )
                self._watch_xp_label_surf = self.font_tiny.render(
                    f"XP {xp}/{xp_to_lv}", True, (190, 190, 190)
                )
                self._watch_lv_label_surf = self.font_tiny.render(
                    f"Lv {level}", True, (220, 200, 120)
                )

            hp_lbl = self._watch_hp_label_surf
            surface.blit(hp_lbl, (cx + 4, sy))
            sy += hp_lbl.get_height() + 1
            HPBar.render(surface, pygame.Rect(cx + 4, sy, bar_w, bar_h), hp, max_hp)
            sy += bar_h + 4

            xp_lbl = self._watch_xp_label_surf
            surface.blit(xp_lbl, (cx + 4, sy))
            sy += xp_lbl.get_height() + 1
            xp_ratio = max(0.0, min(1.0, xp / max(1, xp_to_lv)))
            pygame.draw.rect(surface, (40, 40, 55), pygame.Rect(cx + 4, sy, bar_w, bar_h))
            if xp_ratio > 0:
                pygame.draw.rect(
                    surface, (70, 130, 210), pygame.Rect(cx + 4, sy, int(bar_w * xp_ratio), bar_h)
                )
            pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(cx + 4, sy, bar_w, bar_h), 1)
            sy += bar_h + 4

            lv_lbl = self._watch_lv_label_surf
            surface.blit(lv_lbl, (cx + 4, sy))
            sy += lv_lbl.get_height() + 3

        if self._watch_mana_label_surf is None:
            self._watch_mana_label_surf = self.font_tiny.render(
                "Mana: —", True, (80, 78, 95)
            )
        surface.blit(self._watch_mana_label_surf, (cx + 4, sy))

    def _render_radar_minimap(
        self,
        surface: pygame.Surface,
        minimap_rect: pygame.Rect,
        game_state: dict,
    ) -> None:
        """Colored entity dots in bottom-bar minimap (WK52)."""
        from config import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE

        world_w = MAP_WIDTH * TILE_SIZE
        world_h = MAP_HEIGHT * TILE_SIZE
        inner = minimap_rect.inflate(-6, -6)
        if inner.width <= 0 or inner.height <= 0:
            return

        pygame.draw.rect(surface, (12, 14, 22), inner)

        world = game_state.get("world")
        heroes = game_state.get("heroes") or []
        enemies = game_state.get("enemies") or []
        buildings = game_state.get("buildings") or []
        pin = self._pin_slot

        def to_radar(wx: float, wy: float) -> tuple[int, int]:
            return world_to_radar(wx, wy, inner, world_w, world_h)

        def is_revealed(x: float, y: float) -> bool:
            if world is None:
                return True
            try:
                from game.world import Visibility

                gx, gy = world.world_to_grid(float(x), float(y))
                if 0 <= gx < world.width and 0 <= gy < world.height:
                    return world.visibility[gy][gx] != Visibility.HIDDEN
            except Exception:
                pass
            return True

        for b in buildings:
            bx, by = getattr(b, "x", None), getattr(b, "y", None)
            if bx is None:
                sz = getattr(b, "size", (1, 1))
                bx = (getattr(b, "grid_x", 0) + sz[0] / 2) * TILE_SIZE
            if by is None:
                sz = getattr(b, "size", (1, 1))
                by = (getattr(b, "grid_y", 0) + sz[1] / 2) * TILE_SIZE
            if not is_revealed(float(bx), float(by)):
                continue
            btype = str(getattr(b, "building_type", "") or "").lower()
            is_lair = bool(getattr(b, "is_lair", False)) or "lair" in btype or "crypt" in btype
            rx, ry = to_radar(float(bx), float(by))
            if btype == "castle":
                pygame.draw.rect(surface, (220, 220, 220), pygame.Rect(rx - 3, ry - 3, 6, 6), 1)
            elif is_lair:
                pygame.draw.circle(surface, (140, 30, 30), (rx, ry), 2)
            elif "guild" in btype or btype in (
                "warrior_guild",
                "ranger_guild",
                "rogue_guild",
                "wizard_guild",
            ):
                pygame.draw.circle(surface, (50, 180, 180), (rx, ry), 2)
            else:
                pygame.draw.circle(surface, (80, 100, 160), (rx, ry), 2)

        for en in enemies:
            ex, ey = float(getattr(en, "x", 0.0)), float(getattr(en, "y", 0.0))
            if int(getattr(en, "hp", 1)) <= 0:
                continue
            if not is_revealed(ex, ey):
                continue
            rx, ry = to_radar(ex, ey)
            pygame.draw.circle(surface, (200, 50, 50), (rx, ry), 2)

        pinned_pos = None
        for h in heroes:
            hx, hy = float(getattr(h, "x", 0.0)), float(getattr(h, "y", 0.0))
            if int(getattr(h, "hp", 1)) <= 0:
                continue
            if not is_revealed(hx, hy):
                continue
            rx, ry = to_radar(hx, hy)
            hid = str(getattr(h, "hero_id", "") or "")
            if pin.hero_id and hid == pin.hero_id:
                pinned_pos = (rx, ry)
            else:
                pygame.draw.circle(surface, (220, 180, 50), (rx, ry), 2)

        if pinned_pos is not None:
            px, py = pinned_pos
            pygame.draw.circle(surface, (255, 255, 255), (px, py), 4, 1)
            pygame.draw.circle(surface, (220, 180, 50), (px, py), 3)

        pygame.draw.rect(surface, (60, 65, 80), inner, 1)

    def _render_memorial_button(
        self, surface: pygame.Surface, memorial_rect: pygame.Rect, game_state: dict
    ) -> None:
        """Memorial opener when a fallen pin has a pending record."""
        self.memorial_btn_rect = None
        if self._pending_memorial is None:
            return
        if self.memorial_card.visible:
            return
        self.memorial_btn_rect = pygame.Rect(memorial_rect)
        NineSlice.render(
            surface, memorial_rect, self._button_tex_normal, border=self._button_slice_border
        )
        lbl = self.theme.font_small.render(f"{chr(9904)} Memorial", True, (200, 180, 130))
        surface.blit(
            lbl,
            (
                memorial_rect.x + (memorial_rect.width - lbl.get_width()) // 2,
                memorial_rect.y + (memorial_rect.height - lbl.get_height()) // 2,
            ),
        )

    def _render_recall_button(self, surface: pygame.Surface, recall_rect: pygame.Rect, game_state: dict) -> None:
        """WK51: bottom-bar recall when a hero is pinned."""
        profiles = game_state.get("hero_profiles_by_id") or {}
        pin = self._pin_slot
        if pin.hero_id is None:
            self.recall_rect = None
            return
        hero_alive = pin.hero_id in profiles
        pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))
        if pin.hero_id is None:
            self.recall_rect = None
            return
        self.recall_rect = pygame.Rect(recall_rect)
        prof = profiles.get(pin.hero_id)
        name = "Hero"
        if prof is not None:
            idn = getattr(prof, "identity", None)
            if idn is not None:
                name = str(getattr(idn, "name", "Hero"))
        fallen = pin.is_fallen()
        label = f"{name} (fallen)" if fallen else f"\u21a9 {truncate_panel_line(name, max_chars=14)}"
        sig = (str(pin.hero_id), fallen, label)
        if self._recall_label_sig != sig or self._recall_label_surf is None:
            self._recall_label_sig = sig
            col = (160, 160, 165) if fallen else (240, 240, 240)
            self._recall_label_surf = self.theme.font_small.render(label, True, col)
        tex = self._button_tex_pressed if fallen else self._button_tex_normal
        NineSlice.render(surface, recall_rect, tex, border=self._button_slice_border)

        size = (recall_rect.width, recall_rect.height)
        if self._recall_overlay_size != size:
            self._recall_overlay_size = size
            self._recall_fallen_overlay = pygame.Surface(size, pygame.SRCALPHA)
            self._recall_fallen_overlay.fill((40, 40, 50, 150))
            self._recall_flash_overlay = pygame.Surface(size, pygame.SRCALPHA)
            self._recall_flash_overlay.fill((220, 30, 30, 140))

        if fallen and self._recall_fallen_overlay is not None:
            surface.blit(self._recall_fallen_overlay, recall_rect.topleft)
        if self._recall_label_surf is not None:
            lw, lh = self._recall_label_surf.get_size()
            surface.blit(
                self._recall_label_surf,
                (
                    recall_rect.x + (recall_rect.width - lw) // 2,
                    recall_rect.y + (recall_rect.height - lh) // 2,
                ),
            )
        now = int(sim_now_ms())
        if now < self._recall_flash_end_ms:
            elapsed = max(0, now - (self._recall_flash_end_ms - 750))
            pulse = elapsed // 250
            if pulse % 2 == 0 and self._recall_flash_overlay is not None:
                surface.blit(self._recall_flash_overlay, recall_rect.topleft)

    def _render_building_summary(self, surface: pygame.Surface, building, rect: pygame.Rect) -> None:
        x = rect.x + int(self.theme.margin)
        y = rect.y + self._right_panel_top_pad(rect)
        btype = str(getattr(building, "building_type", building.__class__.__name__) or "")
        header_h = 28
        header_rect = pygame.Rect(rect.x + 6, rect.y + int(self.theme.margin) - 4, rect.width - 12, header_h)
        pygame.draw.rect(surface, (35, 35, 45), header_rect)
        pygame.draw.rect(surface, self._frame_inner, header_rect, 1)
        pygame.draw.line(
            surface,
            self._frame_highlight,
            (header_rect.left + 1, header_rect.top + 1),
            (header_rect.right - 2, header_rect.top + 1),
            1,
        )
        title = btype.replace("_", " ").title()
        TextLabel.render(
            surface,
            self.theme.font_title,
            title,
            (x, header_rect.y + (header_rect.height - self.theme.font_title.get_height()) // 2),
            COLOR_WHITE,
            shadow_color=(20, 20, 30),
        )
        y = header_rect.bottom + 6
        self._draw_section_divider(surface, x, y, int(rect.width - int(self.theme.margin) * 2))
        y += 6
        TextLabel.render(
            surface,
            self.theme.font_small,
            "Status",
            (x, y),
            (180, 180, 200),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_small.get_height() + 4
        hp = int(getattr(building, "hp", 0) or 0)
        max_hp = int(getattr(building, "max_hp", 0) or 0)
        TextLabel.render(
            surface,
            self.theme.font_body,
            f"HP: {hp}/{max_hp}",
            (x, y),
            (220, 220, 220),
            shadow_color=(20, 20, 30),
        )
        y += self.theme.font_body.get_height() + 6
        HPBar.render(
            surface,
            pygame.Rect(x, y, max(0, rect.width - int(self.theme.margin) * 2), 8),
            hp,
            max(1, max_hp),
            color_scheme={
                "bg": (60, 60, 60),
                "good": (80, 200, 100),
                "warn": (220, 180, 90),
                "bad": (220, 80, 80),
                "border": (20, 20, 25),
            },
        )

    def _render_help(self, surface: pygame.Surface, origin: tuple[int, int]) -> None:
        x0, y0 = origin
        if self._help_panel_cache is None:
            pad = 10
            width = 300
            lines = [
                ("Controls (F3 to hide)", COLOR_GOLD),
                ("Build:", (200, 200, 200)),
                ("1 Warrior  2 Market  3 Ranger  4 Rogue  5 Wizard", COLOR_WHITE),
                ("6 Blacksmith  7 Inn  8 Trading Post", COLOR_WHITE),
                ("T Temple  G Gnome  E Elf  V Dwarf", COLOR_WHITE),
                ("U Guardhouse  Y Ballista  O Wizard Tower", COLOR_WHITE),
                ("F Fairgrounds  I Library  R Royal Gardens", COLOR_WHITE),
                ("Actions:", (200, 200, 200)),
                ("H Hire hero (select a built guild first)", COLOR_WHITE),
                ("B Bounty at mouse (cost=reward). Shift/Ctrl: bigger", COLOR_WHITE),
                ("P Use potion (selected hero)", COLOR_WHITE),
                ("View:", (200, 200, 200)),
                ("Space center castle  ESC pause/cancel", COLOR_WHITE),
                ("WASD pan  Wheel or +/- zoom  F1 debug  F2 perf", COLOR_WHITE),
            ]
            height = pad * 2 + len(lines) * 16 + 6
            panel = pygame.Surface((width, height), pygame.SRCALPHA)
            panel.fill((*COLOR_UI_BG, 235))
            pygame.draw.rect(panel, self._frame_outer, (0, 0, width, height), 2)
            inner = pygame.Rect(2, 2, width - 4, height - 4)
            if inner.width > 0 and inner.height > 0:
                pygame.draw.rect(panel, self._frame_inner, inner, 1)
                pygame.draw.line(
                    panel,
                    self._frame_highlight,
                    (inner.left + 1, inner.top + 1),
                    (inner.right - 2, inner.top + 1),
                    1,
                )
                pygame.draw.line(
                    panel,
                    self._frame_highlight,
                    (inner.left + 1, inner.top + 1),
                    (inner.left + 1, inner.bottom - 2),
                    1,
                )
            y = pad
            for text, color in lines:
                line = self.font_tiny.render(text, True, color)
                panel.blit(line, (pad, y))
                y += 16
            self._help_panel_cache = panel
        surface.blit(self._help_panel_cache, (x0, y0))

    def add_message(self, text: str, color: tuple[int, int, int] = COLOR_WHITE) -> None:
        self.messages.append({"text": text, "color": color, "time": pygame.time.get_ticks()})
        if len(self.messages) > 5:
            self.messages.pop(0)

    def update(self) -> None:
        current_time = pygame.time.get_ticks()
        self.messages = [msg for msg in self.messages if current_time - msg["time"] < self.message_duration]

    def toggle_help(self) -> None:
        self.show_help = not self.show_help

    def toggle_right_panel(self) -> None:
        self.right_panel_visible = not self.right_panel_visible

    def _render_hero_focus_profile(self, surface: pygame.Surface, rect: pygame.Rect, game_state: dict) -> None:
        """Top half of HERO_FOCUS mode: condensed profile/memory (WK49)."""
        hero = game_state.get("selected_hero")
        profile = game_state.get("selected_hero_profile")
        if hero is None:
            qh = getattr(self._micro_view, "quest_hero", None)
            hero = qh
        if hero is None:
            return
        self._hero_panel.render_focus_top(
            surface,
            rect,
            hero,
            hero_profile=profile,
        )

    def on_resize(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)

    def render_messages(self, surface: pygame.Surface, left_rect: pygame.Rect | None = None) -> None:
        y_offset = self.top_bar_height + 10
        x_offset = 10
        if left_rect and left_rect.width > 0:
            x_offset = left_rect.right + 10
        for msg in self.messages:
            text = self.font_small.render(msg["text"], True, msg["color"])
            surface.blit(text, (x_offset, y_offset))
            y_offset += 18

    def render(self, surface: pygame.Surface, game_state: dict) -> None:
        # Right panel vanishes when nothing is selected (maximize map view)
        # Fix: right menu shouldn't come up for building descriptions since left menu already shows it
        has_right_content = self._micro_view.mode != ViewMode.OVERVIEW
        self._show_right_panel = self.right_panel_visible and has_right_content

        top, bottom, left, right, minimap, cmd, speed_rect, recall, memorial = self._compute_layout(surface)

        _profiles = game_state.get("hero_profiles_by_id") or {}
        if self._pin_slot.hero_id:
            _pprof = _profiles.get(self._pin_slot.hero_id)
            if _pprof is not None:
                _idn = getattr(_pprof, "identity", None)
                if _idn is not None:
                    self._pin_slot.pinned_name = str(getattr(_idn, "name", "") or "")
        pin = self._pin_slot
        if pin.hero_id is not None:
            hero_alive = pin.hero_id in _profiles
            pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))
        if (
            pin.is_fallen()
            and pin.hero_id is not None
            and pin.hero_id != self._memorial_shown_for
        ):
            _pprof = _profiles.get(pin.hero_id)
            if _pprof is not None:
                from game.ui.memorial_card import MemorialRecord

                _career = getattr(_pprof, "career", None)
                _idn = getattr(_pprof, "identity", None)
                self._pending_memorial = MemorialRecord(
                    hero_id=str(pin.hero_id),
                    name=str(getattr(_idn, "name", pin.pinned_name) if _idn else pin.pinned_name),
                    hero_class=str(getattr(_idn, "hero_class", "hero") if _idn else "hero"),
                    level=int(getattr(_idn, "level", 1) if _idn else 1),
                    enemies_defeated=int(getattr(_career, "enemies_defeated", 0) if _career else 0),
                    bounties_claimed=int(getattr(_career, "bounties_claimed", 0) if _career else 0),
                    gold_earned=int(getattr(_career, "gold_earned", 0) if _career else 0),
                )
                self._memorial_shown_for = str(pin.hero_id)
        self._alert_watcher.check_low_health(_profiles, int(sim_now_ms()))

        self._panel_top.set_rect(top)
        self._panel_bottom.set_rect(bottom)
        self._panel_left.set_rect(left)
        self._panel_right.set_rect(right)
        self._panel_minimap.set_rect(minimap)
        self._panel_top.render(surface)
        self._panel_bottom.render(surface)

        selected_hero = game_state.get("selected_hero")
        selected_peasant = game_state.get("selected_peasant")
        self.left_close_rect = None
        if selected_hero is not None:
            self._panel_left.render(surface)
            self._hero_panel.render(
                surface,
                selected_hero,
                left,
                right_close_rect=None,
                debug_ui=bool(game_state.get("debug_ui", False)),
                hero_profile=game_state.get("selected_hero_profile"),
            )
            # Pin + close must render after HeroPanel header fill or they are painted over (WK51 r6).
            self._render_pin_button(surface, left, game_state)
            self._render_left_close_button(surface, left)
        elif selected_peasant is not None:
            self._panel_left.render(surface)
            self._render_left_close_button(surface, left)
            self._render_peasant_summary(surface, selected_peasant, left)

        if self._show_right_panel:
            self._panel_right.render(surface)

        self._panel_minimap.render(surface)
        self._render_radar_minimap(surface, minimap, game_state)
        self._render_watch_card_chrome(surface, minimap, game_state)

        if minimap.width > 0 and minimap.height > 0:
            sep_x = minimap.right + int(self.theme.gutter // 2)
            pygame.draw.line(surface, self._frame_outer, (sep_x, bottom.y + 8), (sep_x, bottom.bottom - 8), 2)

        self._render_recall_button(surface, recall, game_state)
        self._render_memorial_button(surface, memorial, game_state)

        self.quit_rect = self._top_bar.render(surface, top, game_state)

        placing = game_state.get("placing_building_type")
        if placing != self._last_placing:
            self._last_placing = placing
            if placing:
                placing_name = str(placing).replace("_", " ").title()
                banner_text = f"Placing: {placing_name} (LMB: place, ESC: cancel)"
                text_surf = self.theme.font_body.render(banner_text, True, COLOR_WHITE)
                self._placing_banner_cache = self._build_placing_banner(text_surf)
            else:
                self._placing_banner_cache = None
        if self._placing_banner_cache is not None:
            bx = int(cmd.x + (cmd.width - self._placing_banner_cache.get_width()) // 2) if cmd.width > 0 else int(self.theme.margin)
            by = int(bottom.y - self._placing_banner_cache.get_height() - 6)
            surface.blit(self._placing_banner_cache, (bx, by))

        if self.show_help:
            self._render_help(surface, origin=(self.screen_width - 310, 5))

        try:
            now_ms = int(sim_now_ms())
            elapsed_ms = now_ms - int(self._session_start_ms)
            has_any_bounty = bool(game_state.get("bounties", []))
            if (not has_any_bounty) and elapsed_ms < 90000 and (not self.show_help):
                if self._bounty_hint_cache is None:
                    self._bounty_hint_cache = self.font_small.render(
                        "Tip: Press B to place a bounty at mouse (Shift/Ctrl: bigger).",
                        True,
                        (220, 220, 255),
                    )
                surface.blit(self._bounty_hint_cache, (20, self.top_bar_height + 28))
        except Exception:
            pass

        show_left = selected_hero is not None or selected_peasant is not None
        self.render_messages(surface, left if show_left else None)
        _cur = game_state.get("ui_cursor_pos")
        cursor_pos: tuple[int, int] | None
        if _cur is not None and len(_cur) >= 2:
            cursor_pos = (int(_cur[0]), int(_cur[1]))
        else:
            cursor_pos = pygame.mouse.get_pos()
        self._command_bar.render(surface, cmd, mouse_pos=cursor_pos)
        self._speed_bar.render(surface, speed_rect, cursor_pos)
        self._speed_rect = speed_rect

        selected_hero = game_state.get("selected_hero")
        selected_building = game_state.get("selected_building")
        self.right_close_rect = None
        if self._show_right_panel:
            self._right_rect = right
            interior_panel = getattr(self, "_interior_panel", None)
            quest_panel = getattr(self, "_quest_panel", None)
            chat_panel = getattr(self, "_chat_panel", None)
            exit_msg = self._micro_view.render(
                surface, right, game_state, self, interior_panel, quest_panel, chat_panel
            )
            self._render_right_close_button(surface, right)
            if exit_msg:
                self.add_message(exit_msg, (255, 180, 100))
        else:
            self._right_rect = None

        if self.memorial_card.visible:
            self.memorial_card.render(surface)

    def handle_click(self, mouse_pos: tuple[int, int], game_state: dict) -> str | None:
        x = int(mouse_pos[0])
        y = int(mouse_pos[1])
        profiles = game_state.get("hero_profiles_by_id") or {}
        pin = self._pin_slot
        if pin.hero_id is not None:
            hero_alive = pin.hero_id in profiles
            pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))

        if self.memorial_card.visible:
            if self.memorial_card.handle_click((x, y)):
                return "close_memorial_unpause"
            return None

        if self.quit_rect is not None and self.quit_rect.collidepoint((x, y)):
            return "quit"
        if self.right_close_rect is not None and self.right_close_rect.collidepoint((x, y)):
            return "close_selection"
        if getattr(self, "pin_button_rect", None) is not None and self.pin_button_rect.collidepoint((x, y)):
            sel = game_state.get("selected_hero")
            sel_id = str(getattr(sel, "hero_id", "") or "") if sel is not None else ""
            if not sel_id:
                return None
            if pin.hero_id == sel_id:
                return "unpin_hero"
            return "pin_hero"
        if (
            getattr(self, "_watch_card_rect", None) is not None
            and self._pin_slot.hero_id is not None
        ):
            header_rect = pygame.Rect(
                self._watch_card_rect.x,
                self._watch_card_rect.y,
                self._watch_card_rect.width,
                WATCH_CARD_HEADER_H,
            )
            if header_rect.collidepoint((x, y)):
                self._watch_card_expanded = not self._watch_card_expanded
                return None
        if (
            getattr(self, "memorial_btn_rect", None) is not None
            and self.memorial_btn_rect.collidepoint((x, y))
            and self._pending_memorial is not None
        ):
            self.memorial_card.show(self._pending_memorial)
            return "open_memorial"
        if self.left_close_rect is not None and self.left_close_rect.collidepoint((x, y)):
            return "close_selection"
        if self._right_rect is not None and self._right_rect.collidepoint((x, y)):
            interior_panel = getattr(self, "_interior_panel", None)
            quest_panel = getattr(self, "_quest_panel", None)
            chat_panel = getattr(self, "_chat_panel", None)
            if chat_panel is not None and chat_panel.is_active():
                # HERO_FOCUS renders chat in the bottom half only; hit-test must use the same rect.
                if self._micro_view.mode == ViewMode.HERO_FOCUS:
                    chat_hit_rect = pygame.Rect(
                        self._right_rect.x,
                        self._right_rect.y + self._right_rect.height // 2,
                        self._right_rect.width,
                        self._right_rect.height // 2,
                    )
                    click_result = chat_panel.handle_click((x, y), chat_hit_rect)
                else:
                    click_result = chat_panel.handle_click((x, y), self._right_rect)
                if click_result is not None:
                    return click_result
            action = self._micro_view.handle_click(
                (x, y), self._right_rect, interior_panel, quest_panel, chat_panel
            )
            if isinstance(action, dict) and action.get("type") == "start_conversation":
                return action
            if action == "exit_interior":
                return "exit_interior"
            if action == "exit_quest":
                return "exit_quest"
            if action == "exit_hero_focus":
                return "end_conversation"
        if getattr(self, "recall_rect", None) is not None and self.recall_rect.collidepoint((x, y)):
            if not pin.is_fallen():
                return "recall_pinned_hero"
            return None
        action = self._command_bar.handle_click((x, y))
        if action:
            return action
        if getattr(self, "_speed_rect", None) is not None and self._speed_bar.handle_click((x, y)):
            return None
        return None

