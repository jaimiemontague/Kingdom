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
from game.sim.timebase import now_ms as _sim_now_ms


# Interaction range: hero must be within this many tiles of the POI center.
_INTERACTION_RANGE_TILES = 2

# Shrine cooldown duration in seconds (per-hero per-POI).
_SHRINE_COOLDOWN_SEC = 300.0

# Knowledge reveal radius in tiles.
_KNOWLEDGE_REVEAL_TILES = 15

# Loot gold range (inclusive).
_LOOT_GOLD_MIN = 20
_LOOT_GOLD_MAX = 50

# Long cooldown for one-time interactions so _resolve isn't called every tick
# while a hero stays near an already-interacted POI.
_ONESHOT_COOLDOWN_SEC = 600.0


class POIInteractionSystem:
    """Checks hero proximity to discovered POIs and resolves interactions."""

    def __init__(self):
        # Per-hero per-POI cooldown tracker: (hero_id, poi_id) -> remaining seconds.
        self._hero_poi_cooldowns: dict[tuple[int, int], float] = {}
        self._rng = get_rng("poi_interaction")
        # WK57 Wave 5: underground areas reference (set by sim_engine after setup)
        self._underground_areas: dict = {}
        # WK57 Wave 5: sim engine reference for enemy spawning
        self._sim_engine = None

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
        # Squared distance for fast rejection (avoids math.hypot for most pairs).
        range_sq = interaction_range_px * interaction_range_px

        # Pre-filter POIs: only active (discovered, not depleted, has def) with cached centers.
        active_pois = []
        for poi in pois:
            if not getattr(poi, "is_discovered", False):
                continue
            if getattr(poi, "is_depleted", False):
                continue
            poi_def = getattr(poi, "poi_def", None)
            if poi_def is None:
                continue
            size = getattr(poi_def, "size", (1, 1))
            poi_cx = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
            poi_cy = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE
            active_pois.append((poi, poi_def, poi_cx, poi_cy))

        if not active_pois:
            return

        for hero in heroes:
            if not getattr(hero, "is_alive", False):
                continue

            hx = float(getattr(hero, "world_x", getattr(hero, "x", 0)))
            hy = float(getattr(hero, "world_y", getattr(hero, "y", 0)))
            hero_id = id(hero)

            for poi, poi_def, poi_cx, poi_cy in active_pois:
                dx = hx - poi_cx
                dy = hy - poi_cy
                if dx * dx + dy * dy > range_sq:
                    continue

                poi_id = id(poi)
                cooldown_key = (hero_id, poi_id)

                if cooldown_key in self._hero_poi_cooldowns:
                    continue

                interaction_type = getattr(poi_def, "interaction_type", "")
                self._resolve(interaction_type, hero, poi, world, economy, event_bus, cooldown_key, pois)

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
        pois: list | None = None,
    ) -> None:
        handler = _HANDLERS.get(interaction_type)
        if handler is not None:
            handler(self, hero, poi, world, economy, event_bus, cooldown_key, pois=pois)
            # WK55: stamp the POI so renderer can flash/glow for ~1 second
            try:
                poi.last_interaction_tick = int(_sim_now_ms())
            except Exception:
                pass

    def _handle_shrine(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Heal the hero to full HP, apply a temporary attack buff, and set a cooldown."""
        max_hp = getattr(hero, "max_hp", getattr(hero, "hp", 100))
        hero.hp = max_hp
        poi.cooldown_remaining = _SHRINE_COOLDOWN_SEC
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _SHRINE_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        tier = max(1, int(getattr(poi_def, "difficulty_tier", 1)))
        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        # Apply temporary attack buff if the hero supports it.
        buff_attack = 2 * max(1, (tier + 1) // 2)
        if hasattr(hero, "apply_or_refresh_buff"):
            from game.sim.timebase import now_ms as _buff_now_ms
            hero.apply_or_refresh_buff(
                name="poi_shrine",
                atk_delta=buff_attack,
                duration_s=90.0,
                now_ms=int(_buff_now_ms()),
            )

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="shrine",
            hero_name=hero_name, poi_name=poi_name,
            healed=True, buff_attack=buff_attack,
        )

    def _handle_loot(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Give the hero gold scaled by difficulty tier. Mark POI as depleted."""
        poi_def = getattr(poi, "poi_def", None)
        tier = max(1, int(getattr(poi_def, "difficulty_tier", 1)))
        gold_min = _LOOT_GOLD_MIN * tier
        gold_max = _LOOT_GOLD_MAX * tier
        gold = self._rng.randint(gold_min, gold_max)
        hero.gold = getattr(hero, "gold", 0) + gold
        poi.is_depleted = True
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1

        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="loot",
            hero_name=hero_name, poi_name=poi_name, gold=gold,
        )

    def _handle_combat(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Mark POI as interacted and spawn enemies at the POI location."""
        if getattr(poi, "is_interacted", False):
            return
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        tier = max(1, int(getattr(poi_def, "difficulty_tier", 1)))
        spawn_count = max(2, tier)

        # Enemy types based on difficulty tier.
        if tier <= 2:
            enemy_types = ["goblin"]
        elif tier == 3:
            enemy_types = ["skeleton", "goblin"]
        else:
            enemy_types = ["skeleton", "bandit"]

        # Spawn location: world-pixel center of the POI.
        size = getattr(poi_def, "size", (1, 1))
        spawn_x = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
        spawn_y = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE

        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        self._emit_event(
            event_bus, "poi_combat_triggered",
            hero=hero, poi=poi, interaction_type="combat",
            hero_name=hero_name, poi_name=poi_name,
            spawn_count=spawn_count, enemy_types=enemy_types,
            spawn_x=spawn_x, spawn_y=spawn_y,
        )

    def _handle_knowledge(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Reveal fog of war in a 15-tile radius around the POI and cascade-discover the nearest undiscovered POI."""
        if getattr(poi, "is_interacted", False):
            return
        if hasattr(world, "_reveal_circle"):
            gx = getattr(poi, "grid_x", 0)
            gy = getattr(poi, "grid_y", 0)
            world._reveal_circle(gx, gy, _KNOWLEDGE_REVEAL_TILES)
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        # Cascade reveal: find and discover the nearest undiscovered POI within 15 tiles.
        revealed_poi_name = None
        if pois:
            size = getattr(poi_def, "size", (1, 1))
            this_cx = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
            this_cy = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE
            cascade_range_px = _KNOWLEDGE_REVEAL_TILES * TILE_SIZE

            best_poi = None
            best_dist = float("inf")
            for other_poi in pois:
                if other_poi is poi:
                    continue
                if getattr(other_poi, "is_discovered", False):
                    continue
                other_def = getattr(other_poi, "poi_def", None)
                other_size = getattr(other_def, "size", (1, 1))
                other_cx = (getattr(other_poi, "grid_x", 0) + other_size[0] / 2.0) * TILE_SIZE
                other_cy = (getattr(other_poi, "grid_y", 0) + other_size[1] / 2.0) * TILE_SIZE
                d = math.hypot(this_cx - other_cx, this_cy - other_cy)
                if d <= cascade_range_px and d < best_dist:
                    best_dist = d
                    best_poi = other_poi

            if best_poi is not None:
                best_poi.is_discovered = True
                best_poi_def = getattr(best_poi, "poi_def", None)
                revealed_poi_name = getattr(best_poi_def, "display_name", "Unknown POI")
                self._emit_event(
                    event_bus, "poi_discovered",
                    poi=best_poi, hero=hero,
                    hero_id=str(getattr(hero, "hero_id", "") or ""),
                    poi_type=getattr(best_poi_def, "poi_type", ""),
                    display_name=revealed_poi_name,
                )

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="knowledge",
            hero_name=hero_name, poi_name=poi_name,
            revealed_poi_name=revealed_poi_name,
        )

    def _handle_npc(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Mark as interacted and emit narrative flavor text from the POI description."""
        if getattr(poi, "is_interacted", False):
            return
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")
        narrative = getattr(poi_def, "description", "")

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="npc",
            hero_name=hero_name, poi_name=poi_name, narrative=narrative,
        )

    def _handle_dungeon(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Handle hero entering a dungeon (cave/mine) POI.

        WK57 Wave 5: triggers actual cave entry with descent, fog reveal,
        and underground enemy spawning instead of just flavor text.
        """
        area_id = f"underground_{poi.grid_x}_{poi.grid_y}"

        # Access underground areas from the stored reference
        underground_areas = self._underground_areas
        if not underground_areas:
            # Fallback: emit flavor text only
            self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC
            poi_def = getattr(poi, "poi_def", None)
            hero_name = getattr(hero, "name", "Unknown")
            poi_name = getattr(poi_def, "display_name", "Unknown POI")
            self._emit_event(
                event_bus, "poi_interaction",
                hero=hero, poi=poi, interaction_type="dungeon",
                hero_name=hero_name, poi_name=poi_name,
                narrative="The entrance yawns darkly. Cold air seeps out.",
            )
            return

        area = underground_areas.get(area_id)
        if area is None or not area.is_generated:
            # No underground area generated for this POI
            self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC
            self._emit_event(
                event_bus, "poi_interaction",
                hero=hero, poi=poi, interaction_type="dungeon",
                hero_name=getattr(hero, "name", "Unknown"),
                poi_name=getattr(getattr(poi, "poi_def", None), "display_name", "Unknown POI"),
                narrative="The entrance yawns darkly.",
            )
            return

        hero_layer = getattr(hero, "layer", 0)
        if hero_layer == -1:
            return  # Already underground

        # Begin descent
        if hasattr(hero, "begin_descent"):
            hero.begin_descent(area_id, poi.grid_x, poi.grid_y)

        # Mark first chamber as explored
        if area.chambers:
            area.chambers[0].is_explored = True

        # Reveal underground fog at entrance
        cx = area.total_width // 2
        if hasattr(world, "reveal_underground_circle"):
            world.reveal_underground_circle(area_id, cx, 0, 4)

        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        self._emit_event(
            event_bus, "hero_entered_underground",
            hero=hero, area_id=area_id, poi=poi,
            hero_name=hero_name, poi_name=poi_name,
        )

    def _handle_boss(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
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
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        self._emit_event(
            event_bus, "boss_spawned",
            hero=hero, poi=poi, boss=boss, interaction_type="boss",
            hero_name=hero_name, poi_name=poi_name,
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
