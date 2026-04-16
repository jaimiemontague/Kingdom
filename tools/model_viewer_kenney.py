"""
Standalone Ursina model browser tailored exclusively for Kenney.nl GLB/GLTF assets.

This tool resolves issues with duplicate models by strictly filtering out
legacy .obj, .fbx, and .dae formats. It does **not** scan merged folders such as
``Models/GLB format/`` or ``Models/GLTF format/`` (same basenames appear in multiple
trees). Instead, GLB/GLTF are loaded only from:

  * ``assets/models/environment/`` — promoted in-game environment meshes
  * ``assets/models/Models/Kenny raw downloads (for exact paths)/kenney_*/`` —
    one grid per Kenney download pack (see ``kenney_assets_models_mapping.plan.md``)

Uses an improved lighting rig for vertex-colored low-poly geometry and the
Ursina EditorCamera for panning/orbiting. See
``.cursor/plans/kenney_gltf_ursina_integration_guide.md`` for shader/material
pitfalls.

Usage (from repo root):
  python tools/model_viewer_kenney.py
  python tools/model_viewer_kenney.py --max-total 120

Controls:
  Right-Click & Drag — Orbit camera
  Middle-Click & Drag — Pan camera
  Scroll Wheel — Zoom in / out
  ESC — Quit
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# We strictly exclude .obj, .dae, .fbx because Kenney distributes copies in every format.
# .glb natively embeds all textures cleanly without raw material errors.
MODEL_EXTS = {".glb", ".gltf"}

# Canonical Kenney sources (no merged GLB/GLTF trees — avoids duplicate basenames).
KENNEY_RAW_DOWNLOADS_DIR = "Kenny raw downloads (for exact paths)"
# Order matches ``kenney_assets_models_mapping.plan.md`` §1; folder names match disk.
# Cursor Pixel Pack last (far right): no GLB/GLTF in that download — keeps empty column out of the way.
KENNEY_PACKS_ORDERED: tuple[tuple[str, str], ...] = (
    ("kenney_blocky-characters_20", "Blocky Characters"),
    ("kenney_nature-kit", "Nature Kit"),
    ("kenney_retro-fantasy-kit", "Retro Fantasy Kit"),
    ("kenney_survival-kit", "Survival Kit"),
    ("kenney_cursor-pixel-pack", "Cursor Pixel Pack"),
)

# Layout (world units)
DEFAULT_CELL = 7.0
DEFAULT_PACK_GAP = 14.0
DEFAULT_MODEL_MAX_EXTENT = 5.0  # max axis-aligned size after uniform scale
LABEL_Y = 0.08
TEXT_SCALE = 13.0
PACK_TITLE_SCALE = 20.0
EMPTY_PACK_NOTE_SCALE = 11.0


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


def _collect_gltf_under(root: Path) -> list[Path]:
    """All .glb/.gltf under ``root`` (recursive)."""
    out: list[Path] = []
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in MODEL_EXTS:
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def collect_viewer_sections(assets_models: Path) -> tuple[list[tuple[str, list[Path]]], list[str]]:
    """Build ordered sections: promoted environment, then each Kenney raw download pack.

    GLB/GLTF are taken only from ``environment/`` and from each ``kenney_*`` folder
    under ``Models/Kenny raw downloads (for exact paths)/`` — not from merged
    ``Models/GLB format`` or ``Models/GLTF format`` (overlapping names).

    Returns (sections, warnings) where each section is (title, file paths).
    """
    sections: list[tuple[str, list[Path]]] = []
    warnings: list[str] = []

    env_dir = assets_models / "environment"
    env_files = _collect_gltf_under(env_dir)
    if env_files:
        sections.append(("Official environment", env_files))

    raw_root = assets_models / "Models" / KENNEY_RAW_DOWNLOADS_DIR
    if not raw_root.is_dir():
        warnings.append(
            f"Kenney raw downloads folder missing (expected): {raw_root} — "
            "Kenney pack grids skipped."
        )
        return sections, warnings

    for folder_name, title in KENNEY_PACKS_ORDERED:
        pack_dir = raw_root / folder_name
        if not pack_dir.is_dir():
            warnings.append(f"Kenney pack folder missing: {pack_dir}")
            sections.append((title, []))
            continue
        sections.append((title, _collect_gltf_under(pack_dir)))

    return sections, warnings


def _fit_uniform_and_ground(ent: Any, max_extent: float) -> None:
    """Uniform scale so max axis extent <= max_extent. Origin natively bottom-anchored."""
    try:
        from ursina import Vec3

        m = getattr(ent, "model", None)
        if m is None:
            return
        tb = m.getTightBounds()
        if not tb:
            return
        pmin, pmax = tb
        dx = float(pmax.x - pmin.x)
        dy = float(pmax.y - pmin.y)
        dz = float(pmax.z - pmin.z)
        size = max(dx, dy, dz, 1e-6)
        s = max_extent / size
        ent.scale = Vec3(s, s, s)
        # Note: Do NOT artificially translate ent.y using bounds. 
        # Ursina's Panda3D glTF pipeline natively exposes bounds with Z as height,
        # but places the mesh cleanly positioned at local Y=0 visually when spawned.
    except Exception:
        pass


def _pack_border_entity(
    *,
    ox: float,
    oz_top: float,
    width: float,
    depth: float,
    color,
) -> None:
    """Rectangle on XZ plane: from (ox, oz_top) extending toward -Z by depth."""
    from ursina import Entity, Mesh, Vec3, scene
    from ursina.shaders import unlit_shader

    y = 0.04
    verts = (
        Vec3(ox, y, oz_top),
        Vec3(ox + width, y, oz_top),
        Vec3(ox + width, y, oz_top - depth),
        Vec3(ox, y, oz_top - depth),
        Vec3(ox, y, oz_top),
    )

    Entity(
        parent=scene,
        model=Mesh(vertices=verts, mode="line", thickness=2.5),
        color=color,
        collision=False,
        shader=unlit_shader,
    )


def _setup_scene_lighting(*, center_x: float, center_z: float, span: float) -> None:
    """Studio-style wrap lighting: strong ambient + many weak directionals so orbit does not wash to black.

    A single bright key leaves back faces near zero Lambert term; camera orbit then looks 'all black'.
    Low per-directional intensity plus high ambient keeps normals visible from every viewing angle.
    """
    from ursina import AmbientLight, DirectionalLight, Vec3, color, scene

    focus = Vec3(center_x, 0.0, center_z)
    lift = max(48.0, span * 0.6)
    r = max(span * 0.85, 80.0)

    # Ambient provides shadow-fill so no face is pure black when orbiting.
    # Directionals provide the shading gradient that gives 3D depth.
    AmbientLight(parent=scene, color=color.rgba(0.42, 0.43, 0.48, 1.0))

    def _dir(pos: Vec3, col) -> None:
        d = DirectionalLight(parent=scene, shadows=False, color=col)
        d.position = pos
        d.look_at(focus)

    soft = 0.38
    cool = color.rgba(soft * 0.95, soft * 0.98, soft * 1.0, 1.0)
    warm = color.rgba(soft * 1.02, soft * 1.0, soft * 0.94, 1.0)
    neu = color.rgba(soft, soft, soft, 1.0)

    _dir(Vec3(center_x - r, lift, center_z), warm)       # -X
    _dir(Vec3(center_x + r, lift, center_z), cool)       # +X
    _dir(Vec3(center_x, lift, center_z - r), neu)        # -Z
    _dir(Vec3(center_x, lift, center_z + r), neu)        # +Z
    _dir(Vec3(center_x - r * 0.7, lift * 0.85, center_z - r * 0.7), warm)
    _dir(Vec3(center_x + r * 0.7, lift * 0.85, center_z + r * 0.7), cool)
    # Overhead bias (helps horizontal faces read when looking from above)
    _dir(Vec3(center_x, lift * 1.35, center_z), color.rgba(soft * 1.1, soft * 1.1, soft * 1.05, 1.0))


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
    fragColor = vec4(vColor.rgb * shade, vColor.a);
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

    Factor-only geoms (``baseColorFactor`` with no texture, no vertex color) get a
    lightweight custom lit shader that reads ``p3d_Color`` (from ``ColorAttrib``)
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
            node_has_flat = False

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
                        else:
                            bc = material_base_color(mat)
                            new_state = state.set_attrib(ColorAttrib.make_flat(bc))
                            branch = "flat"
                            local["flat"] += 1
                            node_has_flat = True

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

                if node_has_flat and factor_shader is not None:
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
        return local["flat"] > 0
    except Exception as exc:
        if aggregate_stats is not None:
            aggregate_stats.errors += 1
        if debug_materials:
            model_hdr = model_label or "<unknown>"
            print(f"[materials][error] {model_hdr} {exc!r}")
        return False


def _rel_for_label(assets_models: Path, fpath: Path) -> str:
    try:
        return str(fpath.relative_to(assets_models))
    except ValueError:
        return str(fpath)


def _truncate_label(s: str, max_len: int = 42) -> str:
    if len(s) <= max_len:
        return s
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return s[:head] + "..." + s[-tail:]


def _load_model_node_from_file(abs_path: Path) -> Any:
    """
    Load a glTF/glB mesh from disk using the gltf package natively.
    """
    import gltf
    import panda3d.core as p3d

    p = abs_path.resolve()
    if not p.is_file():
        return None
        
    try:
        gs = gltf.GltfSettings()
        gs.no_srgb = False
        model_root = gltf.load_model(str(p), gltf_settings=gs)
        if model_root is None:
            return None
        return p3d.NodePath(model_root)
    except Exception:
        return None


def run_viewer(
    *,
    assets_models: Path,
    cell: float,
    pack_gap: float,
    model_max_extent: float,
    max_total: int | None,
    debug_materials: bool,
) -> int:
    os.chdir(PROJECT_ROOT)

    sections, layout_warnings = collect_viewer_sections(assets_models)
    for w in layout_warnings:
        print(f"[model_viewer_kenney] Warning: {w}", file=sys.stderr)

    total_models = sum(len(files) for _, files in sections)
    if not sections or total_models == 0:
        print(f"[model_viewer_kenney] No .glb/.gltf models in viewer sections under: {assets_models}", file=sys.stderr)
        return 1

    # Flatten in section order; optional global cap for dev (--max-total)
    items: list[tuple[str, Path]] = []
    for pack_name, files in sections:
        for fpath in files:
            items.append((pack_name, fpath))
            if max_total is not None and len(items) >= max_total:
                break
        if max_total is not None and len(items) >= max_total:
            break

    if max_total is not None and len(items) < total_models:
        print(
            f"[model_viewer_kenney] Showing {len(items)} model(s) (--max-total={max_total}; out of {total_models}).",
            file=sys.stderr,
        )

    from ursina import (
        Entity,
        Text,
        Ursina,
        Vec3,
        application,
        camera,
        color,
        scene,
        window,
        EditorCamera
    )
    from ursina.shaders import unlit_shader
    from panda3d.core import LVecBase4f, getModelPath

    app = Ursina(
        title="Kingdom Sim — Kenney Model Viewer",
        borderless=False,
        fullscreen=False,
        development_mode=False,
    )
    
    application.asset_folder = Path(PROJECT_ROOT)
    getModelPath().append_directory(str(PROJECT_ROOT.resolve()))

    window.exit_button.visible = False
    window.fps_counter.enabled = True
    try:
        scene.clearFog()
        app.setBackgroundColor(LVecBase4f(0.12, 0.13, 0.15, 1))
    except Exception:
        pass

    # Large reference grid on XZ
    try:
        from ursina.models.procedural import Grid
        Entity(
            parent=scene,
            model=Grid(160, 160),
            rotation=(90, 0, 0),
            position=(0, 0, 0),
            scale=(6000, 1, 6000),
            color=color.rgba(0.22, 0.24, 0.28, 1),
            collision=False,
            shader=unlit_shader,
        )
    except Exception:
        pass

    # One column per section, in ``collect_viewer_sections`` order (incl. empty packs)
    pack_order = [title for title, _ in sections]
    pack_files: dict[str, list[Path]] = {title: [] for title in pack_order}
    for pack_name, fpath in items:
        if pack_name in pack_files:
            pack_files[pack_name].append(fpath)

    cursor_x = 0.0
    palette = (
        color.cyan,
        color.magenta,
        color.lime,
        color.yellow,
        color.orange,
        color.azure,
    )
    gallery_min_x = float("inf")
    gallery_max_x = float("-inf")
    gallery_min_z = float("inf")
    gallery_max_z = float("-inf")

    material_stats = MaterialDebugStats() if debug_materials else None

    for pi, pack_name in enumerate(pack_order):
        files = pack_files[pack_name]
        n = len(files)
        if n == 0:
            cols, rows = 1, 1
            pack_width = cell * 4.0
            pack_depth = cell * 3.0
        else:
            cols = max(1, int(math.ceil(math.sqrt(n))))
            rows = int(math.ceil(n / cols))
            pack_width = cols * cell
            pack_depth = rows * cell
        ox = cursor_x
        oz_top = 0.0
        border_col = palette[pi % len(palette)]

        _pack_border_entity(
            ox=ox,
            oz_top=oz_top,
            width=pack_width,
            depth=pack_depth,
            color=border_col,
        )

        cx = ox + pack_width * 0.5
        bottom_z = oz_top - pack_depth - 3.0
        Text(
            text=_truncate_label(pack_name, 56),
            parent=scene,
            position=(cx, LABEL_Y, bottom_z),
            scale=PACK_TITLE_SCALE,
            color=color.white,
            billboard=True,
            origin=(0, 0.5),
        )

        gallery_min_x = min(gallery_min_x, ox)
        gallery_max_x = max(gallery_max_x, ox + pack_width)
        gallery_min_z = min(gallery_min_z, bottom_z, oz_top - pack_depth)
        gallery_max_z = max(gallery_max_z, oz_top)

        if n == 0:
            empty_note = (
                "No GLB/GLTF in this pack (2D tilesheet only — see raw download)."
                if pack_name == "Cursor Pixel Pack"
                else "No GLB/GLTF found under this pack path."
            )
            Text(
                text=empty_note,
                parent=scene,
                position=(cx, LABEL_Y + 0.06, oz_top - pack_depth * 0.5),
                scale=EMPTY_PACK_NOTE_SCALE,
                color=color.light_gray,
                billboard=True,
                origin=(0, 0.5),
            )

        for i, fpath in enumerate(files):
            row = i // cols
            col = i % cols
            cx_i = ox + col * cell + cell * 0.5
            cz_i = oz_top - row * cell - cell * 0.5
            label_txt = _truncate_label(fpath.name)

            node = _load_model_node_from_file(fpath)
            if node is not None:
                ent = Entity(
                    parent=scene,
                    model=node,
                    collider=None,
                    double_sided=True,
                    position=(cx_i, 0.0, cz_i),
                )
                _fit_uniform_and_ground(ent, model_max_extent)
                _apply_gltf_color_and_shading(
                    ent.model,
                    debug_materials=debug_materials,
                    model_label=_rel_for_label(assets_models, fpath),
                    aggregate_stats=material_stats,
                )
            else:
                Entity(
                    parent=scene,
                    model="cube",
                    color=color.red,
                    position=(cx_i, model_max_extent * 0.5, cz_i),
                    scale=model_max_extent * 0.35,
                    shader=unlit_shader,
                )

            Text(
                text=label_txt,
                parent=scene,
                position=(cx_i, LABEL_Y + 0.02, cz_i - cell * 0.42),
                scale=TEXT_SCALE,
                color=color.light_gray,
                billboard=True,
                origin=(0, 0.5),
            )

        cursor_x += pack_width + pack_gap

    if debug_materials and material_stats is not None:
        print(
            "[model_viewer_kenney][materials][aggregate]"
            f" geoms={material_stats.geoms_total}"
            f" textured={material_stats.branch_textured}"
            f" textured_vertex={material_stats.branch_textured_vertex}"
            f" vertex={material_stats.branch_vertex}"
            f" flat={material_stats.branch_flat}"
            f" ambiguous_tex={material_stats.ambiguous_textured}"
            f" errors={material_stats.errors}"
        )

    # Editor Camera setup: overview of gallery
    if not math.isfinite(gallery_min_x) or gallery_min_x > gallery_max_x:
        gallery_min_x = gallery_max_x = 0.0
    if not math.isfinite(gallery_min_z) or gallery_min_z > gallery_max_z:
        gallery_min_z = gallery_max_z = 0.0
        
    center_x = (gallery_min_x + gallery_max_x) * 0.5
    center_z = (gallery_min_z + gallery_max_z) * 0.5
    span = max(gallery_max_x - gallery_min_x, gallery_max_z - gallery_min_z, cell * 3)
    
    _setup_scene_lighting(center_x=center_x, center_z=center_z, span=span)
    
    ec = EditorCamera()
    camera.fov = 50
    camera.clip_plane_near = 0.05
    camera.clip_plane_far = 50000.0
    elev = max(24.0, span * 0.42)
    back = max(34.0, span * 0.72)
    focus_y = max(1.5, model_max_extent * 0.45)
    
    ec.y = focus_y
    ec.x = center_x
    ec.z = center_z
    camera.position = Vec3(center_x, elev, center_z - back)
    ec.rotation_x = 35

    Text(
        text="Right-Drag orbit | Middle-Drag pan | Scroll zoom | ESC quit",
        position=(-0.86, 0.46),
        scale=1.05,
        color=color.white,
        background=True,
    )

    def input(key: str) -> None:
        if key == "escape":
            try:
                application.quit()
            except Exception:
                sys.exit(0)

    import __main__
    __main__.input = input

    app.run()
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Browse GLB/GLTF from assets/models/environment and from each Kenney pack under "
            "Models/Kenny raw downloads (for exact paths)/ (not merged GLB/GLTF folders)."
        ),
    )
    p.add_argument(
        "--assets-models",
        type=str,
        default=str(PROJECT_ROOT / "assets" / "models"),
        help="Root folder containing models (default: assets/models)",
    )
    p.add_argument("--cell", type=float, default=DEFAULT_CELL, help="Grid cell size in world units")
    p.add_argument("--pack-gap", type=float, default=DEFAULT_PACK_GAP, help="Horizontal gap between packs")
    p.add_argument(
        "--model-max-extent",
        type=float,
        default=DEFAULT_MODEL_MAX_EXTENT,
        help="Uniform scale cap (max axis length) per preview model",
    )
    p.add_argument(
        "--max-total",
        type=int,
        default=None,
        metavar="N",
        help="Load at most N models (dev/test; omit for full scan)",
    )
    p.add_argument(
        "--debug-materials",
        action="store_true",
        help="Print per-geom material classification and aggregate stats",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.assets_models).resolve()
    return run_viewer(
        assets_models=root,
        cell=float(args.cell),
        pack_gap=float(args.pack_gap),
        model_max_extent=float(args.model_max_extent),
        max_total=args.max_total,
        debug_materials=bool(args.debug_materials),
    )


if __name__ == "__main__":
    raise SystemExit(main())
