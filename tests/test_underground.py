"""Tests for WK57 underground mechanics (Waves 4 + 5).

Covers: UndergroundArea data model, underground fog of war, LayerPathfinder,
hero descent/ascent transitions, underground enemy spawning, retreat logic,
AI dungeon scoring.
"""
import pytest
from game.sim.determinism import set_sim_seed
from game.underground import (
    generate_underground_area, UndergroundArea, UndergroundChamber,
    check_underground_hero_retreat,
)
from game.entities.poi import PointOfInterest, POI_DEFINITIONS
from game.world import World, Visibility


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cave_poi(gx=50, gy=50):
    set_sim_seed(42)
    return PointOfInterest(gx, gy, POI_DEFINITIONS["poi_cave_entrance"])


def _make_area(gx=50, gy=50):
    set_sim_seed(42)
    poi = _make_cave_poi(gx, gy)
    return generate_underground_area(poi)


# ---------------------------------------------------------------------------
# Underground Data Model
# ---------------------------------------------------------------------------

class TestUndergroundDataModel:
    def test_area_generates_chambers(self):
        area = _make_area()
        assert len(area.chambers) >= 3
        assert area.is_generated

    def test_layout_computes_walkability(self):
        area = _make_area()
        assert area.total_width > 0
        assert area.total_height > 0
        walkable_count = sum(sum(1 for cell in row if cell) for row in area.walkability)
        assert walkable_count > 0

    def test_layout_computes_floor_heightmap(self):
        area = _make_area()
        assert len(area.floor_heightmap) == area.total_height
        assert len(area.floor_heightmap[0]) == area.total_width

    def test_chambers_have_offsets(self):
        area = _make_area()
        for ch in area.chambers:
            assert hasattr(ch, "world_offset_x")
            assert hasattr(ch, "world_offset_z")

    def test_corridors_are_walkable(self):
        area = _make_area()
        if len(area.chambers) < 2:
            pytest.skip("need 2+ chambers")
        ch0 = area.chambers[0]
        ch1 = area.chambers[1]
        cx = area.total_width // 2
        # The corridor spans from the end of ch0 to the start of ch1
        corridor_z = ch0.world_offset_z + ch0.height
        if corridor_z >= ch1.world_offset_z:
            pytest.skip("no corridor gap between first two chambers")
        # Check that at least one cell in the corridor row at the center column is walkable
        found_walkable = False
        for gz in range(corridor_z, ch1.world_offset_z):
            if 0 <= gz < area.total_height and 0 <= cx < area.total_width:
                if area.walkability[gz][cx]:
                    found_walkable = True
                    break
        assert found_walkable, "No walkable corridor tile found between first two chambers"


# ---------------------------------------------------------------------------
# Underground Fog of War
# ---------------------------------------------------------------------------

class TestUndergroundFog:
    def test_init_fog_creates_grid(self):
        area = _make_area()
        world = World.__new__(World)
        world.underground_visibility = {}
        world.init_underground_fog(area)
        assert area.area_id in world.underground_visibility
        grid = world.underground_visibility[area.area_id]
        assert len(grid) == area.total_height
        assert all(cell == Visibility.UNSEEN for row in grid for cell in row)

    def test_reveal_circle_sets_visible(self):
        area = _make_area()
        world = World.__new__(World)
        world.underground_visibility = {}
        world.init_underground_fog(area)
        cx = area.total_width // 2
        world.reveal_underground_circle(area.area_id, cx, 2, 3)
        grid = world.underground_visibility[area.area_id]
        assert grid[2][cx] == Visibility.VISIBLE

    def test_reveal_does_not_crash_on_unknown_area(self):
        world = World.__new__(World)
        world.underground_visibility = {}
        # Should silently return, not raise
        world.reveal_underground_circle("nonexistent_area", 5, 5, 3)

    def test_reveal_circle_respects_bounds(self):
        area = _make_area()
        world = World.__new__(World)
        world.underground_visibility = {}
        world.init_underground_fog(area)
        # Reveal at corner -- should not raise IndexError
        world.reveal_underground_circle(area.area_id, 0, 0, 5)
        grid = world.underground_visibility[area.area_id]
        assert grid[0][0] == Visibility.VISIBLE


# ---------------------------------------------------------------------------
# LayerPathfinder
# ---------------------------------------------------------------------------

class TestLayerPathfinder:
    def test_surface_only_path(self):
        """Surface path through LayerPathfinder works."""
        from game.systems.pathfinding import LayerPathfinder

        class MockWorld:
            width = 100
            height = 100
            def is_walkable(self, x, y):
                return 0 <= x < 100 and 0 <= y < 100

        lp = LayerPathfinder(MockWorld(), {})
        path = lp.find_layer_path(10, 10, 0, 12, 12, 0)
        assert len(path) > 0
        assert all(p[2] == 0 for p in path)

    def test_surface_path_start_equals_goal(self):
        """Degenerate case: start == goal on surface."""
        from game.systems.pathfinding import LayerPathfinder

        class MockWorld:
            width = 100
            height = 100
            def is_walkable(self, x, y):
                return 0 <= x < 100 and 0 <= y < 100

        lp = LayerPathfinder(MockWorld(), {})
        path = lp.find_layer_path(10, 10, 0, 10, 10, 0)
        assert len(path) >= 1
        assert path[0] == (10, 10, 0)

    def test_no_path_for_unknown_underground_goal(self):
        """Cross-layer path with no matching area returns empty."""
        from game.systems.pathfinding import LayerPathfinder

        class MockWorld:
            width = 100
            height = 100
            def is_walkable(self, x, y):
                return True

        lp = LayerPathfinder(MockWorld(), {})
        path = lp.find_layer_path(10, 10, 0, 50, 50, -1)
        assert path == []

    def test_underground_only_path(self):
        """Pure underground path finds route through walkability grid."""
        from game.systems.pathfinding import LayerPathfinder

        area = _make_area(50, 50)

        class MockWorld:
            width = 200
            height = 200
            def is_walkable(self, x, y):
                return True

        areas = {area.area_id: area}
        lp = LayerPathfinder(MockWorld(), areas)

        # Find a walkable start and goal within the area
        cx = area.total_width // 2
        start_local = None
        goal_local = None
        for gz in range(area.total_height):
            for gx in range(area.total_width):
                if area.walkability[gz][gx]:
                    world_gx = gx - cx + area.entrance_grid_x
                    world_gy = gz + area.entrance_grid_y
                    if start_local is None:
                        start_local = (world_gx, world_gy)
                    else:
                        goal_local = (world_gx, world_gy)
        if start_local is None or goal_local is None:
            pytest.skip("No two walkable cells found in area")

        path = lp.find_layer_path(
            start_local[0], start_local[1], -1,
            goal_local[0], goal_local[1], -1,
        )
        assert len(path) > 0
        assert all(p[2] == -1 for p in path)


# ---------------------------------------------------------------------------
# Wave 5: Hero Transitions
# ---------------------------------------------------------------------------

def _make_test_hero():
    from game.entities.hero import Hero
    from config import TILE_SIZE
    set_sim_seed(42)
    return Hero(50 * TILE_SIZE, 50 * TILE_SIZE, "warrior")


class TestHeroTransitions:
    def test_hero_descent_sets_layer(self):
        hero = _make_test_hero()
        assert hero.layer == 0
        hero.begin_descent("test_area", 50, 50)
        assert hero.layer == -1
        assert hero.underground_area_id == "test_area"

    def test_hero_ascent_restores_layer(self):
        hero = _make_test_hero()
        hero.begin_descent("test_area", 50, 50)
        hero.begin_ascent()
        assert hero.layer == 0
        assert hero.underground_area_id is None

    def test_hero_descent_sets_local_coords(self):
        hero = _make_test_hero()
        hero.begin_descent("test_area", 50, 50)
        assert hero.underground_local_x == 0
        assert hero.underground_local_z == 0

    def test_hero_ascent_clears_local_coords(self):
        hero = _make_test_hero()
        hero.begin_descent("test_area", 50, 50)
        hero.underground_local_x = 10
        hero.underground_local_z = 5
        hero.begin_ascent()
        assert hero.underground_local_x == 0
        assert hero.underground_local_z == 0

    def test_hero_has_underground_fields(self):
        hero = _make_test_hero()
        assert hasattr(hero, "begin_descent")
        assert hasattr(hero, "begin_ascent")
        assert hasattr(hero, "underground_area_id")
        assert hasattr(hero, "underground_local_x")
        assert hasattr(hero, "underground_local_z")


# ---------------------------------------------------------------------------
# Wave 5E: Hero Retreat Logic
# ---------------------------------------------------------------------------

class TestHeroRetreat:
    def test_retreat_on_low_hp(self):
        hero = _make_test_hero()
        area = _make_area()
        areas = {area.area_id: area}
        hero.begin_descent(area.area_id, 50, 50)
        hero.hp = int(hero.max_hp * 0.2)  # below 30%
        result = check_underground_hero_retreat(hero, areas)
        assert result is True
        assert hero.layer == 0
        assert hero.underground_area_id is None

    def test_no_retreat_when_healthy(self):
        hero = _make_test_hero()
        area = _make_area()
        areas = {area.area_id: area}
        hero.begin_descent(area.area_id, 50, 50)
        hero.hp = hero.max_hp  # full HP
        result = check_underground_hero_retreat(hero, areas)
        assert result is False
        assert hero.layer == -1

    def test_retreat_when_all_chambers_cleared(self):
        hero = _make_test_hero()
        area = _make_area()
        areas = {area.area_id: area}
        hero.begin_descent(area.area_id, 50, 50)
        # Mark all chambers as cleared
        for ch in area.chambers:
            ch.is_cleared = True
        result = check_underground_hero_retreat(hero, areas)
        assert result is True
        assert hero.layer == 0

    def test_no_retreat_on_surface(self):
        hero = _make_test_hero()
        area = _make_area()
        areas = {area.area_id: area}
        # Hero is on surface, should not trigger retreat
        result = check_underground_hero_retreat(hero, areas)
        assert result is False
        assert hero.layer == 0

    def test_retreat_when_area_missing(self):
        hero = _make_test_hero()
        hero.begin_descent("nonexistent_area", 50, 50)
        result = check_underground_hero_retreat(hero, {})
        assert result is True
        assert hero.layer == 0


# ---------------------------------------------------------------------------
# Wave 5D: AI Dungeon Scoring
# ---------------------------------------------------------------------------

class TestDungeonScoring:
    def test_aggressive_hero_gets_dungeon_bonus(self):
        from ai.behaviors.poi_awareness import score_poi_for_personality
        hero = _make_test_hero()
        hero.personality = "brave and aggressive"
        hero.hp = hero.max_hp  # full HP
        poi = _make_cave_poi(55, 55)
        poi.is_discovered = True
        poi.is_depleted = False
        poi.is_interacted = False
        score = score_poi_for_personality(hero, poi, dist_tiles=5.0)
        assert score > 0

        # Compare with a cautious hero at low level
        hero2 = _make_test_hero()
        hero2.personality = "cautious and strategic"
        hero2.hp = hero2.max_hp
        hero2.level = 1
        score2 = score_poi_for_personality(hero2, poi, dist_tiles=5.0)
        # Aggressive hero should score higher than cautious low-level hero
        assert score > score2

    def test_low_hp_hero_avoids_dungeon(self):
        from ai.behaviors.poi_awareness import score_poi_for_personality
        hero = _make_test_hero()
        hero.personality = "brave and aggressive"
        hero.hp = int(hero.max_hp * 0.5)  # below 70%
        poi = _make_cave_poi(55, 55)
        poi.is_discovered = True
        poi.is_depleted = False
        poi.is_interacted = False
        score_low = score_poi_for_personality(hero, poi, dist_tiles=5.0)

        hero2 = _make_test_hero()
        hero2.personality = "brave and aggressive"
        hero2.hp = hero2.max_hp  # full HP
        score_full = score_poi_for_personality(hero2, poi, dist_tiles=5.0)
        # Low HP hero should score much lower
        assert score_low < score_full * 0.5
