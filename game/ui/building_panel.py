"""Building detail panel for selected structures."""

from __future__ import annotations

from collections.abc import Callable

import pygame

from config import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_UI_BG,
    COLOR_UI_BORDER,
    COLOR_WHITE,
    HERO_HIRE_COST,
)
from game.ui.building_renderers import get_panel_renderer, normalize_building_type_key
from game.ui.hud import HERO_LEFT_MIN_H, LEFT_COL_W, RADAR_MINIMAP_H
from game.ui.quest_create_panel import QuestCreatePanel
from game.ui.widgets import Button, NineSlice

# WK68 G2: buildings that can hire a hero from their own panel.
# source of truth: engine.py:962 `allowed` (try_hire_hero). temple hires a Cleric.
_HIRABLE_TYPES = frozenset(
    {"warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild", "temple"}
)


class BuildingPanel:
    """Panel that shows detailed building information when a building is selected."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        *,
        on_request_ursina_hud_upload: Callable[[], None] | None = None,
    ) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.visible = False
        self.selected_building = None

        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._panel_slice_border = 8

        self.panel_width = LEFT_COL_W
        self.panel_height = 400
        self._panel_height_max = 700  # scratch height for dynamic sizing
        self.menu_scroll_px = 0
        self._menu_max_scroll = 0
        # WK115 BUG 1: natural full content height of the last-rendered building card
        # (header + body + bottom pad, clamped >= HERO_LEFT_MIN_H, NOT clamped to the
        # viewport). Lets the left-column solo layout size the card to its content.
        self.last_content_height = 0
        self._scroll_anchor_id: int | None = None
        self.panel_x = 0
        self.panel_y = 48

        self.font_title = pygame.font.Font(None, 28)
        self.font_normal = pygame.font.Font(None, 20)
        self.font_small = pygame.font.Font(None, 16)

        self.close_button_rect: pygame.Rect | None = None
        self.close_button_hovered = False
        self.research_button_rect: pygame.Rect | None = None
        self.research_button_hovered = False
        self.upgrade_button_rect: pygame.Rect | None = None
        self.upgrade_button_hovered = False
        self.demolish_button_rect: pygame.Rect | None = None
        self.demolish_button_hovered = False
        self.enter_building_button_rect: pygame.Rect | None = None
        self.enter_building_button_hovered = False
        self.hire_hero_button_rect: pygame.Rect | None = None
        self.hire_hero_button_hovered = False
        self.build_catalog_button_rect: pygame.Rect | None = None
        self.build_catalog_button_hovered = False
        self.blacksmith_research_rects: dict[str, pygame.Rect] = {}
        self.blacksmith_research_hovered: str | None = None
        # WK126-T9: Herald's Post → "Create Quest" affordance + the modal it opens.
        # The modal is owned/rendered/click-routed here because the building panel
        # is the selection surface AND its handle_click is the first input hook in
        # game/input/mouse.py that can consume every click while a building is
        # selected (mirrors the build-catalog modal semantics; ESC handled in
        # game/input/keyboard.py).
        self.quest_create_panel = QuestCreatePanel(self.screen_width, self.screen_height)
        self.create_quest_button_rect: pygame.Rect | None = None
        self.create_quest_button_hovered = False

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
        # Optional: wired by GameEngine (Ursina) so economic renderers can request a full HUD surface re-upload
        # for thin progress bars that row-sampling may miss; no engine reference is stored.
        self.on_request_ursina_hud_upload = on_request_ursina_hud_upload

    def select_building(self, building, heroes: list) -> None:
        """Select a building to show details for."""
        new_id = id(building) if building is not None else None
        if new_id != self._scroll_anchor_id:
            self.menu_scroll_px = 0
            self._scroll_anchor_id = new_id
        self.selected_building = building
        self.visible = True

    def deselect(self) -> None:
        """Deselect the current building."""
        self.selected_building = None
        self.visible = False
        self.menu_scroll_px = 0
        self._scroll_anchor_id = None
        # WK126-T9: the quest-create modal cannot outlive its post's selection.
        if self.quest_create_panel.visible:
            self.quest_create_panel.close()

    def apply_menu_scroll(self, wheel_y: int) -> bool:
        if wheel_y == 0 or self._menu_max_scroll <= 0:
            return False
        self.menu_scroll_px -= wheel_y * 24
        self.menu_scroll_px = max(0, min(self.menu_scroll_px, self._menu_max_scroll))
        return True

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

    def _rect_in_viewport(self, rect: pygame.Rect | None) -> bool:
        """True iff a stored interactive rect is inside the visible (clipped) left-column viewport.

        WK68 G1: panel content is rendered into a tall scratch surface and only a scroll-offset
        slice is blitted into ``Rect(panel_x, panel_y, panel_width, panel_height)``. Interactive
        rects are stored with the scroll offset already subtracted (so they track the on-screen
        position), but a button scrolled above/below the clip must not be clickable "through" the
        edge. Gate every collidepoint on this so only rects whose center is actually visible hit.
        """
        if rect is None:
            return False
        viewport = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        return viewport.collidepoint(rect.center)

    def handle_click(self, mouse_pos: tuple[int, int], economy, game_state: dict) -> bool | dict:
        """Handle panel clicks. Returns True or action dict when handled."""
        # WK126-T9: while the quest-create modal is open it is MODAL — it gets
        # every click (anywhere on screen) before the panel's own bounds check,
        # and always consumes (click outside the modal cancels, like the catalog).
        if self.quest_create_panel.visible:
            self.quest_create_panel.handle_click(mouse_pos, economy)
            return True
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

        if self._rect_in_viewport(self.enter_building_button_rect) and self.enter_building_button_rect.collidepoint(mouse_pos):
            building = self.selected_building
            if building and getattr(building, "max_occupants", 0) > 0 and getattr(building, "is_constructed", True):
                return {"type": "enter_building", "building": building}

        if self.hire_hero_button_rect and self._rect_in_viewport(self.hire_hero_button_rect) and self.hire_hero_button_rect.collidepoint(mouse_pos):
            building = self.selected_building
            if building and getattr(building, "is_constructed", True) and (
                (not hasattr(building, "can_hire")) or building.can_hire()
            ):
                return {"type": "hire_hero", "building": building}

        if (
            self.create_quest_button_rect
            and self._rect_in_viewport(self.create_quest_button_rect)
            and self.create_quest_button_rect.collidepoint(mouse_pos)
        ):
            building = self.selected_building
            if (
                building is not None
                and building_type == "herald_post"
                and getattr(building, "is_constructed", True)
            ):
                self.quest_create_panel.open(building, game_state)
            return True

        if self._rect_in_viewport(self.demolish_button_rect) and self.demolish_button_rect.collidepoint(mouse_pos):
            building = self.selected_building
            if building_type == "castle":
                return True
            if getattr(building, "is_lair", False):
                return True
            if hasattr(building, "is_constructed") and not building.is_constructed:
                return True
            return {"type": "demolish_building", "building": building}

        if self._rect_in_viewport(self.research_button_rect) and building_type == "marketplace":
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

        if self._rect_in_viewport(self.build_catalog_button_rect) and building_type == "castle":
            if self.build_catalog_button_rect.collidepoint(mouse_pos):
                return {"type": "open_build_catalog"}

        if self._rect_in_viewport(self.upgrade_button_rect) and building_type == "palace":
            if self.upgrade_button_rect.collidepoint(mouse_pos):
                if self.selected_building.can_upgrade() and self.selected_building.upgrade(economy):
                    return True

        if building_type == "blacksmith" and self.blacksmith_research_rects:
            for research_key, rect in self.blacksmith_research_rects.items():
                if self._rect_in_viewport(rect) and rect.collidepoint(mouse_pos):
                    if hasattr(self.selected_building, "is_constructed") and not self.selected_building.is_constructed:
                        return True
                    self._apply_blacksmith_research(self.selected_building, research_key, economy, game_state)
                    return True

        return True

    def update_hover(self, mouse_pos: tuple[int, int]) -> None:
        """Update button hover state from screen-space mouse coordinates."""
        if self.quest_create_panel.visible:
            self.quest_create_panel.update_hover(mouse_pos)
        if self.create_quest_button_rect:
            self.create_quest_button_hovered = self._rect_in_viewport(self.create_quest_button_rect) and self.create_quest_button_rect.collidepoint(mouse_pos)
        else:
            self.create_quest_button_hovered = False
        if self.close_button_rect:
            self.close_button_hovered = self.close_button_rect.collidepoint(mouse_pos)
        else:
            self.close_button_hovered = False
        if self.research_button_rect:
            self.research_button_hovered = self._rect_in_viewport(self.research_button_rect) and self.research_button_rect.collidepoint(mouse_pos)
        if self.demolish_button_rect:
            self.demolish_button_hovered = self._rect_in_viewport(self.demolish_button_rect) and self.demolish_button_rect.collidepoint(mouse_pos)
        else:
            self.demolish_button_hovered = False
        if self.enter_building_button_rect:
            self.enter_building_button_hovered = self._rect_in_viewport(self.enter_building_button_rect) and self.enter_building_button_rect.collidepoint(mouse_pos)
        else:
            self.enter_building_button_hovered = False
        if self.hire_hero_button_rect:
            self.hire_hero_button_hovered = self._rect_in_viewport(self.hire_hero_button_rect) and self.hire_hero_button_rect.collidepoint(mouse_pos)
        else:
            self.hire_hero_button_hovered = False
        if self.build_catalog_button_rect:
            self.build_catalog_button_hovered = self._rect_in_viewport(self.build_catalog_button_rect) and self.build_catalog_button_rect.collidepoint(mouse_pos)
        else:
            self.build_catalog_button_hovered = False
        if self.upgrade_button_rect:
            self.upgrade_button_hovered = self._rect_in_viewport(self.upgrade_button_rect) and self.upgrade_button_rect.collidepoint(mouse_pos)
        else:
            self.upgrade_button_hovered = False

        building_type = self._building_type_key(self.selected_building) if (self.visible and self.selected_building) else ""

        self.blacksmith_research_hovered = None
        if self.visible and self.selected_building and building_type == "blacksmith":
            for research_key, rect in self.blacksmith_research_rects.items():
                if self._rect_in_viewport(rect) and rect.collidepoint(mouse_pos):
                    self.blacksmith_research_hovered = research_key
                    break

    def _fallback_left_rect(self, surface: pygame.Surface) -> pygame.Rect:
        """Match HUD `_layout_rects_for_screen` when no hero is pinned (tests / legacy callers)."""
        _, h = surface.get_size()
        top_h = 48
        minimap_y = max(0, h - int(RADAR_MINIMAP_H))
        left_h = max(0, minimap_y - top_h)
        return pygame.Rect(0, top_h, int(LEFT_COL_W), left_h)

    def render(
        self,
        surface: pygame.Surface,
        heroes: list,
        economy,
        *,
        left_rect: pygame.Rect | None = None,
    ) -> None:
        """Render selected building panel."""
        if not self.visible or not self.selected_building:
            return

        lr = left_rect if left_rect is not None else self._fallback_left_rect(surface)
        self.panel_width = max(120, int(lr.width))
        self.panel_x = int(lr.x)
        self.panel_y = int(lr.y)

        building = self.selected_building
        self.blacksmith_research_rects = {}
        self.research_button_rect = None
        self.upgrade_button_rect = None
        self.build_catalog_button_rect = None
        self.demolish_button_rect = None
        self.enter_building_button_rect = None
        self.hire_hero_button_rect = None
        self.create_quest_button_rect = None

        viewport_h = min(self._panel_height_max, max(120, int(lr.height)))
        # WK68 G1: pre-clamp the scroll against the prior frame's max so the interactive rects
        # (stored below with ``- self.menu_scroll_px``) use the SAME offset as the final blit's
        # ``src_y`` — keeping the clickable rect aligned with the on-screen (scrolled, clipped)
        # button. The post-render clamp at the end only tightens this if content shrank this frame.
        self.menu_scroll_px = max(0, min(self.menu_scroll_px, self._menu_max_scroll))
        scratch_h = max(900, viewport_h + 400)
        scratch_h = min(2400, scratch_h)
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
        y = self._render_create_quest_button(panel_surf, building, y)
        y = self._render_demolish_button(panel_surf, building, y)
        y = self._render_enter_building_button(panel_surf, building, y)
        y = self._render_hire_hero_button(panel_surf, building, y, economy)

        bottom_padding = 20
        content_h = min(scratch_h, y + bottom_padding)
        # WK115 BUG 1: remember the natural full height the card needs so the
        # left-column solo layout sizes the panel to its content (no floating bar).
        self.last_content_height = max(HERO_LEFT_MIN_H, int(content_h))

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

        self._menu_max_scroll = max(0, content_h - viewport_h)
        self.menu_scroll_px = max(0, min(self.menu_scroll_px, self._menu_max_scroll))
        src_y = self.menu_scroll_px
        dest_clip = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, viewport_h)
        prev_clip = surface.get_clip()
        surface.set_clip(dest_clip)
        surface.blit(
            panel_surf,
            (self.panel_x, self.panel_y),
            area=pygame.Rect(0, src_y, self.panel_width, min(viewport_h, content_h - src_y)),
        )
        surface.set_clip(prev_clip)
        self.panel_height = viewport_h

        # WK126-T9: the quest-create modal draws last (on top of the panel/HUD;
        # this render call runs after HUD render in the render coordinator).
        if self.quest_create_panel.visible:
            self.quest_create_panel.render(surface, economy)

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
        nx = 40 + name_text.get_width() + 5
        if nx + status_text.get_width() < self.panel_width - 8:
            surface.blit(status_text, (nx, y))
        else:
            surface.blit(status_text, (40, y + name_text.get_height() + 1))

        hp_bar_x = 40
        hp_bar_y = y + 14
        hp_bar_width = max(36, min(100, self.panel_width - 55))
        hp_bar_height = 6
        pygame.draw.rect(surface, (60, 60, 60), (hp_bar_x, hp_bar_y, hp_bar_width, hp_bar_height))
        hp_pct = hero.hp / max(1, hero.max_hp)
        hp_color = COLOR_GREEN if hp_pct > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hp_color, (hp_bar_x, hp_bar_y, hp_bar_width * hp_pct, hp_bar_height))

        hp_text = self.font_small.render(f"{hero.hp}/{hero.max_hp}", True, (150, 150, 150))
        surface.blit(hp_text, (hp_bar_x + hp_bar_width + 4, hp_bar_y - 2))
        pot_color = (100, 200, 100) if hero.potions > 0 else (130, 130, 130)
        pot_text = self.font_small.render(f"Potions: {hero.potions}", True, pot_color)
        pot_y = hp_bar_y + hp_bar_height + 2
        surface.blit(pot_text, (hp_bar_x, pot_y))
        return y + max(38, pot_y + pot_text.get_height() - y)

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
        bw = max(60, self.panel_width - 20)
        local_rect = pygame.Rect(10, y, bw, 30)
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
            self.panel_y + local_rect.y - self.menu_scroll_px,
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

        bw = max(60, self.panel_width - 20)
        local_rect = pygame.Rect(10, y, bw, 30)
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
            self.panel_y + local_rect.y - self.menu_scroll_px,
            local_rect.width,
            local_rect.height,
        )
        y += local_rect.height + 10
        return y

    def _render_create_quest_button(self, surface: pygame.Surface, building, y: int) -> int:
        """Render 'Create Quest' on the Herald's Post card (WK126-T9).

        Mirrors the Enter/Hire buttons + the G1 scroll-aware rect convention.
        Disabled (greyed, no live hit-rect) while the post is under construction;
        reward affordability is gated inside the quest-create dialog itself.
        """
        self.create_quest_button_rect = None
        if self._building_type_key(building) != "herald_post":
            return y

        enabled = bool(getattr(building, "is_constructed", True))

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10

        bw = max(60, self.panel_width - 20)
        local_rect = pygame.Rect(10, y, bw, 30)
        button = Button(
            rect=local_rect,
            text="Create Quest" if enabled else "Create Quest (Under Construction)",
            font=self.font_small,
            enabled=enabled,
        )
        button.render(
            surface,
            mouse_pos=pygame.mouse.get_pos() if (enabled and self.create_quest_button_hovered) else None,
            enabled=enabled,
            bg_normal=(60, 80, 150),
            bg_hover=(80, 105, 190),
            bg_pressed=(70, 95, 170),
            bg_disabled=(80, 80, 80),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=COLOR_WHITE,
            text_disabled_color=(120, 120, 120),
        )

        sub_color = (180, 180, 180) if enabled else (120, 120, 120)
        sub = self.font_small.render("Fund a quest for heroes to take", True, sub_color)
        sub_y = local_rect.bottom + 2
        surface.blit(sub, (12, sub_y))

        if enabled:
            self.create_quest_button_rect = pygame.Rect(
                self.panel_x + local_rect.x,
                self.panel_y + local_rect.y - self.menu_scroll_px,
                local_rect.width,
                local_rect.height,
            )
        y = sub_y + sub.get_height() + 10
        return y

    def _render_hire_hero_button(self, surface: pygame.Surface, building, y: int, economy) -> int:
        """Render 'Hire Hero $100' button on the 5 hirable buildings (WK68 G2).

        Mirrors the Enter/Demolish buttons + uses the G1 scroll-aware rect convention.
        Disabled (greyed, no live hit-rect) when at the hero cap or when gold < HERO_HIRE_COST.
        """
        self.hire_hero_button_rect = None
        if self._building_type_key(building) not in _HIRABLE_TYPES:
            return y
        if not getattr(building, "is_constructed", True):
            return y

        can_hire = (not hasattr(building, "can_hire")) or building.can_hire()
        affordable = bool(economy is not None and getattr(economy, "player_gold", 0) >= HERO_HIRE_COST)
        enabled = can_hire and affordable

        pygame.draw.line(surface, COLOR_UI_BORDER, (10, y), (self.panel_width - 10, y))
        y += 10

        bw = max(60, self.panel_width - 20)
        local_rect = pygame.Rect(10, y, bw, 30)
        button = Button(
            rect=local_rect,
            text=f"Hire Hero  ${HERO_HIRE_COST}",
            font=self.font_small,
            enabled=enabled,
        )
        button.render(
            surface,
            mouse_pos=pygame.mouse.get_pos() if (enabled and self.hire_hero_button_hovered) else None,
            enabled=enabled,
            bg_normal=(50, 90, 140),
            bg_hover=(70, 120, 180),
            bg_pressed=(60, 105, 160),
            bg_disabled=(80, 80, 80),
            border_outer=(20, 20, 25),
            border_inner=(80, 80, 100),
            border_highlight=(107, 107, 132),
            text_color=COLOR_WHITE,
            text_disabled_color=(120, 120, 120),
        )

        # Cap sub-line below the button.
        hired = int(getattr(building, "heroes_hired", 0))
        cap = int(getattr(building, "max_heroes", 8))
        sub_color = (180, 180, 180) if enabled else (120, 120, 120)
        sub = self.font_small.render(f"Heroes: {hired}/{cap}", True, sub_color)
        sub_y = local_rect.bottom + 2
        surface.blit(sub, (12, sub_y))

        if enabled:
            self.hire_hero_button_rect = pygame.Rect(
                self.panel_x + local_rect.x,
                self.panel_y + local_rect.y - self.menu_scroll_px,
                local_rect.width,
                local_rect.height,
            )
        y = sub_y + sub.get_height() + 10
        return y

