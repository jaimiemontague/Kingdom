"""Panel-chrome button renderers for the HUD (WK97 slice of hud.py).

Extracted VERBATIM from game/ui/hud.py (WK97 Round B-14): the panel-chrome
button render cluster — ``render_right_close_button`` (right-panel close X),
``render_left_close_button`` (left-panel close X, lazy-inits ``hud._left_close_button``),
``render_pin_button`` (WK51 pin toggle next to the close button),
``trigger_recall_flash`` (WK52 — flashes the Recall button red; called by
``game/ui/pin_alert_watcher.py``), ``render_memorial_button`` (memorial opener
when a fallen pin has a pending record) and ``render_recall_button`` (WK51
bottom-bar recall when a hero is pinned). These are LEAF renderers: each draws a
button and stores a hit-rect that ``handle_click`` (which STAYS on HUD) reads.
This module also OWNS the ``COLOR_PIN_GOLD`` constant (it lives here because the
pin renderer is its only consumer — verified no other use in game/tests/tools, so
no re-export is needed). All hit-rect/flash STATE (``right_close_rect``,
``left_close_rect``, ``pin_button_rect``, ``memorial_btn_rect``,
``_recall_flash_end_ms``, the ``_recall_*`` overlays/caches, ``_pin_slot``,
``_button_*`` textures, ``_frame_*`` colors, fonts, ``theme``) lives on the HUD
instance and is reached here via the ``hud`` argument. HUD keeps 1-line delegating
wrappers (same names + signatures, including the leading-underscore private names
the render() call sites use and the external ``trigger_recall_flash`` that
``pin_alert_watcher`` calls) so the call sites are unchanged. The dependency is
one-directional/acyclic: hud.py reaches this module only via lazy imports in the
wrappers; this module reaches HUD only via the ``hud`` param + TYPE_CHECKING
(NO top-level ``import game.ui.hud``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from game.sim.timebase import now_ms as sim_now_ms
from game.ui.hero_panel import truncate_panel_line
from game.ui.widgets import Button, NineSlice, TextLabel

if TYPE_CHECKING:
    from game.ui.hud import HUD


COLOR_PIN_GOLD = (220, 180, 50)


def render_right_close_button(hud: "HUD", surface: pygame.Surface, right_rect: pygame.Rect) -> None:
    x_surf = TextLabel.get_surface(hud.theme.font_small, "X", (240, 240, 240))
    size = max(18, x_surf.get_height() + 6)
    hud._right_close_button.rect = pygame.Rect(
        int(right_rect.right - size - 6),
        int(right_rect.y + 6),
        int(size),
        int(size),
    )
    hud._right_close_button.text = "X"
    hud._right_close_button.render(
        surface,
        pygame.mouse.get_pos(),
        texture_normal=hud._button_tex_normal,
        texture_hover=hud._button_tex_hover,
        texture_pressed=hud._button_tex_pressed,
        slice_border=hud._button_slice_border,
        bg_normal=(45, 45, 55),
        bg_hover=(60, 60, 70),
        bg_pressed=(70, 70, 85),
        border_outer=hud._frame_outer,
        border_inner=hud._frame_inner,
        border_highlight=hud._frame_highlight,
        text_color=(240, 240, 240),
        text_shadow_color=(20, 20, 30),
    )
    hud.right_close_rect = pygame.Rect(hud._right_close_button.rect)


def render_left_close_button(hud: "HUD", surface: pygame.Surface, left_rect: pygame.Rect) -> None:
    if getattr(hud, "_left_close_button", None) is None:
        hud._left_close_button = Button(
            rect=pygame.Rect(0, 0, 1, 1),
            text="X",
            font=hud.theme.font_small,
            enabled=True,
        )
    x_surf = TextLabel.get_surface(hud.theme.font_small, "X", (240, 240, 240))
    size = max(18, x_surf.get_height() + 6)
    hud._left_close_button.rect = pygame.Rect(
        int(left_rect.right - size - 6),
        int(left_rect.y + 6),
        int(size),
        int(size),
    )
    hud._left_close_button.text = "X"
    hud._left_close_button.render(
        surface,
        pygame.mouse.get_pos(),
        texture_normal=hud._button_tex_normal,
        texture_hover=hud._button_tex_hover,
        texture_pressed=hud._button_tex_pressed,
        slice_border=hud._button_slice_border,
        bg_normal=(45, 45, 55),
        bg_hover=(60, 60, 70),
        bg_pressed=(70, 70, 85),
        border_outer=hud._frame_outer,
        border_inner=hud._frame_inner,
        border_highlight=hud._frame_highlight,
        text_color=(240, 240, 240),
        text_shadow_color=(20, 20, 30),
    )
    hud.left_close_rect = pygame.Rect(hud._left_close_button.rect)


def render_pin_button(hud: "HUD", surface: pygame.Surface, left_rect: pygame.Rect, game_state: dict) -> None:
    """WK51: small pin toggle to the left of the panel close button."""
    sel = game_state.get("selected_hero")
    if sel is None:
        hud.pin_button_rect = None
        return
    pin_size = 20
    gap = 6
    x_surf = TextLabel.get_surface(hud.theme.font_small, "X", (240, 240, 240))
    close_size = max(18, x_surf.get_height() + 6)
    close_x = int(left_rect.right - close_size - 6)
    pin_x = int(close_x - gap - pin_size)
    pin_y = int(left_rect.y + 6)
    hud.pin_button_rect = pygame.Rect(pin_x, pin_y, pin_size, pin_size)
    pr = hud.pin_button_rect
    sel_id = str(getattr(sel, "hero_id", "") or "")
    pinned = bool(sel_id and hud._pin_slot.hero_id == sel_id)
    cx, cy = pr.centerx, pr.centery

    if not hasattr(hud, "_pin_emoji_font") or getattr(hud, "_pin_emoji_font_size", 0) != pin_size:
        try:
            hud._pin_emoji_font = pygame.font.SysFont(
                "segoeuiemoji,segoeui,noto color emoji,arial", pin_size
            )
        except Exception:
            hud._pin_emoji_font = None
        hud._pin_emoji_font_size = pin_size

    emoji_surf = None
    if hud._pin_emoji_font is not None:
        try:
            emoji_surf = hud._pin_emoji_font.render("\U0001f4cc", True, (255, 255, 255))
        except Exception:
            emoji_surf = None

    if emoji_surf is None or emoji_surf.get_width() <= 4:
        if pinned:
            pygame.draw.circle(surface, COLOR_PIN_GOLD, (cx, cy), pin_size // 2 - 1)
            pygame.draw.circle(surface, hud._frame_outer, (cx, cy), pin_size // 2 - 1, 2)
            col = (255, 255, 255)
        else:
            pygame.draw.circle(surface, hud._frame_inner, (cx, cy), pin_size // 2 - 1, 2)
            col = (150, 150, 160)
        p_surf = TextLabel.get_surface(hud.theme.font_small, "P", col)
        surface.blit(p_surf, (cx - p_surf.get_width() // 2, cy - p_surf.get_height() // 2))
        return

    dest_pos = (
        cx - emoji_surf.get_width() // 2,
        cy - emoji_surf.get_height() // 2,
    )
    if pinned:
        surface.blit(emoji_surf, dest_pos)
    else:
        s = emoji_surf.copy()
        s.set_alpha(128)
        surface.blit(s, dest_pos)


def trigger_recall_flash(hud: "HUD") -> None:
    """Flash the Recall button red (WK52). Called by PinAlertWatcher."""
    hud._recall_flash_end_ms = int(sim_now_ms()) + 750


def render_memorial_button(
    hud: "HUD", surface: pygame.Surface, memorial_rect: pygame.Rect, game_state: dict
) -> None:
    """Memorial opener when a fallen pin has a pending record."""
    hud.memorial_btn_rect = None
    if hud._pending_memorial is None:
        return
    if hud.memorial_card.visible:
        return
    hud.memorial_btn_rect = pygame.Rect(memorial_rect)
    NineSlice.render(
        surface, memorial_rect, hud._button_tex_normal, border=hud._button_slice_border
    )
    lbl = hud.theme.font_small.render(f"{chr(9904)} Memorial", True, (200, 180, 130))
    surface.blit(
        lbl,
        (
            memorial_rect.x + (memorial_rect.width - lbl.get_width()) // 2,
            memorial_rect.y + (memorial_rect.height - lbl.get_height()) // 2,
        ),
    )


def render_recall_button(hud: "HUD", surface: pygame.Surface, recall_rect: pygame.Rect, game_state: dict) -> None:
    """WK51: bottom-bar recall when a hero is pinned."""
    profiles = game_state.get("hero_profiles_by_id") or {}
    pin = hud._pin_slot
    if pin.hero_id is None:
        hud.recall_rect = None
        return
    hero_alive = pin.hero_id in profiles
    pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))
    if pin.hero_id is None:
        hud.recall_rect = None
        return
    hud.recall_rect = pygame.Rect(recall_rect)
    prof = profiles.get(pin.hero_id)
    name = "Hero"
    if prof is not None:
        idn = getattr(prof, "identity", None)
        if idn is not None:
            name = str(getattr(idn, "name", "Hero"))
    fallen = pin.is_fallen()
    label = f"{name} (fallen)" if fallen else f"\u21a9 {truncate_panel_line(name, max_chars=14)}"
    sig = (str(pin.hero_id), fallen, label)
    if hud._recall_label_sig != sig or hud._recall_label_surf is None:
        hud._recall_label_sig = sig
        col = (160, 160, 165) if fallen else (240, 240, 240)
        hud._recall_label_surf = hud.theme.font_small.render(label, True, col)
    tex = hud._button_tex_pressed if fallen else hud._button_tex_normal
    NineSlice.render(surface, recall_rect, tex, border=hud._button_slice_border)

    size = (recall_rect.width, recall_rect.height)
    if hud._recall_overlay_size != size:
        hud._recall_overlay_size = size
        hud._recall_fallen_overlay = pygame.Surface(size, pygame.SRCALPHA)
        hud._recall_fallen_overlay.fill((40, 40, 50, 150))
        hud._recall_flash_overlay = pygame.Surface(size, pygame.SRCALPHA)
        hud._recall_flash_overlay.fill((220, 30, 30, 140))

    if fallen and hud._recall_fallen_overlay is not None:
        surface.blit(hud._recall_fallen_overlay, recall_rect.topleft)
    if hud._recall_label_surf is not None:
        lw, lh = hud._recall_label_surf.get_size()
        surface.blit(
            hud._recall_label_surf,
            (
                recall_rect.x + (recall_rect.width - lw) // 2,
                recall_rect.y + (recall_rect.height - lh) // 2,
            ),
        )
    now = int(sim_now_ms())
    if now < hud._recall_flash_end_ms:
        elapsed = max(0, now - (hud._recall_flash_end_ms - 750))
        pulse = elapsed // 250
        if pulse % 2 == 0 and hud._recall_flash_overlay is not None:
            surface.blit(hud._recall_flash_overlay, recall_rect.topleft)
