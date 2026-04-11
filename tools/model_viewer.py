"""
Standalone Ursina model browser for assets under assets/models/.

Scans each immediate subfolder of assets/models as a "pack", lays out all
.glb / .gltf / .obj files on a ground grid, draws a border per pack, and
labels pack + file names.

Usage (from repo root):
  python tools/model_viewer.py
  python tools/model_viewer.py --max-total 120

Controls:
  WASD     — pan on the XZ plane (W = +world Z, S = -world Z, A/D = X)
  Mouse wheel, +/-, Q/E — zoom (field of view)
  ESC      — quit
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_EXTS = {".glb", ".gltf", ".obj"}

# Layout (world units)
DEFAULT_CELL = 7.0
DEFAULT_PACK_GAP = 14.0
DEFAULT_MODEL_MAX_EXTENT = 5.0  # max axis-aligned size after uniform scale
LABEL_Y = 0.08
TEXT_SCALE = 6.0
PACK_TITLE_SCALE = 9.0


def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def scan_packs(assets_models: Path) -> dict[str, list[Path]]:
    """Group model files by top-level folder under assets/models."""
    packs: dict[str, list[Path]] = {}
    if not assets_models.is_dir():
        return packs
    for child in sorted(assets_models.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        found: list[Path] = []
        for p in child.rglob("*"):
            if p.is_file() and p.suffix.lower() in MODEL_EXTS:
                found.append(p)
        if found:
            packs[child.name] = sorted(found, key=lambda x: str(x).lower())
    return packs


def _fit_uniform_and_ground(ent: Any, max_extent: float) -> None:
    """Uniform scale so max axis extent <= max_extent; sit bottom on y=0."""
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
        # After scale, lift so lowest point touches y=0 (model-local bounds).
        tb2 = m.getTightBounds()
        if tb2:
            pmin2, _pmax2 = tb2
            ent.y = float(-pmin2.y * ent.scale_y)
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

    # Closed loop slightly above ground so z-fighting is rare.
    y = 0.04
    verts = (
        Vec3(ox, y, oz_top),
        Vec3(ox + width, y, oz_top),
        Vec3(ox + width, y, oz_top - depth),
        Vec3(ox, y, oz_top - depth),
        Vec3(ox, y, oz_top),
    )
    from ursina.shaders import unlit_shader

    Entity(
        parent=scene,
        model=Mesh(vertices=verts, mode="line", thickness=2.5),
        color=color,
        collision=False,
        shader=unlit_shader,
    )


def _truncate_label(s: str, max_len: int = 42) -> str:
    if len(s) <= max_len:
        return s
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return s[:head] + "..." + s[-tail:]


def _load_model_node_from_file(abs_path: Path) -> Any:
    """
    Load a mesh from disk.

    glTF / glB must use the ``gltf`` package (``gltf.load_model``). Passing a Windows
    absolute path string to ``loader.loadModel`` does not register on Panda's model
    path, so the loader fails and spams ``C:\\Users\\...`` in the console.

    ``.obj`` uses ``Filename.fromOsSpecific`` so Panda resolves the file without
    relying on model-path search.
    """
    import gltf
    import panda3d.core as p3d
    from panda3d.core import Filename
    from ursina import application

    p = abs_path.resolve()
    if not p.is_file():
        return None
    ext = p.suffix.lower()
    try:
        if ext in (".glb", ".gltf"):
            gs = gltf.GltfSettings()
            gs.no_srgb = bool(getattr(application, "gltf_no_srgb", True))
            model_root = gltf.load_model(str(p), gltf_settings=gs)
            if model_root is None:
                return None
            return p3d.NodePath(model_root)

        if ext == ".obj":
            fn = Filename.fromOsSpecific(str(p))
            np = application.base.loader.loadModel(fn)
            if np is not None and not np.isEmpty():
                return np
            from ursina.mesh_importer import obj_to_ursinamesh

            return obj_to_ursinamesh(folder=p.parent, name=p.stem, return_mesh=True)
    except Exception:
        return None
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
        print(f"[model_viewer] No model files found under: {assets_models}", file=sys.stderr)
        return 1

    # Flatten with stable pack order, optional cap
    items: list[tuple[str, Path]] = []
    for pack_name in sorted(packs.keys(), key=lambda s: s.lower()):
        for fpath in packs[pack_name]:
            items.append((pack_name, fpath))
            if max_total is not None and len(items) >= max_total:
                break
        if max_total is not None and len(items) >= max_total:
            break

    if max_total is not None and len(items) < sum(len(v) for v in packs.values()):
        print(
            f"[model_viewer] Showing {len(items)} model(s) (--max-total={max_total}; not all files).",
            file=sys.stderr,
        )
    elif max_total is None and len(items) > 400:
        print(
            "[model_viewer] Loading many models; first open can take a while. "
            "Use --max-total N for a quicker subset.",
            file=sys.stderr,
        )

    from ursina import (
        AmbientLight,
        DirectionalLight,
        Entity,
        Mesh,
        Text,
        Ursina,
        Vec3,
        application,
        camera,
        color,
        held_keys,
        scene,
        time,
        window,
    )
    from ursina.shaders import unlit_shader
    from panda3d.core import LVecBase4f, getModelPath

    app = Ursina(
        title="Kingdom Sim — Model Viewer",
        borderless=False,
        fullscreen=False,
        development_mode=False,
    )
    # Default asset folder is Path(sys.argv[0]).parent → tools/ when run as tools/model_viewer.py.
    # Point at repo root so embedded texture paths and our layout stay consistent with the game.
    application.asset_folder = Path(PROJECT_ROOT)
    getModelPath().append_directory(str(PROJECT_ROOT.resolve()))

    window.exit_button.visible = False
    window.fps_counter.enabled = True
    Entity.default_shader = unlit_shader
    try:
        scene.clearFog()
    except Exception:
        pass
    try:
        app.setBackgroundColor(LVecBase4f(0.06, 0.07, 0.09, 1))
    except Exception:
        pass

    AmbientLight(color=color.rgba(0.38, 0.4, 0.46, 1))
    DirectionalLight(direction=(0.35, -1.0, -0.25), shadows=False)

    # Large reference grid on XZ (Grid mesh is authored in XY; rotate to floor)
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
        Entity(
            parent=scene,
            model="quad",
            scale=(12000, 12000, 1),
            rotation=(90, 0, 0),
            position=(0, 0, 0),
            color=color.rgb(0.15, 0.16, 0.18),
            collision=False,
            shader=unlit_shader,
        )

    # Group items back by pack for layout (preserve order within pack)
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
        color.violet,
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

        # Pack title below bottom edge of rectangle (toward -Z)
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

        pack_root = assets_models / pack_name
        for i, fpath in enumerate(files):
            row = i // cols
            col = i % cols
            cx_i = ox + col * cell + cell * 0.5
            cz_i = oz_top - row * cell - cell * 0.5
            rel_game = _rel_posix(fpath, PROJECT_ROOT).replace("\\", "/")
            label_txt = _truncate_label(_rel_posix(fpath, pack_root))

            node = _load_model_node_from_file(fpath)
            if node is not None:
                ext_l = fpath.suffix.lower()
                ent = Entity(
                    parent=scene,
                    model=node,
                    collider=None,
                    double_sided=True,
                    position=(cx_i, 0.0, cz_i),
                )
                if ext_l in (".gltf", ".glb"):
                    ent.model.setShaderAuto()
                _fit_uniform_and_ground(ent, model_max_extent)
            else:
                print(f"[model_viewer] Failed to load: {rel_game}", file=sys.stderr)
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

    # Camera: overview of gallery
    if not math.isfinite(gallery_min_x) or gallery_min_x > gallery_max_x:
        gallery_min_x = gallery_max_x = 0.0
    if not math.isfinite(gallery_min_z) or gallery_min_z > gallery_max_z:
        gallery_min_z = gallery_max_z = 0.0
    center_x = (gallery_min_x + gallery_max_x) * 0.5
    center_z = (gallery_min_z + gallery_max_z) * 0.5
    span = max(gallery_max_x - gallery_min_x, gallery_max_z - gallery_min_z, cell * 3)
    camera.orthographic = False
    camera.fov = 52
    camera.clip_plane_near = 0.05
    camera.clip_plane_far = 50000.0
    elev = max(35.0, span * 0.55)
    back = max(45.0, span * 0.75)
    camera.position = Vec3(center_x, elev, center_z + back)
    camera.look_at(Vec3(center_x, 0.0, center_z))

    Text(
        text="WASD pan | Wheel / +/- / Q E zoom | ESC quit",
        position=(-0.86, 0.46),
        scale=1.05,
        color=color.white,
        background=True,
    )

    pan_speed = 52.0

    def input(key: str) -> None:
        if key == "escape":
            try:
                application.quit()
            except Exception:
                sys.exit(0)
        if key in ("scroll up", "mouse4"):
            camera.fov = max(10.0, float(camera.fov) - 2.0)
        if key in ("scroll down", "mouse5"):
            camera.fov = min(110.0, float(camera.fov) + 2.0)

    import __main__

    __main__.input = input

    def update() -> None:
        dt = time.dt
        hk = held_keys
        if hk["a"]:
            camera.x -= pan_speed * dt
        if hk["d"]:
            camera.x += pan_speed * dt
        if hk["w"]:
            camera.z += pan_speed * dt
        if hk["s"]:
            camera.z -= pan_speed * dt
        # Zoom keys (match game-adjacent feel)
        rate = 3.2 * dt
        zstep = 1.045
        if hk.get("e", 0):
            camera.fov = max(10.0, float(camera.fov) * (zstep ** (-rate * 18.0)))
        if hk.get("q", 0):
            camera.fov = min(110.0, float(camera.fov) * (zstep ** (rate * 18.0)))
        if hk.get("+", 0) or hk.get("=", 0):
            camera.fov = max(10.0, float(camera.fov) - 28.0 * dt)
        if hk.get("-", 0) or hk.get("_", 0):
            camera.fov = min(110.0, float(camera.fov) + 28.0 * dt)

    __main__.update = update

    app.run()
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Browse all models under assets/models in Ursina.")
    p.add_argument(
        "--assets-models",
        type=str,
        default=str(PROJECT_ROOT / "assets" / "models"),
        help="Root folder containing pack subfolders (default: assets/models)",
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
