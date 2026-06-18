"""WK126-T9 — Quest-creation modal for the Herald's Post (Agent 08).

Centered modal modeled on ``game/ui/build_catalog_panel.py::BuildCatalogPanel``.
Opened from the selected Herald's Post building card ("Create Quest" button in
``game/ui/building_panel.py``, the selection-wiring file). Flow:

    (1) pick quest type   — 4 buttons (raid_lair | slay_enemy_type | find_poi | explore_far)
    (2) pick target       — raid: list of DISCOVERED lairs (name + distance);
                            slay: enemy-type list + count stepper (default 5);
                            find_poi: list of discovered POIs;
                            explore: 4 compass presets toward far map edges
    (3) pick reward tier  — Low/Med/High (QUEST_REWARD_*) with cost shown and
                            affordability checked vs economy.player_gold
                            (insufficient-gold feedback like the build menu)

Confirm calls THE engine action ``SimEngine.create_quest(giver_id, quest_type,
target, reward, count=...)`` (escrow via economy.fund_quest; returns None when
unaffordable). Cancel / X / click-outside / ESC (game/input/keyboard.py) closes.

The modal also embeds the WK126 active-quest board
(``QuestViewPanel.render_active_quests``) so the player can read open/accepted
quest status from the same surface (the wk14 ViewMode.QUEST right-column path
is dormant since the WK130 sidebar overhaul removed the right column).

Determinism note: this panel is player-facing UI; the only sim mutation is the
explicit player action ``sim.create_quest`` on Confirm (mirrors place_bounty).
It draws no RNG and never runs in the WK67 digest scenario.
"""

from __future__ import annotations

import pygame

from config import (
    COLOR_GREEN,
    COLOR_RED,
    MAP_HEIGHT,
    MAP_WIDTH,
    QUEST_REWARD_HIGH,
    QUEST_REWARD_LOW,
    QUEST_REWARD_MED,
    QUEST_SLAY_DEFAULT_COUNT,
    TILE_SIZE,
)
from game.ui.theme import UITheme
from game.ui.widgets import ModalPanel, NineSlice

# The four in-scope quest types (Wave-1 contract vocabulary).
QUEST_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    ("raid_lair", "Raid Lair"),
    ("slay_enemy_type", "Slay Enemies"),
    ("find_poi", "Find POI"),
    ("explore_far", "Explore Far"),
)

# Reward tiers (key, label, gold) — gold from the Wave-1 config contract.
REWARD_TIER_CHOICES: tuple[tuple[str, str, int], ...] = (
    ("low", "Low", int(QUEST_REWARD_LOW)),
    ("med", "Med", int(QUEST_REWARD_MED)),
    ("high", "High", int(QUEST_REWARD_HIGH)),
)

# Huntable enemy types for slay_enemy_type (the regular spawn roster; bosses are
# lair/POI-bound one-offs and not a sane "slay N" target).
SLAY_ENEMY_TYPES: tuple[str, ...] = ("goblin", "wolf", "skeleton", "spider", "bandit")

STORY_CHAIN_CHOICES: tuple[tuple[str, str], ...] = (
    ("relic_of_the_old_shrine", "Relic"),
    ("blackbanners_toll", "Blackbanner"),
    ("ashwings_hoard", "Ashwing"),
)

_MAX_TARGET_ROWS = 6
_MAX_SLAY_COUNT = 25


def _title(s: str) -> str:
    return str(s or "").replace("_", " ").title()


class QuestCreatePanel:
    """Centered modal for creating a quest on a selected Herald's Post."""

    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.visible = False
        self.theme = UITheme()
        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_slice_border = 6

        self.modal = ModalPanel(
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            panel_width=560,
            panel_height=620,
            texture_path=self._panel_tex_modal,
            slice_border=8,
        )

        # Open-time state (cleared on close).
        self.post = None            # the selected Herald's Post Building
        self._sim = None            # game_state["sim"] (SimEngine — has create_quest)
        self._world = None          # for discovered-tile checks + explore presets

        # Selection state.
        self.selected_type: str | None = None
        self.target_index: int | None = None
        self.slay_count: int = int(QUEST_SLAY_DEFAULT_COUNT)
        self.reward_key: str = "low"
        self.feedback: str = ""

        # Screen-space hit rects (stored during render, tested in handle_click).
        self.close_rect: pygame.Rect | None = None
        self.type_rects: dict[str, pygame.Rect] = {}
        self.target_rects: list[pygame.Rect] = []
        self.count_minus_rect: pygame.Rect | None = None
        self.count_plus_rect: pygame.Rect | None = None
        self.reward_rects: dict[str, pygame.Rect] = {}
        self.story_chain_rects: dict[str, pygame.Rect] = {}
        self.confirm_rect: pygame.Rect | None = None
        self.cancel_rect: pygame.Rect | None = None

        self._mouse_pos: tuple[int, int] = (0, 0)
        # Lazy active-quest board (QuestViewPanel) — shared readout renderer.
        self._board = None

    # ------------------------------------------------------------------
    # Open / close / resize
    # ------------------------------------------------------------------
    def open(self, post, game_state: dict) -> None:
        """Open for the given Herald's Post. ``game_state`` provides sim/world."""
        self.post = post
        self._sim = game_state.get("sim") or getattr(game_state.get("engine"), "sim", None)
        self._world = game_state.get("world") or getattr(self._sim, "world", None)
        self.selected_type = None
        self.target_index = None
        self.slay_count = int(QUEST_SLAY_DEFAULT_COUNT)
        self.reward_key = "low"
        self.feedback = ""
        self.visible = True

    def close(self) -> None:
        self.visible = False
        self.post = None
        self._sim = None
        self._world = None
        self.feedback = ""

    def on_resize(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.modal.screen_width = self.screen_width
        self.modal.screen_height = self.screen_height
        self.modal._backdrop_cache = None

    def _ensure_screen_size(self, surface: pygame.Surface) -> None:
        w, h = surface.get_size()
        if (w, h) != (self.screen_width, self.screen_height):
            self.on_resize(w, h)
        # Keep the modal inside short windows (never hardcode 1080p).
        self.modal.panel_height = max(420, min(620, self.screen_height - 90))
        self.modal.panel_width = max(420, min(560, self.screen_width - 40))

    # ------------------------------------------------------------------
    # Target candidates
    # ------------------------------------------------------------------
    def _tile_explored(self, gx: int, gy: int) -> bool:
        """True iff the tile has been revealed (SEEN or better). Missing fog data
        reads as explored so captures/tests without fog never blank the lists."""
        world = self._world
        vis = getattr(world, "visibility", None)
        if not vis:
            return True
        if gy < 0 or gy >= len(vis) or gx < 0 or gx >= len(vis[gy]):
            return False
        return vis[gy][gx] >= 1  # Visibility.SEEN

    def _building_tile(self, b) -> tuple[int, int]:
        gx = int(getattr(b, "grid_x", 0))
        gy = int(getattr(b, "grid_y", 0))
        size = getattr(b, "size", (1, 1)) or (1, 1)
        try:
            return gx + int(size[0]) // 2, gy + int(size[1]) // 2
        except Exception:
            return gx, gy

    def _distance_tiles(self, x: float, y: float) -> int:
        px = float(getattr(self.post, "center_x", getattr(self.post, "x", 0.0)))
        py = float(getattr(self.post, "center_y", getattr(self.post, "y", 0.0)))
        d = ((float(x) - px) ** 2 + (float(y) - py) ** 2) ** 0.5
        return int(round(d / float(TILE_SIZE)))

    def _explore_presets(self) -> list[tuple[tuple[int, int], str]]:
        """4 compass presets toward far map edges (simple, list-pickable)."""
        world = self._world
        w = int(getattr(world, "width", MAP_WIDTH) or MAP_WIDTH)
        h = int(getattr(world, "height", MAP_HEIGHT) or MAP_HEIGHT)
        if self.post is not None:
            pgx, pgy = self._building_tile(self.post)
        else:
            pgx, pgy = w // 2, h // 2
        near = max(2, int(round(min(w, h) * 0.08)))
        presets = [
            ((pgx, near), "North"),
            ((min(w - 3, w - near), pgy), "East"),
            ((pgx, min(h - 3, h - near)), "South"),
            ((near, pgy), "West"),
        ]
        out: list[tuple[tuple[int, int], str]] = []
        for (tx, ty), name in presets:
            tx = max(2, min(w - 3, int(tx)))
            ty = max(2, min(h - 3, int(ty)))
            charted = self._tile_explored(tx, ty)
            tag = "charted" if charted else "unexplored"
            out.append(((tx, ty), f"{name} — tile ({tx},{ty}) [{tag}]"))
        return out

    def _target_candidates(self) -> list[tuple[object, str]]:
        """(target_value, row_label) pairs for the current quest type."""
        qtype = self.selected_type
        if qtype is None or self.post is None:
            return []
        if qtype == "raid_lair":
            out = []
            for b in list(getattr(self._sim, "buildings", []) or []):
                if not getattr(b, "is_lair", False):
                    continue
                if int(getattr(b, "hp", 0)) <= 0:
                    continue
                gx, gy = self._building_tile(b)
                if not self._tile_explored(gx, gy):
                    continue
                name = _title(getattr(b, "building_type", "lair"))
                dist = self._distance_tiles(
                    getattr(b, "center_x", getattr(b, "x", 0.0)),
                    getattr(b, "center_y", getattr(b, "y", 0.0)),
                )
                out.append((b, f"{name} — {dist} tiles"))
            return out[:_MAX_TARGET_ROWS]
        if qtype == "slay_enemy_type":
            return [(et, _title(et)) for et in SLAY_ENEMY_TYPES]
        if qtype == "find_poi":
            out = []
            for poi in list(getattr(self._sim, "pois", []) or []):
                if not getattr(poi, "is_discovered", False):
                    continue
                if getattr(poi, "is_depleted", False):
                    continue
                pd = getattr(poi, "poi_def", None)
                name = str(getattr(pd, "display_name", "") or _title(getattr(poi, "building_type", "POI")))
                dist = self._distance_tiles(
                    getattr(poi, "center_x", getattr(poi, "x", 0.0)),
                    getattr(poi, "center_y", getattr(poi, "y", 0.0)),
                )
                out.append((poi, f"{name} — {dist} tiles"))
            return out[:_MAX_TARGET_ROWS]
        if qtype == "explore_far":
            return list(self._explore_presets())
        return []

    def _no_target_message(self) -> str:
        return {
            "raid_lair": "No discovered lairs yet — explore the map first.",
            "find_poi": "No discovered points of interest yet.",
        }.get(self.selected_type or "", "Nothing to target.")

    def _reward_amount(self) -> int:
        for key, _label, gold in REWARD_TIER_CHOICES:
            if key == self.reward_key:
                return int(gold)
        return int(QUEST_REWARD_LOW)

    def _can_confirm(self, economy) -> bool:
        if self.selected_type is None or self.target_index is None:
            return False
        if self.target_index >= len(self._target_candidates()):
            return False
        gold = int(getattr(economy, "player_gold", 0)) if economy is not None else 0
        return gold >= self._reward_amount()

    # ------------------------------------------------------------------
    # Click handling (modal: consumes every click while visible)
    # ------------------------------------------------------------------
    def handle_click(self, pos: tuple[int, int], economy=None) -> bool:
        """Handle a click while visible. Always returns True (modal consumes)."""
        if not self.visible:
            return False

        panel_rect = self.modal.get_panel_rect()
        if self.close_rect is not None and self.close_rect.collidepoint(pos):
            self.close()
            return True
        if not panel_rect.collidepoint(pos):
            # Click outside the modal cancels (mirrors the build catalog).
            self.close()
            return True

        for key, rect in self.type_rects.items():
            if rect.collidepoint(pos):
                if key != self.selected_type:
                    self.selected_type = key
                    self.target_index = None
                    self.feedback = ""
                return True

        for key, rect in self.story_chain_rects.items():
            if rect.collidepoint(pos):
                self._confirm_story_chain(key)
                return True

        for i, rect in enumerate(self.target_rects):
            if rect.collidepoint(pos):
                self.target_index = i
                self.feedback = ""
                return True

        if self.count_minus_rect is not None and self.count_minus_rect.collidepoint(pos):
            self.slay_count = max(1, int(self.slay_count) - 1)
            return True
        if self.count_plus_rect is not None and self.count_plus_rect.collidepoint(pos):
            self.slay_count = min(_MAX_SLAY_COUNT, int(self.slay_count) + 1)
            return True

        for key, rect in self.reward_rects.items():
            if rect.collidepoint(pos):
                gold = int(getattr(economy, "player_gold", 0)) if economy is not None else 0
                cost = next(g for k, _l, g in REWARD_TIER_CHOICES if k == key)
                if gold < cost:
                    # Insufficient-gold feedback, like the build menu.
                    self.feedback = f"Need ${cost} (have ${gold})"
                else:
                    self.reward_key = key
                    self.feedback = ""
                return True

        if self.cancel_rect is not None and self.cancel_rect.collidepoint(pos):
            self.close()
            return True
        if self.confirm_rect is not None and self.confirm_rect.collidepoint(pos):
            self._confirm(economy)
            return True
        return True

    def update_hover(self, pos: tuple[int, int]) -> None:
        self._mouse_pos = (int(pos[0]), int(pos[1]))

    def _confirm(self, economy) -> None:
        if self.selected_type is None:
            self.feedback = "Pick a quest type."
            return
        candidates = self._target_candidates()
        if self.target_index is None or self.target_index >= len(candidates):
            self.feedback = "Pick a target."
            return
        reward = self._reward_amount()
        gold = int(getattr(economy, "player_gold", 0)) if economy is not None else 0
        if gold < reward:
            self.feedback = f"Need ${reward} (have ${gold})"
            return
        sim = self._sim
        create = getattr(sim, "create_quest", None)
        if not callable(create) or self.post is None:
            self.feedback = "Quest system unavailable."
            return
        target = candidates[self.target_index][0]
        count = int(self.slay_count) if self.selected_type == "slay_enemy_type" else 1
        giver_id = getattr(self.post, "entity_id", None)
        quest = create(giver_id, self.selected_type, target, reward, count=count)
        if quest is None:
            # economy.fund_quest said no (race with other spending).
            self.feedback = f"Need ${reward} (have ${gold})"
            return
        self.close()

    def _live_story_chain(self, chain_type: str):
        system = getattr(self._sim, "quest_chain_system", None)
        if system is None:
            return None
        for chain in list(getattr(system, "chains", []) or []):
            if (
                str(getattr(chain, "chain_type", "") or "") == str(chain_type)
                and str(getattr(chain, "status", "") or "") in {"offered", "active"}
            ):
                return chain
        return None

    def _story_chain_label(self, chain_type: str, label: str) -> str:
        return f"{label} Active" if self._live_story_chain(chain_type) is not None else label

    def _confirm_story_chain(self, chain_type: str) -> None:
        if self._live_story_chain(chain_type) is not None:
            self.feedback = "Already active."
            return
        sim = self._sim
        if sim is None or self.post is None:
            self.feedback = "Quest system unavailable."
            return
        launch = getattr(sim, "start_quest_chain_from_post", None)
        if not callable(launch):
            launch = getattr(sim, "create_quest_chain", None)
        if not callable(launch):
            self.feedback = "Quest system unavailable."
            return
        giver_id = getattr(self.post, "entity_id", None)
        chain = launch(giver_id, chain_type)
        if chain is None:
            self.feedback = "Story chain unavailable."
            return
        if str(getattr(chain, "chain_type", "") or "") != str(chain_type):
            self.feedback = "Story chain unavailable."
            return
        if str(getattr(chain, "status", "") or "") not in {"offered", "active"}:
            self.feedback = "Story chain unavailable."
            return
        label = next((name for key, name in STORY_CHAIN_CHOICES if key == chain_type), "Story")
        self.feedback = f"{label} started."

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _render_pill(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        *,
        selected: bool,
        enabled: bool = True,
        cost_text: str | None = None,
        cost_ok: bool = True,
    ) -> None:
        hovered = enabled and rect.collidepoint(self._mouse_pos)
        if not enabled:
            # Flat dark disabled style — the tan 9-slice texture has too little
            # contrast for disabled text (WK133 screenshot review).
            pygame.draw.rect(surface, (52, 48, 50), rect)
        else:
            tex = self._button_tex_hover if (hovered or selected) else self._button_tex_normal
            if not NineSlice.render(surface, rect, tex, border=self._button_slice_border):
                bg = (70, 80, 100) if (hovered or selected) else (50, 50, 65)
                pygame.draw.rect(surface, bg, rect)
        border = (220, 190, 90) if selected else ((120, 130, 160) if hovered else self.theme.panel_border)
        pygame.draw.rect(surface, border, rect, 2 if selected else 1)
        color = self.theme.text if enabled else (150, 145, 150)
        label = self.theme.font_small.render(text, True, color)
        ly = rect.y + (rect.height - label.get_height()) // 2
        if cost_text is None:
            surface.blit(label, (rect.centerx - label.get_width() // 2, ly))
        else:
            cost = self.theme.font_small.render(cost_text, True, COLOR_GREEN if cost_ok else COLOR_RED)
            total_w = label.get_width() + 6 + cost.get_width()
            x0 = rect.centerx - total_w // 2
            surface.blit(label, (x0, ly))
            surface.blit(cost, (x0 + label.get_width() + 6, ly))

    def _render_section_label(self, surface: pygame.Surface, x: int, y: int, text: str) -> int:
        lbl = self.theme.font_body.render(text, True, (210, 210, 225))
        surface.blit(lbl, (x, y))
        return y + lbl.get_height() + 4

    def render(self, surface: pygame.Surface, economy=None) -> None:
        if not self.visible:
            return
        self._ensure_screen_size(surface)

        self.modal.render_backdrop(surface)
        self.modal.render_panel(surface)
        panel_rect = self.modal.get_panel_rect()
        pad = 14

        # Header (mirrors the build catalog header chrome).
        header_rect = pygame.Rect(panel_rect.x + 8, panel_rect.y + 8, panel_rect.width - 16, 40)
        if not NineSlice.render(surface, header_rect, self._button_tex_normal, border=self._button_slice_border):
            pygame.draw.rect(surface, (45, 45, 60), header_rect)
            pygame.draw.rect(surface, self.theme.panel_border, header_rect, 1)
        title = self.theme.font_title.render("Create Quest", True, self.theme.text)
        shadow = self.theme.font_title.render("Create Quest", True, (20, 20, 30))
        ty = header_rect.y + (header_rect.height - title.get_height()) // 2
        surface.blit(shadow, (header_rect.x + 13, ty + 1))
        surface.blit(title, (header_rect.x + 12, ty))

        # Close X.
        close_rect = pygame.Rect(header_rect.right - 28, header_rect.y + (header_rect.height - 20) // 2, 20, 20)
        hov_close = close_rect.collidepoint(self._mouse_pos)
        if not NineSlice.render(
            surface, close_rect,
            self._button_tex_hover if hov_close else self._button_tex_normal,
            border=self._button_slice_border,
        ):
            pygame.draw.rect(surface, (70, 70, 80) if hov_close else (50, 50, 60), close_rect)
            pygame.draw.rect(surface, self.theme.panel_border, close_rect, 1)
        x_surf = self.theme.font_small.render("X", True, self.theme.text)
        surface.blit(x_surf, (close_rect.centerx - x_surf.get_width() // 2, close_rect.centery - x_surf.get_height() // 2))
        self.close_rect = pygame.Rect(close_rect)

        x = panel_rect.x + pad
        inner_w = panel_rect.width - pad * 2
        y = header_rect.bottom + 10

        # ── 1. Quest type ────────────────────────────────────────────────
        y = self._render_section_label(surface, x, y, "1. Quest type")
        self.type_rects = {}
        gap = 6
        bw = (inner_w - gap * (len(QUEST_TYPE_CHOICES) - 1)) // len(QUEST_TYPE_CHOICES)
        for i, (key, label) in enumerate(QUEST_TYPE_CHOICES):
            rect = pygame.Rect(x + i * (bw + gap), y, bw, 30)
            self._render_pill(surface, rect, label, selected=(key == self.selected_type))
            self.type_rects[key] = rect
        y += 30 + 10

        # ── 2. Target ────────────────────────────────────────────────────
        y = self._render_section_label(surface, x, y, "2. Target")
        self.target_rects = []
        self.count_minus_rect = None
        self.count_plus_rect = None
        target_area_h = _MAX_TARGET_ROWS * 28
        if self.selected_type is None:
            hint = self.theme.font_small.render("Choose a quest type above.", True, (150, 150, 160))
            surface.blit(hint, (x + 4, y + 4))
        else:
            candidates = self._target_candidates()
            if not candidates:
                msg = self.theme.font_small.render(self._no_target_message(), True, (200, 150, 150))
                surface.blit(msg, (x + 4, y + 4))
            else:
                row_w = inner_w if self.selected_type != "slay_enemy_type" else int(inner_w * 0.62)
                ry = y
                for i, (_value, label) in enumerate(candidates):
                    rect = pygame.Rect(x, ry, row_w, 24)
                    self._render_pill(surface, rect, label, selected=(i == self.target_index))
                    self.target_rects.append(rect)
                    ry += 28
                if self.selected_type == "slay_enemy_type":
                    # Count stepper to the right of the enemy list.
                    sx = x + row_w + 12
                    sy = y + 2
                    clabel = self.theme.font_small.render("Count", True, (210, 210, 225))
                    surface.blit(clabel, (sx, sy))
                    sy += clabel.get_height() + 6
                    minus = pygame.Rect(sx, sy, 26, 26)
                    value_rect = pygame.Rect(minus.right + 6, sy, 40, 26)
                    plus = pygame.Rect(value_rect.right + 6, sy, 26, 26)
                    self._render_pill(surface, minus, "-", selected=False)
                    pygame.draw.rect(surface, (35, 38, 45), value_rect)
                    pygame.draw.rect(surface, self.theme.panel_border, value_rect, 1)
                    v = self.theme.font_body.render(str(int(self.slay_count)), True, self.theme.text)
                    surface.blit(v, (value_rect.centerx - v.get_width() // 2, value_rect.centery - v.get_height() // 2))
                    self._render_pill(surface, plus, "+", selected=False)
                    self.count_minus_rect = pygame.Rect(minus)
                    self.count_plus_rect = pygame.Rect(plus)
        y += target_area_h + 8

        # ── 3. Reward ────────────────────────────────────────────────────
        y = self._render_section_label(surface, x, y, "3. Reward (escrowed from treasury)")
        self.reward_rects = {}
        gold = int(getattr(economy, "player_gold", 0)) if economy is not None else 0
        bw = (inner_w - gap * (len(REWARD_TIER_CHOICES) - 1)) // len(REWARD_TIER_CHOICES)
        for i, (key, label, cost) in enumerate(REWARD_TIER_CHOICES):
            rect = pygame.Rect(x + i * (bw + gap), y, bw, 30)
            affordable = gold >= int(cost)
            self._render_pill(
                surface, rect, label,
                selected=(key == self.reward_key),
                enabled=affordable,
                cost_text=f"${int(cost)}",
                cost_ok=affordable,
            )
            self.reward_rects[key] = rect
        y += 30 + 6

        # Story Chains: playtest launcher for existing multi-phase quest chains.
        y = self._render_section_label(surface, x, y, "Story Chains")
        self.story_chain_rects = {}
        bw = (inner_w - gap * (len(STORY_CHAIN_CHOICES) - 1)) // len(STORY_CHAIN_CHOICES)
        for i, (key, label) in enumerate(STORY_CHAIN_CHOICES):
            rect = pygame.Rect(x + i * (bw + gap), y, bw, 28)
            active = self._live_story_chain(key) is not None
            self._render_pill(
                surface,
                rect,
                self._story_chain_label(key, label),
                selected=active,
            )
            self.story_chain_rects[key] = rect
        y += 28 + 6

        # Feedback line (insufficient gold etc).
        if self.feedback:
            fb = self.theme.font_small.render(self.feedback, True, (230, 120, 120))
            surface.blit(fb, (x, y))
        y += 20

        # ── Active-quest board (WK126 readout, shared with QuestViewPanel) ──
        board_bottom = panel_rect.bottom - pad - 36 - 8
        board_rect = pygame.Rect(x, y, inner_w, max(0, board_bottom - y))
        if board_rect.height >= 40:
            if self._board is None:
                from game.ui.quest_view_panel import QuestViewPanel

                self._board = QuestViewPanel(self.theme)
            self._board.render_active_quests(surface, board_rect, {"sim": self._sim})

        # ── Bottom buttons: Cancel | Create Quest ────────────────────────
        btn_h = 32
        by = panel_rect.bottom - pad - btn_h
        cancel = pygame.Rect(x, by, 120, btn_h)
        confirm = pygame.Rect(panel_rect.right - pad - 180, by, 180, btn_h)
        can_confirm = self._can_confirm(economy)
        self._render_pill(surface, cancel, "Cancel", selected=False)
        self._render_pill(
            surface, confirm,
            f"Create Quest  (${self._reward_amount()})",
            selected=False,
            enabled=can_confirm,
        )
        self.cancel_rect = pygame.Rect(cancel)
        self.confirm_rect = pygame.Rect(confirm)
