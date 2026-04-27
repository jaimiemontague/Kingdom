"""
Verify the data contract between GameEngine.get_game_state() and the renderer.

This does NOT instantiate Ursina or any GPU resources. It only checks that
get_game_state() provides the data shapes the renderer expects to consume.
"""
import pygame

from game.engine import GameEngine

# These are the keys UrsinaRenderer.update() reads from get_game_state().
# Extracted by grep of `gs["..."]` in ursina_renderer.py lines 1693-2067.
RENDERER_CONSUMED_KEYS = frozenset({
    "buildings",
    "heroes",
    "enemies",
    "peasants",
    "guards",
    "bounties",
})


def test_game_state_provides_renderer_consumed_keys():
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        missing = RENDERER_CONSUMED_KEYS - set(gs.keys())
        assert not missing, f"Renderer needs keys missing from get_game_state: {missing}"
    finally:
        pygame.quit()


def test_game_state_entity_lists_are_iterable():
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        for key in ("buildings", "heroes", "enemies", "peasants", "guards"):
            assert hasattr(gs[key], "__iter__"), f"gs['{key}'] must be iterable"
    finally:
        pygame.quit()


def test_buildings_have_required_renderer_attributes():
    """Every building must have the attributes the renderer reads."""
    engine = GameEngine(headless=True)
    try:
        gs = engine.get_game_state()
        for b in gs["buildings"]:
            assert hasattr(b, "building_type"), "building missing building_type"
            assert hasattr(b, "x"), "building missing x"
            assert hasattr(b, "y"), "building missing y"
            assert hasattr(b, "width"), "building missing width"
            assert hasattr(b, "height"), "building missing height"
            assert hasattr(b, "hp"), "building missing hp"
            assert hasattr(b, "max_hp"), "building missing max_hp"
            assert hasattr(b, "is_constructed"), "building missing is_constructed"
    finally:
        pygame.quit()

