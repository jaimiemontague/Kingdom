"""
WK56 Wave 1: POI Interaction System.

Resolves interactions when a hero arrives at a discovered POI.
Each interaction type (shrine, loot, combat, knowledge, npc, dungeon, boss)
has distinct resolution logic gated by discovery state, depletion, and
per-hero cooldowns.
"""

from __future__ import annotations

import math

from config import TILE_SIZE
from game.sim.determinism import get_rng


# Interaction range: hero must be within this many tiles of the POI center.
_INTERACTION_RANGE_TILES = 2

# Shrine cooldown duration in seconds (per-hero per-POI).
_SHRINE_COOLDOWN_SEC = 300.0

# Knowledge reveal radius in tiles.
_KNOWLEDGE_REVEAL_TILES = 15

# Loot gold range (inclusive).
_LOOT_GOLD_MIN = 20
_LOOT_GOLD_MAX = 50


class POIInteractionSystem:
    """Checks hero proximity to discovered POIs and resolves interactions."""

    def __init__(self):
        # Per-hero per-POI cooldown tracker: (hero_id, poi_id) -> remaining seconds.
        self._hero_poi_cooldowns: dict[tuple[int, int], float] = {}
        self._rng = get_rng("poi_interaction")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick_cooldowns(self, pois: list, dt: float) -> None:
        """Decrement per-POI global cooldowns and per-hero interaction cooldowns."""
        # Global POI cooldowns (shrine reuse timer on the POI itself).
        for poi in pois:
            cd = getattr(poi, "cooldown_remaining", 0.0)
            if cd > 0:
                poi.cooldown_remaining = max(0.0, cd - dt)

        # Per-hero per-POI cooldowns.
        expired_keys: list[tuple[int, int]] = []
        for key, remaining in self._hero_poi_cooldowns.items():
            new_val = remaining - dt
            if new_val <= 0:
                expired_keys.append(key)
            else:
                self._hero_poi_cooldowns[key] = new_val
        for key in expired_keys:
            self._hero_poi_cooldowns.pop(key, None)

    def check_interactions(
        self,
        heroes: list,
        pois: list,
        world: object,
        economy: object,
        event_bus: object,
        dt: float,
    ) -> None:
        """Check if any hero is close enough to interact with a discovered POI."""
        if not heroes or not pois:
            return

        interaction_range_px = _INTERACTION_RANGE_TILES * TILE_SIZE

        for hero in heroes:
            if not getattr(hero, "is_alive", False):
                continue

            hx = float(getattr(hero, "world_x", getattr(hero, "x", 0)))
            hy = float(getattr(hero, "world_y", getattr(hero, "y", 0)))
            hero_id = id(hero)

            for poi in pois:
                if not getattr(poi, "is_discovered", False):
                    continue
                if getattr(poi, "is_depleted", False):
                    continue

                poi_def = getattr(poi, "poi_def", None)
                if poi_def is None:
                    continue

                # Distance check (center of POI footprint).
                size = getattr(poi_def, "size", (1, 1))
                poi_cx = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
                poi_cy = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE
                dist = math.hypot(hx - poi_cx, hy - poi_cy)
                if dist > interaction_range_px:
                    continue

                poi_id = id(poi)
                cooldown_key = (hero_id, poi_id)

                # Skip if this hero has a cooldown on this POI.
                if cooldown_key in self._hero_poi_cooldowns:
                    continue

                interaction_type = getattr(poi_def, "interaction_type", "")
                self._resolve(interaction_type, hero, poi, world, economy, event_bus, cooldown_key)

    # ------------------------------------------------------------------
    # Interaction resolution (private)
    # ------------------------------------------------------------------

    def _resolve(
        self,
        interaction_type: str,
        hero: object,
        poi: object,
        world: object,
        economy: object,
        event_bus: object,
        cooldown_key: tuple[int, int],
    ) -> None:
        handler = _HANDLERS.get(interaction_type)
        if handler is not None:
            handler(self, hero, poi, world, economy, event_bus, cooldown_key)

    def _handle_shrine(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """Heal the hero to full HP. Set a cooldown on the POI for this hero."""
        max_hp = getattr(hero, "max_hp", getattr(hero, "hp", 100))
        hero.hp = max_hp
        poi.cooldown_remaining = _SHRINE_COOLDOWN_SEC
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _SHRINE_COOLDOWN_SEC

        self._emit_event(event_bus, "poi_interaction", hero=hero, poi=poi, interaction_type="shrine")

    def _handle_loot(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """Give the hero 20-50 gold (deterministic). Mark POI as depleted."""
        gold = self._rng.randint(_LOOT_GOLD_MIN, _LOOT_GOLD_MAX)
        hero.gold = getattr(hero, "gold", 0) + gold
        poi.is_depleted = True
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="loot", gold=gold,
        )

    def _handle_combat(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """Mark POI as interacted and emit combat trigger event."""
        if getattr(poi, "is_interacted", False):
            return
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1

        self._emit_event(
            event_bus, "poi_combat_triggered",
            hero=hero, poi=poi, interaction_type="combat",
        )

    def _handle_knowledge(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """Reveal fog of war in a 15-tile radius around the POI."""
        if getattr(poi, "is_interacted", False):
            return
        if hasattr(world, "_reveal_circle"):
            gx = getattr(poi, "grid_x", 0)
            gy = getattr(poi, "grid_y", 0)
            world._reveal_circle(gx, gy, _KNOWLEDGE_REVEAL_TILES)
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="knowledge",
        )

    def _handle_npc(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """Mark as interacted. Actual NPC conversation via LLM comes in a later sprint."""
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="npc",
        )

    def _handle_dungeon(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """Mark as interacted. Underground system comes in WK57."""
        if getattr(poi, "is_interacted", False):
            return
        poi.is_interacted = True

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="dungeon",
        )

    def _handle_boss(self, hero, poi, world, economy, event_bus, cooldown_key) -> None:
        """WK58: Spawn a named boss enemy at boss-type POI location."""
        if getattr(poi, "is_interacted", False):
            return

        from game.entities.enemy import BanditLord, DemonOverlord

        poi_def = getattr(poi, "poi_def", None)
        poi_type = getattr(poi_def, "poi_type", "")
        size = getattr(poi_def, "size", (1, 1))
        spawn_x = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
        spawn_y = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE

        if poi_type == "poi_bandit_fortress":
            boss = BanditLord(spawn_x, spawn_y)
        elif poi_type == "poi_demon_portal":
            boss = DemonOverlord(spawn_x, spawn_y)
        else:
            poi.is_interacted = True
            return

        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1

        self._emit_event(
            event_bus, "boss_spawned",
            hero=hero, poi=poi, boss=boss, interaction_type="boss",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_event(event_bus, event_type: str, **payload) -> None:
        if event_bus is None:
            return
        try:
            payload["type"] = event_type
            event_bus.emit(payload)
        except Exception:
            pass


# Dispatch table — avoids a long if/elif chain.
_HANDLERS = {
    "shrine":    POIInteractionSystem._handle_shrine,
    "loot":      POIInteractionSystem._handle_loot,
    "combat":    POIInteractionSystem._handle_combat,
    "knowledge": POIInteractionSystem._handle_knowledge,
    "npc":       POIInteractionSystem._handle_npc,
    "dungeon":   POIInteractionSystem._handle_dungeon,
    "boss":      POIInteractionSystem._handle_boss,
}
