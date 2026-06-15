"""Declarative quest-chain content registry."""

from __future__ import annotations

from dataclasses import dataclass

from game.content.elite_affixes import spawn_elite_enemy
from game.sim.timebase import now_ms as sim_now_ms


SCOUT_LOCATION = "scout_location"
COLLECT_ITEM = "collect_item"
DELIVER_ITEM = "deliver_item"

SCOUT_FORTRESS = "scout_fortress"
INTERCEPT_TOLL_TAKER = "intercept_toll_taker"
ASSAULT_GATE = "assault_gate"
SLAY_BLACKBANNER = "slay_blackbanner"
CLAIM_REWARD = "claim_reward"
RESCUE_HERO = "rescue_hero"
SLAY_NAMED_BOSS = "slay_named_boss"
REACH_FORTRESS = "reach_fortress"
AVENGE_FALLEN_HERO = "avenge_fallen_hero"

BLACKBANNER_TOLL_TAKER_NAME = "Blackbanner Toll-Taker"
BLACKBANNER_TOLL_TAKER_STORY_NAME = "Blackbanner Toll-Taker"


@dataclass(frozen=True, slots=True)
class QuestRewardProfile:
    """Immutable reward profile for one chain."""

    gold: int


@dataclass(frozen=True, slots=True)
class QuestPhaseDef:
    """Immutable definition for one quest-chain phase."""

    phase_id: str
    title: str
    objective_type: str
    target_ref: str


@dataclass(frozen=True, slots=True)
class QuestChainDef:
    """Immutable chain definition shared by gameplay and future UI."""

    chain_type: str
    display_name: str
    difficulty_tier: int
    phases: tuple[QuestPhaseDef, ...]
    reward_profile: QuestRewardProfile
    tags: tuple[str, ...] = ()


RELIC_OF_THE_OLD_SHRINE = QuestChainDef(
    chain_type="relic_of_the_old_shrine",
    display_name="Relic of the Old Shrine",
    difficulty_tier=2,
    phases=(
        QuestPhaseDef(
            phase_id=SCOUT_LOCATION,
            title="Scout the Ancient Ruins",
            objective_type=SCOUT_LOCATION,
            target_ref="origin_target",
        ),
        QuestPhaseDef(
            phase_id=COLLECT_ITEM,
            title="Recover the Relic",
            objective_type=COLLECT_ITEM,
            target_ref="origin_target",
        ),
        QuestPhaseDef(
            phase_id=DELIVER_ITEM,
            title="Deliver the Relic",
            objective_type=DELIVER_ITEM,
            target_ref="delivery_target",
        ),
    ),
    reward_profile=QuestRewardProfile(gold=180),
    tags=("relic", "expedition", "shrine"),
)


BLACKBANNERS_TOLL = QuestChainDef(
    chain_type="blackbanners_toll",
    display_name="Blackbanner's Toll",
    difficulty_tier=5,
    phases=(
        QuestPhaseDef(
            phase_id=SCOUT_FORTRESS,
            title="Scout the Bandit Fortress",
            objective_type=SCOUT_FORTRESS,
            target_ref="fortress_target",
        ),
        QuestPhaseDef(
            phase_id=INTERCEPT_TOLL_TAKER,
            title="Intercept the Toll-Taker",
            objective_type=INTERCEPT_TOLL_TAKER,
            target_ref="elite_target",
        ),
        QuestPhaseDef(
            phase_id=ASSAULT_GATE,
            title="Assault the Gate",
            objective_type=ASSAULT_GATE,
            target_ref="gate_target",
        ),
        QuestPhaseDef(
            phase_id=SLAY_BLACKBANNER,
            title="Defeat Rusk Blackbanner",
            objective_type=SLAY_BLACKBANNER,
            target_ref="boss_target",
        ),
        QuestPhaseDef(
            phase_id=CLAIM_REWARD,
            title="Claim the Spoils",
            objective_type=CLAIM_REWARD,
            target_ref="reward_target",
        ),
    ),
    reward_profile=QuestRewardProfile(gold=260),
    tags=("bandit", "siege", "blackbanner"),
)


BLACKBANNER_RESCUE = QuestChainDef(
    chain_type="blackbanner_rescue",
    display_name="Break the Blackbanner Cells",
    difficulty_tier=5,
    phases=(
        QuestPhaseDef(
            phase_id=REACH_FORTRESS,
            title="Reach the Bandit Fortress",
            objective_type=RESCUE_HERO,
            target_ref="origin_target",
        ),
    ),
    reward_profile=QuestRewardProfile(gold=180),
    tags=("bandit", "rescue", "blackbanner"),
)


BLACKBANNER_REVENGE = QuestChainDef(
    chain_type="blackbanner_revenge",
    display_name="Avenge the Fallen",
    difficulty_tier=5,
    phases=(
        QuestPhaseDef(
            phase_id=AVENGE_FALLEN_HERO,
            title="Avenge the Fallen",
            objective_type=SLAY_NAMED_BOSS,
            target_ref="boss_target",
        ),
    ),
    reward_profile=QuestRewardProfile(gold=220),
    tags=("blackbanner", "revenge", "vengeance"),
)


QUEST_CHAIN_DEFS: dict[str, QuestChainDef] = {
    RELIC_OF_THE_OLD_SHRINE.chain_type: RELIC_OF_THE_OLD_SHRINE,
    BLACKBANNERS_TOLL.chain_type: BLACKBANNERS_TOLL,
    BLACKBANNER_RESCUE.chain_type: BLACKBANNER_RESCUE,
    BLACKBANNER_REVENGE.chain_type: BLACKBANNER_REVENGE,
}


def designate_blackbanner_toll_taker(
    enemy: object,
    *,
    chain_id: int,
    now_ms: int | None = None,
    nearby_enemies: tuple[object, ...] | list[object] = (),
) -> tuple[dict[str, object], ...]:
    """Apply the deterministic Blackbanner elite designation to a bandit enemy."""

    spawn_key = f"blackbanner_toll:{int(chain_id)}:toll_taker"
    rolled_facts = list(
        spawn_elite_enemy(
            enemy,
            nearby_enemies=nearby_enemies,
            now_ms=now_ms,
            spawn_key=spawn_key,
        )
    )

    # Keep the affix-derived elite facts, but give the quest chain a stable story
    # name and a distinct phase link for the intercept phase.
    setattr(enemy, "elite_story_name", BLACKBANNER_TOLL_TAKER_STORY_NAME)
    setattr(enemy, "elite_name", BLACKBANNER_TOLL_TAKER_STORY_NAME)
    setattr(enemy, "name", BLACKBANNER_TOLL_TAKER_STORY_NAME)
    designation_fact = {
        "event": "blackbanner_toll_taker_designated",
        "phase_id": INTERCEPT_TOLL_TAKER,
        "phase_title": "Intercept the Toll-Taker",
        "enemy_id": str(getattr(enemy, "entity_id", "") or ""),
        "enemy_type": str(getattr(enemy, "enemy_type", "") or ""),
        "story_name": BLACKBANNER_TOLL_TAKER_STORY_NAME,
        "elite_title": str(getattr(enemy, "elite_title", "") or ""),
        "elite_affix_ids": tuple(getattr(enemy, "elite_affix_ids", ()) or ()),
        "spawn_key": spawn_key,
        "time_ms": int(sim_now_ms() if now_ms is None else now_ms),
    }
    rolled_facts.append(designation_fact)
    enemy.elite_facts = tuple(rolled_facts)
    return enemy.elite_facts


def get_chain_def(chain_type: str) -> QuestChainDef:
    """Return a chain definition by id."""
    return QUEST_CHAIN_DEFS[str(chain_type)]


def all_chain_defs() -> tuple[QuestChainDef, ...]:
    return tuple(QUEST_CHAIN_DEFS.values())
