"""POI awareness and personality-driven exploration behavior (WK55).

Provides helpers to:
1. Build nearby-POI context for LLM decisions (discovered + seen-fog unknowns).
2. Score POIs against hero personality for behavior-level preference.
3. Optionally steer idle heroes toward personality-relevant POIs.
"""

from __future__ import annotations

import math
from typing import Any

from config import TILE_SIZE
from game.world import Visibility


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Radius limits (tiles) for POI awareness buckets.
DISCOVERED_POI_RADIUS_TILES = 30
UNDISCOVERED_SEEN_POI_RADIUS_TILES = 20

# Maximum POIs included in context (to keep LLM token cost low).
MAX_CONTEXT_POIS = 6

# Personality -> interaction_type preference weights.
# Higher = more attractive.  Missing keys default to 1.0.
PERSONALITY_POI_WEIGHTS: dict[str, dict[str, float]] = {
    "brave and aggressive": {
        "combat": 2.0,
        "boss": 2.5,
        "dungeon": 1.8,
        "shrine": 0.4,
        "loot": 1.0,
        "knowledge": 0.5,
        "npc": 0.6,
    },
    "cautious and strategic": {
        "shrine": 2.0,
        "knowledge": 1.8,
        "npc": 1.5,
        "loot": 1.2,
        "combat": 0.4,
        "boss": 0.1,
        "dungeon": 0.5,
    },
    "greedy but cowardly": {
        "loot": 2.5,
        "npc": 1.3,  # potential trades
        "shrine": 0.8,
        "knowledge": 0.6,
        "combat": 0.3,
        "boss": 0.1,
        "dungeon": 0.7,
    },
    "balanced and reliable": {
        "shrine": 1.3,
        "loot": 1.3,
        "knowledge": 1.2,
        "npc": 1.2,
        "combat": 1.0,
        "dungeon": 1.0,
        "boss": 0.7,
    },
}

# Difficulty avoidance threshold: cautious heroes avoid POIs above this tier delta.
_CAUTIOUS_DIFFICULTY_AVOIDANCE = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compass_direction(dx: float, dy: float) -> str:
    """Return 8-point compass label from (dx, dy) offset."""
    if abs(dx) < 1e-3 and abs(dy) < 1e-3:
        return "here"
    angle = math.atan2(dy, dx)  # radians; east=0, south=pi/2
    # Quantize into 8 sectors.
    sector = round(angle / (math.pi / 4)) % 8
    labels = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")
    return labels[sector]


def _poi_center_world(poi: Any) -> tuple[float, float]:
    """World-pixel center of a POI (using grid_x/grid_y + definition size)."""
    poi_def = getattr(poi, "poi_def", None)
    size = getattr(poi_def, "size", (1, 1)) if poi_def else (1, 1)
    cx = (getattr(poi, "grid_x", 0) + size[0] / 2) * TILE_SIZE
    cy = (getattr(poi, "grid_y", 0) + size[1] / 2) * TILE_SIZE
    return (cx, cy)


def _hero_world_pos(hero: Any) -> tuple[float, float]:
    """Hero position in world pixels."""
    hx = getattr(hero, "world_x", getattr(hero, "x", 0))
    hy = getattr(hero, "world_y", getattr(hero, "y", 0))
    return (float(hx), float(hy))


def _is_tile_in_seen_fog(world: Any, gx: int, gy: int) -> bool:
    """True if the tile at (gx, gy) has been SEEN (grey fog) but is not currently VISIBLE."""
    if world is None or not hasattr(world, "visibility"):
        return False
    if gy < 0 or gy >= world.height or gx < 0 or gx >= world.width:
        return False
    vis = world.visibility[gy][gx]
    return vis == Visibility.SEEN


# ---------------------------------------------------------------------------
# Context builder: get_nearby_pois_for_hero
# ---------------------------------------------------------------------------

def get_nearby_pois_for_hero(hero: Any, context: dict) -> list[dict]:
    """Build a list of nearby POI context dicts for LLM consumption.

    Returns up to MAX_CONTEXT_POIS entries, sorted by distance.
    Includes:
      - Discovered POIs within DISCOVERED_POI_RADIUS_TILES
      - Undiscovered POIs whose tile is in SEEN fog within UNDISCOVERED_SEEN_POI_RADIUS_TILES

    WK67 Move 5: ``context`` is the LLM-context mapping built by
    :func:`ai.behaviors.view_compat.view_to_legacy_context` (a fresh dict carrying
    the read-only ``WorldView`` under ``world`` and the POI tuple under ``pois``).
    The AI no longer reaches a live sim service here.
    """
    pois = _get_pois_from_context(context)
    world = context.get("world")
    hx, hy = _hero_world_pos(hero)

    results: list[dict] = []

    for poi in pois:
        poi_def = getattr(poi, "poi_def", None)
        if poi_def is None:
            continue

        pcx, pcy = _poi_center_world(poi)
        dist_tiles = math.hypot(hx - pcx, hy - pcy) / TILE_SIZE
        dx = pcx - hx
        dy = pcy - hy
        direction = _compass_direction(dx, dy)

        discovered = getattr(poi, "is_discovered", False)

        if discovered:
            # Discovered POI: full info, within 30 tiles
            if dist_tiles > DISCOVERED_POI_RADIUS_TILES:
                continue
            entry = {
                "name": getattr(poi_def, "display_name", "Unknown POI"),
                "type": getattr(poi_def, "interaction_type", "unknown"),
                "distance_tiles": round(dist_tiles, 1),
                "direction": direction,
                "difficulty": getattr(poi_def, "difficulty_tier", 0),
                "description": getattr(poi_def, "description", ""),
                "depleted": getattr(poi, "is_depleted", False),
                "previously_visited": getattr(poi, "is_interacted", False),
            }
            results.append(entry)
        else:
            # Undiscovered POI: only include if tile is in SEEN fog
            if dist_tiles > UNDISCOVERED_SEEN_POI_RADIUS_TILES:
                continue
            poi_gx = int(getattr(poi, "grid_x", 0))
            poi_gy = int(getattr(poi, "grid_y", 0))
            if not _is_tile_in_seen_fog(world, poi_gx, poi_gy):
                continue
            entry = {
                "name": "Unknown Structure",
                "type": "unknown",
                "distance_tiles": round(dist_tiles, 1),
                "direction": direction,
                "description": "A shadowy shape in the distance. Could be worth investigating.",
            }
            results.append(entry)

    # Sort by distance, take top N.
    results.sort(key=lambda e: e["distance_tiles"])
    return results[:MAX_CONTEXT_POIS]


# ---------------------------------------------------------------------------
# Personality scoring
# ---------------------------------------------------------------------------

def score_poi_for_personality(
    hero: Any,
    poi: Any,
    *,
    dist_tiles: float | None = None,
) -> float:
    """Score a POI based on hero personality + distance.

    Returns a float score (higher = more attractive to this hero).
    Used by exploration idle behavior to pick a destination.
    """
    poi_def = getattr(poi, "poi_def", None)
    if poi_def is None:
        return 0.0

    personality = str(getattr(hero, "personality", "balanced and reliable"))
    interaction_type = str(getattr(poi_def, "interaction_type", "unknown"))
    difficulty = int(getattr(poi_def, "difficulty_tier", 1))
    hero_level = int(getattr(hero, "level", 1))

    # Base personality weight.
    weights = PERSONALITY_POI_WEIGHTS.get(personality, PERSONALITY_POI_WEIGHTS["balanced and reliable"])
    base_weight = weights.get(interaction_type, 1.0)

    # Distance penalty (closer = better).
    if dist_tiles is None:
        hx, hy = _hero_world_pos(hero)
        pcx, pcy = _poi_center_world(poi)
        dist_tiles = math.hypot(hx - pcx, hy - pcy) / TILE_SIZE

    # Avoid division by zero.
    dist_factor = 1.0 / (1.0 + dist_tiles * 0.08)

    # Difficulty vs level penalty for cautious heroes.
    difficulty_factor = 1.0
    if "cautious" in personality.lower():
        diff_delta = difficulty - hero_level
        if diff_delta >= _CAUTIOUS_DIFFICULTY_AVOIDANCE:
            difficulty_factor = 0.2
    elif "cowardly" in personality.lower():
        diff_delta = difficulty - hero_level
        if diff_delta >= 1:
            difficulty_factor = 0.3

    # WK57 Wave 5D: Dungeon-specific scoring adjustments
    dungeon_factor = 1.0
    if interaction_type == "dungeon":
        # Bold/aggressive heroes are attracted to caves
        if "aggressive" in personality.lower() or "brave" in personality.lower():
            dungeon_factor = 1.5
        # Cautious heroes avoid unless strong enough
        elif "cautious" in personality.lower():
            if hero_level < difficulty * 2:
                dungeon_factor = 0.2  # strongly discourage
            else:
                dungeon_factor = 0.8
        # Don't enter caves when hurt (< 70% max HP)
        hero_hp = getattr(hero, "hp", 0)
        hero_max_hp = getattr(hero, "max_hp", 1)
        if hero_max_hp > 0 and hero_hp < hero_max_hp * 0.7:
            dungeon_factor *= 0.1

    # Depleted POI penalty.
    depleted_factor = 0.1 if getattr(poi, "is_depleted", False) else 1.0

    # Already interacted penalty (reduce but don't eliminate for persistent POIs).
    interacted_factor = 0.4 if getattr(poi, "is_interacted", False) else 1.0

    score = base_weight * dist_factor * difficulty_factor * depleted_factor * interacted_factor * dungeon_factor
    return score


# ---------------------------------------------------------------------------
# Behavior: maybe_visit_poi (for idle exploration)
# ---------------------------------------------------------------------------

def maybe_visit_poi(ai: Any, hero: Any, view: Any) -> bool:
    """If a personality-relevant POI is nearby, set hero target toward it.

    Returns True if a POI target was set (hero should move toward it),
    False if no suitable POI was found.

    Called from exploration idle behavior as an alternative to random wander.

    WK67 Move 5: reads ``view.pois`` (the AiGameView POI tuple) directly.
    """
    from game.entities.hero import HeroState
    from ai.behaviors.view_compat import as_ai_view

    view = as_ai_view(view)
    pois = list(view.pois or [])
    if not pois:
        return False

    hx, hy = _hero_world_pos(hero)

    best_poi = None
    best_score = 0.15  # Minimum threshold to bother

    for poi in pois:
        if not getattr(poi, "is_discovered", False):
            continue
        if getattr(poi, "is_depleted", False):
            continue
        poi_def = getattr(poi, "poi_def", None)
        if poi_def is None:
            continue

        pcx, pcy = _poi_center_world(poi)
        dist_tiles = math.hypot(hx - pcx, hy - pcy) / TILE_SIZE

        # Only consider POIs within reasonable travel distance.
        if dist_tiles > DISCOVERED_POI_RADIUS_TILES:
            continue

        score = score_poi_for_personality(hero, poi, dist_tiles=dist_tiles)
        if score > best_score:
            best_score = score
            best_poi = poi

    if best_poi is None:
        return False

    # Set movement target toward the POI.
    best_poi_def = getattr(best_poi, "poi_def", None)
    best_interaction_type = getattr(best_poi_def, "interaction_type", "")

    # WK57 Wave 5D: For dungeon POIs, target the entrance tile directly
    # (actual entry happens via poi_interaction when hero arrives within range)
    if best_interaction_type == "dungeon":
        target_x = getattr(best_poi, "grid_x", 0) * TILE_SIZE + TILE_SIZE // 2
        target_y = getattr(best_poi, "grid_y", 0) * TILE_SIZE + TILE_SIZE // 2
    else:
        target_x, target_y = _poi_center_world(best_poi)

    hero.set_target_position(target_x, target_y)
    hero.target = {"type": "visit_poi", "poi": best_poi}
    hero.state = HeroState.MOVING
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_pois_from_context(context: dict) -> list:
    """Extract the POI list from the LLM-context mapping.

    WK67 Move 5: the context dict built by
    :func:`ai.behaviors.view_compat.view_to_legacy_context` always carries the
    AiGameView POI tuple under ``pois`` (the same tuple the AI previously reached
    through the live ``sim.pois`` fallback). The live-``sim`` fallback is gone —
    the AI no longer holds a sim service.
    """
    pois = context.get("pois")
    if pois:
        return list(pois)
    return []
