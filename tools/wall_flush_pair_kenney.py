"""
WK31 wall/fence flush evaluation: two identical GLB instances side-by-side in Ursina.

Uses the same glTF load + material classification as ``model_viewer_kenney`` so
lighting and shaders match that tool. Default ``--max-extent`` follows
``tools/kenney_pack_scale.pack_max_extent_for_rel`` (Retro reference = 1.0).

Usage (repo root)::

  python tools/wall_flush_pair_kenney.py --model \"Models/GLB format/wall-fantasy-town.glb\"
  python tools/wall_flush_pair_kenney.py --model \"Models/GLTF format/fence_simple.glb\" --max-extent 4 --gap 0.2

  python tools/wall_flush_pair_kenney.py --dump-inventory

Controls: Right-drag orbit | Middle-drag pan | Scroll zoom | ESC quit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_inventory(assets_models: Path) -> dict:
    glb = assets_models / "Models" / "GLB format"
    gltf = assets_models / "Models" / "GLTF format"
    raw_surv = (
        assets_models
        / "Models"
        / "Kenny raw downloads (for exact paths)"
        / "kenney_survival-kit"
        / "Models"
        / "GLB format"
    )

    def kw_match(name: str, patterns: tuple[str, ...]) -> bool:
        n = name.lower()
        return any(p in n for p in patterns)

    ft_patterns = (
        "wall",
        "fence",
        "hedge",
        "road-edge",
        "road-curb",
        "balcony-wall",
        "pillar-stone",
        "planks-",
        "poles-",
    )
    gy_patterns = (
        "wall",
        "fence",
        "iron-fence",
        "brick-wall",
        "stone-wall",
        "border-pillar",
        "column-",
        "pillar-",
    )

    ft = sorted([p.name for p in glb.glob("*-fantasy-town.glb") if kw_match(p.name, ft_patterns)])
    gy = sorted([p.name for p in glb.glob("*-graveyard.glb") if kw_match(p.name, gy_patterns)])
    nat = sorted(
        p.name
        for p in gltf.glob("*.glb")
        if p.name.startswith(("fence_", "ground_path", "path_"))
    )
    surv: list[str] = []
    if raw_surv.is_dir():
        surv = sorted(
            p.name
            for p in raw_surv.glob("*.glb")
            if kw_match(p.name, ("wall", "fence", "structure-metal", "barrier", "dock"))
        )

    return {
        "fantasy_town_merged_glb": {"count": len(ft), "files": ft},
        "graveyard_merged_glb": {"count": len(gy), "files": gy},
        "nature_gltf_modular_fence_path": {"count": len(nat), "files": nat},
        "survival_raw_glb_wall_fence": {"count": len(surv), "files": surv},
    }


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return s[:head] + "..." + s[-tail:]


def _world_x_extent_after_fit(ent) -> float:
    """Axis-aligned X width of the fitted model in world units (for edge-to-edge spacing)."""
    try:
        m = getattr(ent, "model", None)
        if m is None:
            return 1.0
        tb = m.getTightBounds()
        if not tb:
            return 1.0
        pmin, pmax = tb
        sx = float(getattr(ent, "scale_x", ent.scale[0]))
        return max(1e-4, abs(float(pmax.x) - float(pmin.x)) * sx)
    except Exception:
        return 1.0


def run_pair(
    *,
    assets_models: Path,
    rel_model: str,
    max_extent: float,
    gap: float,
    dx_offset: float,
    bounds_spacing: bool = True,
    screenshot_out: str | None = None,
    show_labels: bool = True,
) -> int:
    os.chdir(PROJECT_ROOT)
    abs_path = (assets_models / rel_model).resolve()
    if not abs_path.is_file():
        print(f"[wall_flush_pair] Not found: {abs_path}", file=sys.stderr)
        return 1

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from tools.model_viewer_kenney import (
        _apply_gltf_color_and_shading,
        _fit_uniform_and_ground,
        _load_model_node_from_file,
        _rel_for_label,
        _setup_scene_lighting,
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
        EditorCamera,
    )
    from ursina.models.procedural.grid import Grid
    from ursina.shaders import unlit_shader
    from panda3d.core import LVecBase4f, getModelPath

    app = Ursina(
        title="Kingdom Sim — Wall flush pair (WK31)",
        borderless=False,
        fullscreen=False,
        development_mode=False,
    )
    application.asset_folder = str(PROJECT_ROOT.resolve())
    getModelPath().append_directory(str(PROJECT_ROOT.resolve()))
    window.exit_button.visible = False
    window.fps_counter.enabled = True
    try:
        scene.clearFog()
        app.setBackgroundColor(LVecBase4f(0.12, 0.13, 0.15, 1))
    except Exception:
        pass

    Entity(
        parent=scene,
        model=Grid(32, 32),
        rotation=(90, 0, 0),
        position=(0, 0, 0),
        scale=(120, 1, 120),
        color=color.rgba(0.22, 0.24, 0.28, 1),
        collision=False,
        shader=unlit_shader,
    )

    label_base = _rel_for_label(assets_models, abs_path)

    def spawn_one(x: float, z: float):
        node = _load_model_node_from_file(abs_path)
        if node is None:
            return None
        ent = Entity(
            parent=scene,
            model=node,
            collider=None,
            double_sided=True,
            position=(x, 0.0, z),
        )
        _fit_uniform_and_ground(ent, max_extent)
        _apply_gltf_color_and_shading(
            ent.model,
            debug_materials=False,
            model_label=label_base,
            aggregate_stats=None,
        )
        return ent

    e0 = spawn_one(0.0, 0.0)
    if e0 is None:
        print("[wall_flush_pair] Failed to load model", file=sys.stderr)
        return 1

    w0 = _world_x_extent_after_fit(e0)
    if bounds_spacing:
        base_x = w0 + float(gap) + float(dx_offset)
    else:
        base_x = float(max_extent) + float(gap) + float(dx_offset)
    e1 = spawn_one(base_x, 0.0)
    if e1 is None:
        return 1

    mid_x = base_x * 0.5
    span = max(max_extent * 8.0, 48.0, base_x * 3.0)
    _setup_scene_lighting(center_x=mid_x, center_z=0.0, span=span)

    ec = EditorCamera()
    camera.fov = 50
    camera.clip_plane_near = 0.05
    camera.clip_plane_far = 50000.0
    ec.position = Vec3(mid_x, 0.0, 0.0)
    camera.position = Vec3(0, max(18.0, max_extent * 2.8), -max(30.0, max_extent * 4.5))
    ec.rotation_x = 35
    ec.target_z = camera.z

    if show_labels:
        Text(
            text=_truncate(rel_model, 52),
            position=(-0.86, 0.46),
            scale=0.9,
            color=color.white,
            background=True,
        )
        Text(
            text="Two copies along +X — edge spacing from bounds | ESC quit",
            position=(-0.86, 0.42),
            scale=0.7,
            color=color.light_gray,
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

    if screenshot_out:
        out_path = os.path.abspath(screenshot_out)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        def _shot_update() -> None:
            if not hasattr(_shot_update, "n"):
                _shot_update.n = 0
            _shot_update.n += 1
            if _shot_update.n < 8:
                return
            try:
                from panda3d.core import Filename

                b = application.base
                win = getattr(b, "win", None) if b is not None else None
                if win is not None:
                    img = win.get_screenshot()
                    if img is not None:
                        img.write(Filename.from_os_specific(out_path))
                        print(f"[wall_flush_pair] Screenshot: {out_path}", flush=True)
                    else:
                        print(f"[wall_flush_pair] get_screenshot returned None: {out_path}", file=sys.stderr)
                else:
                    print("[wall_flush_pair] No graphics window for screenshot", file=sys.stderr)
            except Exception as ex:
                print(f"[wall_flush_pair] Screenshot error: {ex}", file=sys.stderr)
            try:
                application.quit()
            except Exception:
                sys.exit(0)

        __main__.update = _shot_update
    else:

        def _noop_update() -> None:
            pass

        __main__.update = _noop_update

    app.run()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="WK31 side-by-side wall/fence flush pair viewer")
    p.add_argument(
        "--assets-models",
        type=str,
        default=str(PROJECT_ROOT / "assets" / "models"),
    )
    p.add_argument(
        "--model",
        type=str,
        help="Path under assets/models, e.g. Models/GLB format/wall-fantasy-town.glb",
    )
    p.add_argument(
        "--max-extent",
        type=float,
        default=None,
        help="Uniform fit cap (default: from tools/kenney_pack_scale for this model path)",
    )
    p.add_argument(
        "--gap",
        type=float,
        default=0.0,
        help="Extra world units added to spacing between instance centers along +X",
    )
    p.add_argument(
        "--dx-offset",
        type=float,
        default=0.0,
        help="Additional +X offset for the second copy",
    )
    p.add_argument(
        "--dump-inventory",
        action="store_true",
        help="Print wall/fence candidate inventory JSON to stdout and exit",
    )
    p.add_argument(
        "--screenshot-out",
        type=str,
        default=None,
        metavar="PNG",
        help="Save one PNG (after a few frames) and exit; useful for batch evidence",
    )
    p.add_argument(
        "--no-labels",
        action="store_true",
        help="Hide on-screen text (cleaner screenshots)",
    )
    p.add_argument(
        "--legacy-spacing",
        action="store_true",
        help="Use old center spacing (max_extent+gap) instead of edge-to-edge bounds width",
    )
    args = p.parse_args()
    assets = Path(args.assets_models).resolve()

    if args.dump_inventory:
        inv = build_inventory(assets)
        print(json.dumps(inv, indent=2))
        return 0

    if not args.model:
        p.error("--model is required unless using --dump-inventory")

    rel = args.model.replace("\\", "/").lstrip("/")
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from tools.kenney_pack_scale import pack_max_extent_for_rel as _pme

    max_e = (
        float(args.max_extent)
        if args.max_extent is not None
        else _pme(rel)
    )
    return run_pair(
        assets_models=assets,
        rel_model=rel,
        max_extent=max_e,
        gap=float(args.gap),
        dx_offset=float(args.dx_offset),
        bounds_spacing=not bool(args.legacy_spacing),
        screenshot_out=args.screenshot_out,
        show_labels=not bool(args.no_labels),
    )


if __name__ == "__main__":
    raise SystemExit(main())
