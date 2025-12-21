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


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _save(surf: pygame.Surface, path: Path) -> None:
    _ensure_dir(path.parent)
    pygame.image.save(surf, str(path))


def _mk32() -> pygame.Surface:
    return pygame.Surface((32, 32), pygame.SRCALPHA)


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

    # silhouette
    if et == "wolf":
        _outline_rect(s, pygame.Rect(8, 14, 18, 10), base)
        pygame.draw.rect(s, base, pygame.Rect(22, 12, 6, 4))
    elif et == "skeleton":
        _outline_rect(s, pygame.Rect(12, 10, 8, 16), base)
        pygame.draw.rect(s, (30, 30, 35), pygame.Rect(14, 14, 2, 2))
        pygame.draw.rect(s, (30, 30, 35), pygame.Rect(16, 14, 2, 2))
    elif et == "spider":
        pygame.draw.circle(s, (20, 20, 25), (16, 18), 8)
        pygame.draw.circle(s, base, (16, 18), 6)
        for off in (-6, -2, 2, 6):
            pygame.draw.line(s, (20, 20, 25), (10, 18 + off // 3), (4, 20 + off // 3), 2)
            pygame.draw.line(s, (20, 20, 25), (22, 18 + off // 3), (28, 20 + off // 3), 2)
    else:
        pygame.draw.circle(s, (20, 20, 25), (16, 18), 9)
        pygame.draw.circle(s, base, (16, 18), 7)

    st = (state or "idle").lower()
    if st == "attack":
        pygame.draw.line(s, (255, 245, 220), (20, 14), (30, 10), 2)
    elif st == "hurt":
        overlay = pygame.Surface((32, 32), pygame.SRCALPHA)
        overlay.fill((255, 60, 60, 55))
        s.blit(overlay, (0, 0))
    elif st == "dead":
        overlay = pygame.Surface((32, 32), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        s.blit(overlay, (0, 0))
    return s


def _building_frame(building_type: str, state: str) -> pygame.Surface:
    s = _mk32()
    s.fill((0, 0, 0, 0))

    bt = (building_type or "building").lower()
    base = {
        "castle": (150, 120, 90),
        "palace": (170, 140, 90),
        "marketplace": (220, 170, 60),
        "blacksmith": (110, 110, 110),
        "inn": (160, 90, 50),
        "farm": (200, 170, 90),
        "house": (120, 100, 80),
        "food_stand": (210, 120, 60),
        "wizard_tower": (140, 60, 220),
    }.get(bt, (130, 130, 130))

    # simple building icon: base + roof stripe
    _outline_rect(s, pygame.Rect(6, 10, 20, 18), base)
    roof = (max(0, base[0] - 20), max(0, base[1] - 20), max(0, base[2] - 20))
    pygame.draw.rect(s, roof, pygame.Rect(6, 10, 20, 5))

    st = (state or "built").lower()
    if st == "construction":
        for x in range(2, 34, 6):
            pygame.draw.line(s, (140, 120, 80), (x, 28), (x - 10, 10), 2)
        overlay = pygame.Surface((32, 32), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 35))
        s.blit(overlay, (0, 0))
    elif st == "damaged":
        pygame.draw.line(s, (30, 30, 35), (10, 14), (18, 24), 1)
        pygame.draw.line(s, (30, 30, 35), (18, 24), (14, 28), 1)
        pygame.draw.circle(s, (80, 80, 80, 130), (20, 12), 4, 0)

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
        for st in building_states:
            surf = _building_frame(bt, st)
            _save(surf, out / "buildings" / bt / st / "frame_000.png")

    print("[generate_cc0_placeholders] wrote sprites for:")
    print(f"  heroes: {len(heroes)} classes × {len(hero_states)} states")
    print(f"  enemies: {len(enemies)} types × {len(enemy_states)} states")
    print(f"  buildings: {len(buildings)} types × {len(building_states)} states")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


