"""WK132: compact nearby_pois serialization into LLM prompts.

Covers both prompt paths:
- autonomous decisions: ai/profile_context_adapter.py::_compact_situation
  (data source: ContextBuilder.build_hero_context -> nearby_pois via
  ai/behaviors/poi_awareness.py::get_nearby_pois_for_hero)
- chat/direct prompt: ai/prompt_packs.py::build_direct_prompt_messages
  (data source: same build_hero_context output passed as hero_context — the
  read-only AiGameView plumbing; no live sim objects)

Contract: key OMITTED entirely when no POIs are nearby (WK67 digest scenario
has no POIs; its prompts must be unaffected), entries capped at 4, mystery
form for undiscovered POIs.
"""

from __future__ import annotations

import json
import math

from types import SimpleNamespace

from ai.behaviors.poi_awareness import (
    MAX_PROMPT_POIS,
    format_nearby_pois_compact,
)
from ai.decision_moments import DecisionMoment, DecisionMomentType
from ai.profile_context_adapter import build_llm_context_for_moment
from ai.prompt_packs import build_autonomous_user_prompt, build_direct_prompt_messages
from config import TILE_SIZE
from game.entities.hero import Hero, HeroState
from game.world import Visibility


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _poi_def(name: str, itype: str, tier: int, size=(1, 1)) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=name,
        interaction_type=itype,
        difficulty_tier=tier,
        size=size,
        description="A long flavor description that must never reach the prompt.",
    )


def _poi(
    name: str,
    itype: str,
    tier: int,
    grid_x: int,
    grid_y: int,
    *,
    discovered: bool = True,
    depleted: bool = False,
    interacted: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        poi_def=_poi_def(name, itype, tier),
        grid_x=grid_x,
        grid_y=grid_y,
        is_discovered=discovered,
        is_depleted=depleted,
        is_interacted=interacted,
    )


class _SeenWorld:
    """Minimal world stub: every tile is SEEN (grey fog)."""

    def __init__(self, width: int = 64, height: int = 64):
        self.width = width
        self.height = height
        self.visibility = [[Visibility.SEEN] * width for _ in range(height)]


def _hero_east_of(poi_grid_x: int, poi_grid_y: int, tiles_west: float) -> Hero:
    """Hero placed exactly `tiles_west` tiles WEST of a 1x1 POI center (POI is due EAST)."""
    pcx = (poi_grid_x + 0.5) * TILE_SIZE
    pcy = (poi_grid_y + 0.5) * TILE_SIZE
    h = Hero(pcx - tiles_west * TILE_SIZE, pcy, name="PoiHero", hero_id="poi1")
    h.state = HeroState.IDLE
    return h


def _gs(hero: Hero, pois: list, world=None) -> dict:
    return {
        "buildings": [],
        "enemies": [],
        "heroes": [hero],
        "bounties": [],
        "pois": pois,
        "world": world,
    }


def _moment(mtype: DecisionMomentType) -> DecisionMoment:
    return DecisionMoment(
        moment_type=mtype,
        urgency=1,
        reason="test",
        allowed_actions=("explore", "move_to"),
        context_focus=(),
        cooldown_ms=1000,
    )


# ---------------------------------------------------------------------------
# Formatter unit tests (exact formatting)
# ---------------------------------------------------------------------------

def test_formatter_discovered_exact_format():
    entries = [
        {
            "name": "Forgotten Shrine",
            "type": "shrine",
            "distance_tiles": 12.0,
            "direction": "northeast",
            "difficulty": 2,
            "description": "should never appear",
            "depleted": False,
            "previously_visited": False,
        }
    ]
    assert format_nearby_pois_compact(entries) == [
        "Forgotten Shrine (shrine, tier 2), 12 tiles NE"
    ]


def test_formatter_mystery_form_exact():
    entries = [
        {
            "name": "Unknown Structure",
            "type": "unknown",
            "distance_tiles": 20.0,
            "direction": "east",
            "description": "should never appear",
        }
    ]
    assert format_nearby_pois_compact(entries) == ["Unknown structure, 20 tiles E"]


def test_formatter_depleted_and_visited_suffixes():
    base = {
        "name": "Treasure Cache",
        "type": "loot",
        "distance_tiles": 5.0,
        "direction": "south",
        "difficulty": 1,
    }
    assert format_nearby_pois_compact([{**base, "depleted": True}]) == [
        "Treasure Cache (loot, tier 1), 5 tiles S, depleted"
    ]
    assert format_nearby_pois_compact(
        [{**base, "depleted": False, "previously_visited": True}]
    ) == ["Treasure Cache (loot, tier 1), 5 tiles S, visited"]


def test_formatter_caps_at_four():
    entries = [
        {
            "name": f"Shrine {i}",
            "type": "shrine",
            "distance_tiles": float(i + 1),
            "direction": "north",
            "difficulty": 1,
        }
        for i in range(6)
    ]
    out = format_nearby_pois_compact(entries)
    assert len(out) == MAX_PROMPT_POIS == 4
    assert out[0] == "Shrine 0 (shrine, tier 1), 1 tiles N"


def test_formatter_empty_input_returns_empty_list():
    assert format_nearby_pois_compact([]) == []
    assert format_nearby_pois_compact(None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Autonomous decision path (every DecisionMoment carries it when POIs nearby)
# ---------------------------------------------------------------------------

def test_decision_context_includes_compact_pois_for_every_moment():
    poi = _poi("Forgotten Shrine", "shrine", 2, grid_x=30, grid_y=10)
    hero = _hero_east_of(30, 10, tiles_west=12.0)
    gs = _gs(hero, [poi])
    expected = "Forgotten Shrine (shrine, tier 2), 12 tiles E"

    for mtype in DecisionMomentType:
        ctx = build_llm_context_for_moment(hero, gs, _moment(mtype), now_ms=5000)
        sit = ctx["current_situation"]
        assert sit.get("nearby_pois") == [expected], mtype
        # And the serialized user prompt actually carries it.
        up = build_autonomous_user_prompt(ctx)
        assert expected in up, mtype


def test_decision_context_omits_key_when_no_pois():
    hero = Hero(100.0, 100.0, name="NoPoi", hero_id="np1")
    hero.state = HeroState.IDLE
    gs = _gs(hero, [])
    for mtype in DecisionMomentType:
        ctx = build_llm_context_for_moment(hero, gs, _moment(mtype), now_ms=5000)
        assert "nearby_pois" not in ctx["current_situation"], mtype
        assert '"nearby_pois"' not in build_autonomous_user_prompt(ctx), mtype


def test_decision_context_caps_entries_at_four():
    pois = [
        _poi(f"Shrine {i}", "shrine", 1, grid_x=30 + i, grid_y=10) for i in range(6)
    ]
    hero = _hero_east_of(30, 10, tiles_west=5.0)
    gs = _gs(hero, pois)
    ctx = build_llm_context_for_moment(
        hero, gs, _moment(DecisionMomentType.IDLE_SEEKING_ACTIVITY), now_ms=5000
    )
    got = ctx["current_situation"]["nearby_pois"]
    assert len(got) == 4


def test_decision_context_undiscovered_poi_renders_mystery_form():
    # Undiscovered POI in SEEN fog, exactly 20 tiles due east.
    poi = _poi("Dragon Cave", "boss", 5, grid_x=40, grid_y=10, discovered=False)
    hero = _hero_east_of(40, 10, tiles_west=20.0)
    gs = _gs(hero, [poi], world=_SeenWorld())
    ctx = build_llm_context_for_moment(
        hero, gs, _moment(DecisionMomentType.IDLE_SEEKING_ACTIVITY), now_ms=5000
    )
    got = ctx["current_situation"]["nearby_pois"]
    assert got == ["Unknown structure, 20 tiles E"]
    # Identity must not leak through the prompt.
    up = build_autonomous_user_prompt(ctx)
    assert "Dragon Cave" not in up


def test_decision_pois_are_strings_without_descriptions():
    poi = _poi("Ancient Ruins", "knowledge", 3, grid_x=30, grid_y=10)
    hero = _hero_east_of(30, 10, tiles_west=8.0)
    ctx = build_llm_context_for_moment(
        hero, _gs(hero, [poi]), _moment(DecisionMomentType.RESTED_AND_READY), now_ms=5000
    )
    got = ctx["current_situation"]["nearby_pois"]
    assert all(isinstance(s, str) for s in got)
    assert "flavor description" not in json.dumps(got)


# ---------------------------------------------------------------------------
# Chat / direct prompt path
# ---------------------------------------------------------------------------

def _chat_hero_context(nearby_pois: list | None) -> dict:
    ctx = {
        "hero": {"name": "Aldric", "home_building_type": ""},
        "situation": {},
        "current_location": "outdoors",
        "inventory": {},
        "distances": {},
        "known_places_llm": [],
        "hero_home_place_id": "",
        "shop_items": [],
        "market_catalog_items": [],
    }
    if nearby_pois is not None:
        ctx["nearby_pois"] = nearby_pois
    return ctx


def _chat_blob(hero_context: dict) -> dict:
    _system, user = build_direct_prompt_messages(hero_context, [], "go check that shrine")
    return json.loads(user.split("\n\nRespond")[0].strip())


def test_chat_blob_includes_compact_pois():
    raw = [
        {
            "name": "Forgotten Shrine",
            "type": "shrine",
            "distance_tiles": 12.0,
            "direction": "northeast",
            "difficulty": 2,
            "description": "should never appear",
            "depleted": False,
            "previously_visited": False,
        },
        {
            "name": "Unknown Structure",
            "type": "unknown",
            "distance_tiles": 20.0,
            "direction": "east",
            "description": "should never appear",
        },
    ]
    blob = _chat_blob(_chat_hero_context(raw))
    assert blob["nearby_pois"] == [
        "Forgotten Shrine (shrine, tier 2), 12 tiles NE",
        "Unknown structure, 20 tiles E",
    ]
    # Long descriptions must not reach the prompt.
    assert "should never appear" not in json.dumps(blob)


def test_chat_blob_omits_key_when_no_pois():
    assert "nearby_pois" not in _chat_blob(_chat_hero_context(None))
    assert "nearby_pois" not in _chat_blob(_chat_hero_context([]))


def test_chat_blob_caps_entries_at_four():
    raw = [
        {
            "name": f"Shrine {i}",
            "type": "shrine",
            "distance_tiles": float(i + 1),
            "direction": "north",
            "difficulty": 1,
        }
        for i in range(6)
    ]
    blob = _chat_blob(_chat_hero_context(raw))
    assert len(blob["nearby_pois"]) == 4


# ---------------------------------------------------------------------------
# End-to-end: chat path fed by ContextBuilder (same data source as decisions)
# ---------------------------------------------------------------------------

def test_chat_blob_from_context_builder_pipeline():
    from ai.context_builder import ContextBuilder

    poi = _poi("Forgotten Shrine", "shrine", 2, grid_x=30, grid_y=10)
    hero = _hero_east_of(30, 10, tiles_west=12.0)
    hero_context = ContextBuilder.build_hero_context(hero, _gs(hero, [poi]))
    blob = _chat_blob(hero_context)
    assert blob["nearby_pois"] == ["Forgotten Shrine (shrine, tier 2), 12 tiles E"]
