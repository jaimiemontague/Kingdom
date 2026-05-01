"""
Optional dense starting layout for faster manual / LLM testing.

Activated via ``GameEngine(..., playtest_start=True)`` or ``--playtest-start`` on ``main.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE

if TYPE_CHECKING:
    pass


def apply_playtest_quick_start(engine) -> None:
    """
    After normal ``setup_initial_state()`` (castle + lairs): add guilds, market, inn,
    potions researched, two hero squads, seeded known-place memory, extra player gold.
    """
    from game.entities import Hero, Inn, Marketplace, RangerGuild, WarriorGuild
    from game.sim.timebase import now_ms as sim_now_ms

    castle = next((b for b in engine.buildings if getattr(b, "building_type", None) == "castle"), None)
    if castle is None:
        return

    cx = int(getattr(castle, "grid_x", 0))
    cy = int(getattr(castle, "grid_y", 0))

    warrior_guild = WarriorGuild(cx - 6, cy + 4)
    ranger_guild = RangerGuild(cx - 6, cy + 8)
    market = Marketplace(cx + 6, cy + 4)
    market.potions_researched = True
    inn = Inn(cx + 6, cy + 10)

    new_buildings = (warrior_guild, ranger_guild, market, inn)
    eb = getattr(engine, "event_bus", None)
    for b in new_buildings:
        if hasattr(b, "is_constructed"):
            b.is_constructed = True
        if hasattr(b, "construction_started"):
            b.construction_started = True
        engine.buildings.append(b)
        if hasattr(b, "set_event_bus") and eb is not None:
            b.set_event_bus(eb)
        w, h = getattr(b, "size", (2, 2))
        try:
            engine.sim.remove_trees_in_footprint(int(b.grid_x), int(b.grid_y), int(w), int(h))
        except Exception:
            pass

    try:
        engine.economy.player_gold += 2500
    except Exception:
        pass

    now_ms = int(sim_now_ms())
    heroes: list = []
    for _ in range(5):
        h = Hero(warrior_guild.center_x + TILE_SIZE, warrior_guild.center_y, hero_class="warrior")
        h.home_building = warrior_guild
        h.gold = max(int(getattr(h, "gold", 0)), 200)
        heroes.append(h)
    for _ in range(5):
        h = Hero(ranger_guild.center_x + TILE_SIZE, ranger_guild.center_y, hero_class="ranger")
        h.home_building = ranger_guild
        h.gold = max(int(getattr(h, "gold", 0)), 200)
        heroes.append(h)

    for h in heroes:
        engine.heroes.append(h)
        for b in new_buildings:
            slug = str(getattr(getattr(b, "building_type", None), "value", b.building_type) or "")
            gx = int(b.grid_x)
            gy = int(b.grid_y)
            dn = slug.replace("_", " ").strip().title() or "Place"
            try:
                h.remember_known_place(
                    place_type=slug,
                    display_name=dn,
                    tile=(gx, gy),
                    world_pos=(float(b.center_x), float(b.center_y)),
                    sim_time_ms=now_ms,
                    building_type=slug,
                    grid_x=gx,
                    grid_y=gy,
                )
            except Exception:
                pass

    try:
        engine._update_fog_of_war()
    except Exception:
        pass

    try:
        hud = getattr(engine, "hud", None)
        if hud is not None and hasattr(hud, "add_message"):
            hud.add_message("Playtest start: guilds, market (potions), inn, 10 heroes.", (120, 200, 255))
    except Exception:
        pass
