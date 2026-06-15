"""WK138 quest-chain gameplay system.

This system owns the runtime state machine for layered quest chains while
coexisting with the existing one-shot quest system. Runtime state stores only
stable ids and primitive facts. Live entity refs are resolved from the current
system context on demand, and the no-chain/default path returns immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import TILE_SIZE
from game.content.bosses import ASHWING_BOSS_DEF
from game.content.items import get_item
from game.content.quest_chains import (
    ASHWINGS_HOARD,
    ASHWING_THE_RED_NAME,
    ASHWINGS_HOARD_NAME,
    CLAIM_HOARD,
    ASSAULT_GATE,
    BLACKBANNERS_TOLL,
    BLACKBANNER_TOLL_TAKER_STORY_NAME,
    BLACKBANNER_RESCUE,
    BLACKBANNER_REVENGE,
    CLAIM_REWARD,
    COLLECT_ITEM,
    DELIVER_ITEM,
    AVENGE_FALLEN_HERO,
    QUEST_CHAIN_DEFS,
    RELIC_OF_THE_OLD_SHRINE,
    INTERCEPT_TOLL_TAKER,
    PREPARE_HUNT,
    designate_blackbanner_toll_taker,
    RESCUE_HERO,
    SLAY_NAMED_BOSS,
    SCOUT_DRAGON_CAVE,
    SCOUT_LOCATION,
    SCOUT_FORTRESS,
    SLAY_BLACKBANNER,
    SLAY_ASHWING,
    QuestChainDef,
    QuestPhaseDef,
    get_chain_def,
)
from game.events import GameEventType
from game.entities.enemy import Bandit, BanditLord, Dragon
from game.sim.contracts import (
    BossKillMemory,
    HeroCaptureState,
    RescueOpportunitySnapshot,
    RevengeOpportunitySnapshot,
    QuestChainHistorySummary,
    QuestChainPhaseSnapshot,
    QuestChainSnapshot,
)
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.protocol import GameSystem, SystemContext

_LIVE_CHAIN_STATUSES = ("offered", "active")
_TARGET_REACH_RADIUS_PX = TILE_SIZE * 2


@dataclass(slots=True)
class QuestChainInstance:
    """Mutable runtime state for one quest chain."""

    chain_id: int
    chain_type: str
    name: str
    reward_gold: int
    status: str = "offered"
    offered_to_hero_id: str | None = None
    assigned_hero_id: str | None = None
    current_phase_index: int = 0
    current_phase_id: str = ""
    offered_at_ms: int = 0
    accepted_at_ms: int = 0
    completed_at_ms: int = 0
    failed_at_ms: int = 0
    current_phase_started_ms: int = 0
    facts: dict[str, object] = field(default_factory=dict)
    history: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _TargetInfo:
    entity_id: str = ""
    name: str = ""
    position: tuple[float, float] | None = None


class QuestChainSystem(GameSystem):
    """Layered quest-chain runtime for WK138."""

    def __init__(self, definitions: dict[str, QuestChainDef] | None = None):
        self.definitions = dict(QUEST_CHAIN_DEFS if definitions is None else definitions)
        self.chains: list[QuestChainInstance] = []
        self.completed_chains: list[QuestChainInstance] = []
        self.failed_chains: list[QuestChainInstance] = []
        self._captured_heroes: dict[str, HeroCaptureState] = {}
        self._rescue_chain_by_hero_id: dict[str, int] = {}
        self._revenge_chain_by_pair: dict[tuple[str, str], int] = {}
        self._next_chain_id = 1
        self._event_bus: object | None = None

    # ------------------------------------------------------------------
    # Creation / acceptance
    # ------------------------------------------------------------------

    def create_chain(
        self,
        chain_type: str,
        *,
        hero: object | None = None,
        hero_id: str | None = None,
        origin_target: object | str | None = None,
        delivery_target: object | str | None = None,
        reward_gold: int | None = None,
        facts: dict[str, object] | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        return self.offer_chain(
            chain_type,
            hero=hero,
            hero_id=hero_id,
            origin_target=origin_target,
            delivery_target=delivery_target,
            reward_gold=reward_gold,
            facts=facts,
            event_bus=event_bus,
            now_ms=now_ms,
        )

    def offer_chain(
        self,
        chain_type: str,
        *,
        hero: object | None = None,
        hero_id: str | None = None,
        origin_target: object | str | None = None,
        delivery_target: object | str | None = None,
        reward_gold: int | None = None,
        facts: dict[str, object] | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        definition = self.get_definition(chain_type)
        now = int(sim_now_ms() if now_ms is None else now_ms)
        offered_to_hero_id = _hero_id(hero, hero_id)
        origin_info = self._capture_target(origin_target)
        delivery_info = self._capture_target(delivery_target)
        reward = int(reward_gold if reward_gold is not None else definition.reward_profile.gold)

        chain = QuestChainInstance(
            chain_id=int(self._next_chain_id),
            chain_type=str(definition.chain_type),
            name=str(definition.display_name),
            reward_gold=reward,
            status="offered",
            offered_to_hero_id=offered_to_hero_id,
            current_phase_index=0,
            current_phase_id=str(definition.phases[0].phase_id) if definition.phases else "",
            offered_at_ms=now,
            current_phase_started_ms=now,
            facts={
                "origin_target_id": origin_info.entity_id,
                "origin_target_name": origin_info.name,
                "origin_target_position": origin_info.position,
                "delivery_target_id": delivery_info.entity_id,
                "delivery_target_name": delivery_info.name,
                "delivery_target_position": delivery_info.position,
                "relic_id": "relic_of_the_old_shrine",
                "relic_name": "Relic of the Old Shrine",
                "relic_scouted": False,
                "relic_collected": False,
                "relic_carried": False,
                "relic_delivered": False,
            },
        )
        if facts:
            chain.facts.update(dict(facts))
        self._next_chain_id += 1
        self.chains.append(chain)
        self._record_history(
            chain,
            event="chain_offered",
            status="offered",
            hero_id=offered_to_hero_id,
            now_ms=now,
        )
        self._emit(
            event_bus,
            GameEventType.QUEST_CHAIN_OFFERED,
            chain=chain,
            now_ms=now,
        )
        return chain

    def offer_blackbanners_toll(
        self,
        *,
        ctx: SystemContext | None = None,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        fortress_target = self._find_blackbanner_fortress_target(ctx)
        reward_target = getattr(ctx, "castle", None) if ctx is not None else None
        now = int(sim_now_ms() if now_ms is None else now_ms)
        facts = self._blackbanner_base_facts(
            chain_id=self._next_chain_id,
            fortress_target=fortress_target,
            reward_target=reward_target,
            now_ms=now,
        )
        self._ensure_blackbanner_event_hooks(event_bus if event_bus is not None else getattr(ctx, "event_bus", None))
        return self.create_chain(
            BLACKBANNERS_TOLL.chain_type,
            hero=hero,
            hero_id=hero_id,
            reward_gold=BLACKBANNERS_TOLL.reward_profile.gold,
            facts=facts,
            event_bus=event_bus if event_bus is not None else getattr(ctx, "event_bus", None),
            now_ms=now,
        )

    def offer_ashwings_hoard(
        self,
        *,
        ctx: SystemContext | None = None,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        dragon_cave_target = self._find_first_target(ctx, preferred_ids=("poi_dragon_cave",))
        prep_target = self._find_first_target(ctx, preferred_ids=("poi_shrine", "poi_ancient_ruins", "castle"))
        if prep_target is None and ctx is not None:
            prep_target = getattr(ctx, "castle", None) or dragon_cave_target
        if dragon_cave_target is None and prep_target is not None:
            dragon_cave_target = prep_target
        now = int(sim_now_ms() if now_ms is None else now_ms)
        facts = self._ashwing_base_facts(
            chain_id=self._next_chain_id,
            dragon_cave_target=dragon_cave_target,
            prep_target=prep_target,
            now_ms=now,
        )
        return self.create_chain(
            ASHWINGS_HOARD.chain_type,
            hero=hero,
            hero_id=hero_id,
            reward_gold=ASHWINGS_HOARD.reward_profile.gold,
            facts=facts,
            event_bus=event_bus if event_bus is not None else getattr(ctx, "event_bus", None),
            now_ms=now,
        )

    def start_blackbanners_toll(
        self,
        *,
        ctx: SystemContext | None = None,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        chain = self.offer_blackbanners_toll(
            ctx=ctx,
            hero=hero,
            hero_id=hero_id,
            event_bus=event_bus,
            now_ms=now_ms,
        )
        self.accept_chain(
            chain.chain_id,
            hero=hero,
            hero_id=hero_id,
            event_bus=event_bus,
            now_ms=now_ms,
        )
        self._spawn_blackbanner_toll_taker(
            chain,
            ctx=ctx,
            event_bus=event_bus if event_bus is not None else getattr(ctx, "event_bus", None),
            now_ms=now_ms,
        )
        return chain

    def start_ashwings_hoard(
        self,
        *,
        ctx: SystemContext | None = None,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        chain = self.offer_ashwings_hoard(
            ctx=ctx,
            hero=hero,
            hero_id=hero_id,
            event_bus=event_bus,
            now_ms=now_ms,
        )
        self.accept_chain(
            chain.chain_id,
            hero=hero,
            hero_id=hero_id,
            event_bus=event_bus,
            now_ms=now_ms,
        )
        return chain

    def capture_blackbanner_hero(
        self,
        hero: object,
        *,
        killer: object,
        source_chain: QuestChainInstance | None = None,
        location_target: object | str | None = None,
        ctx: SystemContext | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> HeroCaptureState | None:
        if hero is None or killer is None or not self._is_blackbanner_family_killer(killer):
            return None

        hero_id = _hero_id(hero, None)
        if not hero_id:
            return None

        existing = self._captured_heroes.get(hero_id)
        if existing is not None and str(getattr(existing, "status", "")) == "captured":
            rescue_chain_id = self._rescue_chain_by_hero_id.get(hero_id)
            rescue_chain = (
                self.get_chain(rescue_chain_id, include_archived=False)
                if rescue_chain_id is not None
                else None
            )
            if rescue_chain is None or rescue_chain.chain_type != BLACKBANNER_RESCUE.chain_type or rescue_chain.status not in _LIVE_CHAIN_STATUSES:
                rescue_chain = self.offer_blackbanner_rescue(
                    existing,
                    location_target=location_target,
                    source_chain=source_chain or self._active_blackbanner_chain_for_hero(hero_id),
                    ctx=ctx,
                    event_bus=event_bus,
                    now_ms=now_ms,
                )
                if rescue_chain is not None:
                    self._rescue_chain_by_hero_id[str(existing.hero_id)] = int(rescue_chain.chain_id)
            return existing

        active_chain = source_chain or self._active_blackbanner_chain_for_hero(hero_id)
        if active_chain is None:
            return None
        if active_chain.assigned_hero_id and str(active_chain.assigned_hero_id) != str(hero_id):
            return None

        target_info = self._blackbanner_location_target(active_chain, location_target, ctx)
        now = int(sim_now_ms() if now_ms is None else now_ms)
        capture = hero.begin_capture(
            captor_boss_id=str(getattr(killer, "entity_id", "") or ""),
            captor_boss_name=str(getattr(killer, "name", "") or ""),
            captor_boss_type=str(getattr(killer, "enemy_type", "") or ""),
            location_id=target_info.entity_id,
            location_name=target_info.name,
            source_chain_id=str(active_chain.chain_id),
            source_chain_type=str(active_chain.chain_type),
            captured_at_ms=now,
        )
        self._captured_heroes[hero_id] = capture

        if active_chain.chain_type == BLACKBANNERS_TOLL.chain_type and active_chain.status == "active":
            self.fail_chain(
                active_chain.chain_id,
                ctx=ctx,
                event_bus=event_bus,
                now_ms=now,
                reason="hero_captured",
            )

        rescue_chain = self.offer_blackbanner_rescue(
            capture,
            location_target=target_info,
            source_chain=active_chain,
            ctx=ctx,
            event_bus=event_bus,
            now_ms=now,
        )
        if rescue_chain is not None:
            self._rescue_chain_by_hero_id[str(capture.hero_id)] = int(rescue_chain.chain_id)
        return capture

    def offer_blackbanner_rescue(
        self,
        capture: HeroCaptureState | None = None,
        *,
        location_target: object | str | None = None,
        source_chain: QuestChainInstance | None = None,
        ctx: SystemContext | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance | None:
        if capture is None:
            return None
        hero_id = str(capture.hero_id)
        if not hero_id:
            return None

        existing_id = self._rescue_chain_by_hero_id.get(hero_id)
        if existing_id is not None:
            existing = self.get_chain(existing_id, include_archived=False)
            if existing is not None and existing.chain_type == BLACKBANNER_RESCUE.chain_type and existing.status in _LIVE_CHAIN_STATUSES:
                return existing

        target_info = self._blackbanner_location_target(source_chain, location_target, ctx)
        now = int(sim_now_ms() if now_ms is None else now_ms)
        facts = {
            "captured_hero_id": capture.hero_id,
            "captured_hero_name": capture.hero_name,
            "captor_boss_id": capture.captor_boss_id,
            "captor_boss_name": capture.captor_boss_name,
            "captor_boss_type": capture.captor_boss_type,
            "source_chain_id": capture.source_chain_id,
            "source_chain_type": capture.source_chain_type,
            "rescue_id": f"rescue_{capture.hero_id}",
            "origin_target_id": target_info.entity_id,
            "origin_target_name": target_info.name,
            "origin_target_position": target_info.position,
        }
        chain = self.create_chain(
            BLACKBANNER_RESCUE.chain_type,
            origin_target=location_target if location_target is not None else target_info,
            facts=facts,
            event_bus=event_bus,
            now_ms=now,
        )
        self._rescue_chain_by_hero_id[hero_id] = int(chain.chain_id)
        return chain

    def record_blackbanner_revenge(
        self,
        *,
        boss: object,
        hero: object,
        source_chain: QuestChainInstance | None = None,
        location_target: object | str | None = None,
        ctx: SystemContext | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance | None:
        if hero is None or boss is None or getattr(hero, "is_captured", False):
            return None
        if not self._is_blackbanner_revenge_boss(boss):
            return None

        hero_id = _hero_id(hero, None)
        boss_id = _hero_id(boss, None) or str(getattr(boss, "entity_id", "") or "")
        if not hero_id or not boss_id:
            return None

        pair_key = (str(boss_id), str(hero_id))
        existing_id = self._revenge_chain_by_pair.get(pair_key)
        if existing_id is not None:
            existing = self.get_chain(existing_id, include_archived=False)
            if existing is not None and existing.chain_type == BLACKBANNER_REVENGE.chain_type and existing.status in _LIVE_CHAIN_STATUSES:
                return existing

        target_info = self._blackbanner_location_target(source_chain, location_target, ctx, boss=boss)
        now = int(sim_now_ms() if now_ms is None else now_ms)
        boss_name = str(getattr(boss, "name", "") or "Rusk Blackbanner")
        boss_type = str(getattr(boss, "enemy_type", "") or "bandit_lord")
        fallen_hero_name = _hero_name(hero, "")
        revenge_id = f"revenge_{boss_id}_{hero_id}"
        facts = {
            "boss_target_id": str(boss_id),
            "boss_target_entity_id": str(boss_id),
            "boss_target_name": boss_name,
            "boss_target_position": target_info.position,
            "boss_target_story_name": boss_name,
            "boss_target_phase_id": AVENGE_FALLEN_HERO,
            "boss_target_revealed": True,
            "boss_target_defeated": False,
            "fallen_hero_id": hero_id,
            "fallen_hero_name": fallen_hero_name,
            "revenge_id": revenge_id,
            "revenge_chain_id": revenge_id,
            "target_location_id": target_info.entity_id,
            "target_location_name": target_info.name,
            "target_location_position": target_info.position,
            "source_chain_id": "" if source_chain is None else str(source_chain.chain_id),
            "source_chain_type": "" if source_chain is None else str(source_chain.chain_type),
        }
        chain = self.create_chain(
            BLACKBANNER_REVENGE.chain_type,
            facts=facts,
            event_bus=event_bus,
            now_ms=now,
        )
        self._revenge_chain_by_pair[pair_key] = int(chain.chain_id)
        self._prime_blackbanner_revenge_chain_state(
            boss,
            boss_id=str(boss_id),
            boss_name=boss_name,
            boss_type=boss_type,
            fallen_hero_id=hero_id,
            fallen_hero_name=fallen_hero_name,
            location_target=target_info,
            revenge_chain_id=str(chain.chain_id),
            now_ms=now,
        )
        return chain

    def offer_blackbanner_revenge(
        self,
        boss: object,
        hero: object,
        *,
        source_chain: QuestChainInstance | None = None,
        location_target: object | str | None = None,
        ctx: SystemContext | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance | None:
        return self.record_blackbanner_revenge(
            boss=boss,
            hero=hero,
            source_chain=source_chain,
            location_target=location_target,
            ctx=ctx,
            event_bus=event_bus,
            now_ms=now_ms,
        )

    def get_active_captured_hero_snapshots(self) -> tuple[HeroCaptureState, ...]:
        if not self._captured_heroes:
            return ()
        return tuple(self._captured_heroes.values())

    def get_active_captured_heroes(self) -> tuple[HeroCaptureState, ...]:
        return self.get_active_captured_hero_snapshots()

    def get_active_capture_snapshots(self) -> tuple[HeroCaptureState, ...]:
        return self.get_active_captured_hero_snapshots()

    def get_active_rescue_opportunity_snapshots(self) -> tuple[RescueOpportunitySnapshot, ...]:
        if not self.chains:
            return ()
        opportunities: list[RescueOpportunitySnapshot] = []
        for chain in self.chains:
            if chain.chain_type != BLACKBANNER_RESCUE.chain_type or chain.status not in _LIVE_CHAIN_STATUSES:
                continue
            opportunities.append(self._rescue_snapshot(chain))
        return tuple(opportunities)

    def get_active_rescue_opportunities(self) -> tuple[RescueOpportunitySnapshot, ...]:
        return self.get_active_rescue_opportunity_snapshots()

    def get_active_rescue_views(self) -> tuple[RescueOpportunitySnapshot, ...]:
        return self.get_active_rescue_opportunity_snapshots()

    def get_active_revenge_opportunity_snapshots(self) -> tuple[RevengeOpportunitySnapshot, ...]:
        if not self.chains:
            return ()
        opportunities: list[RevengeOpportunitySnapshot] = []
        for chain in self.chains:
            if chain.chain_type != BLACKBANNER_REVENGE.chain_type or chain.status not in _LIVE_CHAIN_STATUSES:
                continue
            opportunities.append(self._revenge_snapshot(chain))
        return tuple(opportunities)

    def get_active_revenge_opportunities(self) -> tuple[RevengeOpportunitySnapshot, ...]:
        return self.get_active_revenge_opportunity_snapshots()

    def get_active_revenge_views(self) -> tuple[RevengeOpportunitySnapshot, ...]:
        return self.get_active_revenge_opportunity_snapshots()

    def offer_relic_of_the_old_shrine(
        self,
        *,
        ctx: SystemContext | None = None,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        origin_target = self._find_first_target(ctx, preferred_ids=("poi_ancient_ruins",))
        delivery_target = self._find_first_target(ctx, preferred_ids=("poi_shrine", "castle"))
        if delivery_target is None and ctx is not None:
            delivery_target = getattr(ctx, "castle", None)
        return self.create_chain(
            RELIC_OF_THE_OLD_SHRINE.chain_type,
            hero=hero,
            hero_id=hero_id,
            origin_target=origin_target,
            delivery_target=delivery_target,
            event_bus=event_bus if event_bus is not None else getattr(ctx, "event_bus", None),
            now_ms=now_ms,
        )

    def accept_chain(
        self,
        chain_or_id: int | str | QuestChainInstance,
        ctx: SystemContext | None = None,
        *,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> bool:
        chain = self.get_chain(chain_or_id, include_archived=False)
        if chain is None or chain.status != "offered":
            return False

        resolved_hero_id = _hero_id(hero, hero_id)
        if chain.offered_to_hero_id and resolved_hero_id and chain.offered_to_hero_id != resolved_hero_id:
            return False
        if chain.chain_type == BLACKBANNER_RESCUE.chain_type:
            captured_hero_id = str(chain.facts.get("captured_hero_id", "") or "")
            capture_state = self._captured_heroes.get(captured_hero_id)
            if capture_state is None or str(getattr(capture_state, "status", "")) != "captured":
                return False
        if chain.chain_type == BLACKBANNER_REVENGE.chain_type and ctx is not None:
            boss_target_id = str(
                chain.facts.get("boss_target_entity_id", "")
                or chain.facts.get("boss_target_id", "")
                or ""
            )
            boss_target = self._find_target_by_id(ctx, boss_target_id) if boss_target_id else None
            if boss_target is None or not bool(getattr(boss_target, "is_alive", True)):
                return False

        now = int(sim_now_ms() if now_ms is None else now_ms)
        chain.status = "active"
        chain.assigned_hero_id = resolved_hero_id
        chain.accepted_at_ms = now
        chain.current_phase_started_ms = now
        chain.current_phase_index = 0
        definition = self.get_definition(chain.chain_type)
        chain.current_phase_id = str(definition.phases[0].phase_id) if definition.phases else ""
        self._record_history(
            chain,
            event="chain_accepted",
            status="active",
            hero_id=resolved_hero_id,
            now_ms=now,
        )
        self._emit(
            event_bus,
            GameEventType.QUEST_CHAIN_ACCEPTED,
            chain=chain,
            hero=hero,
            hero_id=resolved_hero_id,
            now_ms=now,
        )
        self._record_phase_started(chain, now_ms=now, event_bus=event_bus)
        return True

    def start_chain(
        self,
        chain_type: str,
        *,
        hero: object | None = None,
        hero_id: str | None = None,
        origin_target: object | str | None = None,
        delivery_target: object | str | None = None,
        reward_gold: int | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        chain = self.create_chain(
            chain_type,
            hero=hero,
            hero_id=hero_id,
            origin_target=origin_target,
            delivery_target=delivery_target,
            reward_gold=reward_gold,
            event_bus=event_bus,
            now_ms=now_ms,
        )
        self.accept_chain(chain.chain_id, hero=hero, hero_id=hero_id, event_bus=event_bus, now_ms=now_ms)
        return chain

    def start_relic_of_the_old_shrine(
        self,
        *,
        ctx: SystemContext | None = None,
        hero: object | None = None,
        hero_id: str | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> QuestChainInstance:
        chain = self.offer_relic_of_the_old_shrine(
            ctx=ctx,
            hero=hero,
            hero_id=hero_id,
            event_bus=event_bus,
            now_ms=now_ms,
        )
        self.accept_chain(chain.chain_id, hero=hero, hero_id=hero_id, event_bus=event_bus, now_ms=now_ms)
        return chain

    def abandon_chain(
        self,
        chain_or_id: int | str | QuestChainInstance,
        *,
        event_bus: object | None = None,
        now_ms: int | None = None,
        reason: str = "abandoned",
    ) -> bool:
        return self.fail_chain(chain_or_id, event_bus=event_bus, now_ms=now_ms, reason=reason)

    def fail_chain(
        self,
        chain_or_id: int | str | QuestChainInstance,
        ctx: SystemContext | None = None,
        *,
        event_bus: object | None = None,
        now_ms: int | None = None,
        reason: str = "failed",
    ) -> bool:
        chain = self.get_chain(chain_or_id, include_archived=False)
        if chain is None or chain.status not in _LIVE_CHAIN_STATUSES:
            return False

        now = int(sim_now_ms() if now_ms is None else now_ms)
        chain.status = "failed"
        chain.failed_at_ms = now
        self._record_history(
            chain,
            event="chain_failed",
            status="failed",
            now_ms=now,
            reason=str(reason),
        )
        self._emit(
            event_bus,
            GameEventType.QUEST_CHAIN_FAILED,
            chain=chain,
            now_ms=now,
            reason=str(reason),
        )
        self._cleanup_blackbanner_chain_runtime_state(chain, ctx=ctx, completed=False, reason=str(reason))
        if chain.chain_type == BLACKBANNERS_TOLL.chain_type:
            self._clear_blackbanner_runtime_refs(chain)
        self._archive_chain(chain, failed=True)
        return True

    def complete_chain(
        self,
        chain_or_id: int | str | QuestChainInstance,
        hero: object,
        ctx: SystemContext | None = None,
        *,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> bool:
        chain = self.get_chain(chain_or_id, include_archived=False)
        if chain is None or chain.status != "active":
            return False

        now = int(sim_now_ms() if now_ms is None else now_ms)
        reward = int(chain.reward_gold)
        if reward > 0:
            add_gold = getattr(hero, "add_gold", None)
            if callable(add_gold):
                add_gold(reward)
            else:
                hero.gold = int(getattr(hero, "gold", 0) or 0) + int(reward)

        reward_item_id = str(chain.facts.get("reward_item_id", "") or "")
        if reward_item_id:
            try:
                reward_item = get_item(reward_item_id)
            except Exception:
                reward_item = None
            if reward_item is not None:
                receive_item = getattr(hero, "receive_item", None)
                if callable(receive_item):
                    try:
                        receive_item(reward_item)
                    except Exception:
                        pass

        reward_title = str(chain.facts.get("reward_title", "") or "")
        if reward_title:
            reward_summary = str(chain.facts.get("reward_memory_summary", "") or "")
            subject_name = str(chain.facts.get("boss_target_name", "") or chain.name or "")
            award_title = getattr(hero, "award_title", None)
            if callable(award_title):
                try:
                    award_title(
                        reward_title,
                        now_ms=now,
                        memory_summary=reward_summary,
                        subject_type="boss",
                        subject_id=str(chain.facts.get("boss_target_entity_id", "") or chain.facts.get("boss_target_id", "") or ""),
                        subject_name=subject_name,
                        tags=("title", "victory", "dragon"),
                    )
                except Exception:
                    pass
            else:
                current_title = str(getattr(hero, "current_title", "") or "")
                hero_title = str(getattr(hero, "hero_title", "") or "")
                earned_titles = getattr(hero, "earned_titles", None)
                if not isinstance(earned_titles, list):
                    earned_titles = [] if earned_titles is None else list(earned_titles)
                    try:
                        setattr(hero, "earned_titles", earned_titles)
                    except Exception:
                        pass
                if reward_title not in earned_titles:
                    earned_titles.append(reward_title)
                try:
                    setattr(hero, "current_title", reward_title)
                    setattr(hero, "hero_title", reward_title)
                except Exception:
                    pass
                if callable(getattr(hero, "record_profile_memory", None)):
                    try:
                        hero.record_profile_memory(
                            event_type="title_awarded",
                            sim_time_ms=now,
                            summary=reward_summary or f"Earned title {reward_title}",
                            subject_type="boss",
                            subject_id=str(chain.facts.get("boss_target_entity_id", "") or chain.facts.get("boss_target_id", "") or ""),
                            subject_name=subject_name,
                            tags=("title", "victory", "dragon"),
                            importance=3,
                        )
                    except Exception:
                        pass
        chain.status = "completed"
        chain.completed_at_ms = now
        self._record_history(
            chain,
            event="chain_completed",
            status="completed",
            now_ms=now,
            hero_id=chain.assigned_hero_id,
            reward_gold=reward,
        )
        self._emit(
            event_bus,
            GameEventType.QUEST_CHAIN_COMPLETED,
            chain=chain,
            hero=hero,
            hero_id=chain.assigned_hero_id,
            reward_gold=reward,
            now_ms=now,
        )
        self._cleanup_blackbanner_chain_runtime_state(chain, ctx=ctx, completed=True, reason="completed")
        if chain.chain_type == BLACKBANNERS_TOLL.chain_type:
            self._clear_blackbanner_runtime_refs(chain)
        self._archive_chain(chain, failed=False)
        return True

    # ------------------------------------------------------------------
    # Tick / phase resolution
    # ------------------------------------------------------------------

    def update(self, ctx: SystemContext, dt: float) -> None:
        if not self.chains:
            return
        _ = dt
        event_bus = getattr(ctx, "event_bus", None)
        now = int(sim_now_ms())

        for chain in list(self.chains):
            if chain.status not in _LIVE_CHAIN_STATUSES:
                continue

            definition = self.get_definition(chain.chain_type)
            if chain.current_phase_index >= len(definition.phases):
                hero = _find_hero(ctx.heroes or [], chain.assigned_hero_id)
                if hero is None or not getattr(hero, "is_alive", True):
                    self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="hero_lost")
                else:
                    self.complete_chain(chain, hero, ctx=ctx, event_bus=event_bus, now_ms=now)
                continue

            phase = definition.phases[chain.current_phase_index]
            objective_type = str(phase.objective_type)

            if chain.chain_type == BLACKBANNER_RESCUE.chain_type:
                captured_hero_id = str(chain.facts.get("captured_hero_id", "") or "")
                capture_state = self._captured_heroes.get(captured_hero_id)
                if capture_state is None or str(getattr(capture_state, "status", "")) != "captured":
                    self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="captured_target_missing")
                    continue
                target_info = self._resolve_live_target(chain, phase, ctx, allow_missing=False)
                if target_info is None or target_info.position is None:
                    self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="target_missing")
                    continue
                if chain.status == "offered":
                    continue
                hero = _find_hero(ctx.heroes or [], chain.assigned_hero_id)
                if hero is None or not getattr(hero, "is_alive", True):
                    self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="hero_lost")
                    continue
                if self._hero_reached_target(hero, target_info.position):
                    self.complete_chain(chain, hero, ctx=ctx, event_bus=event_bus, now_ms=now)
                continue

            if chain.chain_type == BLACKBANNER_REVENGE.chain_type:
                boss_target_id = str(
                    chain.facts.get("boss_target_entity_id", "")
                    or chain.facts.get("boss_target_id", "")
                    or ""
                )
                boss_target = self._find_target_by_id(ctx, boss_target_id) if boss_target_id else None
                boss_alive = boss_target is not None and bool(getattr(boss_target, "is_alive", True))
                if chain.status == "offered":
                    if not boss_alive:
                        self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="target_missing")
                    continue
                hero = _find_hero(ctx.heroes or [], chain.assigned_hero_id)
                if hero is None or not getattr(hero, "is_alive", True):
                    self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="hero_lost")
                    continue
                if not boss_alive:
                    self.complete_chain(chain, hero, ctx=ctx, event_bus=event_bus, now_ms=now)
                continue

            hero = _find_hero(ctx.heroes or [], chain.assigned_hero_id)
            if hero is None or not getattr(hero, "is_alive", True):
                self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="hero_lost")
                continue

            allow_missing = objective_type in (INTERCEPT_TOLL_TAKER, ASSAULT_GATE, SLAY_BLACKBANNER, SLAY_NAMED_BOSS)
            target_info = self._resolve_live_target(chain, phase, ctx, allow_missing=allow_missing)
            if target_info is None:
                self.fail_chain(chain, ctx=ctx, event_bus=event_bus, now_ms=now, reason="target_missing")
                continue

            if objective_type == SCOUT_LOCATION:
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == COLLECT_ITEM:
                if not chain.facts.get("relic_scouted", False):
                    continue
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == DELIVER_ITEM:
                if not chain.facts.get("relic_collected", False):
                    continue
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == SCOUT_FORTRESS:
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == INTERCEPT_TOLL_TAKER:
                if self._blackbanner_enemy_defeated(chain, kind="elite", ctx=ctx):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == ASSAULT_GATE:
                if chain.facts.get("elite_target_defeated", False) and self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == SLAY_BLACKBANNER:
                if self._blackbanner_enemy_defeated(chain, kind="boss", ctx=ctx):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == PREPARE_HUNT:
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == SLAY_NAMED_BOSS:
                if chain.chain_type == ASHWINGS_HOARD.chain_type and self._ashwing_enemy_defeated(chain, ctx=ctx):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == CLAIM_REWARD:
                if chain.facts.get("boss_target_defeated", False) and self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif objective_type == CLAIM_HOARD:
                if chain.facts.get("boss_target_defeated", False) and self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------

    def get_definition(self, chain_type: str) -> QuestChainDef:
        return get_chain_def(chain_type)

    def get_chain(
        self,
        chain_or_id: int | str | QuestChainInstance,
        *,
        include_archived: bool = True,
    ) -> QuestChainInstance | None:
        if isinstance(chain_or_id, QuestChainInstance):
            return chain_or_id
        chain_id = int(chain_or_id)
        for chain in self.chains:
            if int(chain.chain_id) == chain_id:
                return chain
        if include_archived:
            for chain in self.completed_chains:
                if int(chain.chain_id) == chain_id:
                    return chain
            for chain in self.failed_chains:
                if int(chain.chain_id) == chain_id:
                    return chain
        return None

    def get_active_chain_snapshots(self) -> tuple[QuestChainSnapshot, ...]:
        if not self.chains:
            return ()
        return tuple(self._snapshot_chain(chain) for chain in self.chains)

    def get_active_chain_views(self) -> tuple[QuestChainSnapshot, ...]:
        return self.get_active_chain_snapshots()

    def get_active_chains(self) -> tuple[QuestChainSnapshot, ...]:
        return self.get_active_chain_snapshots()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _complete_phase(
        self,
        chain: QuestChainInstance,
        phase: QuestPhaseDef,
        hero: object,
        target_info: _TargetInfo,
        ctx: SystemContext,
    ) -> None:
        now = int(sim_now_ms())
        if phase.objective_type == SCOUT_LOCATION:
            if chain.chain_type == RELIC_OF_THE_OLD_SHRINE.chain_type:
                chain.facts["relic_scouted"] = True
                chain.facts["relic_scouted_at_ms"] = now
            elif chain.chain_type == ASHWINGS_HOARD.chain_type:
                chain.facts["dragon_cave_scouted"] = True
                chain.facts["dragon_cave_scouted_at_ms"] = now
                chain.facts["boss_target_revealed"] = True
                self._reveal_ashwing(chain, ctx, event_bus=getattr(ctx, "event_bus", None), now_ms=now)
        elif phase.objective_type == COLLECT_ITEM:
            chain.facts["relic_collected"] = True
            chain.facts["relic_carried"] = True
            chain.facts["relic_carried_by_hero_id"] = chain.assigned_hero_id
            chain.facts["relic_collected_at_ms"] = now
        elif phase.objective_type == DELIVER_ITEM:
            chain.facts["relic_delivered"] = True
            chain.facts["relic_delivered_at_ms"] = now
        elif phase.objective_type == PREPARE_HUNT:
            chain.facts["prep_target_prepared"] = True
            chain.facts["prep_target_prepared_at_ms"] = now
            chain.facts["boss_target_weakness_known"] = True

        self._record_history(
            chain,
            event="phase_completed",
            phase_id=str(phase.phase_id),
            phase_title=str(phase.title),
            status="completed",
            hero_id=chain.assigned_hero_id,
            target_id=target_info.entity_id,
            target_name=target_info.name,
            target_position=target_info.position,
            now_ms=now,
        )
        if phase.objective_type == SCOUT_FORTRESS:
            chain.facts["boss_target_revealed"] = True
            self._reveal_blackbanner_boss(chain, ctx, event_bus=getattr(ctx, "event_bus", None), now_ms=now)
        elif phase.objective_type == INTERCEPT_TOLL_TAKER:
            chain.facts["elite_target_defeated"] = True
        elif phase.objective_type == SLAY_BLACKBANNER:
            chain.facts["boss_target_defeated"] = True
        elif phase.objective_type == SLAY_NAMED_BOSS and chain.chain_type == ASHWINGS_HOARD.chain_type:
            chain.facts["boss_target_defeated"] = True
            chain.facts["boss_target_defeated_at_ms"] = now
            chain.facts["boss_target_defeated_by_hero_id"] = chain.assigned_hero_id
        elif phase.objective_type == CLAIM_HOARD and chain.chain_type == ASHWINGS_HOARD.chain_type:
            chain.facts["hoard_target_claimed"] = True
            chain.facts["hoard_target_claimed_at_ms"] = now
        self._emit(
            getattr(ctx, "event_bus", None),
            GameEventType.QUEST_CHAIN_PHASE_COMPLETED,
            chain=chain,
            hero=hero,
            phase=phase,
            target_info=target_info,
            now_ms=now,
        )

        if phase.objective_type in (DELIVER_ITEM, CLAIM_REWARD, CLAIM_HOARD):
            self.complete_chain(chain, hero, event_bus=getattr(ctx, "event_bus", None), now_ms=now)
            return

        self._advance_phase(chain, ctx, now_ms=now)

    def _advance_phase(self, chain: QuestChainInstance, ctx: SystemContext, *, now_ms: int) -> None:
        definition = self.get_definition(chain.chain_type)
        chain.current_phase_index += 1
        if chain.current_phase_index >= len(definition.phases):
            return
        phase = definition.phases[chain.current_phase_index]
        chain.current_phase_id = str(phase.phase_id)
        chain.current_phase_started_ms = now_ms
        self._record_phase_started(chain, now_ms=now_ms, event_bus=getattr(ctx, "event_bus", None))

    def _record_phase_started(
        self,
        chain: QuestChainInstance,
        *,
        now_ms: int,
        event_bus: object | None,
    ) -> None:
        definition = self.get_definition(chain.chain_type)
        if chain.current_phase_index >= len(definition.phases):
            return
        phase = definition.phases[chain.current_phase_index]
        target_info = self._snapshot_target(chain, phase)
        self._record_history(
            chain,
            event="phase_started",
            phase_id=str(phase.phase_id),
            phase_title=str(phase.title),
            status="active",
            hero_id=chain.assigned_hero_id,
            target_id=target_info.entity_id,
            target_name=target_info.name,
            target_position=target_info.position,
            now_ms=now_ms,
        )
        self._emit(
            event_bus,
            GameEventType.QUEST_CHAIN_PHASE_STARTED,
            chain=chain,
            phase=phase,
            target_info=target_info,
            now_ms=now_ms,
        )

    def _snapshot_chain(self, chain: QuestChainInstance) -> QuestChainSnapshot:
        definition = self.get_definition(chain.chain_type)
        phases: list[QuestChainPhaseSnapshot] = []
        for index, phase in enumerate(definition.phases):
            phase_status = self._phase_status(chain, index)
            target_info = self._snapshot_target(chain, phase)
            phase_history = tuple(
                self._history_summary(record)
                for record in chain.history
                if str(record.get("phase_id", "")) == str(phase.phase_id)
            )
            phases.append(
                QuestChainPhaseSnapshot(
                    phase_id=str(phase.phase_id),
                    title=str(phase.title),
                    objective_type=str(phase.objective_type),
                    status=str(phase_status),
                    assigned_hero_id=chain.assigned_hero_id,
                    target_id=target_info.entity_id,
                    target_name=target_info.name,
                    target_position=target_info.position,
                    history=phase_history,
                )
            )

        if definition.phases:
            current_phase = definition.phases[min(chain.current_phase_index, len(definition.phases) - 1)]
            current_target = self._snapshot_target(chain, current_phase)
            current_phase_id = str(current_phase.phase_id)
            current_phase_title = str(current_phase.title)
            current_objective_type = str(current_phase.objective_type)
            target_id = current_target.entity_id
            target_name = current_target.name
            target_position = current_target.position
        else:
            current_phase_id = ""
            current_phase_title = ""
            current_objective_type = ""
            target_id = ""
            target_name = ""
            target_position = None

        return QuestChainSnapshot(
            chain_id=int(chain.chain_id),
            chain_type=str(chain.chain_type),
            name=str(chain.name),
            status=str(chain.status),
            assigned_hero_id=chain.assigned_hero_id,
            current_phase_id=current_phase_id,
            current_phase_title=current_phase_title,
            current_objective_type=current_objective_type,
            target_id=target_id,
            target_name=target_name,
            target_position=target_position,
            phases=tuple(phases),
            history=tuple(self._history_summary(record) for record in chain.history),
        )

    def _phase_status(self, chain: QuestChainInstance, index: int) -> str:
        if chain.status == "offered":
            return "offered" if index == 0 else "upcoming"
        if chain.status == "active":
            if index < chain.current_phase_index:
                return "completed"
            if index == chain.current_phase_index:
                return "active"
            return "upcoming"
        if chain.status == "completed":
            return "completed" if index <= chain.current_phase_index else "upcoming"
        if chain.status == "failed":
            return "failed" if index <= chain.current_phase_index else "upcoming"
        return "upcoming"

    def _snapshot_target(self, chain: QuestChainInstance, phase: QuestPhaseDef) -> _TargetInfo:
        prefix = str(phase.target_ref)
        return _TargetInfo(
            entity_id=str(chain.facts.get(f"{prefix}_id", "") or ""),
            name=str(chain.facts.get(f"{prefix}_name", "") or ""),
            position=chain.facts.get(f"{prefix}_position", None),
        )

    def _resolve_live_target(
        self,
        chain: QuestChainInstance,
        phase: QuestPhaseDef,
        ctx: SystemContext,
        *,
        allow_missing: bool = False,
    ) -> _TargetInfo | None:
        snapshot_target = self._snapshot_target(chain, phase)
        live_entity_id = str(chain.facts.get(f"{phase.target_ref}_entity_id", "") or "")
        lookup_id = live_entity_id or snapshot_target.entity_id
        if lookup_id:
            found = self._find_target_by_id(ctx, lookup_id)
            if found is None:
                if chain.chain_type == ASHWINGS_HOARD.chain_type and phase.objective_type == CLAIM_HOARD and snapshot_target.position is not None:
                    return snapshot_target
                return snapshot_target if allow_missing else None
            return self._capture_target(found)
        if snapshot_target.position is not None:
            return snapshot_target
        return None

    def _find_target_by_id(self, ctx: SystemContext, target_id: str) -> object | None:
        if not target_id:
            return None
        for source in (
            getattr(ctx, "enemies", None) or (),
            getattr(ctx, "pois", None) or (),
            getattr(ctx, "buildings", None) or (),
            (getattr(ctx, "castle", None),),
        ):
            for obj in source:
                if obj is None:
                    continue
                if str(getattr(obj, "entity_id", "")) == str(target_id):
                    return obj
        return None

    def _find_first_target(
        self,
        ctx: SystemContext | None,
        *,
        preferred_ids: tuple[str, ...],
    ) -> object | None:
        if ctx is None:
            return None
        for preferred in preferred_ids:
            for collection in (
                getattr(ctx, "pois", None) or (),
                getattr(ctx, "buildings", None) or (),
                (getattr(ctx, "castle", None),),
            ):
                for obj in collection:
                    if obj is None:
                        continue
                    obj_type = str(getattr(obj, "poi_type", getattr(obj, "building_type", "")) or "")
                    if obj_type == preferred:
                        return obj
                    entity_id = str(getattr(obj, "entity_id", "") or "")
                    if entity_id == preferred:
                        return obj
        return None

    def _ensure_blackbanner_event_hooks(self, event_bus: object | None) -> None:
        if event_bus is None or event_bus is self._event_bus:
            return
        subscribe = getattr(event_bus, "subscribe", None)
        if not callable(subscribe):
            self._event_bus = event_bus
            return
        try:
            subscribe(GameEventType.ENEMY_KILLED, self._on_blackbanner_enemy_killed_event)
            subscribe(GameEventType.BOSS_DEFEATED, self._on_blackbanner_boss_defeated_event)
        except Exception:
            pass
        self._event_bus = event_bus

    def _on_blackbanner_enemy_killed_event(self, event: dict) -> None:
        self._handle_blackbanner_defeat_event(event, kind="elite")

    def _on_blackbanner_boss_defeated_event(self, event: dict) -> None:
        self._handle_blackbanner_defeat_event(event, kind="boss")

    def _handle_blackbanner_defeat_event(self, event: dict, *, kind: str) -> None:
        if kind not in {"elite", "boss"}:
            return
        if not isinstance(event, dict):
            return
        entity_id_key = "enemy_id" if kind == "elite" else "boss_id"
        entity_name_key = "enemy_name" if kind == "elite" else "name"
        entity_id = str(event.get(entity_id_key, "") or "")
        entity_name = str(event.get(entity_name_key, "") or "")
        hero_id = str(event.get("hero_id", "") or "")
        hero_name = str(event.get("hero", "") or "")
        at_ms = int(event.get("time_ms", 0) or sim_now_ms())
        fact_prefix = "elite_target" if kind == "elite" else "boss_target"
        for chain in self.chains:
            if chain.chain_type != BLACKBANNERS_TOLL.chain_type or chain.status != "active":
                continue
            live_entity_id = str(chain.facts.get(f"{fact_prefix}_entity_id", "") or "")
            story_name = str(chain.facts.get(f"{fact_prefix}_name", "") or "")
            if entity_id and live_entity_id and entity_id != live_entity_id:
                continue
            if not entity_id and entity_name and story_name and entity_name != story_name:
                continue
            chain.facts[f"{fact_prefix}_defeated"] = True
            chain.facts[f"{fact_prefix}_defeated_at_ms"] = at_ms
            if hero_id:
                chain.facts[f"{fact_prefix}_defeated_by_hero_id"] = hero_id
            if hero_name:
                chain.facts[f"{fact_prefix}_defeated_by_hero_name"] = hero_name

    def _active_blackbanner_chain_for_hero(self, hero_id: str) -> QuestChainInstance | None:
        if not hero_id:
            return None
        for chain in self.chains:
            if chain.chain_type != BLACKBANNERS_TOLL.chain_type:
                continue
            if chain.status not in _LIVE_CHAIN_STATUSES:
                continue
            if str(chain.assigned_hero_id or "") == str(hero_id):
                return chain
        return None

    @staticmethod
    def _is_blackbanner_family_killer(killer: object) -> bool:
        enemy_type = str(getattr(killer, "enemy_type", "") or "")
        enemy_name = str(getattr(killer, "name", "") or "")
        elite_story_name = str(getattr(killer, "elite_story_name", "") or "")
        return (
            (enemy_type == "bandit_lord" and enemy_name == "Rusk Blackbanner")
            or elite_story_name == BLACKBANNER_TOLL_TAKER_STORY_NAME
        )

    @staticmethod
    def _is_blackbanner_revenge_boss(boss: object) -> bool:
        boss_type = str(getattr(boss, "enemy_type", "") or "")
        boss_name = str(getattr(boss, "name", "") or "")
        return boss_type == "bandit_lord" and boss_name == "Rusk Blackbanner"

    def _blackbanner_location_target(
        self,
        source_chain: QuestChainInstance | None,
        location_target: object | str | None,
        ctx: SystemContext | None,
        *,
        boss: object | None = None,
    ) -> _TargetInfo:
        if location_target is not None:
            return self._capture_target(location_target)

        if source_chain is not None:
            origin_info = _TargetInfo(
                entity_id=str(source_chain.facts.get("fortress_target_entity_id", "") or ""),
                name=str(source_chain.facts.get("fortress_target_name", "") or ""),
                position=source_chain.facts.get("fortress_target_position", None),
            )
            if origin_info.entity_id or origin_info.name or origin_info.position is not None:
                return origin_info

        if boss is not None:
            boss_pos = self._entity_position(boss)
            return _TargetInfo(
                entity_id=str(getattr(boss, "entity_id", "") or ""),
                name=str(getattr(boss, "name", "") or ""),
                position=boss_pos,
            )

        if ctx is not None:
            target = self._find_blackbanner_fortress_target(ctx)
            if target is not None:
                return self._capture_target(target)

        return _TargetInfo(
            entity_id="poi_bandit_fortress",
            name="Bandit Fortress",
            position=None,
        )

    def _prime_blackbanner_revenge_chain_state(
        self,
        boss: object,
        *,
        boss_id: str,
        boss_name: str,
        boss_type: str,
        fallen_hero_id: str,
        fallen_hero_name: str,
        location_target: _TargetInfo,
        revenge_chain_id: str,
        now_ms: int,
    ) -> None:
        memory = BossKillMemory(
            boss_id=str(boss_id),
            boss_name=str(boss_name),
            boss_type=str(boss_type),
            fallen_hero_id=str(fallen_hero_id),
            fallen_hero_name=str(fallen_hero_name),
            location_id=str(location_target.entity_id or ""),
            location_name=str(location_target.name or ""),
            killed_at_ms=int(now_ms),
            revenge_chain_id=str(revenge_chain_id),
            status="remembered",
        )
        snapshot = RevengeOpportunitySnapshot(
            revenge_id=str(revenge_chain_id or f"revenge_{boss_id}_{fallen_hero_id}"),
            boss_id=str(boss_id),
            boss_name=str(boss_name),
            boss_type=str(boss_type),
            fallen_hero_id=str(fallen_hero_id),
            fallen_hero_name=str(fallen_hero_name),
            target_location_id=str(location_target.entity_id or ""),
            target_location_name=str(location_target.name or ""),
            current_phase_id=AVENGE_FALLEN_HERO,
            current_phase_title="Avenge the Fallen",
            revenge_chain_id=str(revenge_chain_id or f"revenge_{boss_id}_{fallen_hero_id}"),
            status="active",
            offered_at_ms=int(now_ms),
        )
        setattr(boss, "_wk142_blackbanner_kill_memory", memory)
        setattr(boss, "_wk142_blackbanner_revenge_snapshot", snapshot)
        setattr(boss, "blackbanner_revenge_chain_id", str(revenge_chain_id))
        setattr(boss, "blackbanner_revenge_chain_status", "active")
        setattr(boss, "blackbanner_revenge_boss_id", str(boss_id))
        setattr(boss, "blackbanner_revenge_boss_name", str(boss_name))
        setattr(boss, "blackbanner_revenge_boss_type", str(boss_type))
        setattr(boss, "blackbanner_revenge_fallen_hero_id", str(fallen_hero_id))
        setattr(boss, "blackbanner_revenge_fallen_hero_name", str(fallen_hero_name))
        setattr(boss, "blackbanner_revenge_location_id", str(location_target.entity_id or ""))
        setattr(boss, "blackbanner_revenge_location_name", str(location_target.name or ""))
        setattr(boss, "blackbanner_revenge_current_phase_id", AVENGE_FALLEN_HERO)
        setattr(boss, "blackbanner_revenge_current_phase_title", "Avenge the Fallen")
        setattr(boss, "blackbanner_revenge_offered_at_ms", int(now_ms))

    def _attach_blackbanner_kill_hook(
        self,
        enemy: object,
        *,
        ctx: SystemContext | None,
        event_bus: object | None,
    ) -> None:
        add_hook = getattr(enemy, "add_hero_killed_hook", None)
        if not callable(add_hook):
            return
        if bool(getattr(enemy, "_wk142_blackbanner_kill_hook_attached", False)):
            return

        def _on_hero_killed(hero: object, *, killer: object | None = None, now_ms: int | None = None) -> None:
            self._on_blackbanner_hero_killed(
                hero,
                killer=killer or enemy,
                ctx=ctx,
                event_bus=event_bus,
                now_ms=now_ms,
            )

        add_hook(_on_hero_killed)
        setattr(enemy, "_wk142_blackbanner_kill_hook_attached", True)

    def _on_blackbanner_hero_killed(
        self,
        hero: object,
        *,
        killer: object,
        ctx: SystemContext | None,
        event_bus: object | None,
        now_ms: int | None = None,
    ) -> None:
        hero_id = _hero_id(hero, None)
        if not hero_id:
            return
        killer_name = str(getattr(killer, "name", "") or "")
        killer_type = str(getattr(killer, "enemy_type", "") or "")
        if not self._is_blackbanner_family_killer(killer):
            return

        active_chain = self._active_blackbanner_chain_for_hero(hero_id)
        if active_chain is not None and active_chain.assigned_hero_id == hero_id:
            if killer_type == "bandit_lord" or killer_name == BLACKBANNER_TOLL_TAKER_STORY_NAME:
                capture_target = self._blackbanner_location_target(active_chain, None, ctx)
                self.capture_blackbanner_hero(
                    hero,
                    killer=killer,
                    source_chain=active_chain,
                    location_target=capture_target,
                    ctx=ctx,
                    event_bus=event_bus,
                    now_ms=now_ms,
                )
                return

        if killer_type == "bandit_lord" and killer_name == "Rusk Blackbanner":
            self.record_blackbanner_revenge(
                boss=killer,
                hero=hero,
                source_chain=active_chain,
                location_target=self._blackbanner_location_target(active_chain, None, ctx, boss=killer),
                ctx=ctx,
                event_bus=event_bus,
                now_ms=now_ms,
            )

    def _rescue_snapshot(self, chain: QuestChainInstance) -> RescueOpportunitySnapshot:
        captured_hero_id = str(chain.facts.get("captured_hero_id", "") or "")
        definition = self.get_definition(chain.chain_type)
        phase = definition.phases[min(chain.current_phase_index, len(definition.phases) - 1)] if definition.phases else None
        current_phase_title = str(phase.title if phase is not None else "")
        return RescueOpportunitySnapshot(
            rescue_id=str(chain.facts.get("rescue_id", "") or f"rescue_{captured_hero_id or chain.chain_id}"),
            captured_hero_id=captured_hero_id,
            captured_hero_name=str(chain.facts.get("captured_hero_name", "") or ""),
            captor_boss_id=str(chain.facts.get("captor_boss_id", "") or ""),
            captor_boss_name=str(chain.facts.get("captor_boss_name", "") or ""),
            captor_boss_type=str(chain.facts.get("captor_boss_type", "") or ""),
            target_location_id=str(chain.facts.get("origin_target_id", "") or ""),
            target_location_name=str(chain.facts.get("origin_target_name", "") or ""),
            current_phase_id=str(chain.current_phase_id or ""),
            current_phase_title=current_phase_title,
            source_chain_id=str(chain.facts.get("source_chain_id", "") or ""),
            source_chain_type=str(chain.facts.get("source_chain_type", "") or ""),
            status=str(chain.status),
            offered_at_ms=int(chain.offered_at_ms or 0),
        )

    def _revenge_snapshot(self, chain: QuestChainInstance) -> RevengeOpportunitySnapshot:
        boss_target_id = str(chain.facts.get("boss_target_id", "") or chain.facts.get("boss_target_entity_id", "") or "")
        definition = self.get_definition(chain.chain_type)
        phase = definition.phases[min(chain.current_phase_index, len(definition.phases) - 1)] if definition.phases else None
        current_phase_title = str(phase.title if phase is not None else "")
        return RevengeOpportunitySnapshot(
            revenge_id=str(chain.facts.get("revenge_id", "") or chain.facts.get("revenge_chain_id", "") or f"revenge_{boss_target_id or chain.chain_id}"),
            boss_id=boss_target_id,
            boss_name=str(chain.facts.get("boss_target_name", "") or ""),
            boss_type=str(chain.facts.get("boss_target_story_name", "") or chain.facts.get("boss_target_type", "") or ""),
            fallen_hero_id=str(chain.facts.get("fallen_hero_id", "") or ""),
            fallen_hero_name=str(chain.facts.get("fallen_hero_name", "") or ""),
            target_location_id=str(chain.facts.get("target_location_id", "") or ""),
            target_location_name=str(chain.facts.get("target_location_name", "") or ""),
            current_phase_id=str(chain.current_phase_id or ""),
            current_phase_title=current_phase_title,
            revenge_chain_id=str(chain.facts.get("revenge_chain_id", "") or ""),
            status=str(chain.status),
            offered_at_ms=int(chain.offered_at_ms or 0),
        )

    def _clear_blackbanner_rescue_state(
        self,
        chain: QuestChainInstance,
        *,
        ctx: SystemContext | None,
        release_captive: bool,
    ) -> None:
        hero_id = str(chain.facts.get("captured_hero_id", "") or "")
        if hero_id:
            self._rescue_chain_by_hero_id.pop(hero_id, None)
        if not release_captive:
            return
        capture = self._captured_heroes.pop(hero_id, None)
        if capture is None or ctx is None:
            return
        hero = _find_hero(ctx.heroes or [], hero_id)
        if hero is None:
            return
        try:
            hero.release_capture(rescued_at_ms=int(chain.completed_at_ms or chain.failed_at_ms or sim_now_ms()))
        except Exception:
            pass

    def _clear_blackbanner_revenge_state_for_chain(
        self,
        chain: QuestChainInstance,
        *,
        ctx: SystemContext | None,
    ) -> None:
        boss_id = str(chain.facts.get("boss_target_entity_id", "") or chain.facts.get("boss_target_id", "") or "")
        hero_id = str(chain.facts.get("fallen_hero_id", "") or "")
        if boss_id and hero_id:
            self._revenge_chain_by_pair.pop((boss_id, hero_id), None)
        if ctx is None or not boss_id:
            return
        boss = self._find_target_by_id(ctx, boss_id)
        if boss is None:
            return
        for attr in (
            "_wk142_blackbanner_kill_memory",
            "_wk142_blackbanner_revenge_snapshot",
            "blackbanner_revenge_chain_id",
            "blackbanner_revenge_chain_status",
            "blackbanner_revenge_boss_id",
            "blackbanner_revenge_boss_name",
            "blackbanner_revenge_boss_type",
            "blackbanner_revenge_fallen_hero_id",
            "blackbanner_revenge_fallen_hero_name",
            "blackbanner_revenge_location_id",
            "blackbanner_revenge_location_name",
            "blackbanner_revenge_current_phase_id",
            "blackbanner_revenge_current_phase_title",
            "blackbanner_revenge_offered_at_ms",
        ):
            if hasattr(boss, attr):
                try:
                    delattr(boss, attr)
                except Exception:
                    try:
                        setattr(boss, attr, "")
                    except Exception:
                        pass

    def _cleanup_blackbanner_chain_runtime_state(
        self,
        chain: QuestChainInstance,
        *,
        ctx: SystemContext | None,
        completed: bool,
        reason: str,
    ) -> None:
        if chain.chain_type == BLACKBANNER_RESCUE.chain_type:
            release_captive = bool(completed or reason in {"target_missing", "captured_target_missing", "target_lost", "invalid_target"})
            self._clear_blackbanner_rescue_state(chain, ctx=ctx, release_captive=release_captive)
            return
        if chain.chain_type == BLACKBANNER_REVENGE.chain_type:
            self._clear_blackbanner_revenge_state_for_chain(chain, ctx=ctx)
            return
        if chain.chain_type == BLACKBANNERS_TOLL.chain_type:
            self._clear_blackbanner_runtime_refs(chain)

    def _blackbanner_base_facts(
        self,
        *,
        chain_id: int,
        fortress_target: object | None,
        reward_target: object | None,
        now_ms: int,
    ) -> dict[str, object]:
        fortress_info = self._capture_target(fortress_target)
        fortress_position = fortress_info.position
        reward_info = self._capture_target(reward_target)
        if fortress_position is None:
            fortress_position = reward_info.position
        gate_position = self._offset_position(fortress_position, 2.0, 0.0) if fortress_position is not None else None
        elite_position = self._offset_position(fortress_position, 1.5, -0.5) if fortress_position is not None else gate_position
        boss_position = self._offset_position(fortress_position, 4.0, 1.5) if fortress_position is not None else gate_position
        return {
            "fortress_target_id": "poi_bandit_fortress",
            "fortress_target_entity_id": fortress_info.entity_id,
            "fortress_target_name": fortress_info.name or "Bandit Fortress",
            "fortress_target_position": fortress_position,
            "fortress_target_story_name": fortress_info.name or "Bandit Fortress",
            "fortress_target_revealed_at_ms": now_ms,
            "elite_target_id": "elite_blackbanner_toll_taker",
            "elite_target_entity_id": "",
            "elite_target_name": BLACKBANNER_TOLL_TAKER_STORY_NAME,
            "elite_target_position": elite_position,
            "elite_target_story_name": BLACKBANNER_TOLL_TAKER_STORY_NAME,
            "elite_target_phase_id": INTERCEPT_TOLL_TAKER,
            "elite_target_spawn_key": f"blackbanner_toll:{int(chain_id)}:toll_taker",
            "elite_target_defeated": False,
            "gate_target_id": "gate_blackbanner",
            "gate_target_name": "Blackbanner Gate",
            "gate_target_position": gate_position,
            "gate_target_story_name": "Blackbanner Gate",
            "boss_target_id": "",
            "boss_target_entity_id": "",
            "boss_target_name": "",
            "boss_target_position": boss_position,
            "boss_target_story_name": "Rusk Blackbanner",
            "boss_target_phase_id": SLAY_BLACKBANNER,
            "boss_target_spawn_key": f"blackbanner_toll:{int(chain_id)}:rusk",
            "boss_target_revealed": False,
            "boss_target_defeated": False,
            "reward_target_id": reward_info.entity_id or "castle",
            "reward_target_name": reward_info.name or "Castle",
            "reward_target_position": reward_info.position,
            "reward_target_story_name": reward_info.name or "Castle",
        }

    def _ashwing_base_facts(
        self,
        *,
        chain_id: int,
        dragon_cave_target: object | None,
        prep_target: object | None,
        now_ms: int,
    ) -> dict[str, object]:
        cave_info = self._capture_target(dragon_cave_target)
        cave_position = cave_info.position
        prep_info = self._capture_target(prep_target)
        prep_position = prep_info.position
        if prep_position is None and cave_position is not None:
            prep_position = self._offset_position(cave_position, 1.5, -0.5)
        hoard_position = cave_position if cave_position is not None else prep_position
        if hoard_position is None:
            hoard_position = (0.0, 0.0)
        boss_position = cave_position if cave_position is not None else hoard_position
        return {
            "dragon_cave_target_id": cave_info.entity_id or "poi_dragon_cave",
            "dragon_cave_target_entity_id": cave_info.entity_id,
            "dragon_cave_target_name": cave_info.name or "Dragon Cave",
            "dragon_cave_target_position": cave_position,
            "dragon_cave_target_story_name": cave_info.name or "Dragon Cave",
            "dragon_cave_scouted": False,
            "dragon_cave_scouted_at_ms": 0,
            "prep_target_id": prep_info.entity_id or "prep_ashwing_fire",
            "prep_target_entity_id": prep_info.entity_id,
            "prep_target_name": prep_info.name or "Prepare at the Shrine",
            "prep_target_position": prep_position,
            "prep_target_story_name": prep_info.name or "Prepare at the Shrine",
            "prep_target_prepared": False,
            "prep_target_prepared_at_ms": 0,
            "boss_target_id": "boss_ashwing",
            "boss_target_entity_id": "",
            "boss_target_name": "",
            "boss_target_position": boss_position,
            "boss_target_story_name": ASHWING_THE_RED_NAME,
            "boss_target_phase_id": SLAY_ASHWING,
            "boss_target_spawn_key": f"ashwing_hoard:{int(chain_id)}:ashwing",
            "boss_target_revealed": False,
            "boss_target_revealed_at_ms": 0,
            "boss_target_defeated": False,
            "boss_target_defeated_at_ms": 0,
            "hoard_target_id": "hoard_ashwing",
            "hoard_target_entity_id": "",
            "hoard_target_name": ASHWINGS_HOARD_NAME,
            "hoard_target_position": hoard_position,
            "hoard_target_story_name": ASHWINGS_HOARD_NAME,
            "hoard_target_claimed": False,
            "hoard_target_claimed_at_ms": 0,
            "reward_item_id": "dragonscale_armor",
            "reward_item_name": "Dragonscale Armor",
            "reward_title": "Ashwing-Bane",
            "reward_memory_summary": f"Claimed {ASHWINGS_HOARD_NAME}",
            "boss_target_weakness_name": "Ashwing's fire",
            "boss_target_weakness_detail": "Prepare at the shrine before the hunt",
            "ashwing_revealed_at_ms": now_ms,
        }

    def _find_blackbanner_fortress_target(self, ctx: SystemContext | None) -> object | None:
        if ctx is None:
            return None
        target = self._find_first_target(ctx, preferred_ids=("poi_bandit_fortress", "bandit_camp"))
        if target is not None:
            return target
        for obj in list(getattr(ctx, "buildings", None) or ()) + list(getattr(ctx, "pois", None) or ()) + [getattr(ctx, "castle", None)]:
            if obj is None:
                continue
            if str(getattr(obj, "building_type", "")) == "bandit_camp":
                return obj
            if bool(getattr(obj, "is_lair", False)) and str(getattr(obj, "building_type", "")) == "bandit_camp":
                return obj
        return None

    def _spawn_blackbanner_toll_taker(
        self,
        chain: QuestChainInstance,
        *,
        ctx: SystemContext | None,
        event_bus: object | None,
        now_ms: int | None,
    ) -> object | None:
        if ctx is None:
            return None
        existing_id = str(chain.facts.get("elite_target_entity_id", "") or "")
        if existing_id:
            existing = self._find_target_by_id(ctx, existing_id)
            if existing is not None:
                self._attach_blackbanner_kill_hook(
                    existing,
                    ctx=ctx,
                    event_bus=event_bus,
                )
                return existing
        fortress_position = chain.facts.get("fortress_target_position", None)
        if fortress_position is None:
            fortress_target = self._find_blackbanner_fortress_target(ctx)
            fortress_position = self._entity_position(fortress_target) if fortress_target is not None else None
        if fortress_position is None:
            fortress_position = (0.0, 0.0)
        elite_position = self._offset_position(fortress_position, 1.5, -0.5) or fortress_position
        elite = Bandit(float(elite_position[0]), float(elite_position[1]))
        ctx.enemies.append(elite)
        designate_blackbanner_toll_taker(
            elite,
            chain_id=chain.chain_id,
            now_ms=now_ms,
            nearby_enemies=tuple(ctx.enemies),
        )
        chain.facts["elite_target_entity_id"] = str(elite.entity_id)
        chain.facts["elite_target_name"] = str(getattr(elite, "elite_story_name", elite.name) or BLACKBANNER_TOLL_TAKER_STORY_NAME)
        chain.facts["elite_target_position"] = (float(elite.x), float(elite.y))
        chain.facts["elite_target_spawned_at_ms"] = int(sim_now_ms() if now_ms is None else now_ms)
        self._attach_blackbanner_kill_hook(elite, ctx=ctx, event_bus=event_bus)
        return elite

    def _reveal_blackbanner_boss(
        self,
        chain: QuestChainInstance,
        ctx: SystemContext | None,
        *,
        event_bus: object | None,
        now_ms: int,
    ) -> object | None:
        if ctx is None:
            return None
        existing_id = str(chain.facts.get("boss_target_entity_id", "") or "")
        if existing_id:
            existing = self._find_target_by_id(ctx, existing_id)
            if existing is not None:
                self._attach_blackbanner_kill_hook(
                    existing,
                    ctx=ctx,
                    event_bus=event_bus,
                )
                return existing
        boss_position = chain.facts.get("boss_target_position", None)
        if boss_position is None:
            fortress_position = chain.facts.get("fortress_target_position", None)
            if fortress_position is not None:
                boss_position = self._offset_position(fortress_position, 4.0, 1.5)
        if boss_position is None:
            boss_position = (0.0, 0.0)
        boss = BanditLord(float(boss_position[0]), float(boss_position[1]))
        ctx.enemies.append(boss)
        chain.facts["boss_target_id"] = "boss_rusk_blackbanner"
        chain.facts["boss_target_entity_id"] = str(boss.entity_id)
        chain.facts["boss_target_name"] = "Rusk Blackbanner"
        chain.facts["boss_target_position"] = (float(boss.x), float(boss.y))
        chain.facts["boss_target_revealed"] = True
        chain.facts["boss_target_revealed_at_ms"] = now_ms
        self._attach_blackbanner_kill_hook(boss, ctx=ctx, event_bus=event_bus)
        return boss

    def _reveal_ashwing(
        self,
        chain: QuestChainInstance,
        ctx: SystemContext | None,
        *,
        event_bus: object | None,
        now_ms: int,
    ) -> object | None:
        _ = event_bus
        if ctx is None:
            return None
        existing_id = str(chain.facts.get("boss_target_entity_id", "") or "")
        if existing_id:
            existing = self._find_target_by_id(ctx, existing_id)
            if existing is not None:
                try:
                    setattr(existing, "name", ASHWING_THE_RED_NAME)
                    setattr(existing, "boss_name", ASHWING_THE_RED_NAME)
                    setattr(existing, "boss_display_name", ASHWING_THE_RED_NAME)
                    setattr(existing, "boss_def", ASHWING_BOSS_DEF)
                except Exception:
                    pass
                chain.facts["boss_target_revealed"] = True
                chain.facts["boss_target_revealed_at_ms"] = now_ms
                return existing

        boss_position = chain.facts.get("boss_target_position", None)
        if boss_position is None:
            boss_position = chain.facts.get("dragon_cave_target_position", None)
        if boss_position is None:
            boss_position = chain.facts.get("hoard_target_position", None)
        if boss_position is None:
            boss_position = (0.0, 0.0)

        ashwing = Dragon(float(boss_position[0]), float(boss_position[1]))
        try:
            ashwing.name = ASHWING_THE_RED_NAME
            ashwing.boss_name = ASHWING_THE_RED_NAME
            ashwing.boss_display_name = ASHWING_THE_RED_NAME
            ashwing.boss_def = ASHWING_BOSS_DEF
        except Exception:
            pass
        ctx.enemies.append(ashwing)
        chain.facts["boss_target_id"] = "boss_ashwing"
        chain.facts["boss_target_entity_id"] = str(ashwing.entity_id)
        chain.facts["boss_target_name"] = ASHWING_THE_RED_NAME
        chain.facts["boss_target_position"] = (float(ashwing.x), float(ashwing.y))
        chain.facts["boss_target_revealed"] = True
        chain.facts["boss_target_revealed_at_ms"] = now_ms
        return ashwing

    def _blackbanner_enemy_defeated(self, chain: QuestChainInstance, *, kind: str, ctx: SystemContext) -> bool:
        if chain.chain_type != BLACKBANNERS_TOLL.chain_type:
            return False
        if kind not in {"elite", "boss"}:
            return False
        fact_prefix = "elite_target" if kind == "elite" else "boss_target"
        if bool(chain.facts.get(f"{fact_prefix}_defeated", False)):
            return True
        live_entity_id = str(chain.facts.get(f"{fact_prefix}_entity_id", "") or "")
        if not live_entity_id:
            return False
        live = self._find_target_by_id(ctx, live_entity_id)
        if live is None:
            return False
        return not bool(getattr(live, "is_alive", True))

    def _ashwing_enemy_defeated(self, chain: QuestChainInstance, *, ctx: SystemContext) -> bool:
        if chain.chain_type != ASHWINGS_HOARD.chain_type:
            return False
        if bool(chain.facts.get("boss_target_defeated", False)):
            return True
        live_entity_id = str(chain.facts.get("boss_target_entity_id", "") or "")
        if not live_entity_id:
            return False
        live = self._find_target_by_id(ctx, live_entity_id)
        if live is None:
            return False
        return not bool(getattr(live, "is_alive", True))

    def _clear_blackbanner_runtime_refs(self, chain: QuestChainInstance) -> None:
        for key in (
            "elite_target_entity_id",
            "elite_target_id",
            "elite_target_name",
            "elite_target_position",
            "elite_target_spawn_key",
            "boss_target_entity_id",
            "boss_target_id",
            "boss_target_name",
            "boss_target_position",
            "boss_target_spawn_key",
        ):
            if key.endswith("_position"):
                chain.facts.pop(key, None)
            else:
                chain.facts[key] = "" if key.endswith("_id") or key.endswith("_name") or key.endswith("_entity_id") or key.endswith("_spawn_key") else ""
        chain.facts["elite_target_defeated"] = bool(chain.facts.get("elite_target_defeated", False))
        chain.facts["boss_target_defeated"] = bool(chain.facts.get("boss_target_defeated", False))

    @staticmethod
    def _offset_position(
        base_position: tuple[float, float] | None,
        dx_tiles: float,
        dy_tiles: float,
    ) -> tuple[float, float] | None:
        if base_position is None:
            return None
        return (
            float(base_position[0]) + float(dx_tiles) * float(TILE_SIZE),
            float(base_position[1]) + float(dy_tiles) * float(TILE_SIZE),
        )

    def _capture_target(self, target: object | str | None) -> _TargetInfo:
        if target is None:
            return _TargetInfo()
        if isinstance(target, _TargetInfo):
            return target
        if isinstance(target, str):
            readable = str(target).replace("poi_", "").replace("building_", "").replace("_", " ").title()
            return _TargetInfo(entity_id=str(target), name=readable, position=None)

        entity_id = str(getattr(target, "entity_id", "") or "")
        name = self._entity_name(target)
        position = self._entity_position(target)
        return _TargetInfo(entity_id=entity_id, name=name, position=position)

    @staticmethod
    def _entity_name(entity: object) -> str:
        poi_def = getattr(entity, "poi_def", None)
        if poi_def is not None:
            display_name = getattr(poi_def, "display_name", "")
            if display_name:
                return str(display_name)
        building_type = getattr(entity, "building_type", "")
        if hasattr(building_type, "value"):
            building_type = getattr(building_type, "value", building_type)
        text = str(building_type or entity.__class__.__name__)
        text = text.replace("poi_", "").replace("building_", "")
        return text.replace("_", " ").title()

    @staticmethod
    def _entity_position(entity: object) -> tuple[float, float] | None:
        try:
            return (float(getattr(entity, "center_x")), float(getattr(entity, "center_y")))
        except Exception:
            try:
                return (float(getattr(entity, "x")), float(getattr(entity, "y")))
            except Exception:
                return None

    @staticmethod
    def _hero_reached_target(hero: object, target_position: tuple[float, float] | None) -> bool:
        if target_position is None:
            return False
        tx, ty = float(target_position[0]), float(target_position[1])
        if hasattr(hero, "distance_to") and callable(getattr(hero, "distance_to")):
            try:
                return float(hero.distance_to(tx, ty)) <= float(_TARGET_REACH_RADIUS_PX)
            except Exception:
                pass
        hx = float(getattr(hero, "x", 0.0))
        hy = float(getattr(hero, "y", 0.0))
        dx = hx - tx
        dy = hy - ty
        return (dx * dx + dy * dy) <= float(_TARGET_REACH_RADIUS_PX) * float(_TARGET_REACH_RADIUS_PX)

    def _archive_chain(self, chain: QuestChainInstance, *, failed: bool) -> None:
        try:
            self.chains.remove(chain)
        except ValueError:
            pass
        if failed:
            self.failed_chains.append(chain)
        else:
            self.completed_chains.append(chain)

    def _record_history(
        self,
        chain: QuestChainInstance,
        *,
        event: str,
        now_ms: int,
        phase_id: str = "",
        phase_title: str = "",
        status: str = "",
        hero_id: str | None = None,
        target_id: str = "",
        target_name: str = "",
        target_position: tuple[float, float] | None = None,
        reason: str = "",
        reward_gold: int = 0,
    ) -> None:
        record = {
            "event": str(event),
            "phase_id": str(phase_id),
            "phase_title": str(phase_title),
            "status": str(status),
            "hero_id": None if hero_id is None or hero_id == "" else str(hero_id),
            "target_id": str(target_id),
            "target_name": str(target_name),
            "target_position": target_position,
            "time_ms": int(now_ms),
        }
        if reason:
            record["reason"] = str(reason)
        if reward_gold:
            record["reward_gold"] = int(reward_gold)
        chain.history.append(record)

    @staticmethod
    def _history_summary(record: dict[str, object]) -> QuestChainHistorySummary:
        return QuestChainHistorySummary(
            event=str(record.get("event", "")),
            phase_id=str(record.get("phase_id", "") or ""),
            phase_title=str(record.get("phase_title", "") or ""),
            status=str(record.get("status", "") or ""),
            hero_id=None if record.get("hero_id", None) in (None, "") else str(record.get("hero_id")),
            target_id=str(record.get("target_id", "") or ""),
            target_name=str(record.get("target_name", "") or ""),
            target_position=record.get("target_position", None),
            at_ms=int(record.get("time_ms", 0) or 0),
        )

    def _emit(
        self,
        event_bus: object | None,
        event_type: GameEventType,
        *,
        chain: QuestChainInstance,
        now_ms: int,
        hero: object | None = None,
        hero_id: str | None = None,
        phase: QuestPhaseDef | None = None,
        target_info: _TargetInfo | None = None,
        reason: str = "",
        reward_gold: int = 0,
    ) -> None:
        if event_bus is None:
            return
        payload: dict[str, object] = {
            "type": event_type.value,
            "chain_id": int(chain.chain_id),
            "chain_type": str(chain.chain_type),
            "name": str(chain.name),
            "status": str(chain.status),
            "assigned_hero_id": chain.assigned_hero_id,
            "current_phase_id": str(chain.current_phase_id),
            "current_phase_title": "",
            "current_objective_type": "",
            "target_id": "",
            "target_name": "",
            "target_position": None,
            "time_ms": int(now_ms),
        }
        definition = self.get_definition(chain.chain_type)
        if definition.phases and chain.current_phase_index < len(definition.phases):
            current_phase = definition.phases[chain.current_phase_index]
            payload["current_phase_title"] = str(current_phase.title)
            payload["current_objective_type"] = str(current_phase.objective_type)
            current_target = target_info if target_info is not None else self._snapshot_target(chain, current_phase)
            payload["target_id"] = current_target.entity_id
            payload["target_name"] = current_target.name
            payload["target_position"] = current_target.position
        if hero is not None:
            payload["hero"] = str(getattr(hero, "name", "") or "")
        if hero_id is not None:
            payload["hero_id"] = str(hero_id)
        if phase is not None:
            payload["phase_id"] = str(phase.phase_id)
            payload["phase_title"] = str(phase.title)
            payload["objective_type"] = str(phase.objective_type)
        if reason:
            payload["reason"] = str(reason)
        if reward_gold:
            payload["reward_gold"] = int(reward_gold)
        try:
            event_bus.emit(payload)
        except Exception:
            pass


def _hero_id(hero: object | None, hero_id: str | None) -> str | None:
    if hero_id is not None and str(hero_id).strip():
        return str(hero_id)
    if hero is None:
        return None
    value = str(getattr(hero, "hero_id", "") or "").strip()
    return value or None


def _hero_name(hero: object | None, fallback: str = "") -> str:
    if hero is None:
        return str(fallback or "")
    value = str(getattr(hero, "name", "") or "").strip()
    return value or str(fallback or "")


def _find_hero(heroes: list, hero_id: str | None) -> object | None:
    if not hero_id:
        return None
    target = str(hero_id)
    for hero in heroes:
        if str(getattr(hero, "hero_id", "")) == target:
            return hero
    return None
