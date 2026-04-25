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
    # Match the nearby Retro-style buildings: smaller warm tan-grey stones,
    # visible but not overpowering mortar, and soft top-left highlights.
    mortar = (100, 96, 88)
    img = Image.new("RGBA", (SIZE, SIZE), mortar + (255,))
    d = ImageDraw.Draw(img)
    row_h = 12
    palette = (
        (174, 164, 144),
        (158, 153, 139),
        (190, 174, 145),
        (144, 148, 139),
        (202, 184, 150),
        (166, 156, 132),
    )
    for row, y in enumerate(range(-2, SIZE, row_h)):
        offset = 0 if row % 2 == 0 else 11
        x = -offset
        block_i = 0
        while x < SIZE:
            w = 18 + ((row * 11 + block_i * 7) % 12)
            x0 = max(0, x + 1)
            x1 = min(SIZE - 1, x + w - 2)
            y0 = max(0, y + 1 + ((block_i + row) % 2))
            y1 = min(SIZE - 1, y + row_h - 2)
            col = palette[(row * 2 + block_i) % len(palette)]
            if x0 <= x1 and y0 <= y1:
                d.rectangle((x0, y0, x1, y1), fill=col + (255,))
                d.line((x0, y0, x1, y0), fill=_shade(col, 24) + (255,), width=1)
                d.line((x0, y0, x0, y1), fill=_shade(col, 12) + (255,), width=1)
                d.line((x0, y1, x1, y1), fill=_shade(col, -28) + (255,), width=1)
                d.line((x1, y0, x1, y1), fill=_shade(col, -20) + (255,), width=1)
                if x1 - x0 >= 9 and y1 - y0 >= 7:
                    chip_x = x0 + 4 + ((row * 17 + block_i * 11) % max(1, x1 - x0 - 7))
                    chip_y = y0 + 3 + ((row * 7 + block_i * 5) % max(1, y1 - y0 - 6))
                    d.rectangle((chip_x, chip_y, min(x1, chip_x + 2), min(y1, chip_y + 1)), fill=_shade(col, -18) + (255,))
                    d.point((min(x1, chip_x + 3), chip_y), fill=_shade(col, 18) + (255,))
            x += w
            block_i += 1
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=(74, 70, 64, 255))
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


def _save_stone_window(path: Path) -> None:
    img = Image.open(OUT_DIR / "inn_stone_blocks.png").convert("RGBA")
    d = ImageDraw.Draw(img)
    frame = (63, 48, 38)
    glass = (116, 144, 151)
    dark_glass = (72, 92, 99)
    highlight = (178, 196, 190)
    for x0 in (18, 54, 90):
        d.rectangle((x0, 42, x0 + 22, 83), fill=frame + (255,))
        d.rectangle((x0 + 4, 47, x0 + 18, 78), fill=glass + (255,))
        d.line((x0 + 11, 47, x0 + 11, 78), fill=frame + (255,), width=2)
        d.line((x0 + 4, 62, x0 + 18, 62), fill=frame + (255,), width=2)
        d.line((x0 + 5, 49, x0 + 10, 49), fill=highlight + (255,))
        d.rectangle((x0 + 4, 74, x0 + 18, 78), fill=dark_glass + (255,))
        d.rectangle((x0 - 1, 40, x0 + 23, 84), outline=(35, 30, 28, 255), width=1)
    img.save(path)


def _save_stone_door(path: Path) -> None:
    img = Image.open(OUT_DIR / "inn_stone_blocks.png").convert("RGBA")
    d = ImageDraw.Draw(img)
    trim = (58, 38, 28)
    door = (113, 65, 36)
    shadow = (38, 30, 28)
    for cx in (24, 64, 104):
        x0 = cx - 16
        x1 = cx + 16
        d.rectangle((x0, 44, x1, 101), fill=trim + (255,))
        d.pieslice((x0, 26, x1, 62), 180, 360, fill=trim + (255,))
        d.rectangle((x0 + 5, 49, x1 - 5, 101), fill=door + (255,))
        d.pieslice((x0 + 5, 33, x1 - 5, 65), 180, 360, fill=door + (255,))
        d.line((cx, 40, cx, 101), fill=_shade(door, -30) + (255,), width=2)
        d.line((x0 + 7, 61, x1 - 7, 61), fill=_shade(door, 26) + (255,))
        d.ellipse((x1 - 11, 73, x1 - 7, 77), fill=(195, 154, 80, 255))
        d.line((x0, 101, x1, 101), fill=shadow + (255,), width=2)
        d.line((x0, 44, x1, 44), fill=_shade(trim, 34) + (255,), width=1)
    img.save(path)


def _save_wood_window(path: Path) -> None:
    img = Image.open(OUT_DIR / "inn_wood_planks.png").convert("RGBA")
    d = ImageDraw.Draw(img)
    frame = (55, 33, 24)
    glass = (96, 126, 134)
    highlight = (166, 186, 181)
    for x0 in (24, 76):
        d.rectangle((x0, 42, x0 + 27, 85), fill=frame + (255,))
        d.rectangle((x0 + 5, 48, x0 + 22, 79), fill=glass + (255,))
        d.line((x0 + 13, 48, x0 + 13, 79), fill=frame + (255,), width=2)
        d.line((x0 + 5, 63, x0 + 22, 63), fill=frame + (255,), width=2)
        d.line((x0 + 6, 50, x0 + 12, 50), fill=highlight + (255,))
        d.rectangle((x0 - 2, 40, x0 + 29, 87), outline=(31, 24, 22, 255), width=1)
    img.save(path)


def _save_roof_window(path: Path) -> None:
    base = (53, 80, 90)
    img = Image.new("RGBA", (SIZE, SIZE), _shade(base, -8) + (255,))
    d = ImageDraw.Draw(img)
    tile_h = 14
    for row, y in enumerate(range(-tile_h, SIZE, tile_h)):
        offset = 0 if row % 2 == 0 else 12
        for x in range(-offset, SIZE, 24):
            col = _shade(base, ((row + x // 24) % 3 - 1) * 7)
            pts = [(x, y + tile_h), (x + 12, y), (x + 24, y + tile_h), (x + 24, y + tile_h + 7), (x, y + tile_h + 7)]
            d.polygon(pts, fill=col + (255,))
            d.line((x + 2, y + tile_h, x + 12, y + 2, x + 22, y + tile_h), fill=_shade(col, 22) + (255,))
            d.line((x, y + tile_h + 7, x + 24, y + tile_h + 7), fill=_shade(col, -32) + (255,))

    trim = (71, 42, 27)
    shadow = (36, 31, 29)
    glass = (116, 144, 151)
    highlight = (169, 190, 188)
    d.rectangle((24, 34, 104, 104), fill=trim + (255,))
    d.rectangle((31, 41, 97, 98), fill=(104, 62, 35, 255))
    d.polygon(((43, 72), (64, 52), (85, 72), (85, 91), (43, 91)), fill=shadow + (255,))
    d.rectangle((51, 66, 77, 91), fill=glass + (255,))
    d.line((64, 66, 64, 91), fill=shadow + (255,), width=2)
    d.line((51, 78, 77, 78), fill=shadow + (255,), width=2)
    d.line((54, 69, 62, 69), fill=highlight + (255,))
    d.line((25, 34, 103, 34), fill=_shade(trim, 34) + (255,), width=2)
    d.line((24, 104, 104, 104), fill=_shade(trim, -30) + (255,), width=2)
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=_shade(base, -50) + (255,))
    img.save(path)


def _save_window_panel(path: Path) -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (34, 28, 25, 255))
    d = ImageDraw.Draw(img)
    frame = (39, 28, 22)
    frame_hi = (92, 59, 36)
    glass = (102, 137, 145)
    glass_shadow = (55, 78, 86)
    highlight = (184, 205, 198)
    d.rectangle((13, 9, 114, 119), fill=frame + (255,))
    d.rectangle((21, 17, 106, 111), fill=frame_hi + (255,))
    d.rectangle((29, 25, 98, 103), fill=glass + (255,))
    d.rectangle((29, 87, 98, 103), fill=glass_shadow + (255,))
    d.rectangle((58, 25, 68, 103), fill=frame + (255,))
    d.rectangle((29, 60, 98, 70), fill=frame + (255,))
    d.line((34, 31, 53, 31), fill=highlight + (255,), width=3)
    d.line((75, 31, 92, 31), fill=highlight + (255,), width=3)
    d.rectangle((13, 9, 114, 119), outline=(20, 17, 15, 255), width=3)
    img.save(path)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _save_wood(OUT_DIR / "inn_wood_planks.png")
    _save_stone(OUT_DIR / "inn_stone_blocks.png")
    _save_roof(OUT_DIR / "inn_roof_shingles.png")
    _save_stone_window(OUT_DIR / "inn_stone_window_detail.png")
    _save_stone_door(OUT_DIR / "inn_stone_door_detail.png")
    _save_wood_window(OUT_DIR / "inn_wood_window_detail.png")
    _save_roof_window(OUT_DIR / "inn_roof_window_detail.png")
    _save_window_panel(OUT_DIR / "inn_window_panel.png")
    (OUT_DIR / "README.md").write_text(
        "# Inn Texture Overrides\n\n"
        "Generated in-repo for Kingdom Sim's Inn texture polish pass. These CC0 "
        "textures use online low-poly fantasy references for style direction, but "
        "no third-party image pixels are copied.\n\n"
        "The detail variants keep whole-piece prefab overrides viable on Fantasy "
        "Town door/window/dormer meshes while restoring strong dark frames and "
        "pale glass reads at the strategy camera distance. `inn_window_panel.png` "
        "is a UV-mapped decal texture for explicit window panels when object-space "
        "projection is not readable enough in game screenshots.\n",
        encoding="utf-8",
    )
    print(f"[inn-textures] Wrote textures to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
