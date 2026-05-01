"""
WK50 Phase 2B: deterministic resolution of direct-prompt movement targets.

LLM output may name a known place id or a compass direction only; this module
turns those hints into world (x, y) using hero profile data and map bounds.
"""

from __future__ import annotations

from typing import Any

from config import TILE_SIZE

from game.sim.hero_profile import build_hero_profile_snapshot
from game.sim.timebase import now_ms as sim_now_ms


_COMPASS_ORDER = (
    "northeast",
    "northwest",
    "southeast",
    "southwest",
    "north",
    "south",
    "east",
    "west",
)

_DIR_VEC = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
    "northeast": (1, -1),
    "northwest": (-1, -1),
    "southeast": (1, 1),
    "southwest": (-1, 1),
}

# Default explore stride in tiles (deterministic; not RNG).
_EXPLORE_TILES_DEFAULT = 10


def parse_compass_direction(*text_parts: str) -> str | None:
    """Return canonical direction key or None."""
    blob = " ".join(p for p in text_parts if p).lower()
    if not blob:
        return None
    for word in _COMPASS_ORDER:
        if word in blob:
            return word
    return None


def resolve_known_place_world_xy(
    hero: Any,
    game_state: dict | None,
    place_id: str,
    *,
    now_ms: int | None = None,
) -> tuple[float, float] | None:
    """
    Match ``place_id`` against the hero's KnownPlaceSnapshot list (sim-authoritative).
    """
    pid = str(place_id or "").strip().lower()
    if not pid:
        return None
    t = int(now_ms) if now_ms is not None else int(sim_now_ms())
    snap = build_hero_profile_snapshot(hero, game_state, now_ms=t)
    for p in snap.known_places:
        k = str(p.place_id or "").strip().lower()
        if not k:
            continue
        if k == pid or (len(pid) >= 4 and pid in k):
            wx, wy = p.world_pos
            return (float(wx), float(wy))
    return None


def resolve_explore_direction_target(
    hero: Any,
    game_state: dict,
    direction: str,
    *,
    tiles_ahead: int = _EXPLORE_TILES_DEFAULT,
) -> tuple[float, float] | None:
    """
    Pick a tile ``tiles_ahead`` steps in ``direction`` from the hero, clamped to the map.
    """
    d = str(direction or "").strip().lower()
    vec = _DIR_VEC.get(d)
    if vec is None:
        return None
    world = game_state.get("world")
    if world is None:
        return None
    w = int(getattr(world, "width", 0) or 0)
    h = int(getattr(world, "height", 0) or 0)
    if w <= 0 or h <= 0:
        return None

    gx0 = int(float(getattr(hero, "x", 0.0)) // TILE_SIZE)
    gy0 = int(float(getattr(hero, "y", 0.0)) // TILE_SIZE)
    dx, dy = vec
    ngx = gx0 + dx * int(tiles_ahead)
    ngy = gy0 + dy * int(tiles_ahead)
    ngx = max(0, min(w - 1, ngx))
    ngy = max(0, min(h - 1, ngy))
    cx = ngx * TILE_SIZE + TILE_SIZE / 2.0
    cy = ngy * TILE_SIZE + TILE_SIZE / 2.0
    return (cx, cy)


def resolve_move_destination(
    hero: Any,
    game_state: dict,
    decision: dict[str, Any],
) -> tuple[float, float] | None:
    """
    Prefer ``target_id`` → hero known-place world position; else string-based building
    resolution (same semantics as ``ai.behaviors.llm_bridge._resolve_move_target``).
    """
    target_id = str(decision.get("target_id") or "").strip()
    if target_id:
        xy = resolve_known_place_world_xy(hero, game_state, target_id)
        if xy is not None:
            return xy

    from ai.behaviors.llm_bridge import _resolve_move_target

    label = str(decision.get("target") or "").strip()
    if label:
        return _resolve_move_target(label, game_state, hero)
    return None


def strip_untrusted_spatial_fields(decision: dict[str, Any]) -> dict[str, Any]:
    """Remove coordinate-like keys the LLM must never author directly."""
    out = dict(decision)
    for k in (
        "world_x",
        "world_y",
        "tile_x",
        "tile_y",
        "grid_x",
        "grid_y",
        "dest_x",
        "dest_y",
        "coordinates",
    ):
        out.pop(k, None)
    return out
