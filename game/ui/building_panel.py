"""Building detail panel for selected structures."""

from __future__ import annotations

import pygame

from config import COLOR_GREEN, COLOR_RED, COLOR_UI_BG, COLOR_UI_BORDER, COLOR_WHITE
from game.ui.building_renderers import get_panel_renderer, normalize_building_type_key
from game.ui.widgets import Button, NineSlice


class BuildingPanel:
    """Panel that shows detailed building information when a building is selected."""

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.visible = False
        self.selected_building = None

        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._panel_slice_border = 8

        self.panel_width = 300
        self.panel_height = 400
        self._panel_height_max = 700  # scratch height for dynamic sizing
        self.panel_x = 10
        self.panel_y = 50

        self.font_title = pygame.font.Font(None, 28)
        self.font_normal = pygame.font.Font(None, 20)
        self.font_small = pygame.font.Font(None, 16)

        self.close_button_rect: pygame.Rect | None = None
        self.close_button_hovered = False
        self.research_button_rect: pygame.Rect | None = None
        self.research_button_hovered = False
        self.library_research_rects: dict[str, pygame.Rect] = {}
        self.library_research_hovered: str | None = None
        self.upgrade_button_rect: pygame.Rect | None = None
        self.upgrade_button_hovered = False
        self.demolish_button_rect: pygame.Rect | None = None
        self.demolish_button_hovered = False
        self.enter_building_button_rect: pygame.Rect | None = None
        self.enter_building_button_hovered = False
        self.build_catalog_button_rect: pygame.Rect | None = None
        self.build_catalog_button_hovered = False
        self.blacksmith_research_rects: dict[str, pygame.Rect] = {}
        self.blacksmith_research_hovered: str | None = None

        self.portrait_colors = [
            (70, 130, 180),
            (178, 34, 34),
            (46, 139, 87),
            (218, 165, 32),
            (147, 112, 219),
            (205, 92, 92),
            (60, 179, 113),
            (255, 140, 0),
        ]
        # Set by GameEngine after init — used to flag Ursina HUD GPU upload for thin animated bars.
        self.engine = None

    def select_building(self, building, heroes: list) -> None:
        """Select a building to show details for."""
        self.selected_building = building
        self.visible = True

    def deselect(self) -> None:
        """Deselect the current building."""
        self.selected_building = None
        self.visible = False

    def get_heroes_for_building(self, building, all_heroes: list) -> dict:
        """Get heroes associated with this building."""
        result = {
            "total": 0,
            "resting": [],
            "fighting": [],
            "idle": [],
            "moving": [],
            "other": [],
        }
        for hero in all_heroes:
            if not hero.is_alive:
                continue
            if hero.home_building == building:
                result["total"] += 1
                state_name = hero.state.name.lower()
                if state_name == "resting":
                    result["resting"].append(hero)
                elif state_name == "fighting":
                    result["fighting"].append(hero)
                elif state_name == "idle":
                    result["idle"].append(hero)
                elif state_name == "moving":
                    result["moving"].append(hero)
                else:
                    result["other"].append(hero)
        return result

    def _building_type_key(self, building) -> str:
        """Return normalized string key for a building type."""
        return normalize_building_type_key(getattr(building, "building_type", ""))

    def handle_click(self, mouse_pos: tuple[int, int], economy, game_state: dict) -> bool | dict:
        """Handle panel clicks. Returns True or action dict when handled."""
        if not self.visible or not self.selected_building:
            return False
        if not (
            self.panel_x <= mouse_pos[0] <= self.panel_x + self.panel_width
            and self.panel_y <= mouse_pos[1] <= self.panel_y + self.panel_height
        ):
            return False

        building_type = self._building_type_key(self.selected_building)

        if self.close_button_rect and self.close_button_rect.collidepoint(mouse_pos):
            self.deselect()
            return True

        if self.enter_building_button_rect and self.enter_building_button_rect.collidepoint(mouse_pos):
            building = self.selected_building
            if building and getattr(building, "max_occupants", 0) > 0 and getattr(building, "is_constructed", True):
                return {"type": "enter_building", "building": building}

        if self.demolish_button_rect and self.demolish_button_rect.collidepoint(mouse_pos):
            building = self.selected_building
            if building_type == "castle":
                return True
            if getattr(building, "is_lair", False):
                return True
            if hasattr(building, "is_constructed") and not building.is_constructed:
                return True
            return {"type": "demolish_building", "building": building}

        if self.research_button_rect and building_type == "marketplace":
            if self.research_button_rect.collidepoint(mouse_pos):
                if hasattr(self.selected_building, "is_constructed") and not self.selected_building.is_constructed:
                    return True
                # WK15: Start timed research if building supports it; otherwise legacy instant unlock.
                if hasattr(self.selected_building, "start_research_potions"):
                    if self.selected_building.start_research_potions(economy):
                        return True
                elif not self.selected_building.potions_researched and economy.player_gold >= 100:
                    economy.player_gold -= 100
                    self.selected_building.potions_researched = True
                    return True

        if self.build_catalog_button_rect and building_type == "castle":
            if self.build_catalog_button_rect.collidepoint(mouse_pos):
                return {"type": "open_build_catalog"}

        if self.upgrade_button_rect and building_type == "palace":
            if self.upgrade_button_rect.collidepoint(mouse_pos):
                if self.selected_building.can_upgrade() and self.selected_building.upgrade(economy):
                    return True

        if building_type == "library" and self.library_research_rects:
            for research_name, rect in self.library_research_rects.items():
                if rect.collidepoint(mouse_pos):
                    if hasattr(self.selected_building, "is_constructed") and not self.selected_building.is_constructed:
                        return True
                    self.selected_building.research(research_name, economy, game_state)
                    return True

        if building_type == "blacksmith" and self.blacksmith_research_rects:
            for research_key, rect in self.blacksmith_research_rects.items():
                if rect.collidepoint(mouse_pos):
                    if hasattr(self.selected_building, "is_constructed") and not self.selected_building.is_constructed:
                        return True
                    self._apply_blacksmith_research(self.selected_building, research_key, economy, game_state)
                    return True

        return True

    def update_hover(self, mouse_pos: tuple[int, int]) -> None:
        """Update button hover state from screen-space mouse coordinates."""
        if self.close_button_rect:
            self.close_button_hovered = self.close_button_rect.collidepoint(mouse_pos)
        else:
            self.close_button_hovered = False
        if self.research_button_rect:
            self.research_button_hovered = self.research_button_rect.collidepoint(mouse_pos)
        if self.demolish_button_rect:
            self.demolish_button_hovered = self.demolish_button_rect.collidepoint(mouse_pos)
        else:
            self.demolish_button_hovered = False
        if self.enter_building_button_rect:
            self.enter_building_button_hovered = self.enter_building_button_rect.collidepoint(mouse_pos)
        else:
            self.enter_building_button_hovered = False
        if self.build_catalog_button_rect:
            self.build_catalog_button_hovered = self.build_catalog_button_rect.collidepoint(mouse_pos)
        else:
            self.build_catalog_button_hovered = False
        if self.upgrade_button_rect:
            self.upgrade_button_hovered = self.upgrade_button_rect.collidepoint(mouse_pos)
        else:
            self.upgrade_button_hovered = False

        building_type = self._building_type_key(self.selected_building) if (self.visible and self.selected_building) else ""

        self.library_research_hovered = None
        if self.visible and self.selected_building and building_type == "library":
            for research_name, rect in self.library_research_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.library_research_hovered = research_name
                    break

        self.blacksmith_research_hovered = None
        if self.visible and self.selected_building and building_type == "blacksmith":
            for research_key, rect in self.blacksmith_research_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.blacksmith_research_hovered = research_key
                    break

    def render(self, surface: pygame.Surface, heroes: list, economy) -> None:
        """Render selected building panel."""
        if not self.visible or not self.selected_building:
            return

        building = self.selected_building
        self.library_research_rects = {}
        self.blacksmith_research_rects = {}
        self.research_button_rect = None
        self.upgrade_button_rect = None
        self.build_catalog_button_rect = None
        self.demolish_button_rect = None
        self.enter_building_button_rect = None

        # Render to oversized scratch so content height can exceed 400 (wk13 hotfix: Enter Building not clipped)
        scratch_h = min(self._panel_height_max, max(400, self.screen_height - self.panel_y - 20))
        panel_surf = pygame.Surface((self.panel_width, scratch_h), pygame.SRCALPHA)
        if not NineSlice.render(
            panel_surf,
            pygame.Rect(0, 0, self.panel_width, scratch_h),
            self._panel_tex_modal,
            border=self._panel_slice_border,
        ):
            panel_surf.fill((*COLOR_UI_BG, 240))
            pygame.draw.rect(panel_surf, COLOR_UI_BORDER, (0, 0, self.panel_width, scratch_h), 2)

        y = 10
        building_type_key = self._building_type_key(building)
        building_name = building_type_key.replace("_", " ").title()
        title = self.font_title.render(building_name, True, COLOR_WHITE)
        panel_surf.blit(title, (10, y))
        y += 35
        pygame.draw.line(panel_surf, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10

        renderer = get_panel_renderer(getattr(building, "building_type", ""))
        y = renderer.render(self, panel_surf, building, heroes, y, economy)
        y = self._render_demolish_button(panel_surf, building, y)
        y = self._render_enter_building_button(panel_surf, building, y)

        bottom_padding = 20
        self.panel_height = min(scratch_h, max(400, y + bottom_padding))

        # Add close button
        close_size = 24
        cb_rect = pygame.Rect(self.panel_width - close_size - 10, 10, close_size, close_size)
        close_btn = Button(
            rect=cb_rect,
            text="X",
            font=self.font_normal,
            enabled=True,
        )
        close_btn.render(
            panel_surf,
            mouse_pos=(pygame.mouse.get_pos()[0] - self.panel_x, pygame.mouse.get_pos()[1] - self.panel_y) if self.close_button_hovered else None,
            enabled=True,
            bg_normal=(45, 45, 55),
            bg_hover=(60, 60, 70),
            bg_pressed=(70, 70, 85),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=(240, 240, 240),
        )
        self.close_button_rect = pygame.Rect(self.panel_x + cb_rect.x, self.panel_y + cb_rect.y, cb_rect.width, cb_rect.height)

        visible = panel_surf.subsurface((0, 0, self.panel_width, self.panel_height))
        surface.blit(visible, (self.panel_x, self.panel_y))

    def render_hero_row(self, surface: pygame.Surface, hero, y: int, index: int) -> int:
        """Render one hero row (portrait + status + vitals)."""
        portrait_color = self.portrait_colors[index % len(self.portrait_colors)]
        portrait_x = 20
        portrait_radius = 12
        pygame.draw.circle(surface, portrait_color, (portrait_x, y + 10), portrait_radius)
        pygame.draw.circle(surface, COLOR_WHITE, (portrait_x, y + 10), portrait_radius, 1)

        status_color = self.get_status_color(hero.state.name)
        name_text = self.font_small.render(f"{hero.name}", True, COLOR_WHITE)
        surface.blit(name_text, (40, y))
        status_text = self.font_small.render(f"[{hero.state.name}]", True, status_color)
        surface.blit(status_text, (40 + name_text.get_width() + 5, y))

        hp_bar_x = 40
        hp_bar_y = y + 14
        hp_bar_width = 80
        hp_bar_height = 6
        pygame.draw.rect(surface, (60, 60, 60), (hp_bar_x, hp_bar_y, hp_bar_width, hp_bar_height))
        hp_pct = hero.hp / max(1, hero.max_hp)
        hp_color = COLOR_GREEN if hp_pct > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hp_color, (hp_bar_x, hp_bar_y, hp_bar_width * hp_pct, hp_bar_height))

        hp_text = self.font_small.render(f"{hero.hp}/{hero.max_hp}", True, (150, 150, 150))
        surface.blit(hp_text, (hp_bar_x + hp_bar_width + 5, y + 7))
        pot_color = (100, 200, 100) if hero.potions > 0 else (130, 130, 130)
        pot_text = self.font_small.render(f"Potions: {hero.potions}", True, pot_color)
        surface.blit(pot_text, (180, y + 7))
        return y + 28

    def get_status_color(self, status: str) -> tuple[int, int, int]:
        """Get display color for hero status."""
        status_colors = {
            "FIGHTING": (220, 60, 60),
            "RESTING": (100, 150, 255),
            "IDLE": (150, 150, 150),
            "MOVING": (200, 200, 100),
            "RETREATING": (255, 165, 0),
            "SHOPPING": (218, 165, 32),
        }
        return status_colors.get(status.upper(), (150, 150, 150))

    def _apply_blacksmith_research(self, building, key: str, economy, game_state: dict):
        """Best-effort call into blacksmith research APIs."""
        if not building:
            return None
        try:
            if callable(getattr(building, "research", None)):
                try:
                    return building.research(key, economy, game_state)
                except TypeError:
                    try:
                        return building.research(key, economy)
                    except TypeError:
                        return building.research(key)

            if hasattr(building, "research_upgrade"):
                try:
                    return building.research_upgrade(key, economy, game_state)
                except TypeError:
                    try:
                        return building.research_upgrade(key, economy)
                    except TypeError:
                        return building.research_upgrade(key)
            if key == "weapon" and hasattr(building, "research_weapon_upgrade"):
                try:
                    return building.research_weapon_upgrade(economy, game_state)
                except TypeError:
                    return building.research_weapon_upgrade(economy)
            if key == "armor" and hasattr(building, "research_armor_upgrade"):
                try:
                    return building.research_armor_upgrade(economy, game_state)
                except TypeError:
                    return building.research_armor_upgrade(economy)
        except Exception:
            return None
        return None

    def _render_demolish_button(self, surface: pygame.Surface, building, y: int) -> int:
        """Render bottom demolish button and update hit rect."""
        if self._building_type_key(building) == "castle" or getattr(building, "is_lair", False):
            self.demolish_button_rect = None
            return y

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10

        is_under_construction = hasattr(building, "is_constructed") and not building.is_constructed
        local_rect = pygame.Rect(10, y, 200, 30)
        text = "Demolish (Under Construction)" if is_under_construction else "Demolish"
        button = Button(
            rect=local_rect,
            text=text,
            font=self.font_small,
            enabled=not is_under_construction,
        )
        button.render(
            surface,
            mouse_pos=pygame.mouse.get_pos() if self.demolish_button_hovered else None,
            enabled=not is_under_construction,
            bg_normal=(120, 40, 40),
            bg_hover=(160, 60, 60),
            bg_pressed=(170, 70, 70),
            bg_disabled=(80, 80, 80),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=COLOR_WHITE,
            text_disabled_color=(120, 120, 120),
        )
        self.demolish_button_rect = pygame.Rect(
            self.panel_x + local_rect.x,
            self.panel_y + local_rect.y,
            local_rect.width,
            local_rect.height,
        )
        y += local_rect.height + 10
        return y

    def _render_enter_building_button(self, surface: pygame.Surface, building, y: int) -> int:
        """Render 'Enter Building' button for enterable, fully constructed buildings (wk13 Living Interiors)."""
        max_occ = int(getattr(building, "max_occupants", 0))
        is_constructed = getattr(building, "is_constructed", True)
        building_type_key = self._building_type_key(building)
        if max_occ <= 0 or not is_constructed or building_type_key == "castle":
            self.enter_building_button_rect = None
            return y

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10

        local_rect = pygame.Rect(10, y, 200, 30)
        button = Button(
            rect=local_rect,
            text="Enter Building",
            font=self.font_small,
            enabled=True,
        )
        button.render(
            surface,
            mouse_pos=pygame.mouse.get_pos() if self.enter_building_button_hovered else None,
            enabled=True,
            bg_normal=(40, 100, 60),
            bg_hover=(60, 140, 80),
            bg_pressed=(50, 120, 70),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=COLOR_WHITE,
        )
        self.enter_building_button_rect = pygame.Rect(
            self.panel_x + local_rect.x,
            self.panel_y + local_rect.y,
            local_rect.width,
            local_rect.height,
        )
        y += local_rect.height + 10
        return y

