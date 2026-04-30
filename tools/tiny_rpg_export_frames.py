"""
Export Tiny RPG Character pack (100x100 horizontal strips) into Kingdom Sim
hero/enemy per-action folders as frame_000.png, frame_001.png, ...

Reads Map_actions.csv (see assets/sprites/vendor/tiny_rpg_pack_v1_03/).

Tiny RPG characters occupy only the center of each 100x100 cell. By default we:
  1) Build a union bounding box of visible pixels across all frames in an action.
  2) Crop every frame with that same rect (aligned motion).
  3) Uniform-scale + letterbox into --out-w x --out-h (nearest neighbor; no squash).

Default on-disk size is 48x48: a transparent runtime canvas with the native
Tiny RPG crop pasted into the center. That keeps the pack's original pixels
intact because ``load_png_frames(..., scale_to=(48, 48))`` becomes a no-op.

Usage (repo root, PowerShell):
  python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --dry-run
  python tools/tiny_rpg_export_frames.py --pack assets/sprites/vendor/tiny_rpg_pack_v1_03 --execute --clean-action
  python tools/tiny_rpg_export_frames.py --execute --clean-action --verify

Requires pygame.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

import pygame

# Runtime unit sprite canvas. Visible characters stay native-size inside it.
_DEFAULT_EXPORT_PX = 48


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _characters_root(pack_root: Path) -> Path:
    return pack_root / "Characters(100x100)"


def _resolve_inner_character_dir(pack_root: Path, tiny_rpg_character: str) -> Path:
    return _characters_root(pack_root) / tiny_rpg_character / tiny_rpg_character


def _find_png(inner_dir: Path, filename: str) -> Path | None:
    """Resolve filename case-insensitively inside inner_dir."""
    want = filename.strip()
    if not want.lower().endswith(".png"):
        want = want + ".png"
    exact = inner_dir / want
    if exact.is_file():
        return exact
    wl = want.lower()
    if not inner_dir.is_dir():
        return None
    for p in inner_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".png" and p.name.lower() == wl:
            return p
    return None


def _split_horizontal_strip(surf: pygame.Surface, frame_w: int, frame_h: int) -> list[pygame.Surface]:
    w, h = surf.get_size()
    if h != frame_h:
        raise ValueError(f"Strip height {h} != frame_h {frame_h} (file would need vertical layout support)")
    if w % frame_w != 0:
        raise ValueError(f"Strip width {w} not divisible by frame_w {frame_w}")
    n = w // frame_w
    out: list[pygame.Surface] = []
    for i in range(n):
        rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
        out.append(surf.subsurface(rect).copy())
    return out


def _content_bbox(
    surf: pygame.Surface,
    *,
    alpha_threshold: int = 10,
    black_threshold: int = 10,
) -> pygame.Rect | None:
    """Bounding rect of visible pixels. None if empty.

    The Tiny RPG sheets use transparent backgrounds, while black pixels are real
    outline/face/weapon detail. Keep those black pixels in the content bounds.
    ``black_threshold`` remains in the signature for compatibility with older
    calls, but is intentionally unused.
    """
    s = surf.convert_alpha()
    w, h = s.get_size()
    try:
        import numpy as np
        from pygame.surfarray import array_alpha

        a = array_alpha(s)
        mask = a > alpha_threshold
        xs, ys = np.where(mask)
        if xs.size == 0:
            return None
        min_x, max_x = int(xs.min()), int(xs.max())
        min_y, max_y = int(ys.min()), int(ys.max())
        return pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
    except Exception:
        min_x, min_y = w, h
        max_x, max_y = -1, -1
        for y in range(h):
            for x in range(w):
                r, g, b, a = s.get_at((x, y))
                if a <= alpha_threshold:
                    continue
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
        if max_x < min_x:
            return None
        return pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def _union_crop_rect(frames: Iterable[pygame.Surface], pad: int, frame_w: int, frame_h: int) -> pygame.Rect:
    rects: list[pygame.Rect] = []
    for f in frames:
        b = _content_bbox(f)
        if b is not None:
            rects.append(b)
    if not rects:
        return pygame.Rect(0, 0, frame_w, frame_h)
    u = rects[0].copy()
    for r in rects[1:]:
        u.union_ip(r)
    if pad:
        u.inflate_ip(pad * 2, pad * 2)
    clip = pygame.Rect(0, 0, frame_w, frame_h)
    u = u.clip(clip)
    if u.width < 1 or u.height < 1:
        return pygame.Rect(0, 0, frame_w, frame_h)
    return u


def _resize_surface_nearest(src: pygame.Surface, dw: int, dh: int) -> pygame.Surface:
    """Nearest-neighbor resize (pixel art). Pygame's transform.scale can soften on downscale."""
    sw, sh = src.get_size()
    if sw == dw and sh == dh:
        return src.copy()
    try:
        from PIL import Image

        raw = pygame.image.tobytes(src, "RGBA")
        im = Image.frombytes("RGBA", (sw, sh), raw)
        try:
            resample = Image.Resampling.NEAREST
        except AttributeError:
            resample = Image.NEAREST  # type: ignore[attr-defined]
        im = im.resize((dw, dh), resample)
        return pygame.image.frombytes(im.tobytes("raw", "RGBA"), (dw, dh), "RGBA")
    except Exception:
        return pygame.transform.scale(src, (dw, dh))


def _crop_fit_canvas(source: pygame.Surface, out_w: int, out_h: int) -> pygame.Surface:
    """Uniform nearest-neighbor scale to fit inside out_w x out_h; transparent letterbox."""
    sw, sh = source.get_size()
    if sw < 1 or sh < 1:
        surf = pygame.Surface((out_w, out_h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        return surf
    scale = min(out_w / sw, out_h / sh)
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    scaled = _resize_surface_nearest(source, nw, nh)
    canvas = pygame.Surface((out_w, out_h), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    x = (out_w - nw) // 2
    y = (out_h - nh) // 2
    canvas.blit(scaled, (x, y))
    return canvas


def _crop_native_canvas(
    source: pygame.Surface,
    crop: pygame.Rect,
    *,
    out_w: int,
    out_h: int,
    frame_w: int,
    frame_h: int,
) -> pygame.Surface:
    """Paste the unscaled crop into an output canvas using the source cell center.

    This preserves native Tiny RPG pixels and keeps body position stable between
    idle/walk and wide attack frames. The source cell center maps to the output
    canvas center; pygame clips automatically if an extreme effect exceeds 48px.
    """
    sub = source.subsurface(crop).copy()
    canvas = pygame.Surface((out_w, out_h), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    x = int(round((out_w - frame_w) / 2 + crop.x))
    y = int(round((out_h - frame_h) / 2 + crop.y))
    canvas.blit(sub, (x, y))
    return canvas


def _apply_rogue_recolor(source: pygame.Surface) -> pygame.Surface:
    """Shift Archer-derived rogue accents toward cool steel/purple tones."""
    surf = source.copy().convert_alpha()
    w, h = surf.get_size()
    for y in range(h):
        for x in range(w):
            r, g, b, a = surf.get_at((x, y))
            if a <= 0:
                continue
            # Preserve skin, bone, dark outlines, and bow/string detail.
            if r > 170 and g > 110 and b < 110:
                continue
            if max(r, g, b) < 55:
                continue
            # Re-theme saturated green/yellow cloth accents from Archer to Rogue.
            if g >= r and g >= b and g > 80:
                v = max(65, min(210, int((r + g + b) / 3)))
                surf.set_at((x, y), (min(220, v + 18), min(220, v + 12), min(235, v + 42), a))
            elif r > 120 and g > 110 and b < 90:
                # Warm gold trim becomes muted steel so the rogue is distinct.
                v = max(70, min(200, int((r + g + b) / 3)))
                surf.set_at((x, y), (min(210, v + 8), min(210, v + 8), min(230, v + 28), a))
    return surf


def _scale_full_frame_nearest(f: pygame.Surface, out_w: int, out_h: int) -> pygame.Surface:
    if f.get_size() == (out_w, out_h):
        return f
    return _resize_surface_nearest(f, out_w, out_h)


def _verify_strip(
    *,
    raw_cell: pygame.Surface,
    crop_rect: pygame.Rect,
    cropped_source: pygame.Surface,
    output: pygame.Surface,
    out_path: Path,
    zoom_src: int = 4,
    zoom_out: int = 10,
) -> None:
    """Write a row: raw cell | cropped region | final file (each magnified for visual QA)."""
    raw_cell = raw_cell.convert_alpha()
    w0, h0 = raw_cell.get_size()
    raw_big = _resize_surface_nearest(raw_cell, w0 * zoom_src, h0 * zoom_src)
    cw, ch = cropped_source.get_size()
    crop_big = _resize_surface_nearest(cropped_source, max(1, cw * zoom_src), max(1, ch * zoom_src))
    ow, oh = output.get_size()
    out_big = _resize_surface_nearest(output, ow * zoom_out, oh * zoom_out)
    gap = 8
    total_w = raw_big.get_width() + gap + crop_big.get_width() + gap + out_big.get_width()
    total_h = max(raw_big.get_height(), crop_big.get_height(), out_big.get_height()) + 36
    sheet = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
    sheet.fill((40, 40, 48, 255))
    y0 = 28
    x = 0
    sheet.blit(raw_big, (x, y0))
    x += raw_big.get_width() + gap
    sheet.blit(crop_big, (x, y0))
    x += crop_big.get_width() + gap
    sheet.blit(out_big, (x, y0))
    try:
        font = pygame.font.Font(None, 18)
        sheet.blit(font.render("100x100 cell", True, (220, 220, 230)), (4, 4))
        sheet.blit(
            font.render(f"crop {crop_rect.w}x{crop_rect.h}", True, (220, 220, 230)),
            (raw_big.get_width() + gap + 4, 4),
        )
        sheet.blit(
            font.render(f"out {ow}x{oh}", True, (220, 220, 230)),
            (raw_big.get_width() + gap + crop_big.get_width() + gap + 4, 4),
        )
    except Exception:
        pass
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, str(out_path))


def _shrink_crop_if_oversized(
    rect: pygame.Rect,
    *,
    out_w: int,
    out_h: int,
    frame_w: int,
    frame_h: int,
    cap_factor: int,
) -> pygame.Rect:
    """If union crop is much larger than the output pixel budget, use a centered square cap.

    Wide attack swings can exceed ~48px; downsampling 63px into 16px destroys pixels. Capping
    the crop (default ``max(out)*3``) keeps nearest-neighbor downscales readable.
    """
    if cap_factor <= 0:
        return rect
    cap = max(int(out_w), int(out_h)) * cap_factor
    if max(rect.w, rect.h) <= cap:
        return rect
    side = min(cap, frame_w, frame_h)
    cx, cy = rect.centerx, rect.centery
    shrunk = pygame.Rect(0, 0, side, side)
    shrunk.center = (cx, cy)
    bounds = pygame.Rect(0, 0, frame_w, frame_h)
    return shrunk.clip(bounds)


def _out_action_dir(repo: Path, kingdom_category: str, kingdom_unit: str, kingdom_action: str) -> Path:
    kc = (kingdom_category or "").strip().lower()
    if kc == "heroes":
        base = repo / "assets" / "sprites" / "heroes"
    elif kc == "enemies":
        base = repo / "assets" / "sprites" / "enemies"
    elif kc == "workers":
        base = repo / "assets" / "sprites" / "workers"
    else:
        raise ValueError(f"Unknown kingdom_category {kingdom_category!r} (expected heroes|enemies|workers)")
    return base / (kingdom_unit or "").strip().lower() / (kingdom_action or "").strip().lower()


def _load_map_rows(map_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with map_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "kingdom_category",
            "kingdom_unit",
            "tiny_rpg_character",
            "kingdom_action",
            "source_filename",
            "merge_index",
        }
        if reader.fieldnames is None:
            raise ValueError(f"Map CSV has no header: {map_csv}")
        missing = required - {x.strip() for x in reader.fieldnames if x}
        if missing:
            raise ValueError(f"Map CSV missing columns {missing}: got {reader.fieldnames}")
        for raw in reader:
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            if not any(row.values()):
                continue
            rows.append(row)
    return rows


def _group_key(r: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        r["kingdom_category"].lower(),
        r["kingdom_unit"].lower(),
        r["tiny_rpg_character"],
        r["kingdom_action"].lower(),
    )


def export_all(
    *,
    pack_root: Path,
    map_csv: Path,
    repo: Path,
    frame_w: int,
    frame_h: int,
    out_w: int,
    out_h: int,
    dry_run: bool,
    clean_action: bool,
    content_crop: bool,
    content_pad: int,
    crop_cap_factor: int,
    scale_crop_to_fit: bool,
    only_units: set[tuple[str, str]] | None,
    verify: bool,
) -> int:
    rows = _load_map_rows(map_csv)
    groups: dict[tuple[str, str, str, str], list[tuple[int, str]]] = {}
    for r in rows:
        key = _group_key(r)
        mi = int(r["merge_index"])
        fn = r["source_filename"]
        groups.setdefault(key, []).append((mi, fn))
    for key in groups:
        groups[key].sort(key=lambda t: t[0])

    verify_root = repo / "docs" / "screenshots" / "tiny_rpg_export_verify"

    errors = 0
    for key, parts in sorted(groups.items(), key=lambda kv: kv[0]):
        kc, ku, character, action = key
        if only_units and (kc, ku) not in only_units:
            continue
        inner = _resolve_inner_character_dir(pack_root, character)
        out_dir = _out_action_dir(repo, kc, ku, action)
        all_frames: list[pygame.Surface] = []

        print(f"\n== {kc}/{ku}/{action} <= {character} ==")
        if dry_run:
            print(f"  OUT {out_dir} (dry-run)")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            if clean_action:
                for stale in out_dir.glob("*.png"):
                    try:
                        stale.unlink()
                    except OSError as e:
                        print(f"  WARN could not remove {stale}: {e}", file=sys.stderr)

        group_errors = 0
        for merge_idx, fname in parts:
            png_path = _find_png(inner, fname)
            if png_path is None:
                print(f"  ERROR missing file under {inner}: {fname!r}", file=sys.stderr)
                group_errors += 1
                continue
            surf = pygame.image.load(str(png_path))
            try:
                strip_frames = _split_horizontal_strip(surf, frame_w, frame_h)
            except ValueError as e:
                print(f"  ERROR {png_path}: {e}", file=sys.stderr)
                group_errors += 1
                continue
            print(f"  + merge {merge_idx} {png_path.name} -> {len(strip_frames)} frames")
            all_frames.extend(strip_frames)

        if group_errors:
            errors += group_errors
            continue
        if not all_frames:
            print("  ERROR no frames assembled", file=sys.stderr)
            errors += 1
            continue

        crop = pygame.Rect(0, 0, frame_w, frame_h)
        if content_crop:
            union = _union_crop_rect(all_frames, content_pad, frame_w, frame_h)
            crop = _shrink_crop_if_oversized(
                union,
                out_w=out_w,
                out_h=out_h,
                frame_w=frame_w,
                frame_h=frame_h,
                cap_factor=crop_cap_factor,
            )
            print(
                f"  content_union=({union.x},{union.y},{union.w}x{union.h}) "
                f"crop_used=({crop.x},{crop.y},{crop.w}x{crop.h}) pad={content_pad} cap_factor={crop_cap_factor}"
            )

        scaled: list[pygame.Surface] = []
        for f in all_frames:
            if content_crop:
                if scale_crop_to_fit:
                    sub = f.subsurface(crop).copy()
                    out = _crop_fit_canvas(sub, out_w, out_h)
                else:
                    out = _crop_native_canvas(
                        f,
                        crop,
                        out_w=out_w,
                        out_h=out_h,
                        frame_w=frame_w,
                        frame_h=frame_h,
                    )
            else:
                out = _scale_full_frame_nearest(f, out_w, out_h)
            if kc == "heroes" and ku == "rogue":
                out = _apply_rogue_recolor(out)
            scaled.append(out)

        if not dry_run:
            for i, surf in enumerate(scaled):
                out_path = out_dir / f"frame_{i:03d}.png"
                pygame.image.save(surf, str(out_path))
            print(f"  wrote {len(scaled)} -> {out_dir}")

            if verify and content_crop and scaled:
                # Spot-check a few frames against the vendor cell + crop.
                n = len(all_frames)
                idxs = sorted({0, n // 2, n - 1})
                for idx in idxs:
                    raw = all_frames[idx]
                    sub = raw.subsurface(crop).copy()
                    output = scaled[idx]
                    vpath = verify_root / f"{kc}__{ku}__{action}__frame_{idx:03d}.png"
                    _verify_strip(
                        raw_cell=raw,
                        crop_rect=crop,
                        cropped_source=sub,
                        output=output,
                        out_path=vpath,
                    )
                    print(f"  verify -> {vpath}")

    if verify and not dry_run and content_crop:
        print(f"\n[verify] Open images under {verify_root} and compare to vendor PNGs.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Slice Tiny RPG strips into Kingdom Sim sprite folders.")
    parser.add_argument(
        "--pack",
        type=Path,
        default=_repo_root() / "assets" / "sprites" / "vendor" / "tiny_rpg_pack_v1_03",
        help="Vendor pack root (contains Characters(100x100)/).",
    )
    parser.add_argument(
        "--map",
        type=Path,
        default=None,
        help="Map_actions.csv path (default: <pack>/Map_actions.csv).",
    )
    parser.add_argument("--frame-w", type=int, default=100, help="Source frame width in the strip.")
    parser.add_argument("--frame-h", type=int, default=100, help="Source frame height in the strip.")
    parser.add_argument(
        "--out-w",
        type=int,
        default=_DEFAULT_EXPORT_PX,
        help="Exported frame width (default 48 runtime canvas pixels).",
    )
    parser.add_argument(
        "--out-h",
        type=int,
        default=_DEFAULT_EXPORT_PX,
        help="Exported frame height (default 48 runtime canvas pixels).",
    )
    parser.add_argument("--repo", type=Path, default=_repo_root(), help="Repository root.")
    parser.add_argument("--execute", action="store_true", help="Write PNGs (default is dry-run if neither flag).")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only.")
    parser.add_argument(
        "--clean-action",
        action="store_true",
        help="Remove existing frame_*.png in each target action folder before writing (avoids rmtree on locked/OneDrive dirs).",
    )
    parser.add_argument(
        "--no-content-crop",
        action="store_true",
        help="Scale full 100x100 cells to out size (legacy; characters look tiny in-game).",
    )
    parser.add_argument(
        "--content-pad",
        type=int,
        default=2,
        help="Pixels to inflate union bbox after detection (default 2).",
    )
    parser.add_argument(
        "--crop-cap-factor",
        type=int,
        default=0,
        help="If max(union w,h) > max(out)*factor, shrink to a centered square cap (default 0 = never shrink).",
    )
    parser.add_argument(
        "--scale-crop-to-fit",
        action="store_true",
        help="Legacy mode: scale the content crop to fill the output canvas instead of pasting native pixels.",
    )
    parser.add_argument(
        "--only-unit",
        action="append",
        default=[],
        metavar="CATEGORY/UNIT",
        help="Optional filter, e.g. heroes/warrior. Can be passed more than once.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After export, write magnified compare strips under docs/screenshots/tiny_rpg_export_verify/.",
    )
    args = parser.parse_args()
    pack_root = args.pack.resolve()
    map_csv = args.map or (pack_root / "Map_actions.csv")
    if not map_csv.is_file():
        print(f"Map CSV not found: {map_csv}", file=sys.stderr)
        return 2
    if not _characters_root(pack_root).is_dir():
        print(f"Characters folder not found: {_characters_root(pack_root)}", file=sys.stderr)
        return 2

    dry_run = args.dry_run or not args.execute
    if dry_run and args.execute:
        print("Use only one of --dry-run or --execute", file=sys.stderr)
        return 2

    pygame.init()
    pygame.display.set_mode((1, 1))

    content_crop = not args.no_content_crop
    print(f"pack_root={pack_root}")
    print(f"map_csv={map_csv}")
    print(
        f"frame={args.frame_w}x{args.frame_h} -> out={args.out_w}x{args.out_h} "
        f"content_crop={content_crop} native_canvas={not args.scale_crop_to_fit} dry_run={dry_run}"
    )
    only_units: set[tuple[str, str]] | None = None
    if args.only_unit:
        only_units = set()
        for raw in args.only_unit:
            parts = str(raw).strip().lower().replace("\\", "/").split("/")
            if len(parts) != 2 or parts[0] not in {"heroes", "enemies", "workers"} or not parts[1]:
                print(
                    f"Invalid --only-unit {raw!r}; expected heroes/<unit> or enemies/<unit> or workers/<unit>",
                    file=sys.stderr,
                )
                return 2
            only_units.add((parts[0], parts[1]))
        print(f"only_units={sorted(only_units)}")

    err = export_all(
        pack_root=pack_root,
        map_csv=map_csv,
        repo=args.repo.resolve(),
        frame_w=args.frame_w,
        frame_h=args.frame_h,
        out_w=args.out_w,
        out_h=args.out_h,
        dry_run=dry_run,
        clean_action=args.clean_action,
        content_crop=content_crop,
        content_pad=max(0, int(args.content_pad)),
        crop_cap_factor=max(0, int(args.crop_cap_factor)),
        scale_crop_to_fit=bool(args.scale_crop_to_fit),
        only_units=only_units,
        verify=bool(args.verify),
    )
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
