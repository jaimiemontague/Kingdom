"""
WK31 — batch side-by-side flush evidence PNGs for representative wall/fence models.

Runs ``wall_flush_pair_kenney.py`` once per sample (separate Ursina process for stability).

Usage (repo root)::

  python tools/wk31_flush_screenshot_batch.py

Output: ``docs/screenshots/wk31_flush/wk31_<key>.png`` (FT + Graveyard + Nature + Survival raw fence + **Survival structure / tent** merged GLBs).

**Coverage note (Agent 15):** Every other ``Models/GLB format/*.glb`` that resolves to
``kenney_survival-kit`` via ``tools/kenney_pack_scale.pack_extent_multiplier_for_rel``
(raw path, merged Survival-only basename, or §3.3 collision row) uses the **same**
uniform multiplier and the same **tight-bounds** edge spacing in ``wall_flush_pair_kenney``.
Extra PNGs here are representative belt-and-suspenders samples, not an exhaustive list.

**Assembler vs flush tool:** The Kenney assembler places pieces on a **1-unit center
snap** (see ``tools/model_assembler_kenney.GRID_CELL``). After uniform fit, some
Survival pieces (e.g. ``structure-floor.glb``) are **narrower in world XZ** than one
cell, so two clicks on adjacent snap points can show a **gap** even though SSOT is
correct. Retro wall pieces often read closer to one unit wide, so they look flush on
the same grid. For kitbash, nudge with WASD / fine placement — or rely on the flush
tool for edge-to-edge *pair* verification. This is **not** fixed by changing
``config.py`` footprints.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Representative samples per pack; after 2–3 successes the SSOT multipliers cover the rest.
WK31_FLUSH_SAMPLES: tuple[tuple[str, str], ...] = (
    ("ft_wall", "Models/GLB format/wall-fantasy-town.glb"),
    ("ft_fence", "Models/GLB format/fence-fantasy-town.glb"),
    ("ft_hedge", "Models/GLB format/hedge-fantasy-town.glb"),
    ("gy_brick", "Models/GLB format/brick-wall-graveyard.glb"),
    ("gy_iron_fence", "Models/GLB format/iron-fence-border-graveyard.glb"),
    ("gy_stone_wall", "Models/GLB format/stone-wall-graveyard.glb"),
    ("nat_fence", "Models/GLTF format/fence_simple.glb"),
    ("nat_path_straight", "Models/GLTF format/ground_pathStraight.glb"),
    (
        "surv_raw_fence",
        "Models/Kenny raw downloads (for exact paths)/kenney_survival-kit/Models/GLB format/fence-fortified.glb",
    ),
    # Merged Survival Kit — structure / shelter family (SSOT 1.14; edge spacing in wall_flush_pair)
    ("surv_structure", "Models/GLB format/structure.glb"),
    ("surv_structure_floor", "Models/GLB format/structure-floor.glb"),
    ("surv_structure_metal_doorway", "Models/GLB format/structure-metal-doorway.glb"),
    ("surv_structure_metal", "Models/GLB format/structure-metal.glb"),
    ("surv_structure_roof", "Models/GLB format/structure-roof.glb"),
    # Survival metal + tent — same SSOT + bounds logic as above; explicit PNGs for review
    ("surv_structure_metal_floor", "Models/GLB format/structure-metal-floor.glb"),
    ("surv_structure_metal_roof", "Models/GLB format/structure-metal-roof.glb"),
    ("surv_structure_metal_wall", "Models/GLB format/structure-metal-wall.glb"),
    ("surv_tent_canvas", "Models/GLB format/tent-canvas.glb"),
)


def main() -> int:
    out_dir = PROJECT_ROOT / "docs" / "screenshots" / "wk31_flush"
    out_dir.mkdir(parents=True, exist_ok=True)
    tool = PROJECT_ROOT / "tools" / "wall_flush_pair_kenney.py"
    failed = 0
    for key, rel in WK31_FLUSH_SAMPLES:
        png = out_dir / f"wk31_{key}.png"
        cmd = [
            sys.executable,
            str(tool),
            "--model",
            rel,
            "--no-labels",
            "--screenshot-out",
            str(png),
        ]
        print("[wk31_flush_batch]", " ".join(cmd), flush=True)
        r = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if r.returncode != 0:
            failed += 1
            print(f"[wk31_flush_batch] FAIL code={r.returncode} key={key}", file=sys.stderr)
        elif not png.is_file():
            failed += 1
            print(f"[wk31_flush_batch] Missing PNG: {png}", file=sys.stderr)
    if failed:
        print(f"[wk31_flush_batch] Completed with {failed} failure(s)", file=sys.stderr)
        return 1
    print(f"[wk31_flush_batch] OK — {len(WK31_FLUSH_SAMPLES)} PNGs in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
