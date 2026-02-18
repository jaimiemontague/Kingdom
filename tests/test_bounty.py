from __future__ import annotations

from config import TILE_SIZE
from game.systems.bounty import BountySystem


def test_place_bounty_creates_object_and_updates_totals() -> None:
    system = BountySystem()

    bounty = system.place_bounty(64, 96, reward=75, bounty_type="explore")

    assert bounty in system.bounties
    assert bounty.reward == 75
    assert bounty.bounty_type == "explore"
    assert system.total_spent == 75


def test_check_claims_proximity_claims_explore_only(make_hero, make_building) -> None:
    system = BountySystem()
    hero = make_hero(name="Scout", x=64, y=64)
    explore = system.place_bounty(64, 64, reward=50, bounty_type="explore")
    lair_target = make_building(building_type="goblin_lair", hp=100, is_lair=True)
    attack_lair = system.place_bounty(64, 64, reward=80, bounty_type="attack_lair", target=lair_target)

    claimed = system.check_claims([hero])

    assert len(claimed) == 1
    assert claimed[0][0] is explore
    assert explore.claimed is True
    assert attack_lair.claimed is False
    assert hero.gold == 50


def test_attack_lair_bounty_validity_depends_on_live_target(make_building) -> None:
    system = BountySystem()
    lair = make_building(building_type="goblin_lair", hp=80, is_lair=True)
    bounty = system.place_bounty(100, 100, reward=60, bounty_type="attack_lair", target=lair)

    assert bounty.is_valid([lair]) is True

    lair.hp = 0
    assert bounty.is_valid([lair]) is False


def test_cleanup_removes_claimed_bounties(make_hero) -> None:
    system = BountySystem()
    hero = make_hero(x=32, y=32)
    bounty = system.place_bounty(32, 32, reward=25, bounty_type="explore")

    system.check_claims([hero])
    system.cleanup()

    assert bounty not in system.bounties
    assert len(system.bounties) == 0


def test_update_ui_metrics_sets_responders_and_tier(make_hero) -> None:
    system = BountySystem()
    bounty = system.place_bounty(64, 64, reward=150, bounty_type="explore")
    hero = make_hero(name="Responder", x=0, y=0)
    hero.target = {"type": "bounty", "bounty_id": bounty.bounty_id}
    system._ui_last_update_ms = -10_000

    system.update_ui_metrics([hero], enemies=[], buildings=[])

    assert bounty.responders >= 1
    assert bounty.attractiveness_tier == "high"
    assert bounty.ui_responders >= 1


def test_summarize_for_hero_returns_sorted_candidate_dicts(make_hero, make_building) -> None:
    system = BountySystem()
    hero = make_hero(name="Planner", x=0, y=0)
    near_explore = system.place_bounty(1 * TILE_SIZE, 0, reward=20, bounty_type="explore")
    far_explore = system.place_bounty(8 * TILE_SIZE, 0, reward=100, bounty_type="explore")
    dead_lair = make_building(building_type="goblin_lair", hp=0, is_lair=True)
    invalid_lair = system.place_bounty(2 * TILE_SIZE, 0, reward=90, bounty_type="attack_lair", target=dead_lair)
    game_state = {"buildings": [dead_lair], "enemies": []}

    summary = system.summarize_for_hero(hero, game_state, limit=5)

    assert len(summary) == 3
    assert summary[0]["id"] == near_explore.bounty_id
    assert summary[1]["id"] == far_explore.bounty_id
    assert summary[2]["id"] == invalid_lair.bounty_id
    assert summary[0]["valid"] is True
    assert summary[2]["valid"] is False
    assert {"id", "type", "reward", "goal", "distance_tiles", "risk", "valid"} <= set(summary[0].keys())


def test_get_unclaimed_bounties_excludes_claimed(make_hero) -> None:
    system = BountySystem()
    hero = make_hero(x=10, y=10)
    claimed = system.place_bounty(10, 10, reward=10, bounty_type="explore")
    unclaimed = system.place_bounty(400, 400, reward=10, bounty_type="explore")

    system.check_claims([hero])
    remaining = system.get_unclaimed_bounties()

    assert claimed not in remaining
    assert unclaimed in remaining
