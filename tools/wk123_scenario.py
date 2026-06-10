"""WK123 shared scenario spawn helpers (tools-only; edits no game code).

Promoted out of ``tmp/wk123/leak_probe.py`` so both the headless leak probe and the
LIVE FPS soak harness (``tools/wk123_fps_soak.py``) build the *same* heavy scenario:

  - ``spawn_heroes(engine, n)``      — n warriors out of a constructed WarriorGuild (>=24).
  - ``add_buildings(engine, target)``— pad the ACTIVE (rendered, non-POI/non-lair) building
                                       count to ``target`` (default 24 = the Sovereign spec)
                                       using BuildingFactory guild/civic types PLUS constructed
                                       neutral Houses/Farms/FoodStands placed via the live
                                       ``NeutralBuildingSystem`` ramp's ``_find_spot``. (Earlier
                                       revs force-padded to ~100, slamming all prefab
                                       instantiation into one frame = the rend=122ms spike.)
  - ``force_spawn_enemies(engine, n)``— n mixed enemies ring-spawned around the castle.
  - ``build_heavy_scenario(engine, ...)`` — convenience: spawn all three + return counts.
  - ``topup_enemies(engine)``        — re-pin alive enemies to ``config.MAX_ALIVE_ENEMIES``.
  - ``topup_heroes(engine, target)`` — re-pin ALIVE heroes to ``target`` (default = the
                                       scenario's spawn count) so the swarm can't decay the
                                       measured hero count to 0 over the run.

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


def _prewarm_building_prefabs() -> int:
    """Warm Panda's prefab piece-model cache so force-spawned buildings don't cold-parse.

    Delegates to the SAME ``game.graphics.ursina_prefabs.prewarm_building_prefab_models``
    that the real Ursina startup runs (ursina_app.py). The live game calls it once at
    boot so neutral buildings that spawn during play take the cheap cached-copy path; the
    soak scenario slams its buildings in *after* that startup prewarm, but calling it again
    here is idempotent (the loader cache is already populated → near-zero cost) and makes
    the scenario self-contained for the headless probe (where the live startup prewarm may
    have skipped, e.g. no GL context). Each model load is try/except'd inside the helper, so
    a headless / no-GL run never raises. Returns the warmed count (0 if the helper is
    unavailable or fails — e.g. ursina not importable in a pure-sim context).
    """
    try:
        from game.graphics.ursina_prefabs import prewarm_building_prefab_models
    except Exception:
        return 0
    try:
        return int(prewarm_building_prefab_models())
    except Exception:
        return 0


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


# Stash the scenario WarriorGuild + the heroes target on the engine so periodic
# ``topup_heroes`` re-spawns into the SAME guild (no new building per top-up) and knows
# the count to hold even when the caller doesn't thread ``target`` through explicitly.
_GUILD_ATTR = "_wk123_warrior_guild"
_HERO_TARGET_ATTR = "_wk123_hero_target"


def _get_or_make_guild(engine):
    """Return the scenario's WarriorGuild, constructing+stashing one on first use."""
    guild = getattr(engine, _GUILD_ATTR, None)
    if guild is not None and guild in engine.buildings:
        return guild
    castle = _find_castle(engine)
    cx = int(getattr(castle, "grid_x", 0))
    cy = int(getattr(castle, "grid_y", 0))
    guild = WarriorGuild(cx - 5, cy + 3)
    guild.is_constructed = True
    guild.construction_started = True
    if hasattr(guild, "set_event_bus") and getattr(engine, "event_bus", None):
        guild.set_event_bus(engine.event_bus)
    engine.buildings.append(guild)
    try:
        setattr(engine, _GUILD_ATTR, guild)
    except Exception:
        pass
    return guild


def _spawn_warriors(engine, guild, n: int, start_index: int = 0) -> int:
    """Append ``n`` warriors anchored to ``guild`` (laid out on a 5-wide grid). Returns count."""
    for i in range(int(n)):
        j = start_index + i
        h = Hero(
            guild.center_x + TILE_SIZE + (j % 5) * 12,
            guild.center_y + (j // 5) * 12,
            hero_class="warrior",
        )
        h.home_building = guild
        h.gold = 200
        engine.heroes.append(h)
    return int(n)


def spawn_heroes(engine, n: int) -> int:
    """Spawn ``n`` warriors out of a freshly-built (constructed) WarriorGuild. Returns count.

    Records ``n`` as the scenario's hero target on the engine so periodic ``topup_heroes``
    holds that count for the whole run, and stashes the guild so top-ups re-spawn into the
    SAME building (no new WarriorGuild per top-up = building count stays at the spec target).
    """
    guild = _get_or_make_guild(engine)
    try:
        setattr(engine, _HERO_TARGET_ATTR, int(n))
    except Exception:
        pass
    return _spawn_warriors(engine, guild, int(n))


def topup_heroes(engine, target: int | None = None) -> int:
    """Re-pin the ALIVE-hero count to ``target`` (default = the scenario's spawn count).

    Mirrors ``topup_enemies``: the swarm kills heroes over the run, so without this the
    measured hero count decays to 0 (the bug this fixes). Call periodically (the harness
    does it every ~40 frames, same cadence as ``topup_enemies``) so steady-state holds
    ~``target`` ALIVE heroes and we measure time-accumulation, not hero attrition.

    Re-spawns warriors into the SAME stashed WarriorGuild via the ``spawn_heroes`` path
    (``_spawn_warriors``) so no extra guild building is added per top-up. Counts ALIVE
    heroes (``is_alive``/hp>0), not raw ``len(engine.heroes)``. ``target`` defaults to the
    value recorded by ``spawn_heroes``/``build_heavy_scenario`` (24 if never set).
    Returns the number of fresh warriors spawned this call.
    """
    if target is None:
        target = int(getattr(engine, _HERO_TARGET_ATTR, 24))
    target = int(target)
    alive = len([h for h in engine.heroes if getattr(h, "is_alive", False)])
    if alive < target:
        guild = _get_or_make_guild(engine)
        return _spawn_warriors(
            engine, guild, target - alive, start_index=len(engine.heroes)
        )
    return 0


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


def _is_poi(b) -> bool:
    """True for POIs (gravestones / caves / treasure caches / etc.) — passive scenery.

    POIs are counted in ``len(engine.buildings)`` but render as HIDDEN until a hero
    discovers them (see ursina_building_sync.py undiscovered-POI early-``continue``), so
    they are NOT part of the heavy 3D-prefab render cost the soak is measuring. We exclude
    them when computing how many *active* (rendered) buildings the target should reach.
    """
    return bool(getattr(b, "is_poi", False)) or str(
        getattr(getattr(b, "building_type", ""), "value", getattr(b, "building_type", ""))
    ).startswith("poi_")


def _active_building_count(engine) -> int:
    """Count constructed, non-POI, non-lair buildings (the ones rendered as 3D prefabs)."""
    n = 0
    for b in engine.buildings:
        if _is_poi(b):
            continue
        if bool(getattr(b, "is_lair", False) or getattr(b, "has_stash_gold", False)):
            continue
        n += 1
    return n


def _add_factory_buildings(engine, max_add: int | None = None) -> int:
    """Place up to ``max_add`` civic/guild buildings (2 of each type) east of the castle.

    ``max_add=None`` keeps the legacy behavior (2 of every _FACTORY_TYPES = up to 16).
    Pass a smaller cap to honor a low ``buildings_target`` so the scenario does not slam
    16 extra civics on top of an already-populated starter world.
    """
    castle = _find_castle(engine)
    bx = int(getattr(castle, "grid_x", 0)) + int(castle.size[0]) + 2
    by = int(getattr(castle, "grid_y", 0))
    factory = getattr(engine, "building_factory", None)
    if factory is None:
        return 0
    cap = (2 * len(_FACTORY_TYPES)) if max_add is None else max(0, int(max_add))
    placed = 0
    col = 0
    for t in _FACTORY_TYPES:
        for rep in range(2):
            if placed >= cap:
                return placed
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


def add_buildings(engine, target: int = 24) -> int:
    """Pad the ACTIVE (rendered, non-POI/non-lair) building count toward ``target``.

    Returns the number of buildings *added* by this call (not the final total). The heavy
    scenario uses target=24 (the Sovereign's "20+ buildings" spec).

    Representativeness — the starter world already ships the castle, 2-3 guilds, a few
    neutrals, ~5 lairs and ~29 POIs, so ``len(engine.buildings)`` starts near ~43. POIs and
    lairs render as HIDDEN/scenery (undiscovered POIs early-``continue`` in the building
    render-sync; lairs gate on fog), so the *heavy 3D-prefab* render cost tracks the ACTIVE
    count, not the raw list length. We therefore pad the ACTIVE count toward ``target`` (a
    handful of civics + neutrals) instead of unconditionally slamming 16 civics + a neutral
    ramp on top of a full world (which is what produced the old B=100 / rend=122ms run).

    Every padded building is finalized CONSTRUCTED (``_finalize_building`` /
    ``is_constructed=True``) so it renders as its FINAL prefab from frame 1 — the staged
    resolver short-circuits on ``is_constructed`` (no per-frame plot/build_20/build_50
    re-resolution, no per-frame entity destroy+reinstantiate cold-parse).
    """
    before = len(engine.buildings)
    need = int(target) - _active_building_count(engine)
    if need <= 0:
        return 0
    # Prefer variety: fill up to half the deficit with civic/guild factory types, the
    # remainder with neutral houses/farms/stands via the live ring-placement logic.
    factory_add = min(need, 2 * len(_FACTORY_TYPES), max(1, need // 2 + need % 2))
    _add_factory_buildings(engine, max_add=factory_add)
    remaining = int(target) - _active_building_count(engine)
    if remaining > 0:
        _add_neutral_buildings(engine, remaining)
    return len(engine.buildings) - before


def build_heavy_scenario(
    engine,
    *,
    heroes: int = 24,
    buildings_target: int = 24,
    enemies: int = 80,
) -> dict:
    """Spawn the full heavy scenario against ``engine`` and return a counts dict.

    Defaults mirror the Sovereign's spec — 24 heroes / 24 buildings / 80 enemies
    ("20+ heroes, 20+ buildings, 75+ enemies"). An earlier revision force-padded
    ``buildings_target`` to 100 (5x spec); that slammed ~100 prefab containers (each
    with several piece child-Entities) into existence in a single frame, which is
    what produced the 122ms ``ursina_renderer`` spikes at B=99-100. Real long-play
    reaches ~20-30 buildings *organically* (one neutral every ~6s), so 24 is both
    spec-accurate AND representative of a 15-min kingdom's steady state.

    REPRESENTATIVENESS (so the scenario == "a kingdom that has played 15 min", not
    "N buildings slammed in this frame"):
      * Every force-spawned building is stamped fully CONSTRUCTED (``is_constructed``
        + ``construction_progress`` == 1.0 via the live property), so the render path
        resolves the stable FINAL prefab once (``_resolve_construction_staged_prefab``
        short-circuits on ``is_constructed`` → no per-frame plot/build_20/build_50
        re-resolution and no per-frame entity destroy+reinstantiate cold-parse).
      * We prewarm the building-prefab piece-model cache up front (same helper the
        real startup uses), so the first ``Entity(model=...)`` for each piece takes
        Panda's cheap cached-copy path instead of cold-parsing the .glb on the render
        thread. The first-frame instantiation cost remains (it exists in real play too,
        just amortized over minutes) but the per-piece GLB parse is moved off it.

    heroes>=24 (WarriorGuild + warriors), ~``buildings_target`` buildings,
    ``enemies`` ring-spawned (over MAX_ALIVE_ENEMIES so steady-state stays pinned).
    """
    # Warm the prefab piece-model cache BEFORE instantiating buildings so their first
    # Entity(model=...) hits Panda's cached-copy path (mirrors real startup prewarm).
    _prewarm_building_prefabs()
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
