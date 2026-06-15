"""Deterministic boss encounter runtime for named bosses and elite affixes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import TILE_SIZE
from game.content.bosses import BossAbilityDef, BossDef, BossPhaseDef, BOSS_DEFS, boss_def_for_enemy_type
from game.content.elite_affixes import apply_elite_affixes, spawn_elite_enemy
from game.entities.enemy import Goblin
from game.events import GameEventType
from game.sim.contracts import (
    BossEncounterSnapshot,
    BossKillMemory,
    BossMemorySummary,
    EliteEncounterSnapshot,
    RevengeOpportunitySnapshot,
)
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.protocol import GameSystem, SystemContext


@dataclass(slots=True)
class _BossEncounterState:
    boss: object
    boss_def: BossDef
    current_phase: str
    current_phase_title: str
    spawned_at_ms: int
    status: str = "active"
    latest_telegraph: str = ""
    telegraph_started_at_ms: int = 0
    telegraph_resolves_at_ms: int = 0
    telegraph_resolved: bool = False
    war_banner_buffed_ids: set[str] = field(default_factory=set)
    memory_facts: list[dict[str, object]] = field(default_factory=list)
    defeated_by: list[dict[str, object]] = field(default_factory=list)
    killed_hero: list[dict[str, object]] = field(default_factory=list)
    spawn_rng: object | None = None


@dataclass(slots=True)
class _EliteEncounterState:
    enemy: object
    affix_ids: tuple[str, ...]
    spawned_at_ms: int
    status: str = "active"
    spawn_key: str = ""


class BossEncounterSystem(GameSystem):
    """Owns boss phase state, elite registration, and memory snapshots."""

    def __init__(self, definitions: dict[str, BossDef] | None = None):
        self.definitions = dict(BOSS_DEFS if definitions is None else definitions)
        self._boss_states: dict[str, _BossEncounterState] = {}
        self._elite_states: dict[str, _EliteEncounterState] = {}
        self._hooked_boss_ids: set[str] = set()
        self.bosses: list[object] = []
        self.elites: list[object] = []
        self.defeated_bosses: list[object] = []
        self.defeated_elites: list[object] = []

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def register_boss(
        self,
        boss: object,
        *,
        boss_def: BossDef | None = None,
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> object:
        boss_id = self._entity_id(boss)
        if not boss_id:
            return boss
        existing = self._boss_states.get(boss_id)
        if existing is not None:
            return boss

        definition = boss_def or self._definition_for_boss(boss)
        now = int(sim_now_ms() if now_ms is None else now_ms)
        phase = self._phase_for_boss(definition, boss)
        state = _BossEncounterState(
            boss=boss,
            boss_def=definition,
            current_phase=str(phase.phase_id),
            current_phase_title=str(phase.title),
            spawned_at_ms=now,
            spawn_rng=get_rng(f"boss_encounters:{boss_id}:rally"),
        )
        self._boss_states[boss_id] = state
        self.bosses.append(boss)

        self._prepare_boss_object(boss, definition, state)
        self._attach_boss_kill_hook(boss)
        self._emit(
            event_bus,
            GameEventType.BOSS_ENCOUNTER_STARTED,
            boss_id=boss_id,
            boss_type=str(getattr(boss, "enemy_type", definition.boss_type)),
            name=str(getattr(boss, "name", "") or definition.display_name_template),
            status="active",
            current_phase=state.current_phase,
            current_phase_title=state.current_phase_title,
            hp_pct=self._health_percent(boss),
            position=self._entity_position(boss),
            time_ms=now,
        )
        return boss

    track_boss = register_boss
    add_boss = register_boss

    def register_elite(
        self,
        enemy: object,
        *,
        nearby_enemies: tuple[object, ...] | list[object] = (),
        affix_ids: tuple[str, ...] | None = None,
        spawn_key: str = "",
        event_bus: object | None = None,
        now_ms: int | None = None,
    ) -> object:
        elite_id = self._entity_id(enemy)
        if not elite_id:
            return enemy
        existing = self._elite_states.get(elite_id)
        if existing is not None:
            return enemy

        now = int(sim_now_ms() if now_ms is None else now_ms)
        rolled_affixes = tuple(str(affix_id) for affix_id in (affix_ids or ()) if str(affix_id).strip())
        if not getattr(enemy, "is_elite", False):
            if rolled_affixes:
                apply_elite_affixes(
                    enemy,
                    rolled_affixes,
                    nearby_enemies=nearby_enemies,
                    now_ms=now,
                    spawn_key=spawn_key or elite_id,
                )
            else:
                rolled_affixes = spawn_elite_enemy(
                    enemy,
                    nearby_enemies=nearby_enemies,
                    now_ms=now,
                    spawn_key=spawn_key or elite_id,
                )
        else:
            if not rolled_affixes:
                rolled_affixes = tuple(str(affix_id) for affix_id in getattr(enemy, "elite_affix_ids", ()) or ())
        state = _EliteEncounterState(
            enemy=enemy,
            affix_ids=rolled_affixes,
            spawned_at_ms=now,
            spawn_key=str(spawn_key or elite_id),
        )
        self._elite_states[elite_id] = state
        self.elites.append(enemy)

        self._prepare_elite_object(enemy, state)
        self._emit(
            event_bus,
            GameEventType.ELITE_SPAWNED,
            elite_id=elite_id,
            base_type=str(getattr(enemy, "enemy_type", "")),
            name=str(getattr(enemy, "name", "") or getattr(enemy, "enemy_type", "")),
            affixes=rolled_affixes,
            status="active",
            position=self._entity_position(enemy),
            time_ms=now,
        )
        return enemy

    track_elite = register_elite
    add_elite = register_elite
    spawn_elite = register_elite

    def register_enemy(self, enemy: object, **kwargs) -> object:
        if getattr(enemy, "is_boss", False):
            return self.register_boss(enemy, **kwargs)
        if getattr(enemy, "is_elite", False) or getattr(enemy, "elite_affix_ids", None):
            return self.register_elite(enemy, **kwargs)
        return enemy

    track_enemy = register_enemy

    # ------------------------------------------------------------------
    # Lifecycle / update
    # ------------------------------------------------------------------

    def update(self, ctx: SystemContext, dt: float) -> None:
        _ = dt
        if not self._boss_states and not self._elite_states:
            return
        now = int(sim_now_ms())
        event_bus = getattr(ctx, "event_bus", None)
        enemies = list(getattr(ctx, "enemies", None) or [])
        if enemies:
            self._sync_live_encounters(enemies, event_bus=event_bus, now_ms=now)

        for state in list(self._boss_states.values()):
            boss = state.boss
            if not self._is_alive(boss):
                hero = self._resolve_defeating_hero(boss, ctx)
                self.record_defeated_by(
                    boss,
                    hero,
                    hero_id=self._hero_id(hero),
                    hero_name=self._hero_name(hero),
                    detail="boss_defeated",
                    now_ms=now,
                    event_bus=event_bus,
                    ctx=ctx,
                )
                continue

            phase = self._phase_for_boss(state.boss_def, boss)
            if phase.phase_id != state.current_phase:
                previous_phase = state.current_phase
                if previous_phase == "war_banner":
                    self._clear_war_banner(state, enemies)
                state.current_phase = str(phase.phase_id)
                state.current_phase_title = str(phase.title)
                self._prepare_boss_object(boss, state.boss_def, state)
                self._emit(
                    event_bus,
                    GameEventType.BOSS_PHASE_CHANGED,
                    boss_id=self._entity_id(boss),
                    boss_type=str(getattr(boss, "enemy_type", state.boss_def.boss_type)),
                    name=str(getattr(boss, "name", "") or state.boss_def.display_name_template),
                    previous_phase=str(previous_phase),
                    current_phase=state.current_phase,
                    current_phase_title=state.current_phase_title,
                    hp_pct=self._health_percent(boss),
                    time_ms=now,
                )
                if state.current_phase == "rally":
                    self._begin_rally(state, event_bus=event_bus, now_ms=now)
                continue

            if state.current_phase == "war_banner":
                self._sync_war_banner(state, enemies)
            elif state.current_phase == "rally":
                if not state.telegraph_started_at_ms:
                    self._begin_rally(state, event_bus=event_bus, now_ms=now)
                self._maybe_resolve_rally(state, ctx, event_bus=event_bus, now_ms=now)

        for state in list(self._elite_states.values()):
            if not self._is_alive(state.enemy):
                self._retire_elite_state(state, ctx, now_ms=now)

    # ------------------------------------------------------------------
    # Memory facts
    # ------------------------------------------------------------------

    def record_defeated_by(
        self,
        boss: object,
        hero: object | None = None,
        *,
        hero_id: str | None = None,
        hero_name: str = "",
        detail: str = "",
        now_ms: int | None = None,
        event_bus: object | None = None,
        ctx: SystemContext | None = None,
    ) -> dict[str, object] | None:
        state = self.get_boss_state(boss)
        if state is None and not getattr(boss, "memory_facts", None):
            self._prepare_boss_object(boss, self._definition_for_boss(boss), None)
        record = self._build_memory_record(
            event="defeated_by",
            hero=hero,
            hero_id=hero_id,
            hero_name=hero_name,
            detail=detail,
            now_ms=now_ms,
        )
        if state is not None:
            self._retire_boss_state(state, ctx, now_ms=int(record["time_ms"]))
        self._append_boss_memory(boss, state, record, bucket="defeated_by")
        self._emit(
            event_bus,
            GameEventType.BOSS_DEFEATED,
            boss_id=self._entity_id(boss),
            boss_type=str(getattr(boss, "enemy_type", "") or self._definition_for_boss(boss).boss_type),
            name=str(getattr(boss, "name", "") or self._definition_for_boss(boss).display_name_template),
            defeated_by_hero_id=record.get("hero_id"),
            defeated_by_hero_name=record.get("hero_name"),
            detail=str(record.get("detail", "")),
            time_ms=int(record["time_ms"]),
        )
        return record

    def record_killed_hero(
        self,
        boss: object,
        hero: object | None = None,
        *,
        hero_id: str | None = None,
        hero_name: str = "",
        detail: str = "",
        now_ms: int | None = None,
    ) -> dict[str, object] | None:
        state = self.get_boss_state(boss)
        if state is None and not getattr(boss, "memory_facts", None):
            self._prepare_boss_object(boss, self._definition_for_boss(boss), None)
        record = self._build_memory_record(
            event="killed_hero",
            hero=hero,
            hero_id=hero_id,
            hero_name=hero_name,
            detail=detail,
            now_ms=now_ms,
        )
        self._append_boss_memory(boss, state, record, bucket="killed_hero")
        self._maybe_prime_blackbanner_revenge_state(boss, hero, record)
        return record

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------

    def get_boss_state(self, boss_or_id: object) -> _BossEncounterState | None:
        boss_id = self._entity_id(boss_or_id)
        if not boss_id:
            return None
        return self._boss_states.get(boss_id)

    def get_elite_state(self, elite_or_id: object) -> _EliteEncounterState | None:
        elite_id = self._entity_id(elite_or_id)
        if not elite_id:
            return None
        return self._elite_states.get(elite_id)

    def get_active_boss_snapshots(self) -> tuple[BossEncounterSnapshot, ...]:
        if not self._boss_states:
            return ()
        return tuple(self._boss_snapshot(state) for state in self._boss_states.values())

    def get_active_boss_views(self) -> tuple[BossEncounterSnapshot, ...]:
        return self.get_active_boss_snapshots()

    def get_active_boss_encounters(self) -> tuple[BossEncounterSnapshot, ...]:
        return self.get_active_boss_snapshots()

    def get_active_boss_kill_memory_snapshots(self) -> tuple[BossKillMemory, ...]:
        if not self._boss_states:
            return ()
        memories: list[BossKillMemory] = []
        for state in self._boss_states.values():
            memory = getattr(state.boss, "_wk142_blackbanner_kill_memory", None)
            if isinstance(memory, BossKillMemory) and str(getattr(memory, "status", "")) == "remembered":
                memories.append(memory)
        return tuple(memories)

    def get_active_boss_kill_memories(self) -> tuple[BossKillMemory, ...]:
        return self.get_active_boss_kill_memory_snapshots()

    def get_active_boss_kill_memory_views(self) -> tuple[BossKillMemory, ...]:
        return self.get_active_boss_kill_memory_snapshots()

    def get_active_revenge_opportunity_snapshots(self) -> tuple[RevengeOpportunitySnapshot, ...]:
        if not self._boss_states:
            return ()
        revenge: list[RevengeOpportunitySnapshot] = []
        for state in self._boss_states.values():
            snapshot = getattr(state.boss, "_wk142_blackbanner_revenge_snapshot", None)
            if isinstance(snapshot, RevengeOpportunitySnapshot) and str(getattr(snapshot, "status", "")) == "active":
                revenge.append(snapshot)
        return tuple(revenge)

    def get_active_revenge_opportunities(self) -> tuple[RevengeOpportunitySnapshot, ...]:
        return self.get_active_revenge_opportunity_snapshots()

    def get_active_revenge_views(self) -> tuple[RevengeOpportunitySnapshot, ...]:
        return self.get_active_revenge_opportunity_snapshots()

    def get_active_elite_snapshots(self) -> tuple[EliteEncounterSnapshot, ...]:
        if not self._elite_states:
            return ()
        return tuple(self._elite_snapshot(state) for state in self._elite_states.values())

    def get_active_elite_views(self) -> tuple[EliteEncounterSnapshot, ...]:
        return self.get_active_elite_snapshots()

    def get_active_elites(self) -> tuple[EliteEncounterSnapshot, ...]:
        return self.get_active_elite_snapshots()

    # ------------------------------------------------------------------
    # WK142 hook/read-model helpers
    # ------------------------------------------------------------------

    def _sync_live_encounters(self, enemies: list[object], *, event_bus: object | None, now_ms: int) -> None:
        for enemy in enemies:
            if not self._is_alive(enemy):
                continue
            if getattr(enemy, "is_boss", False) or boss_def_for_enemy_type(str(getattr(enemy, "enemy_type", "") or "")) is not None:
                self.register_boss(enemy, event_bus=event_bus, now_ms=now_ms)
                continue
            if getattr(enemy, "is_elite", False) or getattr(enemy, "elite_affix_ids", None):
                self.register_elite(enemy, event_bus=event_bus, now_ms=now_ms)

    def _attach_boss_kill_hook(self, boss: object) -> None:
        boss_id = self._entity_id(boss)
        if not boss_id or boss_id in self._hooked_boss_ids:
            return

        add_hook = getattr(boss, "add_hero_killed_hook", None)
        if not callable(add_hook):
            self._hooked_boss_ids.add(boss_id)
            return

        def _on_hero_killed(hero: object, *, killer: object | None = None, now_ms: int | None = None) -> None:
            _ = killer
            self._record_boss_kill_memory(boss, hero, now_ms=now_ms)

        try:
            add_hook(_on_hero_killed)
        finally:
            self._hooked_boss_ids.add(boss_id)

    def _record_boss_kill_memory(self, boss: object, hero: object, *, now_ms: int | None = None) -> None:
        if getattr(hero, "is_captured", False):
            return
        record = self.record_killed_hero(
            boss,
            hero,
            hero_id=self._hero_id(hero),
            hero_name=self._hero_name(hero),
            detail="blackbanner_revenge" if self._is_blackbanner_revenge_boss(boss) else "boss_killed_hero",
            now_ms=now_ms,
        )
        if record is None or not self._is_blackbanner_revenge_boss(boss):
            return

        boss_id = self._entity_id(boss)
        if not boss_id:
            return
        if getattr(boss, "_wk142_blackbanner_revenge_snapshot", None) is not None:
            return

        fallen_hero_id = str(record.get("hero_id", "") or "")
        fallen_hero_name = str(record.get("hero_name", "") or "")
        at_ms = int(record.get("time_ms", 0) or 0)
        location_id = str(getattr(boss, "blackbanner_revenge_location_id", "") or "")
        location_name = str(getattr(boss, "blackbanner_revenge_location_name", "") or "")
        revenge_chain_id = str(getattr(boss, "blackbanner_revenge_chain_id", "") or "")
        memory = BossKillMemory(
            boss_id=str(boss_id),
            boss_name=str(getattr(boss, "name", "") or self._definition_for_boss(boss).display_name_template),
            boss_type=str(getattr(boss, "enemy_type", "") or self._definition_for_boss(boss).boss_type),
            fallen_hero_id=fallen_hero_id,
            fallen_hero_name=fallen_hero_name,
            location_id=location_id,
            location_name=location_name,
            killed_at_ms=at_ms,
            revenge_chain_id=revenge_chain_id,
            status="remembered",
        )
        setattr(boss, "_wk142_blackbanner_kill_memory", memory)

        phase_id = str(getattr(boss, "blackbanner_revenge_current_phase_id", "avenge_fallen_hero") or "avenge_fallen_hero")
        phase_title = str(getattr(boss, "blackbanner_revenge_current_phase_title", "Avenge the Fallen") or "Avenge the Fallen")
        revenge = RevengeOpportunitySnapshot(
            revenge_id=revenge_chain_id or f"revenge_{boss_id}_{fallen_hero_id}",
            boss_id=str(boss_id),
            boss_name=memory.boss_name,
            boss_type=memory.boss_type,
            fallen_hero_id=fallen_hero_id,
            fallen_hero_name=fallen_hero_name,
            target_location_id=location_id,
            target_location_name=location_name,
            current_phase_id=phase_id,
            current_phase_title=phase_title,
            revenge_chain_id=revenge_chain_id or f"revenge_{boss_id}_{fallen_hero_id}",
            status="active",
            offered_at_ms=at_ms,
        )
        setattr(boss, "_wk142_blackbanner_revenge_snapshot", revenge)

    @staticmethod
    def _is_blackbanner_revenge_boss(boss: object) -> bool:
        boss_type = str(getattr(boss, "enemy_type", "") or "")
        boss_name = str(getattr(boss, "name", "") or "")
        return boss_type == "bandit_lord" and boss_name == "Rusk Blackbanner"

    def _clear_blackbanner_revenge_state(self, boss: object) -> None:
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

    def _maybe_prime_blackbanner_revenge_state(
        self,
        boss: object,
        hero: object,
        record: dict[str, object],
    ) -> None:
        if getattr(hero, "is_captured", False):
            return
        if not self._is_blackbanner_revenge_boss(boss):
            return
        if getattr(boss, "_wk142_blackbanner_kill_memory", None) is not None:
            return

        boss_id = self._entity_id(boss)
        if not boss_id:
            return

        fallen_hero_id = str(record.get("hero_id", "") or "")
        fallen_hero_name = str(record.get("hero_name", "") or "")
        at_ms = int(record.get("time_ms", 0) or 0)
        boss_name = str(getattr(boss, "name", "") or self._definition_for_boss(boss).display_name_template)
        boss_type = str(getattr(boss, "enemy_type", "") or self._definition_for_boss(boss).boss_type)
        location_id = str(getattr(boss, "blackbanner_revenge_location_id", "") or "")
        location_name = str(getattr(boss, "blackbanner_revenge_location_name", "") or "")
        revenge_chain_id = str(getattr(boss, "blackbanner_revenge_chain_id", "") or "")

        memory = BossKillMemory(
            boss_id=str(boss_id),
            boss_name=boss_name,
            boss_type=boss_type,
            fallen_hero_id=fallen_hero_id,
            fallen_hero_name=fallen_hero_name,
            location_id=location_id,
            location_name=location_name,
            killed_at_ms=at_ms,
            revenge_chain_id=revenge_chain_id,
            status="remembered",
        )
        setattr(boss, "_wk142_blackbanner_kill_memory", memory)

        phase_id = str(getattr(boss, "blackbanner_revenge_current_phase_id", "avenge_fallen_hero") or "avenge_fallen_hero")
        phase_title = str(getattr(boss, "blackbanner_revenge_current_phase_title", "Avenge the Fallen") or "Avenge the Fallen")
        revenge = RevengeOpportunitySnapshot(
            revenge_id=revenge_chain_id or f"revenge_{boss_id}_{fallen_hero_id}",
            boss_id=str(boss_id),
            boss_name=boss_name,
            boss_type=boss_type,
            fallen_hero_id=fallen_hero_id,
            fallen_hero_name=fallen_hero_name,
            target_location_id=location_id,
            target_location_name=location_name,
            current_phase_id=phase_id,
            current_phase_title=phase_title,
            revenge_chain_id=revenge_chain_id or f"revenge_{boss_id}_{fallen_hero_id}",
            status="active",
            offered_at_ms=at_ms,
        )
        setattr(boss, "_wk142_blackbanner_revenge_snapshot", revenge)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _definition_for_boss(self, boss: object) -> BossDef:
        boss_type = str(getattr(boss, "enemy_type", "") or "").strip()
        definition = self.definitions.get(boss_type)
        if definition is not None:
            return definition
        definition = boss_def_for_enemy_type(boss_type)
        if definition is not None:
            return definition
        display_name = str(getattr(boss, "name", "") or boss_type.replace("_", " ").title())
        return BossDef(
            boss_type=boss_type or "boss",
            display_name_template=display_name,
            base_enemy_type=boss_type or "boss",
            difficulty_tier=1,
            phases=(),
            abilities=(),
            loot_table_id=f"{boss_type or 'boss'}_loot",
            weakness_tags=(),
            memory_tags=("defeated_by", "killed_hero"),
        )

    @staticmethod
    def _entity_id(entity: object) -> str:
        return str(getattr(entity, "entity_id", "") or "").strip()

    @staticmethod
    def _entity_position(entity: object) -> tuple[float, float] | None:
        try:
            return (float(getattr(entity, "x", 0.0) or 0.0), float(getattr(entity, "y", 0.0) or 0.0))
        except Exception:
            return (0.0, 0.0)

    @classmethod
    def _entity_xy(cls, entity: object) -> tuple[float, float]:
        pos = cls._entity_position(entity)
        return (0.0, 0.0) if pos is None else pos

    @classmethod
    def _health_percent(cls, entity: object) -> float:
        try:
            if hasattr(entity, "health_percent"):
                value = float(getattr(entity, "health_percent"))
            else:
                hp = float(getattr(entity, "hp", 0) or 0)
                max_hp = float(getattr(entity, "max_hp", 0) or 0)
                value = 0.0 if max_hp <= 0 else hp / max_hp
        except Exception:
            return 0.0
        return max(0.0, min(1.0, value))

    @staticmethod
    def _is_alive(entity: object) -> bool:
        alive = getattr(entity, "is_alive", None)
        if isinstance(alive, bool):
            return alive
        try:
            return float(getattr(entity, "hp", 0) or 0) > 0
        except Exception:
            return False

    @staticmethod
    def _phase_for_boss(definition: BossDef, boss: object) -> BossPhaseDef:
        hp_pct = BossEncounterSystem._health_percent(boss)
        if not definition.phases:
            return BossPhaseDef(
                phase_id="default",
                starts_below_hp_pct=1.0,
                title=str(getattr(boss, "name", "") or definition.display_name_template),
                abilities=(),
            )

        selected = definition.phases[0]
        for phase in sorted(definition.phases, key=lambda item: float(item.starts_below_hp_pct), reverse=True):
            if hp_pct <= float(phase.starts_below_hp_pct):
                selected = phase
        return selected

    def _prepare_boss_object(self, boss: object, definition: BossDef, state: _BossEncounterState | None) -> None:
        phase_id = state.current_phase if state is not None else ""
        phase_title = state.current_phase_title if state is not None else ""
        desired_name = str(definition.display_name_template or getattr(boss, "name", "") or definition.boss_type.replace("_", " ").title())
        setattr(boss, "is_boss", True)
        setattr(boss, "boss_def", definition)
        setattr(boss, "boss_type", str(getattr(boss, "enemy_type", definition.boss_type)))
        setattr(boss, "name", desired_name)
        setattr(boss, "boss_name", desired_name)
        setattr(boss, "boss_display_name", desired_name)
        setattr(boss, "boss_status", "active" if self._is_alive(boss) else "defeated")
        setattr(boss, "current_boss_phase", phase_id)
        setattr(boss, "current_boss_phase_title", phase_title)
        setattr(boss, "boss_phase", phase_id)
        setattr(boss, "boss_phase_title", phase_title)
        setattr(boss, "latest_telegraph", getattr(boss, "latest_telegraph", ""))
        setattr(boss, "latest_boss_telegraph", getattr(boss, "latest_boss_telegraph", ""))
        memory_facts = getattr(boss, "memory_facts", None)
        if not isinstance(memory_facts, list):
            memory_facts = [] if memory_facts is None else list(memory_facts)
            setattr(boss, "memory_facts", memory_facts)
        defeated_by = getattr(boss, "defeated_by", None)
        if not isinstance(defeated_by, list):
            defeated_by = [] if defeated_by is None else list(defeated_by)
            setattr(boss, "defeated_by", defeated_by)
        killed_hero = getattr(boss, "killed_hero", None)
        if not isinstance(killed_hero, list):
            killed_hero = [] if killed_hero is None else list(killed_hero)
            setattr(boss, "killed_hero", killed_hero)
        setattr(boss, "war_banner_attack_bonus", int(getattr(boss, "war_banner_attack_bonus", 0) or 0))
        setattr(boss, "war_banner_courage_bonus", int(getattr(boss, "war_banner_courage_bonus", 0) or 0))
        setattr(boss, "war_banner_targets", tuple(getattr(boss, "war_banner_targets", ()) or ()))
        setattr(boss, "rally_spawn_cap", int(getattr(boss, "rally_spawn_cap", 0) or 0))
        setattr(boss, "rally_nearby_limit", int(getattr(boss, "rally_nearby_limit", 0) or 0))
        setattr(boss, "rally_telegraph_ms", int(getattr(boss, "rally_telegraph_ms", 0) or 0))
        setattr(boss, "rally_resolve_at_ms", int(getattr(boss, "rally_resolve_at_ms", 0) or 0))
        self._apply_phase_ability_facts(boss, definition, phase_id)

    def _apply_phase_ability_facts(self, boss: object, definition: BossDef, phase_id: str) -> None:
        phase = next((item for item in definition.phases if str(item.phase_id) == str(phase_id)), None)
        if phase is None or not phase.abilities:
            setattr(boss, "current_boss_ability_id", "")
            setattr(boss, "current_boss_ability_name", "")
            setattr(boss, "current_boss_ability_trigger", "")
            setattr(boss, "current_boss_ability_cooldown_ms", 0)
            setattr(boss, "current_boss_ability_telegraph_ms", 0)
            setattr(boss, "current_boss_ability_payload", {})
            setattr(boss, "boss_phase_ability_ids", tuple())
            return

        ability_id = str(phase.abilities[0])
        ability = next((item for item in definition.abilities if str(item.ability_id) == ability_id), None)
        setattr(boss, "boss_phase_ability_ids", tuple(str(item) for item in phase.abilities))
        if ability is None:
            setattr(boss, "current_boss_ability_id", ability_id)
            setattr(boss, "current_boss_ability_name", "")
            setattr(boss, "current_boss_ability_trigger", "")
            setattr(boss, "current_boss_ability_cooldown_ms", 0)
            setattr(boss, "current_boss_ability_telegraph_ms", 0)
            setattr(boss, "current_boss_ability_payload", {})
            return

        setattr(boss, "current_boss_ability_id", str(ability.ability_id))
        setattr(boss, "current_boss_ability_name", str(ability.display_name))
        setattr(boss, "current_boss_ability_trigger", str(ability.trigger))
        setattr(boss, "current_boss_ability_cooldown_ms", int(ability.cooldown_ms))
        setattr(boss, "current_boss_ability_telegraph_ms", int(ability.telegraph_ms))
        setattr(boss, "current_boss_ability_payload", dict(ability.payload))

    def _prepare_elite_object(self, enemy: object, state: _EliteEncounterState) -> None:
        setattr(enemy, "is_elite", True)
        setattr(enemy, "elite_affix_ids", tuple(state.affix_ids))
        setattr(enemy, "elite_status", "active")
        setattr(enemy, "elite_spawn_key", state.spawn_key)
        setattr(enemy, "elite_spawned_at_ms", state.spawned_at_ms)
        setattr(enemy, "elite_name", str(getattr(enemy, "name", "") or getattr(enemy, "enemy_type", "")))
        setattr(enemy, "elite_title", str(getattr(enemy, "elite_title", "") or ""))
        if not hasattr(enemy, "elite_facts"):
            setattr(enemy, "elite_facts", tuple())

    def _boss_snapshot(self, state: _BossEncounterState) -> BossEncounterSnapshot:
        boss = state.boss
        memory_summaries = tuple(
            BossMemorySummary(
                event=str(record.get("event", "")),
                hero_id=None if record.get("hero_id", None) in (None, "") else str(record.get("hero_id")),
                hero_name=str(record.get("hero_name", "") or ""),
                detail=str(record.get("detail", "") or ""),
                at_ms=int(record.get("time_ms", 0) or 0),
            )
            for record in state.memory_facts
        )
        target = getattr(boss, "target", None)
        target_hero_id = None
        if target is not None and getattr(target, "hero_id", None):
            target_hero_id = str(getattr(target, "hero_id"))
        return BossEncounterSnapshot(
            boss_id=self._entity_id(boss),
            boss_type=str(getattr(boss, "enemy_type", state.boss_def.boss_type)),
            name=str(getattr(boss, "name", "") or state.boss_def.display_name_template),
            status=str(getattr(boss, "boss_status", state.status)),
            current_phase=str(state.current_phase),
            current_phase_title=str(state.current_phase_title),
            hp_pct=self._health_percent(boss),
            position=self._entity_position(boss),
            target_hero_id=target_hero_id,
            latest_telegraph=str(state.latest_telegraph or getattr(boss, "latest_telegraph", "") or ""),
            memory_summaries=memory_summaries,
        )

    def _elite_snapshot(self, state: _EliteEncounterState) -> EliteEncounterSnapshot:
        enemy = state.enemy
        return EliteEncounterSnapshot(
            elite_id=self._entity_id(enemy),
            base_type=str(getattr(enemy, "enemy_type", "")),
            name=str(getattr(enemy, "name", "") or getattr(enemy, "enemy_type", "")),
            status=str(getattr(enemy, "elite_status", state.status)),
            affixes=tuple(getattr(enemy, "elite_affix_ids", state.affix_ids) or state.affix_ids),
            position=self._entity_position(enemy),
        )

    def _begin_rally(
        self,
        state: _BossEncounterState,
        *,
        event_bus: object | None,
        now_ms: int,
    ) -> None:
        boss = state.boss
        rally = self._ability_for_phase(state.boss_def, "rally")
        if rally is None:
            return
        state.latest_telegraph = "rally"
        state.telegraph_started_at_ms = now_ms
        state.telegraph_resolves_at_ms = now_ms + int(rally.telegraph_ms)
        state.telegraph_resolved = False
        self._prepare_boss_object(boss, state.boss_def, state)
        setattr(boss, "latest_telegraph", "rally")
        setattr(boss, "latest_boss_telegraph", "rally")
        setattr(boss, "rally_spawn_cap", int(rally.payload.get("spawn_cap", 3) or 3))
        setattr(boss, "rally_nearby_limit", int(rally.payload.get("nearby_limit", 4) or 4))
        setattr(boss, "rally_telegraph_ms", int(rally.telegraph_ms))
        setattr(boss, "rally_resolve_at_ms", int(state.telegraph_resolves_at_ms))
        self._emit(
            event_bus,
            GameEventType.BOSS_ABILITY_TELEGRAPHED,
            boss_id=self._entity_id(boss),
            boss_type=str(getattr(boss, "enemy_type", state.boss_def.boss_type)),
            name=str(getattr(boss, "name", "") or state.boss_def.display_name_template),
            ability_id=str(rally.ability_id),
            ability_name=str(rally.display_name),
            current_phase=state.current_phase,
            current_phase_title=state.current_phase_title,
            telegraph_ms=int(rally.telegraph_ms),
            resolve_at_ms=int(state.telegraph_resolves_at_ms),
            detail=str(rally.payload.get("spawn_enemy_type", "reinforcements")),
            time_ms=now_ms,
        )

    def _maybe_resolve_rally(
        self,
        state: _BossEncounterState,
        ctx: SystemContext,
        *,
        event_bus: object | None,
        now_ms: int,
    ) -> None:
        if state.telegraph_resolved or not state.telegraph_started_at_ms:
            return
        if now_ms < state.telegraph_resolves_at_ms:
            return

        boss = state.boss
        rally = self._ability_for_phase(state.boss_def, "rally")
        if rally is None:
            state.telegraph_resolved = True
            return

        nearby_limit = int(rally.payload.get("nearby_limit", 4) or 4)
        spawn_cap = int(rally.payload.get("spawn_cap", 3) or 3)
        nearby_count = self._count_nearby_enemies(
            boss,
            float(rally.payload.get("radius_tiles", 5.0) or 5.0),
            ctx,
            enemy_type="goblin",
        )
        spawned: list[object] = []
        if nearby_count < nearby_limit:
            spawn_count = min(spawn_cap, nearby_limit - nearby_count)
            spawned = self._spawn_goblin_reinforcements(state, ctx, spawn_count)

        state.telegraph_resolved = True
        self._emit(
            event_bus,
            GameEventType.BOSS_ABILITY_RESOLVED,
            boss_id=self._entity_id(boss),
            boss_type=str(getattr(boss, "enemy_type", state.boss_def.boss_type)),
            name=str(getattr(boss, "name", "") or state.boss_def.display_name_template),
            ability_id=str(rally.ability_id),
            ability_name=str(rally.display_name),
            spawned_count=len(spawned),
            spawned_enemy_ids=tuple(self._entity_id(enemy) for enemy in spawned),
            nearby_goblin_count=nearby_count,
            current_phase=state.current_phase,
            current_phase_title=state.current_phase_title,
            time_ms=now_ms,
        )

    def _sync_war_banner(self, state: _BossEncounterState, enemies: list[object]) -> None:
        boss = state.boss
        banner = self._ability_for_phase(state.boss_def, "war_banner")
        if banner is None:
            return
        attack_bonus = int(banner.payload.get("attack_bonus", 2) or 2)
        courage_bonus = int(banner.payload.get("courage_bonus", 1) or 1)
        radius_tiles = float(banner.payload.get("radius_tiles", 4.5) or 4.5)
        radius_sq = (radius_tiles * TILE_SIZE) ** 2
        boss_x, boss_y = self._entity_xy(boss)
        desired_ids: set[str] = set()

        for ally in enemies:
            if ally is boss or not self._is_alive(ally):
                continue
            if str(getattr(ally, "enemy_type", "")) != "goblin":
                continue
            ally_x, ally_y = self._entity_xy(ally)
            dx = boss_x - ally_x
            dy = boss_y - ally_y
            if (dx * dx + dy * dy) > radius_sq:
                continue
            ally_id = self._entity_id(ally)
            if not ally_id:
                continue
            source = f"boss:{self._entity_id(boss)}:war_banner:{ally_id}"
            ally.set_attack_bonus(source, attack_bonus)
            desired_ids.add(ally_id)

        for ally_id in list(state.war_banner_buffed_ids - desired_ids):
            ally = self._enemy_by_id(enemies, ally_id)
            if ally is None:
                continue
            ally.clear_attack_bonuses_with_prefix(f"boss:{self._entity_id(boss)}:war_banner:")

        state.war_banner_buffed_ids = desired_ids
        setattr(boss, "war_banner_targets", tuple(sorted(desired_ids)))
        setattr(boss, "war_banner_attack_bonus", attack_bonus)
        setattr(boss, "war_banner_courage_bonus", courage_bonus)
        setattr(boss, "war_banner_radius_tiles", radius_tiles)

    def _clear_war_banner(self, state: _BossEncounterState, enemies: list[object]) -> None:
        boss_id = self._entity_id(state.boss)
        for ally in enemies:
            if ally is state.boss or not hasattr(ally, "clear_attack_bonuses_with_prefix"):
                continue
            ally.clear_attack_bonuses_with_prefix(f"boss:{boss_id}:war_banner:")
        state.war_banner_buffed_ids.clear()
        setattr(state.boss, "war_banner_targets", ())
        setattr(state.boss, "war_banner_attack_bonus", 0)
        setattr(state.boss, "war_banner_courage_bonus", 0)

    def _spawn_goblin_reinforcements(
        self,
        state: _BossEncounterState,
        ctx: SystemContext,
        spawn_count: int,
    ) -> list[object]:
        if spawn_count <= 0:
            return []
        boss_x, boss_y = self._entity_xy(state.boss)
        offsets = [
            (-TILE_SIZE, 0.0),
            (TILE_SIZE, 0.0),
            (0.0, -TILE_SIZE),
            (0.0, TILE_SIZE),
            (-TILE_SIZE, -TILE_SIZE),
            (TILE_SIZE, -TILE_SIZE),
            (-TILE_SIZE, TILE_SIZE),
            (TILE_SIZE, TILE_SIZE),
        ]
        start = 0
        rng = state.spawn_rng
        if rng is not None and hasattr(rng, "randrange"):
            start = int(rng.randrange(len(offsets)))
        spawned: list[object] = []
        for index in range(spawn_count):
            dx, dy = offsets[(start + index) % len(offsets)]
            goblin = Goblin(max(1.0, boss_x + dx), max(1.0, boss_y + dy))
            ctx.enemies.append(goblin)
            spawned.append(goblin)
        return spawned

    def _retire_boss_state(
        self,
        state: _BossEncounterState,
        ctx: SystemContext | None,
        *,
        now_ms: int,
    ) -> None:
        boss = state.boss
        boss_id = self._entity_id(boss)
        enemies = list(getattr(ctx, "enemies", None) or []) if ctx is not None else []
        if state.current_phase == "war_banner":
            self._clear_war_banner(state, enemies)
        state.status = "defeated"
        self._prepare_boss_object(boss, state.boss_def, state)
        self._clear_blackbanner_revenge_state(boss)
        setattr(boss, "boss_status", "defeated")
        setattr(boss, "defeated_at_ms", now_ms)
        if boss_id in self._boss_states:
            self._boss_states.pop(boss_id, None)
        try:
            self.bosses.remove(boss)
        except ValueError:
            pass
        self.defeated_bosses.append(boss)

    def _retire_elite_state(
        self,
        state: _EliteEncounterState,
        ctx: SystemContext | None,
        *,
        now_ms: int,
    ) -> None:
        enemy = state.enemy
        enemy_id = self._entity_id(enemy)
        enemies = list(getattr(ctx, "enemies", None) or []) if ctx is not None else []
        affix_ids = tuple(getattr(enemy, "elite_affix_ids", state.affix_ids) or state.affix_ids)
        for affix_id in affix_ids:
            affix_prefix = f"elite:{enemy_id}:{affix_id}:"
            for ally in enemies:
                if ally is enemy or not hasattr(ally, "clear_attack_bonuses_with_prefix"):
                    continue
                ally.clear_attack_bonuses_with_prefix(affix_prefix)
        setattr(enemy, "elite_status", "defeated")
        setattr(enemy, "elite_defeated_at_ms", now_ms)
        if enemy_id in self._elite_states:
            self._elite_states.pop(enemy_id, None)
        try:
            self.elites.remove(enemy)
        except ValueError:
            pass
        self.defeated_elites.append(enemy)

    def _ability_for_phase(self, definition: BossDef, phase_id: str) -> BossAbilityDef | None:
        phase = next((phase for phase in definition.phases if str(phase.phase_id) == str(phase_id)), None)
        if phase is None:
            return None
        if not phase.abilities:
            return None
        ability_id = str(phase.abilities[0])
        return next((ability for ability in definition.abilities if str(ability.ability_id) == ability_id), None)

    def _count_nearby_enemies(
        self,
        boss: object,
        radius_tiles: float,
        ctx: SystemContext,
        *,
        enemy_type: str,
    ) -> int:
        radius_sq = (float(radius_tiles) * TILE_SIZE) ** 2
        boss_x, boss_y = self._entity_xy(boss)
        count = 0
        for enemy in getattr(ctx, "enemies", None) or []:
            if enemy is boss or not self._is_alive(enemy):
                continue
            if str(getattr(enemy, "enemy_type", "")) != enemy_type:
                continue
            ex, ey = self._entity_xy(enemy)
            dx = boss_x - ex
            dy = boss_y - ey
            if (dx * dx + dy * dy) <= radius_sq:
                count += 1
        return count

    def _enemy_by_id(self, enemies: list[object], entity_id: str) -> object | None:
        if not entity_id:
            return None
        for enemy in enemies:
            if self._entity_id(enemy) == entity_id:
                return enemy
        return None

    def _build_memory_record(
        self,
        *,
        event: str,
        hero: object | None,
        hero_id: str | None,
        hero_name: str,
        detail: str,
        now_ms: int | None,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "event": str(event),
            "hero_id": self._hero_id(hero, hero_id),
            "hero_name": self._hero_name(hero, hero_name),
            "detail": str(detail or ""),
            "time_ms": int(sim_now_ms() if now_ms is None else now_ms),
        }
        return record

    def _append_boss_memory(
        self,
        boss: object,
        state: _BossEncounterState | None,
        record: dict[str, object],
        *,
        bucket: str,
    ) -> None:
        if state is None:
            memory_facts = getattr(boss, "memory_facts", None)
            if not isinstance(memory_facts, list):
                memory_facts = [] if memory_facts is None else list(memory_facts)
                setattr(boss, "memory_facts", memory_facts)
            target_list = memory_facts
        else:
            target_list = state.memory_facts
            setattr(boss, "memory_facts", state.memory_facts)
            setattr(boss, "defeated_by", state.defeated_by)
            setattr(boss, "killed_hero", state.killed_hero)
        target_list.append(record)
        if state is not None:
            if bucket == "defeated_by":
                state.defeated_by.append(record)
            elif bucket == "killed_hero":
                state.killed_hero.append(record)
        else:
            if bucket == "defeated_by":
                defeated_by = getattr(boss, "defeated_by", None)
                if not isinstance(defeated_by, list):
                    defeated_by = [] if defeated_by is None else list(defeated_by)
                    setattr(boss, "defeated_by", defeated_by)
                defeated_by.append(record)
            elif bucket == "killed_hero":
                killed_hero = getattr(boss, "killed_hero", None)
                if not isinstance(killed_hero, list):
                    killed_hero = [] if killed_hero is None else list(killed_hero)
                    setattr(boss, "killed_hero", killed_hero)
                killed_hero.append(record)

    def _resolve_defeating_hero(self, boss: object, ctx: SystemContext | None) -> object | None:
        if boss is None:
            return None
        target = getattr(boss, "target", None)
        if target is not None and getattr(target, "hero_id", None):
            return target
        heroes = list(getattr(ctx, "heroes", None) or []) if ctx is not None else []
        attacker_names = sorted(str(name) for name in (getattr(boss, "attackers", set()) or set()))
        if attacker_names:
            heroes_by_name = {str(getattr(hero, "name", "")): hero for hero in heroes}
            for attacker_name in attacker_names:
                hero = heroes_by_name.get(attacker_name)
                if hero is not None:
                    return hero
        return None

    @staticmethod
    def _hero_id(hero: object | None, fallback: str | None = None) -> str | None:
        if hero is None:
            return None if fallback is None else str(fallback)
        value = str(getattr(hero, "hero_id", "") or "").strip()
        if value:
            return value
        return None if fallback is None else str(fallback)

    @staticmethod
    def _hero_name(hero: object | None, fallback: str = "") -> str:
        if hero is None:
            return str(fallback or "")
        value = str(getattr(hero, "name", "") or "").strip()
        return value or str(fallback or "")

    def _emit(self, event_bus: object | None, event_type: GameEventType, **payload: object) -> None:
        if event_bus is None:
            return
        event = dict(payload)
        event["type"] = event_type.value
        emit = getattr(event_bus, "emit", None)
        if callable(emit):
            try:
                emit(event)
            except Exception:
                pass


__all__ = ["BossEncounterSystem"]
