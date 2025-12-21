from __future__ import annotations

"""
Tiny procedural UI icons (pixel-crisp) for readability overlays.

Why procedural?
- avoids blocking on art
- keeps icons consistent with the pixel grid
- allows later replacement with real PNG assets without changing UI contracts
"""

from dataclasses import dataclass
from typing import Dict, Tuple

import pygame


Color = Tuple[int, int, int]


@dataclass(frozen=True)
class IconTheme:
    # Keep near-white, not pure white, for a softer pixel look.
    ink: Color = (245, 245, 245)
    outline: Color = (20, 20, 25)

    # Tier accents (low/med/high)
    low: Color = (120, 180, 255)   # cool blue
    med: Color = (255, 215, 80)    # gold
    high: Color = (255, 120, 80)   # orange/red

    # Background plate for readability over fog/terrain
    plate: Tuple[int, int, int, int] = (0, 0, 0, 140)


_type_cache: Dict[tuple[str, int], pygame.Surface] = {}
_tier_cache: Dict[tuple[str, int], pygame.Surface] = {}
_badge_cache: Dict[tuple[str, str, int], pygame.Surface] = {}


def _mk(size: int) -> pygame.Surface:
    s = max(8, int(size))
    return pygame.Surface((s, s), pygame.SRCALPHA)


def _draw_outline_box(surf: pygame.Surface, theme: IconTheme, pad: int = 0) -> None:
    s = surf.get_width()
    r = pygame.Rect(int(pad), int(pad), int(s - 2 * pad), int(s - 2 * pad))
    pygame.draw.rect(surf, theme.outline, r, 1)


def get_attractiveness_icon(tier: str, *, size: int = 16, theme: IconTheme = IconTheme()) -> pygame.Surface:
    """
    Returns a small tier icon:
    - low: single chevron
    - med: double chevron
    - high: triple chevron
    """
    t = (tier or "low").lower()
    if t not in ("low", "med", "high"):
        t = "low"
    key = (t, int(size))
    cached = _tier_cache.get(key)
    if cached is not None:
        return cached

    surf = _mk(size)
    surf.fill((0, 0, 0, 0))

    accent = theme.low if t == "low" else (theme.med if t == "med" else theme.high)

    s = surf.get_width()
    cx = s // 2
    cy = s // 2
    count = 1 if t == "low" else (2 if t == "med" else 3)

    # Draw stacked upward chevrons (readable at 16px)
    for i in range(count):
        y = cy + (count - 1 - i) * 3
        pts = [(cx - 4, y + 2), (cx, y - 2), (cx + 4, y + 2)]
        pygame.draw.lines(surf, theme.outline, False, pts, 3)  # thick outline underlay
        pygame.draw.lines(surf, accent, False, pts, 1)

    _tier_cache[key] = surf
    return surf


def get_bounty_type_icon(bounty_type: str, *, size: int = 16, theme: IconTheme = IconTheme()) -> pygame.Surface:
    """
    Returns a small type icon (symbol-only, no text).

    Types currently used by the sim:
    - explore: compass/diamond
    - attack_lair: crossed swords (simplified)
    - defend_building: shield
    - hunt_enemy_type: target reticle
    """
    bt = (bounty_type or "explore").lower()
    key = (bt, int(size))
    cached = _type_cache.get(key)
    if cached is not None:
        return cached

    surf = _mk(size)
    surf.fill((0, 0, 0, 0))

    s = surf.get_width()

    def px(x: int, y: int, w: int, h: int, col: Color):
        pygame.draw.rect(surf, col, pygame.Rect(int(x), int(y), int(w), int(h)))

    # Common outline-first style (draw outline, then ink fill)
    if bt == "attack_lair":
        # Crossed swords (very simplified)
        pygame.draw.line(surf, theme.outline, (3, s - 4), (s - 4, 3), 3)
        pygame.draw.line(surf, theme.outline, (3, 3), (s - 4, s - 4), 3)
        pygame.draw.line(surf, theme.ink, (3, s - 4), (s - 4, 3), 1)
        pygame.draw.line(surf, theme.ink, (3, 3), (s - 4, s - 4), 1)
        # tiny pommels
        px(2, s - 5, 3, 3, theme.ink)
        px(s - 5, 2, 3, 3, theme.ink)
    elif bt == "defend_building":
        # Shield
        pts = [(s // 2, 2), (s - 3, 5), (s - 4, s - 5), (s // 2, s - 2), (3, s - 5), (2, 5)]
        pygame.draw.polygon(surf, theme.outline, pts, 0)
        inner = [(s // 2, 3), (s - 4, 6), (s - 5, s - 6), (s // 2, s - 3), (4, s - 6), (3, 6)]
        pygame.draw.polygon(surf, theme.ink, inner, 0)
        pygame.draw.line(surf, theme.outline, (s // 2, 4), (s // 2, s - 4), 1)
    elif bt == "hunt_enemy_type":
        # Target reticle
        pygame.draw.circle(surf, theme.outline, (s // 2, s // 2), s // 2 - 2, 2)
        pygame.draw.circle(surf, theme.ink, (s // 2, s // 2), s // 2 - 3, 1)
        pygame.draw.line(surf, theme.outline, (s // 2, 2), (s // 2, s - 3), 1)
        pygame.draw.line(surf, theme.outline, (2, s // 2), (s - 3, s // 2), 1)
        pygame.draw.rect(surf, theme.ink, pygame.Rect(s // 2 - 1, s // 2 - 1, 2, 2))
    else:
        # explore: diamond/compass
        pts = [(s // 2, 2), (s - 3, s // 2), (s // 2, s - 3), (3, s // 2)]
        pygame.draw.polygon(surf, theme.outline, pts, 0)
        inner = [(s // 2, 3), (s - 4, s // 2), (s // 2, s - 4), (4, s // 2)]
        pygame.draw.polygon(surf, theme.ink, inner, 0)
        pygame.draw.circle(surf, theme.outline, (s // 2, s // 2), 1, 0)

    _type_cache[key] = surf
    return surf


def get_bounty_badge(
    bounty_type: str,
    attractiveness_tier: str,
    *,
    size: int = 20,
    theme: IconTheme = IconTheme(),
) -> pygame.Surface:
    """
    Composite badge for overlays: a readable plate + type icon + tier chevrons.
    """
    bt = (bounty_type or "explore").lower()
    tier = (attractiveness_tier or "low").lower()
    if tier not in ("low", "med", "high"):
        tier = "low"
    key = (bt, tier, int(size))
    cached = _badge_cache.get(key)
    if cached is not None:
        return cached

    surf = _mk(size)
    s = surf.get_width()
    # Plate
    plate = pygame.Surface((s, s), pygame.SRCALPHA)
    plate.fill(theme.plate)
    surf.blit(plate, (0, 0))
    _draw_outline_box(surf, theme, pad=0)

    # Icons
    icon = get_bounty_type_icon(bt, size=max(12, s - 6), theme=theme)
    tier_icon = get_attractiveness_icon(tier, size=max(10, s // 2), theme=theme)

    surf.blit(icon, (2, 2))
    surf.blit(tier_icon, (s - tier_icon.get_width() - 1, s - tier_icon.get_height() - 1))

    _badge_cache[key] = surf
    return surf


