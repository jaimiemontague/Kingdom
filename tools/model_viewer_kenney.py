"""
Standalone Ursina model browser tailored exclusively for Kenney.nl GLB/GLTF assets.

This tool resolves issues with duplicate models by strictly filtering out
legacy .obj, .fbx, and .dae formats. It organizes them logically by their
top-level folder under assets/models, utilizes an improved lighting rig to 
properly display vertex-colored low-poly geometries without black shadows,
and implements the Ursina EditorCamera for improved panning/orbiting controls.

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
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# We strictly exclude .obj, .dae, .fbx because Kenney distributes copies in every format.
# .glb natively embeds all textures cleanly without raw material errors.
MODEL_EXTS = {".glb", ".gltf"}

# Layout (world units)
DEFAULT_CELL = 7.0
DEFAULT_PACK_GAP = 14.0
DEFAULT_MODEL_MAX_EXTENT = 5.0  # max axis-aligned size after uniform scale
LABEL_Y = 0.08
TEXT_SCALE = 13.0
PACK_TITLE_SCALE = 20.0


def scan_packs(assets_models: Path) -> dict[str, list[Path]]:
    """Group model files by their top-level subfolder inside assets/models."""
    packs: dict[str, list[Path]] = defaultdict(list)
    if not assets_models.is_dir():
        return dict(packs)
        
    for p in assets_models.rglob("*"):
        if p.is_file() and p.suffix.lower() in MODEL_EXTS:
            try:
                # Group by top level dir under assets_models (e.g. 'environment', 'heroes')
                rel = p.relative_to(assets_models)
                pack_name = rel.parts[0] if len(rel.parts) > 1 else "Root"
            except ValueError:
                pack_name = "Unknown"
                
            packs[pack_name].append(p)
            
    # Sort files within each pack
    for k in packs:
        packs[k] = sorted(packs[k], key=lambda x: str(x).lower())
        
    return dict(packs)


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

    # Strong hemispheric fill — primary fix for 'one lit stripe, rest black' when orbiting.
    AmbientLight(parent=scene, color=color.rgba(0.82, 0.83, 0.86, 1.0))

    def _dir(pos: Vec3, col) -> None:
        d = DirectionalLight(parent=scene, shadows=False, color=col)
        d.position = pos
        d.look_at(focus)

    # Weak directionals from several compass points + above (wrap, not a single 'sun').
    soft = 0.22
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
) -> int:
    os.chdir(PROJECT_ROOT)

    packs = scan_packs(assets_models)
    if not packs:
        print(f"[model_viewer_kenney] No .glb/.gltf models found under: {assets_models}", file=sys.stderr)
        return 1

    # Flatten with stable pack order
    items: list[tuple[str, Path]] = []
    for pack_name in sorted(packs.keys(), key=lambda s: s.lower()):
        for fpath in packs[pack_name]:
            items.append((pack_name, fpath))
            if max_total is not None and len(items) >= max_total:
                break
        if max_total is not None and len(items) >= max_total:
            break

    total_models = sum(len(v) for v in packs.values())
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
        sys,
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

    # Group items back by pack for layout
    pack_order: list[str] = []
    pack_files: dict[str, list[Path]] = {}
    for pack_name, fpath in items:
        if pack_name not in pack_files:
            pack_order.append(pack_name)
            pack_files[pack_name] = []
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

    for pi, pack_name in enumerate(pack_order):
        files = pack_files[pack_name]
        n = len(files)
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
                # Do not call setShaderAuto(): it replaces glTF/PBR materials and can yield wrong shading.
                _fit_uniform_and_ground(ent, model_max_extent)
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
    p = argparse.ArgumentParser(description="Browse Kenney.nl models under assets/models in Ursina.")
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
    )


if __name__ == "__main__":
    raise SystemExit(main())
