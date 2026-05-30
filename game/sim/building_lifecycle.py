"""WK69 Round B-1 (W2): building-lifecycle (destroyed-building cleanup) service extracted
from SimEngine (behavior-preserving move).

Takes the live SimEngine as ``sim`` and reads/writes its state exactly as the
former ``SimEngine._cleanup_destroyed_buildings`` method did, including the same
HUD messages + BUILDING_DESTROYED events and the same entity-reference clearing.
SimEngine keeps a one-line delegating wrapper so callers/tests are unchanged.

This is behavior-sensitive (destruction mutates authoritative sim state) so the
body is preserved verbatim with ``self.`` rewritten to ``sim.`` — the WK67 digest
guards it.

This module must NOT import ``game.sim_engine`` at runtime (no import cycle): it
takes ``sim`` as a duck-typed parameter and only imports the same leaf helpers
the original method used. (The CleanupManager retirement is deferred to WK70 —
do not touch it here.)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE
from game.events import GameEventType

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.sim_engine
    from game.sim_engine import SimEngine


def cleanup_destroyed_buildings(sim: "SimEngine") -> None:
    """WK61-FIX: Remove buildings at 0 HP and clear stale references.

    The full CleanupManager on the presentation layer handles rubble + HUD messages
    and is wired via GameEngine. This lightweight sim-side pass ensures the
    authoritative buildings list never keeps dead buildings across ticks.
    """
    destroyed = [
        b for b in sim.buildings
        if b.hp <= 0 and getattr(b, "building_type", None) != "castle"
    ]
    if not destroyed:
        return

    from game.entities.rubble import RubbleRecord, make_rubble_id
    from game.sim.timebase import now_ms as _now_ms_fn

    _now = int(_now_ms_fn())
    destruction_events: list[dict] = []

    for building in destroyed:
        bx = float(getattr(building, "center_x", getattr(building, "x", 0.0)))
        by = float(getattr(building, "center_y", getattr(building, "y", 0.0)))
        btype = str(getattr(building, "building_type", "unknown"))

        # Eject occupants
        for occ in list(getattr(building, "occupants", [])):
            if hasattr(occ, "pop_out_of_building"):
                occ.pop_out_of_building()

        # Remove from primary lists
        if building in sim.buildings:
            sim.buildings.remove(building)
        if getattr(building, "is_lair", False) and building in getattr(sim.lair_system, "lairs", []):
            sim.lair_system.lairs.remove(building)

        # Clear entity references
        for hero in sim.heroes:
            if getattr(hero, "target", None) is building:
                hero.target = None
            if getattr(hero, "home_building", None) is building:
                hero.home_building = None
        for enemy in sim.enemies:
            if getattr(enemy, "target", None) is building:
                enemy.target = None
        for peasant in sim.peasants:
            if getattr(peasant, "target_building", None) is building:
                peasant.target_building = None
        if sim.tax_collector and getattr(sim.tax_collector, "target_guild", None) is building:
            sim.tax_collector.target_guild = None
        for guard in sim.guards:
            if getattr(guard, "target", None) is building:
                guard.target = None
            if getattr(guard, "home_building", None) is building:
                guard.home_building = None
        for bounty in getattr(sim.bounty_system, "bounties", []):
            if getattr(bounty, "target", None) is building:
                bounty.target = None

        # Selection: WK63 — moved to presentation-layer SelectionState.
        # on_entity_destroyed() is called by CleanupManager or GameEngine event handler.

        # Rubble record
        rubble_size = getattr(building, "size", (1, 1))
        rubble = RubbleRecord(
            record_id=make_rubble_id(),
            center_x=float(bx),
            center_y=float(by),
            grid_x=int(getattr(building, "grid_x", 0)),
            grid_y=int(getattr(building, "grid_y", 0)),
            width_tiles=int(rubble_size[0]),
            height_tiles=int(rubble_size[1]),
            building_type=btype,
            created_ms=_now,
        )
        sim.rubble_records.append(rubble)

        building_w = getattr(building, "width", 0) or (rubble_size[0] * TILE_SIZE)
        building_h = getattr(building, "height", 0) or (rubble_size[1] * TILE_SIZE)
        destruction_events.append({
            "type": GameEventType.BUILDING_DESTROYED.value,
            "x": float(bx),
            "y": float(by),
            "building_type": btype,
            "w": int(building_w),
            "h": int(building_h),
        })

        # HUD message via event bus
        building_name = btype.replace("_", " ").title()
        sim._emit_hud_message(f"{building_name} destroyed", (220, 20, 60))

    if destruction_events:
        sim.event_bus.emit_batch(destruction_events)
