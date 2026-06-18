"""WK146 Herald's Post quest-chain launcher seam tests."""

from __future__ import annotations

import pytest

from game.content.quest_chains import (
    ASHWINGS_HOARD,
    BLACKBANNERS_TOLL,
    RELIC_OF_THE_OLD_SHRINE,
)
from game.entities.buildings.base import Building
from game.entities.hero import Hero
from game.entities.quest_giver import QuestGiver
from game.sim.timebase import set_sim_now_ms
from game.sim_engine import SimEngine


@pytest.fixture(autouse=True)
def _sim_time_reset():
    set_sim_now_ms(0)
    yield
    set_sim_now_ms(0)


def _sim_with_post(*, constructed: bool = True, with_giver: bool = True):
    sim = SimEngine()
    post = Building(10, 10, "herald_post")
    post.is_constructed = bool(constructed)
    post.construction_started = True
    if not constructed:
        post.hp = 1
    sim.buildings.append(post)
    giver = QuestGiver(post)
    if with_giver:
        sim.quest_givers.append(giver)
    return sim, post, giver


def _active_chain_types(sim: SimEngine) -> set[str]:
    return {snapshot.chain_type for snapshot in sim.quest_chain_system.get_active_chain_snapshots()}


def test_constructed_herald_post_launches_all_player_chain_types_into_snapshots():
    sim, _post, giver = _sim_with_post()

    relic = sim.create_quest_chain(giver.giver_id, "relic_of_the_old_shrine")
    blackbanner = sim.create_quest_chain(giver.giver_id, "blackbanners_toll")
    ashwing = sim.create_quest_chain(giver.giver_id, "ashwings_hoard")

    assert relic is not None and relic.status == "active"
    assert blackbanner is not None and blackbanner.status == "active"
    assert ashwing is not None and ashwing.status == "active"
    assert _active_chain_types(sim) == {
        RELIC_OF_THE_OLD_SHRINE.chain_type,
        BLACKBANNERS_TOLL.chain_type,
        ASHWINGS_HOARD.chain_type,
    }

    view = sim.build_ai_view()
    snapshot = sim.build_snapshot(vfx_projectiles=())
    assert {chain.chain_type for chain in view.quest_chains} == _active_chain_types(sim)
    assert {chain.chain_type for chain in snapshot.quest_chains} == _active_chain_types(sim)


@pytest.mark.parametrize(
    "case",
    ("missing_giver", "unconstructed_post", "destroyed_post", "missing_post"),
)
def test_missing_or_invalid_herald_post_returns_none_and_creates_no_chain(case: str):
    sim, post, giver = _sim_with_post(
        constructed=(case != "unconstructed_post"),
        with_giver=(case != "missing_giver"),
    )
    if case == "destroyed_post":
        post.hp = 0
    elif case == "missing_post":
        sim.buildings.remove(post)

    chain = sim.create_quest_chain(giver.giver_id, "relic_of_the_old_shrine")

    assert chain is None
    assert sim.quest_chain_system.chains == []
    assert sim.quest_chain_system.get_active_chain_snapshots() == ()


def test_duplicate_launch_returns_existing_live_chain_without_spam():
    sim, _post, giver = _sim_with_post()

    first = sim.create_quest_chain(giver.giver_id, "blackbanners_toll")
    second = sim.start_quest_chain_from_post(giver.giver_id, "blackbanners_toll")

    assert first is not None
    assert second is first
    assert [
        chain
        for chain in sim.quest_chain_system.chains
        if chain.chain_type == BLACKBANNERS_TOLL.chain_type
    ] == [first]


def test_hero_id_assignment_resolves_the_intended_live_hero_and_accepts_constants():
    sim, _post, giver = _sim_with_post()
    hero_a = Hero(0.0, 0.0, hero_id="hero_a", name="Astra")
    hero_b = Hero(32.0, 0.0, hero_id="hero_b", name="Borin")
    sim.heroes.extend([hero_a, hero_b])

    chain = sim.create_quest_chain(
        giver.giver_id,
        RELIC_OF_THE_OLD_SHRINE,
        hero_id="hero_b",
    )

    assert chain is not None
    assert chain.assigned_hero_id == "hero_b"
    assert chain.offered_to_hero_id == "hero_b"
    assert any(
        record["event"] == "chain_accepted" and record["hero_id"] == "hero_b"
        for record in chain.history
    )


def test_no_chain_default_path_remains_inert_until_explicit_launcher_call():
    sim, _post, giver = _sim_with_post()

    sim.quest_chain_system.update(sim._build_system_context(), 1 / 60)

    assert sim.quest_chain_system.get_active_chain_snapshots() == ()
    assert sim.build_ai_view().quest_chains == ()
    assert giver.is_open is False

    chain = sim.create_quest_chain(giver.giver_id, "relic_of_the_old_shrine", auto_accept=False)

    assert chain is not None and chain.status == "offered"
    assert sim.quest_chain_system.get_active_chain_snapshots()[0].chain_type == (
        RELIC_OF_THE_OLD_SHRINE.chain_type
    )
    assert giver.is_open is True
