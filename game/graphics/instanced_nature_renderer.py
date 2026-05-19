"""Hardware-instanced 3D nature (tree) renderer — Phase 4 of wk58 perf sprint.

The Wave 3 static-batch pass collapses ~7,500 grass/doodad/path/water Entities into
~hundreds of flattened batches, but the ~2,083 tree Entities stay individual because
``sync_dynamic_trees`` mutates their scale every growth event. After Wave 3 the
remaining per-frame GPU-node ceiling is "one Panda3D NodePath per visible tree".

This module replaces that pile of NodePaths with **one instanced GeomNode per tree
model** (~13 distinct models in the Kenney pack). Each model becomes a single draw
call of N instances. Per-instance world position + uniform scale are packed into a
Panda3D buffer texture (``setup_buffer_texture(T_float, F_rgba32, UH_dynamic)``) and
fetched in the vertex shader via ``texelFetch(samplerBuffer, gl_InstanceID)``. This
mirrors the pattern from ``game/graphics/instanced_unit_renderer.py`` but trees use
3D meshes (with material colors from the GLB), not animated atlas billboards.

Public API (called from ``UrsinaTerrainFogCollab``):

- ``register_tree(model_path, world_pos, scale, tile_xy) -> instance_id``
- ``update_tree_scale(instance_id, scale)`` — growth events
- ``remove_tree(instance_id)`` — sapling built over, footprint chop, etc.
- ``set_fog_visibility(tile_xy, visible: bool)`` — fog sync per tile
- ``update_buffer()`` — per-frame: re-pack the active-only slice into the GPU buffer

Gated behind ``KINGDOM_URSINA_INSTANCED_TREES`` env var; the collab keeps the legacy
individual-Entity path as a fallback when the var is "0".

Hard directive (Jaimie, 2026-05-18): perf gains MUST come from instancing. If this
path is fundamentally blocked, the env flag stays "0" — DO NOT reduce tree density.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Optional

from panda3d.core import (
    GeomEnums,
    GeomNode,
    NodePath,
    PandaNode,
    Texture,
)
from ursina.shader import Shader

import config


# RGBA32F: each texel is 4 floats = 16 bytes. We pack (world_x, world_y, world_z, scale)
# into ONE texel per instance (1 row per instance), unlike the unit renderer which uses
# 2 texels per instance (posScale + uvRegion).
BYTES_PER_TEXEL = 16

# Per-model instance cap. The Kenney pack on a 250x250 map produces ~150-300 trees per
# distinct model. 1024 leaves headroom for sapling growth/respawn during a session
# without re-allocating the buffer.
DEFAULT_MAX_INSTANCES_PER_MODEL = 1024


# -------------------------------------------------------------------------
# Shader: per-instance world transform via buffer texture lookup.
#
# Vertex stage:
#   - Reads ``(world_x, world_y, world_z, scale)`` from ``instanceData`` at
#     ``texelFetch(instanceData, gl_InstanceID)``.
#   - Computes ``worldPos = instancePos + p3d_Vertex.xyz * scale``.
#   - Multiplies by ``p3d_ViewProjectionMatrix`` (NodePath sits at origin with no
#     local transform, so model-view == view).
#
# Fragment stage:
#   - Uses Panda3D's built-in ``p3d_Material.baseColor`` (the GLB material colors
#     from the Kenney tree pack — bark dark, leafs dark, etc.).
#   - Applies a fixed lambert term from a fixed sun direction so trees aren't pure
#     flat-shaded silhouettes. Brightness matches the legacy unlit fallback so the
#     A/B looks identical at default lighting (``URSINA_DIRECTIONAL_SHADOWS=False``).
#   - Discards near-zero alpha (no transparent foliage in these Kenney models, but
#     guard anyway — leaves with alpha-cut textures could appear in future packs).
# -------------------------------------------------------------------------

instanced_nature_shader = Shader(
    name="instanced_nature_shader",
    language=Shader.GLSL,
    vertex="""#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrixInverseTranspose;

in vec4 p3d_Vertex;
in vec3 p3d_Normal;

/* Panda3D buffer texture from ``setup_buffer_texture(T_float, F_rgba32)`` → samplerBuffer. */
uniform samplerBuffer instanceData;

out vec3 v_normal_world;
out float v_pass_through;

void main() {
    vec4 posScale = texelFetch(instanceData, gl_InstanceID);

    vec3 instancePos = posScale.xyz;
    float scale = posScale.w;

    /* Per-instance world transform: translate to instance world pos, uniform scale. */
    vec3 worldPos = instancePos + p3d_Vertex.xyz * scale;

    gl_Position = p3d_ModelViewProjectionMatrix * vec4(worldPos, 1.0);

    /* Pass the mesh's vertex normal through to the fragment for cheap lambert
       lighting. Since the NodePath sits at origin with identity model matrix,
       the normal is already in world-equivalent space. */
    v_normal_world = normalize(p3d_Normal);
    v_pass_through = scale;
}
""",
    fragment="""#version 330

uniform struct p3d_MaterialParameters {
    vec4 baseColor;
    vec4 emission;
    vec3 specular;
    float roughness;
    float metallic;
    float refractiveIndex;
} p3d_Material;

in vec3 v_normal_world;
in float v_pass_through;

out vec4 fragColor;

void main() {
    /* Fixed warm-sun direction matches the directional light Agent 03 set up in
       ``UrsinaRenderer._setup_scene_lighting`` (down-and-right). Keeping the math
       in the shader (vs. binding a uniform) means the instanced path stays
       self-contained when shadows are off (the common URSINA_DIRECTIONAL_SHADOWS
       =False default). */
    vec3 sunDir = normalize(vec3(0.35, 0.85, 0.40));
    float ndotl = max(dot(normalize(v_normal_world), sunDir), 0.0);

    /* Ambient lift so non-lit faces aren't black — matches the AmbientLight
       (0.34, 0.38, 0.44) baseline in ``UrsinaRenderer._setup_scene_lighting``. */
    float ambient = 0.55;
    float light = ambient + 0.55 * ndotl;

    vec3 albedo = p3d_Material.baseColor.rgb;
    fragColor = vec4(albedo * light, p3d_Material.baseColor.a);

    if (fragColor.a < 0.05) {
        discard;
    }
}
""",
)
instanced_nature_shader.compile(shader_includes=False)


# -------------------------------------------------------------------------
# Model loading helper
# -------------------------------------------------------------------------


def _load_geom_node_for_model(model_path: str) -> tuple[Optional[GeomNode], Optional[NodePath]]:
    """Resolve a tree model file into a Panda3D ``GeomNode`` plus its source NodePath.

    Uses Panda3D's loader rather than spinning up an Ursina ``Entity`` so we don't
    pay for an Entity per model in scene-entities. Returns ``(None, None)`` on
    failure so the caller can fall back to legacy individual-Entity rendering for
    that specific model.

    Returns:
        (geom_node, source_np):
          - ``geom_node``: the FIRST GeomNode found under the loaded model. Tree
            models in the Kenney pack are single-mesh; if a model has multiple
            GeomNodes we currently only use one — log a warning so we know.
          - ``source_np``: the loaded model NodePath, kept alive so the GeomNode's
            material/state references aren't garbage-collected.
    """
    try:
        from direct.showbase.Loader import Loader
        from panda3d.core import NodePath as _NP

        # Reuse the global ShowBase loader if available; fall back to a private one.
        try:
            from direct.showbase.ShowBaseGlobal import base as _base  # type: ignore[attr-defined]
            loader = _base.loader if hasattr(_base, "loader") else None
        except Exception:
            loader = None
        if loader is None:
            try:
                from direct.directbase.DirectStart import base as _ds_base  # type: ignore
                loader = _ds_base.loader
            except Exception:
                loader = Loader(None)

        loaded = loader.load_model(model_path)
        if loaded is None:
            return None, None
        # Ursina sometimes returns a NodePath; Panda3D loader returns a NodePath too.
        if not isinstance(loaded, _NP):
            loaded = _NP(loaded)

        # Find the first GeomNode under the loaded model.
        geom_paths = loaded.find_all_matches("**/+GeomNode")
        if geom_paths.get_num_paths() == 0:
            return None, None
        geom_node = geom_paths.get_path(0).node()
        if not isinstance(geom_node, GeomNode):
            return None, None
        return geom_node, loaded
    except Exception:
        return None, None


# -------------------------------------------------------------------------
# InstancedNatureRenderer
# -------------------------------------------------------------------------


class InstancedNatureRenderer:
    """One instanced ``GeomNode`` per tree model; world transforms via buffer texture.

    Per-model state lives in ``_per_model``; the slots dict uses ``model_path`` as
    its key. Each instance has a stable ``instance_id`` (monotonic counter) so the
    caller can grow/remove without caring about slot bookkeeping.

    Memory: 1 ``Texture(T_float, F_rgba32)`` of ``MAX_INSTANCES_PER_MODEL`` texels
    per model, plus one shared NodePath cloned from the loaded model. With 13 models
    × 1024 cap × 16 B/texel that's ~210 KB total — negligible.

    Fog: ``set_fog_visibility`` toggles a per-tile bit; ``update_buffer`` walks every
    instance and only includes ones whose tile is fog-visible AND whose ``alive`` bit
    is set. Out-of-fog trees stay registered but simply don't get packed — no need
    to re-register on fog flips.
    """

    __slots__ = (
        "_initialized",
        "_per_model",                   # model_path -> dict with geom_node, source_np, np, buffer_tex, instances, active_count, dirty
        "_max_instances_per_model",
        "_instance_lookup",             # instance_id -> (model_path, slot_idx)
        "_next_instance_id",
        "_fog_visible_by_tile",         # (tx, ty) -> bool (True = include; False = skip from buffer)
        "_instances_by_tile",           # (tx, ty) -> list[instance_id] for fast fog flip propagation
        "_failed_models",               # set[model_path] that failed to load — caller falls back to legacy Entity
        "_chunk_visible_set",           # set[(cx, cy)] of chunks currently in camera frustum (per-frame)
        "_chunk_size",                  # tile-size of a chunk (default 16 == TERRAIN_CHUNK_SIZE)
        "_chunk_filter_enabled",        # bool: when False, every fog-visible instance is packed (no chunk cull)
    )

    def __init__(self) -> None:
        self._initialized = False
        self._per_model: dict[str, dict] = {}
        try:
            self._max_instances_per_model = max(
                64,
                int(os.environ.get("KINGDOM_URSINA_INSTANCED_TREES_CAP", "") or DEFAULT_MAX_INSTANCES_PER_MODEL),
            )
        except ValueError:
            self._max_instances_per_model = DEFAULT_MAX_INSTANCES_PER_MODEL
        self._instance_lookup: dict[int, tuple[str, int]] = {}
        self._next_instance_id: int = 1
        # Tiles outside fog default to ``False`` so that, post-/revealmap, the
        # collab's reveal-everything fog sync writes ``True`` for every tile and
        # the next ``update_buffer`` packs every tree.
        self._fog_visible_by_tile: dict[tuple[int, int], bool] = {}
        self._instances_by_tile: dict[tuple[int, int], list[int]] = {}
        self._failed_models: set[str] = set()
        # Camera frustum chunk filter — populated each frame by the collab so that
        # the GPU instance count drops from ``total_fog_visible`` (~2,083 after
        # ``/revealmap``) to ``trees_in_visible_chunks`` (~50-400 at default cam).
        # Without this, hardware instancing draws every tree on the map every
        # frame and the vertex throughput dominates the budget.
        self._chunk_visible_set: set[tuple[int, int]] = set()
        self._chunk_size: int = 16  # matches TERRAIN_CHUNK_SIZE
        self._chunk_filter_enabled: bool = False

    # ---- per-model ensure / teardown ------------------------------------

    def _ensure_per_model(self, model_path: str) -> Optional[dict]:
        """Lazy-create the per-model GeomNode + buffer texture + scene-attached NodePath.

        Returns the per-model dict, or ``None`` if the model failed to load (caller
        should fall back to legacy Entity path for that tree).
        """
        if model_path in self._per_model:
            return self._per_model[model_path]
        if model_path in self._failed_models:
            return None

        geom_node, source_np = _load_geom_node_for_model(model_path)
        if geom_node is None:
            self._failed_models.add(model_path)
            return None

        # Buffer texture: one texel per instance, RGBA32F = 16 B/texel.
        buf = Texture(f"tree_instance_data:{Path(model_path).stem}")
        buf.setup_buffer_texture(
            self._max_instances_per_model,
            Texture.T_float,
            Texture.F_rgba32,
            GeomEnums.UH_dynamic,
        )

        # Create a NEW NodePath wrapping the loaded GeomNode so we can independently
        # reparent under scene + set instance_count without disturbing the source.
        # ``NodePath(geom_node)`` shares the underlying node by reference, which is
        # what we want — we're not modifying the geometry, only the parent state.
        try:
            from ursina import scene
        except Exception:
            scene = None  # type: ignore[assignment]

        np = NodePath(PandaNode(f"instanced_nature_{Path(model_path).stem}"))
        if scene is not None:
            try:
                np.reparent_to(scene)
            except Exception:
                pass
        # Attach the geom node under our parent NodePath so transforms cascade.
        geom_np = np.attach_new_node(geom_node)

        # Bind the shader + instance buffer + instance count on the geom-bearing
        # NodePath. Per Panda3D 1.10 docs, ``set_instance_count`` applies to the
        # NodePath, not the GeomNode directly.
        try:
            geom_np.set_shader(instanced_nature_shader._shader)
        except Exception:
            try:
                geom_np.set_shader(instanced_nature_shader)
            except Exception:
                pass
        try:
            geom_np.set_shader_input("instanceData", buf)
        except Exception:
            pass
        geom_np.set_instance_count(0)
        # Trees are opaque; keep default render queue. Disable backface culling
        # because Kenney foliage meshes are single-sided and would otherwise lose
        # leaves from low camera angles.
        try:
            geom_np.set_two_sided(True)
        except Exception:
            pass

        state = {
            "geom_node": geom_node,
            "source_np": source_np,   # keep ref so material state isn't GC'd
            "np": np,
            "geom_np": geom_np,
            "buffer_tex": buf,
            # Instance slot layout: parallel arrays indexed by slot.
            # ``alive[slot]`` False = slot is free; ``id[slot]`` is the stable
            # instance_id for that slot when alive.
            "id": [0] * self._max_instances_per_model,
            "alive": [False] * self._max_instances_per_model,
            "world_x": [0.0] * self._max_instances_per_model,
            "world_y": [0.0] * self._max_instances_per_model,
            "world_z": [0.0] * self._max_instances_per_model,
            "scale": [1.0] * self._max_instances_per_model,
            "tile": [(0, 0)] * self._max_instances_per_model,
            "free_slots": list(range(self._max_instances_per_model - 1, -1, -1)),
            # Compact list of in-use slot indices so ``update_buffer`` walks
            # only ~100 alive slots per model instead of every cap=1024 slot.
            "active_slots": [],
            "dirty": True,
            "last_active_count": 0,
        }
        self._per_model[model_path] = state
        return state

    # ---- public API -----------------------------------------------------

    def register_tree(
        self,
        model_path: str,
        world_pos: tuple[float, float, float],
        scale: float,
        tile_xy: tuple[int, int],
    ) -> Optional[int]:
        """Allocate an instance slot for a tree at ``world_pos`` scaled by ``scale``.

        Returns the assigned ``instance_id`` (callers store this to grow/remove
        later), or ``None`` if the model failed to load or all slots are full.
        """
        state = self._ensure_per_model(model_path)
        if state is None:
            return None
        free = state["free_slots"]
        if not free:
            return None
        slot = free.pop()

        instance_id = self._next_instance_id
        self._next_instance_id = instance_id + 1

        state["id"][slot] = instance_id
        state["alive"][slot] = True
        state["world_x"][slot] = float(world_pos[0])
        state["world_y"][slot] = float(world_pos[1])
        state["world_z"][slot] = float(world_pos[2])
        state["scale"][slot] = float(scale)
        tkey = (int(tile_xy[0]), int(tile_xy[1]))
        state["tile"][slot] = tkey
        state["active_slots"].append(slot)
        state["dirty"] = True

        self._instance_lookup[instance_id] = (model_path, slot)
        self._instances_by_tile.setdefault(tkey, []).append(instance_id)
        return instance_id

    def update_tree_scale(self, instance_id: int, scale: float) -> bool:
        """Mutate the scale of an existing instance (sapling growth path).

        Returns True on success, False if the id is unknown.
        """
        rec = self._instance_lookup.get(int(instance_id))
        if rec is None:
            return False
        model_path, slot = rec
        state = self._per_model.get(model_path)
        if state is None or not state["alive"][slot]:
            return False
        new_scale = float(scale)
        if state["scale"][slot] == new_scale:
            return True
        state["scale"][slot] = new_scale
        state["dirty"] = True
        return True

    def remove_tree(self, instance_id: int) -> bool:
        """Free an instance slot (sapling built over, footprint chop).

        Returns True if the id existed and was removed.
        """
        rec = self._instance_lookup.pop(int(instance_id), None)
        if rec is None:
            return False
        model_path, slot = rec
        state = self._per_model.get(model_path)
        if state is None:
            return False
        state["alive"][slot] = False
        state["id"][slot] = 0
        tkey = state["tile"][slot]
        state["free_slots"].append(slot)
        try:
            state["active_slots"].remove(slot)
        except ValueError:
            pass
        state["dirty"] = True
        # Remove from tile lookup.
        bucket = self._instances_by_tile.get(tkey)
        if bucket is not None:
            try:
                bucket.remove(int(instance_id))
            except ValueError:
                pass
            if not bucket:
                self._instances_by_tile.pop(tkey, None)
        return True

    def set_fog_visibility(self, tile_xy: tuple[int, int], visible: bool) -> None:
        """Toggle whether instances on this tile are packed into the active buffer."""
        tkey = (int(tile_xy[0]), int(tile_xy[1]))
        prev = self._fog_visible_by_tile.get(tkey)
        new = bool(visible)
        if prev is new:
            return
        self._fog_visible_by_tile[tkey] = new
        # Any instances on this tile need a re-pack — mark their model dirty.
        bucket = self._instances_by_tile.get(tkey)
        if not bucket:
            return
        for iid in bucket:
            rec = self._instance_lookup.get(iid)
            if rec is None:
                continue
            model_path, _slot = rec
            state = self._per_model.get(model_path)
            if state is not None:
                state["dirty"] = True

    def set_visible_chunks(
        self,
        chunks: "set[tuple[int, int]] | frozenset[tuple[int, int]]",
        *,
        chunk_size: int = 16,
    ) -> None:
        """Update the camera-frustum chunk set used to filter the instance buffer.

        Called once per frame from ``cull_terrain_chunks`` BEFORE ``update_buffer``.
        ``chunk_size`` must match ``TERRAIN_CHUNK_SIZE`` for the per-instance
        chunk key derivation to line up with the rest of the renderer.

        Marks every per-model state dirty so ``update_buffer`` re-packs into the
        new chunk window. Cheap: just sets dict flags.
        """
        if chunk_size > 0:
            self._chunk_size = int(chunk_size)
        new_set: set[tuple[int, int]] = set()
        for c in chunks:
            new_set.add((int(c[0]), int(c[1])))
        if new_set == self._chunk_visible_set and self._chunk_filter_enabled:
            return
        self._chunk_visible_set = new_set
        self._chunk_filter_enabled = True
        for state in self._per_model.values():
            state["dirty"] = True

    def disable_chunk_filter(self) -> None:
        """Stop filtering by camera-chunk; pack all fog-visible instances.

        Used by tests / debug paths to confirm the chunk filter is responsible
        for any "missing trees" symptom.
        """
        if not self._chunk_filter_enabled:
            return
        self._chunk_filter_enabled = False
        self._chunk_visible_set.clear()
        for state in self._per_model.values():
            state["dirty"] = True

    def set_all_fog_visible(self) -> None:
        """Convenience for ``/revealmap``: mark every registered tile fog-visible.

        Avoids the caller iterating world.height * world.width tiles when the
        only state worth touching is the tiles that actually have trees.
        """
        for tkey in list(self._instances_by_tile.keys()):
            if not self._fog_visible_by_tile.get(tkey, False):
                self._fog_visible_by_tile[tkey] = True
                bucket = self._instances_by_tile.get(tkey, ())
                for iid in bucket:
                    rec = self._instance_lookup.get(iid)
                    if rec is None:
                        continue
                    model_path, _slot = rec
                    state = self._per_model.get(model_path)
                    if state is not None:
                        state["dirty"] = True

    # ---- per-frame upload ----------------------------------------------

    def update_buffer(self) -> dict:
        """Re-pack each dirty model's active-only slice into its buffer texture.

        Returns a small dict for telemetry ({model_path: active_count}) that the
        collab can surface via ``perf_render_benchmark.py``.

        Filtering layers (cheapest first):
          1. ``alive[slot]`` — slot is free, skip
          2. ``fog_visible[tile]`` — fog sync hasn't revealed this tile, skip
          3. ``chunk_visible_set`` — tile's chunk is outside the camera frustum
             (only when ``_chunk_filter_enabled`` is True; off by default until
             ``set_visible_chunks`` is called for the first time)
        """
        active_counts: dict[str, int] = {}
        chunk_size = self._chunk_size if self._chunk_size > 0 else 16
        chunk_filter_on = self._chunk_filter_enabled
        visible_chunks = self._chunk_visible_set

        for model_path, state in self._per_model.items():
            if not state["dirty"]:
                active_counts[model_path] = int(state.get("last_active_count", 0))
                continue

            buf: Texture = state["buffer_tex"]
            mv = memoryview(buf.modify_ram_image())

            count = 0
            cap = self._max_instances_per_model
            wx_arr = state["world_x"]
            wy_arr = state["world_y"]
            wz_arr = state["world_z"]
            sc_arr = state["scale"]
            tile_arr = state["tile"]
            fog = self._fog_visible_by_tile
            active_slots = state["active_slots"]

            # Walk the compact alive-slot list (~100 entries per model) instead
            # of every cap=1024 slot. ``register_tree`` / ``remove_tree`` keep
            # ``active_slots`` in sync.
            for slot in active_slots:
                tkey = tile_arr[slot]
                # Default: tile not yet seen by fog sync → leave OUT of buffer.
                # First fog sync after build will flip every registered tile's bit.
                if not fog.get(tkey, False):
                    continue
                if chunk_filter_on:
                    ckey = (tkey[0] // chunk_size, tkey[1] // chunk_size)
                    if ckey not in visible_chunks:
                        continue
                if count >= cap:
                    break
                struct.pack_into(
                    "ffff",
                    mv,
                    count * BYTES_PER_TEXEL,
                    wx_arr[slot],
                    wy_arr[slot],
                    wz_arr[slot],
                    sc_arr[slot],
                )
                count += 1

            try:
                state["geom_np"].set_instance_count(count)
            except Exception:
                pass
            try:
                buf.reload()
            except Exception:
                pass

            state["last_active_count"] = count
            state["dirty"] = False
            active_counts[model_path] = count

        return active_counts

    # ---- telemetry / inspection ----------------------------------------

    @property
    def model_count(self) -> int:
        return len(self._per_model)

    @property
    def total_active_count(self) -> int:
        return sum(int(s.get("last_active_count", 0)) for s in self._per_model.values())

    @property
    def total_registered_count(self) -> int:
        return len(self._instance_lookup)

    def per_model_active(self) -> dict[str, int]:
        return {mp: int(s.get("last_active_count", 0)) for mp, s in self._per_model.items()}

    def destroy(self) -> None:
        """Tear down NodePaths + buffer textures (used by tests / shutdown)."""
        for state in self._per_model.values():
            try:
                state["np"].remove_node()
            except Exception:
                pass
        self._per_model.clear()
        self._instance_lookup.clear()
        self._instances_by_tile.clear()
        self._fog_visible_by_tile.clear()
        self._next_instance_id = 1


# -------------------------------------------------------------------------
# Module-level helper for the collab
# -------------------------------------------------------------------------


def instanced_trees_env_enabled() -> bool:
    """Return True iff ``KINGDOM_URSINA_INSTANCED_TREES`` env var enables this path.

    Default is "1" (instancing ON) as of Wave 4 visual parity validation.
    Set to "0" explicitly for the A/B baseline / legacy fallback.
    """
    raw = os.environ.get("KINGDOM_URSINA_INSTANCED_TREES", "1")
    return str(raw).strip() in ("1", "true", "yes", "on")
