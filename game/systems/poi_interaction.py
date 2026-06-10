"""
WK56 Wave 1: POI Interaction System.

Resolves interactions when a hero arrives at a discovered POI.
Each interaction type (shrine, loot, combat, knowledge, npc, dungeon, boss,
and the WK132 well/outpost/windmill/ruins) has distinct resolution logic
gated by discovery state, depletion, and per-hero cooldowns.
"""

from __future__ import annotations

import math

from config import TILE_SIZE
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as _sim_now_ms
from game.systems.loot import LootSystem


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

# WK132: Windmill Ruin knowledge reveal radius (smaller than the full 15).
_WINDMILL_REVEAL_TILES = 8

# WK132: Ruined Outpost — per-hero retry cooldown between triggering the
# encounter and coming back to claim the cleared outpost (kept short so the
# hero that wins the fight on-site claims it promptly).
_OUTPOST_RETRY_COOLDOWN_SEC = 10.0

# WK132: enemies within this many tiles of the outpost centre block clearing.
_OUTPOST_CLEAR_RADIUS_TILES = 8

# WK132: Mysterious Well outcome weights (cumulative on one rng.random() draw):
# gold 40% / item 25% (via roll_poi_drop) / monsters 20% / reveal 15%.
_WELL_GOLD_CUM = 0.40
_WELL_ITEM_CUM = 0.65
_WELL_MONSTER_CUM = 0.85


def _tier_enemy_types(tier: int) -> list:
    """Enemy mix for a POI combat encounter, by difficulty tier (WK132:
    factored out of ``_handle_combat``, values unchanged)."""
    if tier <= 2:
        return ["goblin"]
    if tier == 3:
        return ["skeleton", "goblin"]
    return ["skeleton", "bandit"]


class POIInteractionSystem:
    """Checks hero proximity to discovered POIs and resolves interactions."""

    def __init__(self):
        # Per-hero per-POI cooldown tracker: (hero_id, poi_id) -> remaining seconds.
        self._hero_poi_cooldowns: dict[tuple[int, int], float] = {}
        self._rng = get_rng("poi_interaction")
        # WK131: item drops from loot caches. Separate "loot" stream — the gold
        # roll above stays on the legacy "poi_interaction" stream, byte-identical.
        # Constructing this draws no RNG (digest-safe).
        self._loot_system = LootSystem()
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

        # WK131: roll an item drop IN ADDITION to the gold (seeded "loot"
        # stream; drawn only on this interaction event — digest scenario has
        # no POIs so this is structurally unreachable there).
        item = self._loot_system.roll_poi_drop(tier)
        item_name = ""
        item_outcome = ""
        if item is not None:
            item_outcome = LootSystem.grant_item(hero, item)
            item_name = item.name

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="loot",
            hero_name=hero_name, poi_name=poi_name, gold=gold,
            item_name=item_name, item_outcome=item_outcome,
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
        self._emit_combat_spawn(
            hero, poi, event_bus,
            interaction_type="combat",
            spawn_count=spawn_count,
            enemy_types=_tier_enemy_types(tier),
        )

    def _emit_combat_spawn(
        self, hero, poi, event_bus, *,
        interaction_type: str, spawn_count: int, enemy_types: list,
    ) -> None:
        """WK132: shared ``poi_combat_triggered`` emission (factored out of
        ``_handle_combat``, behavior-identical) — reused by the Ruined
        Outpost encounter and the Mysterious Well monster outcome."""
        poi_def = getattr(poi, "poi_def", None)
        # Spawn location: world-pixel center of the POI.
        size = getattr(poi_def, "size", (1, 1))
        spawn_x = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
        spawn_y = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE

        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        self._emit_event(
            event_bus, "poi_combat_triggered",
            hero=hero, poi=poi, interaction_type=interaction_type,
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
        revealed_poi_name = self._cascade_discover_nearest(
            hero, poi, pois, event_bus,
            max_range_px=_KNOWLEDGE_REVEAL_TILES * TILE_SIZE,
        )

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="knowledge",
            hero_name=hero_name, poi_name=poi_name,
            revealed_poi_name=revealed_poi_name,
        )

    def _cascade_discover_nearest(
        self, hero, poi, pois, event_bus, max_range_px: float | None,
    ) -> str | None:
        """Discover the nearest undiscovered POI (WK132: factored out of
        ``_handle_knowledge``, behavior-identical). ``max_range_px=None``
        means unbounded (Mysterious Well reveal outcome). Returns the
        revealed POI's display name, or None when nothing was in range."""
        if not pois:
            return None
        poi_def = getattr(poi, "poi_def", None)
        size = getattr(poi_def, "size", (1, 1))
        this_cx = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
        this_cy = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE

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
            if (max_range_px is None or d <= max_range_px) and d < best_dist:
                best_dist = d
                best_poi = other_poi

        if best_poi is None:
            return None

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
        return revealed_poi_name

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

        from game.entities.enemy import BanditLord, DemonOverlord, Dragon

        poi_def = getattr(poi, "poi_def", None)
        poi_type = getattr(poi_def, "poi_type", "")
        size = getattr(poi_def, "size", (1, 1))
        spawn_x = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
        spawn_y = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE

        if poi_type == "poi_bandit_fortress":
            boss = BanditLord(spawn_x, spawn_y)
        elif poi_type == "poi_demon_portal":
            boss = DemonOverlord(spawn_x, spawn_y)
        elif poi_type == "poi_dragon_cave":
            # WK132: Dragon Cave boss arena. The dragon's guaranteed rare+
            # drop comes from loot.BOSS_ENEMY_TYPES on the kill event.
            boss = Dragon(spawn_x, spawn_y)
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
    # WK132 handlers: well / outpost / windmill / ruins
    # ------------------------------------------------------------------

    def _handle_well(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Mysterious Well: one-time seeded random outcome.

        One draw on the interaction RNG stream picks the outcome:
        gold 40% / item 25% (roll_poi_drop; a miss pays consolation gold) /
        spawn 1-2 monsters 20% / reveal nearest undiscovered POI 15%.
        """
        if getattr(poi, "is_interacted", False):
            return
        poi.is_interacted = True
        poi.is_depleted = True  # one-time: the well goes dark after one look
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        tier = max(1, int(getattr(poi_def, "difficulty_tier", 1)))
        hero_name = getattr(hero, "name", "Unknown")
        poi_name = getattr(poi_def, "display_name", "Unknown POI")

        roll = self._rng.random()
        gold = 0
        item_name = ""
        item_outcome = ""
        revealed_poi_name = None

        if roll < _WELL_GOLD_CUM:
            outcome = "gold"
            gold = self._rng.randint(_LOOT_GOLD_MIN * tier, _LOOT_GOLD_MAX * tier)
            hero.gold = getattr(hero, "gold", 0) + gold
        elif roll < _WELL_ITEM_CUM:
            outcome = "item"
            item = self._loot_system.roll_poi_drop(tier)
            if item is not None:
                item_outcome = LootSystem.grant_item(hero, item)
                item_name = item.name
            else:
                # The drop roll missed — a few coins glint at the bottom.
                gold = 10 * tier
                hero.gold = getattr(hero, "gold", 0) + gold
        elif roll < _WELL_MONSTER_CUM:
            outcome = "monsters"
            spawn_count = self._rng.randint(1, 2)
            self._emit_combat_spawn(
                hero, poi, event_bus,
                interaction_type="well",
                spawn_count=spawn_count,
                enemy_types=_tier_enemy_types(tier),
            )
        else:
            outcome = "reveal"
            revealed_poi_name = self._cascade_discover_nearest(
                hero, poi, pois, event_bus, max_range_px=None,
            )

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="well",
            hero_name=hero_name, poi_name=poi_name,
            outcome=outcome, gold=gold,
            item_name=item_name, item_outcome=item_outcome,
            revealed_poi_name=revealed_poi_name,
        )

    def _handle_outpost(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Ruined Outpost: tier-scaled combat encounter; once the area is
        cleared, the outpost becomes a PERMANENT fog-of-war revealer
        (``poi.grants_vision`` + ``poi_def.vision_radius``, consumed by
        ``game.sim.fog.update_fog_of_war`` like building vision)."""
        if getattr(poi, "grants_vision", False):
            return  # already cleared and claimed

        if not getattr(poi, "is_interacted", False):
            # Phase 1: wake the nest — reuse the poi_combat_triggered pipeline.
            poi.is_interacted = True
            poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
            self._hero_poi_cooldowns[cooldown_key] = _OUTPOST_RETRY_COOLDOWN_SEC
            poi_def = getattr(poi, "poi_def", None)
            tier = max(1, int(getattr(poi_def, "difficulty_tier", 1)))
            self._emit_combat_spawn(
                hero, poi, event_bus,
                interaction_type="outpost",
                spawn_count=max(2, tier),
                enemy_types=_tier_enemy_types(tier),
            )
            return

        # Phase 2: combat already triggered — claim once no enemies remain nearby.
        if self._enemies_near_poi(poi, _OUTPOST_CLEAR_RADIUS_TILES):
            self._hero_poi_cooldowns[cooldown_key] = _OUTPOST_RETRY_COOLDOWN_SEC
            return

        poi.grants_vision = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="outpost",
            hero_name=getattr(hero, "name", "Unknown"),
            poi_name=getattr(poi_def, "display_name", "Unknown POI"),
            cleared=True,
            vision_radius=int(getattr(poi_def, "vision_radius", 0)),
        )

    def _enemies_near_poi(self, poi, radius_tiles: int) -> bool:
        """True if any living enemy is within *radius_tiles* of the POI centre.
        Uses the sim engine reference when wired; without one (unit tests)
        the area counts as clear."""
        sim = self._sim_engine
        enemies = getattr(sim, "enemies", None) if sim is not None else None
        if not enemies:
            return False
        poi_def = getattr(poi, "poi_def", None)
        size = getattr(poi_def, "size", (1, 1))
        cx = (getattr(poi, "grid_x", 0) + size[0] / 2.0) * TILE_SIZE
        cy = (getattr(poi, "grid_y", 0) + size[1] / 2.0) * TILE_SIZE
        radius_px = radius_tiles * TILE_SIZE
        r2 = radius_px * radius_px
        for enemy in enemies:
            if not getattr(enemy, "is_alive", True):
                continue
            dx = float(getattr(enemy, "x", 0.0)) - cx
            dy = float(getattr(enemy, "y", 0.0)) - cy
            if dx * dx + dy * dy <= r2:
                return True
        return False

    def _handle_windmill(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Windmill Ruin: one-time knowledge/flavor — small fog reveal (8
        tiles), no cascade. The repair-quest transform is explicitly deferred
        (WK132 scope decision)."""
        if getattr(poi, "is_interacted", False):
            return
        if hasattr(world, "_reveal_circle"):
            world._reveal_circle(
                getattr(poi, "grid_x", 0), getattr(poi, "grid_y", 0),
                _WINDMILL_REVEAL_TILES,
            )
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="windmill",
            hero_name=getattr(hero, "name", "Unknown"),
            poi_name=getattr(poi_def, "display_name", "Unknown POI"),
            narrative=getattr(poi_def, "description", ""),
        )

    def _handle_ruins(self, hero, poi, world, economy, event_bus, cooldown_key, pois=None) -> None:
        """Ancient Ruins: knowledge + loot combo — fog reveal (15 tiles) +
        cascade-discover the nearest undiscovered POI + tier-scaled gold +
        a roll_poi_drop item chance. One-time; the ruins remain as a landmark."""
        if getattr(poi, "is_interacted", False):
            return
        if hasattr(world, "_reveal_circle"):
            world._reveal_circle(
                getattr(poi, "grid_x", 0), getattr(poi, "grid_y", 0),
                _KNOWLEDGE_REVEAL_TILES,
            )
        poi.is_interacted = True
        poi.interaction_count = getattr(poi, "interaction_count", 0) + 1
        self._hero_poi_cooldowns[cooldown_key] = _ONESHOT_COOLDOWN_SEC

        poi_def = getattr(poi, "poi_def", None)
        tier = max(1, int(getattr(poi_def, "difficulty_tier", 1)))

        revealed_poi_name = self._cascade_discover_nearest(
            hero, poi, pois, event_bus,
            max_range_px=_KNOWLEDGE_REVEAL_TILES * TILE_SIZE,
        )

        gold = self._rng.randint(_LOOT_GOLD_MIN * tier, _LOOT_GOLD_MAX * tier)
        hero.gold = getattr(hero, "gold", 0) + gold

        item = self._loot_system.roll_poi_drop(tier)
        item_name = ""
        item_outcome = ""
        if item is not None:
            item_outcome = LootSystem.grant_item(hero, item)
            item_name = item.name

        self._emit_event(
            event_bus, "poi_interaction",
            hero=hero, poi=poi, interaction_type="ruins",
            hero_name=getattr(hero, "name", "Unknown"),
            poi_name=getattr(poi_def, "display_name", "Unknown POI"),
            gold=gold, item_name=item_name, item_outcome=item_outcome,
            revealed_poi_name=revealed_poi_name,
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
    # WK132: POIs round-out
    "well":      POIInteractionSystem._handle_well,
    "outpost":   POIInteractionSystem._handle_outpost,
    "windmill":  POIInteractionSystem._handle_windmill,
    "ruins":     POIInteractionSystem._handle_ruins,
}
