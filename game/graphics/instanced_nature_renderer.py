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
    OmniBoundingVolume,
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

in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;          /* per-vertex color baked into the Kenney GLBs */

/* Panda3D buffer texture from ``setup_buffer_texture(T_float, F_rgba32)`` → samplerBuffer. */
uniform samplerBuffer instanceData;

out vec3 v_normal_world;
out vec4 v_vertex_color;

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
    /* Kenney nature pack bakes the trunk/foliage colors into per-vertex colors
       rather than a material uniform. Pass through so the fragment stage can
       use them directly — no ``p3d_Material`` lookup needed (which only auto-
       populates under Panda's auto-shader-generator, NOT custom shaders). */
    v_vertex_color = p3d_Color;
}
""",
    fragment="""#version 330

in vec3 v_normal_world;
in vec4 v_vertex_color;

/* Per-model base color extracted from the GLB material at load time. The
   instanced renderer binds this once per model NodePath (16 trees in the
   Kenney pack ⇒ 16 distinct values). When the model has per-vertex colors
   baked, we multiply them with the model color so individual leaf / trunk
   tints survive; pure-material models render flat at the model color. */
uniform vec4 u_modelColor;

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

    /* Combine per-vertex (if any) with per-model color. Kenney GLBs typically
       don't bake vertex colors so ``v_vertex_color`` is white and the
       per-model uniform dominates; if a future asset bakes vertex tints they
       still modulate the per-model color correctly. */
    vec3 albedo = v_vertex_color.rgb * u_modelColor.rgb;
    float alpha = v_vertex_color.a * u_modelColor.a;
    fragColor = vec4(albedo * light, alpha);

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


def _load_geom_node_for_model(
    model_path: str,
) -> tuple[Optional[GeomNode], Optional[NodePath], tuple[float, float, float, float]]:
    """Resolve a tree model file into a Panda3D ``GeomNode`` plus its source NodePath.

    Uses Panda3D's loader rather than spinning up an Ursina ``Entity`` so we don't
    pay for an Entity per model in scene-entities. Returns ``(None, None, ...)``
    on failure so the caller can fall back to legacy individual-Entity rendering
    for that specific model.

    Returns:
        (geom_node, source_np, base_color):
          - ``geom_node``: the FIRST GeomNode found under the loaded model. Tree
            models in the Kenney pack are single-mesh; if a model has multiple
            GeomNodes we currently only use one — log a warning so we know.
          - ``source_np``: the loaded model NodePath, kept alive so the GeomNode's
            material/state references aren't garbage-collected.
          - ``base_color``: ``(r, g, b, a)`` extracted from the GLB material's
            base color (or ColorAttrib / per-geom material). Used as a per-model
            uniform input by the instanced shader because ``p3d_Material`` is NOT
            auto-bound for custom GLSL shaders (only for Panda's auto-shader
            generator path), and Kenney trees don't have ``p3d_Color`` baked.
            Falls back to ``(1, 1, 1, 1)`` if no material can be found — the
            shader will render the trees white in that case, which is at least
            visible (vs the cyan-defaults that come from an unbound struct).
    """
    fallback_color = (1.0, 1.0, 1.0, 1.0)
    try:
        from direct.showbase.Loader import Loader
        from panda3d.core import NodePath as _NP, ColorAttrib, MaterialAttrib

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
            return None, None, fallback_color
        # Ursina sometimes returns a NodePath; Panda3D loader returns a NodePath too.
        if not isinstance(loaded, _NP):
            loaded = _NP(loaded)

        # Find the first GeomNode under the loaded model.
        geom_paths = loaded.find_all_matches("**/+GeomNode")
        if geom_paths.get_num_paths() == 0:
            return None, None, fallback_color
        geom_np_loaded = geom_paths.get_path(0)
        geom_node = geom_np_loaded.node()
        if not isinstance(geom_node, GeomNode):
            return None, None, fallback_color

        # WK58 W7 BUG FIX (Agent 03): extract the per-model base color so the
        # instanced shader can use it as a uniform input. Panda3D's auto-shader
        # generator handles this automatically; custom shaders must bind the
        # material themselves. Kenney GLBs do not bake per-vertex colors.
        # Search up the model tree for any ColorAttrib (often added by the GLB
        # importer when a single base color exists) and any MaterialAttrib.
        base_color = fallback_color
        try:
            # First check the GeomNode's own state (per-geom render state).
            for gi in range(geom_node.get_num_geoms()):
                gs = geom_node.get_geom_state(gi)
                if gs.has_attrib(MaterialAttrib):
                    mat = gs.get_attrib(MaterialAttrib).get_material()
                    if mat is not None:
                        try:
                            bc = mat.get_base_color()
                        except Exception:
                            try:
                                bc = mat.get_diffuse()
                            except Exception:
                                bc = None
                        if bc is not None and (bc[0] or bc[1] or bc[2]):
                            base_color = (float(bc[0]), float(bc[1]), float(bc[2]), float(bc[3]) if len(bc) > 3 else 1.0)
                            break
                if gs.has_attrib(ColorAttrib):
                    ca = gs.get_attrib(ColorAttrib)
                    # ColorAttrib.T_flat: state-attached single color
                    try:
                        if ca.get_color_type() == ColorAttrib.T_flat:
                            c = ca.get_color()
                            base_color = (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
                            break
                    except Exception:
                        pass
        except Exception:
            pass
        # Also walk up the NodePath tree (some GLBs put ColorAttrib on the
        # parent node above the GeomNode).
        if base_color == fallback_color:
            try:
                walk = geom_np_loaded
                for _ in range(8):
                    if walk.is_empty():
                        break
                    state = walk.get_state()
                    if state.has_attrib(ColorAttrib):
                        ca = state.get_attrib(ColorAttrib)
                        try:
                            if ca.get_color_type() == ColorAttrib.T_flat:
                                c = ca.get_color()
                                base_color = (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
                                break
                        except Exception:
                            pass
                    if state.has_attrib(MaterialAttrib):
                        mat = state.get_attrib(MaterialAttrib).get_material()
                        if mat is not None:
                            try:
                                bc = mat.get_base_color()
                            except Exception:
                                try:
                                    bc = mat.get_diffuse()
                                except Exception:
                                    bc = None
                            if bc is not None and (bc[0] or bc[1] or bc[2]):
                                base_color = (float(bc[0]), float(bc[1]), float(bc[2]), float(bc[3]) if len(bc) > 3 else 1.0)
                                break
                    parent = walk.get_parent()
                    if parent.is_empty():
                        break
                    walk = parent
            except Exception:
                pass

        # WK58 W7 BUG FIX (Agent 03): bake per-geom material colors into a new
        # vertex-color column so the custom instanced shader can read
        # ``p3d_Color`` and produce the right trunk-vs-foliage tint per
        # triangle. Without this, a single per-model uniform can only paint
        # ONE color for the whole tree (some trees are 2-3 Geoms in a single
        # GeomNode — trunk + leaves + crown — each with its own material).
        try:
            _bake_per_geom_material_to_vertex_colors(geom_node)
        except Exception:
            pass

        return geom_node, loaded, base_color
    except Exception:
        return None, None, fallback_color


def _resolve_geom_color(geom_state) -> tuple[float, float, float, float]:
    """Pull the (r,g,b,a) base color off a Panda3D GeomState (material/color attribs)."""
    from panda3d.core import ColorAttrib as _CA, MaterialAttrib as _MA

    color = (1.0, 1.0, 1.0, 1.0)
    try:
        if geom_state.has_attrib(_MA):
            mat = geom_state.get_attrib(_MA).get_material()
            if mat is not None:
                bc = None
                try:
                    bc = mat.get_base_color()
                except Exception:
                    try:
                        bc = mat.get_diffuse()
                    except Exception:
                        bc = None
                if bc is not None:
                    r, g, b = float(bc[0]), float(bc[1]), float(bc[2])
                    a = float(bc[3]) if len(bc) > 3 else 1.0
                    if r or g or b:
                        color = (r, g, b, a)
                        return color
        if geom_state.has_attrib(_CA):
            ca = geom_state.get_attrib(_CA)
            try:
                if ca.get_color_type() == _CA.T_flat:
                    c = ca.get_color()
                    color = (float(c[0]), float(c[1]), float(c[2]), float(c[3]))
                    return color
            except Exception:
                pass
    except Exception:
        pass
    return color


def _bake_per_geom_material_to_vertex_colors(geom_node: GeomNode) -> None:
    """Rewrite every Geom inside ``geom_node`` so its vertex data has a per-vertex
    color column filled with the Geom's own material/ColorAttrib base color.

    This is a one-time mutation at load time. After it runs:
    - The vertex data exposes a ``color`` column (vec4 floats).
    - The custom instanced shader's ``in vec4 p3d_Color;`` reads the correct
      tint for every vertex — trunk vertices get the trunk material color,
      foliage vertices get the foliage material color, etc.

    Why this is needed: custom GLSL shaders cannot read ``p3d_Material``
    (Panda3D only auto-binds it in the auto-shader-generator path), and we
    can't use a single per-model uniform because a single GeomNode draw covers
    multiple Geoms with different materials.
    """
    from panda3d.core import (
        Geom as _Geom,
        GeomVertexArrayFormat as _AF,
        GeomVertexData as _VD,
        GeomVertexFormat as _VF,
        GeomVertexWriter as _VW,
        InternalName as _IN,
    )

    for gi in range(geom_node.get_num_geoms()):
        gs = geom_node.get_geom_state(gi)
        color = _resolve_geom_color(gs)
        geom = geom_node.modify_geom(gi)
        old_vd = geom.get_vertex_data()
        # If a color column already exists, just overwrite it.
        has_color = bool(old_vd.has_column(_IN.get_color()))
        if not has_color:
            # Build new format with the existing arrays + a separate color array.
            new_fmt = _VF(old_vd.get_format())
            af = _AF()
            af.add_column(
                _IN.get_color(),
                4,
                _Geom.NT_float32,
                _Geom.C_color,
            )
            new_fmt.add_array(af)
            registered = _VF.register_format(new_fmt)
            new_vd = old_vd.convert_to(registered)
            geom.set_vertex_data(new_vd)
            target_vd = geom.modify_vertex_data()
        else:
            target_vd = geom.modify_vertex_data()
        # Fill the color column for every vertex.
        cw = _VW(target_vd, _IN.get_color())
        cw.set_row(0)
        r, g, b, a = color
        num_rows = target_vd.get_num_rows()
        for _ in range(num_rows):
            cw.set_data4f(r, g, b, a)


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

        geom_node, source_np, base_color = _load_geom_node_for_model(model_path)
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
        # WK58 W7 BUG FIX (Agent 03): bind a neutral white per-model uniform.
        # The fragment shader reads ``vertex_color * u_modelColor``; the
        # ``_bake_per_geom_material_to_vertex_colors`` pass at load time already
        # bakes the correct trunk-vs-foliage tint into the per-vertex color,
        # so the model-level uniform stays white and only acts as a fallback
        # multiplier if a future asset wants to override globally.
        try:
            from panda3d.core import LVector4f
            geom_np.set_shader_input("u_modelColor", LVector4f(1.0, 1.0, 1.0, 1.0))
        except Exception:
            try:
                geom_np.set_shader_input("u_modelColor", (1.0, 1.0, 1.0, 1.0))
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
        # WK58 W7 BUG FIX (Agent 03): the loaded model's bounding sphere lives in
        # the model's LOCAL coord space (e.g. ``c (0, 0.6, 0), r 0.7``). With
        # hardware instancing, per-instance world positions are computed in the
        # vertex shader from a buffer texture — the GeomNode's local bounds tell
        # Panda3D nothing about where instances actually land in world space.
        # Result: Panda3D's view-frustum cull skips the entire GeomNode because
        # its bsphere is far from where the camera is pointing, even when 300+
        # instanced trees should be on-screen. Symptom: trees invisible at runtime.
        # Fix: install an OmniBoundingVolume so the cull pass always passes.
        # ``set_final(True)`` prevents Panda3D from auto-computing tighter bounds
        # from the mesh data on later traversals.
        try:
            gnode = geom_np.node()
            gnode.set_bounds(OmniBoundingVolume())
            gnode.set_final(True)
        except Exception:
            pass
        try:
            np.node().set_bounds(OmniBoundingVolume())
            np.node().set_final(True)
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

    def diagnostic_dump(self, label: str = "") -> None:
        """Print a one-line-per-model summary of the renderer state.

        Gated on ``KINGDOM_DIAG_INSTANCED_TREES=1`` to keep noise out of
        production logs. When the env var is set, ``UrsinaTerrainFogCollab``
        invokes this after ``build_3d_terrain`` and on each fog-revision
        change so the bug-search history is reproducible. To enable from a
        capture command:

        ``$env:KINGDOM_DIAG_INSTANCED_TREES = "1"; python main.py --renderer ursina``

        Originally written for WK58 Wave 7 (WK58-BUG-004 — invisible trees);
        kept in place so any future "trees stop rendering" regression can be
        diagnosed without recreating the scaffolding.
        """
        if os.environ.get("KINGDOM_DIAG_INSTANCED_TREES", "").strip() != "1":
            return
        try:
            from ursina import scene as _scene
        except Exception:
            _scene = None
        try:
            from direct.showbase.ShowBaseGlobal import base as _base  # type: ignore[attr-defined]
            render_root = getattr(_base, "render", None)
        except Exception:
            render_root = None
        print(f"[diag-trees] === {label} ===", flush=True)
        print(
            f"[diag-trees] total_registered={self.total_registered_count} "
            f"total_active={self.total_active_count} models={self.model_count} "
            f"chunk_filter_on={self._chunk_filter_enabled} "
            f"chunk_visible_count={len(self._chunk_visible_set)} "
            f"fog_visible_tiles={sum(1 for v in self._fog_visible_by_tile.values() if v)}",
            flush=True,
        )
        for mp, state in self._per_model.items():
            np = state["np"]
            geom_np = state["geom_np"]
            buf = state["buffer_tex"]
            num_alive = sum(1 for a in state["alive"] if a)
            try:
                np_parent = np.get_parent()
                np_parent_name = str(np_parent) if np_parent else "<no-parent>"
            except Exception:
                np_parent_name = "<err>"
            try:
                hidden = np.is_hidden()
            except Exception:
                hidden = "<err>"
            try:
                ic = geom_np.get_instance_count()
            except Exception:
                ic = "<err>"
            try:
                # Different Panda3D versions: has_shader / hasShader / get_shader
                sh_attr = geom_np.get_shader()
                has_shader = (sh_attr is not None)
            except Exception as e:
                try:
                    has_shader = f"getshader-err:{type(e).__name__}"
                except Exception:
                    has_shader = "<err>"
            # Also get the shader name if possible
            try:
                shader_state = geom_np.get_state()
                shader_state_str = str(shader_state).replace("\n", " ")[:120]
            except Exception:
                shader_state_str = "<state-err>"
            try:
                first_row = None
                mv = memoryview(buf.modify_ram_image())
                if num_alive > 0 and len(mv) >= 16:
                    first_row = struct.unpack_from("ffff", mv, 0)
            except Exception:
                first_row = None
            try:
                last_active_count = int(state.get("last_active_count", 0))
            except Exception:
                last_active_count = -1
            stem = Path(mp).stem
            # Inspect the geom node itself: how many geoms, how many vertices?
            try:
                gnode = state["geom_node"]
                num_geoms = gnode.get_num_geoms()
                total_verts = 0
                for gi in range(num_geoms):
                    gg = gnode.get_geom(gi)
                    total_verts += int(gg.get_vertex_data().get_num_rows())
                geom_info = f"geoms={num_geoms} verts={total_verts}"
            except Exception as e:
                geom_info = f"geom-info-err:{type(e).__name__}"
            # Inspect bounds — if instance_count > 0 but bounds are degenerate, that's the bug.
            try:
                bounds = geom_np.get_bounds()
                bounds_str = str(bounds).replace("\n", " ")[:80]
            except Exception:
                bounds_str = "<bounds-err>"
            print(
                f"[diag-trees] model={stem!r:32s} alive={num_alive:3d} "
                f"active_packed={last_active_count:3d} instance_count={ic} "
                f"shader={has_shader} hidden={hidden} parent={np_parent_name} "
                f"first_row={first_row}",
                flush=True,
            )
            print(
                f"[diag-trees]   state={shader_state_str} {geom_info} bounds={bounds_str}",
                flush=True,
            )

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
