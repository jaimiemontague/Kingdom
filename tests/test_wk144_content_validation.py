"""WK144 quest-chain content validation tests."""

from __future__ import annotations

from game.content.quest_chains import (
    ASHWINGS_HOARD,
    BLACKBANNER_RESCUE,
    BLACKBANNERS_TOLL,
    BLACKBANNER_REVENGE,
    ASSAULT_GATE,
    CLAIM_HOARD,
    CLAIM_REWARD,
    COLLECT_ITEM,
    DELIVER_ITEM,
    INTERCEPT_TOLL_TAKER,
    PREPARE_HUNT,
    QUEST_CHAIN_DEFS,
    RELIC_OF_THE_OLD_SHRINE,
    RESCUE_HERO,
    SCOUT_FORTRESS,
    SCOUT_LOCATION,
    SLAY_BLACKBANNER,
    SLAY_NAMED_BOSS,
    all_chain_defs,
    get_chain_def,
)


EXPECTED_CHAIN_TYPES = {
    RELIC_OF_THE_OLD_SHRINE.chain_type,
    BLACKBANNERS_TOLL.chain_type,
    BLACKBANNER_RESCUE.chain_type,
    BLACKBANNER_REVENGE.chain_type,
    ASHWINGS_HOARD.chain_type,
}

SUPPORTED_OBJECTIVE_TYPES = {
    SCOUT_LOCATION,
    COLLECT_ITEM,
    DELIVER_ITEM,
    SCOUT_FORTRESS,
    INTERCEPT_TOLL_TAKER,
    ASSAULT_GATE,
    SLAY_BLACKBANNER,
    RESCUE_HERO,
    SLAY_NAMED_BOSS,
    PREPARE_HUNT,
    CLAIM_REWARD,
    CLAIM_HOARD,
}


def test_live_quest_chain_registry_contains_only_the_wk138_wk141_wk142_wk143_chains():
    chains = all_chain_defs()
    chain_types = tuple(chain.chain_type for chain in chains)

    assert set(chain_types) == EXPECTED_CHAIN_TYPES
    assert len(chain_types) == len(EXPECTED_CHAIN_TYPES)
    assert set(QUEST_CHAIN_DEFS) == EXPECTED_CHAIN_TYPES

    for chain in chains:
        assert get_chain_def(chain.chain_type) is chain
        assert QUEST_CHAIN_DEFS[chain.chain_type] is chain


def test_live_quest_chain_definitions_are_authoring_safe():
    for chain in all_chain_defs():
        assert chain.display_name.strip()
        assert chain.difficulty_tier > 0
        assert chain.reward_profile.gold > 0
        assert chain.tags
        assert len(chain.tags) == len(set(chain.tags))
        assert all(tag.strip() for tag in chain.tags)

        phase_ids = [phase.phase_id for phase in chain.phases]
        assert phase_ids
        assert len(phase_ids) == len(set(phase_ids))

        for phase in chain.phases:
            assert phase.phase_id.strip()
            assert phase.title.strip()
            assert phase.objective_type.strip()
            assert phase.target_ref.strip()
            assert phase.objective_type in SUPPORTED_OBJECTIVE_TYPES

    # Keep the current named chain content rooted in the shipped WK138/WK141/WK142/WK143 stories.
    assert RELIC_OF_THE_OLD_SHRINE.chain_type in EXPECTED_CHAIN_TYPES
    assert BLACKBANNERS_TOLL.chain_type in EXPECTED_CHAIN_TYPES
    assert BLACKBANNER_RESCUE.chain_type in EXPECTED_CHAIN_TYPES
    assert BLACKBANNER_REVENGE.chain_type in EXPECTED_CHAIN_TYPES
    assert ASHWINGS_HOARD.chain_type in EXPECTED_CHAIN_TYPES
