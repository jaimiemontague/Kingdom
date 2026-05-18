"""Underground terrain mesh generation and rendering (WK57).

For each UndergroundArea, generates:
- A cave floor mesh (Perlin noise heightmap at Y < 0)
- Stalactite/stalagmite decoration entities
- A dark rock ground texture
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.underground import UndergroundArea

from ursina import Entity, Mesh, Vec2, Vec3, color
from ursina.shaders import unlit_shader

from config import (
    TILE_SIZE,
    UNDERGROUND_DEPTH,
    UNDERGROUND_CEILING_Y,
    UNDERGROUND_CAVE_NOISE_AMP,
)

from game.graphics.ursina_coords import sim_px_to_world_xz


class UndergroundTerrainManager:
    """Creates and manages Ursina entities for underground cave meshes."""

    def __init__(self):
        self._area_entities: dict[str, list[Entity]] = {}  # area_id -> [floor_ent, decorations...]

    def create_underground_mesh(self, area: "UndergroundArea", root_parent) -> Entity | None:
        """Build and return a cave floor mesh entity for the given underground area.

        The mesh is positioned at the area's entrance POI location, offset downward.
        Each vertex Y comes from area.floor_heightmap (Perlin noise at Y < 0).
        """
        if not area.is_generated or not area.floor_heightmap:
            return None

        gw = area.total_width
        gh = area.total_height

        # World position of the entrance POI
        entrance_px = area.entrance_grid_x * TILE_SIZE + TILE_SIZE
        entrance_py = area.entrance_grid_y * TILE_SIZE + TILE_SIZE
        base_wx, base_wz = sim_px_to_world_xz(entrance_px, entrance_py)

        # Each tile = approximately 1.0 world unit (TILE_SIZE / TILE_SIZE)
        tile_world = 1.0

        verts = []
        uvs = []

        for gz in range(gh):
            for gx in range(gw):
                # Position relative to entrance, then offset to world
                # Center the mesh on the entrance
                cx_offset = gx - gw // 2
                cz_offset = gz  # deeper chambers go further in z

                wx = cx_offset * tile_world
                wz = -cz_offset * tile_world  # negative z = "forward" in world
                wy = area.floor_heightmap[gz][gx]

                # Non-walkable areas get pushed to ceiling height (invisible wall)
                if not area.walkability[gz][gx]:
                    wy = UNDERGROUND_CEILING_Y

                verts.append((wx, wy, wz))
                uvs.append((gx / max(1, gw - 1), gz / max(1, gh - 1)))

        # Compute normals (same approach as surface terrain)
        norms = []
        for gz in range(gh):
            for gx in range(gw):
                gx0 = max(0, gx - 1)
                gx1 = min(gw - 1, gx + 1)
                gz0 = max(0, gz - 1)
                gz1 = min(gh - 1, gz + 1)

                def _idx(_gz, _gx):
                    return _gz * gw + _gx

                hL = verts[_idx(gz, gx0)][1]
                hR = verts[_idx(gz, gx1)][1]
                hD = verts[_idx(gz0, gx)][1]
                hU = verts[_idx(gz1, gx)][1]
                nx = -(hR - hL)
                ny = 2.0
                nz = -(hU - hD)
                ln = math.sqrt(nx * nx + ny * ny + nz * nz)
                if ln > 1e-8:
                    nx /= ln
                    ny /= ln
                    nz /= ln
                else:
                    nx, ny, nz = 0.0, 1.0, 0.0
                norms.append((nx, ny, nz))

        # Build triangle indices
        triangles = []
        for gz in range(gh - 1):
            for gx in range(gw - 1):
                i00 = gz * gw + gx
                i10 = gz * gw + gx + 1
                i01 = (gz + 1) * gw + gx
                i11 = (gz + 1) * gw + gx + 1
                triangles.extend([i00, i01, i10])
                triangles.extend([i10, i01, i11])

        cave_mesh = Mesh(
            vertices=verts,
            triangles=triangles,
            uvs=uvs,
            normals=norms,
            mode="triangle",
        )

        cave_ent = Entity(
            parent=root_parent,
            model=cave_mesh,
            color=color.rgb(0.35, 0.28, 0.22),  # dark brown rock
            position=Vec3(base_wx, 0, base_wz),
            collision=False,
            double_sided=True,
            shader=unlit_shader,
            add_to_scene_entities=False,
        )

        entities = [cave_ent]
        self._area_entities[area.area_id] = entities
        return cave_ent

    def create_stalactites(self, area: "UndergroundArea", root_parent, rng=None):
        """Place stalactite decoration entities at random positions in walkable chambers."""
        if rng is None:
            from game.sim.determinism import get_rng
            rng = get_rng("underground_deco")

        entrance_px = area.entrance_grid_x * TILE_SIZE + TILE_SIZE
        entrance_py = area.entrance_grid_y * TILE_SIZE + TILE_SIZE
        base_wx, base_wz = sim_px_to_world_xz(entrance_px, entrance_py)
        cx = area.total_width // 2

        for ch in area.chambers:
            num_stalactites = rng.randint(2, max(3, ch.width))
            for _ in range(num_stalactites):
                dx = rng.randint(0, ch.width - 1)
                dz = rng.randint(0, ch.height - 1)
                gx = cx + ch.world_offset_x + dx
                gz = ch.world_offset_z + dz

                if not (0 <= gx < area.total_width and 0 <= gz < area.total_height):
                    continue
                if not area.walkability[gz][gx]:
                    continue

                wx = (gx - cx) * 1.0 + base_wx
                wz = -gz * 1.0 + base_wz

                # Stalactite: thin stretched cube hanging from ceiling
                try:
                    stalactite = Entity(
                        parent=root_parent,
                        model="cube",
                        color=color.rgb(0.3, 0.25, 0.2),
                        scale=(0.12, 0.5 + rng.random() * 0.3, 0.12),
                        position=Vec3(wx, UNDERGROUND_CEILING_Y, wz),
                        rotation=(180, rng.randint(0, 360), 0),
                        add_to_scene_entities=False,
                    )
                    if area.area_id in self._area_entities:
                        self._area_entities[area.area_id].append(stalactite)
                except Exception:
                    pass

    def set_underground_visible(self, area_id: str, visible: bool):
        """Show or hide all entities for an underground area."""
        for ent in self._area_entities.get(area_id, []):
            ent.enabled = visible

    def destroy_all(self):
        """Clean up all underground entities."""
        for entities in self._area_entities.values():
            for ent in entities:
                try:
                    ent.enabled = False
                    from ursina import destroy
                    destroy(ent)
                except Exception:
                    pass
        self._area_entities.clear()
