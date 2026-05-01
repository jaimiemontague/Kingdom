"""WK50 Agent 03: engine-side direct prompt target resolution (deterministic)."""

from __future__ import annotations

from types import SimpleNamespace

from config import TILE_SIZE
from game.sim.direct_prompt_targets import (
    parse_compass_direction,
    resolve_explore_direction_target,
    resolve_known_place_world_xy,
    resolve_move_destination,
    strip_untrusted_spatial_fields,
)
from game.sim.hero_profile import KnownPlaceSnapshot


def _place(pid: str, wx: float, wy: float) -> KnownPlaceSnapshot:
    return KnownPlaceSnapshot(
        place_id=pid,
        place_type="inn",
        display_name="Inn",
        tile=(3, 4),
        world_pos=(wx, wy),
        first_seen_ms=1,
        last_seen_ms=2,
    )


def test_parse_compass_direction_order():
    assert parse_compass_direction("head northeast then east") == "northeast"
    assert parse_compass_direction("go westward") == "west"
    assert parse_compass_direction("", "north") == "north"


def test_strip_untrusted_spatial_fields():
    d = {"tool_action": "move_to", "world_x": 99.0, "tile_x": 3}
    s = strip_untrusted_spatial_fields(d)
    assert "world_x" not in s
    assert s["tool_action"] == "move_to"


def test_resolve_known_place_world_xy_exact():
    hero = SimpleNamespace(
        hero_id="h1",
        name="A",
        known_places={"inn:1": _place("inn:1", 100.0, 200.0)},
    )
    gs = {}
    xy = resolve_known_place_world_xy(hero, gs, "inn:1")
    assert xy == (100.0, 200.0)


def test_resolve_explore_direction_target_clamped():
    hero = SimpleNamespace(x=5 * TILE_SIZE, y=5 * TILE_SIZE)
    world = SimpleNamespace(width=20, height=20)
    gs = {"world": world}
    ex, ey = resolve_explore_direction_target(hero, gs, "east", tiles_ahead=50)
    assert ex == 19 * TILE_SIZE + TILE_SIZE / 2.0


def test_resolve_move_destination_prefers_place_id_over_label():
    hero = SimpleNamespace(
        hero_id="h1",
        name="A",
        known_places={
            "market:99": KnownPlaceSnapshot(
                place_id="market:99",
                place_type="marketplace",
                display_name="Far Market",
                tile=(90, 90),
                world_pos=(1234.0, 5678.0),
                first_seen_ms=1,
                last_seen_ms=2,
            )
        },
    )
    b_near = SimpleNamespace(building_type="marketplace", center_x=10.0, center_y=10.0)
    b_far = SimpleNamespace(building_type="marketplace", center_x=100.0, center_y=100.0)
    gs = {"buildings": [b_near, b_far], "castle": None, "heroes": [hero]}
    dec = {"target_id": "market:99", "target": "marketplace"}
    xy = resolve_move_destination(hero, gs, dec)
    assert xy == (1234.0, 5678.0)


def test_direct_prompt_commit_sets_target_and_moving_state():
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import (
        DIRECT_PROMPT_TARGET_TYPE,
        attach_direct_prompt_move,
        clear_direct_prompt_commit,
    )

    hero = Hero(0.0, 0.0, name="T", hero_id="t_dp")
    hero.target = {"type": "bounty", "bounty_id": 1}
    attach_direct_prompt_move(hero, sub_intent="buy_potions", wx=64.0, wy=96.0)
    assert hero.state == HeroState.MOVING
    assert hero.target_position == (64.0, 96.0)
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target.get("sub_intent") == "buy_potions"
    clear_direct_prompt_commit(hero)
    assert hero.target is None


def test_apply_validated_direct_prompt_uses_commit_not_llm_move_request():
    """Direct prompt movement applies immediately; does not rely on next-tick llm_move_request drain."""

    from types import SimpleNamespace

    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
    from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical

    class _FakeAI:
        def set_intent(self, hero, label: str) -> None:
            hero.intent = label

        def record_decision(self, hero, **kwargs) -> None:
            pass

    hero = Hero(0.0, 0.0, name="T", hero_id="t_dexec")
    hero.state = HeroState.IDLE
    hero.target = {"type": "bounty", "bounty_id": 99}
    m = SimpleNamespace(center_x=128.0, center_y=256.0, building_type="marketplace", hp=100)
    gs: dict = {"buildings": [m], "world": SimpleNamespace(width=32, height=32), "heroes": [hero]}
    ai = _FakeAI()
    assert (
        apply_validated_direct_prompt_physical(
            ai,
            hero,
            {
                "tool_action": "move_to",
                "interpreted_intent": "buy_potions",
                "target": "marketplace",
                "reasoning": "test",
            },
            gs,
            player_message="buy potions",
            source="chat",
        )
        is True
    )
    assert hero.llm_move_request is None
    assert hero.state == HeroState.MOVING
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target.get("sub_intent") == "buy_potions"


def test_apply_validated_explore_east_commits_direct_prompt_without_llm_move_request():
    """WK50 R11: explore east attaches sovereign direct_prompt target (engine resolution), not llm_move_request."""
    from types import SimpleNamespace

    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
    from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical
    from game.sim.timebase import set_sim_now_ms

    class _FakeAI:
        def set_intent(self, hero, label: str) -> None:
            hero.intent = label

        def record_decision(self, hero, **kwargs) -> None:
            pass

    set_sim_now_ms(5000)
    try:
        hx = 5 * TILE_SIZE + TILE_SIZE / 2.0
        hy = 5 * TILE_SIZE + TILE_SIZE / 2.0
        hero = Hero(hx, hy, name="Ex", hero_id="t_ex_east")
        hero.state = HeroState.IDLE
        world = SimpleNamespace(width=20, height=20)
        gs: dict = {"buildings": [], "world": world, "heroes": [hero]}
        ai = _FakeAI()
        assert (
            apply_validated_direct_prompt_physical(
                ai,
                hero,
                {
                    "tool_action": "explore",
                    "interpreted_intent": "explore_direction",
                    "target_description": "east",
                    "reasoning": "scout east",
                },
                gs,
                player_message="explore east please",
                source="chat",
            )
            is True
        )
        assert hero.llm_move_request is None
        assert hero.state == HeroState.MOVING
        assert isinstance(hero.target, dict)
        assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
        assert hero.target.get("sub_intent") == "explore_direction"
        expected_xy = resolve_explore_direction_target(hero, gs, "east")
        assert expected_xy is not None
        assert hero.target_position is not None
        assert abs(hero.target_position[0] - expected_xy[0]) < 1e-3
        assert abs(hero.target_position[1] - expected_xy[1]) < 1e-3
        assert hero.target_position[0] > hx + TILE_SIZE * 2
    finally:
        set_sim_now_ms(None)


def test_basic_ai_tick_preserves_direct_prompt_explore_destination():
    """WK50 R11: one simulation tick must not overwrite an in-flight direct_prompt sovereign move."""
    from types import SimpleNamespace

    from ai.basic_ai import BasicAI
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE, attach_direct_prompt_move
    from game.sim.timebase import set_sim_now_ms

    set_sim_now_ms(10_000)
    try:
        ai = BasicAI(llm_brain=None)
        hx = 5 * TILE_SIZE + TILE_SIZE / 2.0
        hy = 5 * TILE_SIZE + TILE_SIZE / 2.0
        hero = Hero(hx, hy, name="Dp", hero_id="dp_explore_hold")
        hero.state = HeroState.MOVING
        east_x = 19 * TILE_SIZE + TILE_SIZE / 2.0
        attach_direct_prompt_move(hero, sub_intent="explore_direction", wx=east_x, wy=hy, now_ms=10_000)
        gs = {
            "buildings": [],
            "world": SimpleNamespace(width=20, height=20),
            "castle": None,
            "enemies": [],
            "bounties": [],
        }
        ai.update_hero(hero, 0.05, gs)
        assert isinstance(hero.target, dict)
        assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
        assert hero.target.get("sub_intent") == "explore_direction"
        assert hero.state == HeroState.MOVING
        assert hero.target_position is not None
    finally:
        set_sim_now_ms(None)
