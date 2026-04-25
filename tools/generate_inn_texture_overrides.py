#!/usr/bin/env python3
"""
Generate CC0 low-res texture overrides for the Inn prefab polish pass.

The textures are authored procedurally in-repo so there is no third-party
license dependency. Online references inform the style only.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "assets" / "textures" / "buildings" / "inn"
SIZE = 128


def _shade(rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, c + delta)) for c in rgb)


def _save_wood(path: Path) -> None:
    base = (124, 78, 43)
    img = Image.new("RGBA", (SIZE, SIZE), _shade(base, -8) + (255,))
    d = ImageDraw.Draw(img)
    plank_w = 16
    for x in range(0, SIZE, plank_w):
        col = _shade(base, ((x // plank_w) % 3 - 1) * 8)
        d.rectangle((x, 0, x + plank_w - 1, SIZE), fill=col + (255,))
        d.line((x, 0, x, SIZE), fill=_shade(base, -42) + (255,), width=2)
        d.line((x + 2, 0, x + 2, SIZE), fill=_shade(base, 20) + (255,), width=1)
        for y in range(8, SIZE, 13):
            yy = y + ((x // plank_w) * 5) % 9
            d.line((x + 4, yy, x + plank_w - 5, yy + 2), fill=_shade(col, -18) + (255,))
        knot_x = x + 7 + ((x // plank_w) * 3) % 5
        knot_y = 22 + ((x // plank_w) * 23) % 82
        d.ellipse((knot_x - 3, knot_y - 2, knot_x + 4, knot_y + 3), fill=_shade(base, -32) + (255,))
        d.arc((knot_x - 5, knot_y - 4, knot_x + 6, knot_y + 5), 20, 330, fill=_shade(base, 18) + (255,))
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=_shade(base, -50) + (255,))
    img.save(path)


def _save_stone(path: Path) -> None:
    # Retro Fantasy stone reads warmer and chunkier than the Fantasy Town grey.
    # Keep large uneven blocks, tan-grey ramps, and heavy dark seams.
    mortar = (76, 72, 66)
    img = Image.new("RGBA", (SIZE, SIZE), mortar + (255,))
    d = ImageDraw.Draw(img)
    row_h = 18
    palette = (
        (142, 132, 112),
        (128, 124, 112),
        (158, 145, 118),
        (112, 115, 108),
        (172, 154, 124),
    )
    for row, y in enumerate(range(-2, SIZE, row_h)):
        offset = 0 if row % 2 == 0 else 18
        x = -offset
        block_i = 0
        while x < SIZE:
            w = 26 + ((row * 13 + block_i * 9) % 19)
            x0 = max(0, x + 2)
            x1 = min(SIZE - 1, x + w - 3)
            y0 = max(0, y + 2 + ((block_i + row) % 2))
            y1 = min(SIZE - 1, y + row_h - 3)
            col = palette[(row * 2 + block_i) % len(palette)]
            if x0 <= x1 and y0 <= y1:
                d.rectangle((x0, y0, x1, y1), fill=col + (255,))
                d.line((x0, y0, x1, y0), fill=_shade(col, 32) + (255,), width=2)
                d.line((x0, y0, x0, y1), fill=_shade(col, 18) + (255,), width=1)
                d.line((x0, y1, x1, y1), fill=_shade(col, -36) + (255,), width=2)
                d.line((x1, y0, x1, y1), fill=_shade(col, -28) + (255,), width=1)
                if x1 - x0 >= 10 and y1 - y0 >= 8:
                    chip_x = x0 + 5 + ((row * 17 + block_i * 11) % max(1, x1 - x0 - 8))
                    chip_y = y0 + 4 + ((row * 7 + block_i * 5) % max(1, y1 - y0 - 7))
                    d.rectangle((chip_x, chip_y, min(x1, chip_x + 3), min(y1, chip_y + 2)), fill=_shade(col, -24) + (255,))
                    d.point((min(x1, chip_x + 4), chip_y), fill=_shade(col, 22) + (255,))
            x += w
            block_i += 1
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=(48, 46, 42, 255))
    img.save(path)


def _save_roof(path: Path) -> None:
    base = (54, 83, 94)
    img = Image.new("RGBA", (SIZE, SIZE), _shade(base, -10) + (255,))
    d = ImageDraw.Draw(img)
    tile_h = 14
    for row, y in enumerate(range(-tile_h, SIZE, tile_h)):
        offset = 0 if row % 2 == 0 else 12
        for x in range(-offset, SIZE, 24):
            col = _shade(base, ((row + x // 24) % 3 - 1) * 8)
            pts = [(x, y + tile_h), (x + 12, y), (x + 24, y + tile_h), (x + 24, y + tile_h + 7), (x, y + tile_h + 7)]
            d.polygon(pts, fill=col + (255,))
            d.line((x + 2, y + tile_h, x + 12, y + 2, x + 22, y + tile_h), fill=_shade(col, 24) + (255,))
            d.line((x, y + tile_h + 7, x + 24, y + tile_h + 7), fill=_shade(col, -34) + (255,))
        d.line((0, y + tile_h + 7, SIZE, y + tile_h + 7), fill=_shade(base, -42) + (255,), width=1)
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=_shade(base, -52) + (255,))
    img.save(path)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _save_wood(OUT_DIR / "inn_wood_planks.png")
    _save_stone(OUT_DIR / "inn_stone_blocks.png")
    _save_roof(OUT_DIR / "inn_roof_shingles.png")
    (OUT_DIR / "README.md").write_text(
        "# Inn Texture Overrides\n\n"
        "Generated in-repo for Kingdom Sim's Inn texture polish pass. These CC0 "
        "textures use online low-poly fantasy references for style direction, but "
        "no third-party image pixels are copied.\n",
        encoding="utf-8",
    )
    print(f"[inn-textures] Wrote textures to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
