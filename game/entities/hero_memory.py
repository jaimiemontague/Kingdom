"""
WK71: hero memory / intent / LLM-context behavior extracted from Hero into a mixin.

Mixed into Hero (``class Hero(..., HeroMemoryMixin)``). Holds ONLY methods;
all instance state stays initialized in ``Hero.__init__``. Method bodies moved
VERBATIM (they already use ``self.*``, which resolves on the combined Hero
instance), so the MRO and every call site are unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import TILE_SIZE
from game.sim.timebase import now_ms as sim_now_ms
from game.sim.contracts import HeroDecisionRecord, HeroIntentSnapshot
from game.sim.hero_profile import HeroMemoryEntry, KnownPlaceSnapshot
from game.systems import hero_memory
from game.systems.hero_memory import stable_place_id
from game.entities.hero import HeroState

if TYPE_CHECKING:
    from game.entities.buildings.base import Building


class HeroMemoryMixin:
    """WK71: memory/intent/LLM-context behavior extracted from Hero. Mixed into Hero; accesses self.* set in Hero.__init__."""

    def record_profile_memory(
        self,
        *,
        event_type: str,
        sim_time_ms: int,
        summary: str,
        subject_type: str = "",
        subject_id: str = "",
        subject_name: str = "",
        tile: tuple[int, int] | None = None,
        world_pos: tuple[float, float] | None = None,
        tags: tuple[str, ...] = (),
        importance: int = 1,
    ) -> HeroMemoryEntry:
        """Append a memory row; drops oldest entries past the configured cap."""
        eid = self._next_profile_memory_entry_id
        self._next_profile_memory_entry_id += 1
        entry = HeroMemoryEntry(
            entry_id=int(eid),
            hero_id=str(self.hero_id),
            event_type=str(event_type),
            sim_time_ms=int(sim_time_ms),
            summary=str(summary),
            subject_type=str(subject_type),
            subject_id=str(subject_id),
            subject_name=str(subject_name),
            tile=tile,
            world_pos=world_pos,
            tags=tags,
            importance=int(importance),
        )
        self.profile_memory.append(entry)
        while len(self.profile_memory) > hero_memory.PROFILE_MEMORY_MAX_ENTRIES:
            self.profile_memory.pop(0)
        # WK123 perf: invalidate the cached sorted-memory tuple used by
        # build_hero_profile_snapshot (see Hero._profile_memory_version).
        self._profile_memory_version += 1
        return entry

    def remember_known_place(
        self,
        *,
        place_type: str,
        display_name: str,
        tile: tuple[int, int],
        world_pos: tuple[float, float],
        sim_time_ms: int,
        place_id: str | None = None,
        building_type: str | None = None,
        grid_x: int | None = None,
        grid_y: int | None = None,
        explicit_place_key: str | None = None,
        is_destroyed: bool = False,
    ) -> KnownPlaceSnapshot:
        """
        Upsert a known place. First sight increments ``places_discovered``; revisits bump visits.
        """
        pid = stable_place_id(
            str(building_type or place_type),
            int(grid_x if grid_x is not None else tile[0]),
            int(grid_y if grid_y is not None else tile[1]),
            explicit_id=explicit_place_key or place_id,
        )
        existing = self.known_places.get(pid)
        first = existing is None
        if first:
            self.increment_career_stat("places_discovered", 1)

        visits = 1 if first else int(existing.visits) + 1  # type: ignore[union-attr]
        first_seen = int(sim_time_ms) if first else int(existing.first_seen_ms)  # type: ignore[union-attr]
        last_visited = int(sim_time_ms) if visits > 1 else None
        snap = KnownPlaceSnapshot(
            place_id=str(pid),
            place_type=str(place_type),
            display_name=str(display_name),
            tile=(int(tile[0]), int(tile[1])),
            world_pos=(float(world_pos[0]), float(world_pos[1])),
            first_seen_ms=first_seen,
            last_seen_ms=int(sim_time_ms),
            visits=int(visits),
            last_visited_ms=last_visited,
            is_destroyed=bool(is_destroyed),
        )
        self.known_places[str(pid)] = snap
        # WK123 perf: the upsert (new place OR updated visits/last_seen) changes the sorted
        # known-places tuple, so bump the cache version (see Hero._profile_memory_version).
        self._profile_memory_version += 1
        self._trim_known_places_if_needed()
        return snap

    def _trim_known_places_if_needed(self) -> None:
        while len(self.known_places) > hero_memory.KNOWN_PLACES_MAX_ENTRIES:
            drop_key = min(
                self.known_places.keys(),
                key=lambda k: (self.known_places[k].first_seen_ms, self.known_places[k].place_id),
            )
            del self.known_places[drop_key]
            # WK123 perf: eviction changes the sorted known-places tuple (see
            # Hero._profile_memory_version).
            self._profile_memory_version += 1

    def record_decision(self, action: str, reason: str, now_ms: int | None = None, context: dict | None = None):
        if now_ms is None:
            now_ms = sim_now_ms()
        self.last_decision = HeroDecisionRecord(
            action=str(action),
            reason=str(reason)[:120],
            at_ms=int(now_ms),
            context={} if context is None else dict(context),
        )

    def get_intent_snapshot(self, now_ms: int | None = None) -> dict:
        if now_ms is None:
            now_ms = sim_now_ms()
        snap = HeroIntentSnapshot(intent=str(getattr(self, "intent", "idle")), last_decision=getattr(self, "last_decision", None))
        return snap.to_dict(now_ms=now_ms)

    def get_stuck_snapshot(self, now_ms: int | None = None) -> dict:
        """
        UI/QA-friendly stuck status snapshot (contract field names).
        """
        if now_ms is None:
            now_ms = sim_now_ms()
        since = getattr(self, "stuck_since_ms", None)
        age_ms = 0
        if since is not None:
            try:
                age_ms = max(0, int(now_ms) - int(since))
            except Exception:
                age_ms = 0
        return {
            "stuck_active": bool(getattr(self, "stuck_active", False)),
            "stuck_since_ms": since,
            "stuck_age_ms": int(age_ms),
            "last_progress_ms": int(getattr(self, "last_progress_ms", 0) or 0),
            "unstuck_attempts": int(getattr(self, "unstuck_attempts", 0) or 0),
            "stuck_reason": str(getattr(self, "stuck_reason", "") or ""),
        }

    def _derive_intent(self) -> tuple[str, str, dict]:
        """
        Derive (intent, reason, context) from state + target.

        Intents are aligned with the current sprint taxonomy:
        idle, pursuing_bounty, shopping, returning_to_safety, engaging_enemy, defending_building, attacking_lair.
        """
        # Default
        intent = "idle"
        reason = "no urgent goal"
        context: dict = {}

        t = getattr(self, "target", None)
        state = getattr(self, "state", HeroState.IDLE)

        if state == HeroState.CAPTURED:
            capture_state = getattr(self, "capture_state", None)
            if capture_state is not None:
                captor_name = str(getattr(capture_state, "captor_boss_name", "") or getattr(capture_state, "captor_boss_id", "") or "captured")
                return "captured", f"captured by {captor_name}", {
                    "captor_boss_id": getattr(capture_state, "captor_boss_id", ""),
                    "captor_boss_name": getattr(capture_state, "captor_boss_name", ""),
                    "location_id": getattr(capture_state, "location_id", ""),
                    "location_name": getattr(capture_state, "location_name", ""),
                }
            return "captured", "captured", {}

        # Enemy engagement
        if state == HeroState.FIGHTING or (t is not None and hasattr(t, "is_alive") and getattr(t, "is_alive", False)):
            return "engaging_enemy", "engaging nearby enemy", {"target": "enemy", "enemy_type": getattr(t, "enemy_type", None)}

        # Dict targets (AI/controller activities)
        if isinstance(t, dict):
            ttype = t.get("type")
            if ttype == "bounty":
                btype = t.get("bounty_type", "explore")
                bid = t.get("bounty_id")
                if btype == "attack_lair":
                    return "attacking_lair", "pursuing lair bounty", {"target": "bounty", "bounty_id": bid, "bounty_type": btype}
                if btype == "defend_building":
                    return "defending_building", "pursuing defense bounty", {"target": "bounty", "bounty_id": bid, "bounty_type": btype}
                return "pursuing_bounty", "pursuing bounty", {"target": "bounty", "bounty_id": bid, "bounty_type": btype}
            if ttype == "shopping":
                return "shopping", "heading to marketplace", {"target": "marketplace", "item": t.get("item")}
            if ttype == "going_home":
                return "returning_to_safety", "returning home to rest", {"target": "home"}

        # Movement without a specific activity is usually "idle/exploring" for now.
        if state in (HeroState.MOVING, HeroState.RETREATING):
            intent = "idle"
            reason = "moving"
            if state == HeroState.RETREATING:
                intent = "returning_to_safety"
                reason = "retreating to safety"

        # Resting maps to safety intent (taxonomy-friendly).
        if state == HeroState.RESTING:
            intent = "returning_to_safety"
            reason = "resting at home"
            context = {"target": "home"}

        return intent, reason, context

    def _update_intent_and_decision(self, game_state: dict | None):
        now_ms = sim_now_ms()
        intent, reason, ctx = self._derive_intent()

        # Detect meaningful changes and store a new "last decision" snapshot.
        t = getattr(self, "target", None)
        key_target = None
        if isinstance(t, dict) and t.get("type") == "bounty":
            key_target = ("bounty", t.get("bounty_id"), t.get("bounty_type"))
        elif isinstance(t, dict):
            key_target = ("dict", t.get("type"))
        elif t is None:
            key_target = None
        else:
            # Avoid non-deterministic identities (id()) in snapshots.
            key_target = ("obj", t.__class__.__name__)

        new_key = (intent, getattr(self, "state", None), key_target)
        if self._intent_prev_key != new_key:
            self.intent = str(intent)
            self.record_decision(action=intent, reason=reason, now_ms=now_ms, context=ctx)
            self._intent_prev_key = new_key

    def get_context_for_llm(self, game_state: dict) -> dict:
        """Build context dictionary for LLM decision making."""
        context = {
            "hero": {
                "name": self.name,
                "class": self.hero_class,
                "level": self.level,
                "hp": self.hp,
                "max_hp": self.max_hp,
                "health_percent": round(self.health_percent * 100),
                "gold": self.gold,
                "attack": self.attack,
                "defense": self.defense,
            },
            "inventory": {
                "weapon": self.weapon["name"] if self.weapon else "Fists",
                "armor": self.armor["name"] if self.armor else "None",
                "potions": self.potions,
            },
            "personality": self.personality,
            "current_state": self.state.name,
            "nearby_enemies": [],
            "available_bounties": game_state.get("bounties", []),
            "shop_items": [],
            "situation": {
                "in_combat": False,
                "low_health": self.health_percent < 0.5,
                "critical_health": self.health_percent < 0.25,
                "has_potions": self.potions > 0,
                "near_safety": False,
            },
        }

        # Add nearby enemies
        for enemy in game_state.get("enemies", []):
            if enemy.is_alive:
                dist = self.distance_to(enemy.x, enemy.y)
                if dist < TILE_SIZE * 10:  # Within 10 tiles
                    context["nearby_enemies"].append({
                        "type": enemy.enemy_type,
                        "hp": enemy.hp,
                        "max_hp": enemy.max_hp,
                        "distance": round(dist / TILE_SIZE, 1),
                    })

        # Add shop items if near marketplace
        for building in game_state.get("buildings", []):
            if building.building_type == "marketplace":
                dist = self.distance_to(building.center_x, building.center_y)
                if dist < TILE_SIZE * 5:
                    context["shop_items"] = building.get_available_items()
                    context["near_marketplace"] = True

        return context
