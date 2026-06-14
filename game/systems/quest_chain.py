"""WK138 quest-chain gameplay system.

This system owns the runtime state machine for layered quest chains while
coexisting with the existing one-shot quest system. Runtime state stores only
stable ids and primitive facts. Live entity refs are resolved from the current
system context on demand, and the no-chain/default path returns immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import TILE_SIZE
from game.content.quest_chains import (
    COLLECT_ITEM,
    DELIVER_ITEM,
    QUEST_CHAIN_DEFS,
    RELIC_OF_THE_OLD_SHRINE,
    SCOUT_LOCATION,
    QuestChainDef,
    QuestPhaseDef,
    get_chain_def,
)
from game.events import GameEventType
from game.sim.contracts import (
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
        self._next_chain_id = 1

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
        self._archive_chain(chain, failed=True)
        return True

    def complete_chain(
        self,
        chain_or_id: int | str | QuestChainInstance,
        hero: object,
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
        self._archive_chain(chain, failed=False)
        return True

    # ------------------------------------------------------------------
    # Tick / phase resolution
    # ------------------------------------------------------------------

    def update(self, ctx: SystemContext, dt: float) -> None:
        if not self.chains:
            return
        _ = dt

        for chain in list(self.chains):
            if chain.status != "active":
                continue

            hero = _find_hero(ctx.heroes or [], chain.assigned_hero_id)
            if hero is None or not getattr(hero, "is_alive", True):
                self.fail_chain(chain, event_bus=getattr(ctx, "event_bus", None), reason="hero_lost")
                continue

            definition = self.get_definition(chain.chain_type)
            if chain.current_phase_index >= len(definition.phases):
                self.complete_chain(chain, hero, event_bus=getattr(ctx, "event_bus", None))
                continue

            phase = definition.phases[chain.current_phase_index]
            target_info = self._resolve_live_target(chain, phase, ctx)
            if target_info is None:
                self.fail_chain(chain, event_bus=getattr(ctx, "event_bus", None), reason="target_missing")
                continue

            if phase.objective_type == SCOUT_LOCATION:
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif phase.objective_type == COLLECT_ITEM:
                if not chain.facts.get("relic_scouted", False):
                    continue
                if self._hero_reached_target(hero, target_info.position):
                    self._complete_phase(chain, phase, hero, target_info, ctx)
            elif phase.objective_type == DELIVER_ITEM:
                if not chain.facts.get("relic_collected", False):
                    continue
                if self._hero_reached_target(hero, target_info.position):
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
            chain.facts["relic_scouted"] = True
            chain.facts["relic_scouted_at_ms"] = now
        elif phase.objective_type == COLLECT_ITEM:
            chain.facts["relic_collected"] = True
            chain.facts["relic_carried"] = True
            chain.facts["relic_carried_by_hero_id"] = chain.assigned_hero_id
            chain.facts["relic_collected_at_ms"] = now
        elif phase.objective_type == DELIVER_ITEM:
            chain.facts["relic_delivered"] = True
            chain.facts["relic_delivered_at_ms"] = now

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
        self._emit(
            getattr(ctx, "event_bus", None),
            GameEventType.QUEST_CHAIN_PHASE_COMPLETED,
            chain=chain,
            hero=hero,
            phase=phase,
            target_info=target_info,
            now_ms=now,
        )

        if phase.objective_type == DELIVER_ITEM:
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
    ) -> _TargetInfo | None:
        snapshot_target = self._snapshot_target(chain, phase)
        if snapshot_target.entity_id:
            found = self._find_target_by_id(ctx, snapshot_target.entity_id)
            if found is None:
                return None
            return self._capture_target(found)
        if snapshot_target.position is not None:
            return snapshot_target
        return None

    def _find_target_by_id(self, ctx: SystemContext, target_id: str) -> object | None:
        if not target_id:
            return None
        for source in (
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

    def _capture_target(self, target: object | str | None) -> _TargetInfo:
        if target is None:
            return _TargetInfo()
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


def _find_hero(heroes: list, hero_id: str | None) -> object | None:
    if not hero_id:
        return None
    target = str(hero_id)
    for hero in heroes:
        if str(getattr(hero, "hero_id", "")) == target:
            return hero
    return None
