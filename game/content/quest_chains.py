"""Declarative quest-chain content registry."""

from __future__ import annotations

from dataclasses import dataclass


SCOUT_LOCATION = "scout_location"
COLLECT_ITEM = "collect_item"
DELIVER_ITEM = "deliver_item"


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


QUEST_CHAIN_DEFS: dict[str, QuestChainDef] = {
    RELIC_OF_THE_OLD_SHRINE.chain_type: RELIC_OF_THE_OLD_SHRINE,
}


def get_chain_def(chain_type: str) -> QuestChainDef:
    """Return a chain definition by id."""
    return QUEST_CHAIN_DEFS[str(chain_type)]


def all_chain_defs() -> tuple[QuestChainDef, ...]:
    return tuple(QUEST_CHAIN_DEFS.values())
