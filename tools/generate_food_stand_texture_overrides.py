#!/usr/bin/env python3
"""
Generate CC0 low-res texture overrides for the Food Stand prefab polish pass.

Covers food_stand_v1.json (stall + banner + stool) and food_stand_v2.json
(stall-green single piece) — both made from Fantasy Town Kit pieces that
require texture overrides per the prefab_texture_override_standard.

The textures are authored procedurally in-repo so there is no third-party
license dependency.  Online references inform the style only.

Outputs
-------
assets/textures/buildings/food_stand/food_stand_wood_stall.png  (64x64)
    Warm plank-board wood for stall frame + counter + stool.
assets/textures/buildings/food_stand/food_stand_canvas_awning.png  (64x64)
    Warm cream-tan canvas for banner/awning canopy surface.
assets/textures/buildings/food_stand/README.md
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "assets" / "textures" / "buildings" / "food_stand"
SIZE = 64


def _shade(rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, c + delta)) for c in rgb)


def _save_wood_stall(path: Path) -> None:
    """Warm reclaimed-wood planks: medium brown, broad boards, visible grain lines."""
    base = (138, 90, 52)  # warm brown
    img = Image.new("RGBA", (SIZE, SIZE), _shade(base, -10) + (255,))
    d = ImageDraw.Draw(img)
    plank_w = 10
    for x in range(0, SIZE, plank_w):
        idx = x // plank_w
        col = _shade(base, ((idx % 3) - 1) * 10)
        d.rectangle((x, 0, x + plank_w - 1, SIZE - 1), fill=col + (255,))
        # Dark left edge (shadow between planks)
        d.line((x, 0, x, SIZE - 1), fill=_shade(base, -44) + (255,), width=2)
        # Subtle highlight one pixel in
        d.line((x + 2, 0, x + 2, SIZE - 1), fill=_shade(base, 18) + (255,), width=1)
        # Grain lines
        for y in range(6, SIZE, 11):
            yy = y + ((idx * 4) % 7)
            d.line(
                (x + 3, yy, x + plank_w - 4, yy + 2),
                fill=_shade(col, -22) + (255,),
            )
        # Knot
        kx = x + 4 + ((idx * 3) % 4)
        ky = 14 + ((idx * 19) % 36)
        d.ellipse(
            (kx - 2, ky - 2, kx + 3, ky + 3),
            fill=_shade(base, -36) + (255,),
        )
    # Border
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=_shade(base, -52) + (255,))
    img.save(path)


def _save_canvas_awning(path: Path) -> None:
    """
    Warm cream/ochre canvas for the stall awning / banner piece.

    Uses broad horizontal bands to mimic a striped market tent canopy.
    Bands alternate between muted cream and a warm tan, with subtle
    top-left highlights baked in.
    """
    cream = (214, 196, 154)
    tan   = (188, 162, 110)

    img = Image.new("RGBA", (SIZE, SIZE), cream + (255,))
    d = ImageDraw.Draw(img)

    band_h = 8
    for row in range(SIZE // band_h + 1):
        y0 = row * band_h
        y1 = min(SIZE - 1, y0 + band_h - 1)
        if y1 < y0:
            break
        col = cream if row % 2 == 0 else tan
        d.rectangle((0, y0, SIZE - 1, y1), fill=col + (255,))
        # Top-left highlight per band
        d.line((0, y0, SIZE - 1, y0), fill=_shade(col, 20) + (255,), width=1)
        # Subtle bottom shadow
        d.line((0, y1, SIZE - 1, y1), fill=_shade(col, -24) + (255,), width=1)
        # Loose warp-thread variation
        for x in range(4, SIZE, 9):
            var = ((row * 7 + x // 9) % 3) - 1
            if y1 - y0 > 3:
                mid = (y0 + y1) // 2
                d.line(
                    (x, mid, x + 2, mid),
                    fill=_shade(col, var * 8) + (255,),
                )

    # Overall border: dark olive outline
    d.rectangle(
        (0, 0, SIZE - 1, SIZE - 1),
        outline=_shade(tan, -50) + (255,),
    )
    img.save(path)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _save_wood_stall(OUT_DIR / "food_stand_wood_stall.png")
    print(f"  wrote {OUT_DIR / 'food_stand_wood_stall.png'}")

    _save_canvas_awning(OUT_DIR / "food_stand_canvas_awning.png")
    print(f"  wrote {OUT_DIR / 'food_stand_canvas_awning.png'}")

    (OUT_DIR / "README.md").write_text(
        "# Food Stand Texture Overrides\n\n"
        "Generated in-repo for Kingdom Sim's Food Stand texture polish pass.  "
        "These CC0 textures use online low-poly fantasy market references for "
        "style direction only; no third-party image pixels are copied.\n\n"
        "## Files\n\n"
        "| File | Purpose | Applied to |\n"
        "|------|---------|------------|\n"
        "| `food_stand_wood_stall.png` | Warm reclaimed-wood planks | "
        "`stall-fantasy-town.glb`, `stall-green-fantasy-town.glb`, "
        "`stall-stool-fantasy-town.glb` |\n"
        "| `food_stand_canvas_awning.png` | Cream/tan canvas stripes | "
        "`banner-green-fantasy-town.glb` |\n\n"
        "## Regenerate\n\n"
        "```powershell\n"
        "python tools/generate_food_stand_texture_overrides.py\n"
        "```\n",
        encoding="utf-8",
    )
    print(f"  wrote {OUT_DIR / 'README.md'}")
    print(f"[food-stand-textures] Done — textures in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
