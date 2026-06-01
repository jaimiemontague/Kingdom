"""WK116: input/pointer cluster extracted from ursina_app.py (owner-arg pure-move,
WK105/WK113 pattern). UrsinaApp keeps thin delegating wrappers; these functions take
the app instance as ``owner``. Byte-faithful move — no behavior change."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ursina import mouse

from game.graphics.ursina_pick import pick_world_xz_on_floor_y0
from game.graphics.ursina_renderer import SCALE
from game.graphics.ursina_screenshot import save_ursina_window_screenshot
from game.input_manager import InputEvent
from game.ursina_input_manager import ursina_key_to_input_event

if TYPE_CHECKING:  # one-way edge: ursina_app imports THIS module (lazily in wrappers)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401


def _is_chat_active(owner: "UrsinaApp") -> bool:
    if getattr(owner.engine, '_command_mode', False):
        return True
    cp = getattr(getattr(owner.engine, "hud", None), "_chat_panel", None)
    return cp is not None and getattr(cp, "is_active", lambda: False)()


def _install_ursina_input_hook(owner: "UrsinaApp") -> None:
    app = owner

    def ursina_input(key: str) -> None:
        _handle_ursina_input(app, key)

    import __main__

    __main__.input = ursina_input


def _pixel_hits_opaque_ui(owner: "UrsinaApp", px: int, py: int) -> bool:
    """True if virtual screen pixel has opaque HUD (alpha high enough to steal the click)."""
    surf = owner.engine.screen
    try:
        c = surf.get_at((px, py))
    except Exception:
        return True
    if len(c) < 4:
        return bool(c[0] or c[1] or c[2])
    return c[3] >= 24


def _engine_screen_pos_for_pointer(owner: "UrsinaApp") -> tuple[tuple[int, int], str, tuple[float, float] | None, float, float]:
    """
    Map Ursina pointer → virtual pygame pixel + engine screen coords for handlers.

    Returns:
        (engine_sx, engine_sy), kind, world_xz_or_none, wx_sim, wy_sim
    """
    px, py = owner.input_manager.get_mouse_pos()
    eng = owner.engine

    # Stationary-pointer/camera early-out: when nothing the result depends on has
    # changed, the (pos, kind, hit, wx_sim, wy_sim) tuple and the
    # eng._ursina_pointer_world_sim side effect are provably identical to last frame,
    # so skip get_game_state / virtual_pointer_in_hud_chrome / floor raycast entirely.
    try:
        from ursina import camera as _cam
        _cam_wp = tuple(round(v, 4) for v in _cam.world_position)
        _cam_wr = tuple(round(v, 4) for v in _cam.world_rotation)
    except Exception:
        _cam_wp = None
        _cam_wr = None
    key = (
        (px, py),
        float(eng.zoom if eng.zoom else 1.0),
        float(getattr(eng, "camera_x", 0.0)),
        float(getattr(eng, "camera_y", 0.0)),
        _cam_wp,
        _cam_wr,
        bool(getattr(eng, "paused", False)),
        bool(getattr(getattr(eng, "pause_menu", None), "visible", False)),
    )
    if key == owner._pointer_cache_key and owner._pointer_cache_result is not None:
        eng._ursina_pointer_world_sim = owner._pointer_cache_world_sim
        return owner._pointer_cache_result

    eng._ursina_pointer_world_sim = None
    z = float(eng.zoom if eng.zoom else 1.0)
    hit: tuple[float, float] | None = None
    wx_sim = wy_sim = 0.0

    # Paused / ESC menu: the center of the screen is pygame HUD (often semi-transparent
    # backdrop). get_at() can be <24 alpha or stale → world-mapping breaks hover/clicks.
    # Input is consumed by the menu while open; when paused, world clicks are blocked too.
    if getattr(eng, "_ursina_viewer", False) and (
        getattr(eng, "paused", False)
        or (
            getattr(eng, "pause_menu", None) is not None
            and getattr(eng.pause_menu, "visible", False)
        )
    ):
        result = (px, py), "ui", None, 0.0, 0.0
        owner._pointer_cache_key = key
        owner._pointer_cache_result = result
        owner._pointer_cache_world_sim = eng._ursina_pointer_world_sim
        return result

    gs = eng.get_game_state()
    if _pixel_hits_opaque_ui(owner, px, py) or eng.hud.virtual_pointer_in_hud_chrome(
        (px, py), eng.screen, gs
    ):
        pos = (px, py)
        kind = "ui"
    else:
        hit = pick_world_xz_on_floor_y0()
        if hit is None:
            pos = (px, py)
            kind = "ui_fallback"
        else:
            wx, wz = hit
            wx_sim = wx * SCALE
            wy_sim = -wz * SCALE
            eng._ursina_pointer_world_sim = (wx_sim, wy_sim)
            sx = (wx_sim - eng.camera_x) * z
            sy = (wy_sim - eng.camera_y) * z
            pos = (int(round(sx)), int(round(sy)))
            kind = "world"

    result = (pos, kind, hit, wx_sim, wy_sim)
    owner._pointer_cache_key = key
    owner._pointer_cache_result = result
    owner._pointer_cache_world_sim = eng._ursina_pointer_world_sim
    return result


def _sidebar_split_drag_active(owner: "UrsinaApp") -> bool:
    hud = getattr(owner.engine, "hud", None)
    return hud is not None and getattr(hud, "_left_split_drag_kind", None) is not None


def _virtual_screen_pos(owner: "UrsinaApp") -> tuple[int, int]:
    pos = owner.input_manager.get_mouse_pos()
    return int(pos[0]), int(pos[1])


def _pointer_event_pos(owner: "UrsinaApp") -> tuple[int, int]:
    """Virtual HUD pixels for sidebar split drags; otherwise engine routing coords."""
    if _sidebar_split_drag_active(owner):
        return _virtual_screen_pos(owner)
    pos, _kind, _hit, _wx, _wy = _engine_screen_pos_for_pointer(owner)
    return pos


def _queue_pointer_motion_event(owner: "UrsinaApp") -> None:
    """Building placement needs update_preview() via MOUSEMOTION before MOUSEDOWN sets preview_valid."""
    pos = _pointer_event_pos(owner)
    owner._last_engine_screen_pos = pos
    # Ursina: expose left-button hold state so UI sliders only drag while LMB is down.
    try:
        lmb = 1 if bool(mouse.left) else 0
    except Exception:
        lmb = 0
    buttons = (lmb, 1 if bool(getattr(mouse, "right", False)) else 0, 0)
    owner.input_manager.queue_event(
        InputEvent(type="MOUSEMOTION", pos=pos, key=None, buttons=buttons)
    )


def _handle_ursina_input(owner: "UrsinaApp", key: str) -> None:
    # WK21: F12 — full Ursina window (3D + UI overlay) → docs/screenshots/
    if str(key).lower() == "f12":
        from ursina import application

        path = save_ursina_window_screenshot(application.base)
        if path and hasattr(owner.engine, "hud") and owner.engine.hud:
            import os as _os

            owner.engine.hud.add_message(
                f"Screenshot: {_os.path.basename(str(path))}",
                (100, 200, 255),
            )
        return
    if key == "left mouse down":
        # WK61-R11 BUG-005: capture sidebar split handle before deferred world MOUSEDOWN.
        vpos = _virtual_screen_pos(owner)
        hud = getattr(owner.engine, "hud", None)
        if hud is not None and hasattr(hud, "handle_sidebar_split_pointer_down"):
            try:
                hud.handle_sidebar_split_pointer_down(vpos, owner.engine.get_game_state())
            except Exception:
                pass
        # Process click on next update() after motion, so BuildingMenu.preview_valid is current.
        owner._pending_lmb = True
        return
    if key == "left mouse up":
        pos = _virtual_screen_pos(owner) if _sidebar_split_drag_active(owner) else owner._last_engine_screen_pos
        owner.input_manager.queue_event(InputEvent(type="MOUSEUP", button=1, pos=pos, key=None))
        return
    _ks = str(key).strip().lower()
    if not _is_chat_active(owner):
        if _ks == 'home':
            owner._reset_camera_to_default()
            return
        if _ks == 'l':
            owner._toggle_camera_lock()
            return
        if _ks == 'u':
            owner._toggle_underground_camera()
            return
    # WK52 R12: Route wheel to left menus before queuing — MOUSEMOTION may map pointer to
    # world-relative coords while building/hero menus use virtual framebuffer pixels only.
    if _ks in ("scroll up", "scroll down"):
        _wy = 1 if _ks == "scroll up" else -1
        _eng = owner.engine
        _hud = getattr(_eng, "hud", None)
        if _hud is not None:
            try:
                _mx = owner.input_manager.get_mouse_pos()
            except Exception:
                _mx = (0, 0)
            if _hud.handle_menu_scroll(tuple(_mx), int(_wy), _eng.get_game_state(), getattr(_eng, "building_panel", None)):
                return
    # WK22 SPRINT-BUG-004: forward keyboard / wheel to engine (was dropped by early return).
    evt = ursina_key_to_input_event(key)
    if evt is not None:
        owner.input_manager.queue_event(evt)
