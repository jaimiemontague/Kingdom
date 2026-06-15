"""WK141 Blackbanner elite gameplay tests."""

from __future__ import annotations

import pytest

from game.content.quest_chains import BLACKBANNER_TOLL_TAKER_STORY_NAME, designate_blackbanner_toll_taker
from game.entities.enemy import Bandit
from game.sim.timebase import set_sim_now_ms


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


def _designate_fixed_bandit(chain_id: int):
    enemy = Bandit(96.0, 128.0)
    enemy.entity_id = "bandit_fixed"
    facts = designate_blackbanner_toll_taker(
        enemy,
        chain_id=chain_id,
        now_ms=4_000,
        nearby_enemies=(),
    )
    return enemy, facts


def test_blackbanner_toll_taker_designation_is_deterministic():
    first, first_facts = _designate_fixed_bandit(chain_id=17)
    second, second_facts = _designate_fixed_bandit(chain_id=17)

    assert first.is_elite is True
    assert first.name == BLACKBANNER_TOLL_TAKER_STORY_NAME
    assert first.elite_story_name == BLACKBANNER_TOLL_TAKER_STORY_NAME
    assert first.elite_name == BLACKBANNER_TOLL_TAKER_STORY_NAME
    assert first.elite_affix_ids == second.elite_affix_ids
    assert first.elite_facts == second.elite_facts

    assert first_facts[-1]["event"] == "blackbanner_toll_taker_designated"
    assert first_facts[-1]["phase_id"] == "intercept_toll_taker"
    assert first_facts[-1]["phase_title"] == "Intercept the Toll-Taker"
    assert first_facts[-1]["spawn_key"] == "blackbanner_toll:17:toll_taker"
    assert first_facts[-1]["story_name"] == BLACKBANNER_TOLL_TAKER_STORY_NAME
    assert first_facts[-1]["time_ms"] == 4_000
    assert first_facts[-1]["elite_affix_ids"] == first.elite_affix_ids

