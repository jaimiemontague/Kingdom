from __future__ import annotations

from random import Random
from types import SimpleNamespace

import pytest

from ai.behaviors import daily_life
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.world import Visibility


class _Hero:
    def __init__(
        self,
        hero_id: str,
        name: str,
        hero_class: str,
        personality: str,
        x: float,
        y: float,
        *,
        hp: int = 100,
        max_hp: int = 100,
        gold: int = 0,
    ) -> None:
        self.hero_id = hero_id
        self.name = name
        self.hero_class = hero_class
        self.personality = personality
        self.x = float(x)
        self.y = float(y)
        self.hp = int(hp)
        self.max_hp = int(max_hp)
        self.gold = int(gold)
        self.state = HeroState.IDLE
        self.target = None
        self.target_position = None
        self.intent = "idle"
        self.last_decision = None
        self.damage_since_left_home = 0
        self.home_building = None

    @property
    def health_percent(self) -> float:
        return float(self.hp) / float(self.max_hp) if self.max_hp else 1.0

    def distance_to(self, x: float, y: float) -> float:
        from math import hypot

        return hypot(self.x - float(x), self.y - float(y))

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))

    def record_decision(self, *, action: str, reason: str, now_ms: int, context: dict) -> None:
        self.last_decision = {
            "action": action,
            "reason": reason,
            "now_ms": int(now_ms),
            "context": dict(context),
        }


class _Building:
    def __init__(self, building_type: str, x: float, y: float, **attrs) -> None:
        self.building_type = building_type
        self.center_x = float(x)
        self.center_y = float(y)
        self.entity_id = attrs.pop("entity_id", building_type)
        for key, value in attrs.items():
            setattr(self, key, value)


class _PoiDef:
    def __init__(self, display_name: str, interaction_type: str, difficulty_tier: int, size: tuple[int, int] = (1, 1)) -> None:
        self.display_name = display_name
        self.interaction_type = interaction_type
        self.difficulty_tier = difficulty_tier
        self.size = size


class _Poi:
    def __init__(self, grid_x: int, grid_y: int, poi_def: _PoiDef) -> None:
        self.grid_x = int(grid_x)
        self.grid_y = int(grid_y)
        self.poi_def = poi_def
        self.is_discovered = True
        self.is_seen = True
        self.is_depleted = False
        self.is_interacted = False


class _Enemy:
    def __init__(self, x: float, y: float, name: str = "Goblin") -> None:
        self.x = float(x)
        self.y = float(y)
        self.is_alive = True
        self.name = name


class _World:
    def __init__(self, size: int = 40, *, seen_center: tuple[int, int] = (12, 12)) -> None:
        self.width = int(size)
        self.height = int(size)
        self.visibility = [[Visibility.UNSEEN for _ in range(size)] for _ in range(size)]
        cx, cy = seen_center
        for y in range(cy - 2, cy + 3):
            for x in range(cx - 2, cx + 3):
                if 0 <= x < size and 0 <= y < size:
                    self.visibility[y][x] = Visibility.SEEN
        if 0 <= cx + 1 < size and 0 <= cy - 3 < size:
            self.visibility[cy - 3][cx + 1] = Visibility.VISIBLE


class _AI:
    def __init__(self, seed: int = 11) -> None:
        self._ai_rng = Random(seed)
        self._debug_log = lambda *args, **kwargs: None
        self.bounty_behavior = SimpleNamespace(maybe_take_bounty=lambda *_a, **_k: False)
        self.shopping_behavior = SimpleNamespace(
            find_marketplace_with_potions=lambda *_a, **_k: None,
            find_blacksmith=lambda *_a, **_k: None,
        )
        self.bounty_assign_ttl_ms = 15_000
        self.bounty_pick_cooldown_ms = 2_500
        self.bounty_max_pursue_ms = 35_000
        self.bounty_claim_radius_px = TILE_SIZE * 2


def _best_motive(ai: _AI, hero: _Hero, view: SimpleNamespace) -> str:
    daily_life.reset_ambient_memory(hero.hero_id)
    picked = daily_life.try_daily_life(ai, hero, view)
    assert picked is True
    return daily_life.get_ambient_snapshot(hero)["active_motive"]


def _frontier_world() -> SimpleNamespace:
    world = _World(seen_center=(18, 10))
    hero = _Hero("ranger", "Rin", "ranger", "balanced and reliable", 18 * TILE_SIZE, 10 * TILE_SIZE)
    view = SimpleNamespace(world=world, buildings=[], heroes=[hero], pois=[], enemies=[], bounties=[], castle=None)
    return view


def _warrior_world() -> SimpleNamespace:
    hero = _Hero("warrior", "Ward", "warrior", "brave and aggressive", 12 * TILE_SIZE, 12 * TILE_SIZE)
    enemy = _Enemy(hero.x + 6 * TILE_SIZE, hero.y)
    lair = _Building("lair", hero.x + 14 * TILE_SIZE, hero.y, is_lair=True, hp=100)
    view = SimpleNamespace(world=None, buildings=[lair], heroes=[hero], pois=[], enemies=[enemy], bounties=[], castle=None)
    return view


def _rogue_world() -> SimpleNamespace:
    hero = _Hero("rogue", "Rue", "rogue", "greedy but cowardly", 15 * TILE_SIZE, 15 * TILE_SIZE, gold=80)
    poi = _Poi(18, 11, _PoiDef("Ancient Shrine", "shrine", 2))
    herald = _Building("herald_post", 17 * TILE_SIZE, 15 * TILE_SIZE)
    marketplace = _Building("marketplace", 13 * TILE_SIZE, 15 * TILE_SIZE)
    blacksmith = _Building("blacksmith", 19 * TILE_SIZE, 15 * TILE_SIZE)
    view = SimpleNamespace(
        world=_World(seen_center=(15, 15)),
        buildings=[herald, marketplace, blacksmith],
        heroes=[hero],
        pois=[poi],
        enemies=[],
        bounties=[],
        castle=None,
    )
    return view


def _cleric_world() -> SimpleNamespace:
    hero = _Hero("cleric", "Celia", "cleric", "cautious and strategic", 15 * TILE_SIZE, 15 * TILE_SIZE, hp=35)
    castle = _Building("castle", 15 * TILE_SIZE, 15 * TILE_SIZE)
    inn = _Building("inn", 17 * TILE_SIZE, 15 * TILE_SIZE)
    temple = _Building("temple", 15 * TILE_SIZE, 19 * TILE_SIZE)
    view = SimpleNamespace(
        world=_World(seen_center=(15, 15)),
        buildings=[castle, inn, temple],
        heroes=[hero],
        pois=[],
        enemies=[],
        bounties=[],
        castle=castle,
    )
    hero.home_building = castle
    return view


@pytest.mark.parametrize(
    ("builder", "expected"),
    [
        (_frontier_world, "wilderness_explore"),
        (_warrior_world, "monster_patrol"),
        (_rogue_world, "opportunity_check"),
        (_cleric_world, "safe_rest"),
    ],
)
def test_class_bias_selects_the_expected_daily_life_motive(builder, expected, monkeypatch) -> None:
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: 20_000)
    ai = _AI()
    view = builder()
    hero = view.heroes[0]

    motive = _best_motive(ai, hero, view)

    assert motive == expected


def test_crowding_penalty_discourages_heroes_from_the_same_cluster() -> None:
    ai = _AI()
    hero_a = _Hero("crowd_a", "A", "warrior", "balanced and reliable", 10 * TILE_SIZE, 10 * TILE_SIZE)
    hero_b = _Hero("crowd_b", "B", "warrior", "balanced and reliable", 10 * TILE_SIZE, 10 * TILE_SIZE)
    view = SimpleNamespace(world=None, buildings=[], heroes=[hero_a, hero_b], pois=[], enemies=[], bounties=[], castle=None)

    crowded_candidate = daily_life.AmbientCandidate(
        motive="kingdom_roam",
        target_key="cluster-a",
        target_xy=(6 * TILE_SIZE, 10 * TILE_SIZE),
        primitive="patrol",
        base_score=20.0,
        cluster_key="shared-cluster",
    )
    open_candidate = daily_life.AmbientCandidate(
        motive="kingdom_roam",
        target_key="cluster-b",
        target_xy=(14 * TILE_SIZE, 10 * TILE_SIZE),
        primitive="patrol",
        base_score=20.0,
        cluster_key="other-cluster",
    )

    daily_life._write_ambient_memory(hero_a, crowded_candidate, now_ms=1_000)
    score_crowded = daily_life.score_daily_life_candidate(ai, hero_b, crowded_candidate, view, now_ms=1_000)
    score_open = daily_life.score_daily_life_candidate(ai, hero_b, open_candidate, view, now_ms=1_000)

    assert score_open > score_crowded + 5.0


def test_recent_target_cooldown_prevents_immediate_looping() -> None:
    ai = _AI()
    hero = _Hero("loop", "Loop", "warrior", "balanced and reliable", 10 * TILE_SIZE, 10 * TILE_SIZE)
    view = SimpleNamespace(world=None, buildings=[], heroes=[hero], pois=[], enemies=[], bounties=[], castle=None)

    recent_candidate = daily_life.AmbientCandidate(
        motive="kingdom_roam",
        target_key="recent-target",
        target_xy=(6 * TILE_SIZE, 10 * TILE_SIZE),
        primitive="patrol",
        base_score=20.0,
        cluster_key="loop-a",
        cooldown_ms=60_000,
    )
    alternate_candidate = daily_life.AmbientCandidate(
        motive="kingdom_roam",
        target_key="alternate-target",
        target_xy=(14 * TILE_SIZE, 10 * TILE_SIZE),
        primitive="patrol",
        base_score=20.0,
        cluster_key="loop-b",
    )

    daily_life._write_ambient_memory(hero, recent_candidate, now_ms=1_000)
    score_recent = daily_life.score_daily_life_candidate(ai, hero, recent_candidate, view, now_ms=1_000)
    score_alternate = daily_life.score_daily_life_candidate(ai, hero, alternate_candidate, view, now_ms=1_000)

    assert score_alternate > score_recent + 90.0
