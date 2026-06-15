"""Boss content registry for reusable named encounters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BossAbilityDef:
    """Static description of one boss ability."""

    ability_id: str
    display_name: str
    trigger: str
    cooldown_ms: int
    telegraph_ms: int
    payload: dict[str, object] = field(default_factory=dict)
    max_uses: int | None = None


@dataclass(frozen=True, slots=True)
class BossPhaseDef:
    """Static description of a boss phase."""

    phase_id: str
    starts_below_hp_pct: float
    title: str
    abilities: tuple[str, ...]
    on_enter_event: str | None = None
    add_spawn_budget: int = 0


@dataclass(frozen=True, slots=True)
class BossDef:
    """Static description of a named boss encounter."""

    boss_type: str
    display_name_template: str
    base_enemy_type: str
    difficulty_tier: int
    phases: tuple[BossPhaseDef, ...]
    abilities: tuple[BossAbilityDef, ...]
    loot_table_id: str
    weakness_tags: tuple[str, ...] = ()
    memory_tags: tuple[str, ...] = ()


WARCHIEF_WAR_BANNER = BossAbilityDef(
    ability_id="war_banner",
    display_name="War Banner",
    trigger="phase_start",
    cooldown_ms=0,
    telegraph_ms=0,
    payload={
        "attack_bonus": 2,
        "radius_tiles": 4.5,
        "courage_bonus": 1,
    },
)

WARCHIEF_RALLY = BossAbilityDef(
    ability_id="rally",
    display_name="Rally",
    trigger="hp_below",
    cooldown_ms=6_000,
    telegraph_ms=1_200,
    payload={
        "spawn_cap": 3,
        "nearby_limit": 4,
        "radius_tiles": 5.0,
        "spawn_enemy_type": "goblin",
    },
)

WARCHIEF_WAR_BANNER_PHASE = BossPhaseDef(
    phase_id="war_banner",
    starts_below_hp_pct=1.0,
    title="War Banner",
    abilities=("war_banner",),
)

WARCHIEF_RALLY_PHASE = BossPhaseDef(
    phase_id="rally",
    starts_below_hp_pct=0.5,
    title="Rally",
    abilities=("rally",),
    on_enter_event="boss_phase_changed",
    add_spawn_budget=3,
)

WARCHIEF_BOSS_DEF = BossDef(
    boss_type="goblin_warchief",
    display_name_template="The Goblin Warchief",
    base_enemy_type="goblin_warchief",
    difficulty_tier=1,
    phases=(WARCHIEF_WAR_BANNER_PHASE, WARCHIEF_RALLY_PHASE),
    abilities=(WARCHIEF_WAR_BANNER, WARCHIEF_RALLY),
    loot_table_id="goblin_warchief_boss_loot",
    weakness_tags=("focus-fire", "burst"),
    memory_tags=("defeated_by", "killed_hero"),
)

THE_GOBLIN_WARCHIEF = WARCHIEF_BOSS_DEF

RUSK_TOLL_BANNER = BossAbilityDef(
    ability_id="toll_banner",
    display_name="Toll Banner",
    trigger="phase_start",
    cooldown_ms=0,
    telegraph_ms=0,
    payload={
        "attack_bonus": 2,
        "radius_tiles": 4.5,
        "courage_bonus": 1,
        "buff_enemy_type": "bandit",
        "announce_on_register": True,
    },
)

RUSK_SMOKE_RETREAT = BossAbilityDef(
    ability_id="smoke_retreat",
    display_name="Smoke Retreat",
    trigger="hp_below",
    cooldown_ms=6_000,
    telegraph_ms=1_200,
    payload={
        "defense_bonus": 2,
        "speed_multiplier": 1.15,
        "announce_on_phase_change": True,
    },
)

RUSK_TOLL_BANNER_PHASE = BossPhaseDef(
    phase_id="toll_banner",
    starts_below_hp_pct=1.0,
    title="Toll Banner",
    abilities=("toll_banner",),
)

RUSK_SMOKE_RETREAT_PHASE = BossPhaseDef(
    phase_id="smoke_retreat",
    starts_below_hp_pct=0.5,
    title="Smoke Retreat",
    abilities=("smoke_retreat",),
    on_enter_event="boss_phase_changed",
)

RUSK_BLACKBANNER_BOSS_DEF = BossDef(
    boss_type="bandit_lord",
    display_name_template="Rusk Blackbanner",
    base_enemy_type="bandit_lord",
    difficulty_tier=2,
    phases=(RUSK_TOLL_BANNER_PHASE, RUSK_SMOKE_RETREAT_PHASE),
    abilities=(RUSK_TOLL_BANNER, RUSK_SMOKE_RETREAT),
    loot_table_id="bandit_lord_boss_loot",
    weakness_tags=("focus-fire", "burst", "anti-armor"),
    memory_tags=("defeated_by", "killed_hero"),
)

BOSS_DEFS: dict[str, BossDef] = {
    WARCHIEF_BOSS_DEF.boss_type: WARCHIEF_BOSS_DEF,
    RUSK_BLACKBANNER_BOSS_DEF.boss_type: RUSK_BLACKBANNER_BOSS_DEF,
}


def get_boss_def(boss_type: str) -> BossDef:
    """Look up a boss definition by boss type."""
    return BOSS_DEFS[str(boss_type)]


def boss_def_for_enemy_type(enemy_type: str) -> BossDef | None:
    """Return a boss definition for an enemy type, if one exists."""
    return BOSS_DEFS.get(str(enemy_type))
