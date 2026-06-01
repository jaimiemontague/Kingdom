"""WK113: camera-control cluster extracted from ursina_app.py (owner-arg pure-move,
WK87-92/WK104-105 pattern). UrsinaApp keeps thin delegating wrappers; these functions
take the app instance as ``owner``. Byte-faithful move — no behavior change."""
from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

import config
from ursina import EditorCamera, Vec2, Vec3, camera

from game.graphics.ursina_renderer import SCALE, sim_px_to_world_xz

if TYPE_CHECKING:  # avoid a runtime import cycle; UrsinaApp imports THIS module (lazily)
    from game.graphics.ursina_app import UrsinaApp  # noqa: F401

# WK57/58: Zone-specific fog color hints
_ZONE_FOG_COLORS: dict[str, tuple[float, float, float]] = {
    "darkwood": (0.35, 0.55, 0.35),       # Greenish forest mist
    "mountains": (0.60, 0.70, 0.85),       # Cool blue mountain haze
    "canyon_land": (0.75, 0.60, 0.50),      # Warm reddish canyon dust
    "castle_town": (0.53, 0.72, 0.88),     # Default sky blue
}
_DEFAULT_FOG_COLOR: tuple[float, float, float] = (0.53, 0.72, 0.88)


def _setup_ursina_camera_for_castle(owner: "UrsinaApp") -> None:
    """Frame castle + surrounding tiles (PM WK20); do not sync 2D engine camera when 3D pans.

    WK32: **EditorCamera** (orbit/pan) is default-on for model viewer parity.
    ``KINGDOM_URSINA_EDITORCAMERA=0`` keeps the legacy world-space camera as a fallback.
    The EditorCamera pivot sits on the castle floor point, while the starting world pose is
    derived from the known-good legacy ``look_at`` framing.
    """
    castle = next(
        (
            b
            for b in owner.engine.buildings
            if getattr(b, "building_type", "") == "castle" and getattr(b, "hp", 1) > 0
        ),
        None,
    )
    if castle is not None:
        cx, cz = sim_px_to_world_xz(float(castle.center_x), float(castle.center_y))
    else:
        cx, cz = owner._map_center_xz

    camera.fov = 42
    span = 58.0
    # WK30 debug: when the prefab-test layout is active, frame the castle + prefab
    # row. Optional ``KINGDOM_URSINA_CAM_TOPDOWN=1`` to switch to a top-down shot.
    if os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1":
        cx += 10.5  # midpoint between castle center and east end of test row
        span = 32.0

    # WK32 debug: allow deterministic close oblique captures by focusing a single building.
    # Apply *after* the prefab-test layout default framing so focus can override it.
    focus_type = os.environ.get("KINGDOM_URSINA_CAM_FOCUS_BUILDING_TYPE", "").strip().lower()
    if focus_type:
        def _matches_focus(bt) -> bool:
            raw = bt
            try:
                s = str(raw or "").strip().lower()
            except Exception:
                s = ""
            if s == focus_type:
                return True
            # Accept enum-ish strings like "BuildingType.INN" or "inn_v2".
            if s.endswith(f".{focus_type}") or s.endswith(f"_{focus_type}") or s.endswith(focus_type):
                return True
            try:
                name = str(getattr(raw, "name", "") or "").strip().lower()
                if name == focus_type:
                    return True
            except Exception:
                pass
            return False

        target_b = next(
            (
                b
                for b in getattr(owner.engine, "buildings", [])
                if _matches_focus(getattr(b, "building_type", ""))
                and getattr(b, "hp", 1) > 0
            ),
            None,
        )
        if target_b is not None:
            cx, cz = sim_px_to_world_xz(float(target_b.center_x), float(target_b.center_y))
            try:
                span = float(os.environ.get("KINGDOM_URSINA_CAM_FOCUS_SPAN", "") or span)
            except Exception:
                pass
            print(
                f"[ursina-camera] focus={focus_type} cx={cx:.2f} cz={cz:.2f} span={span:.2f}",
                flush=True,
            )

    hfov = math.radians(float(camera.fov))
    d = (span * 0.5) / max(1e-6, math.tan(hfov * 0.5))
    elev = d * 0.8
    back = d

    # Perspective FOV that matches engine.zoom==default_zoom (single source of truth: engine.zoom).
    owner._ursina_reference_fov = float(camera.fov)

    editor_camera_env = os.environ.get("KINGDOM_URSINA_EDITORCAMERA", "").strip().lower()
    use_editor_camera = editor_camera_env not in ("0", "false", "no", "off")
    if not use_editor_camera:
        owner._editor_camera = None
        if os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1":
            if os.environ.get("KINGDOM_URSINA_CAM_TOPDOWN") == "1":
                camera.position = Vec3(cx, d * 1.6, cz)
                camera.look_at(Vec3(cx, 0, cz))
            else:
                # Deterministic oblique shot with optional yaw/pitch overrides.
                try:
                    yaw_deg = float(os.environ.get("KINGDOM_URSINA_CAM_YAW", "") or 0.0)
                except Exception:
                    yaw_deg = 0.0
                try:
                    pitch_mul = float(os.environ.get("KINGDOM_URSINA_CAM_PITCH_MUL", "") or 1.0)
                except Exception:
                    pitch_mul = 1.0
                try:
                    height_mul = float(os.environ.get("KINGDOM_URSINA_CAM_HEIGHT_MUL", "") or 0.85)
                except Exception:
                    height_mul = 0.85
                yaw_rad = math.radians(yaw_deg)
                back_mul = 0.7
                by = d * height_mul * max(0.0, pitch_mul)
                bx = math.sin(yaw_rad) * d * back_mul
                bz = math.cos(yaw_rad) * d * back_mul
                camera.position = Vec3(cx + bx, by, cz - bz)
                camera.look_at(Vec3(cx, 0, cz))
        else:
            camera.position = Vec3(cx, elev, cz - back)
            camera.look_at(Vec3(cx, 0, cz))
        owner._default_cam_state = {
            'cam_position': Vec3(camera.position),
            'cam_rotation': Vec3(camera.rotation),
            'cam_world_position': Vec3(camera.world_position),
        }
        owner._camera_orbit_locked = False
        return

    target = Vec3(cx, 0.0, cz)
    debug_layout = os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT") == "1"
    rig_rotation: Vec3 | None = None
    rig_world_position = Vec3(cx, elev, cz - back)
    if not debug_layout:
        # Derive the initial rig rotation from the known-good legacy framing, then parent the
        # camera under EditorCamera for mouse orbit/pan. This avoids sign/axis drift between
        # Ursina's camera look_at and EditorCamera's pivot transform.
        camera.position = rig_world_position
        camera.look_at(target)
        rig_rotation = Vec3(camera.rotation)

    # EditorCamera: pivot on the castle floor point; the camera keeps the centered legacy
    # world position after the rig rotation is applied.
    ec = EditorCamera(
        zoom_speed=0.0,
        rotation_speed=200.0,
        pan_speed=Vec2(5, 5),
        ignore_scroll_on_ui=True,
    )
    ec.position = target
    if debug_layout:
        # Debug layout: fixed rig pitch (no look_at — avoids fighting ec.rotation for prefab shots).
        if os.environ.get("KINGDOM_URSINA_CAM_TOPDOWN") == "1":
            camera.position = Vec3(0.0, d * 1.6, -d * 0.02)
            ec.rotation = Vec3(89.0, 0.0, 0.0)
        else:
            cam_dist = d
            try:
                cam_dist = float(os.environ.get("KINGDOM_URSINA_CAM_DIST", "") or cam_dist)
            except Exception:
                cam_dist = d
            camera.position = Vec3(0.0, cam_dist * 0.85, -cam_dist * 0.7)
            try:
                pitch = float(os.environ.get("KINGDOM_URSINA_CAM_PITCH", "") or 40.0)
            except Exception:
                pitch = 40.0
            try:
                yaw = float(os.environ.get("KINGDOM_URSINA_CAM_YAW", "") or 0.0)
            except Exception:
                yaw = 0.0
            ec.rotation = Vec3(pitch, yaw, 0.0)
    else:
        camera.rotation = Vec3(0.0, 0.0, 0.0)
        if rig_rotation is not None:
            ec.rotation = rig_rotation
        camera.world_position = rig_world_position
    # EditorCamera.__init__ snapshots camera.editor_position before parenting; on_enable can
    # leave stale state. Sync so orbit/pivot matches castle framing.
    try:
        camera.editor_position = camera.position
    except Exception:
        pass
    ec.target_z = camera.z
    owner._editor_camera = ec
    owner._default_cam_state = {
        'ec_position': Vec3(ec.position),
        'ec_rotation': Vec3(ec.rotation),
        'cam_position': Vec3(camera.position),
        'cam_world_position': Vec3(camera.world_position),
        'target_z': ec.target_z,
    }
    owner._camera_orbit_locked = False


def _recenter_editor_camera_to_sim_xy(owner: "UrsinaApp", sim_x: float, sim_y: float) -> None:
    """WK51: move EditorCamera pivot to follow recall / camera snap (sim pixel coords)."""
    wx, wz = sim_px_to_world_xz(float(sim_x), float(sim_y))
    ec = getattr(owner, "_editor_camera", None)
    if ec is not None:
        ec.position = Vec3(wx, 0.0, wz)


def _reset_camera_to_default(owner: "UrsinaApp") -> None:
    state = getattr(owner, '_default_cam_state', None)
    if state is None:
        return

    if owner._camera_orbit_locked:
        owner._camera_orbit_locked = False
        ec = getattr(owner, '_editor_camera', None)
        if ec is not None:
            ec.rotation_speed = 200.0

    ec = getattr(owner, '_editor_camera', None)
    if ec is not None and state.get('ec_position') is not None:
        ec.position = Vec3(state['ec_position'])
        ec.rotation = Vec3(state['ec_rotation'])
        camera.position = Vec3(state['cam_position'])
        camera.world_position = Vec3(state['cam_world_position'])
        ec.target_z = state['target_z']
        try:
            camera.editor_position = camera.position
        except Exception:
            pass
    else:
        camera.position = Vec3(state['cam_position'])
        camera.world_position = Vec3(state['cam_world_position'])
        rot = state.get('cam_rotation')
        if rot is not None:
            camera.rotation = Vec3(rot)

    owner.engine.zoom = float(getattr(owner.engine, 'default_zoom', 1.0))
    _sync_ursina_camera_fov_from_zoom(owner)

    hud = getattr(owner.engine, 'hud', None)
    if hud:
        hud.add_message("Camera reset", (100, 200, 255))


def _toggle_camera_lock(owner: "UrsinaApp") -> None:
    owner._camera_orbit_locked = not getattr(owner, '_camera_orbit_locked', False)
    ec = getattr(owner, '_editor_camera', None)
    if ec is not None:
        ec.rotation_speed = 0.0 if owner._camera_orbit_locked else 200.0
    hud = getattr(owner.engine, 'hud', None)
    if hud:
        label = "Camera Lock: ON" if owner._camera_orbit_locked else "Camera Lock: OFF"
        hud.add_message(label, (100, 200, 255))


def _toggle_underground_camera(owner: "UrsinaApp") -> None:
    """WK57 Wave 4: Toggle camera between surface (layer 0) and underground (layer -1)."""
    if owner._camera_transitioning:
        return  # ignore while already transitioning
    if owner._camera_active_layer == 0:
        # Descend to underground
        from config import UNDERGROUND_DEPTH
        target_y = -(UNDERGROUND_DEPTH - 3.0)  # ~-7.0, above cave floor
        begin_camera_underground_transition(owner, target_y)
        print("Camera: Underground", flush=True)
        hud = getattr(owner.engine, 'hud', None)
        if hud:
            hud.add_message("Camera: Underground", (100, 200, 255))
    else:
        # Ascend to surface
        begin_camera_surface_transition(owner)
        print("Camera: Surface", flush=True)
        hud = getattr(owner.engine, 'hud', None)
        if hud:
            hud.add_message("Camera: Surface", (100, 200, 255))


def _sync_ursina_camera_fov_from_zoom(owner: "UrsinaApp") -> None:
    """Keep perspective FOV tied to engine.zoom so wheel, +/-, and Q/E match HUD/world mapping."""
    eng = owner.engine
    z = float(eng.zoom if eng.zoom else 1.0) / float(
        eng.default_zoom if getattr(eng, "default_zoom", None) else 1.0
    )
    z = max(z, 1e-6)
    ref = float(owner._ursina_reference_fov)
    camera.fov = max(8.0, min(95.0, ref / z))


def update_zone_fog_color(owner: "UrsinaApp", camera_world_x: float, camera_world_z: float) -> None:
    """Lerp atmospheric fog color toward the zone under the camera."""
    fog = owner._atmo_fog
    if fog is None:
        return
    try:
        from game.world_zones import get_zone
    except Exception:
        return

    # Convert camera world position to tile coords
    tile_x = int(camera_world_x * SCALE / float(config.TILE_SIZE))
    tile_z = int(-camera_world_z * SCALE / float(config.TILE_SIZE))

    # Castle center in tile coords for zone lookup
    castle_cx = int(config.MAP_WIDTH) // 2
    castle_cy = int(config.MAP_HEIGHT) // 2
    try:
        castle = next(
            (b for b in owner.engine.buildings
             if getattr(b, "building_type", "") == "castle" and getattr(b, "hp", 1) > 0),
            None,
        )
        if castle is not None:
            castle_cx = int(getattr(castle, "grid_x", castle_cx)) + int(getattr(castle, "size", (1, 1))[0]) // 2
            castle_cy = int(getattr(castle, "grid_y", castle_cy)) + int(getattr(castle, "size", (1, 1))[1]) // 2
    except Exception:
        pass

    zone = get_zone(tile_x, tile_z, castle_cx, castle_cy)
    zone_id = getattr(zone, "zone_id", None) if zone is not None else None
    target = _ZONE_FOG_COLORS.get(zone_id, _DEFAULT_FOG_COLOR) if zone_id else _DEFAULT_FOG_COLOR
    owner._zone_fog_target = target

    # Lerp current color toward target for smooth transition
    cr, cg, cb = owner._zone_fog_current
    tr, tg, tb = owner._zone_fog_target
    lerp_speed = 0.02  # per-frame lerp factor — gradual over ~50 frames
    nr = cr + (tr - cr) * lerp_speed
    ng = cg + (tg - cg) * lerp_speed
    nb = cb + (tb - cb) * lerp_speed
    owner._zone_fog_current = (nr, ng, nb)

    # Apply only when the delta is perceptible (avoid per-frame setColor thrash)
    if abs(nr - cr) > 0.001 or abs(ng - cg) > 0.001 or abs(nb - cb) > 0.001:
        try:
            fog.setColor(nr, ng, nb, 1.0)
        except Exception:
            pass


def begin_camera_underground_transition(owner: "UrsinaApp", target_y: float) -> None:
    """Start smooth camera descent to underground level."""
    from config import UNDERGROUND_CAMERA_TRANSITION_SPEED
    owner._camera_surface_y = camera.y
    owner._camera_transition_target_y = target_y
    owner._camera_transition_speed = UNDERGROUND_CAMERA_TRANSITION_SPEED
    owner._camera_transitioning = True
    owner._camera_active_layer = -1


def begin_camera_surface_transition(owner: "UrsinaApp") -> None:
    """Start smooth camera ascent back to surface."""
    from config import UNDERGROUND_CAMERA_TRANSITION_SPEED
    if owner._camera_surface_y is not None:
        owner._camera_transition_target_y = owner._camera_surface_y
    else:
        owner._camera_transition_target_y = 30.0  # reasonable default
    owner._camera_transition_speed = UNDERGROUND_CAMERA_TRANSITION_SPEED
    owner._camera_transitioning = True
    owner._camera_active_layer = 0
