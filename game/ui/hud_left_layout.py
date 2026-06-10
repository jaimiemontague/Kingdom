"""Left-column segment/split layout + sidebar-resize drag, extracted from game.ui.hud (WK99).

All layout/drag state lives on HUD, reached via the hud arg; acyclic -- imports only
leaf modules + TYPE_CHECKING HUD.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import pygame
from game.sim.timebase import now_ms as sim_now_ms
from game.ui.micro_view_manager import ViewMode
from game.ui.hud_layout import (
    HERO_LEFT_MIN_H,
    HERO_MENU_CHAT_GAP,
    HERO_MENU_CHAT_MAX_FRAC,
    HERO_MENU_CHAT_MIN_H,
    HERO_MENU_CHAT_PREFERRED_H,
    HERO_MENU_HERO_MIN_H,
    LEFT_COL_W,
    LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO,
    LEFT_SPLIT_HANDLE_H,
    LEFT_SPLIT_HANDLE_HIT_H,
    MAIN_MENU_MIN_PRESENT_H,
    RADAR_MINIMAP_H,
)
from game.ui.hud_watch_card import WATCH_CARD_HEADER_H
if TYPE_CHECKING:
    from game.ui.hud import HUD


def split_handle_hit_rect(rect: pygame.Rect) -> pygame.Rect:
    """The pointer hit band for a split handle: the visual bar (LEFT_SPLIT_HANDLE_H px)
    expanded vertically to the standard LEFT_SPLIT_HANDLE_HIT_H grab band (WK130 — all
    pointer-down / chrome hit tests must use this, never the bare visual rect)."""
    extra = max(0, LEFT_SPLIT_HANDLE_HIT_H - rect.height)
    return pygame.Rect(
        rect.x,
        rect.y - (extra + 1) // 2,
        rect.width,
        rect.height + extra,
    )


def left_column_segments_open(hud, game_state: dict | None) -> tuple[bool, bool]:
    """Return (main_panel_open, watch_card_open) for left-column split layout."""
    gs = game_state or {}
    main_open = (
        gs.get("selected_hero") is not None
        or gs.get("selected_peasant") is not None
        or gs.get("selected_enemy") is not None
        or gs.get("selected_building") is not None
    )
    watch_open = hud._pin_slot.hero_id is not None
    return main_open, watch_open


def normalized_left_split_fracs(hud, main_open: bool, watch_open: bool) -> dict[str, float]:
    if main_open and not watch_open:
        solo = max(
            0.05,
            min(
                0.95,
                float(
                    hud._left_split_fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
                ),
            ),
        )
        return {"main_solo": solo}
    keys: list[str] = []
    if main_open:
        keys.append("main")
    if watch_open:
        keys.append("watch")
    if not keys:
        return {}
    raw = {k: max(0.05, float(hud._left_split_fracs.get(k, 0.5))) for k in keys}
    total = sum(raw.values())
    return {k: raw[k] / total for k in keys}


def layout_left_column_segments(
    hud,
    top_h: int,
    minimap: pygame.Rect,
    game_state: dict | None,
) -> tuple[pygame.Rect, pygame.Rect | None, pygame.Rect | None]:
    """Allocate main + watch rects above the fixed minimap using session split fractions."""
    available = max(0, minimap.y - top_h)
    main_open, watch_open = hud._left_column_segments_open(game_state)
    hud._left_main_rect = None
    hud._left_watch_rect = None
    hud._left_split_handle_rects = {}

    if available <= 0 or (not main_open and not watch_open):
        left = pygame.Rect(0, top_h, LEFT_COL_W, available)
        hud._last_left_rect = left if main_open else None
        return left, None, None

    fracs = hud._normalized_left_split_fracs(main_open, watch_open)
    main_h = watch_h = 0

    if main_open and watch_open:
        # WK121: clicking the watch-card header must NEVER maximize the card over /
        # evict the building/hero (main) menu. The watch segment is bounded to the
        # card's OWN content: just the header when collapsed, or its desired
        # expanded height (incl. chat when open) when expanded — it can no longer
        # claim a large pre-reserved fraction that the body then "fills" on toggle.
        # The main menu always keeps at least its natural content height (down to a
        # sane minimum only when the column is genuinely too short), so the two
        # panels visibly coexist instead of one taking over the sidebar.
        if hud._watch_card_expanded:
            watch_want = int(hud._desired_watch_card_expanded_h())
        else:
            watch_want = WATCH_CARD_HEADER_H
        watch_want = max(WATCH_CARD_HEADER_H, watch_want)

        main_natural = int(hud._left_main_natural_h(game_state or {}))
        if main_natural <= 0:
            # First frame after selection (panel not yet rendered): fall back to the
            # saved fraction so the menu still has room until content height reports.
            main_natural = max(HERO_LEFT_MIN_H, int(round(fracs["main"] * available)))
        # The main menu's floor: prefer its full content, but never demand more than
        # a sane menu-present minimum when forced to share a short column.
        main_floor = min(main_natural, max(HERO_LEFT_MIN_H, MAIN_MENU_MIN_PRESENT_H))

        # The watch card takes only its bounded want; the main menu takes its
        # natural content. If both don't fit, shrink the watch first (down to its
        # header), then the main toward its floor — the main menu is never the
        # first to lose space. Any leftover column stays EMPTY (no giant card):
        # neither panel is inflated to absorb slack, so a collapsed watch card is
        # an 18px header peek, not a full-column box.
        watch_h = min(watch_want, max(WATCH_CARD_HEADER_H, available - main_floor))
        main_h = min(main_natural, available - watch_h)
        if main_h < HERO_LEFT_MIN_H:
            main_h = HERO_LEFT_MIN_H
            watch_h = max(WATCH_CARD_HEADER_H, available - main_h)
        # WK130 invariant: the two stacked segments may NEVER overflow the column
        # (overlap the minimap) at any drag position / on genuinely too-short columns.
        main_h = min(main_h, available)
        watch_h = max(0, min(watch_h, available - main_h))
    elif main_open:
        if hud._should_render_hero_menu_chat_popup(game_state or {}):
            main_h = available
        else:
            # WK115 BUG 1: size the solo hero/building card to its content so no
            # resize bar floats below the last line. Falls back to the legacy
            # fraction only on the first frame after selection (before the panel
            # has rendered + reported its content height).
            natural = hud._left_main_natural_h(game_state or {})
            if natural > 0:
                main_h = max(HERO_LEFT_MIN_H, min(natural, available))
            else:
                solo_frac = fracs.get("main_solo", LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO)
                main_h = max(HERO_LEFT_MIN_H, int(round(float(solo_frac) * available)))
                main_h = min(main_h, available)
    else:
        watch_h = available

    main_rect: pygame.Rect | None = None
    watch_rect: pygame.Rect | None = None
    y = top_h

    if main_open:
        main_rect = pygame.Rect(0, y, LEFT_COL_W, main_h)
        hud._left_main_rect = main_rect
        hud._last_left_rect = main_rect
        if watch_open:
            divider = pygame.Rect(0, y + main_h - LEFT_SPLIT_HANDLE_H, LEFT_COL_W, LEFT_SPLIT_HANDLE_H)
            hud._left_split_handle_rects["main_bottom"] = divider
            hud._left_split_handle_rects["watch_top"] = divider
        # WK115 BUG 1: no handle in the solo case — the card is sized to its
        # content (above), so there is no empty space below it to resize against.
        # Overflow (rare) is handled by mouse-wheel scroll, not a resize bar.
        y += main_h

    if watch_open:
        watch_y = y if main_open else minimap.y - watch_h
        watch_rect = pygame.Rect(0, watch_y, LEFT_COL_W, watch_h)
        hud._left_watch_rect = watch_rect
        bottom_handle = pygame.Rect(
            0, watch_y + watch_h - LEFT_SPLIT_HANDLE_H, LEFT_COL_W, LEFT_SPLIT_HANDLE_H
        )
        hud._left_split_handle_rects["watch_bottom"] = bottom_handle
        if not main_open:
            hud._last_left_rect = watch_rect

    left = main_rect or watch_rect or pygame.Rect(0, top_h, LEFT_COL_W, available)
    return left, main_rect, watch_rect


def render_left_split_handles(hud, surface: pygame.Surface) -> None:
    """Draw thin resize bars on open left-column segment boundaries (WK61-R10)."""
    for key, rect in hud._left_split_handle_rects.items():
        if rect.width <= 0 or rect.height <= 0:
            continue
        hover = key == hud._left_split_drag_kind
        color = (120, 130, 160) if hover else (70, 78, 98)
        pygame.draw.rect(surface, color, rect)
        mid_y = rect.centery
        pygame.draw.line(
            surface,
            (150, 160, 190) if hover else (95, 105, 130),
            (rect.x + 8, mid_y),
            (rect.right - 8, mid_y),
            1,
        )


def handle_sidebar_split_pointer_down(hud, pos: tuple[int, int], game_state: dict) -> bool:
    """Begin dragging a left-column split handle; returns True if consumed."""
    if hud._left_split_drag_kind is not None:
        return True
    x, y = int(pos[0]), int(pos[1])
    for key, rect in hud._left_split_handle_rects.items():
        # WK130: hit-test the standard 8px grab band, not the 4px visual bar.
        if split_handle_hit_rect(rect).collidepoint(x, y):
            hud._left_split_drag_kind = key
            hud._left_split_drag_start_y = y
            hud._left_split_drag_main_h0 = int(hud._left_main_rect.height) if hud._left_main_rect else 0
            hud._left_split_drag_watch_h0 = int(hud._left_watch_rect.height) if hud._left_watch_rect else 0
            return True
    return False


def handle_sidebar_split_pointer_move(hud, pos: tuple[int, int], game_state: dict) -> bool:
    """Update split fractions while dragging; returns True if consumed."""
    if hud._left_split_drag_kind is None:
        return False
    top_h = int(getattr(hud.theme, "top_bar_h", 48))
    minimap_y = hud.screen_height - int(RADAR_MINIMAP_H)
    available = max(0, minimap_y - top_h)
    if available <= 0:
        return True
    dy = int(pos[1]) - hud._left_split_drag_start_y
    kind = hud._left_split_drag_kind
    if kind in ("main_bottom", "watch_top"):
        new_main_h = max(HERO_LEFT_MIN_H, min(available - WATCH_CARD_HEADER_H, hud._left_split_drag_main_h0 + dy))
        new_watch_h = available - new_main_h
    elif kind == "watch_bottom":
        new_watch_h = max(
            WATCH_CARD_HEADER_H,
            min(available - HERO_LEFT_MIN_H, hud._left_split_drag_watch_h0 + dy),
        )
        new_main_h = available - new_watch_h
    elif kind == "main_solo":
        new_main_h = max(
            HERO_LEFT_MIN_H,
            min(available, hud._left_split_drag_main_h0 + dy),
        )
        hud._left_split_fracs["main_solo"] = float(new_main_h) / float(available)
        return True
    else:
        return True
    if new_main_h > 0 and new_watch_h > 0:
        hud._left_split_fracs["main"] = float(new_main_h) / float(available)
        hud._left_split_fracs["watch"] = float(new_watch_h) / float(available)
    return True


def handle_sidebar_split_pointer_up(hud) -> bool:
    """End split-handle drag; returns True if a drag was active."""
    if hud._left_split_drag_kind is None:
        return False
    hud._left_split_drag_kind = None
    return True


def layout_rects_for_screen(
    hud, w: int, h: int, *, show_right_panel: bool, game_state: dict | None = None
) -> tuple[
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
]:
    """Geometry only — shared by _compute_layout and Ursina pointer routing.

    Delegates core rectangle math to HUDLayoutManager, then overlays the
    left-column segment allocation which depends on game state.
    """
    top_h = int(getattr(hud.theme, "top_bar_h", 48))
    bottom_h = int(getattr(hud.theme, "bottom_bar_h", 96))
    margin = int(getattr(hud.theme, "margin", 8))
    gutter = int(getattr(hud.theme, "gutter", 8))

    _ = show_right_panel  # right chrome retired (WK52 R4)

    layout = hud._layout_mgr.compute(
        w, h,
        top_bar_h=top_h,
        bottom_bar_h=bottom_h,
        margin=margin,
        gutter=gutter,
    )

    hud._watch_card_chat_rect = None

    # Left-column segments depend on game_state (selected hero/building/pin).
    left, _main_rect, _watch_rect = hud._layout_left_column_segments(
        top_h, layout.minimap, game_state
    )

    return (
        layout.top_bar,
        layout.bottom_bar,
        left,
        layout.right_panel,
        layout.minimap,
        layout.command_bar,
        layout.speed_control,
        layout.recall_button,
        layout.memorial_button,
    )


def compute_layout(
    hud, surface: pygame.Surface, game_state: dict | None = None
) -> tuple[
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
    pygame.Rect,
]:
    """Compute UI rects from current surface size. Returns top, bottom, left, right, minimap, command, speed_rect."""
    w, h = surface.get_width(), surface.get_height()
    hud.screen_width = int(w)
    hud.screen_height = int(h)
    show_right = getattr(hud, "_show_right_panel", hud.right_panel_visible)
    top, bottom, left, right, minimap, command, speed_rect, recall, memorial = hud._layout_rects_for_screen(
        w, h, show_right_panel=show_right, game_state=game_state
    )
    hud.side_panel_width = right.width
    return top, bottom, left, right, minimap, command, speed_rect, recall, memorial


def virtual_pointer_in_hud_chrome(
    hud, pos: tuple[int, int], surface: pygame.Surface, game_state: dict
) -> bool:
    """True if virtual-screen coords lie over HUD chrome (use UI pixel coords, not world raycast).

    Anti-aliased or icon pixels can have alpha < 24; alpha-only hit tests miss command buttons (e.g. Bounty).
    """
    x, y = int(pos[0]), int(pos[1])
    w, h = surface.get_width(), surface.get_height()
    if w <= 0 or h <= 0 or not (0 <= x < w and 0 <= y < h):
        return False
    has_right_content = hud._micro_view.mode != ViewMode.OVERVIEW
    show_right = hud.right_panel_visible and has_right_content
    _ = show_right  # Tab/no-op; no right chrome hit region (WK52 R4)
    top, bottom, left, right, minimap, command, speed_rect, recall, memorial = hud._layout_rects_for_screen(
        w, h, show_right_panel=bool(hud.right_panel_visible), game_state=game_state
    )
    profiles = game_state.get("hero_profiles_by_id") or {}
    pin = hud._pin_slot
    if pin.hero_id is not None:
        hero_alive = pin.hero_id in profiles
        pin.update_liveness(hero_alive=hero_alive, now_ms=int(sim_now_ms()))
    mem_ov = getattr(hud, "memorial_card", None)
    if mem_ov is not None and getattr(mem_ov, "visible", False):
        return True
    regions = [top, bottom, minimap, command, speed_rect]
    if pin.hero_id is not None:
        regions.append(recall)
        regions.append(memorial)
    bio = getattr(hud, "building_interior_overlay", None)
    if bio is not None and getattr(bio, "visible", False):
        return True
    dco = getattr(hud, "demolish_confirm_overlay", None)
    if dco is not None and getattr(dco, "visible", False):
        return True
    if pin.hero_id is not None:
        # WK130: single source of geometry — the watch segment rect was just computed by
        # the SAME layout call the render path uses (hud._layout_rects_for_screen above
        # sets hud._left_watch_rect via layout_left_column_segments). The chat band is
        # always contained within that rect, so no independently rebuilt chat/card rects.
        if hud._left_watch_rect is not None:
            regions.append(pygame.Rect(hud._left_watch_rect))
        else:
            ch = hud._effective_watch_card_h(h)
            if ch > 0:
                regions.append(pygame.Rect(minimap.x, minimap.y - ch, minimap.width, ch))
    if (
        game_state.get("selected_hero") is not None
        or game_state.get("selected_peasant") is not None
        or game_state.get("selected_building") is not None
        or game_state.get("selected_enemy") is not None
    ):
        regions.append(left)
    for r in regions:
        if r.collidepoint(x, y):
            return True
    for handle in hud._left_split_handle_rects.values():
        # WK130: same 8px grab band as handle_sidebar_split_pointer_down.
        if split_handle_hit_rect(handle).collidepoint(x, y):
            return True
    if hud.show_help:
        help_r = pygame.Rect(max(0, w - 320), 0, min(320, w), min(520, h))
        if help_r.collidepoint(x, y):
            return True
    return False


def should_render_hero_menu_chat_popup(hud, game_state: dict) -> bool:
    cp = hud._chat_panel
    sel = game_state.get("selected_hero")
    if cp is None or not cp.is_active() or sel is None:
        return False
    if game_state.get("selected_building") is not None:
        return False
    hid = str(getattr(sel, "hero_id", "") or "")
    chat_hid = str(getattr(cp.hero_target, "hero_id", "") or "")
    if hid != chat_hid:
        return False
    return not hud._uses_pinned_watch_card_chat(hid)


def hero_menu_chat_desired_h(hud, left_h: int) -> int:
    """Vertical space to reserve for in-column hero-menu chat (WK61-R9)."""
    if left_h <= 0:
        return 0
    pref = min(
        HERO_MENU_CHAT_PREFERRED_H,
        max(HERO_MENU_CHAT_MIN_H, int(left_h * HERO_MENU_CHAT_MAX_FRAC)),
    )
    max_chat = max(HERO_MENU_CHAT_MIN_H, left_h - HERO_MENU_HERO_MIN_H - HERO_MENU_CHAT_GAP)
    return max(HERO_MENU_CHAT_MIN_H, min(pref, max_chat))


def hero_menu_chat_split_rects(
    hud, left: pygame.Rect
) -> tuple[pygame.Rect, pygame.Rect] | None:
    """Split left column: shrunk scrollable hero sheet + readable chat band."""
    if left.width <= 0 or left.height <= 0:
        return None
    chat_h = hud._hero_menu_chat_desired_h(left.height)
    hero_h = left.height - chat_h - HERO_MENU_CHAT_GAP
    if hero_h < HERO_MENU_HERO_MIN_H:
        hero_h = max(HERO_MENU_HERO_MIN_H, left.height - HERO_MENU_CHAT_MIN_H - HERO_MENU_CHAT_GAP)
        chat_h = left.height - hero_h - HERO_MENU_CHAT_GAP
    if chat_h < HERO_MENU_CHAT_MIN_H or hero_h < HERO_LEFT_MIN_H:
        return None
    hero_rect = pygame.Rect(left.x, left.y, left.width, hero_h)
    chat_rect = pygame.Rect(
        left.x + 4,
        left.y + hero_h + HERO_MENU_CHAT_GAP,
        left.width - 8,
        chat_h,
    )
    return hero_rect, chat_rect
