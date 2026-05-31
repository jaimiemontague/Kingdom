"""Heads-up display for game information."""

from __future__ import annotations

import pygame

from config import COLOR_GOLD, COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.command_bar import CommandBar
from game.ui.hero_panel import HeroPanel
from game.ui.enemy_panel import EnemyPanel
from game.ui.chat_panel import ChatPanel
from game.ui.hud_layout import (
    HERO_LEFT_MIN_H,
    HUDLayout,
    HUDLayoutManager,
    LEFT_COL_W,
    MEMORIAL_BTN_W,
    RADAR_MINIMAP_H,
    RADAR_MINIMAP_W,
    RECALL_BTN_W,
)
from game.ui.interior_view_panel import InteriorViewPanel
from game.ui.micro_view_manager import MicroViewManager, ViewMode
from game.ui.quest_view_panel import QuestViewPanel
from game.ui.speed_control import SpeedControlBar
from game.ui.theme import UITheme
from game.ui.top_bar import TopBar
from game.ui.pin_slot import PinSlot
from game.ui.info_card import InfoCard
from game.ui.ui_actions import UIAction, normalize_ui_action
from game.ui.widgets import Button, HPBar, NineSlice, Panel, TextLabel

# WATCH_CARD_* layout constants moved to game.ui.hud_watch_card (WK96); re-imported
# here so the names stay module attributes of hud — preserving
# `from game.ui.hud import WATCH_CARD_*` (tests/test_wk52_watch_card.py) and the
# bare-name references in the watch-card layout helpers that STAY on HUD.
from game.ui.hud_watch_card import (
    WATCH_CARD_HEADER_H,
    WATCH_CARD_MAP_H,
    WATCH_CARD_STATS_H,
    WATCH_CARD_STATS_COMPACT_H,
    WATCH_CARD_CHAT_H,
    WATCH_CARD_FULL_H_WITH_CHAT,
    WATCH_CARD_FULL_H_NO_CHAT,
    WATCH_CARD_FULL_H,
)
HERO_MENU_CHAT_GAP = 4
HERO_MENU_CHAT_MIN_H = 152
HERO_MENU_CHAT_PREFERRED_H = 220
HERO_MENU_HERO_MIN_H = 120
WATCH_MINIMAP_SIZE = LEFT_COL_W
LEFT_SPLIT_HANDLE_H = 4
LEFT_SPLIT_HANDLE_HIT_H = 8
LEFT_SPLIT_DEFAULT_FRAC_MAIN = 0.55
LEFT_SPLIT_DEFAULT_FRAC_WATCH = 0.45
LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO = 0.72


# world_to_radar moved to game.ui.hud_radar (WK93); re-exported here for the
# existing importers (tests/test_wk52_watch_card.py: `from game.ui.hud import world_to_radar`).
from game.ui.hud_radar import world_to_radar  # noqa: E402,F401


def building_display_name(building) -> str:
    """Human-readable building title for HUD chrome (WK52; avoids ``str(Enum)`` 'BuildingType.X' glitches)."""
    gd = getattr(building, "get_display_name", None)
    if callable(gd):
        try:
            name = gd()
            if name:
                return str(name)
        except Exception:
            pass
    dn = getattr(building, "display_name", None)
    if dn:
        return str(dn)
    bt = getattr(building, "building_type", None)
    if bt is None:
        cn = type(building).__name__.replace("Building", "").strip()
        return cn.title() if cn else "Building"
    key = getattr(bt, "value", bt)
    s = str(key)
    return s.replace("_", " ").title()


class HUD:
    """Displays game information to the player."""

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.theme = UITheme()
        self._layout_mgr = HUDLayoutManager()

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
        self._enemy_panel = EnemyPanel(
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
        self._watch_card_chevron_rect: pygame.Rect | None = None
        self.watch_card_map_world_center: tuple[float, float] | None = None
        self.watch_card_map_world_wh: tuple[float, float] | None = None
        self._watch_card_chat_rect: pygame.Rect | None = None
        self._radar_terrain_cache_key: tuple[int, int, int, int] | None = None
        self._radar_terrain_surface: pygame.Surface | None = None
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

        from game.ui.building_interior_overlay import BuildingInteriorOverlay

        self.building_interior_overlay = BuildingInteriorOverlay(
            self.theme,
            frame_outer=self._frame_outer,
            frame_highlight=self._frame_highlight,
            button_tex_normal=self._button_tex_normal,
            button_tex_hover=self._button_tex_hover,
            button_tex_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
        )

        from game.ui.demolish_confirm_overlay import DemolishConfirmOverlay

        self.demolish_confirm_overlay = DemolishConfirmOverlay()

        from game.ui.pin_alert_watcher import PinAlertWatcher

        self._alert_watcher = PinAlertWatcher(self._pin_slot, self)

        self._chat_visible: bool = False
        self._chat_close_rect: pygame.Rect | None = None
        self._chat_open_rect: pygame.Rect | None = None
        self._hero_menu_chat_rect: pygame.Rect | None = None
        self._hero_menu_hero_rect: pygame.Rect | None = None
        self._info_card = InfoCard()
        self._card_slot_kind: str | None = None
        self._last_left_rect: pygame.Rect | None = None
        self._left_split_fracs: dict[str, float] = {
            "main": LEFT_SPLIT_DEFAULT_FRAC_MAIN,
            "watch": LEFT_SPLIT_DEFAULT_FRAC_WATCH,
            "main_solo": LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
        }
        self._left_main_rect: pygame.Rect | None = None
        self._left_watch_rect: pygame.Rect | None = None
        self._left_split_handle_rects: dict[str, pygame.Rect] = {}
        self._left_split_drag_kind: str | None = None
        self._left_split_drag_start_y: int = 0
        self._left_split_drag_main_h0: int = 0
        self._left_split_drag_watch_h0: int = 0

        # POI discovery toast notifications (WK55/WK58)
        # Each toast: (message, remaining_ms, interaction_type)
        self._poi_toasts: list[tuple[str, float, str]] = []
        self._POI_TOAST_DURATION_MS = 4000  # milliseconds to show each toast
        self._POI_TOAST_FADE_MS = 500.0  # fade-in / fade-out duration
        self._poi_toast_ids: set[int] = set()  # track which POIs already triggered a toast
        self._poi_last_tick_ms: int = pygame.time.get_ticks()
        self._poi_toast_font: pygame.font.Font = pygame.font.Font(None, 26)  # slightly larger than font_small(18)

        # POI interaction toast subscriptions (lazy-bound to event bus on first render)
        self._poi_interaction_subscribed: bool = False

        # WK60: Wave event toast state (richer than plain hud_message)
        self._wave_toast_text: str | None = None
        self._wave_toast_color: tuple[int, int, int] = (255, 100, 100)
        self._wave_toast_start_ms: int = 0
        self._wave_toast_duration_ms: int = 4000
        self._wave_toast_countdown_end_ms: int = 0  # 0 = no countdown
        self._wave_toast_font: pygame.font.Font = pygame.font.Font(None, 30)

    # ------------------------------------------------------------------
    # WK60: Wave event toast API (consumed by engine EventBus subscription)
    # ------------------------------------------------------------------

    def on_wave_incoming(self, event: dict) -> None:
        from game.ui import hud_toasts
        return hud_toasts.on_wave_incoming(self, event)

    def on_wave_cleared(self, event: dict) -> None:
        from game.ui import hud_toasts
        return hud_toasts.on_wave_cleared(self, event)

    def _render_wave_toast(self, surface: pygame.Surface) -> None:
        from game.ui import hud_toasts
        return hud_toasts.render_wave_toast(self, surface)

    # ------------------------------------------------------------------
    # WK60 Feature 9: DEV MODE HUD label
    # ------------------------------------------------------------------

    def _render_dev_mode_label(self, surface: pygame.Surface) -> None:
        """Render '[DEV MODE]' label in the top-right when config.DEV_MODE is True."""
        from config import DEV_MODE
        if not DEV_MODE:
            return
        text_surf = self.font_small.render("[DEV MODE]", True, (255, 200, 60))
        tw = text_surf.get_size()[0]
        # Top-right corner, semi-transparent background
        x = surface.get_width() - tw - 12
        y = 6
        bg = pygame.Surface((tw + 8, 18), pygame.SRCALPHA)
        bg.fill((20, 20, 40, 140))
        surface.blit(bg, (x - 4, y - 2))
        surface.blit(text_surf, (x, y))

    def effective_card_full_h(self) -> int:
        from game.ui import hud_watch_card
        return hud_watch_card.effective_card_full_h(self)

    def notify_poi_discovered(self, poi_name: str, interaction_type: str = "") -> None:
        from game.ui import hud_toasts
        return hud_toasts.notify_poi_discovered(self, poi_name, interaction_type)

    def _check_poi_discoveries(self, game_state: dict) -> None:
        from game.ui import hud_toasts
        return hud_toasts.check_poi_discoveries(self, game_state)

    # ------------------------------------------------------------------
    # POI interaction toasts (WK59)
    # ------------------------------------------------------------------

    def _ensure_poi_interaction_subscription(self, game_state: dict) -> None:
        from game.ui import hud_toasts
        return hud_toasts.ensure_poi_interaction_subscription(self, game_state)

    def _on_poi_interaction(self, event: dict) -> None:
        from game.ui import hud_toasts
        return hud_toasts.on_poi_interaction(self, event)

    def _on_boss_spawned_toast(self, event: dict) -> None:
        from game.ui import hud_toasts
        return hud_toasts.on_boss_spawned_toast(self, event)

    def _render_poi_toasts(self, surface: pygame.Surface) -> None:
        from game.ui import hud_toasts
        return hud_toasts.render_poi_toasts(self, surface)

    def _desired_watch_card_expanded_h(self) -> int:
        from game.ui import hud_watch_card
        return hud_watch_card.desired_watch_card_expanded_h(self)

    def _effective_watch_card_h(self, screen_h: int) -> int:
        from game.ui import hud_watch_card
        return hud_watch_card.effective_watch_card_h(self, screen_h)

    def _watch_card_body_split(self, ch: int) -> tuple[int, int, int]:
        from game.ui import hud_watch_card
        return hud_watch_card.watch_card_body_split(self, ch)

    def _watch_chat_band_rect(
        self,
        cx: int,
        cy: int,
        cw: int,
        ch: int,
        map_h: int,
        stats_h: int,
        chat_h: int,
        profiles: dict,
        hero_id: str,
        painted_stats_bottom_override: int | None = None,
    ) -> pygame.Rect | None:
        from game.ui import hud_watch_card
        return hud_watch_card.watch_chat_band_rect(
            self, cx, cy, cw, ch, map_h, stats_h, chat_h, profiles, hero_id, painted_stats_bottom_override
        )

    def _left_column_segments_open(self, game_state: dict | None) -> tuple[bool, bool]:
        """Return (main_panel_open, watch_card_open) for left-column split layout."""
        gs = game_state or {}
        main_open = (
            gs.get("selected_hero") is not None
            or gs.get("selected_peasant") is not None
            or gs.get("selected_enemy") is not None
            or gs.get("selected_building") is not None
        )
        watch_open = self._pin_slot.hero_id is not None
        return main_open, watch_open

    def _normalized_left_split_fracs(self, main_open: bool, watch_open: bool) -> dict[str, float]:
        if main_open and not watch_open:
            solo = max(
                0.05,
                min(
                    0.95,
                    float(
                        self._left_split_fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
                    ),
                ),
            )
            return {"main_solo": solo}
        keys: list[str] = []
        if main_open:
            keys.append("main")
        if watch_open:
            keys.append("watch")
        if not keys:
            return {}
        raw = {k: max(0.05, float(self._left_split_fracs.get(k, 0.5))) for k in keys}
        total = sum(raw.values())
        return {k: raw[k] / total for k in keys}

    def _layout_left_column_segments(
        self,
        top_h: int,
        minimap: pygame.Rect,
        game_state: dict | None,
    ) -> tuple[pygame.Rect, pygame.Rect | None, pygame.Rect | None]:
        """Allocate main + watch rects above the fixed minimap using session split fractions."""
        available = max(0, minimap.y - top_h)
        main_open, watch_open = self._left_column_segments_open(game_state)
        self._left_main_rect = None
        self._left_watch_rect = None
        self._left_split_handle_rects = {}

        if available <= 0 or (not main_open and not watch_open):
            left = pygame.Rect(0, top_h, LEFT_COL_W, available)
            self._last_left_rect = left if main_open else None
            return left, None, None

        fracs = self._normalized_left_split_fracs(main_open, watch_open)
        main_h = watch_h = 0

        if main_open and watch_open:
            main_h = max(HERO_LEFT_MIN_H, int(round(fracs["main"] * available)))
            watch_h = available - main_h
            if watch_h < WATCH_CARD_HEADER_H:
                watch_h = WATCH_CARD_HEADER_H
                main_h = max(HERO_LEFT_MIN_H, available - watch_h)
            if main_h < HERO_LEFT_MIN_H:
                main_h = HERO_LEFT_MIN_H
                watch_h = max(WATCH_CARD_HEADER_H, available - main_h)
        elif main_open:
            if self._should_render_hero_menu_chat_popup(game_state or {}):
                main_h = available
            else:
                solo_frac = fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
                main_h = max(HERO_LEFT_MIN_H, int(round(float(solo_frac) * available)))
                main_h = min(main_h, available)
        else:
            watch_h = available

        main_rect: pygame.Rect | None = None
        watch_rect: pygame.Rect | None = None
        y = top_h

        if main_open:
            main_rect = pygame.Rect(0, y, LEFT_COL_W, main_h)
            self._left_main_rect = main_rect
            self._last_left_rect = main_rect
            if watch_open:
                divider = pygame.Rect(0, y + main_h - LEFT_SPLIT_HANDLE_H, LEFT_COL_W, LEFT_SPLIT_HANDLE_H)
                self._left_split_handle_rects["main_bottom"] = divider
                self._left_split_handle_rects["watch_top"] = divider
            else:
                solo_handle = pygame.Rect(
                    0,
                    y + main_h - LEFT_SPLIT_HANDLE_HIT_H,
                    LEFT_COL_W,
                    LEFT_SPLIT_HANDLE_HIT_H,
                )
                self._left_split_handle_rects["main_solo"] = solo_handle
            y += main_h

        if watch_open:
            watch_y = y if main_open else minimap.y - watch_h
            watch_rect = pygame.Rect(0, watch_y, LEFT_COL_W, watch_h)
            self._left_watch_rect = watch_rect
            bottom_handle = pygame.Rect(
                0, watch_y + watch_h - LEFT_SPLIT_HANDLE_H, LEFT_COL_W, LEFT_SPLIT_HANDLE_H
            )
            self._left_split_handle_rects["watch_bottom"] = bottom_handle
            if not main_open:
                self._last_left_rect = watch_rect

        left = main_rect or watch_rect or pygame.Rect(0, top_h, LEFT_COL_W, available)
        return left, main_rect, watch_rect

    def _render_left_split_handles(self, surface: pygame.Surface) -> None:
        """Draw thin resize bars on open left-column segment boundaries (WK61-R10)."""
        for key, rect in self._left_split_handle_rects.items():
            if rect.width <= 0 or rect.height <= 0:
                continue
            hover = key == self._left_split_drag_kind
            color = (120, 130, 160) if hover else (70, 78, 98)
            pygame.draw.rect(surface, color, rect)
            mid_y = rect.centery
            pygame.draw.line(
                surface,
                (150, 160, 190) if hover else (95, 105, 130),
                (rect.x + 8, mid_y),
                (rect.right - 8, mid_y),
                1,
            )

    def handle_sidebar_split_pointer_down(self, pos: tuple[int, int], game_state: dict) -> bool:
        """Begin dragging a left-column split handle; returns True if consumed."""
        if self._left_split_drag_kind is not None:
            return True
        x, y = int(pos[0]), int(pos[1])
        for key, rect in self._left_split_handle_rects.items():
            if rect.collidepoint(x, y):
                self._left_split_drag_kind = key
                self._left_split_drag_start_y = y
                self._left_split_drag_main_h0 = int(self._left_main_rect.height) if self._left_main_rect else 0
                self._left_split_drag_watch_h0 = int(self._left_watch_rect.height) if self._left_watch_rect else 0
                return True
        return False

    def handle_sidebar_split_pointer_move(self, pos: tuple[int, int], game_state: dict) -> bool:
        """Update split fractions while dragging; returns True if consumed."""
        if self._left_split_drag_kind is None:
            return False
        top_h = int(getattr(self.theme, "top_bar_h", 48))
        minimap_y = self.screen_height - int(RADAR_MINIMAP_H)
        available = max(0, minimap_y - top_h)
        if available <= 0:
            return True
        dy = int(pos[1]) - self._left_split_drag_start_y
        kind = self._left_split_drag_kind
        if kind in ("main_bottom", "watch_top"):
            new_main_h = max(HERO_LEFT_MIN_H, min(available - WATCH_CARD_HEADER_H, self._left_split_drag_main_h0 + dy))
            new_watch_h = available - new_main_h
        elif kind == "watch_bottom":
            new_watch_h = max(
                WATCH_CARD_HEADER_H,
                min(available - HERO_LEFT_MIN_H, self._left_split_drag_watch_h0 + dy),
            )
            new_main_h = available - new_watch_h
        elif kind == "main_solo":
            new_main_h = max(
                HERO_LEFT_MIN_H,
                min(available, self._left_split_drag_main_h0 + dy),
            )
            self._left_split_fracs["main_solo"] = float(new_main_h) / float(available)
            return True
        else:
            return True
        if new_main_h > 0 and new_watch_h > 0:
            self._left_split_fracs["main"] = float(new_main_h) / float(available)
            self._left_split_fracs["watch"] = float(new_watch_h) / float(available)
        return True

    def handle_sidebar_split_pointer_up(self) -> bool:
        """End split-handle drag; returns True if a drag was active."""
        if self._left_split_drag_kind is None:
            return False
        self._left_split_drag_kind = None
        return True

    def _layout_rects_for_screen(
        self, w: int, h: int, *, show_right_panel: bool, game_state: dict | None = None
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
        """Geometry only — shared by _compute_layout and Ursina pointer routing.

        Delegates core rectangle math to HUDLayoutManager, then overlays the
        left-column segment allocation which depends on game state.
        """
        top_h = int(getattr(self.theme, "top_bar_h", 48))
        bottom_h = int(getattr(self.theme, "bottom_bar_h", 96))
        margin = int(getattr(self.theme, "margin", 8))
        gutter = int(getattr(self.theme, "gutter", 8))

        _ = show_right_panel  # right chrome retired (WK52 R4)

        layout = self._layout_mgr.compute(
            w, h,
            top_bar_h=top_h,
            bottom_bar_h=bottom_h,
            margin=margin,
            gutter=gutter,
        )

        self._watch_card_chat_rect = None

        # Left-column segments depend on game_state (selected hero/building/pin).
        left, _main_rect, _watch_rect = self._layout_left_column_segments(
            top_h, layout.minimap, game_state
        )

        return (
            layout.top_bar,
            layout.bottom_bar,
            left,
            layout.right_panel,
            layout.minimap,
            layout.command_bar,
            layout.speed_control,
            layout.recall_button,
            layout.memorial_button,
        )

    def _compute_layout(
        self, surface: pygame.Surface, game_state: dict | None = None
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
            w, h, show_right_panel=show_right, game_state=game_state
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
        _ = show_right  # Tab/no-op; no right chrome hit region (WK52 R4)
        top, bottom, left, right, minimap, command, speed_rect, recall, memorial = self._layout_rects_for_screen(
            w, h, show_right_panel=bool(self.right_panel_visible), game_state=game_state
        )
        profiles = game_state.get("hero_profiles_by_id") or {}
        pin = self._pin_slot
        if pin.hero_id is not None:
            hero_alive = pin.hero_id in profiles
            pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))
        mem_ov = getattr(self, "memorial_card", None)
        if mem_ov is not None and getattr(mem_ov, "visible", False):
            return True
        regions = [top, bottom, minimap, command, speed_rect]
        if pin.hero_id is not None:
            regions.append(recall)
            regions.append(memorial)
        bio = getattr(self, "building_interior_overlay", None)
        if bio is not None and getattr(bio, "visible", False):
            return True
        dco = getattr(self, "demolish_confirm_overlay", None)
        if dco is not None and getattr(dco, "visible", False):
            return True
        if pin.hero_id is not None:
            ch = self._effective_watch_card_h(h)
            if ch > 0:
                if self._left_watch_rect is not None:
                    regions.append(pygame.Rect(self._left_watch_rect))
                else:
                    regions.append(pygame.Rect(minimap.x, minimap.y - ch, minimap.width, ch))
            map_h, stats_h, chat_h = self._watch_card_body_split(ch)
            if chat_h > 0 and self._chat_visible:
                cx, cy = minimap.x, minimap.y - ch
                cbr = self._watch_chat_band_rect(
                    cx,
                    cy,
                    minimap.width,
                    ch,
                    map_h,
                    stats_h,
                    chat_h,
                    profiles,
                    str(pin.hero_id),
                )
                if cbr is not None:
                    regions.append(cbr)
        if (
            game_state.get("selected_hero") is not None
            or game_state.get("selected_peasant") is not None
            or game_state.get("selected_building") is not None
            or game_state.get("selected_enemy") is not None
        ):
            regions.append(left)
        for r in regions:
            if r.collidepoint(x, y):
                return True
        for handle in self._left_split_handle_rects.values():
            if handle.collidepoint(x, y):
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
        from game.ui import hud_summaries
        return hud_summaries.peasant_action_label(self, peasant)

    def _render_peasant_summary(self, surface: pygame.Surface, peasant, left_rect: pygame.Rect) -> None:
        from game.ui import hud_summaries
        return hud_summaries.render_peasant_summary(self, surface, peasant, left_rect)

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
        from game.ui import hud_panel_buttons
        return hud_panel_buttons.render_right_close_button(self, surface, right_rect)

    def _render_left_close_button(self, surface: pygame.Surface, left_rect: pygame.Rect) -> None:
        from game.ui import hud_panel_buttons
        return hud_panel_buttons.render_left_close_button(self, surface, left_rect)

    def _render_pin_button(self, surface: pygame.Surface, left_rect: pygame.Rect, game_state: dict) -> None:
        from game.ui import hud_panel_buttons
        return hud_panel_buttons.render_pin_button(self, surface, left_rect, game_state)

    def trigger_recall_flash(self) -> None:
        from game.ui import hud_panel_buttons
        return hud_panel_buttons.trigger_recall_flash(self)

    def _render_hero_watch_card_infocard(
        self,
        surface: pygame.Surface,
        minimap_rect: pygame.Rect,
        game_state: dict,
    ) -> None:
        from game.ui import hud_watch_card
        return hud_watch_card.render_hero_watch_card_infocard(self, surface, minimap_rect, game_state)

    def _render_card_slot(
        self,
        surface: pygame.Surface,
        minimap_rect: pygame.Rect,
        game_state: dict,
    ) -> None:
        from game.ui import hud_watch_card
        return hud_watch_card.render_card_slot(self, surface, minimap_rect, game_state)

    def _render_watch_card_chrome(
        self,
        surface: pygame.Surface,
        minimap_rect: pygame.Rect,
        game_state: dict,
    ) -> None:
        from game.ui import hud_watch_card
        return hud_watch_card.render_watch_card_chrome(self, surface, minimap_rect, game_state)

    def _ensure_radar_terrain_surface(self, inner: pygame.Rect, world) -> pygame.Surface | None:
        from game.ui import hud_radar
        return hud_radar.ensure_radar_terrain_surface(self, inner, world)

    def _render_radar_minimap(
        self,
        surface: pygame.Surface,
        minimap_rect: pygame.Rect,
        game_state: dict,
    ) -> None:
        from game.ui import hud_radar
        return hud_radar.render_radar_minimap(self, surface, minimap_rect, game_state)

    def _render_memorial_button(
        self, surface: pygame.Surface, memorial_rect: pygame.Rect, game_state: dict
    ) -> None:
        from game.ui import hud_panel_buttons
        return hud_panel_buttons.render_memorial_button(self, surface, memorial_rect, game_state)

    def _render_recall_button(self, surface: pygame.Surface, recall_rect: pygame.Rect, game_state: dict) -> None:
        from game.ui import hud_panel_buttons
        return hud_panel_buttons.render_recall_button(self, surface, recall_rect, game_state)

    def _render_building_summary(self, surface: pygame.Surface, building, rect: pygame.Rect) -> None:
        from game.ui import hud_summaries
        return hud_summaries.render_building_summary(self, surface, building, rect)

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
        """Legacy Tab hook — right HUD column removed (WK52 R4)."""
        pass

    def _uses_pinned_watch_card_chat(self, hero_id: str) -> bool:
        if not hero_id or self._pin_slot.hero_id != hero_id:
            return False
        return bool(self._chat_visible and self._watch_card_expanded)

    def _should_render_hero_menu_chat_popup(self, game_state: dict) -> bool:
        cp = self._chat_panel
        sel = game_state.get("selected_hero")
        if cp is None or not cp.is_active() or sel is None:
            return False
        if game_state.get("selected_building") is not None:
            return False
        hid = str(getattr(sel, "hero_id", "") or "")
        chat_hid = str(getattr(cp.hero_target, "hero_id", "") or "")
        if hid != chat_hid:
            return False
        return not self._uses_pinned_watch_card_chat(hid)

    def _hero_menu_chat_desired_h(self, left_h: int) -> int:
        """Vertical space to reserve for in-column hero-menu chat (WK61-R9)."""
        if left_h <= 0:
            return 0
        pref = min(
            HERO_MENU_CHAT_PREFERRED_H,
            max(HERO_MENU_CHAT_MIN_H, int(left_h * 0.38)),
        )
        max_chat = max(HERO_MENU_CHAT_MIN_H, left_h - HERO_MENU_HERO_MIN_H - HERO_MENU_CHAT_GAP)
        return max(HERO_MENU_CHAT_MIN_H, min(pref, max_chat))

    def _hero_menu_chat_split_rects(
        self, left: pygame.Rect
    ) -> tuple[pygame.Rect, pygame.Rect] | None:
        """Split left column: shrunk scrollable hero sheet + readable chat band."""
        if left.width <= 0 or left.height <= 0:
            return None
        chat_h = self._hero_menu_chat_desired_h(left.height)
        hero_h = left.height - chat_h - HERO_MENU_CHAT_GAP
        if hero_h < HERO_MENU_HERO_MIN_H:
            hero_h = max(HERO_MENU_HERO_MIN_H, left.height - HERO_MENU_CHAT_MIN_H - HERO_MENU_CHAT_GAP)
            chat_h = left.height - hero_h - HERO_MENU_CHAT_GAP
        if chat_h < HERO_MENU_CHAT_MIN_H or hero_h < HERO_LEFT_MIN_H:
            return None
        hero_rect = pygame.Rect(left.x, left.y, left.width, hero_h)
        chat_rect = pygame.Rect(
            left.x + 4,
            left.y + hero_h + HERO_MENU_CHAT_GAP,
            left.width - 8,
            chat_h,
        )
        return hero_rect, chat_rect

    def _render_hero_focus_profile(self, surface: pygame.Surface, rect: pygame.Rect, game_state: dict) -> None:
        from game.ui import hud_summaries
        return hud_summaries.render_hero_focus_profile(self, surface, rect, game_state)

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
        _ = has_right_content  # interior/quest/chat no longer use right column
        self._show_right_panel = False

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

        if getattr(pin, "_just_pinned", False):
            self._watch_card_expanded = True
            self._chat_visible = False
            pin._just_pinned = False

        top, bottom, left, right, minimap, cmd, speed_rect, recall, memorial = self._compute_layout(
            surface, game_state
        )

        self._panel_top.set_rect(top)
        self._panel_bottom.set_rect(bottom)
        main_col = self._left_main_rect if self._left_main_rect is not None else left
        self._panel_left.set_rect(main_col if main_col.height > 0 else left)
        self._panel_right.set_rect(right)
        self._panel_minimap.set_rect(minimap)
        self._panel_top.render(surface)
        self._panel_bottom.render(surface)

        selected_hero = game_state.get("selected_hero")
        selected_peasant = game_state.get("selected_peasant")
        selected_enemy = game_state.get("selected_enemy")
        self.left_close_rect = None
        main_col = self._left_main_rect if self._left_main_rect is not None else left
        self._last_left_rect = pygame.Rect(main_col) if main_col.width > 0 else None
        sel_building = game_state.get("selected_building")
        hero_panel_rect = main_col
        self._hero_menu_hero_rect = pygame.Rect(main_col)
        self._hero_menu_chat_rect = None
        if selected_hero is not None and sel_building is None:
            if self._should_render_hero_menu_chat_popup(game_state):
                split = self._hero_menu_chat_split_rects(main_col)
                if split is not None:
                    hero_panel_rect, chat_rect = split
                    self._hero_menu_hero_rect = hero_panel_rect
                    self._hero_menu_chat_rect = chat_rect
            self._panel_left.render(surface)
            self._hero_panel.render(
                surface,
                selected_hero,
                hero_panel_rect,
                right_close_rect=None,
                debug_ui=bool(game_state.get("debug_ui", False)),
                hero_profile=game_state.get("selected_hero_profile"),
            )
            if self._hero_menu_chat_rect is not None:
                divider_y = self._hero_menu_chat_rect.top - 2
                pygame.draw.line(
                    surface,
                    self._frame_outer,
                    (main_col.x + 4, divider_y),
                    (main_col.right - 4, divider_y),
                    1,
                )
            # Pin + close must render after HeroPanel header fill or they are painted over (WK51 r6).
            self._render_pin_button(surface, main_col, game_state)
            self._render_left_close_button(surface, main_col)
        elif selected_enemy is not None and sel_building is None:
            self._panel_left.render(surface)
            self._enemy_panel.render(surface, selected_enemy, main_col)
            self._render_left_close_button(surface, main_col)
        elif selected_peasant is not None:
            self._panel_left.render(surface)
            self._render_left_close_button(surface, main_col)
            self._render_peasant_summary(surface, selected_peasant, main_col)

        self._render_left_split_handles(surface)

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

        show_left = selected_hero is not None or selected_peasant is not None or selected_enemy is not None
        self.render_messages(surface, main_col if show_left else None)

        # POI discovery + interaction toasts (WK58/WK59)
        self._ensure_poi_interaction_subscription(game_state)
        self._check_poi_discoveries(game_state)
        self._render_poi_toasts(surface)

        # WK60: Wave event toast (centered, prominent)
        self._render_wave_toast(surface)

        # WK60: DEV MODE label
        self._render_dev_mode_label(surface)

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
        self._right_rect = None

        if self.memorial_card.visible:
            self.memorial_card.render(surface)
        if getattr(self, "building_interior_overlay", None) is not None and self.building_interior_overlay.visible:
            self.building_interior_overlay.render(surface)
            left = self._last_left_rect
            if left is not None and selected_hero is not None and selected_building is None:
                hero_panel_rect = getattr(self, "_hero_menu_hero_rect", None) or left
                self._panel_left.render(surface)
                self._hero_panel.render(
                    surface,
                    selected_hero,
                    hero_panel_rect,
                    right_close_rect=None,
                    debug_ui=bool(game_state.get("debug_ui", False)),
                    hero_profile=game_state.get("selected_hero_profile"),
                )
                self._render_pin_button(surface, left, game_state)
                self._render_left_close_button(surface, left)
        if getattr(self, "demolish_confirm_overlay", None) is not None and self.demolish_confirm_overlay.visible:
            self.demolish_confirm_overlay.render(surface)

        # WK61-R9: Hero-menu chat split inside left column (shrunk hero sheet + chat band).
        if self._hero_menu_chat_rect is not None and self._should_render_hero_menu_chat_popup(game_state):
            self._chat_panel.render(surface, self._hero_menu_chat_rect, game_state)

        # Command mode input display (universal Enter-key command bar)
        eng = game_state.get('engine')
        if eng and getattr(eng, '_command_mode', False):
            cmd_text = getattr(eng, '_command_buffer', '')
            cursor = "|" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
            font = pygame.font.SysFont(None, 28)
            if cmd_text:
                prompt_surf = font.render(f"> {cmd_text}{cursor}", True, (255, 255, 200))
            else:
                prompt_surf = font.render(f"> {cursor}", True, (255, 255, 200))
            bar_h = 36
            bg = pygame.Surface((surface.get_width(), bar_h), pygame.SRCALPHA)
            bg.fill((20, 20, 40, 220))
            y = surface.get_height() - bar_h - 4
            surface.blit(bg, (0, y))
            surface.blit(prompt_surf, (10, y + 6))
            if not cmd_text:
                hint_font = pygame.font.SysFont(None, 22)
                hint_surf = hint_font.render("Type a command (/help) or message... ESC to close", True, (120, 120, 140))
                surface.blit(hint_surf, (30, y + 10))

    def is_mouse_over_menu(
        self,
        pos: tuple[int, int],
        game_state: dict,
        building_panel,
    ) -> bool:
        """True if ``pos`` (``engine.screen`` / virtual framebuffer pixels) is over a menu that captures wheel."""
        x, y = int(pos[0]), int(pos[1])
        lr = self._last_left_rect
        if (
            building_panel is not None
            and getattr(building_panel, "visible", False)
            and getattr(building_panel, "selected_building", None) is not None
        ):
            bx = int(getattr(building_panel, "panel_x", 0))
            by = int(getattr(building_panel, "panel_y", 0))
            bw = int(getattr(building_panel, "panel_width", 0))
            bh = int(getattr(building_panel, "panel_height", 0))
            if bw > 0 and bh >= 0 and pygame.Rect(bx, by, bw, bh).collidepoint(x, y):
                return True
        if (
            lr is not None
            and lr.collidepoint(x, y)
            and game_state.get("selected_hero") is not None
            and game_state.get("selected_peasant") is None
            and game_state.get("selected_building") is None
        ):
            return True
        return False

    def scroll_active_menu(
        self,
        direction: int,
        pointer_pos: tuple[int, int],
        game_state: dict,
        building_panel,
    ) -> bool:
        """Scroll the menu under ``pointer_pos``.

        ``direction`` +1 moves content downward (wheel ``wheel_y=-1``); -1 moves content up.
        """
        wheel_y = -int(direction)
        if wheel_y == 0:
            return False
        return self.handle_menu_scroll(pointer_pos, wheel_y, game_state, building_panel)

    def handle_menu_scroll(
        self,
        pos: tuple[int, int],
        wheel_y: int,
        game_state: dict,
        building_panel,
    ) -> bool:
        if wheel_y == 0:
            return False
        if not self.is_mouse_over_menu(pos, game_state, building_panel):
            return False
        x, y = int(pos[0]), int(pos[1])
        lr = self._last_left_rect
        if (
            building_panel is not None
            and getattr(building_panel, "visible", False)
            and getattr(building_panel, "selected_building", None) is not None
        ):
            bx = int(getattr(building_panel, "panel_x", 0))
            by = int(getattr(building_panel, "panel_y", 0))
            bw = int(getattr(building_panel, "panel_width", 0))
            bh = int(getattr(building_panel, "panel_height", 0))
            if bw > 0 and bh >= 0 and pygame.Rect(bx, by, bw, bh).collidepoint(x, y):
                if building_panel.apply_menu_scroll(int(wheel_y)):
                    return True
                return True
        if (
            lr is not None
            and game_state.get("selected_hero") is not None
            and game_state.get("selected_peasant") is None
            and game_state.get("selected_building") is None
        ):
            hmcr = getattr(self, "_hero_menu_chat_rect", None)
            if hmcr is not None and hmcr.collidepoint(x, y):
                return True
            hero_rect = getattr(self, "_hero_menu_hero_rect", None) or lr
            if hero_rect.collidepoint(x, y):
                if self._hero_panel.apply_menu_scroll(int(wheel_y)):
                    return True
                return True
        return False

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

        bio = getattr(self, "building_interior_overlay", None)
        if bio is not None and getattr(bio, "visible", False):
            left = self._last_left_rect
            on_left_panel = left is not None and left.collidepoint(x, y)
            if not on_left_panel:
                bio_result = bio.handle_click((x, y))
                if bio_result is True:
                    return "close_building_interior_unpause"
                if isinstance(bio_result, dict):
                    return bio_result
                return None

        dco = getattr(self, "demolish_confirm_overlay", None)
        if dco is not None and getattr(dco, "visible", False):
            result = dco.handle_click((x, y))
            if result == "confirm":
                return "confirm_demolish"
            elif result == "cancel":
                dco.hide()
            return None

        for _key, handle_rect in self._left_split_handle_rects.items():
            if handle_rect.collidepoint((x, y)):
                if self.handle_sidebar_split_pointer_down((x, y), game_state):
                    return "sidebar_split_drag"
                return "sidebar_split_drag"

        cp = getattr(self, "_chat_panel", None)
        hmcr = getattr(self, "_hero_menu_chat_rect", None)
        if (
            cp is not None
            and cp.is_active()
            and hmcr is not None
            and hmcr.collidepoint((x, y))
        ):
            chat_click = cp.handle_click((x, y), hmcr)
            if chat_click is not None:
                return chat_click

        if (
            getattr(self, "_chat_close_rect", None) is not None
            and self._chat_close_rect.collidepoint((x, y))
            and pin.hero_id is not None
        ):
            self._chat_visible = False
            return "chat_band_close"
        if (
            getattr(self, "_chat_open_rect", None) is not None
            and self._chat_open_rect.collidepoint((x, y))
            and pin.hero_id is not None
        ):
            self._chat_visible = True
            return "chat_band_open"

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
            self._watch_card_expanded
            and getattr(self, "watch_card_map_rect", None) is not None
            and self.watch_card_map_rect.collidepoint((x, y))
            and self._pin_slot.hero_id is not None
        ):
            wc = self.watch_card_map_world_center
            wh = self.watch_card_map_world_wh
            mr = self.watch_card_map_rect
            if (
                wc is not None
                and wh is not None
                and mr is not None
                and mr.width > 0
                and mr.height > 0
            ):
                rel_x = (x - mr.x) / float(mr.width)
                rel_y = (y - mr.y) / float(mr.height)
                wx = wc[0] + (rel_x - 0.5) * wh[0]
                wy = wc[1] + (rel_y - 0.5) * wh[1]
                return {"type": "select_hero_at_world", "wx": wx, "wy": wy}
        chev = getattr(self, "_watch_card_chevron_rect", None)
        if chev is not None and chev.collidepoint((x, y)):
            if self._pin_slot.hero_id is not None:
                self._watch_card_expanded = not self._watch_card_expanded
                return "watch_card_chevron_toggle"
        cp = getattr(self, "_chat_panel", None)
        if (
            self._chat_visible
            and getattr(self, "_watch_card_chat_rect", None) is not None
            and cp is not None
            and self._watch_card_chat_rect.collidepoint((x, y))
            and self._watch_card_expanded
            and pin.hero_id is not None
        ):
            pinned_hero = next(
                (
                    h
                    for h in (game_state.get("heroes") or [])
                    if str(getattr(h, "hero_id", "") or "") == str(pin.hero_id)
                ),
                None,
            )
            chat_active = (
                cp.is_active()
                and pinned_hero is not None
                and getattr(cp, "hero_target", None) is pinned_hero
            )
            if chat_active:
                chat_click = cp.handle_click((x, y), self._watch_card_chat_rect)
                if chat_click is not None:
                    return chat_click
            elif pinned_hero is not None:
                return {"type": "start_conversation", "hero": pinned_hero}
        if (
            getattr(self, "memorial_btn_rect", None) is not None
            and self.memorial_btn_rect.collidepoint((x, y))
            and self._pending_memorial is not None
        ):
            self.memorial_card.show(self._pending_memorial)
            return "open_memorial"
        # WK61-FEAT-005: Check hero panel chat button before close button
        if (
            game_state.get("selected_hero") is not None
            and game_state.get("selected_building") is None
        ):
            hero_click = self._hero_panel.handle_click((x, y))
            if hero_click is not None:
                return hero_click
        if self.left_close_rect is not None and self.left_close_rect.collidepoint((x, y)):
            return "close_selection"
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

