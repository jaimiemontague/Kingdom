"""
Translates the GameEngine simulation state into Ursina 3D entities.

Perspective view: floor plane is X/Z (Y up). Simulation pixels (x, y) map to
(world_x, world_z) with world_z = -px_y / SCALE so screen-north stays intuitive
(PM WK19 decision).

WK21: Terrain is startup-baked from TileSpriteLibrary into one floor quad.
Buildings use BuildingSpriteLibrary textures on cubes. Units use pixel-art
billboards (Hero/Enemy/Worker sprite libraries).
"""
from __future__ import annotations

import pygame
import config
from ursina import Entity, Vec2, color, Text

from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.tile_sprites import TileSpriteLibrary
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.worker_sprites import WorkerSpriteLibrary

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


def _hero_idle_surface(hero):
    hc = str(getattr(hero, "hero_class", "warrior") or "warrior").lower()
    clips = HeroSpriteLibrary.clips_for(hc)
    return clips["idle"].frames[0]


def _enemy_idle_surface(enemy):
    et = str(getattr(enemy, "enemy_type", "goblin") or "goblin").lower()
    clips = EnemySpriteLibrary.clips_for(et)
    return clips["idle"].frames[0]


def _worker_idle_surface(worker_type: str):
    wt = str(worker_type or "peasant").lower()
    clips = WorkerSpriteLibrary.clips_for(wt)
    return clips["idle"].frames[0]


class UrsinaRenderer:
    def __init__(self, engine):
        self.engine = engine

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}

        # Single baked terrain quad (WK21 startup bake)
        self._terrain_entity: Entity | None = None

        # Status Text UI (2D overlay, not affected by world camera)
        self.status_text = Text(
            text="Kingdom Sim - Ursina Viewer",
            position=(-0.85, 0.47),
            scale=1.2,
            color=color.black,
            background=True,
        )

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

        tex = TerrainTextureBridge.surface_to_texture(sheet)
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
            position=(wx, 0.002, wz),
            color=color.white,
            double_sided=True,
        )
        if self._terrain_entity.texture:
            self._terrain_entity.texture.filtering = None
        # Align baked pygame sheet (row 0 = top / low sim y) with world Z after quad rotation:
        # without this, north/south vs 2D map often looks "flipped" or rotated wrong.
        self._terrain_entity.texture_scale = Vec2(1, -1)
        self._terrain_entity.texture_offset = Vec2(0, 1)

    @staticmethod
    def _apply_pixel_billboard_settings(ent: Entity) -> None:
        """Alpha-cutout sprites: discard transparent texels; sort/blend without black halos."""
        from panda3d.core import TransparencyAttrib

        ent.shader = sprite_unlit_shader
        ent.double_sided = True
        ent.setTransparency(TransparencyAttrib.M_alpha)
        ent.set_depth_write(False)
        ent.render_queue = 1

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
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    def update(self):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        self._bake_terrain_floor()

        gs = self.engine.get_game_state()

        active_ids = set()

        # Buildings — textured cubes (center position: b.x / b.y are already building centers)
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
            b_tex = TerrainTextureBridge.surface_to_texture(b_surf) if b_surf else None

            ent, obj_id = self._get_or_create_entity(b, model="cube", col=col)
            ent.model = "cube"
            ent.texture = b_tex if b_tex is not None else None
            ent.color = color.white if b_tex is not None else col
            ent.scale = (fx, hy, fz)
            ent.rotation = (0, 0, 0)
            wx, wz = sim_px_to_world_xz(b.x, b.y)
            ent.position = (wx, hy * 0.5, wz)
            active_ids.add(obj_id)

        # Heroes — pixel billboards
        for h in gs["heroes"]:
            col = COLOR_HERO
            if HeroClass:
                hc = getattr(h, "hero_class", None)
                if hc == HeroClass.RANGER or str(hc).lower() == "ranger":
                    col = color.lime
                elif hc == HeroClass.WIZARD or str(hc).lower() == "wizard":
                    col = color.magenta
                elif hc == HeroClass.ROGUE or str(hc).lower() == "rogue":
                    col = color.violet

            hsurf = _hero_idle_surface(h)
            htex = TerrainTextureBridge.surface_to_texture(hsurf)
            sy = UNIT_BILLBOARD_SCALE
            ent, obj_id = self._get_or_create_entity(
                h,
                model="quad",
                col=color.white,
                scale=(sy, sy, 1),
                texture=htex,
                billboard=True,
            )
            ent.model = "quad"
            ent.texture = htex
            ent.color = color.white if htex is not None else col
            ent.scale = (sy, sy, 1)
            ent.billboard = True
            ent.shader = sprite_unlit_shader
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            ent.position = (wx, sy * 0.5, wz)
            active_ids.add(obj_id)

        # Enemies — billboards
        for e in gs["enemies"]:
            s = ENEMY_SCALE
            col = COLOR_ENEMY
            esurf = _enemy_idle_surface(e)
            etex = TerrainTextureBridge.surface_to_texture(esurf)
            ent, obj_id = self._get_or_create_entity(
                e,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=etex,
                billboard=True,
            )
            ent.model = "quad"
            ent.texture = etex
            ent.color = color.white if etex is not None else col
            ent.scale = (s, s, 1)
            ent.billboard = True
            ent.shader = sprite_unlit_shader
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            ent.position = (wx, s * 0.5, wz)
            active_ids.add(obj_id)

        # Peasants — billboards
        for p in gs["peasants"]:
            s = PEASANT_SCALE
            col = COLOR_PEASANT
            psurf = _worker_idle_surface("peasant")
            ptex = TerrainTextureBridge.surface_to_texture(psurf)
            ent, obj_id = self._get_or_create_entity(
                p,
                model="quad",
                col=color.white,
                scale=(s, s, 1),
                texture=ptex,
                billboard=True,
            )
            ent.model = "quad"
            ent.texture = ptex
            ent.color = color.white if ptex is not None else col
            ent.scale = (s, s, 1)
            ent.billboard = True
            ent.shader = sprite_unlit_shader
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            ent.position = (wx, s * 0.5, wz)
            active_ids.add(obj_id)

        # Guards — billboards
        for g in gs["guards"]:
            col = COLOR_GUARD
            gsurf = _worker_idle_surface("guard")
            gtex = TerrainTextureBridge.surface_to_texture(gsurf)
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
            ent.model = "quad"
            ent.texture = gtex
            ent.color = color.white if gtex is not None else col
            ent.scale = (sxz, sy, 1)
            ent.billboard = True
            ent.shader = sprite_unlit_shader
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            ent.position = (wx, sy * 0.5, wz)
            active_ids.add(obj_id)

        heroes_alive = len([h for h in gs["heroes"] if getattr(h, "is_alive", True)])
        enemies_alive = len(gs["enemies"])
        self.status_text.text = (
            f"Gold: {gs['gold']}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(gs['buildings'])}"
        )

        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            ent = self._entities.pop(obj_id)
            import ursina

            ursina.destroy(ent)
