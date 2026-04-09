"""
ESC pause/settings menu (WK7).

Centered modal menu with pages: Resume, Graphics, Audio, Controls, Quit.
"""
from __future__ import annotations

import pygame
from game.ui.widgets import Button, ModalPanel, Slider, RadioGroup, load_image_cached
from game.ui.theme import UITheme
from game.ui.chat_panel import _wrap_text
from config import COLOR_WHITE, COLOR_UI_BG, COLOR_UI_BORDER


class PauseMenu:
    """Centered pause/settings menu modal."""
    
    def __init__(self, screen_width: int, screen_height: int, engine=None, audio_system=None):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.visible = False
        self.current_page = "main"  # main, graphics, audio, controls
        self.theme = UITheme()
        self.engine = engine  # WK7: For apply_display_settings() and get_game_state()
        self.audio_system = audio_system  # WK7: For master volume control
        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_tex_pressed = "assets/ui/kingdomsim_ui_cc0/buttons/button_pressed.png"
        self._button_slice_border = 6
        # WK16: Use blank 16x16 for resume/quit when icons missing so Button layout aligns all 5
        _blank_16 = pygame.Surface((16, 16), pygame.SRCALPHA)
        self._icon_map = {
            "resume": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_play.png", (16, 16)) or _blank_16,
            "quit": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_quit.png", (16, 16)) or _blank_16,
            # Missing files → None breaks hover hitbox vs texture in some builds; use blank slot.
            "graphics": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_graphics.png", (16, 16)) or _blank_16,
            "audio": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_audio.png", (16, 16)) or _blank_16,
            "controls": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_controls.png", (16, 16)) or _blank_16,
        }
        
        # Modal panel
        self.modal = ModalPanel(
            screen_width=screen_width,
            screen_height=screen_height,
            panel_width=320,
            panel_height=420,
            texture_path=self._panel_tex_modal,
            slice_border=8,
        )
        
        # Page buttons (main menu)
        self.page_buttons = {}  # {page_name: rect}
        self.page_button_widgets: dict[str, Button] = {}
        self._update_page_buttons()
        
        # Controls page: keybinds list
        self.keybinds = self._build_keybinds_list()
        
        # Graphics page — short labels so text fits the modal; values match engine display_mode
        self.graphics_radio = RadioGroup(
            options=[
                ("Fullscreen", "fullscreen"),
                ("Borderless", "borderless"),
                ("Windowed", "windowed"),
            ],
            selected_value="windowed",  # Default; synced from engine when opening Graphics
            option_height=36,
            spacing=6,
        )
        
        # Audio page (stub until Agent 14 API)
        self.audio_master_slider = Slider(
            rect=pygame.Rect(0, 0, 300, 40),
            value=0.8,  # Default 80% (0.8)
            track_color=(60, 60, 70),
            fill_color=(100, 150, 200),
            thumb_color=(150, 200, 255)
        )
        self.audio_music_slider = Slider(
            rect=pygame.Rect(0, 0, 300, 40),
            value=0.8,
            track_color=(60, 60, 70),
            fill_color=(100, 150, 200),
            thumb_color=(150, 200, 255)
        )
        self.audio_sfx_slider = Slider(
            rect=pygame.Rect(0, 0, 300, 40),
            value=0.8,
            track_color=(60, 60, 70),
            fill_color=(100, 150, 200),
            thumb_color=(150, 200, 255)
        )
        self.audio_slider_dragging = None  # "master" | "music" | "sfx" | None
        # Controls page: scroll long keybind list inside the modal
        self.controls_scroll_px = 0
    
    def _update_page_buttons(self):
        """Update page button rectangles based on current panel size."""
        panel_rect = self.modal.get_panel_rect()
        button_y = panel_rect.y + 56
        button_h = 42
        button_w = 260
        button_x = panel_rect.centerx - button_w // 2
        spacing = 48
        
        self.page_buttons = {
            "resume": pygame.Rect(button_x, button_y, button_w, button_h),
            "graphics": pygame.Rect(button_x, button_y + spacing, button_w, button_h),
            "audio": pygame.Rect(button_x, button_y + spacing * 2, button_w, button_h),
            "controls": pygame.Rect(button_x, button_y + spacing * 3, button_w, button_h),
            "quit": pygame.Rect(button_x, button_y + spacing * 4, button_w, button_h),
        }
        self.page_button_widgets = {}
        for page_name, rect in self.page_buttons.items():
            if page_name == "resume":
                # ASCII only — default pygame font has no glyph for ► (shows tofu in Ursina HUD).
                text = "Resume"
            elif page_name == "quit":
                text = "Quit"
            else:
                text = page_name.replace("_", " ").title()
            self.page_button_widgets[page_name] = Button(
                rect=pygame.Rect(rect),
                text=text,
                font=self.theme.font_body,
                icon=self._icon_map.get(page_name),
            )
    
    def _build_keybinds_list(self) -> list[tuple[str, str]]:
        """Build read-only keybinds list for Controls page."""
        return [
            ("Buildings", ""),
            ("1-8", "Warrior Guild, Marketplace, Ranger Guild, Rogue Guild, Wizard Guild, Blacksmith, Inn, Trading Post"),
            ("T", "Temple of Agrela"),
            ("G", "Gnome Hovel"),
            ("E", "Elven Bungalow"),
            ("V", "Dwarven Settlement"),
            ("U", "Guardhouse"),
            ("Y", "Ballista Tower"),
            ("O", "Wizard Tower"),
            ("F", "Fairgrounds"),
            ("I", "Library"),
            ("R", "Royal Gardens"),
            ("", ""),
            ("Actions", ""),
            ("H", "Hire Hero ($50)"),
            ("B", "Place Bounty ($50)"),
            ("P", "Use Potion (selected hero)"),
            ("", ""),
            ("Camera", ""),
            ("WASD / Mouse Edge", "Scroll camera"),
            ("Mouse Wheel / +/-", "Zoom"),
            ("Space", "Center on Castle"),
            ("", ""),
            ("Menu", ""),
            ("Esc", "Pause / Open Menu"),
        ]

    def _measure_controls_content_height(self, inner_width: int) -> int:
        """Total pixel height of the keybind column (for scroll bounds)."""
        desc_max_w = max(80, inner_width - 130)
        line_h = self.theme.font_small.get_height() + 2
        y = 0
        for key, desc in self.keybinds:
            if not key and not desc:
                y += 10
                continue
            if desc and not key:
                y += 30
            else:
                if desc:
                    lines = _wrap_text(self.theme.font_small, desc, desc_max_w)
                    y += max(22, len(lines) * line_h)
                else:
                    y += 22
        return y
    
    def open(self):
        """Open the menu."""
        self.visible = True
        self.current_page = "main"
        self._update_page_buttons()

    def on_resize(self, screen_width: int, screen_height: int):
        """Update modal sizing after a window resize."""
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.modal.screen_width = self.screen_width
        self.modal.screen_height = self.screen_height
        # Clear cached backdrop so it matches new size
        self.modal._backdrop_cache = None
        self._update_page_buttons()
    
    def close(self):
        """Close the menu."""
        self.visible = False
        self.current_page = "main"
        self.audio_slider_dragging = None
        self.controls_scroll_px = 0
    
    def toggle(self):
        """Toggle menu visibility."""
        if self.visible:
            self.close()
        else:
            self.open()

    def _get_audio_volume(self, kind: str) -> float:
        if not self.audio_system:
            return 0.8
        if kind == "master":
            return float(self.audio_system.get_master_volume())
        if kind == "music":
            getter = getattr(self.audio_system, "get_music_volume", None)
            if callable(getter):
                return float(getter())
        if kind == "sfx":
            getter = getattr(self.audio_system, "get_sfx_volume", None)
            if callable(getter):
                return float(getter())
        return float(self.audio_system.get_master_volume()) if self.audio_system else 0.8

    def _set_audio_volume(self, kind: str, value: float):
        if not self.audio_system:
            return
        if kind == "master":
            self.audio_system.set_master_volume(value)
            return
        if kind == "music":
            setter = getattr(self.audio_system, "set_music_volume", None)
            if callable(setter):
                setter(value)
            return
        if kind == "sfx":
            setter = getattr(self.audio_system, "set_sfx_volume", None)
            if callable(setter):
                setter(value)
            return

    def _position_audio_sliders(self):
        panel_rect = self.modal.get_panel_rect()
        x = panel_rect.centerx - self.audio_master_slider.rect.width // 2
        self.audio_master_slider.rect.x = x
        self.audio_music_slider.rect.x = x
        self.audio_sfx_slider.rect.x = x
        self.audio_master_slider.rect.y = panel_rect.y + 190
        self.audio_music_slider.rect.y = panel_rect.y + 260
        self.audio_sfx_slider.rect.y = panel_rect.y + 330
    
    def handle_click(self, pos: tuple[int, int]) -> str | None:
        """
        Handle mouse click.
        Returns action string: "resume", "quit", "graphics", "audio", "controls", or None.
        """
        if not self.visible:
            return None
        
        if self.current_page == "main":
            # Main menu buttons
            for page_name, rect in self.page_buttons.items():
                if rect.collidepoint(pos):
                    if page_name == "resume":
                        self.close()
                        return "resume"
                    elif page_name == "quit":
                        return "quit"
                    else:
                        self.current_page = page_name
                        if page_name == "controls":
                            self.controls_scroll_px = 0
                        if page_name == "graphics":
                            # WK7: Update radio selection from engine state
                            if self.engine:
                                game_state = self.engine.get_game_state()
                                current_mode = game_state.get("display_mode", "borderless")
                                self.graphics_radio.selected_value = current_mode
                        elif page_name == "audio":
                            # WK7: Update slider from audio system state
                            if self.audio_system:
                                self.audio_master_slider.set_value(self._get_audio_volume("master"))
                                self.audio_music_slider.set_value(self._get_audio_volume("music"))
                                self.audio_sfx_slider.set_value(self._get_audio_volume("sfx"))
                            # Position audio slider
                            self._position_audio_sliders()
                        return None
        
        elif self.current_page == "graphics":
            # Graphics page: radio group selection (geometry must match render())
            panel_rect = self.modal.get_panel_rect()
            radio_x = panel_rect.x + 24
            radio_y = panel_rect.y + 136
            radio_w = max(120, panel_rect.width - 48)
            selected = self.graphics_radio.hit_test(pos, radio_x, radio_y, radio_w)
            if selected and self.engine:
                self.graphics_radio.selected_value = selected
                game_state = self.engine.get_game_state()
                window_size = game_state.get("window_size", None)
                if hasattr(self.engine, "request_display_settings"):
                    self.engine.request_display_settings(selected, window_size)
                else:
                    self.engine.apply_display_settings(selected, window_size)
                return f"graphics_select_{selected}"
        
        elif self.current_page == "audio":
            # Audio page: slider drag start (track or thumb — WK24 wider hit area)
            if self.audio_master_slider.hit_test_interactive(pos):
                self.audio_slider_dragging = "master"
                self.audio_master_slider.set_value_from_x(pos[0])
                self._set_audio_volume("master", self.audio_master_slider.value)
                return "audio_slider_drag"
            if self.audio_music_slider.hit_test_interactive(pos):
                self.audio_slider_dragging = "music"
                self.audio_music_slider.set_value_from_x(pos[0])
                self._set_audio_volume("music", self.audio_music_slider.value)
                return "audio_slider_drag"
            if self.audio_sfx_slider.hit_test_interactive(pos):
                self.audio_slider_dragging = "sfx"
                self.audio_sfx_slider.set_value_from_x(pos[0])
                self._set_audio_volume("sfx", self.audio_sfx_slider.value)
                return "audio_slider_drag"
        
        # Back button (top-left corner)
        panel_rect = self.modal.get_panel_rect()
        back_rect = pygame.Rect(panel_rect.x + 10, panel_rect.y + 10, 60, 30)
        if back_rect.collidepoint(pos):
            self.current_page = "main"
            self.controls_scroll_px = 0
            return "back"
        
        return None
    
    def handle_wheel(self, wheel_y: int) -> None:
        """Scroll the Controls page keybind list (negative wheel_y = scroll down)."""
        if not self.visible or self.current_page != "controls" or wheel_y == 0:
            return
        step = 28
        self.controls_scroll_px = max(0, self.controls_scroll_px - wheel_y * step)

    def handle_mousemove(self, pos: tuple[int, int], lmb_held: bool = True):
        """Handle mouse movement (slider drag only while left button is held)."""
        if not self.visible:
            return None
        if self.audio_slider_dragging and not lmb_held:
            return self.handle_mouseup(pos)
        if not self.audio_slider_dragging:
            return None
        
        if self.current_page == "audio":
            if self.audio_slider_dragging == "master":
                self.audio_master_slider.set_value_from_x(pos[0])
                self._set_audio_volume("master", self.audio_master_slider.value)
            elif self.audio_slider_dragging == "music":
                self.audio_music_slider.set_value_from_x(pos[0])
                self._set_audio_volume("music", self.audio_music_slider.value)
            elif self.audio_slider_dragging == "sfx":
                self.audio_sfx_slider.set_value_from_x(pos[0])
                self._set_audio_volume("sfx", self.audio_sfx_slider.value)
            return "audio_slider_drag"
        
        return None
    
    def handle_mouseup(self, pos: tuple[int, int]):
        """Handle mouse release (end slider drag)."""
        if self.audio_slider_dragging:
            self.audio_slider_dragging = None
            if self.current_page == "audio":
                # WK7: Final volume update on release
                if self.audio_system:
                    self._set_audio_volume("master", self.audio_master_slider.value)
                    self._set_audio_volume("music", self.audio_music_slider.value)
                    self._set_audio_volume("sfx", self.audio_sfx_slider.value)
                return "audio_slider_release"
        return None
    
    def render(self, surface: pygame.Surface, mouse_pos: tuple[int, int] | None = None):
        """Render the menu. Pass mouse_pos when the host uses a virtual UI cursor (e.g. Ursina)."""
        if not self.visible:
            return
        # Ursina: row-sampled HUD CRC can miss small vertical bands (e.g. top menu rows), so hover
        # state updates never reach the GPU texture. Match economic_panel: force one upload this frame.
        if self.engine is not None and getattr(self.engine, "_ursina_viewer", False):
            setattr(self.engine, "_ursina_hud_force_upload", True)
        cur_mouse = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()

        # Backdrop
        self.modal.render_backdrop(surface)
        
        # Panel
        self.modal.render_panel(surface)
        panel_rect = self.modal.get_panel_rect()
        
        if self.current_page == "main":
            # Main menu
            title = self.theme.font_title.render("Menu", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))
            
            # Buttons (draw bottom items first so Resume/Graphics stay on top for hover/stacking)
            for page_name, rect in reversed(list(self.page_buttons.items())):
                button = self.page_button_widgets.get(page_name)
                if button is None:
                    continue
                button.rect = pygame.Rect(rect)
                button.icon = self._icon_map.get(page_name)
                if page_name == "resume":
                    button.text = "Resume"
                elif page_name == "quit":
                    button.text = "Quit"
                else:
                    button.text = page_name.replace("_", " ").title()
                button.render(
                    surface,
                    cur_mouse,
                    texture_normal=self._button_tex_normal,
                    texture_hover=self._button_tex_hover,
                    texture_pressed=self._button_tex_pressed,
                    slice_border=self._button_slice_border,
                    bg_normal=(50, 50, 60),
                    bg_hover=(70, 70, 80),
                    bg_pressed=(80, 80, 95),
                    border_outer=(20, 20, 25),
                    border_inner=(80, 80, 100),
                    border_highlight=(107, 107, 132),
                    text_color=self.theme.text,
                    text_shadow_color=(20, 20, 30),
                    text_align="left",
                    content_left_pad=14,
                    icon_slot=16,
                    icon_gap=8,
                )
        
        elif self.current_page == "graphics":
            # Graphics page
            title = self.theme.font_title.render("Graphics", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))
            
            # Display mode options (wide row for hit-testing + label fit)
            label = self.theme.font_body.render("Display Mode:", True, self.theme.text)
            surface.blit(label, (panel_rect.x + 24, panel_rect.y + 108))
            
            radio_x = panel_rect.x + 24
            radio_y = panel_rect.y + 136
            radio_w = max(120, panel_rect.width - 48)
            self.graphics_radio.render(
                surface, self.theme.font_body,
                radio_x, radio_y, radio_w,
                text_color=self.theme.text,
                selected_color=(100, 150, 200),
                bg_color=(50, 50, 60),
                mouse_pos=cur_mouse,
            )
            if self.engine and getattr(self.engine, "_ursina_viewer", False):
                note_y = radio_y + len(self.graphics_radio.options) * (
                    self.graphics_radio.option_height + self.graphics_radio.spacing
                ) + 8
                note = self.theme.font_small.render(
                    "Changes apply to the game window (Ursina).",
                    True,
                    (130, 130, 145),
                )
                surface.blit(note, (radio_x, note_y))
            
            # Back button
            back_text = self.theme.font_small.render("< Back", True, self.theme.text)
            surface.blit(back_text, (panel_rect.x + 10, panel_rect.y + 10))
        
        elif self.current_page == "audio":
            # Audio page
            title = self.theme.font_title.render("Audio", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))
            
            # Labels + sliders
            label_x = panel_rect.x + 80
            master_label = self.theme.font_body.render("Master Volume:", True, self.theme.text)
            music_label = self.theme.font_body.render("Music (Ambient):", True, self.theme.text)
            sfx_label = self.theme.font_body.render("SFX Volume:", True, self.theme.text)
            surface.blit(master_label, (label_x, panel_rect.y + 140))
            surface.blit(music_label, (label_x, panel_rect.y + 210))
            surface.blit(sfx_label, (label_x, panel_rect.y + 280))

            master_pct = int(self.audio_master_slider.value * 100)
            music_pct = int(self.audio_music_slider.value * 100)
            sfx_pct = int(self.audio_sfx_slider.value * 100)
            master_text = self.theme.font_body.render(f"{master_pct}%", True, self.theme.text)
            music_text = self.theme.font_body.render(f"{music_pct}%", True, self.theme.text)
            sfx_text = self.theme.font_body.render(f"{sfx_pct}%", True, self.theme.text)
            surface.blit(master_text, (label_x, panel_rect.y + 166))
            surface.blit(music_text, (label_x, panel_rect.y + 236))
            surface.blit(sfx_text, (label_x, panel_rect.y + 306))

            self.audio_master_slider.render(surface)
            self.audio_music_slider.render(surface)
            self.audio_sfx_slider.render(surface)
            
            # Back button
            back_text = self.theme.font_small.render("< Back", True, self.theme.text)
            surface.blit(back_text, (panel_rect.x + 10, panel_rect.y + 10))
        
        elif self.current_page == "controls":
            # Controls page (clipped + scroll — long list stays inside the modal)
            title = self.theme.font_title.render("Controls", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))

            content_total_h = self._measure_controls_content_height(
                max(1, panel_rect.width - 16)
            )
            inner_pad = 8
            list_top = panel_rect.y + 50
            if content_total_h > panel_rect.height - 70:
                wheel_hint = self.theme.font_small.render("Mouse wheel: scroll", True, (130, 130, 145))
                surface.blit(wheel_hint, (panel_rect.x + 12, panel_rect.y + 42))
                list_top = panel_rect.y + 58
            viewport = pygame.Rect(
                panel_rect.x + inner_pad,
                list_top,
                max(1, panel_rect.width - 2 * inner_pad),
                max(1, panel_rect.y + panel_rect.height - 10 - list_top),
            )
            content_w = viewport.width
            content_total_h = self._measure_controls_content_height(content_w)
            max_scroll = max(0, content_total_h - viewport.height)
            self.controls_scroll_px = max(0, min(self.controls_scroll_px, max_scroll))

            desc_max_w = max(80, content_w - 130)
            line_h = self.theme.font_small.get_height() + 2
            clip_prev = surface.get_clip()
            surface.set_clip(viewport)
            try:
                y = viewport.y - self.controls_scroll_px
                for key, desc in self.keybinds:
                    if not key and not desc:
                        y += 10
                        continue

                    if desc and not key:
                        header = self.theme.font_body.render(desc, True, self.theme.accent)
                        surface.blit(header, (panel_rect.x + 20, y))
                        y += 30
                    else:
                        key_text = self.theme.font_body.render(key, True, self.theme.text)
                        surface.blit(key_text, (panel_rect.x + 30, y))

                        if desc:
                            lines = _wrap_text(self.theme.font_small, desc, desc_max_w)
                            dy = y
                            for line in lines:
                                desc_text = self.theme.font_small.render(line, True, (200, 200, 200))
                                surface.blit(desc_text, (panel_rect.x + 120, dy + 2))
                                dy += line_h
                            y = max(y + 22, dy)
                        else:
                            y += 22
            finally:
                surface.set_clip(clip_prev)

            # Back button
            back_text = self.theme.font_small.render("< Back", True, self.theme.text)
            surface.blit(back_text, (panel_rect.x + 10, panel_rect.y + 10))
