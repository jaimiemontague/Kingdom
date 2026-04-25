r"""
WK32 R3: Prewarm Panda3D .bam cache files for OBJ assets.

Problem:
  Panda3D may log lines like:
    :loader(error): Unable to open models_compressed/... .bam
    saved .bam to: models_compressed\...
  on first run after adding new .obj models. This is usually expected cache-miss
  noise (not a missing-asset crash), but the first-run OBJ parse + conversion can
  make Ursina preview feel "stuck".

This tool loads selected .obj files once (offscreen) and writes the corresponding
`.bam` files under `models_compressed/` so subsequent Ursina runs can start faster
and the cache-miss noise disappears.

Usage (from repo root):
  python tools/prewarm_panda_bam_cache.py --environment
  python tools/prewarm_panda_bam_cache.py --environment --force

Note:
  This tool intentionally prewarms only `.obj` assets. Promoted `.glb` assets are
  already fast to load and do not use the same OBJ→BAM conversion path.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PROJECT_ROOT / "assets"
DEFAULT_CACHE_ROOT = PROJECT_ROOT / "models_compressed"


def _iter_obj_files_under(dir_path: Path) -> list[Path]:
    if not dir_path.is_dir():
        return []
    return sorted([p for p in dir_path.rglob("*.obj") if p.is_file()], key=lambda p: str(p).lower())


def _asset_relpath_under_assets(p: Path) -> Path:
    try:
        rel = p.resolve().relative_to(ASSETS_ROOT.resolve())
    except Exception:
        # Should never happen for our own asset discovery, but keep it safe.
        rel = Path(p.name)
    return rel


def _cache_bam_path_for_obj(obj_path: Path, *, cache_root: Path) -> Path:
    rel_under_assets = _asset_relpath_under_assets(obj_path)
    # Mirror Panda's observed layout: models_compressed/assets/models/.../<stem>.bam
    return cache_root / "assets" / rel_under_assets.with_suffix(".bam")

def _panda_load_path_for_obj(obj_path: Path) -> str:
    r"""
    Panda3D/Assimp can get confused by Windows drive-letter absolute paths (eg `C:\...`).
    Use a project-relative path (POSIX slashes) similar to how Ursina loads models.
    """
    rel = obj_path.resolve().relative_to(PROJECT_ROOT.resolve())
    return rel.as_posix()


def _load_offscreen_showbase() -> "ShowBase":
    # Import lazily so running --help doesn't require Panda/Ursina to import.
    from panda3d.core import loadPrcFileData  # type: ignore
    from direct.showbase.ShowBase import ShowBase  # type: ignore

    # Avoid opening a visible window.
    loadPrcFileData("", "window-type offscreen")
    # Avoid audio init churn (esp. on CI / headless setups).
    loadPrcFileData("", "audio-library-name null")
    # Ensure the project root is on Panda's model-path so relative paths like
    # `assets/models/environment/foo.obj` can be resolved regardless of script dir.
    proj = PROJECT_ROOT.as_posix()
    loadPrcFileData("", f"model-path {proj}")

    base = ShowBase(windowType="offscreen")
    try:
        base.disableMouse()
    except Exception:
        pass
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prewarm Panda3D .bam cache for OBJ assets.")
    parser.add_argument("--cache-root", type=str, default=str(DEFAULT_CACHE_ROOT), help="Cache output root dir.")
    parser.add_argument(
        "--environment",
        action="store_true",
        help="Prewarm OBJ files under assets/models/environment/ (recommended).",
    )
    parser.add_argument("--force", action="store_true", help="Rewrite existing .bam files.")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N OBJ files (0 = all).")

    ns = parser.parse_args(argv)

    targets: list[Path] = []
    if ns.environment:
        targets.extend(_iter_obj_files_under(ASSETS_ROOT / "models" / "environment"))

    targets = sorted(set(targets), key=lambda p: str(p).lower())
    if ns.limit and ns.limit > 0:
        targets = targets[: ns.limit]

    if not targets:
        print("[prewarm_bam_cache] No OBJ targets found. Use --environment.")
        return 0

    cache_root = Path(ns.cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)

    base = _load_offscreen_showbase()

    wrote = 0
    skipped = 0
    failed = 0
    t0 = time.time()

    for obj in targets:
        bam = _cache_bam_path_for_obj(obj, cache_root=cache_root)
        if bam.is_file() and not ns.force:
            skipped += 1
            continue

        bam.parent.mkdir(parents=True, exist_ok=True)
        try:
            node = base.loader.loadModel(_panda_load_path_for_obj(obj))
            if node is None:
                raise RuntimeError("loadModel returned None")
            node.writeBamFile(str(bam))
            wrote += 1
            print(f"[prewarm_bam_cache] wrote: {bam}")
        except Exception as e:
            failed += 1
            print(f"[prewarm_bam_cache] ERROR: {obj} -> {bam}: {e}")

    try:
        base.destroy()
    except Exception:
        pass

    dt = time.time() - t0
    print(
        f"[prewarm_bam_cache] DONE wrote={wrote} skipped={skipped} failed={failed} seconds={dt:.2f} cache_root={cache_root}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

