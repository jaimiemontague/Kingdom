"""
Translates the GameEngine simulation state into Ursina 3D entities.

Perspective view: floor plane is X/Z (Y up). Simulation pixels (x, y) map to
(world_x, world_z) with world_z = -px_y / SCALE so screen-north stays intuitive
(PM WK19 decision).

WK21: Terrain is startup-baked from TileSpriteLibrary into one floor quad.
Buildings use BuildingSpriteLibrary on a single billboard quad (not a textured
cube — avoids "two volumes" from facade + top face). Units use pixel-art
billboards (Hero/Enemy/Worker sprite libraries).
"""
from __future__ import annotations

import time
import zlib

import pygame
import config
from ursina import Entity, Vec2, color, Text
from ursina.shaders import unlit_shader

from game.graphics.animation import AnimationClip
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.tile_sprites import TileSpriteLibrary
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.worker_sprites import WorkerSpriteLibrary
from game.world import Visibility

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

# Vertical extents (world units), from Agent 09 volumetric mapping table
H_CASTLE = 2.2
H_BUILDING_3X3 = 1.6
H_BUILDING_2X2 = 1.4
H_BUILDING_1X1 = 0.9
H_LAIR = 1.0

# Pixel billboard height in world units (32px sprite read at map scale)
UNIT_BILLBOARD_SCALE = 0.62

# Stable bridge keys — never use id(surface) alone for multi-megapixel sheets (see terrain_texture_bridge).
_TERRAIN_TEX_KEY = "kingdom_ursina_terrain_baked"
_FOG_TEX_KEY = "kingdom_ursina_fog_overlay"

ENEMY_SCALE = 0.5
PEASANT_SCALE = 0.3
GUARD_SCALE_XZ = 0.5
GUARD_SCALE_Y = 0.7


def sim_px_to_world_xz(px_x: float, px_y: float) -> tuple[float, float]:
    """Map sim pixel coords to the X/Z floor (Y-up world)."""
    return px_x / SCALE, -px_y / SCALE


def px_to_world(px_x: float, px_y: float) -> tuple[float, float]:
    """Backward-compatible name: returns (world_x, world_z) for the floor plane."""
    return sim_px_to_world_xz(px_x, px_y)


def _building_type_str(bt) -> str:
    if bt is None:
        return ""
    return str(getattr(bt, "value", bt) or "")


def _footprint_tiles(building_type) -> tuple[int, int]:
    key = getattr(building_type, "value", building_type)
    return config.BUILDING_SIZES.get(key, (2, 2))


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

        # Single baked terrain quad (WK21 startup bake)
        self._terrain_entity: Entity | None = None
        # Keep the bake sheet alive so its address is never reused to collide with fog in TextureBridge.
        self._terrain_sheet: pygame.Surface | None = None

        # Fog-of-war overlay quad (WK22): matches pygame render_fog tints per visibility tile.
        self._fog_entity: Entity | None = None
        self._fog_full_surf: pygame.Surface | None = None
        # RGBA tile buffer reused for fog rebuilds (WK22 R3 perf: avoid 22k pygame.set_at calls).
        self._fog_tile_buf: bytearray | None = None
        self._fog_vis_signature: int | None = None
        self._fog_next_allowed_at: float = 0.0

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
        trigger = getattr(entity, "_render_anim_trigger", None)
        if trigger:
            tname = str(trigger)
            if tname in clips:
                setattr(entity, "_render_anim_trigger", None)
                base = base_clip_fn(entity)
                self._unit_anim_state[obj_id] = {
                    "clip": tname,
                    "t0": time.time(),
                    "base": base,
                    "oneshot": not clips[tname].loop,
                }
            else:
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

        WK22 Agent-10 perf fix:  The engine increments ``_fog_revision`` only when
        the visibility grid actually changes (a hero crosses a tile boundary).
        We compare against our cached revision to skip the expensive CRC32 and
        surface rebuild on frames where nothing moved.  Combined with the
        URSINA_FOG_MIN_UPDATE_INTERVAL_SEC throttle, this reduces fog cost from
        ~0.5 ms/frame to near zero on idle frames.
        """
        if self._terrain_entity is None:
            return

        world = self.engine.world

        # ---- Fast path: skip if engine reports no fog change ----
        engine_rev = getattr(self.engine, "_fog_revision", 0)
        my_rev = getattr(self, "_fog_revision_seen", -1)
        if engine_rev == my_rev and self._fog_entity is not None:
            return

        # ---- Throttle: respect min update interval ----
        now = time.perf_counter()
        min_iv = float(getattr(config, "URSINA_FOG_MIN_UPDATE_INTERVAL_SEC", 0.0) or 0.0)
        if self._fog_entity is not None and min_iv > 0.0 and now < self._fog_next_allowed_at:
            return
        self._fog_next_allowed_at = now + min_iv

        # ---- Double-check with CRC (catches non-engine visibility mutations) ----
        sig = _visibility_signature(world)
        if sig == self._fog_vis_signature and self._fog_entity is not None:
            self._fog_revision_seen = engine_rev
            return
        self._fog_vis_signature = sig
        self._fog_revision_seen = engine_rev

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
        for ty in range(th):
            row = world.visibility[ty]
            base = ty * tw * 4
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
            return

        ts = int(config.TILE_SIZE)
        wpx, hpx = tw * ts, th * ts
        w_world = wpx / SCALE
        d_world = hpx / SCALE
        cx_px = wpx * 0.5
        cy_px = hpx * 0.5
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
            self._fog_entity.shader = unlit_shader
            self._fog_entity.hide(0b0001)
            self._fog_entity.render_queue = 2
        else:
            self._fog_entity.texture = ftex
            self._fog_entity.position = (wx, fog_y, wz)
            self._fog_entity.scale = (w_world, d_world, 1)
            self._fog_entity.texture_scale = Vec2(1, -1)
            self._fog_entity.texture_offset = Vec2(0, 1)

    def _bake_terrain_floor(self) -> None:
        """One quad covering the map with a pygame terrain sheet → single texture."""
        if self._terrain_entity is not None:
            return

        world = self.engine.world
        tw, th = int(world.width), int(world.height)
        ts = int(config.TILE_SIZE)

        sheet = pygame.Surface((tw * ts, th * ts), pygame.SRCALPHA)
        for ty in range(th):
            for tx in range(tw):
                tile_type = int(world.tiles[ty][tx])
                surf = TileSpriteLibrary.get(tile_type, tx, ty, size=ts)
                if surf:
                    sheet.blit(surf, (tx * ts, ty * ts))

        self._terrain_sheet = sheet
        tex = TerrainTextureBridge.surface_to_texture(sheet, cache_key=_TERRAIN_TEX_KEY)
        if tex is None:
            return

        # World size in X/Z (same as legacy 2D tile stepping).
        w_world = (tw * ts) / SCALE
        d_world = (th * ts) / SCALE
        cx_px = tw * ts * 0.5
        cy_px = th * ts * 0.5
        wx, wz = sim_px_to_world_xz(cx_px, cy_px)

        # Quad mesh lies in local X/Y (see ursina.models.procedural.quad). After rotation_x=90°,
        # local Y becomes world depth (Z). Both axes must match map size — using (w, 1, d) left
        # the quad only 1 unit tall in Y, stretching the atlas into a thin strip (noisy paths,
        # grass apparently "missing" / wrong sampling).
        self._terrain_entity = Entity(
            model="quad",
            texture=tex,
            scale=(w_world, d_world, 1),
            rotation=(90, 0, 0),
            position=(wx, 0.0, wz),
            color=color.white,
            double_sided=True,
        )
        if self._terrain_entity.texture:
            self._terrain_entity.texture.filtering = None
        # WK22 R2: Terrain atlas must stay on its own Texture object (see bridge cache_key).
        # UV: V-flip + offset aligns world north with 2D map after Ursina's PIL upload flip — without
        # this, only the "wrong" band of the atlas can dominate (looked like solid grass / missing trees).
        self._terrain_entity.texture_scale = Vec2(1, -1)
        self._terrain_entity.texture_offset = Vec2(0, 1)
        # WK22 SPRINT-BUG-006: full-map terrain must not use lit+shadows or cast into the shadow pass.
        self._terrain_entity.shader = unlit_shader
        self._terrain_entity.hide(0b0001)
        self._terrain_entity.render_queue = 0

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

    def update(self):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        self._bake_terrain_floor()
        self._ensure_fog_overlay()

        gs = self.engine.get_game_state()

        active_ids = set()

        # Buildings — single vertical billboard quad (center: b.x / b.y are building centers)
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
            wx, wz = sim_px_to_world_xz(b.x, b.y)
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
            self._sync_billboard_entity(
                ent,
                tex=htex,
                tint_col=col,
                scale_xyz=(sy, sy, 1),
                pos_xyz=(wx, sy * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)

        # Enemies — billboards (same animation contract as pygame EnemyRenderer)
        for e in gs["enemies"]:
            if not getattr(e, "is_alive", True):
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
