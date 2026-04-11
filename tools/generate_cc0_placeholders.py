"""
Generate small original CC0 placeholder sprites (WK3 Build B).

Purpose:
- Unblock end-to-end asset ingestion pipeline and strict validator.
- Replace procedural "letters/shapes" with real PNG files without pulling large third-party packs.

Notes:
- These are intentionally simple and consistent; meant to be replaced later by curated third-party packs.
- Output files follow existing loader conventions:
  assets/sprites/<category>/<kind>/<state>/frame_000.png
"""

from __future__ import annotations

import json
from pathlib import Path

import pygame


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
MANIFEST = ROOT / "tools" / "assets_manifest.json"

# 2D frame-state lists for CC0 PNG output (decoupled from assets_manifest.json v1.5+,
# which tracks one 3D model file per kind instead of per-state folders).
_LEGACY_HERO_STATES = ["idle", "walk", "attack", "hurt", "inside"]
_LEGACY_ENEMY_STATES = ["idle", "walk", "attack", "hurt", "dead"]
_LEGACY_BUILDING_STATES = ["built", "construction", "damaged"]
_LEGACY_WORKER_STATES = ["idle", "walk", "work", "collect", "return", "hurt", "dead"]

try:
    # Optional import for native-size building sprites (avoids scaling artifacts).
    from config import BUILDING_SIZES, TILE_SIZE
except Exception:
    BUILDING_SIZES = {}
    TILE_SIZE = 32


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _save(surf: pygame.Surface, path: Path) -> None:
    _ensure_dir(path.parent)
    pygame.image.save(surf, str(path))


def _mk32() -> pygame.Surface:
    return pygame.Surface((32, 32), pygame.SRCALPHA)

def _mk(size: int) -> pygame.Surface:
    s = max(8, int(size))
    return pygame.Surface((s, s), pygame.SRCALPHA)


def _clamp8(x: int) -> int:
    return max(0, min(255, int(x)))


def _shade(rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    r, g, b = rgb
    return (_clamp8(r + delta), _clamp8(g + delta), _clamp8(b + delta))


def _outline_poly(s: pygame.Surface, pts, fill, outline=(20, 20, 25)) -> None:
    pygame.draw.polygon(s, outline, pts, 0)
    pygame.draw.polygon(s, fill, pts, 0)
    pygame.draw.polygon(s, outline, pts, 1)


def _draw_shadow(s: pygame.Surface, rect: pygame.Rect, alpha: int = 60) -> None:
    sh = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    sh.fill((0, 0, 0, max(0, min(255, int(alpha)))))
    s.blit(sh, rect.topleft)


def _draw_construction_overlay(s: pygame.Surface) -> None:
    w, h = s.get_width(), s.get_height()
    # subtle darkening
    ov = pygame.Surface((w, h), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 40))
    s.blit(ov, (0, 0))
    # scaffolding beams (deterministic pattern)
    beam = (150, 120, 80)
    for x in range(6, w, 18):
        pygame.draw.line(s, beam, (x, h - 6), (x - 16, 6), 3)
    for y in range(10, h, 22):
        pygame.draw.line(s, beam, (6, y), (w - 6, y), 2)


def _draw_damaged_overlay(s: pygame.Surface) -> None:
    w, h = s.get_width(), s.get_height()
    # cracks + small smoke puff
    crack = (30, 30, 35)
    pygame.draw.line(s, crack, (w * 0.35, h * 0.35), (w * 0.55, h * 0.6), 2)
    pygame.draw.line(s, crack, (w * 0.55, h * 0.6), (w * 0.45, h * 0.78), 2)
    pygame.draw.circle(s, (80, 80, 80, 120), (int(w * 0.65), int(h * 0.25)), int(max(3, min(w, h) * 0.06)), 0)
    # slight darken
    ov = pygame.Surface((w, h), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 35))
    s.blit(ov, (0, 0))


def _outline_rect(s: pygame.Surface, r: pygame.Rect, fill, outline=(20, 20, 25)) -> None:
    pygame.draw.rect(s, outline, r, 0)
    pygame.draw.rect(s, fill, r.inflate(-2, -2), 0)


def _hero_frames(hero_class: str, state: str) -> list[pygame.Surface]:
    import math
    st = (state or "idle").lower()
    counts = {"idle": 6, "walk": 8, "attack": 6, "hurt": 4, "inside": 6}
    num_frames = counts.get(st, 1)

    frames = []
    # Class accents
    accents = {
        "warrior": (70, 120, 255),
        "ranger": (70, 200, 120),
        "rogue": (180, 180, 200),
        "wizard": (170, 90, 230),
    }
    acc = accents.get(hero_class, (220, 220, 220))
    skin = (255, 210, 180)
    dark = (20, 20, 25)
    
    for i in range(num_frames):
        s = _mk32()
        s.fill((0, 0, 0, 0))
        t = i / float(num_frames) if num_frames > 1 else 0

        if st == "inside":
            pygame.draw.circle(s, (245, 245, 245, 230), (16, 16), int(10 + 2 * math.sin(t * math.tau)), 2)
            pygame.draw.circle(s, (255, 215, 80, 210), (18, 14), 2, 0)
            frames.append(s)
            continue

        bob = int(max(0, math.sin(t * math.tau) * 2)) if st == "idle" else 0
        lean = int(math.sin(t * math.tau) * 1.5) if st == "walk" else 0
        if st == "hurt":
            lean = -2 if i % 2 == 0 else 2
        elif st == "attack":
            lean = 3 if t > 0.3 else -1

        # Body Base
        bx, by = 16 + lean, 18 + bob
        # Head
        pygame.draw.rect(s, dark, pygame.Rect(bx - 4, by - 12, 8, 8))
        pygame.draw.rect(s, skin, pygame.Rect(bx - 3, by - 11, 6, 6))
        
        # Torso
        pygame.draw.rect(s, dark, pygame.Rect(bx - 5, by - 4, 10, 8))
        pygame.draw.rect(s, acc, pygame.Rect(bx - 4, by - 3, 8, 5))
        pygame.draw.rect(s, _shade(acc, -20), pygame.Rect(bx - 4, by + 2, 8, 2))

        # Legs (Walking logic)
        leg_base = by + 4
        if st == "walk":
            l_off = int(math.sin(t * math.tau) * 4)
            r_off = int(math.cos(t * math.tau) * 4)
        else:
            l_off, r_off = -2, 2

        # Left Leg
        pygame.draw.rect(s, dark, pygame.Rect(bx - 3 + l_off, leg_base, 4, 6))
        pygame.draw.rect(s, (100, 100, 100), pygame.Rect(bx - 2 + l_off, leg_base, 2, 5))
        # Right Leg
        pygame.draw.rect(s, dark, pygame.Rect(bx - 1 + r_off, leg_base, 4, 6))
        pygame.draw.rect(s, (100, 100, 100), pygame.Rect(bx + r_off, leg_base, 2, 5))

        # Attack logic (arms / weapons)
        hc_lower = (hero_class or "").lower()
        if st == "attack":
            if hc_lower == "warrior":
                start_x, start_y = bx - 2, by - 4
                end_x, end_y = bx + 10, by - 14 + int(28 * t)
                pygame.draw.line(s, (220, 220, 225), (start_x, start_y), (end_x, end_y), 3)
                pygame.draw.line(s, (255, 255, 255), (start_x+1, start_y), (end_x, end_y), 1)
                pygame.draw.rect(s, (255, 200, 50), pygame.Rect(start_x-1, start_y-1, 3, 3))
            elif hc_lower == "ranger":
                pygame.draw.line(s, dark, (bx+4, by-8), (bx+6, by+4), 2)
                pygame.draw.line(s, (200, 200, 200), (bx+4, by-8), (bx+4, by+4), 1)
                if t > 0.2:
                    pygame.draw.line(s, (220, 200, 150), (bx, by-2), (bx+14, by-4), 2)
            elif hc_lower == "wizard":
                pygame.draw.line(s, (100, 60, 20), (bx+2, by+8), (bx+10, by-10), 2)
                glow_r = int(6 * math.sin(t * math.pi))
                if glow_r > 0:
                    pygame.draw.circle(s, (200, 150, 255, 150), (bx+10, by-10), glow_r)
                    pygame.draw.circle(s, (255, 255, 255), (bx+10, by-10), 2)
            elif hc_lower == "rogue":
                dx1, dy1 = bx + 8, by - 4 + int(8 * t)
                dx2, dy2 = bx + 10, by + 6 - int(10 * t)
                pygame.draw.line(s, (180, 180, 190), (bx, by-2), (dx1, dy1), 2)
                pygame.draw.line(s, (180, 180, 190), (bx+2, by+2), (dx2, dy2), 2)
        else:
            pygame.draw.rect(s, skin, pygame.Rect(bx - 6, by - 2, 2, 4))
            pygame.draw.rect(s, skin, pygame.Rect(bx + 4, by - 2, 2, 4))

        if st == "hurt":
            ov = pygame.Surface((32, 32), pygame.SRCALPHA)
            ov.fill((255, 60, 60, 80))
            s.blit(ov, (0, 0))

        frames.append(s)
    return frames



def _enemy_frames(enemy_type: str, state: str) -> list[pygame.Surface]:
    import math
    et = (enemy_type or "goblin").lower()
    st = (state or "idle").lower()
    
    counts = {"idle": 6, "walk": 8, "attack": 6, "hurt": 4, "dead": 1}
    num_frames = counts.get(st, 1)

    base = {
        "goblin": (90, 170, 90),
        "wolf": (160, 160, 160),
        "skeleton": (220, 220, 240),
        "skeleton_archer": (220, 220, 240),
        "spider": (50, 50, 55),
        "bandit": (140, 100, 65),
    }.get(et, (150, 150, 150))

    dark = (20, 20, 25)
    hi = _shade(base, 35)
    mid = base
    sh = _shade(base, -25)

    frames = []
    
    for i in range(num_frames):
        s = _mk32()
        s.fill((0, 0, 0, 0))
        t = i / float(num_frames) if num_frames > 1 else 0
        
        # Animations
        bob = int(max(0, math.sin(t * math.tau) * 2)) if st == "idle" else 0
        lean = int(math.sin(t * math.tau) * 1.5) if st == "walk" else 0
        if st == "hurt":
            lean = -2 if i % 2 == 0 else 2
        elif st == "attack":
            lean = 4 if t > 0.3 else -2
        elif st == "dead":
            lean = 0
            
        bx, by = 16 + lean, 18 + bob

        if et == "goblin":
            pygame.draw.circle(s, dark, (bx-1, by-5), 7)
            pygame.draw.circle(s, mid, (bx-1, by-5), 6)
            pygame.draw.circle(s, sh, (bx-3, by-7), 3)
            _outline_rect(s, pygame.Rect(bx-4, by, 8, 10), mid)
            pygame.draw.rect(s, hi, pygame.Rect(bx-4, by, 8, 3))
            pygame.draw.rect(s, (250, 250, 250), pygame.Rect(bx-3, by-6, 2, 2))
            pygame.draw.rect(s, (250, 250, 250), pygame.Rect(bx, by-6, 2, 2))
            arm_y = by
            if st == "attack":
                pygame.draw.line(s, dark, (bx+3, arm_y), (bx+12+int(4*t), arm_y-4+int(8*t)), 2)
                pygame.draw.line(s, (220, 220, 230), (bx+10, arm_y-5), (bx+14+int(4*t), arm_y-7+int(8*t)), 2)
            else:
                pygame.draw.line(s, dark, (bx+3, arm_y), (bx+9, arm_y+2), 2)
                pygame.draw.line(s, (220, 220, 230), (bx+8, arm_y+1), (bx+11, arm_y), 2)
                
            l_off = int(math.sin(t * math.tau) * 3) if st == "walk" else 0
            r_off = int(math.cos(t * math.tau) * 3) if st == "walk" else 0
            pygame.draw.rect(s, dark, pygame.Rect(bx-3+l_off, by+10, 2, 3))
            pygame.draw.rect(s, dark, pygame.Rect(bx+1+r_off, by+10, 2, 3))

        elif et == "wolf":
            wx, wy = bx-2, by+4
            _outline_rect(s, pygame.Rect(wx-9, wy-2, 18, 8), mid)
            pygame.draw.rect(s, hi, pygame.Rect(wx-9, wy-2, 18, 2))
            _outline_rect(s, pygame.Rect(wx+6, wy-4, 7, 6), mid)
            pygame.draw.rect(s, sh, pygame.Rect(wx+6, wy, 7, 2))
            t_wag = int(math.sin(t * math.tau * 2) * 2) if st == "idle" else 0
            pygame.draw.line(s, dark, (wx-9, wy), (wx-13, wy-2+t_wag), 2)
            step = 2 if st == "walk" else 0
            pygame.draw.rect(s, dark, pygame.Rect(wx-6, wy+6, 2, 2 + step*math.sin(t*math.tau)))
            pygame.draw.rect(s, dark, pygame.Rect(wx+0, wy+6, 2, 2 - step*math.sin(t*math.tau)))
            if st == "attack":
                pygame.draw.line(s, (255, 245, 220), (wx+8, wy-4), (wx+15, wy-7), 2)

        elif "skeleton" in et:
            pygame.draw.circle(s, dark, (bx, by-7), 6)
            pygame.draw.circle(s, mid, (bx, by-7), 5)
            pygame.draw.rect(s, dark, pygame.Rect(bx-2, by-8, 2, 2))
            pygame.draw.rect(s, dark, pygame.Rect(bx+1, by-8, 2, 2))
            _outline_rect(s, pygame.Rect(bx-4, by-2, 8, 10), mid)
            for j in range(3):
                pygame.draw.line(s, sh, (bx-3, by+j*2), (bx+3, by+j*2), 1)

            if et == "skeleton":
                if st == "attack":
                    pygame.draw.line(s, dark, (bx+3, by), (bx+13, by-4+int(8*t)), 2)
                    pygame.draw.line(s, (200, 200, 210), (bx+11, by-5), (bx+15, by-7+int(8*t)), 2)
            else:
                if st == "attack":
                    pygame.draw.line(s, dark, (bx+6, by-8), (bx+10, by+4), 2)
                    pygame.draw.line(s, (200, 200, 210), (bx+8, by-8), (bx+8, by+4), 1)
                    pygame.draw.line(s, (255, 245, 220), (bx+10, by-4), (bx+15, by-6), 2)
                else:
                    pygame.draw.line(s, dark, (bx+6, by-6), (bx+9, by+5), 2)
                    pygame.draw.line(s, (200, 200, 210), (bx+7, by-6), (bx+7, by+5), 1)
                    pygame.draw.rect(s, (120, 75, 55), pygame.Rect(bx-7, by-2, 3, 8))
                    
            l_off = int(math.sin(t * math.tau) * 3) if st == "walk" else 0
            r_off = int(math.cos(t * math.tau) * 3) if st == "walk" else 0
            pygame.draw.line(s, mid, (bx-2, by+8), (bx-2+l_off, by+13), 2)
            pygame.draw.line(s, mid, (bx+2, by+8), (bx+2+r_off, by+13), 2)

        elif "spider" in et:
            pygame.draw.circle(s, dark, (bx, by), 8)
            pygame.draw.circle(s, mid, (bx, by), 6)
            pygame.draw.circle(s, sh, (bx-2, by-2), 3)
            l_w = int(math.sin(t * math.tau) * 2) if st == "walk" else 0
            for off in (-6, -2, 2, 6):
                pygame.draw.line(s, dark, (bx-5, by + off//3), (bx-12, by+2 + off//3 + l_w), 2)
                pygame.draw.line(s, dark, (bx+5, by + off//3), (bx+12, by+2 + off//3 - l_w), 2)
            if st == "attack":
                pygame.draw.line(s, (255, 245, 220), (bx+2, by-2), (bx+10, by-6), 2)

        elif "bandit" in et:
            pygame.draw.circle(s, dark, (bx, by-6), 6)
            pygame.draw.circle(s, mid, (bx, by-6), 5)
            pygame.draw.rect(s, sh, pygame.Rect(bx-4, by-8, 8, 3))
            _outline_rect(s, pygame.Rect(bx-4, by-1, 8, 11), mid)
            pygame.draw.rect(s, hi, pygame.Rect(bx-4, by-1, 8, 3))
            if st == "attack":
                pygame.draw.line(s, dark, (bx+4, by), (bx+13, by+2+int(8*t)), 3)
            else:
                pygame.draw.line(s, dark, (bx+4, by), (bx+10, by+6), 3)
            
            l_off = int(math.sin(t * math.tau) * 3) if st == "walk" else 0
            r_off = int(math.cos(t * math.tau) * 3) if st == "walk" else 0
            pygame.draw.line(s, mid, (bx-2, by+10), (bx-2+l_off, by+15), 2)
            pygame.draw.line(s, mid, (bx+2, by+10), (bx+2+r_off, by+15), 2)

        else:
            pygame.draw.circle(s, dark, (bx, by), 9)
            pygame.draw.circle(s, mid, (bx, by), 7)

        if st == "hurt":
            ov = pygame.Surface((32, 32), pygame.SRCALPHA)
            ov.fill((255, 60, 60, 55))
            s.blit(ov, (0, 0))
        elif st == "dead":
            ov = pygame.Surface((32, 32), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 110))
            s.blit(ov, (0, 0))
            pygame.draw.line(s, (10, 10, 12), (10, 26), (24, 24), 2)
            
        frames.append(s)
    return frames


def _building_frame(building_type: str, state: str) -> pygame.Surface:
    # Default to 1x1 (32px). Caller can request native tile-multiple sizes.
    s = _mk32()
    s.fill((0, 0, 0, 0))

    bt = (building_type or "building").lower()
    return _building_frame_sized(bt, state, size_px=32)


def _building_frame_sized(building_type: str, state: str, *, size_px: int) -> pygame.Surface:
    s = _mk(size_px)
    s.fill((0, 0, 0, 0))
    bt = (building_type or "building").lower()
    st = (state or "built").lower()

    # Palette anchors (keep consistent with style contract: top-left light, 1px outline)
    OUT = (20, 20, 25)
    stone = (120, 125, 135)
    wood = (140, 105, 70)
    roof_red = (150, 70, 55)
    roof_brown = (120, 75, 55)
    roof_blue = (70, 100, 170)
    cloth_yellow = (220, 175, 70)
    crop = (185, 160, 80)

    w, h = s.get_width(), s.get_height()
    pad = max(2, w // 24)

    def baseplate(col: tuple[int, int, int]):
        # small drop shadow and base plate to ground the building
        _draw_shadow(s, pygame.Rect(pad + 2, h - pad - 6, w - pad * 2, 6), alpha=50)
        pygame.draw.rect(s, OUT, pygame.Rect(pad, h - pad - 8, w - pad * 2, 8), 1)
        pygame.draw.rect(s, _shade(col, -15), pygame.Rect(pad + 1, h - pad - 7, w - pad * 2 - 2, 6), 0)

    def roof_poly(pts, col):
        _outline_poly(s, pts, col, outline=OUT)
        # highlight edge (top-left)
        pygame.draw.line(s, _shade(col, 35), pts[0], pts[1], 2)
        # 4x Detail: shingle / roof texture lines
        r_w = abs(pts[2][0] - pts[0][0])
        r_h = abs(pts[1][1] - pts[0][1])
        if r_w > 10 and r_h > 5:
            col_dark = _shade(col, -20)
            for yy in range(pts[1][1]+4, pts[0][1], 6):
                dx = int((pts[0][1] - yy) * (r_w/2.0) / float(r_h)) if r_h > 0 else 0
                cx = pts[1][0]
                pygame.draw.line(s, col_dark, (int(cx - dx + 2), yy), (int(cx + dx - 2), yy), 1)

    def wall_rect(r: pygame.Rect, col: tuple[int, int, int]):
        pygame.draw.rect(s, OUT, r, 0)
        pygame.draw.rect(s, col, r.inflate(-2, -2), 0)
        # 4x detail: brick/wood texture
        col_dark = _shade(col, -15)
        for yy in range(r.top + 4, r.bottom - 2, 8):
            pygame.draw.line(s, col_dark, (r.left + 2, yy), (r.right - 3, yy), 1)
        # subtle top highlight
        pygame.draw.line(s, _shade(col, 25), (r.left + 2, r.top + 2), (r.right - 3, r.top + 2), 2)
        pygame.draw.rect(s, OUT, r, 1)

    def draw_window(wx, wy, ww=6, wh=10, lit=False):
        pygame.draw.rect(s, OUT, pygame.Rect(wx, wy, ww, wh), 0)
        win_col = (200, 220, 255) if lit else (60, 80, 100)
        pygame.draw.rect(s, win_col, pygame.Rect(wx+1, wy+1, ww-2, wh-2), 0)
        pygame.draw.line(s, OUT, (wx+ww//2, wy), (wx+ww//2, wy+wh), 1)
        pygame.draw.line(s, OUT, (wx, wy+wh//2), (wx+ww, wy+wh//2), 1)

    # Tier-1: distinct silhouettes (others fall back to generic hut)
    if bt == "castle":
        baseplate(stone)
        # keep
        keep = pygame.Rect(pad * 3, pad * 4, w - pad * 6, h - pad * 10)
        wall_rect(keep, stone)
        draw_window(keep.centerx - 12, keep.centery - 8, 6, 8, lit=True)
        draw_window(keep.centerx + 6, keep.centery - 8, 6, 8, lit=True)
        # towers
        tw = max(10, w // 6)
        for tx in (pad * 2, w - pad * 2 - tw):
            t = pygame.Rect(tx, pad * 3, tw, h - pad * 11)
            wall_rect(t, _shade(stone, -5))
            roof_poly([(t.left, t.top), (t.centerx, t.top - tw // 2), (t.right, t.top)], _shade(roof_blue, -10))
        # gate
        gate = pygame.Rect(keep.centerx - w // 10, keep.bottom - w // 8, w // 5, w // 8)
        pygame.draw.rect(s, OUT, gate, 1)
        pygame.draw.rect(s, _shade(wood, -10), gate.inflate(-2, -2), 0)
        # flag
        pygame.draw.line(s, OUT, (keep.centerx, keep.top - 8), (keep.centerx, keep.top + 6), 2)
        pygame.draw.polygon(s, (90, 120, 255), [(keep.centerx, keep.top - 6), (keep.centerx + 10, keep.top - 3), (keep.centerx, keep.top)])
    elif bt == "marketplace":
        baseplate(wood)
        body = pygame.Rect(pad * 4, pad * 7, w - pad * 8, h - pad * 13)
        wall_rect(body, _shade(wood, -5))
        # awning
        aw = pygame.Rect(body.left - pad, body.top - pad * 3, body.w + pad * 2, pad * 4)
        pygame.draw.rect(s, OUT, aw, 0)
        pygame.draw.rect(s, cloth_yellow, aw.inflate(-2, -2), 0)
        # stripes
        for x in range(aw.left + 2, aw.right - 2, 6):
            pygame.draw.line(s, _shade(cloth_yellow, -35), (x, aw.top + 2), (x, aw.bottom - 3), 2)
        # crates
        pygame.draw.rect(s, OUT, pygame.Rect(body.left + 4, body.bottom - 10, 10, 8), 1)
        pygame.draw.rect(s, _shade(wood, -15), pygame.Rect(body.left + 5, body.bottom - 9, 8, 6), 0)
    elif bt == "inn":
        baseplate(wood)
        body = pygame.Rect(pad * 5, pad * 8, w - pad * 10, h - pad * 14)
        wall_rect(body, _shade(wood, -10))
        draw_window(body.left + 4, body.top + 4, 6, 8, lit=True)
        draw_window(body.right - 10, body.top + 4, 6, 8, lit=True)
        roof_poly([(body.left - pad, body.top), (body.centerx, body.top - pad * 4), (body.right + pad, body.top)], roof_red)
        # door + sign
        door = pygame.Rect(body.centerx - 5, body.bottom - 12, 10, 12)
        pygame.draw.rect(s, OUT, door, 1)
        pygame.draw.rect(s, _shade(wood, -25), door.inflate(-2, -2), 0)
        pygame.draw.circle(s, cloth_yellow, (body.right + pad * 2, body.top + pad * 3), pad * 2)
        pygame.draw.line(s, OUT, (body.right, body.top + pad * 2), (body.right + pad * 2, body.top + pad * 3), 2)
    elif bt == "blacksmith":
        baseplate(stone)
        body = pygame.Rect(pad * 5, pad * 8, w - pad * 10, h - pad * 14)
        wall_rect(body, _shade(stone, -10))
        roof_poly([(body.left - pad, body.top), (body.centerx, body.top - pad * 3), (body.right + pad, body.top)], roof_brown)
        # chimney + spark
        chim = pygame.Rect(body.right - pad * 3, body.top - pad * 6, pad * 3, pad * 6)
        wall_rect(chim, _shade(stone, -20))
        pygame.draw.circle(s, (255, 140, 60), (chim.centerx, chim.top - 2), 2)
        # anvil plate
        pygame.draw.rect(s, OUT, pygame.Rect(body.left + pad * 2, body.bottom - pad * 4, pad * 5, pad * 3), 1)
        pygame.draw.rect(s, (110, 110, 120), pygame.Rect(body.left + pad * 2 + 1, body.bottom - pad * 4 + 1, pad * 5 - 2, pad * 3 - 2), 0)
    elif bt == "guardhouse":
        baseplate(stone)
        tower = pygame.Rect(pad * 6, pad * 4, w - pad * 12, h - pad * 12)
        wall_rect(tower, _shade(stone, -8))
        roof_poly([(tower.left, tower.top), (tower.centerx, tower.top - pad * 5), (tower.right, tower.top)], roof_blue)
        # banner
        pygame.draw.rect(s, (90, 120, 255), pygame.Rect(tower.centerx - 2, tower.top + pad * 2, 4, 10))
        pygame.draw.rect(s, OUT, pygame.Rect(tower.centerx - 2, tower.top + pad * 2, 4, 10), 1)
    elif bt == "house":
        baseplate(wood)
        body = pygame.Rect(pad * 7, pad * 10, w - pad * 14, h - pad * 16)
        wall_rect(body, _shade(wood, -5))
        roof_poly([(body.left - pad, body.top), (body.centerx, body.top - pad * 3), (body.right + pad, body.top)], roof_brown)
        pygame.draw.rect(s, cloth_yellow, pygame.Rect(body.left + 6, body.top + 6, 6, 6))
        pygame.draw.rect(s, OUT, pygame.Rect(body.left + 6, body.top + 6, 6, 6), 1)
    elif bt == "farm":
        baseplate(crop)
        # field rows
        field = pygame.Rect(pad * 4, pad * 9, w - pad * 8, h - pad * 14)
        pygame.draw.rect(s, OUT, field, 1)
        pygame.draw.rect(s, crop, field.inflate(-2, -2), 0)
        for yy in range(field.top + 3, field.bottom - 3, 6):
            pygame.draw.line(s, _shade(crop, -25), (field.left + 2, yy), (field.right - 3, yy), 2)
        # barn corner
        barn = pygame.Rect(field.left + 4, field.top - pad * 5, pad * 10, pad * 8)
        wall_rect(barn, _shade(roof_red, -10))
        roof_poly([(barn.left - pad, barn.top), (barn.centerx, barn.top - pad * 2), (barn.right + pad, barn.top)], roof_red)
    elif bt == "food_stand":
        baseplate(wood)
        base_r = pygame.Rect(pad * 7, pad * 12, w - pad * 14, h - pad * 18)
        wall_rect(base_r, _shade(wood, -5))
        aw = pygame.Rect(base_r.left - pad * 2, base_r.top - pad * 4, base_r.w + pad * 4, pad * 4)
        pygame.draw.rect(s, OUT, aw, 0)
        pygame.draw.rect(s, cloth_yellow, aw.inflate(-2, -2), 0)
        pygame.draw.circle(s, (255, 80, 80), (aw.centerx, aw.centery), 3)
    elif bt == "goblin_camp":
        baseplate((100, 70, 40))
        tent = pygame.Rect(pad*4, pad*8, w - pad*8, h - pad*10)
        roof_poly([(tent.left, tent.bottom), (tent.centerx, tent.top), (tent.right, tent.bottom)], (130, 90, 50))
        pygame.draw.circle(s, (40, 40, 40), (tent.centerx, tent.bottom - 4), pad*2)
    elif bt == "wolf_den":
        baseplate((70, 70, 70))
        cave = pygame.Rect(pad*3, pad*6, w - pad*6, h - pad*8)
        pygame.draw.ellipse(s, (80, 80, 80), cave)
        pygame.draw.ellipse(s, OUT, cave, 2)
        pygame.draw.ellipse(s, (10, 10, 15), cave.inflate(-pad*4, -pad*4))
    elif bt == "skeleton_crypt":
        baseplate((50, 40, 60))
        crypt = pygame.Rect(pad*5, pad*7, w - pad*10, h - pad*10)
        wall_rect(crypt, (80, 70, 90))
        roof_poly([(crypt.left, crypt.top), (crypt.centerx, crypt.top - pad*3), (crypt.right, crypt.top)], (60, 50, 70))
        pygame.draw.rect(s, (20, 15, 25), pygame.Rect(crypt.centerx - pad, crypt.bottom - pad*4, pad*2, pad*4))
    elif bt == "spider_nest":
        baseplate((30, 30, 30))
        pygame.draw.circle(s, (40, 40, 45), (w//2, h//2 + pad), w//3)
        # web lines
        for r in (w//6, w//4, w//3):
            pygame.draw.circle(s, (200, 200, 210, 100), (w//2, h//2 + pad), r, 1)
        pygame.draw.line(s, (200, 200, 210, 100), (w//2, h//2 + pad - w//3), (w//2, h//2 + pad + w//3), 1)
        pygame.draw.line(s, (200, 200, 210, 100), (w//2 - w//3, h//2 + pad), (w//2 + w//3, h//2 + pad), 1)
    elif bt == "bandit_camp":
        baseplate((90, 60, 40))
        # two tents
        t1 = pygame.Rect(pad*4, pad*10, w//2 - pad*2, h//2 - pad*2)
        roof_poly([(t1.left, t1.bottom), (t1.centerx, t1.top), (t1.right, t1.bottom)], (160, 110, 70))
        t2 = pygame.Rect(w//2, pad*8, w//2 - pad*4, h//2)
        roof_poly([(t2.left, t2.bottom), (t2.centerx, t2.top), (t2.right, t2.bottom)], (140, 90, 60))
        # campfire
        pygame.draw.circle(s, (200, 100, 40), (w//2, h - pad*6), pad)
        pygame.draw.circle(s, (250, 180, 50), (w//2, h - pad*6), pad - 1)
    else:
        # Generic hut
        baseplate(wood)
        body = pygame.Rect(pad * 6, pad * 10, w - pad * 12, h - pad * 16)
        wall_rect(body, _shade(wood, -5))
        roof_poly([(body.left - pad, body.top), (body.centerx, body.top - pad * 3), (body.right + pad, body.top)], roof_brown)

    if st == "construction":
        _draw_construction_overlay(s)
    elif st == "damaged":
        _draw_damaged_overlay(s)

    return s


def _worker_frames(worker_type: str, state: str) -> list[pygame.Surface]:
    import math
    st = (state or "idle").lower()
    counts = {"idle": 6, "walk": 8, "work": 6, "collect": 6, "return": 8, "hurt": 4, "dead": 1}
    num_frames = counts.get(st, 1)

    frames = []
    wt = (worker_type or "peasant").lower()
    
    dark = (20, 20, 25)
    if wt == "peasant":
        base = (140, 110, 80)
    elif wt == "tax_collector":
        base = (160, 130, 100)
    else:
        base = (150, 120, 90)

    mid = base
    hi = _shade(base, 35)
    sh = _shade(base, -25)
    
    for i in range(num_frames):
        s = _mk32()
        s.fill((0, 0, 0, 0))
        t = i / float(num_frames) if num_frames > 1 else 0

        bob = int(max(0, math.sin(t * math.tau) * 2)) if st == "idle" else 0
        lean = int(math.sin(t * math.tau) * 1.5) if st in ("walk", "return") else 0
        if st == "hurt":
            lean = -2 if i % 2 == 0 else 2
        elif st in ("work", "collect"):
            lean = 2 if t > 0.5 else -1

        bx, by = 16 + lean, 18 + bob

        _outline_rect(s, pygame.Rect(bx-5, by-8, 10, 14), (60, 60, 70))
        _outline_rect(s, pygame.Rect(bx-4, by-12, 8, 6), (90, 90, 100))
        pygame.draw.rect(s, mid, pygame.Rect(bx-5, by-2, 10, 8))
        pygame.draw.rect(s, dark, pygame.Rect(bx-5, by-2, 10, 8), 1)

        if wt == "tax_collector":
            pygame.draw.rect(s, (80, 60, 40), pygame.Rect(bx-5, by-14, 10, 4))
            pygame.draw.rect(s, dark, pygame.Rect(bx-5, by-14, 10, 4), 1)
            pygame.draw.rect(s, _shade(base, -15), pygame.Rect(bx-7, by, 14, 6))
            pygame.draw.rect(s, dark, pygame.Rect(bx-7, by, 14, 6), 1)

        l_off = int(math.sin(t * math.tau) * 3) if st in ("walk", "return") else 0
        r_off = int(math.cos(t * math.tau) * 3) if st in ("walk", "return") else 0
        pygame.draw.rect(s, dark, pygame.Rect(bx-4+l_off, by+6, 2, 4))
        pygame.draw.rect(s, dark, pygame.Rect(bx+1+r_off, by+6, 2, 4))

        if st == "work" and wt == "peasant":
            pygame.draw.line(s, dark, (bx+4, by), (bx+12, by-4+int(8*t)), 2)
            pygame.draw.rect(s, (100, 80, 60), pygame.Rect(bx+10, by-5+int(8*t), 4, 3))
        elif st == "collect" and wt == "tax_collector":
            pygame.draw.circle(s, (255, 215, 0), (bx+6, by+2), 4)
            pygame.draw.circle(s, dark, (bx+6, by+2), 4, 1)
            pygame.draw.line(s, dark, (bx+4, by), (bx+8, by), 1)

        if st == "hurt":
            ov = pygame.Surface((32, 32), pygame.SRCALPHA)
            ov.fill((255, 60, 60, 55))
            s.blit(ov, (0, 0))
        elif st == "dead":
            ov = pygame.Surface((32, 32), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 110))
            s.blit(ov, (0, 0))
            pygame.draw.line(s, (10, 10, 12), (10, 26), (24, 24), 2)
            
        frames.append(s)
    return frames


def main() -> int:
    pygame.init()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    heroes = data["heroes"]["classes"]
    hero_states = _LEGACY_HERO_STATES
    enemies = data["enemies"]["types"]
    enemy_states = _LEGACY_ENEMY_STATES
    buildings = data["buildings"]["types"]
    building_states = _LEGACY_BUILDING_STATES
    workers = data.get("workers", {}).get("types", [])
    worker_states = _LEGACY_WORKER_STATES

    out = ASSETS / "sprites"

    for hc in heroes:
        for st in hero_states:
            for i, surf in enumerate(_hero_frames(hc, st)):
                _save(surf, out / "heroes" / hc / st / f"frame_{i:03d}.png")

    for et in enemies:
        for st in enemy_states:
            for i, surf in enumerate(_enemy_frames(et, st)):
                _save(surf, out / "enemies" / et / st / f"frame_{i:03d}.png")

    for bt in buildings:
        # Build native pixel sizes when possible (tile multiples); otherwise fall back to 32.
        sz = BUILDING_SIZES.get(bt, (1, 1))
        w_tiles, h_tiles = int(sz[0]), int(sz[1])
        size_px = int(max(1, w_tiles) * int(TILE_SIZE))
        for st in building_states:
            surf = _building_frame_sized(bt, st, size_px=size_px)
            _save(surf, out / "buildings" / bt / st / "frame_000.png")

    # Generate worker frames (generate all states for all types to satisfy validator)
    # Note: Some states are type-specific (peasant: work; tax_collector: collect/return),
    # but we generate all frames to pass strict validation.
    for wt in workers:
        for st in worker_states:
            for i, surf in enumerate(_worker_frames(wt, st)):
                _save(surf, out / "workers" / wt / st / f"frame_{i:03d}.png")

    print("[generate_cc0_placeholders] wrote sprites for:")
    print(f"  heroes: {len(heroes)} classes × {len(hero_states)} states (animated)")
    print(f"  enemies: {len(enemies)} types × {len(enemy_states)} states (animated)")
    print(f"  buildings: {len(buildings)} types × {len(building_states)} states")
    if workers:
        print(f"  workers: {len(workers)} types × {len(worker_states)} states (animated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



