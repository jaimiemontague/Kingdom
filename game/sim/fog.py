"""WK69 Round B-1: fog-of-war service extracted from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._update_fog_of_war`` method did. SimEngine keeps a one-line
delegating wrapper so callers/tests are unchanged.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original method used.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from game.world import Visibility
from config import (
    PLAYER_BUILDING_VISION_TILES,
    PLAYER_GUILD_EXTRA_VISION_TILES,
    PLAYER_GUILD_TYPES,
)

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine


def update_fog_of_war(sim: "SimEngine") -> None:
    """Update fog-of-war visibility around the castle, living heroes, neutral buildings, and guards.

    WK22 Agent-10 perf fix: cache the tile-grid positions of every revealer and
    skip the expensive ``world.update_visibility`` call when no vision source has
    moved by at least one full tile since the last rebuild.

    WK34: All constructed player-placed buildings reveal 3 tiles (building LoS).

    WK59 perf: throttle to every 3 ticks — heroes move ~0.08 tiles/tick at normal
    speed, so skipping 2 ticks adds at most 0.24-tile latency (invisible to player).
    """
    tick_counter = getattr(sim, "_fog_tick_counter", 0) + 1
    sim._fog_tick_counter = tick_counter
    if getattr(sim.world, 'fog_disabled', False):
        return
    if tick_counter % 3 != 0 and getattr(sim, "_fog_revealers_snapshot", None) is not None:
        return

    # Tunables (tile radius). Kept local to avoid cross-agent config conflicts.
    # WK17: per docs/vision_rules_fog_of_war.md (Agent 05 spec).
    CASTLE_VISION_TILES = 10
    HERO_VISION_TILES = 7
    GUARD_VISION_TILES = 6
    # WK43 Stage 1: Peasants (incl. BuilderPeasant) provide limited local LoS.
    PEASANT_VISION_TILES = 6
    NEUTRAL_VISION = {"house": 3, "farm": 5, "food_stand": 3}

    castle = next((b for b in sim.buildings if getattr(b, "building_type", None) == "castle"), None)
    revealers = []
    hero_revealers = []  # Track which revealers are heroes (for XP tracking)

    if castle is not None:
        revealers.append((castle.center_x, castle.center_y, CASTLE_VISION_TILES))

    for hero in sim.heroes:
        if getattr(hero, "is_alive", True):
            revealers.append((hero.x, hero.y, HERO_VISION_TILES))
            hero_revealers.append((hero, hero.x, hero.y, HERO_VISION_TILES))

    # WK43: Living peasants as vision sources.
    for peasant in sim.peasants:
        if not getattr(peasant, "is_alive", True):
            continue
        revealers.append((peasant.x, peasant.y, PEASANT_VISION_TILES))

    # WK17: Neutral buildings (house, farm, food_stand) as vision sources.
    for building in sim.buildings:
        btype = getattr(building, "building_type", None)
        if btype not in NEUTRAL_VISION:
            continue
        if getattr(building, "is_constructed", True) is not True:
            continue
        if getattr(building, "hp", 1) <= 0:
            continue
        radius = NEUTRAL_VISION[btype]
        revealers.append((building.center_x, building.center_y, radius))

    # WK34: All constructed player-placed buildings get a small LoS ring; see
    # `PLAYER_BUILDING_VISION_TILES` / `PLAYER_GUILD_EXTRA_VISION_TILES` in config.
    for building in sim.buildings:
        if not getattr(building, "is_constructed", False):
            continue
        if getattr(building, "hp", 1) <= 0:
            continue
        if getattr(building, "is_neutral", False):
            continue
        # Lairs are hostile world structures, not player vision sources.
        if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
            continue
        # POIs are world features, not player buildings — don't reveal fog.
        if getattr(building, "is_poi", False):
            continue
        raw_bt = getattr(building, "building_type", None)
        btype_name = str(getattr(raw_bt, "value", raw_bt) or "")
        if btype_name == "castle":
            continue
        r = int(PLAYER_BUILDING_VISION_TILES)
        if btype_name in PLAYER_GUILD_TYPES:
            r += int(PLAYER_GUILD_EXTRA_VISION_TILES)
        revealers.append((building.center_x, building.center_y, r))

    # WK17: Living guards as vision sources.
    for guard in sim.guards:
        if not getattr(guard, "is_alive", True):
            continue
        revealers.append((guard.x, guard.y, GUARD_VISION_TILES))

    if not revealers:
        return

    # ---- Dirty check: skip update if no revealer moved a full tile ----
    w2g = sim.world.world_to_grid
    grid_list = []
    for wx, wy, r in revealers:
        gxy = w2g(wx, wy)
        grid_list.append((gxy[0], gxy[1], r))
    grid_list.sort()
    grid_snapshot = tuple(grid_list)
    prev = getattr(sim, "_fog_revealers_snapshot", None)
    if prev is not None and prev == grid_snapshot:
        return
    sim._fog_revealers_snapshot = grid_snapshot
    sim._fog_revision = getattr(sim, "_fog_revision", 0) + 1

    # ---- Perform the full visibility update ----
    newly_revealed = sim.world.update_visibility(revealers, return_new_reveals=True)

    # WK6: Award XP to Rangers for newly revealed tiles
    if newly_revealed:
        for hero, hx, hy, radius in hero_revealers:
            if hero.hero_class == "ranger":
                hero_grid_x, hero_grid_y = sim.world.world_to_grid(hx, hy)
                radius_sq = radius * radius

                for grid_x, grid_y in newly_revealed:
                    dx = grid_x - hero_grid_x
                    dy = grid_y - hero_grid_y
                    if (dx * dx + dy * dy) <= radius_sq:
                        if (grid_x, grid_y) not in hero._revealed_tiles:
                            hero._revealed_tiles.add((grid_x, grid_y))
                            hero.grant_tile_exploration_xp(1)
                            hero.increment_career_stat("tiles_revealed", 1)

    # WK49: Known places — runs on every FoW rebuild (not only frontier reveals). POIs uncovered
    # by castle/neutral/other revealers use the visibility-frame encounter path inside discovery.
    if hero_revealers:
        from game.sim.hero_profile import discover_known_buildings_after_fog
        from game.sim.timebase import now_ms as fog_profile_now_ms

        w = sim.world

        def _tile_currently_visible(gx: int, gy: int) -> bool:
            if gx < 0 or gy < 0 or gx >= w.width or gy >= w.height:
                return False
            return w.visibility[gy][gx] == Visibility.VISIBLE

        hero_grids: list[tuple[object, int, int, int]] = []
        for hero, hx, hy, radius in hero_revealers:
            gx, gy = sim.world.world_to_grid(hx, hy)
            hero_grids.append((hero, gx, gy, radius))
        discover_known_buildings_after_fog(
            buildings=sim.buildings,
            heroes_world_vision=hero_grids,
            newly_revealed=newly_revealed or (),
            now_ms=int(fog_profile_now_ms()),
            tile_currently_visible=_tile_currently_visible,
        )
