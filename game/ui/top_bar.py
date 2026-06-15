"""Top-bar rendering for HUD statistics and quit action."""

from __future__ import annotations

from typing import Any

import pygame

from config import COLOR_GOLD, COLOR_RED, COLOR_WHITE
from game.content.elite_affixes import get_elite_affix_def
from game.ui.widgets import Button, TextLabel


class TopBar:
    """Render top-bar metrics and quit button."""

    def __init__(
        self,
        theme,
        *,
        frame_outer: tuple[int, int, int],
        sep_color: tuple[int, int, int],
        button_tex_normal: str,
        button_tex_hover: str,
        button_tex_pressed: str,
        button_slice_border: int,
    ) -> None:
        self.theme = theme
        self._frame_outer = frame_outer
        self._sep_color = sep_color
        self._button_tex_normal = button_tex_normal
        self._button_tex_hover = button_tex_hover
        self._button_tex_pressed = button_tex_pressed
        self._button_slice_border = int(button_slice_border)
        self._quit_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="Quit",
            font=self.theme.font_small,
        )
        self.quit_rect: pygame.Rect | None = None

    @staticmethod
    def _truncate(font: pygame.font.Font, text: str, max_px: int) -> str:
        s = str(text or "")
        if max_px <= 0 or font.size(s)[0] <= max_px:
            return s
        while s and font.size(s + "...")[0] > max_px:
            s = s[:-1]
        return s + "..."

    @staticmethod
    def _read_snapshots_from_system(system: Any, *getter_names: str) -> tuple[Any, ...]:
        if system is None:
            return ()
        for getter_name in getter_names:
            getter = getattr(system, getter_name, None)
            if not callable(getter):
                continue
            try:
                values = getter()
            except Exception:
                continue
            try:
                return tuple(values or ())
            except TypeError:
                return (values,)
        return ()

    def _active_boss_snapshots(self, game_state: dict) -> tuple[Any, ...]:
        sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        system = getattr(sim, "boss_encounter_system", None)
        return self._read_snapshots_from_system(
            system,
            "get_active_boss_snapshots",
            "get_active_boss_views",
            "get_active_boss_encounters",
        )

    def _active_elite_snapshots(self, game_state: dict) -> tuple[Any, ...]:
        sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        system = getattr(sim, "boss_encounter_system", None)
        return self._read_snapshots_from_system(
            system,
            "get_active_elite_snapshots",
            "get_active_elite_views",
            "get_active_elites",
        )

    @staticmethod
    def _primary_boss_snapshot(bosses: tuple[Any, ...]) -> Any | None:
        if not bosses:
            return None

        def _priority(snapshot: Any) -> tuple[int, float]:
            status = str(getattr(snapshot, "status", "") or "")
            active_rank = 0 if status == "active" else 1
            try:
                hp_pct = float(getattr(snapshot, "hp_pct", 0.0) or 0.0)
            except Exception:
                hp_pct = 1.0
            return active_rank, hp_pct

        return min(bosses, key=_priority)

    @staticmethod
    def _elite_marker_hint(affix_ids: tuple[str, ...]) -> str:
        markers: list[str] = []
        for affix_id in affix_ids:
            try:
                affix = get_elite_affix_def(str(affix_id))
            except Exception:
                continue
            marker = str(
                getattr(affix, "spawn_marker", "") or getattr(affix, "display_name", "") or affix_id
            ).strip()
            if marker and marker not in markers:
                markers.append(marker)
            if len(markers) >= 2:
                break
        return "/".join(markers)

    def _boss_status_lines(self, game_state: dict) -> tuple[tuple[str, pygame.font.Font, tuple[int, int, int]], ...]:
        bosses = self._active_boss_snapshots(game_state)
        elites = self._active_elite_snapshots(game_state)
        if not bosses and not elites:
            return ()

        lines: list[tuple[str, pygame.font.Font, tuple[int, int, int]]] = []
        boss = self._primary_boss_snapshot(bosses)
        if boss is not None:
            boss_name = str(getattr(boss, "name", "") or getattr(boss, "boss_type", "Boss")).strip()
            if len(bosses) > 1:
                boss_name = f"{boss_name} +{len(bosses) - 1}"
            boss_color = (230, 210, 130) if str(getattr(boss, "status", "") or "") == "active" else (190, 190, 200)
            lines.append((boss_name, self.theme.font_body, boss_color))

            phase_title = str(getattr(boss, "current_phase_title", "") or "").strip()
            if not phase_title:
                phase_title = str(getattr(boss, "current_phase", "") or "phase").replace("_", " ").title()
            hp_pct = max(0, min(100, int(round(float(getattr(boss, "hp_pct", 0.0) or 0.0) * 100.0))))
            telegraph = str(getattr(boss, "latest_telegraph", "") or "").strip()
            status = str(getattr(boss, "status", "") or "active").replace("_", " ").title()
            if telegraph:
                detail = f"Phase: {phase_title} | HP: {hp_pct}% | Tell: {telegraph.replace('_', ' ').title()}"
            else:
                detail = f"Phase: {phase_title} | HP: {hp_pct}% | Status: {status}"
            lines.append((detail, self.theme.font_small, (210, 210, 220)))

            if elites:
                elite = elites[0]
                affix_ids = tuple(str(affix_id) for affix_id in getattr(elite, "affixes", ()) or ())
                hint = self._elite_marker_hint(affix_ids)
                elite_count = len(elites)
                if hint:
                    elite_line = f"Elites: {elite_count} | {hint}"
                else:
                    elite_line = f"Elites: {elite_count}"
                lines.append((elite_line, self.theme.font_small, (180, 185, 195)))
        else:
            elite_count = len(elites)
            elite_line = f"Elites: {elite_count}"
            if elites:
                elite = elites[0]
                affix_ids = tuple(str(affix_id) for affix_id in getattr(elite, "affixes", ()) or ())
                hint = self._elite_marker_hint(affix_ids)
                if hint:
                    elite_line = f"Elites: {elite_count} | {hint}"
            lines.append(("Elite Forces", self.theme.font_body, (230, 210, 130)))
            lines.append((elite_line, self.theme.font_small, (180, 185, 195)))

        return tuple(lines)

    def _render_boss_status_panel(self, surface: pygame.Surface, top_rect: pygame.Rect, game_state: dict) -> None:
        lines = self._boss_status_lines(game_state)
        if not lines:
            return

        panel_w = min(360, max(0, surface.get_width() - int(self.theme.margin) * 2))
        if panel_w <= 0:
            return

        title_font = self.theme.font_body
        body_font = self.theme.font_small
        pad_x = 10
        pad_y = 8
        gap = 2
        line_heights = [font.get_height() for _, font, _ in lines]
        panel_h = pad_y * 2 + sum(line_heights) + max(0, len(lines) - 1) * gap
        panel_h = max(panel_h, title_font.get_height() + body_font.get_height() + pad_y * 2)
        panel_x = int(surface.get_width() - panel_w - int(self.theme.margin))
        panel_y = int(top_rect.bottom + 4)
        if panel_x < int(self.theme.margin):
            panel_x = int(self.theme.margin)

        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(surface, self.theme.panel_bg, panel_rect)
        pygame.draw.rect(surface, self._frame_outer, panel_rect, 2)
        inner = panel_rect.inflate(-4, -4)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(surface, self.theme.panel_border, inner, 1)
            pygame.draw.line(
                surface,
                self._sep_color,
                (inner.left + 1, inner.top + 1),
                (inner.right - 2, inner.top + 1),
                1,
            )
            pygame.draw.line(
                surface,
                self._sep_color,
                (inner.left + 1, inner.top + 1),
                (inner.left + 1, inner.bottom - 2),
                1,
            )

        inner_x = panel_rect.x + pad_x
        inner_y = panel_rect.y + pad_y
        inner_w = max(0, panel_rect.width - pad_x * 2)
        for idx, (text, font, color) in enumerate(lines):
            shadow = (20, 20, 24) if idx == 0 else (24, 24, 30)
            TextLabel.render(
                surface,
                font,
                self._truncate(font, text, inner_w),
                (inner_x, inner_y),
                color,
                shadow_color=shadow,
            )
            inner_y += font.get_height() + (gap if idx < len(lines) - 1 else 0)

    def _render_quit_button(self, surface: pygame.Surface, top_rect: pygame.Rect) -> pygame.Rect:
        label_surf = TextLabel.get_surface(self.theme.font_small, "Quit", (240, 240, 240))
        pad_x = 10
        pad_y = 6
        w = int(label_surf.get_width() + pad_x * 2)
        h = int(label_surf.get_height() + pad_y * 2)
        x = int(top_rect.right - w - int(self.theme.margin))
        y = int(top_rect.y + (top_rect.height - h) // 2)
        self._quit_button.rect = pygame.Rect(x, y, w, h)
        self._quit_button.text = "Quit"
        self._quit_button.render(
            surface,
            pygame.mouse.get_pos(),
            texture_normal=self._button_tex_normal,
            texture_hover=self._button_tex_hover,
            texture_pressed=self._button_tex_pressed,
            slice_border=self._button_slice_border,
            bg_normal=(55, 40, 40),
            bg_hover=(70, 45, 45),
            bg_pressed=(75, 55, 55),
            border_outer=(0x14, 0x14, 0x19),
            border_inner=(0x50, 0x50, 0x64),
            border_highlight=(0x6B, 0x6B, 0x84),
            text_shadow_color=(20, 20, 25),
        )
        return pygame.Rect(self._quit_button.rect)

    def render(self, surface: pygame.Surface, top_rect: pygame.Rect, game_state: dict) -> pygame.Rect:
        # Header strip for subtle depth.
        pygame.draw.rect(surface, (30, 30, 40), (top_rect.x, top_rect.y, top_rect.width, 6))

        gold = int(game_state.get("gold", 0) or 0)
        heroes = game_state.get("heroes", [])
        enemies = game_state.get("enemies", [])
        alive_heroes = sum(1 for hero in heroes if getattr(hero, "is_alive", True))
        alive_enemies = sum(1 for enemy in enemies if getattr(enemy, "is_alive", True))
        wave = int(game_state.get("wave", 1) or 1)

        items = [
            (f"Gold: {gold}", COLOR_GOLD),
            (f"Heroes: {alive_heroes}", (230, 230, 230)),
            (f"Enemies: {alive_enemies}", COLOR_RED),
            (f"Wave: {wave}", (230, 230, 230)),
        ]
        x = int(self.theme.margin)
        icon_size = 6
        icon_pad = 6
        item_gap = int(self.theme.gutter) * 2
        text_h = TextLabel.get_surface(self.theme.font_title, "Ag", COLOR_WHITE).get_height()
        y = int((top_rect.height - text_h) // 2)

        for idx, (label, icon_color) in enumerate(items):
            text_font = self.theme.font_title if idx == 0 else self.theme.font_body
            text_surf = TextLabel.get_surface(text_font, label, COLOR_GOLD if idx == 0 else COLOR_WHITE if idx != 2 else COLOR_RED)
            icon_y = int(y + (text_surf.get_height() - icon_size) // 2)
            pygame.draw.rect(surface, icon_color, (x, icon_y, icon_size, icon_size))
            text_x = int(x + icon_size + icon_pad)
            surface.blit(text_surf, (text_x, y + 1))
            x = int(text_x + text_surf.get_width() + item_gap)
            if idx < len(items) - 1:
                sep_x = int(x - (item_gap // 2))
                pygame.draw.line(surface, self._sep_color, (sep_x, top_rect.y + 10), (sep_x, top_rect.bottom - 10), 1)

        pygame.draw.line(surface, self._frame_outer, (top_rect.x, top_rect.bottom - 1), (top_rect.right, top_rect.bottom - 1), 1)
        self.quit_rect = self._render_quit_button(surface, top_rect)
        self._render_boss_status_panel(surface, top_rect, game_state)
        return pygame.Rect(self.quit_rect)
