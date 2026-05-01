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


def test_resolve_move_destination_guild_via_label_when_id_not_memorized():
    """R14: guild home move uses building_type label if place_id misses profile memory."""

    hero = SimpleNamespace(
        hero_id="h1",
        name="Aria",
        x=400.0,
        y=400.0,
        known_places={},
    )
    g = SimpleNamespace(building_type="ranger_guild", center_x=500.0, center_y=500.0)
    gs = {"buildings": [g], "castle": None, "heroes": [hero]}
    dec = {
        "target_id": "ranger_guild:10:15",
        "target": "ranger_guild",
    }
    xy = resolve_move_destination(hero, gs, dec)
    assert xy == (500.0, 500.0)


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


def test_apply_validated_buy_item_commits_direct_prompt():
    """WK50 R16: buy_item uses sovereign direct_prompt (not only type=shopping) for long trips."""
    from types import SimpleNamespace

    from ai.basic_ai import BasicAI
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
    from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical

    hero = Hero(0.0, 0.0, name="Shopper", hero_id="t_buy_dp")
    hero.state = HeroState.IDLE
    m = SimpleNamespace(
        center_x=128.0,
        center_y=256.0,
        building_type="marketplace",
        hp=100,
        potions_researched=True,
    )
    gs: dict = {"buildings": [m], "world": SimpleNamespace(width=32, height=32), "heroes": [hero]}
    ai = BasicAI(llm_brain=None)
    assert (
        apply_validated_direct_prompt_physical(
            ai,
            hero,
            {
                "tool_action": "buy_item",
                "interpreted_intent": "buy_potions",
                "target": "healing potion",
                "reasoning": "test",
            },
            gs,
            player_message="buy potions",
            source="chat",
        )
        is True
    )
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target.get("sub_intent") == "buy_potions"
    assert hero.state == HeroState.MOVING
    assert hero.target_position is not None


def test_apply_validated_retreat_commits_direct_prompt():
    """WK50 R16: retreat path applies sovereign direct_prompt toward safety."""
    from types import SimpleNamespace

    from ai.basic_ai import BasicAI
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
    from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical

    hero = Hero(400.0, 400.0, name="Runner", hero_id="t_ret_dp")
    hero.state = HeroState.FIGHTING
    castle = SimpleNamespace(
        building_type="castle",
        center_x=100.0,
        center_y=100.0,
    )
    gs: dict = {
        "buildings": [castle],
        "world": SimpleNamespace(width=32, height=32),
        "heroes": [hero],
    }
    ai = BasicAI(llm_brain=None)
    assert (
        apply_validated_direct_prompt_physical(
            ai,
            hero,
            {
                "action": "retreat",
                "interpreted_intent": "seek_healing",
                "target": "",
                "reasoning": "low HP",
            },
            gs,
            player_message="retreat",
            source="chat",
        )
        is True
    )
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target.get("sub_intent") == "seek_healing"
    assert hero.state == HeroState.MOVING
    assert hero.target_position == (100.0, 100.0)


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


def test_direct_prompt_commit_survives_past_ttl_while_moving_far():
    """WK50 R15: sovereign direct_prompt survives long journeys (no TTL while actively MOVING)."""
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import (
        DIRECT_PROMPT_TARGET_TYPE,
        attach_direct_prompt_move,
        expire_direct_prompt_commit_if_timed_out,
    )
    from game.sim.timebase import set_sim_now_ms

    set_sim_now_ms(0)
    try:
        hero = Hero(0.0, 0.0, name="FarWalker", hero_id="wk50_far_dp")
        hero.state = HeroState.IDLE
        far_x = 200 * TILE_SIZE + TILE_SIZE / 2
        attach_direct_prompt_move(
            hero, sub_intent="return_home", wx=far_x, wy=TILE_SIZE / 2, now_ms=0
        )
        assert hero.state == HeroState.MOVING
        set_sim_now_ms(500_000)
        expire_direct_prompt_commit_if_timed_out(hero)
        assert isinstance(hero.target, dict)
        assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
        assert hero.state == HeroState.MOVING
        assert hero.target_position is not None
    finally:
        set_sim_now_ms(None)


def test_direct_prompt_commit_can_abort_when_stuck_too_long():
    """WK50 R15: prolonged pathing stall still drops sovereign move (anti soft-lock)."""
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import (
        attach_direct_prompt_move,
        expire_direct_prompt_commit_if_timed_out,
        DIRECT_PROMPT_STUCK_ABORT_MS,
    )
    from game.sim.timebase import set_sim_now_ms

    set_sim_now_ms(0)
    try:
        hero = Hero(0.0, 0.0, name="Stucker", hero_id="wk50_stuck_dp")
        far_x = 50 * TILE_SIZE + TILE_SIZE / 2
        attach_direct_prompt_move(hero, sub_intent="go_to_known_place", wx=far_x, wy=0.0, now_ms=0)
        hero.stuck_active = True
        hero.stuck_since_ms = 10_000
        now = 10_000 + DIRECT_PROMPT_STUCK_ABORT_MS + 5_000
        set_sim_now_ms(now)
        expire_direct_prompt_commit_if_timed_out(hero)
        assert hero.target is None
        assert hero.state == HeroState.IDLE
    finally:
        set_sim_now_ms(None)


def test_basic_ai_many_ticks_preserve_direct_prompt_after_long_sim_time():
    """WK50 R15: many ticks with sim time beyond legacy TTL — BasicAI must not drop sovereign routing."""
    from ai.basic_ai import BasicAI
    from game.entities.hero import Hero, HeroState
    from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE, attach_direct_prompt_move
    from game.sim.timebase import set_sim_now_ms

    class _WorldStub:
        """Minimal grid helpers if stuck_recovery reaches nudge/repath branches."""

        def __init__(self, w: int, h: int):
            self.width = w
            self.height = h

        def world_to_grid(self, wx: float, wy: float) -> tuple[int, int]:
            return int(wx // TILE_SIZE), int(wy // TILE_SIZE)

        def is_walkable(self, gx: int, gy: int) -> bool:
            return 0 <= gx < self.width and 0 <= gy < self.height

    set_sim_now_ms(0)
    try:
        ai = BasicAI(llm_brain=None)
        hero = Hero(0.0, 0.0, name="Marathon", hero_id="dp_many_ticks")
        hero.state = HeroState.MOVING
        far_x = 300 * TILE_SIZE + TILE_SIZE / 2.0
        attach_direct_prompt_move(
            hero, sub_intent="return_home", wx=far_x, wy=TILE_SIZE / 2.0, now_ms=0
        )
        gs = {
            "buildings": [],
            "world": _WorldStub(400, 400),
            "castle": None,
            "enemies": [],
            "bounties": [{"id": 1, "reward_gold": 50}],
        }
        dt = 0.05
        for i in range(40):
            set_sim_now_ms(60_000 + i * 15_000)
            # Simulated march progress keeps stuck_recovery from clearing the sovereign target.
            hero.x += TILE_SIZE * 0.5
            ai.update_hero(hero, dt, gs)
            assert isinstance(hero.target, dict), f"lost commit at tick {i}"
            assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
            assert hero.target.get("sub_intent") == "return_home"
            assert hero.state == HeroState.MOVING
            assert hero.target_position is not None
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
