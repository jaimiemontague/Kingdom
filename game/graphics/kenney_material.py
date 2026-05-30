"""WK67 Round A-2 (L9): runtime-side Kenney material + pack-scale/tint helpers.

A packaged/frozen build cannot ship the dev ``tools/`` tree, but the Ursina render
paths (``ursina_environment``/``ursina_prefabs``) need the Kenney material-shading and
per-pack scale/tint logic to render the models correctly. This module is the new
**runtime home** for those load-bearing helpers; they were moved here VERBATIM from
``tools/model_viewer_kenney.py`` and ``tools/kenney_pack_scale.py`` (behavior is
byte-identical). The dev tools (``model_viewer_kenney``, ``kenney_pack_scale``,
``model_assembler_kenney``, ``wall_flush_pair_kenney``, …) re-import these symbols from
here — ``tools/`` → ``game.graphics`` is the allowed import direction.

Two groups live here:

1. **Material shading** (from ``tools/model_viewer_kenney.py``): ``MaterialDebugStats``,
   the ``_FACTOR_LIT_VERT`` / ``_FACTOR_LIT_FRAG`` shader strings, ``_get_factor_lit_shader``,
   and ``_apply_gltf_color_and_shading``. Deps: ``panda3d.core`` only.
2. **Pack scale + tint** (from ``tools/kenney_pack_scale.py``): the per-pack multiplier
   dicts, ``_norm_rel``, ``_load_merged_survival_only_basenames``, ``infer_kenney_pack_folder_id``,
   ``pack_extent_multiplier_for_rel``, ``pack_max_extent_for_rel``, ``pack_color_multiplier_for_rel``,
   and ``apply_kenney_pack_color_tint_to_entity``. Deps: ``ursina.color`` (lazy) + stdlib.

Calibration / tuning history (kept with the code so viewer/assembler/game stay aligned):
*Retro Fantasy Kit* is the **1.0** reference for both uniform-fit extent and albedo tint.
Non-Retro packs use extent multipliers 1.14/1.20/1.10 and an albedo tint of **0.75**
(~25% darker; WK32-BUG-005 retune 2026-04-18). Promoted ``environment/`` meshes match the
Nature Kit tint (0.75); ``environment/`` tree meshes use a slightly stronger **0.65**
(overridable via ``KINGDOM_ENV_TREE_COLOR_MULT``). See
``.cursor/plans/kenney_assets_models_mapping.plan.md`` §3.3 and
``.cursor/plans/kenney_gltf_ursina_integration_guide.md`` for the shader/material pitfalls.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Material shading (moved verbatim from tools/model_viewer_kenney.py)
# ---------------------------------------------------------------------------


@dataclass
class MaterialDebugStats:
    geoms_total: int = 0
    branch_textured: int = 0
    branch_textured_vertex: int = 0
    branch_vertex: int = 0
    branch_flat: int = 0
    ambiguous_textured: int = 0
    errors: int = 0

    def add_branch(self, branch: str, *, ambiguous: bool) -> None:
        self.geoms_total += 1
        if branch == "textured":
            self.branch_textured += 1
        elif branch == "textured_vertex":
            self.branch_textured_vertex += 1
        elif branch == "vertex":
            self.branch_vertex += 1
        elif branch == "flat":
            self.branch_flat += 1
        if ambiguous:
            self.ambiguous_textured += 1


_FACTOR_LIT_VERT = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat3 p3d_NormalMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec3 vNormal;
out vec4 vColor;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vNormal = normalize(p3d_NormalMatrix * p3d_Normal);
    vColor = p3d_Color;
}
"""

_FACTOR_LIT_FRAG = """
#version 150
uniform vec4 p3d_ColorScale;
in vec3 vNormal;
in vec4 vColor;
out vec4 fragColor;
void main() {
    vec3 N = normalize(vNormal);
    vec3 keyDir  = normalize(vec3( 0.4,  0.7, -0.5));
    vec3 fillDir = normalize(vec3(-0.3,  0.4,  0.6));
    float key  = max(dot(N, keyDir),  0.0);
    float fill = max(dot(N, fillDir), 0.0);
    float shade = 0.38 + 0.48 * key + 0.18 * fill;
    fragColor = vec4(vColor.rgb * p3d_ColorScale.rgb * shade, vColor.a * p3d_ColorScale.a);
}
"""

_factor_lit_shader_cache: list[Any] = []


def _get_factor_lit_shader() -> Any:
    if _factor_lit_shader_cache:
        return _factor_lit_shader_cache[0]
    from panda3d.core import Shader
    s = Shader.make(Shader.SL_GLSL, vertex=_FACTOR_LIT_VERT, fragment=_FACTOR_LIT_FRAG)
    _factor_lit_shader_cache.append(s)
    return s


def _apply_gltf_color_and_shading(
    root: Any,
    *,
    debug_materials: bool = False,
    model_label: str = "",
    aggregate_stats: MaterialDebugStats | None = None,
) -> bool:
    """Classify each geom and select the correct shading path.

    Textured geoms keep Ursina's default unlit shader (textures carry visual detail).

    Non-textured geoms (``baseColorFactor`` or vertex colors, with no texture) get
    a lightweight custom lit shader that reads ``p3d_Color`` (from ``ColorAttrib``)
    and applies key+fill Lambert lighting via vertex normals.  This avoids both the
    flat-unlit look **and** the ``setShaderAuto`` black-silhouette regression.

    Returns True if any geom was factor-only (i.e. lit shading was enabled).
    """
    try:
        from panda3d.core import (
            ColorAttrib,
            GeomNode,
            InternalName,
            LColor,
            MaterialAttrib,
            TextureAttrib,
        )

        if root is None or root.isEmpty():
            return False

        def state_has_base_texture(state: Any) -> tuple[bool, str]:
            ta = state.get_attrib(TextureAttrib.get_class_type())
            if not ta:
                return False, "no-texture-attrib"
            for j in range(ta.get_num_on_stages()):
                st = ta.get_on_stage(j)
                tex = ta.get_on_texture(st)
                if tex is not None:
                    return True, st.get_name() or "<unnamed>"
            return False, "no-stages-with-texture"

        def material_base_color(mat: Any) -> Any:
            if mat is None:
                return LColor(1, 1, 1, 1)
            try:
                if mat.has_base_color():
                    return mat.get_base_color()
            except Exception:
                pass
            try:
                return mat.get_diffuse()
            except Exception:
                return LColor(1, 1, 1, 1)

        factor_shader = _get_factor_lit_shader()

        local = {
            "geoms": 0,
            "textured": 0,
            "textured_vertex": 0,
            "vertex": 0,
            "flat": 0,
        }

        def walk(np: Any) -> None:
            node = np.node()
            node_needs_lit_shader = False

            if isinstance(node, GeomNode):
                for gi in range(node.get_num_geoms()):
                    local["geoms"] += 1
                    geom = node.get_geom(gi)
                    state = node.get_geom_state(gi)
                    vdata = geom.get_vertex_data()
                    fmt = vdata.get_format() if vdata else None
                    has_vcolor = bool(fmt and fmt.has_column(InternalName.get_color()))

                    ma = state.get_attrib(MaterialAttrib.get_class_type())
                    mat = ma.get_material() if ma else None
                    has_tex, tex_reason = state_has_base_texture(state)
                    branch = "flat"

                    if has_tex:
                        if has_vcolor:
                            new_state = state.set_attrib(ColorAttrib.make_vertex())
                            branch = "textured_vertex"
                            local["textured_vertex"] += 1
                        else:
                            new_state = state
                            branch = "textured"
                            local["textured"] += 1
                    else:
                        if has_vcolor:
                            new_state = state.set_attrib(ColorAttrib.make_vertex())
                            branch = "vertex"
                            local["vertex"] += 1
                            node_needs_lit_shader = True
                        else:
                            bc = material_base_color(mat)
                            new_state = state.set_attrib(ColorAttrib.make_flat(bc))
                            branch = "flat"
                            local["flat"] += 1
                            node_needs_lit_shader = True

                    if aggregate_stats is not None:
                        aggregate_stats.add_branch(branch, ambiguous=False)

                    node.set_geom_state(gi, new_state)
                    if debug_materials:
                        model_hdr = model_label or "<unknown>"
                        print(
                            f"[materials] {model_hdr} geom={gi}"
                            f" branch={branch} tex={tex_reason}"
                            f" vcolor={has_vcolor}"
                        )

                if node_needs_lit_shader and factor_shader is not None:
                    np.setShader(factor_shader)

            for i in range(np.getNumChildren()):
                walk(np.getChild(i))

        walk(root)
        if debug_materials:
            model_hdr = model_label or "<unknown>"
            print(
                f"[materials][summary] {model_hdr}"
                f" geoms={local['geoms']}"
                f" textured={local['textured']}"
                f" textured_vertex={local['textured_vertex']}"
                f" vertex={local['vertex']}"
                f" flat={local['flat']}"
            )
        return (local["flat"] + local["vertex"]) > 0
    except Exception as exc:
        if aggregate_stats is not None:
            aggregate_stats.errors += 1
        if debug_materials:
            model_hdr = model_label or "<unknown>"
            print(f"[materials][error] {model_hdr} {exc!r}")
        return False


# ---------------------------------------------------------------------------
# Pack scale + tint policy (moved verbatim from tools/kenney_pack_scale.py)
# ---------------------------------------------------------------------------

# Grid fit reference: uniform-fit target (max axis length after fit) for Retro.
RETRO_REFERENCE_MAX_EXTENT = 5.0

# Per top-level Kenney raw-download folder id (under
# ``Models/Kenny raw downloads (for exact paths)/``). Values are multipliers on
# ``RETRO_REFERENCE_MAX_EXTENT`` for the viewer's uniform fit, and uniform scale on
# prefab pieces at runtime (relative to Retro).
_PACK_EXTENT_MULTIPLIER_BY_FOLDER: dict[str, float] = {
    "kenney_retro-fantasy-kit": 1.0,
    "kenney_survival-kit": 1.14,
    "kenney_nature-kit": 1.20,
    "kenney_fantasy-town-kit_2.0": 1.10,
    "kenney_graveyard-kit_5.0": 1.10,
    "kenney_blocky-characters_20": 1.0,
    "kenney_cursor-pixel-pack": 1.0,
}

# WK32: RGB multiplier vs Retro (1.0 = unchanged). Applied as Ursina ``Entity.color``
# modulate after ``_apply_gltf_color_and_shading`` (viewer, assembler, game).
# WK32-BUG-005 retune (2026-04-18): 0.60 was too strong -> **0.75** (~25% darker vs Retro).
_PACK_COLOR_MULTIPLIER_BY_FOLDER: dict[str, float] = {
    "kenney_retro-fantasy-kit": 1.0,
    "kenney_survival-kit": 0.75,
    "kenney_nature-kit": 0.75,
    "kenney_fantasy-town-kit_2.0": 0.75,
    "kenney_graveyard-kit_5.0": 0.75,
    "kenney_blocky-characters_20": 0.75,
    "kenney_cursor-pixel-pack": 1.0,
}

# WK32 r4: Some promoted environment trees (eg tree_meadow_*.obj) still read too bright
# even after the global environment/Nature tint. Apply a slightly stronger multiplier
# for environment tree models only. Can be overridden for quick tuning without code edits.
_ENV_TREE_COLOR_MULTIPLIER_DEFAULT = 0.65

# Merged ``Models/GLB format`` mixes Retro + Survival (+ suffixed FT/GY); unsuffixed
# names default to Retro (1.0) except as resolved below (WK31 Agent 15 + mapping §3.3).
_MERGED_GLB_DEFAULT_MULTIPLIER = 1.0

# Basenames that appear **only** in ``kenney_survival-kit`` (not in Retro raw GLB list).
# Computed at import from ``assets/models/.../Kenny raw downloads`` when present.
_SURVIVAL_RAW_GLB: Path | None = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "models"
    / "Models"
    / "Kenny raw downloads (for exact paths)"
    / "kenney_survival-kit"
    / "Models"
    / "GLB format"
)
_RETRO_RAW_GLB: Path | None = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "models"
    / "Models"
    / "Kenny raw downloads (for exact paths)"
    / "kenney_retro-fantasy-kit"
    / "Models"
    / "GLB format"
)


def _load_merged_survival_only_basenames() -> frozenset[str]:
    """Filenames in Survival but not Retro — merged ``Models/GLB format`` uses Survival bytes."""
    try:
        if _SURVIVAL_RAW_GLB is None or _RETRO_RAW_GLB is None:
            return frozenset()
        if not _SURVIVAL_RAW_GLB.is_dir() or not _RETRO_RAW_GLB.is_dir():
            return frozenset()
        sset = {p.name.lower() for p in _SURVIVAL_RAW_GLB.glob("*.glb")}
        rset = {p.name.lower() for p in _RETRO_RAW_GLB.glob("*.glb")}
        return frozenset(sset - rset)
    except OSError:
        return frozenset()


_MERGED_SURVIVAL_ONLY_BASENAMES = _load_merged_survival_only_basenames()

# Retro–Survival filename collisions: which pack's copy lives in merged ``Models/GLB format``.
# See ``kenney_assets_models_mapping.plan.md`` §3.3.
_MERGED_COLLISION_PACK: dict[str, str] = {
    "fence.glb": "retro",
    "floor.glb": "survival",
    "structure.glb": "survival",
}


def _norm_rel(rel: str) -> str:
    return str(rel).replace("\\", "/").lstrip("/")


def infer_kenney_pack_folder_id(rel: str) -> str | None:
    """Best-effort pack id string for logs / attribution hints (not always unique)."""
    r = _norm_rel(rel)
    parts = tuple(Path(r).parts)
    raw_mark = "Kenny raw downloads (for exact paths)"
    if raw_mark in parts:
        i = parts.index(raw_mark)
        if i + 1 < len(parts):
            return parts[i + 1]
    name = Path(r).name.lower()
    if name.endswith("-fantasy-town.glb") or name.endswith("-fantasy-town.gltf"):
        return "kenney_fantasy-town-kit_2.0"
    if name.endswith("-graveyard.glb") or name.endswith("-graveyard.gltf"):
        return "kenney_graveyard-kit_5.0"
    stem = Path(name).stem
    if stem.startswith("character-") and len(stem) == len("character-x"):
        return "kenney_blocky-characters_20"
    if r.startswith("environment/"):
        return None
    if r.startswith("Models/GLB format/"):
        return "__merged_glb__"
    if r.startswith("Models/GLTF format/"):
        return "kenney_nature-kit"
    return None


def pack_extent_multiplier_for_rel(rel: str) -> float:
    """Uniform extent/scale multiplier vs Retro (1.0 = Retro Fantasy calibration)."""
    r = _norm_rel(rel)
    if not r:
        return 1.0
    if r.startswith("environment/"):
        return 1.0

    parts = tuple(Path(r).parts)
    raw_mark = "Kenny raw downloads (for exact paths)"
    if raw_mark in parts:
        i = parts.index(raw_mark)
        if i + 1 < len(parts):
            folder = parts[i + 1]
            return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER.get(folder, 1.0))

    name = Path(r).name
    nl = name.lower()
    if nl.endswith("-fantasy-town.glb") or nl.endswith("-fantasy-town.gltf"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_fantasy-town-kit_2.0"])
    if nl.endswith("-graveyard.glb") or nl.endswith("-graveyard.gltf"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_graveyard-kit_5.0"])

    stem_l = Path(nl).stem
    if stem_l.startswith("character-") and len(stem_l) == len("character-x"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_blocky-characters_20"])

    if r.startswith("Models/GLB format/"):
        bn = Path(r).name.lower()
        if bn in _MERGED_COLLISION_PACK:
            side = _MERGED_COLLISION_PACK[bn]
            if side == "survival":
                return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_survival-kit"])
            return float(_MERGED_GLB_DEFAULT_MULTIPLIER)
        if bn in _MERGED_SURVIVAL_ONLY_BASENAMES:
            return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_survival-kit"])
        return float(_MERGED_GLB_DEFAULT_MULTIPLIER)
    if r.startswith("Models/GLTF format/"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_nature-kit"])

    return 1.0


def pack_max_extent_for_rel(rel: str, *, base_max_extent: float = RETRO_REFERENCE_MAX_EXTENT) -> float:
    """Max axis length after uniform fit (viewer / wall-flush tools)."""
    return float(base_max_extent) * pack_extent_multiplier_for_rel(rel)


def pack_color_multiplier_for_rel(rel: str) -> float:
    """Per-pack albedo tint vs Retro (1.0 = no darkening). Mirrors ``pack_extent_multiplier_for_rel`` routing."""
    r = _norm_rel(rel)
    # Ursina ``Entity(model="assets/models/...")`` passes full repo-relative paths; prefab pieces use ``Models/...``.
    if r.startswith("assets/models/"):
        r = r[len("assets/models/") :]
    if not r:
        return 1.0
    # Promoted env/ meshes (grass, tree_pine, etc.) match Nature Kit albedo — same tint as GLTF path.
    if r.startswith("environment/"):
        env_base = float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_nature-kit"])
        name = Path(r).name.lower()
        if name.startswith("tree_"):
            try:
                m = float(os.getenv("KINGDOM_ENV_TREE_COLOR_MULT", str(_ENV_TREE_COLOR_MULTIPLIER_DEFAULT)))
            except Exception:
                m = _ENV_TREE_COLOR_MULTIPLIER_DEFAULT
            return max(0.0, min(env_base, float(m)))
        return env_base

    parts = tuple(Path(r).parts)
    raw_mark = "Kenny raw downloads (for exact paths)"
    if raw_mark in parts:
        i = parts.index(raw_mark)
        if i + 1 < len(parts):
            folder = parts[i + 1]
            return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER.get(folder, 1.0))

    name = Path(r).name
    nl = name.lower()
    if nl.endswith("-fantasy-town.glb") or nl.endswith("-fantasy-town.gltf"):
        return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_fantasy-town-kit_2.0"])
    if nl.endswith("-graveyard.glb") or nl.endswith("-graveyard.gltf"):
        return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_graveyard-kit_5.0"])

    stem_l = Path(nl).stem
    if stem_l.startswith("character-") and len(stem_l) == len("character-x"):
        return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_blocky-characters_20"])

    if r.startswith("Models/GLB format/"):
        bn = Path(r).name.lower()
        if bn in _MERGED_COLLISION_PACK:
            side = _MERGED_COLLISION_PACK[bn]
            if side == "survival":
                return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_survival-kit"])
            return 1.0
        if bn in _MERGED_SURVIVAL_ONLY_BASENAMES:
            return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_survival-kit"])
        return 1.0
    if r.startswith("Models/GLTF format/"):
        return float(_PACK_COLOR_MULTIPLIER_BY_FOLDER["kenney_nature-kit"])

    return 1.0


def apply_kenney_pack_color_tint_to_entity(entity: Any, rel: str) -> None:
    """WK32: modulate ``Entity.color`` by ``pack_color_multiplier_for_rel`` (lazy Ursina import)."""
    m = float(pack_color_multiplier_for_rel(rel))
    if m >= 0.9999:
        return
    try:
        from ursina import color as uc

        entity.color = uc.rgb(m, m, m)
    except Exception:
        pass
