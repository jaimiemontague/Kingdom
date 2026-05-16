"""Tests for WK55 POI awareness in hero AI context and personality scoring."""

from __future__ import annotations

import math

from ai.behaviors.poi_awareness import (
    DISCOVERED_POI_RADIUS_TILES,
    MAX_CONTEXT_POIS,
    PERSONALITY_POI_WEIGHTS,
    UNDISCOVERED_SEEN_POI_RADIUS_TILES,
    _compass_direction,
    get_nearby_pois_for_hero,
    maybe_visit_poi,
    score_poi_for_personality,
)
from config import TILE_SIZE
from game.world import Visibility


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _POIDefinition:
    def __init__(
        self,
        *,
        display_name="Test POI",
        interaction_type="shrine",
        difficulty_tier=1,
        size=(1, 1),
        description="A test POI.",
        rarity="common",
        poi_type="poi_shrine",
    ):
        self.display_name = display_name
        self.interaction_type = interaction_type
        self.difficulty_tier = difficulty_tier
        self.size = size
        self.description = description
        self.rarity = rarity
        self.poi_type = poi_type


class _POI:
    def __init__(
        self,
        *,
        grid_x=10,
        grid_y=10,
        poi_def=None,
        is_discovered=True,
        is_depleted=False,
        is_interacted=False,
    ):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.poi_def = poi_def or _POIDefinition()
        self.is_discovered = is_discovered
        self.is_depleted = is_depleted
        self.is_interacted = is_interacted
        self.is_poi = True


class _Hero:
    def __init__(
        self,
        *,
        x=5.0 * TILE_SIZE,
        y=5.0 * TILE_SIZE,
        personality="balanced and reliable",
        level=2,
        name="Tester",
    ):
        self.x = float(x)
        self.y = float(y)
        self.world_x = self.x
        self.world_y = self.y
        self.personality = personality
        self.level = level
        self.name = name
        self.target = None
        self.target_position = None
        self.state = None
        self.is_alive = True

    def set_target_position(self, x: float, y: float) -> None:
        self.target_position = (float(x), float(y))

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - x, self.y - y)


class _World:
    def __init__(self, *, width=50, height=50, default_vis=Visibility.SEEN):
        self.width = width
        self.height = height
        self.visibility = [[default_vis for _ in range(width)] for _ in range(height)]


class _AI:
    def __init__(self):
        self._debug_log = lambda *a, **kw: None

        class _RNG:
            def random(self):
                return 0.0

            def uniform(self, a, b):
                return (a + b) / 2

        self._ai_rng = _RNG()


# ---------------------------------------------------------------------------
# Tests: compass direction
# ---------------------------------------------------------------------------


def test_compass_direction_east():
    assert _compass_direction(10.0, 0.0) == "east"


def test_compass_direction_north():
    # Negative dy = north in screen coords.
    assert _compass_direction(0.0, -10.0) == "north"


def test_compass_direction_southwest():
    assert _compass_direction(-10.0, 10.0) == "southwest"


def test_compass_direction_here():
    assert _compass_direction(0.0, 0.0) == "here"


# ---------------------------------------------------------------------------
# Tests: get_nearby_pois_for_hero
# ---------------------------------------------------------------------------


def test_discovered_poi_included_in_context():
    hero = _Hero(x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    poi = _POI(grid_x=10, grid_y=5, is_discovered=True)
    game_state = {"pois": [poi], "world": _World()}

    result = get_nearby_pois_for_hero(hero, game_state)

    assert len(result) == 1
    assert result[0]["name"] == "Test POI"
    assert result[0]["type"] == "shrine"
    assert result[0]["distance_tiles"] > 0
    assert result[0]["direction"] == "east"
    assert result[0]["depleted"] is False
    assert result[0]["previously_visited"] is False


def test_undiscovered_poi_in_seen_fog_shows_as_unknown():
    hero = _Hero(x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    world = _World(default_vis=Visibility.SEEN)  # all tiles in seen fog
    poi = _POI(grid_x=10, grid_y=5, is_discovered=False)
    game_state = {"pois": [poi], "world": world}

    result = get_nearby_pois_for_hero(hero, game_state)

    assert len(result) == 1
    assert result[0]["name"] == "Unknown Structure"
    assert result[0]["type"] == "unknown"
    assert "description" in result[0]


def test_undiscovered_poi_in_unseen_fog_excluded():
    hero = _Hero(x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    world = _World(default_vis=Visibility.UNSEEN)  # all tiles black fog
    poi = _POI(grid_x=10, grid_y=5, is_discovered=False)
    game_state = {"pois": [poi], "world": world}

    result = get_nearby_pois_for_hero(hero, game_state)

    assert len(result) == 0


def test_poi_beyond_radius_excluded():
    hero = _Hero(x=0, y=0)
    # Place POI far away (beyond 30 tiles).
    far_gx = int(DISCOVERED_POI_RADIUS_TILES + 10)
    poi = _POI(grid_x=far_gx, grid_y=0, is_discovered=True)
    game_state = {"pois": [poi], "world": _World()}

    result = get_nearby_pois_for_hero(hero, game_state)

    assert len(result) == 0


def test_max_context_pois_respected():
    hero = _Hero(x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    pois = [
        _POI(grid_x=5 + i, grid_y=5, is_discovered=True)
        for i in range(1, MAX_CONTEXT_POIS + 5)
    ]
    game_state = {"pois": pois, "world": _World()}

    result = get_nearby_pois_for_hero(hero, game_state)

    assert len(result) <= MAX_CONTEXT_POIS


def test_depleted_poi_shows_depleted_flag():
    hero = _Hero(x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    poi = _POI(grid_x=7, grid_y=5, is_discovered=True, is_depleted=True)
    game_state = {"pois": [poi], "world": _World()}

    result = get_nearby_pois_for_hero(hero, game_state)

    assert len(result) == 1
    assert result[0]["depleted"] is True


# ---------------------------------------------------------------------------
# Tests: score_poi_for_personality
# ---------------------------------------------------------------------------


def test_brave_hero_prefers_combat_poi():
    hero = _Hero(personality="brave and aggressive")
    combat_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="combat", difficulty_tier=2),
    )
    shrine_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="shrine", difficulty_tier=1),
    )

    combat_score = score_poi_for_personality(hero, combat_poi, dist_tiles=5.0)
    shrine_score = score_poi_for_personality(hero, shrine_poi, dist_tiles=5.0)

    assert combat_score > shrine_score


def test_cautious_hero_prefers_shrine_over_boss():
    hero = _Hero(personality="cautious and strategic")
    shrine_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="shrine", difficulty_tier=1),
    )
    boss_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="boss", difficulty_tier=5),
    )

    shrine_score = score_poi_for_personality(hero, shrine_poi, dist_tiles=5.0)
    boss_score = score_poi_for_personality(hero, boss_poi, dist_tiles=5.0)

    assert shrine_score > boss_score


def test_greedy_hero_prefers_loot():
    hero = _Hero(personality="greedy but cowardly")
    loot_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="loot", difficulty_tier=1),
    )
    knowledge_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="knowledge", difficulty_tier=1),
    )

    loot_score = score_poi_for_personality(hero, loot_poi, dist_tiles=5.0)
    knowledge_score = score_poi_for_personality(hero, knowledge_poi, dist_tiles=5.0)

    assert loot_score > knowledge_score


def test_cautious_hero_avoids_high_difficulty():
    hero = _Hero(personality="cautious and strategic", level=1)
    easy_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="combat", difficulty_tier=1),
    )
    hard_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="combat", difficulty_tier=4),
    )

    easy_score = score_poi_for_personality(hero, easy_poi, dist_tiles=5.0)
    hard_score = score_poi_for_personality(hero, hard_poi, dist_tiles=5.0)

    assert easy_score > hard_score


def test_depleted_poi_scores_low():
    hero = _Hero(personality="balanced and reliable")
    fresh_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="loot"),
        is_depleted=False,
    )
    depleted_poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="loot"),
        is_depleted=True,
    )

    fresh_score = score_poi_for_personality(hero, fresh_poi, dist_tiles=5.0)
    depleted_score = score_poi_for_personality(hero, depleted_poi, dist_tiles=5.0)

    assert fresh_score > depleted_score * 5


def test_distance_penalizes_score():
    hero = _Hero(personality="balanced and reliable")
    poi = _POI(
        grid_x=10, grid_y=5,
        poi_def=_POIDefinition(interaction_type="shrine"),
    )

    close_score = score_poi_for_personality(hero, poi, dist_tiles=2.0)
    far_score = score_poi_for_personality(hero, poi, dist_tiles=25.0)

    assert close_score > far_score


# ---------------------------------------------------------------------------
# Tests: maybe_visit_poi
# ---------------------------------------------------------------------------


def test_maybe_visit_poi_returns_true_when_suitable_poi_nearby():
    from game.entities.hero import HeroState

    hero = _Hero(personality="brave and aggressive", x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    hero.state = HeroState.IDLE  # need a real state for the function
    poi = _POI(
        grid_x=8, grid_y=5,
        poi_def=_POIDefinition(interaction_type="combat", difficulty_tier=2),
        is_discovered=True,
        is_depleted=False,
    )
    game_state = {"pois": [poi], "world": _World()}
    ai = _AI()

    result = maybe_visit_poi(ai, hero, game_state)

    assert result is True
    assert hero.target is not None
    assert hero.target.get("type") == "visit_poi"
    assert hero.target_position is not None


def test_maybe_visit_poi_returns_false_when_no_pois():
    hero = _Hero(personality="balanced and reliable")
    game_state = {"pois": [], "world": _World()}
    ai = _AI()

    result = maybe_visit_poi(ai, hero, game_state)

    assert result is False


def test_maybe_visit_poi_skips_depleted():
    hero = _Hero(personality="greedy but cowardly", x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    poi = _POI(
        grid_x=8, grid_y=5,
        poi_def=_POIDefinition(interaction_type="loot"),
        is_discovered=True,
        is_depleted=True,
    )
    game_state = {"pois": [poi], "world": _World()}
    ai = _AI()

    result = maybe_visit_poi(ai, hero, game_state)

    assert result is False


# ---------------------------------------------------------------------------
# Tests: context_builder integration
# ---------------------------------------------------------------------------


def test_context_builder_includes_nearby_pois():
    """Verify the ContextBuilder.build_hero_context includes nearby_pois key."""
    from ai.context_builder import ContextBuilder

    class _FullHero(_Hero):
        def __init__(self):
            super().__init__(personality="balanced and reliable")
            self.hero_id = "h1"
            self.hero_class = "warrior"
            self.hp = 100
            self.max_hp = 100
            self.health_percent = 1.0
            self.gold = 50
            self.attack = 10
            self.defense = 5
            self.xp = 0
            self.xp_to_level = 100
            self.weapon = {"name": "Sword", "attack": 5}
            self.armor = {"name": "Shield", "defense": 3}
            self.potions = 2
            self.home_building = None
            self.is_inside_building = False
            self.inside_building = None
            self.pending_llm_decision = False
            self.last_llm_decision_time = 0
            self.profile_memory = ()

            class _State:
                name = "IDLE"
            self.state = _State()

        def distance_to(self, x, y):
            return math.hypot(self.x - x, self.y - y)

    hero = _FullHero()
    poi = _POI(grid_x=8, grid_y=5, is_discovered=True)
    game_state = {
        "pois": [poi],
        "world": _World(),
        "heroes": [hero],
        "enemies": [],
        "buildings": [],
        "bounties": [],
    }

    context = ContextBuilder.build_hero_context(hero, game_state)

    assert "nearby_pois" in context
    assert len(context["nearby_pois"]) >= 1
    assert context["nearby_pois"][0]["name"] == "Test POI"
