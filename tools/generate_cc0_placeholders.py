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


def _hero_frame(hero_class: str, state: str) -> pygame.Surface:
    s = _mk32()
    s.fill((0, 0, 0, 0))

    # Class accents (match existing placeholder color language)
    accents = {
        "warrior": (70, 120, 255),
        "ranger": (70, 200, 120),
        "rogue": (180, 180, 200),
        "wizard": (170, 90, 230),
    }
    acc = accents.get(hero_class, (220, 220, 220))

    # Body + head (simple silhouette)
    _outline_rect(s, pygame.Rect(11, 10, 10, 14), (60, 60, 70))
    _outline_rect(s, pygame.Rect(12, 6, 8, 6), (90, 90, 100))
    # Accent cloak/trim
    pygame.draw.rect(s, acc, pygame.Rect(9, 14, 14, 10))
    pygame.draw.rect(s, (20, 20, 25), pygame.Rect(9, 14, 14, 10), 1)

    # State hint pixels
    st = (state or "idle").lower()
    if st == "attack":
        pygame.draw.line(s, (255, 235, 160), (20, 12), (30, 6), 2)
    elif st == "hurt":
        overlay = pygame.Surface((32, 32), pygame.SRCALPHA)
        overlay.fill((255, 60, 60, 55))
        s.blit(overlay, (0, 0))
    elif st == "inside":
        pygame.draw.circle(s, (245, 245, 245, 230), (16, 8), 6, 2)
        pygame.draw.circle(s, (255, 215, 80, 210), (18, 6), 2, 0)
    elif st == "walk":
        pygame.draw.rect(s, (240, 240, 240), pygame.Rect(10, 26, 4, 2))
        pygame.draw.rect(s, (240, 240, 240), pygame.Rect(18, 26, 4, 2))
    return s


def _enemy_frame(enemy_type: str, state: str) -> pygame.Surface:
    s = _mk32()
    s.fill((0, 0, 0, 0))
    et = (enemy_type or "goblin").lower()

    base = {
        "goblin": (90, 170, 90),
        "wolf": (160, 160, 160),
        "skeleton": (220, 220, 240),
        "spider": (50, 50, 55),
        "bandit": (140, 100, 65),
    }.get(et, (150, 150, 150))

    # Stronger silhouette per enemy type (still simple, but readable)
    dark = (20, 20, 25)
    hi = _shade(base, 35)
    mid = base
    sh = _shade(base, -25)

    if et == "goblin":
        # big head + small body + dagger
        pygame.draw.circle(s, dark, (15, 13), 7)
        pygame.draw.circle(s, mid, (15, 13), 6)
        pygame.draw.circle(s, sh, (13, 11), 3)
        _outline_rect(s, pygame.Rect(12, 18, 8, 10), mid)
        pygame.draw.rect(s, hi, pygame.Rect(12, 18, 8, 3))
        # eyes
        pygame.draw.rect(s, (250, 250, 250), pygame.Rect(13, 12, 2, 2))
        pygame.draw.rect(s, (250, 250, 250), pygame.Rect(16, 12, 2, 2))
        # dagger arm (state affects)
        arm_y = 18
        if (state or "").lower() == "attack":
            pygame.draw.line(s, dark, (19, arm_y), (28, 14), 2)
            pygame.draw.line(s, (220, 220, 230), (26, 13), (30, 11), 2)
        else:
            pygame.draw.line(s, dark, (19, arm_y), (25, 20), 2)
            pygame.draw.line(s, (220, 220, 230), (24, 19), (27, 18), 2)
    elif et == "wolf":
        # body + head + tail
        _outline_rect(s, pygame.Rect(7, 16, 18, 8), mid)
        pygame.draw.rect(s, hi, pygame.Rect(7, 16, 18, 2))
        _outline_rect(s, pygame.Rect(22, 14, 7, 6), mid)
        pygame.draw.rect(s, sh, pygame.Rect(22, 18, 7, 2))
        # tail
        pygame.draw.line(s, dark, (7, 18), (3, 16), 2)
        # legs (walk offset)
        step = 1 if (state or "").lower() == "walk" else 0
        pygame.draw.rect(s, dark, pygame.Rect(10, 24, 2, 2 + step))
        pygame.draw.rect(s, dark, pygame.Rect(16, 24, 2, 2 - step))
        if (state or "").lower() == "attack":
            # pounce cue
            pygame.draw.line(s, (255, 245, 220), (24, 14), (31, 11), 2)
    elif et == "skeleton":
        # skull + ribs + limbs
        pygame.draw.circle(s, dark, (16, 11), 6)
        pygame.draw.circle(s, mid, (16, 11), 5)
        pygame.draw.rect(s, dark, pygame.Rect(14, 10, 2, 2))
        pygame.draw.rect(s, dark, pygame.Rect(17, 10, 2, 2))
        _outline_rect(s, pygame.Rect(12, 16, 8, 10), mid)
        for i in range(3):
            pygame.draw.line(s, sh, (13, 18 + i * 2), (19, 18 + i * 2), 1)
        # weapon cue
        if (state or "").lower() == "attack":
            pygame.draw.line(s, dark, (19, 18), (29, 14), 2)
            pygame.draw.line(s, (200, 200, 210), (27, 13), (31, 11), 2)
    elif et == "spider":
        pygame.draw.circle(s, dark, (16, 18), 8)
        pygame.draw.circle(s, mid, (16, 18), 6)
        pygame.draw.circle(s, sh, (14, 16), 3)
        for off in (-6, -2, 2, 6):
            pygame.draw.line(s, dark, (11, 18 + off // 3), (4, 20 + off // 3), 2)
            pygame.draw.line(s, dark, (21, 18 + off // 3), (28, 20 + off // 3), 2)
        if (state or "").lower() == "attack":
            pygame.draw.line(s, (255, 245, 220), (18, 16), (26, 12), 2)
    elif et == "bandit":
        # hooded humanoid with club
        pygame.draw.circle(s, dark, (16, 12), 6)
        pygame.draw.circle(s, mid, (16, 12), 5)
        pygame.draw.rect(s, sh, pygame.Rect(12, 10, 8, 3))
        _outline_rect(s, pygame.Rect(12, 17, 8, 11), mid)
        pygame.draw.rect(s, hi, pygame.Rect(12, 17, 8, 3))
        if (state or "").lower() == "attack":
            pygame.draw.line(s, dark, (20, 18), (29, 20), 3)
        else:
            pygame.draw.line(s, dark, (20, 18), (26, 24), 3)
    else:
        pygame.draw.circle(s, dark, (16, 18), 9)
        pygame.draw.circle(s, mid, (16, 18), 7)

    st = (state or "idle").lower()
    if st == "attack":
        # attack is expressed in the per-type silhouette above where possible
        pass
    elif st == "hurt":
        overlay = pygame.Surface((32, 32), pygame.SRCALPHA)
        overlay.fill((255, 60, 60, 55))
        s.blit(overlay, (0, 0))
    elif st == "dead":
        overlay = pygame.Surface((32, 32), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        s.blit(overlay, (0, 0))
        # collapse hint
        pygame.draw.line(s, (10, 10, 12), (10, 26), (24, 24), 2)
    return s


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

    def wall_rect(r: pygame.Rect, col: tuple[int, int, int]):
        pygame.draw.rect(s, OUT, r, 0)
        pygame.draw.rect(s, col, r.inflate(-2, -2), 0)
        # subtle top highlight
        pygame.draw.line(s, _shade(col, 25), (r.left + 2, r.top + 2), (r.right - 3, r.top + 2), 2)
        pygame.draw.rect(s, OUT, r, 1)

    # Tier-1: distinct silhouettes (others fall back to generic hut)
    if bt == "castle":
        baseplate(stone)
        # keep
        keep = pygame.Rect(pad * 3, pad * 4, w - pad * 6, h - pad * 10)
        wall_rect(keep, stone)
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


def main() -> int:
    pygame.init()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    heroes = data["heroes"]["classes"]
    hero_states = data["heroes"]["states"]
    enemies = data["enemies"]["types"]
    enemy_states = data["enemies"]["states"]
    buildings = data["buildings"]["types"]
    building_states = data["buildings"]["states"]

    out = ASSETS / "sprites"

    for hc in heroes:
        for st in hero_states:
            surf = _hero_frame(hc, st)
            _save(surf, out / "heroes" / hc / st / "frame_000.png")

    for et in enemies:
        for st in enemy_states:
            surf = _enemy_frame(et, st)
            _save(surf, out / "enemies" / et / st / "frame_000.png")

    for bt in buildings:
        # Build native pixel sizes when possible (tile multiples); otherwise fall back to 32.
        sz = BUILDING_SIZES.get(bt, (1, 1))
        w_tiles, h_tiles = int(sz[0]), int(sz[1])
        size_px = int(max(1, w_tiles) * int(TILE_SIZE))
        for st in building_states:
            surf = _building_frame_sized(bt, st, size_px=size_px)
            _save(surf, out / "buildings" / bt / st / "frame_000.png")

    print("[generate_cc0_placeholders] wrote sprites for:")
    print(f"  heroes: {len(heroes)} classes × {len(hero_states)} states")
    print(f"  enemies: {len(enemies)} types × {len(enemy_states)} states")
    print(f"  buildings: {len(buildings)} types × {len(building_states)} states")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



