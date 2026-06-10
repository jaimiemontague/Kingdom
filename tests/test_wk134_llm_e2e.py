"""WK134 — LLM Connection Verification Pass.

Covers the four verification lanes of the WK134 sprint:

1. accept_bounty wiring (was a dead no-op in ai/behaviors/llm_bridge.py):
   both directions — with a bounty the action commits the hero through the
   bounty-pursuit path; without one it degrades gracefully to explore.
2. Prompt-snapshot tests: REAL serialized prompts (build_llm_context_for_moment
   + prompt_packs builders) for a rich scenario must carry the inventory
   (weapon/armor/accessory/backpack), compact nearby_pois entries, and the
   quest_offer block in the QUEST_OFFER moment — while the digest-shaped
   scenario (defaults, no POIs, no quests) carries NONE of those keys.
3. Provider audit: ANTHROPIC_MODEL env override; loud mock fallback (flag +
   one-shot HUD_MESSAGE); pending_llm_decision watchdog with a hanging provider.
4. E2E command-following: every direct-prompt tool_action driven through the
   REAL chat path (request_conversation -> validator -> direct_prompt_exec ->
   apply_llm_decision) asserting the hero's state/target actually changes,
   plus the obey/defy paths.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

from ai.basic_ai import BasicAI
from ai.context_builder import ContextBuilder
from ai.decision_moments import (
    DecisionMomentType,
    moment_idle_seeking_activity,
    moment_quest_offer,
)
from ai.decision_output_validator import validate_autonomous_decision
from ai.behaviors.llm_bridge import apply_llm_decision
from ai.llm_brain import LLMBrain
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_packs import build_autonomous_user_prompt, build_direct_prompt_messages
from ai.providers.claude_provider import DEFAULT_ANTHROPIC_MODEL, ClaudeProvider
from config import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE
from game.entities import Inn, RangerGuild
from game.entities.buildings.economic import Marketplace
from game.entities.hero import Hero, HeroState
from game.sim.direct_prompt_commit import DIRECT_PROMPT_TARGET_TYPE
from game.sim.direct_prompt_exec import apply_validated_direct_prompt_physical
from game.sim.timebase import set_sim_now_ms


# ---------------------------------------------------------------------------
# Harness (mirrors tests/test_direct_prompt_integration.py)
# ---------------------------------------------------------------------------

NOW_MS = 10_000


@pytest.fixture(autouse=True)
def _sim_clock():
    set_sim_now_ms(NOW_MS)
    try:
        yield
    finally:
        set_sim_now_ms(None)


def _drain_conversation(brain: LLMBrain, hero_key: str, *, max_wait_s: float = 4.0) -> dict | None:
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        r = brain.get_conversation_response(hero_key)
        if r is not None:
            return r
        time.sleep(0.01)
    return None


def _drain_decision(brain: LLMBrain, hero_key: str, *, max_wait_s: float = 4.0) -> dict | None:
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        r = brain.get_decision(hero_key)
        if r is not None:
            return r
        time.sleep(0.01)
    return None


def _base_layout():
    cx, cy = MAP_WIDTH // 2 - 1, MAP_HEIGHT // 2 - 1
    ranger_guild = RangerGuild(cx - 6, cy + 8)
    market = Marketplace(cx + 40, cy + 40)
    market.potions_researched = True
    market.potion_price = 15
    return cx, cy, ranger_guild, market


def _game_state(hero: Hero, buildings: list, *, bounties: list | None = None,
                pois: list | None = None, world_size: tuple[int, int] | None = None):
    w, h = world_size if world_size else (MAP_WIDTH, MAP_HEIGHT)
    gs = {
        "heroes": [hero],
        "buildings": buildings,
        "enemies": [],
        "bounties": bounties or [],
        "castle": None,
        "world": SimpleNamespace(width=w, height=h, is_walkable=lambda gx, gy: True),
    }
    if pois is not None:
        gs["pois"] = pois
    return gs


def _hero(ranger_guild, *, name="RangerW134", hero_id="wk134", x=None, y=None) -> Hero:
    h = Hero(
        float(x if x is not None else ranger_guild.center_x),
        float(y if y is not None else ranger_guild.center_y),
        hero_class="ranger",
        hero_id=hero_id,
        name=name,
    )
    h.home_building = ranger_guild
    return h


def _remember(hero: Hero, place_type: str, display_name: str, building) -> None:
    hero.remember_known_place(
        place_type=place_type,
        display_name=display_name,
        tile=(building.grid_x, building.grid_y),
        world_pos=(building.center_x, building.center_y),
        sim_time_ms=NOW_MS,
        building_type=place_type,
        grid_x=building.grid_x,
        grid_y=building.grid_y,
    )


def _make_poi(grid_x: int, grid_y: int, name: str, itype: str = "shrine", tier: int = 2):
    return SimpleNamespace(
        grid_x=grid_x,
        grid_y=grid_y,
        is_discovered=True,
        is_depleted=False,
        is_interacted=False,
        poi_def=SimpleNamespace(
            display_name=name,
            interaction_type=itype,
            difficulty_tier=tier,
            description=f"A {itype} of testing.",
            size=(1, 1),
        ),
    )


def _make_bounty(bounty_id: str, x: float, y: float, reward: int = 80):
    return SimpleNamespace(
        bounty_id=bounty_id,
        bounty_type="explore",
        reward=reward,
        x=float(x),
        y=float(y),
    )


def _rich_hero(ranger_guild) -> Hero:
    hero = _hero(ranger_guild, name="RangerRich", hero_id="wk134_rich")
    hero.weapon = {"name": "Steel Longsword", "attack": 7}
    hero.armor = {"name": "Chainmail Vest", "defense": 5}
    hero.accessory = {"name": "Lucky Charm of Testing", "attack": 1}
    hero.backpack = ["Wolf Pelt", "Ancient Relic"]
    hero.potions = 2
    hero.gold = 60
    return hero


class _StubProvider:
    """Provider returning fixed JSON — drives the REAL parse/validate path."""

    def __init__(self, payload: dict):
        self._text = json.dumps(payload)

    @property
    def name(self) -> str:
        return "stub"

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
        return self._text


class _HangingProvider:
    """Provider that never answers within the test window (ignores timeout)."""

    def __init__(self):
        self._gate = threading.Event()

    @property
    def name(self) -> str:
        return "hang"

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
        self._gate.wait(timeout=60.0)
        return "{}"


class _FakeAI:
    """Minimal ai object for direct apply_llm_decision tests."""

    def __init__(self) -> None:
        self.explore_calls = 0
        self.recorded: list[dict] = []
        self.defense_behavior = SimpleNamespace(start_retreat=lambda *a, **k: None)
        self.shopping_behavior = SimpleNamespace(go_shopping=lambda *a, **k: None)
        self.exploration_behavior = SimpleNamespace(explore=self._explore)
        self.llm_brain = None

    def _explore(self, ai, hero, view):
        self.explore_calls += 1

    def set_intent(self, hero, label: str) -> None:
        hero.intent = label

    def record_decision(self, hero, **kwargs) -> None:
        self.recorded.append(kwargs)

    def _debug_log(self, msg: str, throttle_key: str = "") -> None:
        pass


# ===========================================================================
# 1. accept_bounty wiring
# ===========================================================================


def test_parse_response_accepts_accept_bounty_and_validator_allows_it():
    brain = LLMBrain(provider_name="mock")
    try:
        parsed = brain._parse_response(
            '{"action": "accept_bounty", "target": "", "reasoning": "bounty pays well"}'
        )
        assert parsed is not None
        assert parsed["action"] == "accept_bounty"

        _, _, ranger_guild, _ = _base_layout()
        hero = _hero(ranger_guild)
        hero.state = HeroState.IDLE
        gs = _game_state(hero, [ranger_guild])
        moment = moment_idle_seeking_activity(hero, gs)
        assert moment is not None
        assert moment.moment_type == DecisionMomentType.IDLE_SEEKING_ACTIVITY
        assert "accept_bounty" in moment.allowed_actions

        validated = validate_autonomous_decision(parsed, moment)
        assert validated is not None
        assert validated["action"] == "accept_bounty"
    finally:
        brain.stop()


def test_accept_bounty_full_brain_path_commits_hero_to_bounty():
    """Stub provider -> REAL LLMBrain worker -> apply_llm_decision -> bounty commit."""
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_ab1", name="RangerBounty")
    hero.state = HeroState.IDLE
    bounty = _make_bounty("b_explore_1", hero.x + TILE_SIZE * 8, hero.y, reward=90)
    gs = _game_state(hero, [ranger_guild, market], bounties=[bounty])

    moment = moment_idle_seeking_activity(hero, gs)
    assert moment is not None

    brain = LLMBrain(provider_name="mock")
    brain.provider = _StubProvider(
        {"action": "accept_bounty", "target": "", "reasoning": "good reward nearby", "confidence": 0.9}
    )
    try:
        base_context = ContextBuilder.build_hero_context(hero, gs)
        autonomous = build_llm_context_for_moment(hero, gs, moment, now_ms=NOW_MS)
        brain.request_decision(hero.name, {**base_context, "wk50_autonomous": autonomous})
        decision = _drain_decision(brain, hero.name)
        assert decision is not None, "decision timeout"
        assert decision["action"] == "accept_bounty"
    finally:
        brain.stop()

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(ai, hero, decision, gs, source="llm")
    assert hero.state == HeroState.MOVING
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == "bounty"
    assert hero.target.get("bounty_id") == "b_explore_1"
    assert hero.target_position is not None
    assert hero.intent == "pursuing_bounty"


def test_accept_bounty_prefers_targeted_bounty_id():
    _, _, ranger_guild, _ = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_ab2", name="RangerPick")
    hero.state = HeroState.IDLE
    near = _make_bounty("b_near", hero.x + TILE_SIZE * 3, hero.y)
    far = _make_bounty("b_far", hero.x + TILE_SIZE * 20, hero.y)
    gs = _game_state(hero, [ranger_guild], bounties=[near, far])

    ai = BasicAI(llm_brain=None)
    apply_llm_decision(
        ai, hero, {"action": "accept_bounty", "target": "b_far", "reasoning": "that one"}, gs,
        source="llm",
    )
    assert hero.target.get("bounty_id") == "b_far"


def test_accept_bounty_without_bounty_degrades_to_explore_no_crash():
    _, _, ranger_guild, _ = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_ab3", name="RangerNoBounty")
    hero.state = HeroState.IDLE
    gs = _game_state(hero, [ranger_guild])  # no bounties

    ai = _FakeAI()
    apply_llm_decision(ai, hero, {"action": "accept_bounty", "target": ""}, gs, source="llm")
    assert ai.explore_calls == 1
    assert hero.intent == "idle"
    assert not isinstance(hero.target, dict) or hero.target.get("type") != "bounty"
    # The decision is still recorded (audit trail) even when degraded.
    assert any(r.get("action") == "accept_bounty" for r in ai.recorded)


# ===========================================================================
# 2. Prompt snapshots
# ===========================================================================


def _rich_gs_and_pois(hero, ranger_guild, market):
    hgx = int(hero.x // TILE_SIZE)
    hgy = int(hero.y // TILE_SIZE)
    pois = [
        _make_poi(hgx + 6, hgy, "Forgotten Shrine", "shrine", 2),
        _make_poi(hgx, hgy + 9, "Collapsed Ruins", "loot", 1),
    ]
    return _game_state(hero, [ranger_guild, market], pois=pois)


def test_autonomous_prompt_rich_scenario_carries_inventory_and_pois():
    _, _, ranger_guild, market = _base_layout()
    hero = _rich_hero(ranger_guild)
    hero.state = HeroState.IDLE
    gs = _rich_gs_and_pois(hero, ranger_guild, market)

    moment = moment_idle_seeking_activity(hero, gs)
    assert moment is not None
    ctx = build_llm_context_for_moment(hero, gs, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(ctx)

    # Inventory block (WK130/131 items through HeroInventorySnapshot).
    assert '"weapon_name": "Steel Longsword"' in prompt
    assert '"armor_name": "Chainmail Vest"' in prompt
    assert '"accessory_name": "Lucky Charm of Testing"' in prompt
    assert "Wolf Pelt" in prompt and "Ancient Relic" in prompt

    # nearby_pois compact entries (WK132).
    assert '"nearby_pois"' in prompt
    assert "Forgotten Shrine (shrine, tier 2)" in prompt
    assert "Collapsed Ruins (loot, tier 1)" in prompt
    assert "tiles" in prompt


def test_autonomous_prompt_quest_offer_moment_carries_quest_block():
    _, _, ranger_guild, market = _base_layout()
    hero = _rich_hero(ranger_guild)
    hero.state = HeroState.IDLE
    gs = _rich_gs_and_pois(hero, ranger_guild, market)

    hero._pending_quest_offer = {
        "giver_id": "giver_1",
        "quest_id": 7,
        "quest_type": "raid_lair",
        "target": "goblin_lair",
        "reward": 120,
        "count": 1,
        "x": hero.x + TILE_SIZE * 12,
        "y": hero.y,
        "staged_ms": NOW_MS,
        "expires_ms": NOW_MS + 30_000,
    }
    moment = moment_quest_offer(hero, now_ms=NOW_MS)
    assert moment is not None and moment.moment_type == DecisionMomentType.QUEST_OFFER

    ctx = build_llm_context_for_moment(hero, gs, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(ctx)

    assert '"quest_offer"' in prompt
    assert '"quest_type": "raid_lair"' in prompt
    assert '"reward_gold": 120' in prompt
    assert "To ACCEPT the quest" in prompt  # decision_rule carrier explanation
    # Rich context still present alongside the quest block.
    assert '"accessory_name": "Lucky Charm of Testing"' in prompt


def test_autonomous_prompt_digest_shape_contains_none_of_the_rich_keys():
    """Defaults-only hero, no POIs, no quests — the WK67-digest-shaped prompt."""
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_digest", name="RangerPlain")
    hero.state = HeroState.IDLE
    gs = _game_state(hero, [ranger_guild, market])  # no pois key, no offer

    moment = moment_idle_seeking_activity(hero, gs)
    assert moment is not None
    ctx = build_llm_context_for_moment(hero, gs, moment, now_ms=NOW_MS)
    prompt = build_autonomous_user_prompt(ctx)

    assert '"nearby_pois"' not in prompt
    assert '"quest_offer"' not in prompt
    assert '"accessory_name": ""' in prompt  # default-empty slot
    assert '"backpack": []' in prompt


def test_direct_prompt_blob_rich_scenario_carries_inventory_and_pois():
    _, _, ranger_guild, market = _base_layout()
    hero = _rich_hero(ranger_guild)
    gs = _rich_gs_and_pois(hero, ranger_guild, market)
    ctx = ContextBuilder.build_hero_context(hero, gs)

    _, user_prompt = build_direct_prompt_messages(ctx, [], "what do you carry?")

    assert '"weapon": "Steel Longsword"' in user_prompt
    assert '"armor": "Chainmail Vest"' in user_prompt
    assert '"accessory": "Lucky Charm of Testing"' in user_prompt
    assert "Wolf Pelt" in user_prompt and "Ancient Relic" in user_prompt
    assert '"nearby_pois"' in user_prompt
    assert "Forgotten Shrine (shrine, tier 2)" in user_prompt


def test_direct_prompt_blob_digest_shape_omits_rich_keys():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_dp_plain", name="RangerPlainChat")
    gs = _game_state(hero, [ranger_guild, market])
    ctx = ContextBuilder.build_hero_context(hero, gs)

    _, user_prompt = build_direct_prompt_messages(ctx, [], "status?")

    assert '"nearby_pois"' not in user_prompt
    assert '"quest_offer"' not in user_prompt
    assert '"accessory": ""' in user_prompt
    assert '"backpack": []' in user_prompt


# ===========================================================================
# 3. Provider audit
# ===========================================================================


def test_claude_model_env_override(monkeypatch):
    monkeypatch.setattr("ai.providers.claude_provider.ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-8")
    assert ClaudeProvider().model == "claude-opus-4-8"

    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert ClaudeProvider().model == DEFAULT_ANTHROPIC_MODEL
    # Default is a current bare alias, not the retired dated haiku-3 pin.
    assert DEFAULT_ANTHROPIC_MODEL == "claude-sonnet-4-6"

    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    assert ClaudeProvider(model="explicit-wins").model == "explicit-wins"


def test_llm_brain_unknown_provider_falls_back_to_mock_loudly(capsys):
    brain = LLMBrain(provider_name="not_a_real_provider")
    try:
        assert brain.provider_fallback is True
        assert brain.provider.name == "mock"
        assert brain.provider_fallback_reason
        out = capsys.readouterr().out
        assert "WARNING" in out and "MOCK" in out.upper()
    finally:
        brain.stop()


def test_llm_brain_claude_without_key_falls_back_to_mock_loudly(monkeypatch):
    monkeypatch.setattr("ai.providers.claude_provider.ANTHROPIC_API_KEY", "")
    brain = LLMBrain(provider_name="claude")
    try:
        assert brain.provider_fallback is True
        assert brain.provider.name == "mock"
        assert "not available" in brain.provider_fallback_reason
    finally:
        brain.stop()


def test_provider_fallback_emits_one_shot_hud_message():
    from game.events import GameEventType

    emitted: list[dict] = []
    bus = SimpleNamespace(emit=lambda payload: emitted.append(payload))

    brain = LLMBrain(provider_name="not_a_real_provider")
    try:
        brain.set_event_bus(bus)
        hud = [e for e in emitted if e.get("type") == GameEventType.HUD_MESSAGE.value]
        assert len(hud) == 1
        assert "mock" in hud[0]["text"].lower()
        # One-shot: re-wiring the bus must not re-emit.
        brain.set_event_bus(bus)
        hud = [e for e in emitted if e.get("type") == GameEventType.HUD_MESSAGE.value]
        assert len(hud) == 1
    finally:
        brain.stop()

    # Healthy mock brain emits nothing.
    emitted.clear()
    brain2 = LLMBrain(provider_name="mock")
    try:
        brain2.set_event_bus(bus)
        assert not emitted
        assert brain2.provider_fallback is False
    finally:
        brain2.stop()


def test_pending_llm_decision_watchdog_clears_with_hanging_provider():
    """A provider that ignores LLM_TIMEOUT must never wedge the hero."""
    from ai.task_router import PENDING_LLM_DECISION_TIMEOUT_MS, update_hero

    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_hang", name="RangerHang")
    hero.state = HeroState.IDLE
    gs = _game_state(hero, [ranger_guild, market])

    brain = LLMBrain(provider_name="mock")
    brain.provider = _HangingProvider()
    ai = BasicAI(llm_brain=brain)
    try:
        moment = moment_idle_seeking_activity(hero, gs)
        assert moment is not None
        ai.llm_bridge_behavior.request_llm_decision(ai, hero, gs)
        assert hero.pending_llm_decision is True
        assert hero.last_llm_decision_time == NOW_MS

        # Before the watchdog window: still pending (no decision arrived).
        set_sim_now_ms(NOW_MS + 1_000)
        update_hero(ai, hero, 0.05, gs)
        assert hero.pending_llm_decision is True

        # Past the watchdog window: pending MUST clear so the hero can consult again.
        set_sim_now_ms(NOW_MS + PENDING_LLM_DECISION_TIMEOUT_MS + 1_500)
        update_hero(ai, hero, 0.05, gs)
        assert hero.pending_llm_decision is False
    finally:
        brain.stop()


# ===========================================================================
# 4. E2E command-following (REAL chat path, seeded MockProvider)
# ===========================================================================


def _chat_roundtrip(hero: Hero, gs: dict, message: str) -> tuple[dict, bool]:
    """request_conversation -> validated output -> physical exec. Returns (out, applied)."""
    ctx = ContextBuilder.build_hero_context(hero, gs)
    brain = LLMBrain(provider_name="mock")
    try:
        brain.request_conversation(hero.name, ctx, [], message)
        out = _drain_conversation(brain, hero.name)
    finally:
        brain.stop()
    assert out is not None, f"conversation timeout for {message!r}"
    ai = BasicAI(llm_brain=None)
    applied = apply_validated_direct_prompt_physical(
        ai, hero, out, gs, player_message=message, source="chat"
    )
    return out, applied


@pytest.mark.parametrize(
    "place_type,display,message",
    [
        ("castle", "The Castle", "go to the castle"),
        ("marketplace", "Market", "go to the market"),
        ("blacksmith", "Forge", "go to the blacksmith"),
        ("inn", "The Inn", "go to the inn"),
    ],
)
def test_e2e_move_to_each_named_place_type(place_type, display, message):
    cx, cy, ranger_guild, market = _base_layout()
    inn = Inn(cx + 5, cy - 5)
    hero = _hero(ranger_guild, hero_id=f"wk134_mv_{place_type}", name="RangerMove")
    # Remember a place of the requested type at the inn's location (the world
    # position is what the resolver reads — the building list need not match).
    anchor = {"castle": inn, "marketplace": market, "blacksmith": inn, "inn": inn}[place_type]
    _remember(hero, place_type, display, anchor)
    gs = _game_state(hero, [ranger_guild, market, inn])

    out, applied = _chat_roundtrip(hero, gs, message)
    assert out["tool_action"] == "move_to"
    assert out["obey_defy"] == "Obey"
    assert applied is True
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.state == HeroState.MOVING
    assert hero.target_position is not None
    tx, ty = hero.target_position
    assert abs(tx - anchor.center_x) < TILE_SIZE * 3
    assert abs(ty - anchor.center_y) < TILE_SIZE * 3


def test_e2e_move_to_unknown_place_defies_without_state_change():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_mv_unknown", name="RangerLost")
    gs = _game_state(hero, [ranger_guild, market])
    state_before = hero.state

    out, applied = _chat_roundtrip(hero, gs, "go to the blacksmith")
    assert out["tool_action"] is None
    assert out["obey_defy"] == "Defy"
    assert out["refusal_reason"] == "unknown_place"
    assert out["spoken_response"]  # feedback line for the chat panel
    assert applied is False
    assert hero.state == state_before
    assert hero.target is None


@pytest.mark.parametrize("direction,sign_axis", [
    ("north", ("y", -1)),
    ("south", ("y", 1)),
    ("east", ("x", 1)),
    ("west", ("x", -1)),
])
def test_e2e_explore_each_compass_direction(direction, sign_axis):
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id=f"wk134_ex_{direction}", name="RangerScout")
    hero.state = HeroState.IDLE
    gs = _game_state(hero, [ranger_guild, market])
    x0, y0 = hero.x, hero.y

    out, applied = _chat_roundtrip(hero, gs, f"explore {direction}")
    assert out["tool_action"] == "explore"
    assert out["interpreted_intent"] == "explore_direction"
    assert applied is True
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target.get("sub_intent") == "explore_direction"
    axis, sign = sign_axis
    tx, ty = hero.target_position
    delta = (tx - x0) if axis == "x" else (ty - y0)
    assert delta * sign > 0, f"{direction}: expected displacement along {axis} sign {sign}"


def test_e2e_fight_command_defies_no_state_change():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_fight", name="RangerNoFight")
    hero.state = HeroState.IDLE
    gs = _game_state(hero, [ranger_guild, market])

    out, applied = _chat_roundtrip(hero, gs, "attack the lair now")
    assert out["obey_defy"] == "Defy"
    assert out["tool_action"] is None
    assert out["refusal_reason"] == "mvp_combat_deferred"
    assert out["spoken_response"]
    assert applied is False
    assert hero.state == HeroState.IDLE
    assert hero.target is None


def test_e2e_retreat_via_seek_healing_without_potions():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_retreat", name="RangerHurt",
                 x=ranger_guild.center_x + 300.0, y=ranger_guild.center_y + 300.0)
    hero.hp = max(1, hero.max_hp // 3)
    hero.potions = 0
    gs = _game_state(hero, [ranger_guild, market])

    out, applied = _chat_roundtrip(hero, gs, "I need healing")
    assert out["interpreted_intent"] == "seek_healing"
    assert out["tool_action"] == "retreat"
    assert applied is True
    assert isinstance(hero.target, dict)
    assert hero.target.get("type") == DIRECT_PROMPT_TARGET_TYPE
    assert hero.target_position is not None


def test_e2e_use_potion_heals_and_consumes():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_potion", name="RangerSip")
    hero.hp = max(1, hero.max_hp // 3)
    hero.potions = 2
    gs = _game_state(hero, [ranger_guild, market])
    hp_before = hero.hp

    out, applied = _chat_roundtrip(hero, gs, "I need healing")
    assert out["tool_action"] == "use_potion"
    assert applied is True
    assert hero.potions == 1
    assert hero.hp > hp_before


def test_e2e_buy_item_adjacent_to_market():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_buy", name="RangerShop",
                 x=market.center_x + TILE_SIZE * 2, y=market.center_y)
    hero.gold = 25
    _remember(hero, "marketplace", "Market", market)
    gs = _game_state(hero, [ranger_guild, market])

    out, applied = _chat_roundtrip(hero, gs, "buy potions please")
    assert out["tool_action"] == "buy_item"
    assert out["obey_defy"] == "Obey"
    assert applied is True
    assert hero.intent == "shopping"


def test_e2e_leave_building():
    _, _, ranger_guild, market = _base_layout()
    hero = _hero(ranger_guild, hero_id="wk134_leave", name="RangerOut")
    hero.is_inside_building = True
    hero.inside_building = ranger_guild
    hero.state = HeroState.RESTING
    gs = _game_state(hero, [ranger_guild, market])

    out, applied = _chat_roundtrip(hero, gs, "leave the building")
    assert out["tool_action"] == "leave_building"
    assert applied is True
    assert hero.is_inside_building is False
    assert hero.state == HeroState.IDLE
