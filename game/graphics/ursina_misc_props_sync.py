"""Per-frame misc-prop sync (projectiles + bounty flags + rubble) for the Ursina renderer.

WK90, Round B-7. Pure-move of the three isolated "misc prop" per-frame sync
methods out of ``game/graphics/ursina_renderer.py``:

* ``sync_snapshot_projectiles`` — VFX arrow billboards (was ``_sync_snapshot_projectiles``)
* ``sync_snapshot_bounties``    — 3D bounty flag assemblies (was ``_sync_snapshot_bounties``)
* ``sync_snapshot_rubble``      — destroyed-building rubble rocks (was ``_sync_snapshot_rubble``)

Each function takes the ``UrsinaRenderer`` instance as ``r`` and reads/writes its
state (``r._projectile_tex``, ``r._entity_render``, ``r._bounty_entities``,
``r._rubble_entities``) exactly as the original methods read ``self.*``. The
bounty-flag visual constants that lived as class attributes
(``_BOUNTY_POLE_HEIGHT`` etc.) are read via ``r.`` since they remain on the
renderer class. ``UrsinaRenderer`` keeps 1-line delegating wrappers
(``_sync_snapshot_projectiles`` / ``_sync_snapshot_bounties`` /
``_sync_snapshot_rubble``) that import this module lazily, so the ``update()``
pipeline call sites are unchanged and there is no import cycle (this module never
imports ``ursina_renderer`` at module top). Leaf deps only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import config
from ursina import Entity, Vec3, color, Text, scene
from ursina.shaders import unlit_shader

from game.graphics.terrain_texture_bridge import TerrainTextureBridge
from game.graphics.ursina_sprite_unlit_shader import sprite_unlit_shader
from game.graphics.vfx import get_projectile_billboard_surface
from game.graphics.ursina_coords import sim_px_to_world_xz
from game.graphics.ursina_environment import _environment_model_path
from game.graphics.terrain_height import get_terrain_height, is_initialized as _terrain_height_ok

if TYPE_CHECKING:
    from game.graphics.ursina_renderer import UrsinaRenderer
    from game.sim.snapshot import SimStateSnapshot

# Projectile billboard constants — recomputed here identically to the
# ursina_renderer module-level values (config-derived, no renderer import needed).
_US = float(getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)) / float(config.TILE_SIZE)
ENEMY_SCALE = 0.5 * _US
# Ranged VFX billboards — smaller than unit sprites, readable in perspective.
# 0.3 was large in playtest; 25% of that keeps arrows visible (snapshot + depth fix) without dominating the frame.
PROJECTILE_BILLBOARD_SCALE = 0.075
# Vertical lift: match enemy sprite center (ENEMY_SCALE*0.5) so arrows aren't drawn under terrain.
PROJECTILE_BILLBOARD_Y = ENEMY_SCALE * 0.5


def sync_snapshot_projectiles(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set) -> None:
    # Projectiles — VFX arrows as textured billboards (WK5 colors via get_projectile_billboard_surface)
    if r._projectile_tex is None:
        psurf = get_projectile_billboard_surface()
        r._projectile_tex = TerrainTextureBridge.surface_to_texture(
            psurf, cache_key=("ursina", "projectile_arrow_billboard_v1")
        )
    ptex = r._projectile_tex
    for proj in getattr(snapshot, "vfx_projectiles", ()) or ():
        s = PROJECTILE_BILLBOARD_SCALE
        ent, obj_id = r._entity_render.get_or_create_entity(
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
            r._entity_render.apply_pixel_billboard_settings(ent)
            ent._ks_billboard_configured = True
        # Draw above the floor plane: tiny Y (s*0.5) caused depth-fighting with terrain; stack with units.
        if not getattr(ent, "_ks_projectile_depth", False):
            ent.set_depth_test(False)
            ent.render_queue = 2
            ent._ks_projectile_depth = True
        wx, wz = sim_px_to_world_xz(proj.x, proj.y)
        proj_terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0
        r._entity_render.sync_billboard_entity(
            ent,
            tex=ptex,
            tint_col=color.white,
            scale_xyz=(s, s, 1),
            pos_xyz=(wx, proj_terrain_y + PROJECTILE_BILLBOARD_Y, wz),
            shader=sprite_unlit_shader,
        )
        active_ids.add(obj_id)


def sync_snapshot_bounties(r: "UrsinaRenderer", snapshot: "SimStateSnapshot", active_ids: set) -> None:
    """Create/update/remove 3D bounty flag entities for each unclaimed bounty."""
    import ursina

    # WK66 Move 3: consume frozen BountyDTOs (bounty_id/claimed/x/y/reward) — the
    # Ursina flag shows only $reward (not responders/tier), and none of those
    # fields are mutated during the render pass, so this is behavior-identical.
    # WK68 R3 (Agent 03): the live ``snapshot.bounties`` fallback was deleted with
    # the live entity tuples (L1); ``bounty_dtos`` is always present now.
    bounties = getattr(snapshot, "bounty_dtos", ()) or ()

    # Build set of currently active bounty IDs
    active_bounty_ids: set[int] = set()
    for b in bounties:
        bid = getattr(b, "bounty_id", None)
        if bid is None:
            continue
        if getattr(b, "claimed", False):
            continue
        active_bounty_ids.add(bid)

        bx = float(getattr(b, "x", 0))
        by = float(getattr(b, "y", 0))
        reward = int(getattr(b, "reward", 0))

        wx, wz = sim_px_to_world_xz(bx, by)
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

        if bid in r._bounty_entities:
            # Update existing entities positions (in case bounty moved, unlikely but safe)
            parts = r._bounty_entities[bid]
            pole_y = terrain_y + r._BOUNTY_POLE_HEIGHT * 0.5
            parts[0].position = Vec3(wx, pole_y, wz)  # pole
            parts[1].position = Vec3(wx + 0.08, terrain_y + r._BOUNTY_POLE_HEIGHT - r._BOUNTY_FLAG_OFFSET_Y, wz)  # flag
            parts[2].position = Vec3(wx, terrain_y + r._BOUNTY_POLE_HEIGHT + r._BOUNTY_TEXT_OFFSET_Y, wz)  # text
        else:
            # Create new flag assembly: pole + pennant + reward text
            pole = Entity(
                model="cube",
                color=color.rgb(0.4, 0.25, 0.1),  # brown
                scale=Vec3(r._BOUNTY_POLE_RADIUS * 2, r._BOUNTY_POLE_HEIGHT, r._BOUNTY_POLE_RADIUS * 2),
                position=Vec3(wx, terrain_y + r._BOUNTY_POLE_HEIGHT * 0.5, wz),
                shader=unlit_shader,
            )
            # Gold pennant flag — offset slightly to the side of the pole
            flag = Entity(
                model="quad",
                color=color.rgb(1.0, 0.84, 0.0),  # gold
                scale=Vec3(*r._BOUNTY_FLAG_SCALE),
                position=Vec3(wx + 0.08, terrain_y + r._BOUNTY_POLE_HEIGHT - r._BOUNTY_FLAG_OFFSET_Y, wz),
                billboard=True,
                shader=unlit_shader,
            )
            # Reward text label above the flag
            reward_text = Text(
                text=f"${reward}",
                position=(0, 0),
                scale=1.0,
                color=color.rgb(1.0, 0.84, 0.0),
                billboard=True,
                parent=scene,
            )
            reward_text.world_position = Vec3(wx, terrain_y + r._BOUNTY_POLE_HEIGHT + r._BOUNTY_TEXT_OFFSET_Y, wz)
            reward_text.world_scale = Vec3(0.15, 0.15, 0.15)

            r._bounty_entities[bid] = [pole, flag, reward_text]

    # Remove entities for claimed/expired bounties
    removed_ids = set(r._bounty_entities.keys()) - active_bounty_ids
    for bid in removed_ids:
        parts = r._bounty_entities.pop(bid)
        for part in parts:
            ursina.destroy(part)


def sync_snapshot_rubble(r: "UrsinaRenderer", snapshot: "SimStateSnapshot") -> None:
    """Create/destroy rubble entity groups from snapshot.rubble_records.

    NOTE: the original ``_sync_snapshot_rubble(self, ...)`` method used the local
    name ``r`` for each rubble *record*; here the renderer is ``r``, so the
    per-record loop variable is renamed ``rec`` to avoid shadowing. This is a
    local-name-only change — the logic is byte-for-byte identical.
    """
    import ursina as _ursina
    import random as _random

    rubble_records = getattr(snapshot, 'rubble_records', ())
    active_ids = {rec.record_id for rec in rubble_records}

    # Remove expired rubble
    for rid in list(r._rubble_entities.keys()):
        if rid not in active_ids:
            for ent in r._rubble_entities[rid]:
                _ursina.destroy(ent)
            del r._rubble_entities[rid]

    # Create new rubble
    for rec in rubble_records:
        if rec.record_id in r._rubble_entities:
            continue  # already rendered

        entities = []
        # Convert grid position to world position using the same
        # coordinate system as buildings (sim pixels -> Ursina X/Z).
        ts = float(config.TILE_SIZE)
        center_px_x = rec.grid_x * ts + (rec.width_tiles * ts) * 0.5
        center_px_y = rec.grid_y * ts + (rec.height_tiles * ts) * 0.5
        wx, wz = sim_px_to_world_xz(center_px_x, center_px_y)
        terrain_y = get_terrain_height(wx, wz) if _terrain_height_ok() else 0.0

        # Place 3 small rock models scattered within footprint
        rng = _random.Random(rec.record_id)  # deterministic per rubble
        footprint_world = rec.width_tiles * 0.5  # half-extent in world units

        _rock_stems = [
            'rock_smallA', 'rock_smallB', 'rock_smallC',
            'rock_smallD', 'rock_smallE', 'rock_smallF',
        ]

        for _i in range(3):
            offset_x = rng.uniform(-footprint_world * 0.3, footprint_world * 0.3)
            offset_z = rng.uniform(-footprint_world * 0.3, footprint_world * 0.3)
            rock_stem = rng.choice(_rock_stems)
            rock_model = _environment_model_path(rock_stem)
            rock_scale = rng.uniform(0.8, 1.5)
            rock_rot = rng.uniform(0, 360)

            rock = Entity(
                model=rock_model,
                position=(wx + offset_x, terrain_y + 0.1, wz + offset_z),
                scale=rock_scale,
                rotation_y=rock_rot,
                color=color.rgb(0.6, 0.55, 0.5),  # dusty gray-brown
            )
            entities.append(rock)

        r._rubble_entities[rec.record_id] = entities
