"""WK135 — Hero inventory window (Agent 08).

Centered modal modeled on ``game/ui/quest_create_panel.py::QuestCreatePanel``
(the newer modal template: ModalPanel backdrop + 9-slice header chrome + close
X + click-outside/ESC dismissal), opened from:

- the "Inventory (I)" button on the selected-hero panel (game/ui/hero_panel.py,
  same pattern as the WK61 Chat button),
- the "Bag" button on the pinned watch card (game/ui/hud_watch_card.py),
- the ``I`` hotkey (game/input/keyboard.py — free since WK114 released the
  zombie build hotkeys G/E/V/Y/O/F/I/R).

This is a VIEW, not a management screen: heroes are autonomous (Majesty-style
indirect control), so there is no drag-drop. The window shows:

- Equipment: three labeled slot boxes (Weapon / Armor / Accessory) with the
  item name + key stats, rarity-colored border/name; empty slots dimmed.
- Backpack: exactly ``hero.backpack_capacity`` slot boxes ("Backpack n/cap"),
  filled boxes rarity-colored with the item name under each, empty boxes drawn
  as dimmed empty squares.
- Consumables: potion flask marker + "Potions n/max".
- Footer hint explaining the auto-equip/sell-spare-loot behavior.

Rarity comes from the item registry (``game/content/items.py``): backpack
entries are ItemDefs (carry ``.rarity``); the legacy equip dicts carry an
``"id"`` looked up in the registry, falling back to a name lookup and finally
to "common".

Determinism note: purely visual — reads hero state, never writes sim state,
draws no RNG, and never runs in the WK67 digest scenario.
"""

from __future__ import annotations

import pygame

from game.ui.theme import UITheme
from game.ui.widgets import ModalPanel, NineSlice

# Rarity -> (name/border color). Standard RPG ramp: common gray-white,
# uncommon green, rare blue, legendary orange.
RARITY_COLORS: dict[str, tuple[int, int, int]] = {
    "common": (200, 200, 205),
    "uncommon": (110, 200, 110),
    "rare": (95, 155, 235),
    "legendary": (235, 150, 60),
}

_EMPTY_BORDER = (90, 90, 105)
_EMPTY_TEXT = (130, 130, 140)
_SLOT_BG = (38, 38, 50)
_SLOT_BG_FILLED = (46, 46, 62)

SLOT_BOX = 52  # equipment/backpack slot box edge (px)


def resolve_rarity(item) -> str:
    """Rarity for an ItemDef OR a legacy equip dict (id -> registry, then name,
    then 'common'). Safe on None/garbage."""
    if item is None:
        return "common"
    r = str(getattr(item, "rarity", "") or "").strip().lower()
    if r in RARITY_COLORS:
        return r
    if isinstance(item, dict):
        from game.content.items import ITEMS, find_by_name

        item_id = str(item.get("id", "") or "")
        found = ITEMS.get(item_id)
        if found is None:
            found = find_by_name(str(item.get("name", "") or ""))
        if found is not None and found.rarity in RARITY_COLORS:
            return found.rarity
    return "common"


def rarity_color(rarity: str) -> tuple[int, int, int]:
    return RARITY_COLORS.get(str(rarity or "").strip().lower(), RARITY_COLORS["common"])


def item_stats_text(item) -> str:
    """Short key-stat summary, e.g. '+10 ATK' / '+7 DEF' / '+2 ATK, +2 DEF'.

    Works for ItemDefs and the legacy equip dicts (which carry the same keys).
    """
    if item is None:
        return ""

    def _get(key, default=0):
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    parts: list[str] = []
    atk = int(_get("attack", 0) or 0)
    dfs = int(_get("defense", 0) or 0)
    spd = float(_get("speed", 0.0) or 0.0)
    mhp = int(_get("max_hp", 0) or 0)
    eff = int(_get("effect", 0) or 0)
    if atk:
        parts.append(f"+{atk} ATK")
    if dfs:
        parts.append(f"+{dfs} DEF")
    if spd:
        parts.append(f"+{spd:g} SPD")
    if mhp:
        parts.append(f"+{mhp} HP")
    if eff:
        parts.append(f"Heals {eff}")
    return ", ".join(parts)


def item_name(item) -> str:
    if item is None:
        return ""
    if isinstance(item, dict):
        return str(item.get("name", "") or "")
    return str(getattr(item, "name", item) or "")


class InventoryPanel:
    """Centered modal showing the selected hero's equipment + backpack."""

    def __init__(self, screen_width: int, screen_height: int):
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self.visible = False
        self.theme = UITheme()
        self.font_tiny = pygame.font.Font(None, 16)
        self._panel_tex_modal = "assets/ui/kingdomsim_ui_cc0/panels/panel_modal.png"
        self._button_tex_normal = "assets/ui/kingdomsim_ui_cc0/buttons/button_normal.png"
        self._button_tex_hover = "assets/ui/kingdomsim_ui_cc0/buttons/button_hover.png"
        self._button_slice_border = 6

        self.modal = ModalPanel(
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            panel_width=560,
            panel_height=412,
            texture_path=self._panel_tex_modal,
            slice_border=8,
        )

        self.hero = None
        self.close_rect: pygame.Rect | None = None
        self._mouse_pos: tuple[int, int] = (0, 0)

    # ------------------------------------------------------------------
    # Open / close / resize
    # ------------------------------------------------------------------
    def open(self, hero) -> None:
        self.hero = hero
        self.visible = True

    def close(self) -> None:
        self.visible = False
        self.hero = None

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
        self.modal.panel_height = max(380, min(412, self.screen_height - 60))
        self.modal.panel_width = max(420, min(560, self.screen_width - 40))

    # ------------------------------------------------------------------
    # Click handling (modal: consumes every click while visible)
    # ------------------------------------------------------------------
    def handle_click(self, pos: tuple[int, int]) -> bool:
        """Handle a click while visible. Always returns True (modal consumes)."""
        if not self.visible:
            return False
        panel_rect = self.modal.get_panel_rect()
        if self.close_rect is not None and self.close_rect.collidepoint(pos):
            self.close()
            return True
        if not panel_rect.collidepoint(pos):
            # Click outside the modal closes (mirrors the quest-create dialog).
            self.close()
            return True
        return True

    def update_hover(self, pos: tuple[int, int]) -> None:
        self._mouse_pos = (int(pos[0]), int(pos[1]))

    # ------------------------------------------------------------------
    # Hero state readers (legacy dicts + ItemDefs, all attrs optional)
    # ------------------------------------------------------------------
    def _equip_slots(self) -> list[tuple[str, object]]:
        h = self.hero
        return [
            ("Weapon", getattr(h, "weapon", None) if h is not None else None),
            ("Armor", getattr(h, "armor", None) if h is not None else None),
            ("Accessory", getattr(h, "accessory", None) if h is not None else None),
        ]

    def _backpack(self) -> tuple[list[object], int]:
        h = self.hero
        items = list(getattr(h, "backpack", None) or ()) if h is not None else []
        cap = int(getattr(h, "backpack_capacity", 5) or 5) if h is not None else 5
        cap = max(1, cap)
        return items[:cap], cap

    def _potions(self) -> tuple[int, int]:
        h = self.hero
        n = int(getattr(h, "potions", 0) or 0) if h is not None else 0
        mx = int(getattr(h, "max_potions", 5) or 5) if h is not None else 5
        return n, max(1, mx)

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------
    def _fit_line(self, font: pygame.font.Font, text: str, max_w: int) -> str:
        s = str(text or "")
        if max_w <= 0 or font.size(s)[0] <= max_w:
            return s
        while len(s) > 1 and font.size(s + "…")[0] > max_w:
            s = s[:-1]
        return s.rstrip() + "…"

    def _draw_slot_box(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        item,
        *,
        empty_label: str = "Empty",
    ) -> None:
        """Bordered square: rarity-colored 2px border when filled, dimmed when empty."""
        filled = item is not None
        pygame.draw.rect(surface, _SLOT_BG_FILLED if filled else _SLOT_BG, rect)
        if filled:
            border = rarity_color(resolve_rarity(item))
            pygame.draw.rect(surface, border, rect, 2)
            # Inner shading for a subtle inset look.
            pygame.draw.rect(surface, (25, 25, 34), rect.inflate(-4, -4), 1)
            # Item initials marker in the box center (no item icons exist yet).
            initials = "".join(w[0] for w in item_name(item).split()[:2]).upper()
            if initials:
                mark = self.theme.font_body.render(initials, True, border)
                surface.blit(
                    mark,
                    (rect.centerx - mark.get_width() // 2, rect.centery - mark.get_height() // 2),
                )
        else:
            pygame.draw.rect(surface, _EMPTY_BORDER, rect, 1)
            lbl = self.font_tiny.render(empty_label, True, _EMPTY_TEXT)
            if lbl.get_width() <= rect.width - 4:
                surface.blit(
                    lbl,
                    (rect.centerx - lbl.get_width() // 2, rect.centery - lbl.get_height() // 2),
                )

    def _render_section_label(self, surface: pygame.Surface, x: int, y: int, text: str) -> int:
        lbl = self.theme.font_body.render(text, True, (210, 210, 225))
        surface.blit(lbl, (x, y))
        return y + lbl.get_height() + 6

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def render(self, surface: pygame.Surface, cursor_pos: tuple[int, int] | None = None) -> None:
        if not self.visible:
            return
        if cursor_pos is not None:
            self.update_hover(cursor_pos)
        self._ensure_screen_size(surface)

        self.modal.render_backdrop(surface)
        self.modal.render_panel(surface)
        panel_rect = self.modal.get_panel_rect()
        pad = 14

        # Header (mirrors the quest-create modal header chrome).
        hero_name = str(getattr(self.hero, "name", "Hero") or "Hero")
        title_text = self._fit_line(self.theme.font_title, f"{hero_name} — Inventory", panel_rect.width - 70)
        header_rect = pygame.Rect(panel_rect.x + 8, panel_rect.y + 8, panel_rect.width - 16, 40)
        if not NineSlice.render(surface, header_rect, self._button_tex_normal, border=self._button_slice_border):
            pygame.draw.rect(surface, (45, 45, 60), header_rect)
            pygame.draw.rect(surface, self.theme.panel_border, header_rect, 1)
        title = self.theme.font_title.render(title_text, True, self.theme.text)
        shadow = self.theme.font_title.render(title_text, True, (20, 20, 30))
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
        y = header_rect.bottom + 12

        # ── Equipment: three labeled slot boxes ──────────────────────────
        y = self._render_section_label(surface, x, y, "Equipment")
        col_w = inner_w // 3
        text_h = self.theme.font_small.get_height()
        for i, (slot_label, item) in enumerate(self._equip_slots()):
            cx0 = x + i * col_w
            lbl = self.theme.font_small.render(slot_label, True, (170, 175, 195))
            surface.blit(lbl, (cx0, y))
            box = pygame.Rect(cx0, y + text_h + 4, SLOT_BOX, SLOT_BOX)
            self._draw_slot_box(surface, box, item)
            # Name + key stats beside the box.
            tx = box.right + 8
            tw = max(0, cx0 + col_w - 8 - tx)
            if item is not None:
                name_col = rarity_color(resolve_rarity(item))
                name = self.theme.font_small.render(
                    self._fit_line(self.theme.font_small, item_name(item), tw), True, name_col
                )
                surface.blit(name, (tx, box.y + 6))
                stats = item_stats_text(item)
                if stats:
                    st = self.font_tiny.render(self._fit_line(self.font_tiny, stats, tw), True, (215, 215, 225))
                    surface.blit(st, (tx, box.y + 6 + name.get_height() + 3))
            else:
                none_lbl = self.font_tiny.render("None", True, _EMPTY_TEXT)
                surface.blit(none_lbl, (tx, box.y + 6))
        y += text_h + 4 + SLOT_BOX + 14

        # ── Backpack: capacity slot boxes ────────────────────────────────
        bag_items, cap = self._backpack()
        y = self._render_section_label(surface, x, y, f"Backpack {len(bag_items)}/{cap}")
        gap = 10
        # Keep cap boxes on one row inside inner_w (cap is 5 by design; clamp anyway).
        box_w = min(SLOT_BOX, max(34, (inner_w - gap * (cap - 1)) // cap))
        name_h = self.font_tiny.get_height()
        for i in range(cap):
            item = bag_items[i] if i < len(bag_items) else None
            box = pygame.Rect(x + i * (box_w + gap), y, box_w, SLOT_BOX)
            self._draw_slot_box(surface, box, item, empty_label="—")
            if item is not None:
                name_col = rarity_color(resolve_rarity(item))
                nm = self.font_tiny.render(
                    self._fit_line(self.font_tiny, item_name(item), box_w + gap - 4), True, name_col
                )
                surface.blit(nm, (box.x, box.bottom + 3))
        y += SLOT_BOX + name_h + 12

        # ── Consumables row ──────────────────────────────────────────────
        y = self._render_section_label(surface, x, y, "Consumables")
        n_pot, max_pot = self._potions()
        # Small potion-flask marker (red body + neck) — readable without art assets.
        flask = pygame.Rect(x + 2, y + 2, 12, 16)
        pygame.draw.rect(surface, (120, 50, 55), pygame.Rect(flask.x + 4, flask.y - 2, 4, 4))
        pygame.draw.ellipse(surface, (205, 70, 80) if n_pot > 0 else (95, 60, 65), flask)
        pygame.draw.ellipse(surface, (60, 25, 30), flask, 1)
        pot_lbl = self.theme.font_small.render(f"Potions {n_pot}/{max_pot}", True,
                                               (120, 220, 130) if n_pot > 0 else _EMPTY_TEXT)
        surface.blit(pot_lbl, (flask.right + 8, y + 2))
        y += 24 + 10

        # ── Footer hint (how items work — view-only window) ──────────────
        line_y = panel_rect.bottom - pad - self.font_tiny.get_height() * 2 - 6
        pygame.draw.line(surface, (70, 70, 90), (x, line_y - 6), (x + inner_w, line_y - 6), 1)
        hint1 = self.font_tiny.render(
            self._fit_line(self.font_tiny, "Heroes auto-equip upgrades and sell spare loot at shops.", inner_w),
            True, (185, 190, 205),
        )
        hint2 = self.font_tiny.render(
            self._fit_line(self.font_tiny, "View only — heroes manage their own gear.  I / ESC closes.", inner_w),
            True, (150, 150, 165),
        )
        surface.blit(hint1, (x, line_y))
        surface.blit(hint2, (x, line_y + self.font_tiny.get_height() + 3))
