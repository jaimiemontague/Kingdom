"""
Translates the GameEngine simulation state into Ursina 3D entities.

Perspective view: floor plane is X/Z (Y up). Simulation pixels (x, y) map to
(world_x, world_z) with world_z = -px_y / SCALE so screen-north stays intuitive
(PM WK19 decision). Volumetric primitives per Agent 09 WK19 spec.
"""
from __future__ import annotations

import config
from ursina import Entity, color, Text, Cylinder

# Basic colors for our low-fi MVP
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

HERO_CYLINDER = Cylinder(resolution=12, radius=0.28, height=1.0, start=0.0)
HERO_Y = 0.5  # cylinder y=0..1, center at 0.5

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


def _footprint_tiles(building_type: str) -> tuple[int, int]:
    return config.BUILDING_SIZES.get(building_type, (2, 2))


def _building_height_y(
    tw: int, th: int, building_type: str, is_lair: bool, is_castle: bool
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


class UrsinaRenderer:
    def __init__(self, engine):
        self.engine = engine

        # Entity mappings: simulation object id() -> Ursina Entity
        self._entities = {}

        # Status Text UI (2D overlay, not affected by world camera)
        self.status_text = Text(
            text='Kingdom Sim - Ursina Viewer',
            position=(-0.85, 0.47),
            scale=1.2,
            color=color.black,
            background=True,
        )

    def _get_or_create_entity(
        self,
        sim_obj,
        model='cube',
        col=color.white,
        scale=(1, 1, 1),
        rotation=(0, 0, 0),
    ):
        obj_id = id(sim_obj)
        if obj_id not in self._entities:
            ent = Entity(model=model, color=col, scale=scale, rotation=rotation)
            self._entities[obj_id] = ent
        return self._entities[obj_id], obj_id

    def update(self):
        """Called every frame by the Ursina app loop."""
        try:
            from game.types import HeroClass
        except Exception:
            HeroClass = None

        gs = self.engine.get_game_state()

        active_ids = set()

        # Buildings
        for b in gs['buildings']:
            bt = getattr(b, 'building_type', '') or ''
            is_castle = bt == 'castle'
            is_lair = hasattr(b, 'stash_gold')
            if is_castle:
                col = COLOR_CASTLE
            elif is_lair:
                col = COLOR_LAIR
            else:
                col = COLOR_BUILDING

            tw, th = _footprint_tiles(bt)
            fx = b.width / SCALE
            fz = b.height / SCALE
            hy = _building_height_y(tw, th, bt, is_lair, is_castle)

            ent, obj_id = self._get_or_create_entity(b, model='cube', col=col)
            wx, wz = sim_px_to_world_xz(b.x + b.width / 2, b.y + b.height / 2)
            ent.model = 'cube'
            ent.color = col
            ent.scale = (fx, hy, fz)
            ent.rotation = (0, 0, 0)
            ent.position = (wx, hy * 0.5, wz)
            active_ids.add(obj_id)

        # Heroes — cylinder (capsule stand-in), class tint
        for h in gs['heroes']:
            col = COLOR_HERO
            if HeroClass:
                hc = getattr(h, 'hero_class', None)
                if hc == HeroClass.RANGER:
                    col = color.lime
                elif hc == HeroClass.WIZARD:
                    col = color.magenta
                elif hc == HeroClass.ROGUE:
                    col = color.violet

            ent, obj_id = self._get_or_create_entity(h, model=HERO_CYLINDER, col=col)
            ent.model = HERO_CYLINDER
            ent.color = col
            ent.scale = (1, 1, 1)
            ent.rotation = (0, 0, 0)
            wx, wz = sim_px_to_world_xz(h.x, h.y)
            ent.position = (wx, HERO_Y, wz)
            active_ids.add(obj_id)

        # Enemies — red cube
        for e in gs['enemies']:
            s = ENEMY_SCALE
            ent, obj_id = self._get_or_create_entity(e, model='cube', col=COLOR_ENEMY)
            ent.model = 'cube'
            ent.color = COLOR_ENEMY
            ent.scale = (s, s, s)
            ent.rotation = (0, 0, 0)
            wx, wz = sim_px_to_world_xz(e.x, e.y)
            ent.position = (wx, s * 0.5, wz)
            active_ids.add(obj_id)

        # Peasants — small orange cube
        for p in gs['peasants']:
            s = PEASANT_SCALE
            ent, obj_id = self._get_or_create_entity(p, model='cube', col=COLOR_PEASANT)
            ent.model = 'cube'
            ent.color = COLOR_PEASANT
            ent.scale = (s, s, s)
            ent.rotation = (0, 0, 0)
            wx, wz = sim_px_to_world_xz(p.x, p.y)
            ent.position = (wx, s * 0.5, wz)
            active_ids.add(obj_id)

        # Guards — yellow cube, slightly taller than wide
        for g in gs['guards']:
            ent, obj_id = self._get_or_create_entity(g, model='cube', col=COLOR_GUARD)
            ent.model = 'cube'
            ent.color = COLOR_GUARD
            ent.scale = (GUARD_SCALE_XZ, GUARD_SCALE_Y, GUARD_SCALE_XZ)
            ent.rotation = (0, 0, 0)
            wx, wz = sim_px_to_world_xz(g.x, g.y)
            ent.position = (wx, GUARD_SCALE_Y * 0.5, wz)
            active_ids.add(obj_id)

        heroes_alive = len([h for h in gs['heroes'] if getattr(h, 'is_alive', True)])
        enemies_alive = len(gs['enemies'])
        self.status_text.text = (
            f"Gold: {gs['gold']}  |  Heroes: {heroes_alive}  |  "
            f"Enemies: {enemies_alive}  |  Buildings: {len(gs['buildings'])}"
        )

        dead_ids = set(self._entities.keys()) - active_ids
        for obj_id in dead_ids:
            ent = self._entities.pop(obj_id)
            import ursina

            ursina.destroy(ent)
