from __future__ import annotations

from collections import Counter
from random import Random
from types import SimpleNamespace

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
    def __init__(self, size: int = 40) -> None:
        self.width = int(size)
        self.height = int(size)
        self.visibility = [[Visibility.UNSEEN for _ in range(size)] for _ in range(size)]
        for y in range(12, 19):
            for x in range(12, 19):
                self.visibility[y][x] = Visibility.SEEN
        for y in range(6, 12):
            self.visibility[y][18] = Visibility.SEEN
        for x in range(18, 26):
            self.visibility[10][x] = Visibility.SEEN
        self.visibility[5][18] = Visibility.VISIBLE


class _FixedAI:
    def __init__(self, seed: int = 7) -> None:
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


def _build_view() -> tuple[SimpleNamespace, list[_Hero]]:
    castle = _Building("castle", 15 * TILE_SIZE, 15 * TILE_SIZE)
    inn = _Building("inn", 17 * TILE_SIZE, 15 * TILE_SIZE)
    market = _Building("marketplace", 13 * TILE_SIZE, 15 * TILE_SIZE)
    blacksmith = _Building("blacksmith", 19 * TILE_SIZE, 15 * TILE_SIZE)
    herald = _Building("herald_post", 15 * TILE_SIZE, 17 * TILE_SIZE)
    house = _Building("house", 11 * TILE_SIZE, 15 * TILE_SIZE)
    temple = _Building("temple", 15 * TILE_SIZE, 19 * TILE_SIZE)
    warrior_guild = _Building("warrior_guild", 9 * TILE_SIZE, 15 * TILE_SIZE)
    ranger_guild = _Building("ranger_guild", 21 * TILE_SIZE, 15 * TILE_SIZE)
    rogue_guild = _Building("rogue_guild", 15 * TILE_SIZE, 21 * TILE_SIZE)
    wizard_guild = _Building("wizard_guild", 15 * TILE_SIZE, 9 * TILE_SIZE)
    lair = _Building("lair", 28 * TILE_SIZE, 26 * TILE_SIZE, is_lair=True, hp=100)

    world = _World()
    pois = [
        _Poi(24, 11, _PoiDef("Ancient Shrine", "shrine", 2)),
        _Poi(9, 25, _PoiDef("Bandit Camp", "combat", 3)),
    ]
    enemies = [_Enemy(27 * TILE_SIZE, 25 * TILE_SIZE)]

    heroes = [
        _Hero("h1", "Aldous", "warrior", "brave and aggressive", castle.center_x, castle.center_y, hp=35),
        _Hero("h2", "Brina", "ranger", "balanced and reliable", castle.center_x + 3 * TILE_SIZE, castle.center_y, gold=12),
        _Hero("h3", "Cora", "rogue", "greedy but cowardly", castle.center_x - TILE_SIZE, castle.center_y, gold=80),
        _Hero("h4", "Doran", "cleric", "cautious and strategic", castle.center_x, castle.center_y + TILE_SIZE, hp=40),
        _Hero("h5", "Elara", "wizard", "balanced and reliable", castle.center_x, castle.center_y - TILE_SIZE, gold=60),
        _Hero("h6", "Fenn", "warrior", "balanced and reliable", castle.center_x + 5 * TILE_SIZE, castle.center_y, gold=30),
        _Hero("h7", "Gwen", "ranger", "brave and aggressive", castle.center_x - 4 * TILE_SIZE, castle.center_y),
        _Hero("h8", "Hale", "rogue", "balanced and reliable", castle.center_x, castle.center_y + 4 * TILE_SIZE, gold=15),
        _Hero("h9", "Iris", "cleric", "greedy but cowardly", castle.center_x, castle.center_y - 4 * TILE_SIZE, hp=80),
        _Hero("h10", "Jory", "wizard", "cautious and strategic", castle.center_x + 6 * TILE_SIZE, castle.center_y),
    ]

    view = SimpleNamespace(
        world=world,
        buildings=[castle, inn, market, blacksmith, herald, house, temple, warrior_guild, ranger_guild, rogue_guild, wizard_guild, lair],
        heroes=heroes,
        pois=pois,
        enemies=enemies,
        bounties=[],
        castle=castle,
    )
    return view, heroes


def _summaries_for(seed: int = 7) -> list[tuple[str, str, str, str]]:
    daily_life.reset_ambient_memory()
    ai = _FixedAI(seed)
    view, heroes = _build_view()

    summaries: list[tuple[str, str, str, str]] = []
    for hero in heroes:
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
    return summaries


def test_daily_life_is_deterministic_for_fixed_setup(monkeypatch) -> None:
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: 20_000)
    first = _summaries_for(seed=17)
    second = _summaries_for(seed=17)

    assert first == second


def test_daily_life_splits_ten_heroes_across_four_motives(monkeypatch) -> None:
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: 20_000)
    summaries = _summaries_for(seed=17)
    counts = Counter(motive for _hero_id, motive, _target_key, _intent in summaries)

    assert len(counts) >= 4
    assert counts["safe_rest"] >= 1
    assert counts["poi_scout"] >= 1
    assert counts["opportunity_check"] >= 1
    assert counts["monster_patrol"] >= 1
    assert all(summary[3] for summary in summaries)
