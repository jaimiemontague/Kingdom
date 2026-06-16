from __future__ import annotations

from collections import Counter
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
        self.is_alive = True

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
    def __init__(self) -> None:
        self._debug_log = lambda *args, **kwargs: None

    def set_intent(self, hero: _Hero, intent: str) -> None:
        hero.intent = str(intent or "idle")

    def record_decision(self, hero: _Hero, *, action: str, reason: str, intent: str, inputs_summary: dict, source: str, now_ms: int) -> None:
        hero.record_decision(
            action=action,
            reason=reason,
            now_ms=now_ms,
            context={
                "intent": intent,
                "source": source,
                "inputs_summary": dict(inputs_summary),
            },
        )


def _candidate(
    motive: str,
    target_key: str,
    target_xy: tuple[float, float],
    primitive: str,
    *,
    target_ref=None,
    detail: str = "",
    cluster_key: str = "",
) -> daily_life.AmbientCandidate:
    return daily_life.AmbientCandidate(
        motive=motive,
        target_key=target_key,
        target_xy=target_xy,
        primitive=primitive,
        target_ref=target_ref,
        base_score=0.0,
        commit_ms=0,
        cooldown_ms=0,
        cluster_key=cluster_key,
        detail=detail,
    )


def _seed_behavior(
    hero: _Hero,
    candidate: daily_life.AmbientCandidate,
    *,
    now_ms: int,
    last_switch_ms: int | None = None,
    significance: float = 30.0,
    commit_until_ms: int | None = None,
    switch_count: int = 0,
) -> None:
    daily_life.reset_ambient_memory(hero.hero_id)
    daily_life._write_ambient_memory(hero, candidate, now_ms=now_ms)
    mem = daily_life.get_ambient_memory(hero)
    mem["active_significance"] = float(significance)
    mem["last_switch_ms"] = int(now_ms if last_switch_ms is None else last_switch_ms)
    mem["commit_until_ms"] = int(now_ms if commit_until_ms is None else commit_until_ms)
    mem["switch_count"] = int(switch_count)
    mem["behavior_trace"] = []


def _make_spread_view() -> tuple[SimpleNamespace, list[_Hero], _Building]:
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
    return view, heroes, castle


def test_no_rapid_flicker_under_near_tie_pressure_with_trace(monkeypatch) -> None:
    clock = {"now": 20_000}
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: clock["now"])
    ai = _FixedAI()
    inn = _Building("inn", 16 * TILE_SIZE, 15 * TILE_SIZE)
    temple = _Building("temple", 14 * TILE_SIZE, 15 * TILE_SIZE)
    hero = _Hero("wk145_flicker", "Mara", "cleric", "cautious and strategic", 15 * TILE_SIZE, 15 * TILE_SIZE)
    hero.home_building = temple
    current = _candidate("social_linger", "social:inn", (inn.center_x, inn.center_y), "get_drink", target_ref=inn, detail="inn")
    challenger = _candidate(
        "home_or_guild_time",
        "home:temple",
        (temple.center_x, temple.center_y),
        "going_home",
        target_ref=temple,
        detail="temple",
    )
    view = SimpleNamespace(world=None, buildings=[inn, temple], heroes=[hero], pois=[], enemies=[], bounties=[], castle=temple)

    _seed_behavior(hero, current, now_ms=19_000, last_switch_ms=19_000, significance=30.0, commit_until_ms=19_500)

    def _score_fn(ai_obj, hero_obj, candidate_obj, view_obj, *, now_ms=None, ignore_memory_penalties=False):
        phase = ((int(now_ms or 0) - 20_000) // 500) % 2
        if candidate_obj.motive == "social_linger":
            return 31.0 if phase == 0 else 30.0
        if candidate_obj.motive == "home_or_guild_time":
            return 30.0 if phase == 0 else 31.0
        raise AssertionError(candidate_obj.motive)

    monkeypatch.setattr(daily_life, "build_daily_life_candidates", lambda *_a, **_k: [current, challenger])
    monkeypatch.setattr(daily_life, "score_daily_life_candidate", _score_fn)

    for ts in range(20_000, 30_000, 500):
        clock["now"] = ts
        assert daily_life.try_daily_life(ai, hero, view) is True

    snapshot = daily_life.get_ambient_snapshot(hero)
    trace = snapshot["behavior_trace"]

    assert snapshot["active_motive"] == "social_linger"
    assert snapshot["switch_count"] == 0
    assert len(trace) == 20
    assert [entry["t"] for entry in trace] == sorted(entry["t"] for entry in trace)
    assert {entry["to"] for entry in trace} == {"social_linger"}
    assert all(entry["reason"] == "hysteresis_hold" for entry in trace)
    assert max(abs(float(entry["significance_delta"])) for entry in trace) == 1.0


def test_significant_new_motive_overwhelms_current_behavior_once(monkeypatch) -> None:
    clock = {"now": 28_500}
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: clock["now"])
    ai = _FixedAI()
    inn = _Building("inn", 16 * TILE_SIZE, 15 * TILE_SIZE)
    lair = _Building("lair", 25 * TILE_SIZE, 23 * TILE_SIZE, is_lair=True, hp=100, is_alive=True)
    hero = _Hero("wk145_overwhelm", "Bram", "warrior", "balanced and reliable", 15 * TILE_SIZE, 15 * TILE_SIZE)
    current = _candidate("social_linger", "social:inn", (inn.center_x, inn.center_y), "get_drink", target_ref=inn, detail="inn")
    challenger = _candidate("revenge_hero", "revenge:lair", (lair.center_x, lair.center_y), "move_enemy", target_ref=lair, detail="lair")
    view = SimpleNamespace(world=None, buildings=[inn, lair], heroes=[hero], pois=[], enemies=[], bounties=[], castle=inn)

    _seed_behavior(hero, current, now_ms=20_000, last_switch_ms=20_000, significance=30.0, commit_until_ms=20_000)

    def _score_fn(ai_obj, hero_obj, candidate_obj, view_obj, *, now_ms=None, ignore_memory_penalties=False):
        if candidate_obj.motive == "social_linger":
            return 30.0
        if candidate_obj.motive == "revenge_hero":
            return 42.0
        raise AssertionError(candidate_obj.motive)

    monkeypatch.setattr(daily_life, "build_daily_life_candidates", lambda *_a, **_k: [current, challenger])
    monkeypatch.setattr(daily_life, "score_daily_life_candidate", _score_fn)

    assert daily_life.try_daily_life(ai, hero, view) is True
    clock["now"] = 29_000
    assert daily_life.try_daily_life(ai, hero, view) is True

    snapshot = daily_life.get_ambient_snapshot(hero)
    trace = snapshot["behavior_trace"]
    switches = [entry for entry in trace if entry["from"] != entry["to"]]

    assert snapshot["active_motive"] == "revenge_hero"
    assert snapshot["switch_count"] == 1
    assert len(switches) == 1
    assert switches[0]["from"] == "social_linger"
    assert switches[0]["to"] == "revenge_hero"
    assert switches[0]["reason"] == "significance_overwhelm"
    assert float(switches[0]["significance_delta"]) > 6.0
    assert trace[-1]["from"] == "revenge_hero"
    assert trace[-1]["to"] == "revenge_hero"
    assert trace[-1]["reason"] == "hysteresis_hold"


def test_critical_health_bypasses_hysteresis_immediately_toward_safety(monkeypatch) -> None:
    clock = {"now": 29_000}
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: clock["now"])
    ai = _FixedAI()
    castle = _Building("castle", 15 * TILE_SIZE, 15 * TILE_SIZE)
    shrine = _Building("shrine", 23 * TILE_SIZE, 21 * TILE_SIZE)
    hero = _Hero("wk145_safety", "Celia", "wizard", "balanced and reliable", 12 * TILE_SIZE, 12 * TILE_SIZE, hp=24)
    current = _candidate("wilderness_explore", "frontier:23:21", (shrine.center_x, shrine.center_y), "explore_frontier", detail="frontier")
    safe = _candidate("safe_rest", "rest:castle", (castle.center_x, castle.center_y), "going_home", target_ref=castle, detail="castle")
    view = SimpleNamespace(world=None, buildings=[castle, shrine], heroes=[hero], pois=[], enemies=[], bounties=[], castle=castle)

    _seed_behavior(hero, current, now_ms=28_000, last_switch_ms=28_000, significance=40.0, commit_until_ms=60_000)

    def _score_fn(ai_obj, hero_obj, candidate_obj, view_obj, *, now_ms=None, ignore_memory_penalties=False):
        if candidate_obj.motive == "wilderness_explore":
            return 40.0
        if candidate_obj.motive == "safe_rest":
            return 30.0
        raise AssertionError(candidate_obj.motive)

    monkeypatch.setattr(daily_life, "build_daily_life_candidates", lambda *_a, **_k: [current, safe])
    monkeypatch.setattr(daily_life, "score_daily_life_candidate", _score_fn)

    assert daily_life.try_daily_life(ai, hero, view) is True
    clock["now"] = 29_500
    assert daily_life.try_daily_life(ai, hero, view) is True

    snapshot = daily_life.get_ambient_snapshot(hero)
    trace = snapshot["behavior_trace"]

    assert snapshot["active_motive"] == "safe_rest"
    assert snapshot["switch_count"] == 1
    assert trace[0]["reason"] == "urgent_safety_bypass"
    assert float(trace[0]["significance_delta"]) < 0.0
    assert trace[-1]["from"] == "safe_rest"
    assert trace[-1]["to"] == "safe_rest"
    assert trace[-1]["reason"] == "urgent_safety_hold"


def test_existing_wk144_spread_still_holds(monkeypatch) -> None:
    monkeypatch.setattr(daily_life, "sim_now_ms", lambda: 20_000)
    ai = _FixedAI()
    view, heroes, castle = _make_spread_view()

    daily_life.reset_ambient_memory()
    summaries: list[tuple[str, str, str, str, int, int]] = []
    for hero in heroes:
        assert daily_life.try_daily_life(ai, hero, view) is True
        snapshot = daily_life.get_ambient_snapshot(hero)
        summaries.append(
            (
                hero.hero_id,
                snapshot["active_motive"],
                snapshot["active_target_key"],
                snapshot["last_cluster_key"],
                len(snapshot["behavior_trace"]),
                int(snapshot["switch_count"]),
            )
        )

    motives = Counter(motive for _hero_id, motive, _target_key, _cluster_key, _trace_len, _switch_count in summaries)
    clusters = {cluster_key for _hero_id, _motive, _target_key, cluster_key, _trace_len, _switch_count in summaries}

    assert len(motives) >= 5
    assert len(clusters) >= 5
    assert motives["safe_rest"] >= 1
    assert motives["home_or_guild_time"] >= 1
    assert motives["social_linger"] >= 1
    assert motives["poi_scout"] >= 1
    assert motives["monster_patrol"] >= 1
    assert motives["opportunity_check"] >= 1
    assert any(m in {"poi_scout", "wilderness_explore"} for m in motives)
    assert any(m in {"monster_patrol", "opportunity_check"} for m in motives)
    assert len(summaries) == 10
    assert all(trace_len == 1 for _hero_id, _motive, _target_key, _cluster_key, trace_len, _switch_count in summaries)
    assert all(switch_count == 0 for _hero_id, _motive, _target_key, _cluster_key, _trace_len, switch_count in summaries)
