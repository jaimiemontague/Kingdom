"""
Entity/building cleanup coordination for GameEngine.
"""
from typing import TYPE_CHECKING

from config import COLOR_RED, TILE_SIZE
from game.events import GameEventType

if TYPE_CHECKING:
    from game.engine import GameEngine


class CleanupManager:
    """Centralize building destruction cleanup rules."""

    def __init__(self, engine: "GameEngine"):
        self.engine = engine

    def cleanup_destroyed_buildings(self, emit_messages: bool = True):
        """
        Remove buildings at hp <= 0 (except castle) and clear all references.

        This method is idempotent (safe to call multiple times per tick).
        """
        engine = self.engine

        # Collect destroyed buildings first (avoid modifying list during iteration)
        destroyed = [b for b in engine.buildings if b.hp <= 0 and getattr(b, "building_type", None) != "castle"]

        if not destroyed:
            return

        # Collect building destruction events for debris spawning
        destruction_events = []

        for building in destroyed:
            # WK18-BUG-002: Eject occupants to adjacent tile before removing building
            occupants = getattr(building, "occupants", [])
            for hero in list(occupants):
                if hasattr(hero, "pop_out_of_building"):
                    hero.pop_out_of_building()

            # Capture building position/type for debris before removal
            building_x = getattr(building, "center_x", getattr(building, "x", 0.0))
            building_y = getattr(building, "center_y", getattr(building, "y", 0.0))
            building_type = getattr(building, "building_type", "unknown")

            # Emit auto-demolish message (red, warning) unless suppressed
            if emit_messages:
                building_name = building_type.replace("_", " ").title()
                engine.hud.add_message(f"{building_name} destroyed", COLOR_RED)

            # 1. Remove from primary lists
            if building in engine.buildings:
                engine.buildings.remove(building)
            if getattr(building, "is_lair", False) and building in getattr(engine.lair_system, "lairs", []):
                engine.lair_system.lairs.remove(building)

            # 2. Clear selection
            if engine.selected_building is building:
                engine.selected_building = None
                engine.building_panel.deselect()

            # 3. Clear entity target references
            for hero in engine.heroes:
                if getattr(hero, "target", None) is building:
                    hero.target = None
                # Hero target dict with bounty_ref
                target = getattr(hero, "target", None)
                if isinstance(target, dict) and target.get("type") == "bounty":
                    bounty_ref = target.get("bounty_ref")
                    if bounty_ref and getattr(bounty_ref, "target", None) is building:
                        hero.target = None

            for enemy in engine.enemies:
                if getattr(enemy, "target", None) is building:
                    enemy.target = None

            for peasant in engine.peasants:
                if getattr(peasant, "target_building", None) is building:
                    peasant.target_building = None

            if engine.tax_collector:
                if getattr(engine.tax_collector, "target_guild", None) is building:
                    engine.tax_collector.target_guild = None

            for guard in engine.guards:
                if getattr(guard, "target", None) is building:
                    guard.target = None

            # 4. Clear home_building references
            for hero in engine.heroes:
                if getattr(hero, "home_building", None) is building:
                    hero.home_building = None

            for guard in engine.guards:
                if getattr(guard, "home_building", None) is building:
                    guard.home_building = None

            # 5. Clear bounty target references
            for bounty in getattr(engine.bounty_system, "bounties", []):
                if getattr(bounty, "target", None) is building:
                    bounty.target = None

            # Emit building destruction event for debris spawning.
            building_w = getattr(building, "width", 0) or (getattr(building, "size", (1, 1))[0] * TILE_SIZE)
            building_h = getattr(building, "height", 0) or (getattr(building, "size", (1, 1))[1] * TILE_SIZE)
            destruction_events.append({
                "type": GameEventType.BUILDING_DESTROYED.value,
                "x": float(building_x),
                "y": float(building_y),
                "building_type": building_type,
                "w": int(building_w),  # Footprint width in pixels
                "h": int(building_h),  # Footprint height in pixels
            })

        # EventBus subscribers (Audio/VFX) handle downstream processing.
        if destruction_events and hasattr(engine, "event_bus"):
            engine.event_bus.emit_batch(destruction_events)
