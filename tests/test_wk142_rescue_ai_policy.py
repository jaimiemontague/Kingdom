"""WK142 rescue/revenge daily-life AI pins."""

from __future__ import annotations

from collections import Counter
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
        self.is_alive = True
        self.is_captured = False
        self.is_inside_building = False
        self.inside_building = None

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
    def __init__(self, grid_x: int, grid_y: int, poi_def: _PoiDef, *, entity_id: str | None = None) -> None:
        self.grid_x = int(grid_x)
        self.grid_y = int(grid_y)
        self.poi_def = poi_def
        self.is_discovered = True
        self.is_seen = True
        self.is_depleted = False
        self.is_interacted = False
        self.entity_id = entity_id or f"poi_{grid_x}_{grid_y}"
        self.poi_type = self.entity_id
        self.building_type = self.entity_id
        self.name = poi_def.display_name

    @property
    def center_x(self) -> float:
        return (self.grid_x + self.poi_def.size[0] / 2) * TILE_SIZE

    @property
    def center_y(self) -> float:
        return (self.grid_y + self.poi_def.size[1] / 2) * TILE_SIZE


class _World:
    def __init__(self, size: int = 40) -> None:
        self.width = int(size)
        self.height = int(size)
        self.visibility = [[Visibility.VISIBLE for _ in range(size)] for _ in range(size)]


class _FixedAI:
    def __init__(self) -> None:
        self._debug_log = lambda *args, **kwargs: None

    def set_intent(self, hero, intent: str) -> None:
        hero.intent = str(intent or "idle")

    def record_decision(self, hero, **kwargs) -> None:
        hero.record_decision(**kwargs)


def _build_view(*, heroes: list[_Hero]) -> SimpleNamespace:
    rescue_fortress = _Poi(1, 1, _PoiDef("Bandit Fortress", "combat", 3), entity_id="poi_bandit_fortress")
    rescue_fortress.is_discovered = False
    rescue_fortress.is_seen = False
    shrine = _Poi(24, 11, _PoiDef("Ancient Shrine", "shrine", 2), entity_id="poi_ancient_shrine")

    boss = SimpleNamespace(
        boss_id="boss_rusk_blackbanner",
        entity_id="boss_rusk_blackbanner",
        boss_type="bandit_lord",
        name="Rusk Blackbanner",
        is_alive=True,
        status="remembered",
        current_phase="toll_banner",
        current_phase_title="Toll Banner",
        hp_pct=0.61,
        position=(28 * TILE_SIZE, 26 * TILE_SIZE),
        target_hero_id=None,
        latest_telegraph="toll_banner",
    )

    return SimpleNamespace(
        world=_World(),
        buildings=[],
        heroes=heroes,
        pois=[rescue_fortress, shrine],
        enemies=[],
        bounties=[],
        captured_heroes=(
            {
                "hero_id": "wk142_captive",
                "hero_name": "Astra",
                "captor_boss_id": "boss_rusk_blackbanner",
                "captor_boss_name": "Rusk Blackbanner",
                "captor_boss_type": "bandit_lord",
                "location_id": "poi_bandit_fortress",
                "location_name": "Bandit Fortress",
                "source_chain_id": "chain_blackbanner_cells",
                "source_chain_type": "blackbanners_toll",
                "captured_at_ms": 1_000,
                "status": "captured",
            },
        ),
        rescue_opportunities=(
            {
                "rescue_id": "rescue_blackbanner_cells",
                "captured_hero_id": "wk142_captive",
                "captured_hero_name": "Astra",
                "captor_boss_id": "boss_rusk_blackbanner",
                "captor_boss_name": "Rusk Blackbanner",
                "captor_boss_type": "bandit_lord",
                "target_location_id": "poi_bandit_fortress",
                "target_location_name": "Bandit Fortress",
                "current_phase_id": "reach_fortress",
                "current_phase_title": "Reach the Bandit Fortress",
                "source_chain_id": "chain_blackbanner_cells",
                "source_chain_type": "blackbanners_toll",
                "status": "active",
                "offered_at_ms": 1_100,
            },
        ),
        boss_kill_memories=(
            {
                "boss_id": "boss_rusk_blackbanner",
                "boss_name": "Rusk Blackbanner",
                "boss_type": "bandit_lord",
                "fallen_hero_id": "wk142_fallen",
                "fallen_hero_name": "Mira",
                "location_id": "poi_bandit_fortress",
                "location_name": "Bandit Fortress",
                "killed_at_ms": 2_000,
                "revenge_chain_id": "revenge_rusk_mira",
                "status": "remembered",
            },
        ),
        revenge_opportunities=(
            {
                "revenge_id": "revenge_rusk_mira",
                "boss_id": "boss_rusk_blackbanner",
                "boss_name": "Rusk Blackbanner",
                "boss_type": "bandit_lord",
                "fallen_hero_id": "wk142_fallen",
                "fallen_hero_name": "Mira",
                "target_location_id": "poi_bandit_fortress",
                "target_location_name": "Bandit Fortress",
                "current_phase_id": "avenge_fallen_hero",
                "current_phase_title": "Avenge Mira",
                "revenge_chain_id": "revenge_rusk_mira",
                "status": "active",
                "offered_at_ms": 2_050,
            },
        ),
        boss_encounters=(boss,),
        elite_enemies=(),
        elite_encounters=(),
        castle=None,
    )


def _hero(
    hero_id: str,
    name: str,
    hero_class: str,
    personality: str,
    x: float,
    y: float,
    *,
    hp: int = 100,
    gold: int = 0,
) -> _Hero:
    return _Hero(hero_id, name, hero_class, personality, x, y, hp=hp, gold=gold)


@pytest.fixture(autouse=True)
def _reset_memory():
    daily_life.reset_ambient_memory()
    yield
    daily_life.reset_ambient_memory()


def test_wk142_captured_heroes_skip_daily_life_and_decision_moments(monkeypatch):
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: 20_000)
    hero = _hero(
        "wk142_captive",
        "Astra",
        "warrior",
        "balanced and reliable",
        15 * TILE_SIZE,
        15 * TILE_SIZE,
    )
    hero.is_captured = True
    hero.state = HeroState.CAPTURED

    view = SimpleNamespace(buildings=[], heroes=[hero], pois=[], enemies=[], bounties=[], castle=None, world=None)
    legacy = {"buildings": [], "enemies": []}

    from ai.decision_moments import determine_decision_moment

    assert determine_decision_moment(hero, legacy, now_ms=20_000) is None
    assert daily_life.try_daily_life(_FixedAI(), hero, view) is False


def test_wk142_story_facts_diversify_daily_life_choices_without_stampedes(monkeypatch):
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: 20_000)
    ai = _FixedAI()

    heroes = [
        _hero(
            "wk142_warrior",
            "Aldous",
            "warrior",
            "brave and aggressive",
            27 * TILE_SIZE,
            25 * TILE_SIZE,
        ),
        _hero(
            "wk142_cleric",
            "Doran",
            "cleric",
            "cautious and strategic",
            1 * TILE_SIZE,
            1 * TILE_SIZE,
            hp=88,
        ),
        _hero(
            "wk142_rogue",
            "Cora",
            "rogue",
            "greedy but cowardly",
            24 * TILE_SIZE,
            11 * TILE_SIZE,
            gold=80,
        ),
    ]
    view = _build_view(heroes=heroes)

    warrior_candidates = daily_life.build_daily_life_candidates(ai, heroes[0], view, now_ms=20_000)
    assert any(candidate.motive == "revenge_hero" for candidate in warrior_candidates)
    assert any(candidate.motive == "rescue_hero" for candidate in warrior_candidates)

    summaries: list[tuple[str, str, str, str]] = []
    for hero in heroes[1:]:
        picked = daily_life.try_daily_life(ai, hero, view)
        assert picked is True
        snapshot = daily_life.get_ambient_snapshot(hero)
        summaries.append(
            (
                hero.hero_id,
                snapshot["active_motive"],
                snapshot["active_target_key"],
                hero.intent,
            )
        )
        assert hero.last_decision is not None
        assert hero.last_decision["action"] == snapshot["active_motive"]

    counts = Counter(motive for _hero_id, motive, _target_key, _intent in summaries)

    assert len(counts) >= 2
    assert counts["rescue_hero"] == 1
    assert counts["revenge_hero"] == 1
    assert len({target_key for _hero_id, motive, target_key, _intent in summaries if motive == "rescue_hero"}) == 1
    assert all(summary[3] for summary in summaries)
