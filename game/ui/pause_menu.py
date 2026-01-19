"""
ESC pause/settings menu (WK7).

Centered modal menu with pages: Resume, Graphics, Audio, Controls, Quit.
"""
from __future__ import annotations

import pygame
from game.ui.widgets import ModalPanel, Slider, RadioGroup, NineSlice, load_image_cached
from game.ui.theme import UITheme
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
        self._button_slice_border = 6
        self._icon_map = {
            "graphics": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_graphics.png", (16, 16)),
            "audio": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_audio.png", (16, 16)),
            "controls": load_image_cached("assets/ui/kingdomsim_ui_cc0/icons/icon_controls.png", (16, 16)),
        }
        
        # Modal panel
        self.modal = ModalPanel(
            screen_width=screen_width,
            screen_height=screen_height,
            panel_width=480,
            panel_height=520,
            texture_path=self._panel_tex_modal,
            slice_border=8,
        )
        
        # Page buttons (main menu)
        self.page_buttons = {}  # {page_name: rect}
        self._update_page_buttons()
        
        # Controls page: keybinds list
        self.keybinds = self._build_keybinds_list()
        
        # Graphics page (stub until Agent 03 API)
        self.graphics_radio = RadioGroup(
            options=[
                ("Fullscreen", "fullscreen"),
                ("Borderless (Fullscreen Windowed)", "borderless"),
                ("Windowed", "windowed")
            ],
            selected_value="borderless"  # Default, will be updated from engine state
        )
        
        # Audio page (stub until Agent 14 API)
        self.audio_slider = Slider(
            rect=pygame.Rect(0, 0, 300, 24),
            value=0.8,  # Default 80% (0.8)
            track_color=(60, 60, 70),
            fill_color=(100, 150, 200),
            thumb_color=(150, 200, 255)
        )
        self.audio_slider_dragging = False
    
    def _update_page_buttons(self):
        """Update page button rectangles based on current panel size."""
        panel_rect = self.modal.get_panel_rect()
        button_y = panel_rect.y + 70
        button_h = 40
        button_w = 200
        button_x = panel_rect.centerx - button_w // 2
        spacing = 44
        
        self.page_buttons = {
            "resume": pygame.Rect(button_x, button_y, button_w, button_h),
            "graphics": pygame.Rect(button_x, button_y + spacing, button_w, button_h),
            "audio": pygame.Rect(button_x, button_y + spacing * 2, button_w, button_h),
            "controls": pygame.Rect(button_x, button_y + spacing * 3, button_w, button_h),
            "quit": pygame.Rect(button_x, button_y + spacing * 4, button_w, button_h),
        }
    
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
        self.audio_slider_dragging = False
    
    def toggle(self):
        """Toggle menu visibility."""
        if self.visible:
            self.close()
        else:
            self.open()
    
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
                        if page_name == "graphics":
                            # WK7: Update radio selection from engine state
                            if self.engine:
                                game_state = self.engine.get_game_state()
                                current_mode = game_state.get("display_mode", "borderless")
                                self.graphics_radio.selected_value = current_mode
                        elif page_name == "audio":
                            # WK7: Update slider from audio system state
                            if self.audio_system:
                                current_volume = self.audio_system.get_master_volume()
                                self.audio_slider.set_value(current_volume)
                            # Position audio slider
                            panel_rect = self.modal.get_panel_rect()
                            self.audio_slider.rect.x = panel_rect.centerx - self.audio_slider.rect.width // 2
                            self.audio_slider.rect.y = panel_rect.y + 190
                        return None
        
        elif self.current_page == "graphics":
            # Graphics page: radio group selection
            panel_rect = self.modal.get_panel_rect()
            radio_x = panel_rect.x + 80
            radio_y = panel_rect.y + 140
            radio_w = panel_rect.width - 160
            selected = self.graphics_radio.hit_test(pos, radio_x, radio_y, radio_w)
            if selected and self.engine:
                # WK7: Apply display mode change immediately
                self.graphics_radio.selected_value = selected
                game_state = self.engine.get_game_state()
                window_size = game_state.get("window_size", None)
                self.engine.apply_display_settings(selected, window_size)
                return f"graphics_select_{selected}"
        
        elif self.current_page == "audio":
            # Audio page: slider drag start
            if self.audio_slider.hit_test_thumb(pos):
                self.audio_slider_dragging = True
                self.audio_slider.set_value_from_x(pos[0])
                return "audio_slider_drag"
        
        # Back button (top-left corner)
        panel_rect = self.modal.get_panel_rect()
        back_rect = pygame.Rect(panel_rect.x + 10, panel_rect.y + 10, 60, 30)
        if back_rect.collidepoint(pos):
            self.current_page = "main"
            return "back"
        
        return None
    
    def handle_mousemove(self, pos: tuple[int, int]):
        """Handle mouse movement (for slider dragging)."""
        if not self.visible or not self.audio_slider_dragging:
            return None
        
        if self.current_page == "audio":
            self.audio_slider.set_value_from_x(pos[0])
            # WK7: Update audio volume in real-time during drag
            if self.audio_system:
                self.audio_system.set_master_volume(self.audio_slider.value)
            return "audio_slider_drag"
        
        return None
    
    def handle_mouseup(self, pos: tuple[int, int]):
        """Handle mouse release (end slider drag)."""
        if self.audio_slider_dragging:
            self.audio_slider_dragging = False
            if self.current_page == "audio":
                # WK7: Final volume update on release
                if self.audio_system:
                    self.audio_system.set_master_volume(self.audio_slider.value)
                return "audio_slider_release"
        return None
    
    def render(self, surface: pygame.Surface):
        """Render the menu."""
        if not self.visible:
            return
        
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
            
            # Buttons
            for page_name, rect in self.page_buttons.items():
                # Button background
                is_hover = rect.collidepoint(pygame.mouse.get_pos())
                tex = self._button_tex_hover if is_hover else self._button_tex_normal
                if not NineSlice.render(surface, rect, tex, border=self._button_slice_border):
                    bg_color = (70, 70, 80) if is_hover else (50, 50, 60)
                    pygame.draw.rect(surface, bg_color, rect)
                    pygame.draw.rect(surface, self.theme.panel_border, rect, 2)
                
                # Button text
                label = page_name.replace("_", " ").title()
                text_surf = self.theme.font_body.render(label, True, self.theme.text)
                icon = self._icon_map.get(page_name)
                if icon is not None:
                    icon_x = rect.x + 12
                    icon_y = rect.centery - icon.get_height() // 2
                    surface.blit(icon, (icon_x, icon_y))
                    text_x = icon_x + icon.get_width() + 8
                else:
                    text_x = rect.centerx - text_surf.get_width() // 2
                text_y = rect.centery - text_surf.get_height() // 2
                surface.blit(text_surf, (text_x, text_y))
        
        elif self.current_page == "graphics":
            # Graphics page
            title = self.theme.font_title.render("Graphics", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))
            
            # Display mode options
            label = self.theme.font_body.render("Display Mode:", True, self.theme.text)
            surface.blit(label, (panel_rect.x + 80, panel_rect.y + 110))
            
            radio_x = panel_rect.x + 80
            radio_y = panel_rect.y + 140
            radio_w = panel_rect.width - 160
            self.graphics_radio.render(
                surface, self.theme.font_body,
                radio_x, radio_y, radio_w,
                text_color=self.theme.text,
                selected_color=(100, 150, 200),
                bg_color=(50, 50, 60)
            )
            
            # Back button
            back_text = self.theme.font_small.render("< Back", True, self.theme.text)
            surface.blit(back_text, (panel_rect.x + 10, panel_rect.y + 10))
        
        elif self.current_page == "audio":
            # Audio page
            title = self.theme.font_title.render("Audio", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))
            
            # Master volume label
            volume_label = self.theme.font_body.render("Master Volume:", True, self.theme.text)
            surface.blit(volume_label, (panel_rect.x + 80, panel_rect.y + 140))
            
            # Volume percentage
            volume_pct = int(self.audio_slider.value * 100)
            volume_text = self.theme.font_body.render(f"{volume_pct}%", True, self.theme.text)
            surface.blit(volume_text, (panel_rect.x + 80, panel_rect.y + 170))
            
            # Slider
            self.audio_slider.render(surface)
            
            # Back button
            back_text = self.theme.font_small.render("< Back", True, self.theme.text)
            surface.blit(back_text, (panel_rect.x + 10, panel_rect.y + 10))
        
        elif self.current_page == "controls":
            # Controls page
            title = self.theme.font_title.render("Controls", True, self.theme.text)
            title_x = panel_rect.centerx - title.get_width() // 2
            surface.blit(title, (title_x, panel_rect.y + 20))
            
            # Keybinds list
            y = panel_rect.y + 60
            for key, desc in self.keybinds:
                if not key and not desc:
                    y += 10  # Spacing
                    continue
                
                if desc and not key:
                    # Section header
                    header = self.theme.font_body.render(desc, True, self.theme.accent)
                    surface.blit(header, (panel_rect.x + 20, y))
                    y += 30
                else:
                    # Keybind row
                    key_text = self.theme.font_body.render(key, True, self.theme.text)
                    surface.blit(key_text, (panel_rect.x + 30, y))
                    
                    if desc:
                        desc_text = self.theme.font_small.render(desc, True, (200, 200, 200))
                        surface.blit(desc_text, (panel_rect.x + 120, y + 2))
                    y += 24
            
            # Back button
            back_text = self.theme.font_small.render("< Back", True, self.theme.text)
            surface.blit(back_text, (panel_rect.x + 10, panel_rect.y + 10))
