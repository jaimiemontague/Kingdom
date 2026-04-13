"""
Translates the GameEngine simulation state into Ursina 3D entities.

Perspective view: floor plane is X/Z (Y up). Simulation pixels (x, y) map to
(world_x, world_z) with world_z = -px_y / SCALE so screen-north stays intuitive
(PM WK19 decision).

v1.5 Sprint 1.2 (Agent 03): Terrain is built from discrete 3D meshes under
``assets/models/environment/`` (grass/path/water tint + tree/rock props), parented
under one root Entity — no TileSpriteLibrary bake or terrain atlas.

Most buildings use BuildingSpriteLibrary on a single billboard quad; **castle**, **house**,
and **lair** use static 3D meshes from ``assets/models/environment/`` (v1.5 Sprint 2.1).
Units use pixel-art billboards (Hero/Enemy/Worker sprite libraries).

v1.5 Sprint 1.2 (Agent 09): Scene lighting (AmbientLight + shadow-casting
DirectionalLight) is created in ``UrsinaRenderer.__init__`` so untextured 3D
terrain/props read with simple flat-shaded dimensionality.
"""
from __future__ import annotations

import time
import zlib
from pathlib import Path

import pygame
import config
from ursina import Entity, Vec2, Vec3, color, Text, scene
from ursina.lights import AmbientLight, DirectionalLight
from ursina.shaders import lit_with_shadows_shader, unlit_shader

from game.graphics.animation import AnimationClip
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.vfx import get_projectile_billboard_surface
from game.graphics.worker_sprites import WorkerSpriteLibrary
from game.world import TileType, Visibility

# Fallback tints when a texture is missing
COLOR_HERO = color.azure
COLOR_ENEMY = color.red
COLOR_PEASANT = color.orange
COLOR_GUARD = color.yellow
COLOR_BUILDING = color.light_gray
COLOR_CASTLE = color.gold
COLOR_LAIR = color.brown

# 1 world unit along the floor == 1 tile == 32 px (unchanged from ortho MVP)
SCALE = 32.0

# v1.5 Sprint 1.2: uniform scale for Kenney OBJ tiles (1×1 plane ≈ one sim tile).
TERRAIN_SCALE_MULTIPLIER = 1.0
# Props sit on the same grid; tune if authored mesh bounds drift.
TREE_SCALE_MULTIPLIER = 1.15
ROCK_SCALE_MULTIPLIER = 0.42
# Grass tiles use organic scatter doodads on the base plane, not full-tile voxels.
GRASS_SCATTER_SCALE_MULTIPLIER = 0.52

# Vertical extents (world units), from Agent 09 volumetric mapping table
H_CASTLE = 2.2
H_BUILDING_3X3 = 1.6
H_BUILDING_2X2 = 1.4
H_BUILDING_1X1 = 0.9
H_LAIR = 1.0

# v1.5 Sprint 2.1 (Agent 09): XZ inset so 1×1 houses sit side-by-side; castle/lair
# fill most of the sim footprint (matches BUILDING_SIZES × TILE_SIZE / SCALE).
BUILDING_3D_HOUSE_XZ_INSET = 0.88
BUILDING_3D_CASTLE_XZ_INSET = 0.98
BUILDING_3D_LAIR_XZ_INSET = 0.94

# Pixel billboard height in world units (32px sprite read at map scale)
UNIT_BILLBOARD_SCALE = 0.62

# Stable bridge keys — never use id(surface) alone for multi-megapixel sheets (see terrain_texture_bridge).
_FOG_TEX_KEY = "kingdom_ursina_fog_overlay"

ENEMY_SCALE = 0.5
PEASANT_SCALE = 0.465
GUARD_SCALE_XZ = 0.5
GUARD_SCALE_Y = 0.7

# Ranged VFX billboards — keep smaller than hero sprites (~UNIT_BILLBOARD_SCALE 0.62)
PROJECTILE_BILLBOARD_SCALE = 0.1


def sim_px_to_world_xz(px_x: float, px_y: float) -> tuple[float, float]:
    """Map sim pixel coords to the X/Z floor (Y-up world)."""
    return px_x / SCALE, -px_y / SCALE


def px_to_world(px_x: float, px_y: float) -> tuple[float, float]:
    """Backward-compatible name: returns (world_x, world_z) for the floor plane."""
    return sim_px_to_world_xz(px_x, px_y)


_ENV_MODEL_DIR = Path(__file__).resolve().parents[2] / "assets" / "models" / "environment"


def _environment_model_path(kind: str) -> str:
    """Resolve ``assets/models/environment/<kind>.{glb,gltf,obj}`` for Ursina ``Entity(model=...)``."""
    for ext in (".glb", ".gltf", ".obj"):
        p = _ENV_MODEL_DIR / f"{kind}{ext}"
        if p.is_file():
            return f"assets/models/environment/{kind}{ext}"
    return "cube"


def _grass_scatter_jitter(tx: int, ty: int) -> tuple[float, float, float]:
    """Deterministic XZ offset + yaw (degrees) so grass doodads read as scattered foliage."""
    h = (tx * 92837111 ^ ty * 689287499) & 0xFFFFFFFF
    jx = ((h & 0xFFFF) / 65535.0 - 0.5) * 0.38
    jz = (((h >> 16) & 0xFFFF) / 65535.0 - 0.5) * 0.38
    yaw = float((tx * 127 + ty * 331) % 360)
    return jx, jz, yaw


def _building_type_str(bt) -> str:
    if bt is None:
        return ""
    return str(getattr(bt, "value", bt) or "")


def _footprint_tiles(building_type) -> tuple[int, int]:
    key = getattr(building_type, "value", building_type)
    return config.BUILDING_SIZES.get(key, (2, 2))


def _is_3d_mesh_building(bts: str, building) -> bool:
    """Castle, peasant house, and monster lairs render as lit 3D meshes (not sprite billboards)."""
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        return True
    return bts in ("castle", "house")


def _mesh_kind_for_building(bts: str, building) -> str:
    if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
        return "lair"
    if bts == "castle":
        return "castle"
    return "house"


def _building_3d_origin_y(model_path: str, sy: float) -> float:
    """Ursina ``cube`` is centered on its local origin; scale ``sy`` is the world height."""
    if model_path == "cube":
        return sy * 0.5
    # Authored meshes: assume pivot near ground (common for env exports); adjust per-asset if needed.
    return 0.0


def _footprint_scale_3d(
    mesh_kind: str, fx: float, fz: float, hy: float
) -> tuple[float, float, float]:
    """Fill sim footprint in XZ with small insets so adjacent 1×1 houses do not overlap meshes."""
    ix = iz = 1.0
    if mesh_kind == "house":
        ix = iz = BUILDING_3D_HOUSE_XZ_INSET
    elif mesh_kind == "castle":
        ix = iz = BUILDING_3D_CASTLE_XZ_INSET
    elif mesh_kind == "lair":
        ix = iz = BUILDING_3D_LAIR_XZ_INSET
    return (fx * ix, hy, fz * iz)


def _building_height_y(
    tw: int, th: int, building_type, is_lair: bool, is_castle: bool
) -> float:
    if is_castle:
        return H_CASTLE
    if is_lair:
        return H_LAIR
    if tw >= 3 and th >= 3:
        return H_BUILDING_3X3
    if tw == 1 and th == 1:
        return H_BUILDING_1X1
    return H_BUILDING_2X2


def _frame_index_for_clip(clip: AnimationClip, elapsed: float) -> tuple[int, bool]:
    """Match ``AnimationPlayer`` timing: non-looping finishes after n frame-times."""
    n = len(clip.frames)
    ft = clip.frame_time_sec
    if n == 0:
        return 0, True
    if ft <= 0:
        return 0, False
    if clip.loop:
        cycle = n * ft
        if cycle <= 0:
            return 0, False
        t = elapsed % cycle
        idx = int(t / ft) % n
        return idx, False
    steps = int(elapsed / ft)
    if steps >= n:
        return n - 1, True
    return steps, False


def _hero_base_clip(hero) -> str:
    if bool(getattr(hero, "is_inside_building", False)):
        return "inside"
    state = getattr(hero, "state", None)
    state_name = str(getattr(state, "name", state))
    if state_name in ("MOVING", "RETREATING"):
        return "walk"
    return "idle"


def _enemy_base_clip(enemy) -> str:
    state = getattr(enemy, "state", None)
    state_name = str(getattr(state, "name", state))
    return "walk" if state_name == "MOVING" else "idle"


def _worker_idle_surface(worker_type: str):
    wt = str(worker_type or "peasant").lower()
    clips = WorkerSpriteLibrary.clips_for(wt)
    return clips["idle"].frames[0]


def _visibility_signature(world) -> int:
    """Cheap checksum so we only rebuild the fog texture when the grid changes.

    WK22 Agent-10 perf note: this is O(W*H) — ~22,500 tiles at default map size.
    Callers should gate on ``engine._fog_revision`` to avoid running this every frame.
    """
    h = zlib.crc32(b"")
    for y in range(world.height):
        h = zlib.crc32(bytes(world.visibility[y]), h)
    return h & 0xFFFFFFFF


class UrsinaRenderer:
    def __init__(self, engine):
        self.engine = engine

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}

        # v1.5: parent Entity for per-tile 3D terrain meshes (see _build_3d_terrain).
        self._terrain_entity: Entity | None = None

        # Fog-of-war overlay quad (WK22): matches pygame render_fog tints per visibility tile.
        self._fog_entity: Entity | None = None
        self._fog_full_surf: pygame.Surface | None = None
        # RGBA tile buffer reused for fog rebuilds (WK22 R3 perf: avoid 22k pygame.set_at calls).
        self._fog_tile_buf: bytearray | None = None

        # Status Text UI (2D overlay, not affected by world camera)
        self.status_text = Text(
            text="Kingdom Sim - Ursina Viewer",
            position=(-0.85, 0.47),
            scale=1.2,
            color=color.black,
            background=True,
        )

        # WK22 R3: per-sim-object billboard animation (wall clock; consumes _render_anim_trigger).
        self._unit_anim_state: dict[int, dict] = {}
        # WK23: single shared GPU texture for VFX projectiles (arrow-shaped, not yellow fallback).
        self._projectile_tex = None

        # --- v1.5: base lighting for 3D meshes (flat-shaded, optional shadows) ---
        self._directional_light = None
        self._shadow_bounds_initialized = False
        self._setup_scene_lighting()

    def _setup_scene_lighting(self) -> None:
        """Dim gray-blue ambient + warm directional sun; directional casts shadow maps when enabled.

        Billboards keep unlit_shader + shadow-mask hide; lit 3D terrain/props use default_shader
        from UrsinaApp (lit_with_shadows when URSINA_DIRECTIONAL_SHADOWS is True).
        """
        try:
            from ursina import color as ucolor

            world = self.engine.world
            tw, th = int(world.width), int(world.height)
            ts = float(config.TILE_SIZE)
            cx_px = tw * ts * 0.5
            cy_px = th * ts * 0.5
            cx, cz = sim_px_to_world_xz(cx_px, cy_px)

            # Slightly cool ambient so untextured meshes are not silhouette-black.
            AmbientLight(parent=scene, color=ucolor.rgba(0.34, 0.38, 0.44, 1.0))

            _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
            sm = int(getattr(config, "URSINA_SHADOW_MAP_SIZE", 768))
            sm = max(256, min(2048, sm))

            dl = DirectionalLight(
                parent=scene,
                shadows=_shadows,
                shadow_map_resolution=Vec2(sm, sm),
                color=ucolor.rgba(0.98, 0.95, 0.88, 1.0),
            )
            # Downward angled sun toward map center (same framing as prior UrsinaApp setup).
            dl.position = Vec3(cx + 55.0, 95.0, cz + 40.0)
            dl.look_at(Vec3(cx, 0.0, cz))
            self._directional_light = dl
        except Exception:
            self._directional_light = None

    def _unit_anim_surface(
        self,
        obj_id: int,
        entity,
        clips: dict[str, AnimationClip],
        base_clip_fn,
        cache_prefix: str,
        class_key: str,
    ) -> tuple[pygame.Surface, tuple]:
        """Pick hero/enemy frame from clips using triggers + base locomotion; time-based playback."""
        # Prefer snapshot from engine (see _update_render_animations): pygame clears _render_anim_trigger first.
        trigger = getattr(entity, "_ursina_anim_trigger", None) or getattr(
            entity, "_render_anim_trigger", None
        )
        if trigger:
            tname = str(trigger)
            if tname in clips:
                setattr(entity, "_ursina_anim_trigger", None)
                setattr(entity, "_render_anim_trigger", None)
                base = base_clip_fn(entity)
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": time.time(),
                    "base": base,
                    "oneshot": not clips[tname].loop,
                }
            else:
                setattr(entity, "_ursina_anim_trigger", None)
                setattr(entity, "_render_anim_trigger", None)

        base = base_clip_fn(entity)
        st = self._unit_anim_state.get(obj_id)
        if st is None:
            self._unit_anim_state[obj_id] = {
                "clip": base,
                "t0": time.time(),
                "base": base,
                "oneshot": False,
            }
            st = self._unit_anim_state[obj_id]
        else:
            st["base"] = base
            if st.get("oneshot"):
                oc = clips[st["clip"]]
                elapsed_done = time.time() - st["t0"]
                _i, finished = _frame_index_for_clip(oc, elapsed_done)
                if finished:
                    st["clip"] = st["base"]
                    st["t0"] = time.time()
                    st["oneshot"] = False
            if not st.get("oneshot"):
                if st["clip"] != base:
                    st["clip"] = base
                    st["t0"] = time.time()

        clip_name = st["clip"]
        clip = clips[clip_name]
        elapsed = time.time() - st["t0"]
        idx, _fin = _frame_index_for_clip(clip, elapsed)
        surf = clip.frames[idx]
        cache_key = (cache_prefix, "anim", class_key, clip_name, idx, int(config.TILE_SIZE))
        return surf, cache_key

    def _ensure_fog_overlay(self) -> None:
        """Darken unexplored / non-visible tiles in 3D (matches 2D render_fog semantics).

        WK22: Rebuild only when ``engine._fog_revision`` advances (revealer crossed a tile).

        WK23 follow-up: removed throttle; removed CRC skip path; advance ``_fog_revision_seen`` only
        after a successful GPU upload; fog quad uses ``set_depth_test(False)`` so the overlay tints
        consistently (no depth rejects vs billboards).
        """
        if self._terrain_entity is None:
            return

        world = self.engine.world

        engine_rev = getattr(self.engine, "_fog_revision", 0)
        my_rev = getattr(self, "_fog_revision_seen", -1)
        if engine_rev == my_rev and self._fog_entity is not None:
            return

        tw, th = int(world.width), int(world.height)

        # WK22 Agent-10 perf: render fog at TILE resolution (1 px per tile)
        # instead of pixel resolution (TILE_SIZE px per tile).  This shrinks
        # the surface from 4800×4800 (92 MB) to 150×150 (90 KB) — a ~1000×
        # reduction in tobytes / PIL / GPU upload cost.  The GPU upscales
        # the texture to cover the terrain quad; nearest-neighbor filtering
        # keeps hard tile edges.
        #
        # WK22 R3 bug hunt: building the fog surface with set_at() per tile
        # costs tens of ms (Python call overhead) and caused rhythmic hitches
        # whenever visibility changed.  Fill a packed RGBA bytearray instead.
        need = tw * th * 4
        if self._fog_tile_buf is None or len(self._fog_tile_buf) != need:
            self._fog_tile_buf = bytearray(need)
        buf = self._fog_tile_buf
        row_unseen = b"\x00\x00\x00\xff" * tw
        for ty in range(th):
            buf[ty * tw * 4 : (ty + 1) * tw * 4] = row_unseen
        vis_b = b"\x00\x00\x00\x00"
        seen_b = b"\x00\x00\x00\xaa"  # 170 alpha — matches 2D fog "seen" tint
        # WK23 FIX: write rows in REVERSE sim-Y order so the texture's row-0
        # corresponds to map-south (sim_py == th*ts).  sim_px_to_world_xz negates
        # the Y axis (world_z = -py/SCALE), so map-south ends at world_z=0 (the
        # +Z edge of the quad after rotation_x=90°).  Without this reversal the
        # fog is mirrored North↔South and the lit circle tracks the wrong half of
        # the map relative to where heroes actually stand.
        for ty in range(th):
            row = world.visibility[ty]
            # Map sim row ty → buf row (th-1-ty) to flip N/S in texture space.
            buf_row = th - 1 - ty
            base = buf_row * tw * 4
            for tx in range(tw):
                st = row[tx]
                if st == Visibility.VISIBLE:
                    o = base + tx * 4
                    buf[o : o + 4] = vis_b
                elif st == Visibility.SEEN:
                    o = base + tx * 4
                    buf[o : o + 4] = seen_b

        surf = pygame.image.frombuffer(buf, (tw, th), "RGBA")
        self._fog_full_surf = surf

        ftex = TerrainTextureBridge.refresh_surface_texture(surf, cache_key=_FOG_TEX_KEY)
        if ftex is None:
            # Do not advance _fog_revision_seen — otherwise we never retry and fog stays stale.
            return

        ts = int(config.TILE_SIZE)
        # WK23 R1: Quad size + center MUST match _build_3d_terrain() map extent — any drift
        # misaligns fog vs terrain and makes FOW “slide” relative to heroes/units.
        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE
        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5
        wx, wz = sim_px_to_world_xz(cx_px, cy_px)

        from panda3d.core import TransparencyAttrib

        # SPRINT-BUG-008: keep fog well above the terrain quad.
        fog_y = float(getattr(config, "URSINA_FOG_QUAD_Y", 0.12))

        if self._fog_entity is None:
            self._fog_entity = Entity(
                model="quad",
                texture=ftex,
                scale=(w_world, d_world, 1),
                rotation=(90, 0, 0),
                position=(wx, fog_y, wz),
                color=color.white,
                double_sided=True,
            )
            if self._fog_entity.texture:
                self._fog_entity.texture.filtering = None
            self._fog_entity.texture_scale = Vec2(1, -1)
            self._fog_entity.texture_offset = Vec2(0, 1)
            self._fog_entity.setTransparency(TransparencyAttrib.M_alpha)
            self._fog_entity.set_depth_write(False)
            # Overlay must not depth-fail against billboards/terrain or FOW darkening desyncs visually.
            self._fog_entity.set_depth_test(False)
            self._fog_entity.shader = unlit_shader
            self._fog_entity.hide(0b0001)
            self._fog_entity.render_queue = 2
        else:
            self._fog_entity.texture = ftex
            self._fog_entity.position = (wx, fog_y, wz)
            self._fog_entity.scale = (w_world, d_world, 1)
            self._fog_entity.texture_scale = Vec2(1, -1)
            self._fog_entity.texture_offset = Vec2(0, 1)

        self._fog_revision_seen = engine_rev

    def _build_3d_terrain(self) -> None:
        """Per-tile path/water meshes + scatter grass doodads on a full-map base plane (v1.5 Sprint 1.2)."""
        if self._terrain_entity is not None:
            return

        world = self.engine.world
        tw, th = int(world.width), int(world.height)
        ts = int(config.TILE_SIZE)
        m = float(TERRAIN_SCALE_MULTIPLIER)
        grass_model = _environment_model_path("grass")
        path_model = _environment_model_path("path")
        rock_model = _environment_model_path("rock")
        tree_model = _environment_model_path("tree_pine")
        tm = m * float(TREE_SCALE_MULTIPLIER)
        rm = m * float(ROCK_SCALE_MULTIPLIER)
        g_sc = m * float(GRASS_SCATTER_SCALE_MULTIPLIER)

        root = Entity(name="terrain_3d_root")
        water_tint = color.rgb(0.24, 0.48, 0.82)

        # Cohesive green ground plane under the grid (organic scatter sits on y≈0 above this).
        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE
        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5
        base_wx, base_wz = sim_px_to_world_xz(cx_px, cy_px)
        Entity(
            parent=root,
            model="quad",
            color=color.rgb(0.2, 0.5, 0.2),
            scale=(w_world, d_world, 1),
            rotation=(90, 0, 0),
            position=(base_wx, -0.05, base_wz),
            collision=False,
            double_sided=True,
            shader=unlit_shader,
            add_to_scene_entities=False,
        )

        for ty in range(th):
            for tx in range(tw):
                tile = int(world.tiles[ty][tx])
                cx_px = tx * ts + ts * 0.5
                cy_px = ty * ts + ts * 0.5
                wx, wz = px_to_world(cx_px, cy_px)

                if tile == TileType.PATH:
                    Entity(
                        parent=root,
                        model=path_model,
                        position=(wx, 0.0, wz),
                        scale=(m, m, m),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                elif tile == TileType.WATER:
                    Entity(
                        parent=root,
                        model=grass_model,
                        position=(wx, 0.0, wz),
                        scale=(m, m, m),
                        color=water_tint,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )

                if tile == TileType.GRASS or tile == TileType.TREE:
                    jx, jz, yaw = _grass_scatter_jitter(tx, ty)
                    Entity(
                        parent=root,
                        model=grass_model,
                        position=(wx + jx, 0.0, wz + jz),
                        scale=(g_sc, g_sc, g_sc),
                        rotation=(0, yaw, 0),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )

                if tile == TileType.TREE:
                    Entity(
                        parent=root,
                        model=tree_model,
                        position=(wx, 0.0, wz),
                        scale=(tm, tm, tm),
                        color=color.white,
                        collision=False,
                        double_sided=True,
                        add_to_scene_entities=False,
                    )
                elif tile == TileType.GRASS:
                    h = (tx * 92837111 ^ ty * 689287499) & 0xFFFFFFFF
                    if h % 503 == 0:
                        Entity(
                            parent=root,
                            model=rock_model,
                            position=(wx, 0.0, wz),
                            scale=(rm, rm, rm),
                            color=color.white,
                            collision=False,
                            double_sided=True,
                            add_to_scene_entities=False,
                        )

        root.flattenStrong()
        self._terrain_entity = root

    @staticmethod
    def _apply_pixel_billboard_settings(ent: Entity) -> None:
        """Alpha-cutout sprites: discard transparent texels; sort/blend without black halos."""
        from panda3d.core import TransparencyAttrib

        ent.shader = sprite_unlit_shader
        ent.double_sided = True
        ent.setTransparency(TransparencyAttrib.M_alpha)
        ent.set_depth_write(False)
        ent.render_queue = 1
        # WK22 SPRINT-BUG-006: exclude alpha billboards from directional shadow pass (mask 0b0001).
        ent.hide(0b0001)

    @staticmethod
    def _sync_inside_hero_draw_layer(ent: Entity, is_inside: bool) -> None:
        """Stack order like a 2D top layer: same world position, drawn after buildings, no depth reject.

        When a hero uses the ``inside`` clip (bubble/circle), the quad must composite over the
        building façade pixels — not float in Y. Terrain/fog stay 0–2; inside heroes use queue 3.
        """
        want = bool(is_inside)
        if getattr(ent, "_ks_inside_layer", None) is want:
            return
        ent._ks_inside_layer = want
        if want:
            ent.render_queue = 3
            ent.set_depth_test(False)
        else:
            ent.render_queue = 1
            ent.set_depth_test(True)

    @staticmethod
    def _set_texture_if_changed(ent: Entity, tex) -> None:
        """Avoid model.setTexture every frame — Ursina's texture setter always reapplies (WK22 R3)."""
        if getattr(ent, "_texture", None) is tex:
            return
        ent.texture = tex

    @staticmethod
    def _set_shader_if_changed(ent: Entity, sh) -> None:
        """Avoid setShader + default_input churn every frame (major cost when hiring many heroes)."""
        if getattr(ent, "_shader", None) is sh:
            return
        ent.shader = sh

    @staticmethod
    def _sync_billboard_entity(
        ent: Entity,
        *,
        tex,
        tint_col,
        scale_xyz: tuple[float, float, float],
        pos_xyz: tuple[float, float, float],
        shader,
    ) -> None:
        """Position every frame; avoid re-setting billboard/scale/shader when unchanged (Ursina churn)."""
        UrsinaRenderer._set_texture_if_changed(ent, tex)
        ent.color = color.white if tex is not None else tint_col
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        if not getattr(ent, "_billboard", False):
            ent.billboard = True
        UrsinaRenderer._set_shader_if_changed(ent, shader)
        ent.position = pos_xyz

    def _get_or_create_entity(
        self,
        sim_obj,
        *,
        model="cube",
        col=color.white,
        scale=(1, 1, 1),
        rotation=(0, 0, 0),
        texture=None,
        billboard=False,
    ):
        obj_id = id(sim_obj)
        if obj_id not in self._entities:
            kw = dict(
                model=model,
                color=col,
                scale=scale,
                rotation=rotation,
                billboard=billboard,
            )
            if texture is not None:
                kw["texture"] = texture
            ent = Entity(**kw)
            if billboard:
                self._apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    @staticmethod
    def _apply_lit_3d_building_settings(ent: Entity) -> None:
        """Lit meshes use the same shader as world geometry (lit + shadows), not sprite_unlit."""
        from panda3d.core import TransparencyAttrib

        ent.billboard = False
        _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        ent.shader = lit_with_shadows_shader if _shadows else unlit_shader
        ent.double_sided = True
        ent.render_queue = 1
        ent.collision = False
        try:
            ent.setTransparency(TransparencyAttrib.M_none)
        except Exception:
            pass
        ent.set_depth_test(True)
        ent.set_depth_write(True)

    def _get_or_create_3d_building_entity(
        self, sim_obj, model_path: str, col
    ) -> tuple:
        """Replace a prior billboard entity for the same sim object if switching render mode."""
        import ursina as u

        obj_id = id(sim_obj)
        if obj_id in self._entities:
            ent = self._entities[obj_id]
            if getattr(ent, "_ks_building_mode", None) != "mesh_3d":
                u.destroy(ent)
                del self._entities[obj_id]
            elif getattr(ent, "_ks_mesh_model_path", None) != model_path:
                u.destroy(ent)
                del self._entities[obj_id]

        if obj_id not in self._entities:
            ent = Entity(
                model=model_path,
                color=col,
                collider=None,
                double_sided=True,
            )
            ent._ks_building_mode = "mesh_3d"
            ent._ks_mesh_model_path = model_path
            ent._ks_billboard_configured = False
            self._apply_lit_3d_building_settings(ent)
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    @staticmethod
    def _sync_3d_building_entity(
        ent: Entity,
        *,
        mesh_kind: str,
        model_path: str,
        wx: float,
        wz: float,
        fx: float,
        fz: float,
        hy: float,
        tint_col,
        state: str,
    ) -> None:
        """Position/scale lit mesh to footprint; sim-agnostic (render only)."""
        UrsinaRenderer._set_texture_if_changed(ent, None)
        scale_xyz = _footprint_scale_3d(mesh_kind, fx, fz, hy)
        if getattr(ent, "_ks_last_scale", None) != scale_xyz:
            ent.scale = scale_xyz
            ent._ks_last_scale = scale_xyz
        _sx, sy, _sz = scale_xyz
        oy = _building_3d_origin_y(model_path, sy)
        ent.position = (wx, oy, wz)
        _shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
        want_shader = lit_with_shadows_shader if _shadows else unlit_shader
        UrsinaRenderer._set_shader_if_changed(ent, want_shader)
        if state == "damaged":
            ent.color = color.rgb(0.78, 0.42, 0.42)
        elif state == "construction":
            ent.color = color.rgb(0.72, 0.72, 0.65)
        else:
            ent.color = tint_col

    def update(self):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        if (
            not self._shadow_bounds_initialized
            and self._directional_light is not None
        ):
            try:
                self._directional_light.update_bounds(scene)
            except Exception:
                pass
            self._shadow_bounds_initialized = True

        self._build_3d_terrain()
        self._ensure_fog_overlay()

        gs = self.engine.get_game_state()

        active_ids = set()

        # Buildings — billboard quads, except castle / house / lair (v1.5 Sprint 2.1: lit 3D meshes).
        for b in gs["buildings"]:
            bt_raw = getattr(b, "building_type", "") or ""
            bts = _building_type_str(bt_raw)
            is_castle = bts == "castle"
            is_lair = hasattr(b, "stash_gold")
            if is_castle:
                col = COLOR_CASTLE
            elif is_lair:
                col = COLOR_LAIR
            else:
                col = COLOR_BUILDING

            tw, th = _footprint_tiles(bt_raw)
            fx = b.width / SCALE
            fz = b.height / SCALE
            hy = _building_height_y(tw, th, bt_raw, is_lair, is_castle)

            state = "construction" if not getattr(b, "is_constructed", True) else "built"
            if getattr(b, "hp", 200) < getattr(b, "max_hp", 200) * 0.4:
                state = "damaged"

            wx, wz = sim_px_to_world_xz(b.x, b.y)

            if _is_3d_mesh_building(bts, b):
                mesh_kind = _mesh_kind_for_building(bts, b)
                model_path = _environment_model_path(mesh_kind)
                ent, obj_id = self._get_or_create_3d_building_entity(b, model_path, col)
                self._sync_3d_building_entity(
                    ent,
                    mesh_kind=mesh_kind,
                    model_path=model_path,
                    wx=wx,
                    wz=wz,
                    fx=fx,
                    fz=fz,
                    hy=hy,
                    tint_col=col,
                    state=state,
                )
                active_ids.add(obj_id)
                continue

            bw = max(1, int(b.width))
            bh = max(1, int(b.height))
            b_surf = BuildingSpriteLibrary.get(bts, state, size_px=(bw, bh))
            b_tex = (
                TerrainTextureBridge.surface_to_texture(
                    b_surf, cache_key=("bld", bts, state, bw, bh)
                )
                if b_surf
                else None
            )

            # Facade width ≈ larger footprint edge; one textured face (no cube "roof" duplicate).
            face_w = max(fx, fz)
            ent, obj_id = self._get_or_create_entity(
                b,
                model="quad",
                col=col,
                scale=(face_w, hy, 1),
                billboard=True,
            )
            if not getattr(ent, "_ks_billboard_configured", False):
                ent.model = "quad"
                ent.billboard = True
                self._apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            # Do not assign ent.model every frame — model_setter reloads the mesh (WK22 R2).
            ent.rotation = (0, 0, 0)
            self._sync_billboard_entity(
                ent,
                tex=b_tex if b_tex is not None else None,
                tint_col=col,
                scale_xyz=(face_w, hy, 1),
                pos_xyz=(wx, hy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Heroes — pixel billboards (WK22 R3: walk/idle/inside + attack/hurt from _render_anim_trigger)
        for h in gs["heroes"]:
            if not getattr(h, "is_alive", True):
                continue
            col = COLOR_HERO
            if HeroClass:
                hc = getattr(h, "hero_class", None)
                if hc == HeroClass.RANGER or str(hc).lower() == "ranger":
                    col = color.lime
                elif hc == HeroClass.WIZARD or str(hc).lower() == "wizard":
                    col = color.magenta
                elif hc == HeroClass.ROGUE or str(hc).lower() == "rogue":
                    col = color.violet

            hc_key = str(getattr(h, "hero_class", "warrior") or "warrior").lower()
            clips_h = HeroSpriteLibrary.clips_for(hc_key, size=int(config.TILE_SIZE))
            sy = UNIT_BILLBOARD_SCALE
            ent, obj_id = self._get_or_create_entity(
                h,
                model="quad",
                col=color.white,
                scale=(sy, sy, 1),
                texture=None,
                billboard=True,
            )
            hsurf, h_cache_key = self._unit_anim_surface(
                obj_id, h, clips_h, _hero_base_clip, "hero", hc_key
            )
            htex = TerrainTextureBridge.surface_to_texture(hsurf, cache_key=h_cache_key)
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            y_center = sy * 0.5
            self._sync_billboard_entity(
                ent,
                tex=htex,
                tint_col=col,
                scale_xyz=(sy, sy, 1),
                pos_xyz=(wx, y_center, wz),
                shader=sprite_unlit_shader,
            )
            # Layer compositing (not Y offset): draw after building billboards; skip depth so the
            # "inside" bubble paints over the same footprint as the façade.
            self._sync_inside_hero_draw_layer(ent, bool(getattr(h, "is_inside_building", False)))
            active_ids.add(obj_id)

        # Enemies — billboards (same animation contract as pygame EnemyRenderer)
        world = self.engine.world
        ts = float(config.TILE_SIZE)
        for e in gs["enemies"]:
            tx, ty = int(e.x / ts), int(e.y / ts)
            is_visible = True
            if 0 <= ty < world.height and 0 <= tx < world.width:
                is_visible = (world.visibility[ty][tx] == Visibility.VISIBLE)
            
            if not getattr(e, "is_alive", True) or not is_visible:
                continue
            s = ENEMY_SCALE
            col = COLOR_ENEMY
            et_key = str(getattr(e, "enemy_type", "goblin") or "goblin").lower()
            clips_e = EnemySpriteLibrary.clips_for(et_key, size=int(config.TILE_SIZE))
            ent, obj_id = self._get_or_create_entity(
                e,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=None,
                billboard=True,
            )
            esurf, e_cache_key = self._unit_anim_surface(
                obj_id, e, clips_e, _enemy_base_clip, "enemy", et_key
            )
            etex = TerrainTextureBridge.surface_to_texture(esurf, cache_key=e_cache_key)
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            self._sync_billboard_entity(
                ent,
                tex=etex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Peasants — billboards
        for p in gs["peasants"]:
            if not getattr(p, "is_alive", True):
                continue
            s = PEASANT_SCALE
            col = COLOR_PEASANT
            psurf = _worker_idle_surface("peasant")
            ptex = TerrainTextureBridge.surface_to_texture(
                psurf, cache_key=("worker_idle", "peasant", int(config.TILE_SIZE))
            )
            ent, obj_id = self._get_or_create_entity(
                p,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=ptex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            self._sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Guards — billboards
        for g in gs["guards"]:
            if not getattr(g, "is_alive", True):
                continue
            col = COLOR_GUARD
            gsurf = _worker_idle_surface("guard")
            gtex = TerrainTextureBridge.surface_to_texture(
                gsurf, cache_key=("worker_idle", "guard", int(config.TILE_SIZE))
            )
            sxz = GUARD_SCALE_XZ
            sy = GUARD_SCALE_Y
            ent, obj_id = self._get_or_create_entity(
                g,
                model="quad",
                col=color.white,
                scale=(sxz, sy, 1),
                texture=gtex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            self._sync_billboard_entity(
                ent,
                tex=gtex,
                tint_col=col,
                scale_xyz=(sxz, sy, 1),
                pos_xyz=(wx, sy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Tax Collectors — billboards (get_game_state may omit tax_collectors; fall back to engine singleton)
        _tc_list = gs.get("tax_collectors")
        if not _tc_list:
            _singleton = getattr(self.engine, "tax_collector", None)
            _tc_list = [_singleton] if _singleton is not None else []
        for tc in _tc_list:
            if not getattr(tc, "is_alive", True):
                continue
            col = COLOR_PEASANT
            tcsurf = _worker_idle_surface("tax_collector")
            tctex = TerrainTextureBridge.surface_to_texture(
                tcsurf, cache_key=("worker_idle", "tax_collector", int(config.TILE_SIZE))
            )
            s = PEASANT_SCALE
            ent, obj_id = self._get_or_create_entity(
                tc,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=tctex,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(tc.x, tc.y)
            self._sync_billboard_entity(
                ent,
                tex=tctex,
                tint_col=col,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Projectiles — VFX arrows as textured billboards (WK5 colors via get_projectile_billboard_surface)
        if self._projectile_tex is None:
            psurf = get_projectile_billboard_surface()
            self._projectile_tex = TerrainTextureBridge.surface_to_texture(
                psurf, cache_key=("ursina", "projectile_arrow_billboard_v1")
            )
        ptex = self._projectile_tex
        vfx = getattr(self.engine, "vfx_system", None)
        for proj in gs.get("projectiles") or (
            vfx.get_active_projectiles() if vfx is not None else []
        ):
            s = PROJECTILE_BILLBOARD_SCALE
            ent, obj_id = self._get_or_create_entity(
                proj,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=ptex,
                billboard=True,
            )
            if not getattr(ent, "_ks_billboard_configured", False):
                ent.model = "quad"
                ent.billboard = True
                self._apply_pixel_billboard_settings(ent)
                ent._ks_billboard_configured = True
            wx, wz = sim_px_to_world_xz(proj.x, proj.y)
            self._sync_billboard_entity(
                ent,
                tex=ptex,
                tint_col=color.white,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        heroes_alive = len([h for h in gs["heroes"] if getattr(h, "is_alive", True)])
        enemies_alive = len(gs["enemies"])
        status_text = (
            f"Gold: {gs['gold']}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(gs['buildings'])}"
        )
        if self.status_text.text != status_text:
            self.status_text.text = status_text

        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            self._unit_anim_state.pop(obj_id, None)
            ent = self._entities.pop(obj_id)
            import ursina

            ursina.destroy(ent)
