"""
Split Legacy Vania horizontal strips into Kingdom worker sprite folders.

Peasants: one walk strip (+ stub fallback) with letterboxing and optional content scale.

Tax collector: **npc-cape2** character only — composes vendor strips into
workers/tax_collector/{idle,walk,return,collect,hurt,dead,rest}/frame_*.png
(no knife walk or knife-attack strips; collect uses jab only; return matches walk).

Letterboxing: **nearest-neighbor** scale to fit inside the output square (no bilinear blur).
Optional ``--content-scale`` (< 1) shrinks the source *before* the fit (legacy tuning); default **1.0**
keeps vendor resolution. On-screen size in Ursina is controlled by ``URSINA_WORKER_BILLBOARD_BASE``
in ``config.py``, not by shrinking textures here.

PowerShell (repo root):
  python tools/legacy_vania_export_worker_frames.py --execute
  python tools/legacy_vania_export_worker_frames.py --execute --verify
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import pygame

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

from game.graphics.pixel_scale import scale_surface_nearest


def _ensure_pygame_headless() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    if not pygame.get_init():
        pygame.init()
    if pygame.display.get_surface() is None:
        hidden = int(getattr(pygame, "HIDDEN", 0) or 0)
        pygame.display.set_mode((1, 1), hidden)


REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / "assets" / "sprites" / "vendor" / "legacy-vania-npc-v7" / "spritesheets"
WORKERS_ROOT = REPO_ROOT / "assets" / "sprites" / "workers"

DEFAULT_PEASANT_WALK = "npc-villager1-fisherman_walk.png"
FALLBACK_PEASANT_WALK = "npc-villager10-anim-walk_strip6.png"
LIKELY_STUB_MAX_BYTES = 600
DEFAULT_CONTENT_SCALE = 1.0


def _is_stub_file(path: Path) -> bool:
    try:
        return path.stat().st_size < LIKELY_STUB_MAX_BYTES
    except OSError:
        return True


def _pick_peasant_strip(primary_name: str) -> Path:
    primary = VENDOR_DIR / primary_name
    fb = VENDOR_DIR / FALLBACK_PEASANT_WALK
    if primary.is_file() and not _is_stub_file(primary):
        return primary
    if primary.is_file() and _is_stub_file(primary):
        print(
            f"[legacy_vania_export] WARN peasant: '{primary_name}' looks like a stub "
            f"({primary.stat().st_size} bytes); using '{FALLBACK_PEASANT_WALK}'.",
            file=sys.stderr,
        )
        if fb.is_file():
            return fb
        return primary
    if fb.is_file():
        print(f"[legacy_vania_export] WARN peasant: missing '{primary_name}'; using '{FALLBACK_PEASANT_WALK}'.", file=sys.stderr)
        return fb
    raise FileNotFoundError(f"No peasant strip: {primary} / {fb}")


def split_cells_from_surface(surf: pygame.Surface, filename: str) -> list[pygame.Surface]:
    """Split a horizontal strip into frame cells (supports non-square cells via _stripN)."""
    w, h = surf.get_width(), surf.get_height()
    m = re.search(r"_strip(\d+)", filename, re.I)
    if m:
        n = int(m.group(1))
        if w % n != 0:
            raise ValueError(f"{filename}: width {w} not divisible by _strip{n}")
        fw = w // n
    elif h > 0 and w >= h and w % h == 0 and (w // h) >= 2:
        n = w // h
        fw = h
    else:
        return [surf.copy()]
    out: list[pygame.Surface] = []
    for i in range(n):
        out.append(surf.subsurface((i * fw, 0, fw, h)).copy())
    return out


def load_cells(vendor_filename: str) -> list[pygame.Surface]:
    p = VENDOR_DIR / vendor_filename
    if not p.is_file():
        raise FileNotFoundError(p)
    surf = pygame.image.load(str(p)).convert_alpha()
    return split_cells_from_surface(surf, p.name)


def load_full_frame(vendor_filename: str) -> list[pygame.Surface]:
    p = VENDOR_DIR / vendor_filename
    if not p.is_file():
        raise FileNotFoundError(p)
    return [pygame.image.load(str(p)).convert_alpha()]


def _key_black_background(surf: pygame.Surface, *, threshold: int = 12) -> pygame.Surface:
    w, h = surf.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            r, g, b, a = int(c[0]), int(c[1]), int(c[2]), int(c[3]) if len(c) > 3 else 255
            if r <= threshold and g <= threshold and b <= threshold:
                out.set_at((x, y), (0, 0, 0, 0))
            else:
                out.set_at((x, y), (r, g, b, a))
    return out


def letterbox_nearest(src: pygame.Surface, size: int, *, content_scale: float = 1.0) -> pygame.Surface:
    """Uniform nearest-neighbor scale to fit inside ``size``×``size``; center on transparency."""
    sw, sh = src.get_width(), src.get_height()
    if sw <= 0 or sh <= 0:
        raise ValueError("empty surface")
    if content_scale != 1.0:
        tsw = max(1, int(round(sw * content_scale)))
        tsh = max(1, int(round(sh * content_scale)))
        if (tsw, tsh) != (sw, sh):
            src = scale_surface_nearest(src, tsw, tsh)
        sw, sh = src.get_width(), src.get_height()
    scale = min(size / sw, size / sh)
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    scaled = scale_surface_nearest(src, nw, nh) if (nw, nh) != (sw, sh) else src.copy()
    canvas = pygame.Surface((size, size), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas.blit(scaled, (ox, oy))
    return canvas


def _recolor_straw_hat_to_green(surf: pygame.Surface) -> pygame.Surface:
    w, h = surf.get_size()
    out = surf.copy()
    y_max = max(1, int(h * 0.38))
    for y in range(y_max):
        for x in range(w):
            c = surf.get_at((x, y))
            if len(c) < 4 or int(c[3]) < 8:
                continue
            r, g, b = int(c[0]), int(c[1]), int(c[2])
            warm = (r + g) > (b + 100)
            straw_like = r >= 158 and g >= 125 and b <= 118 and warm and (r - b) >= 38
            shadow_hat = (
                y < int(h * 0.25)
                and r >= 105
                and g >= 82
                and b <= 72
                and (r - b) >= 28
                and warm
            )
            if straw_like or shadow_hat:
                t = (r + g + b) // 3
                nr = max(0, min(255, 22 + t // 5))
                ng = max(0, min(255, 95 + t // 2))
                nb = max(0, min(255, 32 + t // 6))
                out.set_at((x, y), (nr, ng, nb, int(c[3])))
    return out


def _write_frames(dir_path: Path, frames: list[pygame.Surface]) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    for old in dir_path.glob("frame_*.png"):
        old.unlink()
    for i, fr in enumerate(frames):
        pygame.image.save(fr, dir_path / f"frame_{i:03d}.png")


def _bootstrap_stub_strips() -> None:
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_pygame_headless()

    def make_strip(n: int, color: tuple[int, int, int], w: int = 48, h: int = 48) -> pygame.Surface:
        surf = pygame.Surface((n * w, h))
        surf.fill((0, 0, 0))
        for i in range(n):
            pygame.draw.rect(surf, color, (i * w + 4, 8, w - 8, h - 16))
            pygame.draw.circle(surf, (min(255, color[0] + 40), color[1], color[2]), (i * w + w // 2, 14), 6)
        return surf

    pygame.image.save(make_strip(6, (90, 90, 110)), VENDOR_DIR / "npc-believer-1_walk_strip6.png")
    pygame.image.save(make_strip(4, (110, 100, 95)), VENDOR_DIR / "npc-believer-1_yes_strip4.png")
    pygame.image.save(make_strip(6, (70, 120, 90)), VENDOR_DIR / DEFAULT_PEASANT_WALK)
    print(f"[legacy_vania_export] Wrote stub strips under {VENDOR_DIR}")


def _opaque_bbox(surf: pygame.Surface) -> tuple[int, int, int, int] | None:
    w, h = surf.get_size()
    min_x, min_y = w, h
    max_x = max_y = -1
    for y in range(h):
        for x in range(w):
            if surf.get_at((x, y))[3] > 8:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < 0:
        return None
    return min_x, min_y, max_x - min_x + 1, max_y - min_y + 1


def _process_cells(cells: list[pygame.Surface], frame_size: int, content_scale: float) -> list[pygame.Surface]:
    return [letterbox_nearest(_key_black_background(c), frame_size, content_scale=content_scale) for c in cells]


def export_tax_collector_cape2(*, frame_size: int, content_scale: float) -> None:
    """All motion uses npc-cape2 art from the vendor folder (single character)."""
    tc_root = WORKERS_ROOT / "tax_collector"
    if tc_root.is_dir():
        allowed = {"idle", "walk", "return", "collect", "hurt", "dead", "rest"}
        for child in tc_root.iterdir():
            if child.is_dir() and child.name not in allowed:
                try:
                    shutil.rmtree(child)
                except OSError as exc:
                    print(
                        f"[legacy_vania_export] WARN: remove stale folder {child} manually ({exc})",
                        file=sys.stderr,
                    )

    idle = _process_cells(load_cells("npc-cape2-idle-stance_strip4.png"), frame_size, content_scale)
    # Walk + return: same non-knife locomotion (no walk-knife / walk-stance-knife strips).
    walk_raw = load_cells("npc-cape2-walk-stance_strip4.png") + load_cells("npc-cape2-walk_strip6.png")
    walk = _process_cells(walk_raw, frame_size, content_scale)
    ret = _process_cells(walk_raw, frame_size, content_scale)
    # Collect: jab-only (no knife-attack strip).
    collect = _process_cells(load_cells("npc-cape2-jab.png"), frame_size, content_scale)
    hurt = _process_cells(
        load_full_frame("npc-cape2-stronghurt.png")
        + load_cells("npc-cape2-hurt_strip2.png")
        + load_cells("npc-cape2-ground-recover_strip2.png"),
        frame_size,
        content_scale,
    )
    dead = _process_cells(load_cells("npc-cape2-fall_strip10.png"), frame_size, content_scale)
    rest = _process_cells(
        load_full_frame("npc-cape2-waiting-crouch.png")
        + load_full_frame("npc-cape2-waiting-crouch-front.png")
        + load_full_frame("npc-cape2-waiting-crouch-back.png"),
        frame_size,
        content_scale,
    )

    _write_frames(WORKERS_ROOT / "tax_collector" / "idle", idle)
    _write_frames(WORKERS_ROOT / "tax_collector" / "walk", walk)
    _write_frames(WORKERS_ROOT / "tax_collector" / "return", ret)
    _write_frames(WORKERS_ROOT / "tax_collector" / "collect", collect)
    _write_frames(WORKERS_ROOT / "tax_collector" / "hurt", hurt)
    _write_frames(WORKERS_ROOT / "tax_collector" / "dead", dead)
    _write_frames(WORKERS_ROOT / "tax_collector" / "rest", rest)


def export_peasants(*, peasant_strip: str | None, frame_size: int, content_scale: float, verify: bool) -> None:
    pw = peasant_strip or DEFAULT_PEASANT_WALK
    peasant_path = _pick_peasant_strip(pw)
    fish_src = pygame.image.load(str(peasant_path)).convert_alpha()
    fish_raw = split_cells_from_surface(fish_src, peasant_path.name)
    fish_frames = _process_cells(fish_raw, frame_size, content_scale)
    _write_frames(WORKERS_ROOT / "peasant" / "walk", fish_frames)
    _write_frames(WORKERS_ROOT / "peasant" / "idle", [fish_frames[0]])
    _write_frames(WORKERS_ROOT / "peasant" / "work", list(fish_frames))

    fish_green = [_recolor_straw_hat_to_green(f) for f in fish_frames]
    _write_frames(WORKERS_ROOT / "peasant_builder" / "walk", fish_green)
    _write_frames(WORKERS_ROOT / "peasant_builder" / "idle", [fish_green[0]])
    _write_frames(WORKERS_ROOT / "peasant_builder" / "work", list(fish_green))

    if verify:
        _verify_peasant_matches_strip(peasant_path, fish_raw[0], frame_size, content_scale)


def export_all(
    *,
    frame_size: int,
    content_scale: float,
    peasant_strip: str | None,
    verify: bool,
) -> None:
    _ensure_pygame_headless()
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    export_tax_collector_cape2(frame_size=frame_size, content_scale=content_scale)
    export_peasants(peasant_strip=peasant_strip, frame_size=frame_size, content_scale=content_scale, verify=verify)

    _invalidate_runtime_caches()

    print(
        f"[legacy_vania_export] OK -> {WORKERS_ROOT} ({frame_size}px, content_scale={content_scale})\n"
        f"  tax_collector: npc-cape2 set (idle/walk/return/collect/hurt/dead/rest)\n"
        f"  peasant strip: {_pick_peasant_strip(peasant_strip or DEFAULT_PEASANT_WALK).name}"
    )


def _invalidate_runtime_caches() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from game.graphics.unit_atlas import UnitAtlasBuilder
        from game.graphics.worker_sprites import WorkerSpriteLibrary

        UnitAtlasBuilder._instance = None
        WorkerSpriteLibrary._cache.clear()
    except Exception as exc:
        print(f"[legacy_vania_export] note: cache invalidate skipped ({exc})", file=sys.stderr)


def _verify_peasant_matches_strip(
    vendor_path: Path, first_cell_raw: pygame.Surface, frame_size: int, content_scale: float
) -> None:
    exported = pygame.image.load(str(WORKERS_ROOT / "peasant" / "walk" / "frame_000.png")).convert_alpha()
    exp_bbox = _opaque_bbox(exported)
    raw_bbox = _opaque_bbox(_key_black_background(first_cell_raw.copy()))
    key_raw = letterbox_nearest(
        _key_black_background(first_cell_raw.copy()), frame_size, content_scale=content_scale
    )
    key_bbox = _opaque_bbox(key_raw)
    print("[legacy_vania_export] verify:")
    print(f"  vendor strip: {vendor_path}")
    print(f"  raw cell opaque bbox (after black-key): {raw_bbox}")
    print(f"  letterboxed opaque bbox: {key_bbox}")
    print(f"  exported frame_000 opaque bbox: {exp_bbox}")
    if exp_bbox is None or exp_bbox[2] < 8 or exp_bbox[3] < 8:
        print("  FAILED: exported frame has almost no opaque pixels.", file=sys.stderr)
        sys.exit(3)
    if raw_bbox and exp_bbox:
        raw_area = raw_bbox[2] * raw_bbox[3]
        exp_area = exp_bbox[2] * exp_bbox[3]
        if exp_area < raw_area * 0.08:
            print("  FAILED: exported silhouette area far smaller than source — pipeline bug?", file=sys.stderr)
            sys.exit(3)
    print("  PASS silhouette sanity check")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Legacy Vania NPC strips to worker sprite folders.")
    ap.add_argument("--bootstrap-stubs", action="store_true", help="Write placeholder vendor PNGs (dev only).")
    ap.add_argument("--execute", action="store_true", help="Split strips and write workers/*/ frames.")
    ap.add_argument("--verify", action="store_true", help="After export, sanity-check peasant frame_000 silhouette.")
    ap.add_argument("--frame-size", type=int, default=None, help="Square canvas size (default: UNIT_SPRITE_PIXELS)")
    ap.add_argument(
        "--content-scale",
        type=float,
        default=None,
        help=f"Character scale before letterbox fit (default: {DEFAULT_CONTENT_SCALE})",
    )
    ap.add_argument("--peasant-strip", type=str, default=None, help="Filename under spritesheets/ for peasant walk")
    args = ap.parse_args()

    if args.bootstrap_stubs:
        _bootstrap_stub_strips()
        return 0
    if not args.execute:
        ap.print_help()
        return 0

    sys.path.insert(0, str(REPO_ROOT))
    import config as _cfg

    fs = int(args.frame_size if args.frame_size is not None else getattr(_cfg, "UNIT_SPRITE_PIXELS", 48))
    cs = float(args.content_scale if args.content_scale is not None else DEFAULT_CONTENT_SCALE)
    if cs <= 0 or cs > 1.5:
        print("[legacy_vania_export] ERROR: --content-scale must be in (0, 1.5]", file=sys.stderr)
        return 2

    export_all(frame_size=fs, content_scale=cs, peasant_strip=args.peasant_strip, verify=bool(args.verify))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
