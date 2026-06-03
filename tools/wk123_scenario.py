"""WK123 shared scenario spawn helpers (tools-only; edits no game code).

Promoted out of ``tmp/wk123/leak_probe.py`` so both the headless leak probe and the
LIVE FPS soak harness (``tools/wk123_fps_soak.py``) build the *same* heavy scenario:

  - ``spawn_heroes(engine, n)``      — n warriors out of a constructed WarriorGuild (>=24).
  - ``add_buildings(engine, target)``— pad the building count to ``target`` (~100) using the
                                       BuildingFactory guild/civic types PLUS a batch of
                                       constructed neutral Houses/Farms/FoodStands placed via
                                       the live ``NeutralBuildingSystem`` ramp's ``_find_spot``.
  - ``force_spawn_enemies(engine, n)``— n mixed enemies ring-spawned around the castle.
  - ``build_heavy_scenario(engine, ...)`` — convenience: spawn all three + return counts.
  - ``topup_enemies(engine)``        — re-pin alive enemies to ``config.MAX_ALIVE_ENEMIES``.

These mutate ``engine.heroes`` / ``engine.buildings`` / ``engine.enemies`` /
``engine.peasants`` directly and mark buildings constructed so the scenario is "heavy"
from frame 1 (we are measuring time-degradation, not the organic build-up ramp).

No import-time side effects; safe to import from a capture patch or a headless probe.
"""
from __future__ import annotations

import math

import config
from config import TILE_SIZE, MAX_ALIVE_ENEMIES

from game.entities import WarriorGuild
from game.entities.hero import Hero
from game.entities.enemy import Goblin, Wolf, Skeleton, SkeletonArcher, Spider, Bandit


# Mixed enemy roster (matches the leak-probe ring spawn).
_ENEMY_CLASSES = [Goblin, Wolf, Skeleton, SkeletonArcher, Spider, Bandit]

# BuildingFactory civic/guild types we pad with first (2 of each = 16 buildings).
_FACTORY_TYPES = [
    "ranger_guild", "rogue_guild", "wizard_guild", "inn", "marketplace",
    "blacksmith", "guardhouse", "trading_post",
]


def _find_castle(engine):
    return next(
        (b for b in engine.buildings if getattr(b, "building_type", "") == "castle"),
        None,
    )


def force_spawn_enemies(engine, n: int) -> int:
    """Drop ``n`` enemies in a ring around the castle (mixed types). Returns count added."""
    castle = _find_castle(engine)
    cx = float(getattr(castle, "center_x", 0.0))
    cy = float(getattr(castle, "center_y", 0.0))
    added = 0
    for i in range(int(n)):
        ang = i * 2.3999632  # golden-angle spiral so the ring fills evenly
        r = TILE_SIZE * (3.0 + (i % 50) * 0.3)
        ex = cx + r * math.cos(ang)
        ey = cy + r * math.sin(ang)
        cls = _ENEMY_CLASSES[i % len(_ENEMY_CLASSES)]
        engine.enemies.append(cls(ex, ey))
        added += 1
    return added


def topup_enemies(engine, cap: int | None = None) -> int:
    """Re-pin the alive-enemy count to ``cap`` (default config.MAX_ALIVE_ENEMIES).

    Call periodically (the harness does it every ~40 frames) so steady-state stays
    pinned at the cap and we measure time-accumulation, not entity attrition.
    Returns the number of fresh enemies spawned this call.
    """
    cap = int(cap if cap is not None else MAX_ALIVE_ENEMIES)
    alive = len([e for e in engine.enemies if getattr(e, "is_alive", False)])
    if alive < cap:
        return force_spawn_enemies(engine, cap - alive + 5)  # +5 overshoot keeps it pinned
    return 0


def spawn_heroes(engine, n: int) -> int:
    """Spawn ``n`` warriors out of a freshly-built (constructed) WarriorGuild. Returns count."""
    castle = _find_castle(engine)
    cx = int(getattr(castle, "grid_x", 0))
    cy = int(getattr(castle, "grid_y", 0))
    guild = WarriorGuild(cx - 5, cy + 3)
    guild.is_constructed = True
    guild.construction_started = True
    if hasattr(guild, "set_event_bus") and getattr(engine, "event_bus", None):
        guild.set_event_bus(engine.event_bus)
    engine.buildings.append(guild)
    for i in range(int(n)):
        h = Hero(
            guild.center_x + TILE_SIZE + (i % 5) * 12,
            guild.center_y + (i // 5) * 12,
            hero_class="warrior",
        )
        h.home_building = guild
        h.gold = 200
        engine.heroes.append(h)
    return int(n)


def _finalize_building(engine, b) -> None:
    """Mark a building fully constructed + alive + bus-wired (constructed-from-frame-1)."""
    b.is_constructed = True
    b.construction_started = True
    if hasattr(b, "hp") and hasattr(b, "max_hp"):
        try:
            b.hp = b.max_hp
        except Exception:
            pass
    if hasattr(b, "set_event_bus") and getattr(engine, "event_bus", None):
        try:
            b.set_event_bus(engine.event_bus)
        except Exception:
            pass


def _add_factory_buildings(engine) -> int:
    """Place 2 of each civic/guild type east of the castle via BuildingFactory. Returns count."""
    castle = _find_castle(engine)
    bx = int(getattr(castle, "grid_x", 0)) + int(castle.size[0]) + 2
    by = int(getattr(castle, "grid_y", 0))
    factory = getattr(engine, "building_factory", None)
    if factory is None:
        return 0
    placed = 0
    col = 0
    for t in _FACTORY_TYPES:
        for rep in range(2):
            try:
                b = factory.create(t, bx + col * 3, by + rep * 4)
            except Exception:
                b = None
            if b is None:
                continue
            _finalize_building(engine, b)
            engine.buildings.append(b)
            placed += 1
            col += 1
    return placed


def _add_neutral_buildings(engine, want: int) -> int:
    """Force-spawn up to ``want`` constructed neutral buildings (House/Farm/FoodStand).

    Uses the live ``NeutralBuildingSystem._find_spot`` ramp logic (real ring placement +
    overlap/gap rules) so the scenario mirrors the in-game neutral layout, but stamps each
    one constructed immediately instead of waiting on the slow builder-peasant ramp.
    Returns the number actually placed (may be < want if the rings fill up).
    """
    from game.entities.neutral_buildings import House, Farm, FoodStand

    castle = _find_castle(engine)
    nbs = getattr(engine, "neutral_building_system", None)
    if castle is None or nbs is None:
        return 0

    # Mirror the want_* ratios the ramp targets: house : food : farm ~ 6 : 2 : 3.
    plan = (
        [(House, (1, 1), 3, 12)] * 6
        + [(FoodStand, (1, 1), 3, 18)] * 2
        + [(Farm, (3, 2), 8, 18)] * 3
    )
    placed = 0
    idx = 0
    # Cycle the plan, widening max radius if rings fill, until we hit `want` or stall.
    stalls = 0
    while placed < want and stalls < 8:
        cls, size, min_r, max_r = plan[idx % len(plan)]
        idx += 1
        spot = nbs._find_spot(
            castle=castle,
            buildings=engine.buildings,
            size=size,
            min_r=min_r,
            max_r=max_r + (stalls * 6),  # widen the ring band when placement stalls
            shuffle_within_ring=True,
        )
        if spot is None:
            stalls += 1
            continue
        stalls = 0
        try:
            b = cls(*spot, is_constructed=True)
        except Exception:
            continue
        _finalize_building(engine, b)
        engine.buildings.append(b)
        placed += 1
    return placed


def add_buildings(engine, target: int = 100) -> int:
    """Pad ``engine.buildings`` toward ``target`` total (factory civics + neutral ramp).

    Returns the number of buildings *added* by this call (not the final total). The heavy
    scenario uses target=100; the building count is read off ``len(engine.buildings)``.
    """
    before = len(engine.buildings)
    _add_factory_buildings(engine)
    remaining = int(target) - len(engine.buildings)
    if remaining > 0:
        _add_neutral_buildings(engine, remaining)
    return len(engine.buildings) - before


def build_heavy_scenario(
    engine,
    *,
    heroes: int = 24,
    buildings_target: int = 100,
    enemies: int = 80,
) -> dict:
    """Spawn the full heavy scenario against ``engine`` and return a counts dict.

    heroes>=24 (WarriorGuild + warriors), ~``buildings_target`` buildings,
    ``enemies`` ring-spawned (over MAX_ALIVE_ENEMIES so steady-state stays pinned).
    """
    spawn_heroes(engine, heroes)
    add_buildings(engine, buildings_target)
    # Overshoot the cap a touch so the first top-up doesn't immediately fire.
    force_spawn_enemies(engine, max(enemies, MAX_ALIVE_ENEMIES))
    return scenario_counts(engine)


def scenario_counts(engine) -> dict:
    """Return the {heroes, buildings, enemies, enemies_alive} counts for logging."""
    return {
        "heroes": len(engine.heroes),
        "buildings": len(engine.buildings),
        "enemies": len(engine.enemies),
        "enemies_alive": len([e for e in engine.enemies if getattr(e, "is_alive", False)]),
    }
