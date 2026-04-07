"""Bottom command bar renderer for HUD."""

from __future__ import annotations

import pygame

from config import HERO_HIRE_COST, COLOR_WHITE
from game.ui.widgets import Button, Tooltip, load_image_cached


class CommandBar:
    """Render and manage HUD command buttons."""

    def __init__(
        self,
        theme,
        *,
        frame_inner: tuple[int, int, int],
        frame_outer: tuple[int, int, int],
        frame_highlight: tuple[int, int, int],
        button_tex_normal: str,
        button_tex_hover: str,
        button_tex_pressed: str,
        button_slice_border: int,
    ) -> None:
        self.theme = theme
        self._frame_inner = frame_inner
        self._frame_outer = frame_outer
        self._frame_highlight = frame_highlight
        self._button_tex_normal = button_tex_normal
        self._button_tex_hover = button_tex_hover
        self._button_tex_pressed = button_tex_pressed
        self._button_slice_border = int(button_slice_border)
        self._tooltip = Tooltip((40, 40, 50), (80, 80, 100), alpha=240)
        self._buttons: list[Button] = []
        self._button_actions: list[str] = []
        self._buttons_last_size: tuple[int, int] | None = None
        self._icon_build = load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_build.png", (16, 16))
        self._icon_hire = load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_hire.png", (16, 16))
        self._icon_bounty = load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_bounty.png", (16, 16))

    def _ensure_buttons(self, cmd_rect: pygame.Rect) -> None:
        size_key = (int(cmd_rect.width), int(cmd_rect.height))
        if self._buttons and self._buttons_last_size == size_key:
            return
        self._buttons_last_size = size_key
        self._buttons = []
        self._button_actions = []

        gutter = int(self.theme.gutter)
        button_w = min(140, max(110, int(cmd_rect.width / 3) - gutter))
        button_h = int(cmd_rect.height)
        x = int(cmd_rect.x)
        y = int(cmd_rect.y)

        specs = [
            {
                "title": "Build",
                "hotkey_chip": "1-8",
                "tooltip": "Build\nHotkeys: 1-8, T,G,E,V,U,Y,O,F,I,R\nCost shown in top messages on fail.",
                "action": "build_menu_toggle",
                "icon": self._icon_build,
            },
            {
                "title": "Hire",
                "hotkey_chip": "H",
                "tooltip": f"Hire Hero\nHotkey: H\nCost: ${int(HERO_HIRE_COST)} (select a built guild first)",
                "action": "hire_hero",
                "icon": self._icon_hire,
            },
            {
                "title": "Bounty",
                "hotkey_chip": "B",
                "tooltip": "Place Bounty\nHotkey: B\nPlace at mouse cursor\nShift/Ctrl: bigger (cost=reward)",
                "action": "place_bounty",
                "icon": self._icon_bounty,
            },
        ]

        for spec in specs:
            button = Button(
                rect=pygame.Rect(x, y, button_w, button_h),
                text=str(spec["title"]),
                font=self.theme.font_body,
                tooltip=str(spec["tooltip"]),
                hotkey=str(spec["hotkey_chip"]),
                icon=spec["icon"],
            )
            self._buttons.append(button)
            self._button_actions.append(str(spec["action"]))
            x += button_w + gutter

    def render(
        self,
        surface: pygame.Surface,
        cmd_rect: pygame.Rect,
        *,
        mouse_pos: tuple[int, int] | None = None,
    ) -> None:
        if cmd_rect.width <= 0 or cmd_rect.height <= 0:
            return
        self._ensure_buttons(cmd_rect)
        mouse = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()
        hovered_button: Button | None = None

        for button in self._buttons:
            is_hover = button.hit_test(mouse)
            button.render(
                surface,
                mouse_pos=mouse,
                texture_normal=self._button_tex_normal,
                texture_hover=self._button_tex_hover,
                texture_pressed=self._button_tex_pressed,
                slice_border=self._button_slice_border,
                bg_normal=(45, 45, 60),
                bg_hover=(70, 80, 100),
                bg_pressed=(75, 90, 110),
                border_outer=self._frame_outer,
                border_inner=self._frame_inner,
                border_highlight=self._frame_highlight,
                text_color=COLOR_WHITE if not is_hover else (240, 240, 255),
                text_shadow_color=(20, 20, 30),
                text_align="left",
                content_left_pad=12,
                icon_slot=16,
                icon_gap=6,
                show_hotkey_chip=True,
                hotkey_font=self.theme.font_small,
                hotkey_text_color=(200, 200, 200) if is_hover else (180, 180, 180),
                hotkey_bg=(60, 60, 75) if is_hover else (45, 45, 60),
                hotkey_border=self._frame_inner,
            )
            if is_hover:
                hovered_button = button

        if hovered_button is not None:
            self._tooltip.set_text(self.theme.font_small, hovered_button.tooltip, (230, 230, 230))
            self._tooltip.render(surface, mouse[0] + 12, mouse[1] + 12)
        else:
            self._tooltip.set_text(self.theme.font_small, "", (230, 230, 230))

    def handle_click(self, pos: tuple[int, int]) -> str | None:
        for idx, button in enumerate(self._buttons):
            if button.hit_test(pos):
                action = self._button_actions[idx]
                return action if action else None
        return None
