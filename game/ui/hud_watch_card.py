"""Pinned-hero watch-card renderer for the HUD (WK96 slice of hud.py).

Extracted VERBATIM from game/ui/hud.py (WK96 Round B-13): the pinned-hero
watch-card render cluster — ``render_hero_watch_card_infocard`` (the WK52 card
above the minimap: header, optional map slot + HP/XP/Lvl stats rows + bars +
Chat button + chat band), ``render_card_slot`` (resets the per-frame watch-card
rects then renders the hero card when a hero is pinned) and
``render_watch_card_chrome`` (the render() entry point). This module also OWNS
the ``WATCH_CARD_*`` layout constants (they live here because the renderer reads
``WATCH_CARD_HEADER_H``; hud.py re-imports + re-exports them so
``from game.ui.hud import WATCH_CARD_*`` keeps resolving for tests and the layout
helpers that STAY on HUD). All watch-card STATE (``_pin_slot``, ``_info_card``,
``_chat_panel``, the ``_watch_*`` caches, ``_button_*``, fonts) and the layout
helpers (``_effective_watch_card_h`` / ``_watch_card_body_split`` /
``_watch_chat_band_rect``) live on the HUD instance and are reached here via the
``hud`` argument. HUD keeps 1-line delegating wrappers (same names + signatures,
including the leading-underscore private names render() calls) so the call sites
are unchanged. The dependency is one-directional/acyclic: hud.py imports this
module at top level; this module reaches HUD only via the ``hud`` param +
TYPE_CHECKING (NO top-level ``import game.ui.hud``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from game.ui.widgets import HPBar, NineSlice
from game.ui.hud_layout import HERO_LEFT_MIN_H, RADAR_MINIMAP_H

if TYPE_CHECKING:
    from game.ui.hud import HUD


WATCH_CARD_HEADER_H = 18
WATCH_CARD_MAP_H = 160
WATCH_CARD_STATS_H = 78
# Snug vitals block when chat band is collapsed (no dead padding under stats rows).
WATCH_CARD_STATS_COMPACT_H = 58
WATCH_CARD_CHAT_H = 150
WATCH_CARD_FULL_H_WITH_CHAT = (
    WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H + WATCH_CARD_CHAT_H
)
WATCH_CARD_FULL_H_NO_CHAT = WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_COMPACT_H
WATCH_CARD_FULL_H = WATCH_CARD_FULL_H_WITH_CHAT


def render_hero_watch_card_infocard(
    hud: "HUD",
    surface: pygame.Surface,
    minimap_rect: pygame.Rect,
    game_state: dict,
) -> None:
    """Watch card above minimap: header, optional map slot + stats + chat (WK52)."""
    hud._card_slot_kind = "hero"
    pin = hud._pin_slot
    profiles = game_state.get("hero_profiles_by_id") or {}
    prof = profiles.get(pin.hero_id)

    cw = minimap_rect.width
    sh = int(surface.get_height())
    if hud._left_watch_rect is not None:
        watch_rect = hud._left_watch_rect
        cx = watch_rect.x
        cy = watch_rect.y
        ch = watch_rect.height
        cw = watch_rect.width
    else:
        ch = hud._effective_watch_card_h(sh)
        cx = minimap_rect.x
        cy = minimap_rect.y - ch

    raw_name = pin.pinned_name or "Hero"
    name_max_w = max(8, cw - 14 - 8)
    name_sig = (raw_name, name_max_w)
    if hud._watch_name_sig != name_sig or hud._watch_name_surf is None:
        name = raw_name
        name_surf = hud.font_tiny.render(name, True, (200, 195, 220))
        while name_surf.get_width() > name_max_w and len(name) > 2:
            name = name[:-1]
            name_surf = hud.font_tiny.render(name + "…", True, (200, 195, 220))
        hud._watch_name_sig = name_sig
        hud._watch_name_surf = name_surf
    name_surf = hud._watch_name_surf

    card_rect, hud._watch_card_chevron_rect, body_top = hud._info_card.draw_shell(
        surface,
        cx=cx,
        cy=cy,
        cw=cw,
        ch=ch,
        expanded=hud._watch_card_expanded,
        header_h=WATCH_CARD_HEADER_H,
        name_surf=name_surf,
        chevron_surf=None,
        header_close_x=True,
    )
    hud._watch_card_rect = card_rect

    if not hud._watch_card_expanded:
        return

    map_h, stats_h, chat_h = hud._watch_card_body_split(ch)
    if map_h <= 0:
        return

    map_rect = pygame.Rect(cx + 2, cy + WATCH_CARD_HEADER_H, cw - 4, map_h)
    pygame.draw.rect(surface, (8, 10, 16), map_rect)
    hud.watch_card_map_rect = map_rect

    sy = cy + WATCH_CARD_HEADER_H + map_h + 4
    bar_h = 6
    gutter = 6
    half = max(52, (cw - gutter * 3) // 2)
    left_x = cx + 4
    right_x = left_x + half + gutter // 2
    bar_left_w = max(36, half - 4)
    painted_stats_bottom_for_chat: int | None = None
    hud._chat_open_rect = None

    if stats_h > 0 and prof is not None:
        vitals = getattr(prof, "vitals", None)
        prog = getattr(prof, "progression", None)
        idn = getattr(prof, "identity", None)

        hp = int(getattr(vitals, "hp", 0) if vitals else 0)
        max_hp = int(getattr(vitals, "max_hp", 1) if vitals else 1)
        xp = int(getattr(prog, "xp", 0) if prog else 0)
        xp_to_lv = int(getattr(prog, "xp_to_level", 100) if prog else 100)
        level = int(getattr(idn, "level", 1) if idn else 1)

        stats_sig = (hp, max_hp, xp, xp_to_lv, level)
        if hud._watch_stats_sig != stats_sig or hud._watch_hp_label_surf is None:
            hud._watch_stats_sig = stats_sig
            hud._watch_hp_label_surf = hud.font_tiny.render(
                f"HP {hp}/{max_hp}", True, (190, 190, 190)
            )
            hud._watch_xp_label_surf = hud.font_tiny.render(
                f"XP {xp}/{xp_to_lv}", True, (190, 190, 190)
            )
            hud._watch_lv_label_surf = hud.font_tiny.render(
                f"Lvl {level}", True, (220, 200, 120)
            )
            hud._watch_mana_label_surf = hud.font_tiny.render("Mana —", True, (80, 78, 95))

        row1_y = sy
        surface.blit(hud._watch_hp_label_surf, (left_x, row1_y))
        surface.blit(hud._watch_mana_label_surf, (right_x, row1_y))
        bar_y1 = row1_y + hud._watch_hp_label_surf.get_height() + 1
        HPBar.render(surface, pygame.Rect(left_x, bar_y1, bar_left_w, bar_h), hp, max_hp)

        row2_y = bar_y1 + bar_h + 5
        surface.blit(hud._watch_xp_label_surf, (left_x, row2_y))
        surface.blit(hud._watch_lv_label_surf, (right_x, row2_y))

        if not hud._chat_visible:
            lv_surf = hud._watch_lv_label_surf
            bx = right_x + lv_surf.get_width() + 4
            bh = max(16, lv_surf.get_height() + 2)
            bw = max(40, hud.font_tiny.size("Chat")[0] + 10)
            bw = min(bw, cx + cw - bx - 6)
            btn_r = pygame.Rect(bx, row2_y + max(0, (lv_surf.get_height() - bh) // 2), bw, bh)
            if btn_r.width > 8 and btn_r.height > 8:
                NineSlice.render(surface, btn_r, hud._button_tex_normal, border=hud._button_slice_border)
                chat_lbl = hud.font_tiny.render("Chat", True, (210, 205, 230))
                surface.blit(
                    chat_lbl,
                    (
                        btn_r.centerx - chat_lbl.get_width() // 2,
                        btn_r.centery - chat_lbl.get_height() // 2,
                    ),
                )
                hud._chat_open_rect = btn_r

        bar_y2 = row2_y + hud._watch_xp_label_surf.get_height() + 1
        xp_ratio = max(0.0, min(1.0, xp / max(1, xp_to_lv)))
        pygame.draw.rect(surface, (40, 40, 55), pygame.Rect(left_x, bar_y2, bar_left_w, bar_h))
        if xp_ratio > 0:
            pygame.draw.rect(
                surface, (70, 130, 210), pygame.Rect(left_x, bar_y2, int(bar_left_w * xp_ratio), bar_h)
            )
        pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(left_x, bar_y2, bar_left_w, bar_h), 1)
        painted_stats_bottom_for_chat = bar_y2 + bar_h
    elif stats_h > 0:
        if hud._watch_mana_label_surf is None:
            hud._watch_mana_label_surf = hud.font_tiny.render("Mana —", True, (80, 78, 95))

    if chat_h > 0 and hud._chat_visible:
        chat_rect_inside_card = hud._watch_chat_band_rect(
            cx,
            cy,
            cw,
            ch,
            map_h,
            stats_h,
            chat_h,
            profiles,
            str(pin.hero_id),
            painted_stats_bottom_override=painted_stats_bottom_for_chat,
        )
        if chat_rect_inside_card is not None:
            hud._watch_card_chat_rect = chat_rect_inside_card
            hud._chat_panel.render_watch_band(
                surface, chat_rect_inside_card, game_state, str(pin.hero_id)
            )
            hud._chat_close_rect = getattr(hud._chat_panel, "_watch_band_close_rect", None)


def render_card_slot(
    hud: "HUD",
    surface: pygame.Surface,
    minimap_rect: pygame.Rect,
    game_state: dict,
) -> None:
    hud.watch_card_map_rect = None
    hud._watch_card_rect = None
    hud._watch_card_chevron_rect = None
    hud._watch_card_chat_rect = None
    hud._chat_close_rect = None
    hud._chat_open_rect = None
    hud._card_slot_kind = None

    if hud._pin_slot.hero_id is None:
        return
    render_hero_watch_card_infocard(hud, surface, minimap_rect, game_state)


def render_watch_card_chrome(
    hud: "HUD",
    surface: pygame.Surface,
    minimap_rect: pygame.Rect,
    game_state: dict,
) -> None:
    """WK52: pinned hero watch card above minimap (unaffected by building selection)."""
    render_card_slot(hud, surface, minimap_rect, game_state)


def effective_card_full_h(hud: "HUD") -> int:
    return WATCH_CARD_FULL_H_WITH_CHAT if hud._chat_visible else WATCH_CARD_FULL_H_NO_CHAT


def desired_watch_card_expanded_h(hud: "HUD") -> int:
    """Natural expanded height: no slack band under stats when chat is collapsed (WK52 R13)."""
    stats_blk = WATCH_CARD_STATS_H if hud._chat_visible else WATCH_CARD_STATS_COMPACT_H
    h = WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + stats_blk
    if hud._chat_visible:
        h += WATCH_CARD_CHAT_H
    return h


def effective_watch_card_h(hud: "HUD", screen_h: int) -> int:
    """Pinned watch-card height from layout split or legacy cap when layout not computed yet."""
    if hud._left_watch_rect is not None and hud._left_watch_rect.height > 0:
        return int(hud._left_watch_rect.height)
    if hud._pin_slot.hero_id is None:
        return 0
    top_h = int(getattr(hud.theme, "top_bar_h", 48))
    minimap_y = screen_h - int(RADAR_MINIMAP_H)
    if hud._watch_card_expanded:
        want = hud._desired_watch_card_expanded_h()
    else:
        want = WATCH_CARD_HEADER_H
    min_top = top_h + HERO_LEFT_MIN_H
    max_ch = minimap_y - min_top
    return min(want, max(WATCH_CARD_HEADER_H, max_ch))


def watch_card_body_split(hud: "HUD", ch: int) -> tuple[int, int, int]:
    if ch <= WATCH_CARD_HEADER_H or not hud._watch_card_expanded:
        return (0, 0, 0)
    inner = ch - WATCH_CARD_HEADER_H
    map_h = min(WATCH_CARD_MAP_H, inner)
    inner -= map_h
    stats_cap = WATCH_CARD_STATS_H if hud._chat_visible else WATCH_CARD_STATS_COMPACT_H
    stats_h = min(stats_cap, inner)
    inner -= stats_h
    if hud._chat_visible:
        chat_h = max(0, inner)
    else:
        chat_h = 0
    return (map_h, stats_h, chat_h)


def watch_chat_band_rect(
    hud: "HUD",
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
    """Screen-space rect for WK52 chat band; matches slack absorption in _render_watch_card_chrome."""
    if not hero_id or not hud._watch_card_expanded or chat_h <= 0 or map_h <= 0:
        return None
    sy = cy + WATCH_CARD_HEADER_H + map_h + 4
    allotted_stats_bottom = cy + WATCH_CARD_HEADER_H + map_h + stats_h
    default_top = allotted_stats_bottom
    prof = profiles.get(hero_id)
    painted_bottom: int | None = painted_stats_bottom_override
    if painted_bottom is None and stats_h > 0 and prof is not None:
        lab_h = hud.font_tiny.get_height()
        bar_h = 6
        row1_y = sy
        bar_y1 = row1_y + lab_h + 1
        row2_y = bar_y1 + bar_h + 5
        bar_y2 = row2_y + lab_h + 1
        painted_bottom = bar_y2 + bar_h
    chat_y = max(sy, painted_bottom + 2) if painted_bottom is not None else default_top
    chat_h_draw = max(0, cy + ch - chat_y)
    if chat_h_draw <= 0:
        return None
    return pygame.Rect(cx + 2, chat_y, cw - 4, chat_h_draw)
