"""WK126 — Quest data model + QuestSystem (Herald's Post on-map quests).

Deliberately a near-clone of the bounty system (game/systems/bounty.py): the
player funds a reward (gold escrow at creation, ``economy.fund_quest``), a hero
accepts the offer at a Quest-Giver NPC, and the system detects completion and
pays the accepted hero via ``hero.add_gold(reward)`` (the existing 25%-tax
payout path — no new payout plumbing).

Quest types (the Wave-2 contract vocabulary):
    "raid_lair"       target = lair object        (completes via LAIR_CLEARED routing)
    "slay_enemy_type" target = enemy_type str     (ENEMY_KILLED counter; ``count`` kills)
    "find_poi"        target = POI object         (accepting-hero proximity poll)
    "explore_far"     target = (tile_x, tile_y)   (fog SEEN poll around the tile)

DIGEST RAILS (WK126 central constraint — tests/test_wk67_ai_boundary.py):
``QuestSystem.update`` EARLY-RETURNS (no events, no RNG, no state mutation)
when ``self.quests`` is empty, and the system draws NO randomness ever. The
event-routing hooks (``on_lair_cleared`` / ``on_enemy_killed``) early-return the
same way. The WK67 digest scenario contains zero quests, so every path here is
structurally unreachable in it.

Determinism: time only from ``game.sim.timebase.now_ms``; NO RNG in this module.

Failure policy (PM decision of record, WK133 kickoff): rewards are GOLD-ONLY;
on failure the escrow is CONSUMED (no refund) and the giver becomes re-armable;
``QUEST_FAILED`` is emitted.
"""
from __future__ import annotations

from collections import namedtuple

from config import (
    QUEST_EXPLORE_REVEAL_RADIUS_TILES,
    TILE_SIZE,
)
from game.events import GameEventType
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.protocol import GameSystem, SystemContext

# The four in-scope quest types (rare-item quests are deferred — no loot system).
QUEST_TYPES = ("raid_lair", "slay_enemy_type", "find_poi", "explore_far")

# Arrival radius for find_poi completion (mirrors the 2-tile proximity used by
# bounty claims / POI interactions).
_FIND_POI_ARRIVAL_PX = TILE_SIZE * 2

# explore_far: the accepting hero must actually be the one at the frontier when
# the tiles flip SEEN — "nearby" = within (reveal radius + hero vision slack).
_EXPLORE_HERO_NEARBY_PX = TILE_SIZE * (QUEST_EXPLORE_REVEAL_RADIUS_TILES + 5)


# ---------------------------------------------------------------------------
# Plain-data AI snapshots (the T4 boundary contract — immutable, no live refs).
# ``SimEngine.build_ai_view`` fills ``view.quests`` / ``view.quest_givers`` with
# tuples of these; Agent 06 reads attributes only.
# ---------------------------------------------------------------------------
QuestAiInfo = namedtuple(
    "QuestAiInfo",
    [
        "quest_id",     # int
        "giver_id",     # str — owning Herald's Post Building.entity_id
        "quest_type",   # one of QUEST_TYPES
        "target",       # plain-data target summary (NEVER an object ref):
                        #   raid_lair/find_poi -> target building's entity_id str
                        #   slay_enemy_type    -> the enemy_type str
                        #   explore_far        -> "gx,gy" tile str
        "reward",       # int gold (player-escrowed)
        "is_open",      # bool — funded, unaccepted, not completed/failed
        "accepted_by",  # str hero_id or None
        "x",            # float world px of the objective (0.0 for slay_enemy_type)
        "y",
        "count",        # int — N kills for slay_enemy_type, else 1
        "progress",     # int — kill counter for slay, 0/1 otherwise
    ],
)

QuestGiverAiInfo = namedtuple(
    "QuestGiverAiInfo",
    [
        "giver_id",        # str — owning post's Building.entity_id
        "x",               # float world px (NPC stands beside its post)
        "y",
        "is_open",         # bool — the post has an open (unaccepted) quest
        "interact_radius", # float px — arrival radius at the NPC
    ],
)


class Quest:
    """A player-funded quest offer attached to a Herald's Post quest-giver."""

    _NEXT_ID = 1

    def __init__(self, giver_id, quest_type, target, reward, *, count=1, created_time_ms=None):
        self.quest_id = Quest._NEXT_ID
        Quest._NEXT_ID += 1
        self.giver_id = str(giver_id)
        self.quest_type = str(quest_type)  # see QUEST_TYPES
        self.target = target               # lair obj | enemy_type str | poi obj | (tile_x, tile_y)
        self.count = max(1, int(count)) if self.quest_type == "slay_enemy_type" else 1
        self.progress = 0
        self.reward = int(reward)          # PLAYER-funded gold (escrowed at creation)
        self.funded = True
        self.accepted_by = None            # hero_id (str) once a hero takes it
        self.accepted_by_name = None       # display-name mirror for HUD messages
        self.accepted_time_ms = None
        self.completed = False
        self.failed = False
        self.created_time_ms = (
            int(created_time_ms) if created_time_ms is not None else int(sim_now_ms())
        )

    @property
    def is_open(self) -> bool:
        """Funded, unaccepted, not finished — drives the '!' marker + AI candidates."""
        return bool(self.funded) and self.accepted_by is None and not self.completed and not self.failed

    def accept(self, hero) -> bool:
        """A hero takes this offer. Returns False if it is no longer open."""
        if not self.is_open:
            return False
        self.accepted_by = str(getattr(hero, "hero_id", "") or "")
        self.accepted_by_name = str(getattr(hero, "name", "") or "")
        self.accepted_time_ms = int(sim_now_ms())
        return True

    def is_target_alive(self, buildings: list) -> bool:
        """Whether the quest's objective still exists (pre/post acceptance)."""
        if self.quest_type == "raid_lair":
            return (self.target in buildings) and getattr(self.target, "hp", 1) > 0
        if self.quest_type == "find_poi":
            return self.target in buildings
        # slay_enemy_type: valid while target is a non-empty enemy-type string.
        if self.quest_type == "slay_enemy_type":
            return isinstance(self.target, str) and bool(self.target.strip())
        # explore_far: a map tile never disappears.
        return True

    def get_goal_position(self) -> tuple[float, float]:
        """World-px objective position (0,0 for slay_enemy_type — hunt anywhere)."""
        if self.quest_type in ("raid_lair", "find_poi") and self.target is not None:
            return (
                float(getattr(self.target, "center_x", getattr(self.target, "x", 0.0))),
                float(getattr(self.target, "center_y", getattr(self.target, "y", 0.0))),
            )
        if self.quest_type == "explore_far" and isinstance(self.target, (tuple, list)):
            tx, ty = self.target
            return (
                (float(tx) + 0.5) * TILE_SIZE,
                (float(ty) + 0.5) * TILE_SIZE,
            )
        return (0.0, 0.0)

    def target_summary(self) -> str:
        """Plain-data target identifier for the AI boundary (never an object)."""
        if self.quest_type == "slay_enemy_type":
            return str(self.target)
        if self.quest_type == "explore_far" and isinstance(self.target, (tuple, list)):
            return f"{int(self.target[0])},{int(self.target[1])}"
        return str(getattr(self.target, "entity_id", "") or "")

    def to_ai_info(self) -> QuestAiInfo:
        gx, gy = self.get_goal_position()
        return QuestAiInfo(
            quest_id=int(self.quest_id),
            giver_id=str(self.giver_id),
            quest_type=str(self.quest_type),
            target=self.target_summary(),
            reward=int(self.reward),
            is_open=bool(self.is_open),
            accepted_by=self.accepted_by,
            x=float(gx),
            y=float(gy),
            count=int(self.count),
            progress=int(self.progress),
        )


class QuestSystem(GameSystem):
    """Holds quests; registered/ticked on SimEngine mirroring BountySystem.

    DIGEST GUARD #2: ``update`` early-returns (no events, no RNG, no mutation)
    when there are no quests. This module never draws RNG at all.
    """

    def __init__(self):
        self.quests: list[Quest] = []
        self.total_completed = 0
        self.total_failed = 0

    # ------------------------------------------------------------------
    # Creation / lookup (escrow is debited by the caller — SimEngine.create_quest
    # runs economy.fund_quest BEFORE calling this; the UI never calls this raw).
    # ------------------------------------------------------------------
    def create_quest(self, giver_id, quest_type, target, reward, *, count=1) -> Quest:
        quest = Quest(giver_id, quest_type, target, reward, count=count)
        self.quests.append(quest)
        return quest

    def has_open_quest_for(self, giver_id) -> bool:
        gid = str(giver_id)
        return any(q.is_open and q.giver_id == gid for q in self.quests)

    def open_quest_for(self, giver_id) -> Quest | None:
        """The first open offer on this giver (what a hero is shown on arrival)."""
        gid = str(giver_id)
        for q in self.quests:
            if q.is_open and q.giver_id == gid:
                return q
        return None

    def get_active_quests(self) -> list[Quest]:
        return [q for q in self.quests if not q.completed and not q.failed]

    # ------------------------------------------------------------------
    # Tick (GameSystem protocol)
    # ------------------------------------------------------------------
    def update(self, ctx: SystemContext, dt: float) -> None:
        if not self.quests:
            return  # DIGEST GUARD #2 — complete no-op when there are no quests.
        _ = dt

        heroes = ctx.heroes or []
        buildings = ctx.buildings or []

        for quest in self.quests:
            if quest.completed or quest.failed:
                continue

            # Target gone before/after acceptance -> fail (escrow consumed).
            if not quest.is_target_alive(buildings):
                self._fail(quest, ctx.event_bus, reason="target_gone")
                continue

            if quest.accepted_by is None:
                continue

            hero = _find_hero(heroes, quest.accepted_by)
            if hero is None or not getattr(hero, "is_alive", True):
                self._fail(quest, ctx.event_bus, reason="hero_died")
                continue

            if quest.quest_type == "find_poi":
                gx, gy = quest.get_goal_position()
                if _dist_sq(hero, gx, gy) <= _FIND_POI_ARRIVAL_PX * _FIND_POI_ARRIVAL_PX:
                    self._complete(quest, hero, ctx.event_bus)
            elif quest.quest_type == "explore_far":
                if self._explore_far_done(quest, hero, ctx.world):
                    self._complete(quest, hero, ctx.event_bus)
            elif quest.quest_type == "slay_enemy_type":
                # Progress is incremented by on_enemy_killed; double-check here so
                # a quest can never get stuck if the hook completed-check races.
                if quest.progress >= quest.count:
                    self._complete(quest, hero, ctx.event_bus)
            elif quest.quest_type == "raid_lair":
                # raid_lair completes via on_lair_cleared (LAIR_CLEARED routing);
                # WK133 QA gap 1: re-pin a raider who got pulled into combat and
                # came back IDLE with no target (quest would otherwise dangle).
                self._repin_idle_raider(quest, hero)

        # Drop finished quests (mirrors BountySystem.cleanup) — the giver becomes
        # re-armable because has_open_quest_for / open_quest_for no longer match.
        if any(q.completed or q.failed for q in self.quests):
            self.quests = [q for q in self.quests if not q.completed and not q.failed]

    # ------------------------------------------------------------------
    # Event-routing hooks (called from SimEngine._route_combat_events)
    # ------------------------------------------------------------------
    def on_lair_cleared(self, lair_obj, heroes: list, event_bus) -> None:
        """raid_lair completion: match accepted quests whose target IS that lair."""
        if not self.quests:
            return
        for quest in self.quests:
            if quest.completed or quest.failed:
                continue
            if quest.quest_type != "raid_lair" or quest.target is not lair_obj:
                continue
            if quest.accepted_by is None:
                # Lair cleared before any hero took the offer: objective is gone.
                self._fail(quest, event_bus, reason="target_gone")
                continue
            hero = _find_hero(heroes, quest.accepted_by)
            if hero is None or not getattr(hero, "is_alive", True):
                self._fail(quest, event_bus, reason="hero_died")
                continue
            self._complete(quest, hero, event_bus)

    def on_enemy_killed(self, enemy_type: str, killer_hero, event_bus) -> None:
        """slay_enemy_type progress: kills by the ACCEPTING hero of the right type."""
        if not self.quests:
            return
        if killer_hero is None:
            return
        killer_id = str(getattr(killer_hero, "hero_id", "") or "")
        etype = str(enemy_type or "")
        for quest in self.quests:
            if quest.completed or quest.failed:
                continue
            if quest.quest_type != "slay_enemy_type" or quest.accepted_by is None:
                continue
            if quest.accepted_by != killer_id or str(quest.target) != etype:
                continue
            quest.progress += 1
            if quest.progress >= quest.count:
                self._complete(quest, killer_hero, event_bus)

    def on_giver_destroyed(self, giver_id, event_bus) -> None:
        """WK133: the giver's Herald's Post was destroyed (NPC culled).

        An OPEN (unaccepted) offer on that giver is unreachable forever — there
        is no NPC left to walk to — so it FAILS (escrow consumed per the PM
        decision of record, ``QUEST_FAILED`` emitted) and is dropped immediately
        so ``view.quests`` stops carrying it. An ACCEPTED quest SURVIVES: the
        hero is already on the job and completion pays normally.
        """
        if not self.quests:
            return  # DIGEST GUARD — complete no-op when there are no quests.
        gid = str(giver_id)
        dropped = False
        for quest in self.quests:
            if quest.completed or quest.failed:
                continue
            if quest.giver_id == gid and quest.accepted_by is None:
                self._fail(quest, event_bus, reason="giver_destroyed")
                dropped = True
        if dropped:
            self.quests = [q for q in self.quests if not q.completed and not q.failed]

    # ------------------------------------------------------------------
    # Completion / failure internals
    # ------------------------------------------------------------------
    @staticmethod
    def _repin_idle_raider(quest: Quest, hero) -> None:
        """WK133 QA gap 1: an accepted raider who finished an interrupting fight
        sits IDLE with no target — re-point it at the (still-alive) lair. Only
        fires for truly idle heroes (never hijacks fighting/resting/shopping)
        and only when FIT (>= 60% HP): a wounded raider must keep its normal
        retreat/rest cycle, not be thrown back at the lair to die (this exact
        death-loop showed up in the WK126 raid soak while tuning)."""
        from game.entities.hero import HeroState  # lazy: avoid entity import cycle

        if getattr(hero, "state", None) != HeroState.IDLE:
            return
        if getattr(hero, "target", None) is not None:
            return
        max_hp = float(getattr(hero, "max_hp", 0) or 0)
        if max_hp > 0 and float(getattr(hero, "hp", 0)) < 0.6 * max_hp:
            return
        lair = quest.target
        hero.target = lair  # live-entity target: the MOVING/FIGHTING path raids it
        hero.set_target_position(
            float(getattr(lair, "center_x", getattr(lair, "x", hero.x))),
            float(getattr(lair, "center_y", getattr(lair, "y", hero.y))),
        )
        hero.state = HeroState.MOVING
    def _explore_far_done(self, quest: Quest, hero, world) -> bool:
        """All tiles within QUEST_EXPLORE_REVEAL_RADIUS_TILES of the target tile are
        SEEN (or better) AND the accepting hero is the one nearby."""
        if not isinstance(quest.target, (tuple, list)) or len(quest.target) != 2:
            return False
        if world is None:
            return False
        visibility = getattr(world, "visibility", None)
        if not visibility:
            return False
        from game.world import Visibility

        tx, ty = int(quest.target[0]), int(quest.target[1])
        width = int(getattr(world, "width", 0))
        height = int(getattr(world, "height", 0))
        r = int(QUEST_EXPLORE_REVEAL_RADIUS_TILES)
        for gy in range(max(0, ty - r), min(height, ty + r + 1)):
            row = visibility[gy]
            for gx in range(max(0, tx - r), min(width, tx + r + 1)):
                if row[gx] < Visibility.SEEN:
                    return False
        gx_px, gy_px = quest.get_goal_position()
        return _dist_sq(hero, gx_px, gy_px) <= _EXPLORE_HERO_NEARBY_PX * _EXPLORE_HERO_NEARBY_PX

    def _complete(self, quest: Quest, hero, event_bus) -> None:
        quest.completed = True
        self.total_completed += 1
        # Existing taxed payout path — identical to bounty claims (25% hero tax).
        if hasattr(hero, "add_gold"):
            hero.add_gold(quest.reward)
        else:  # pragma: no cover — prototype-friendly fallback (mirrors Bounty.claim)
            hero.gold += quest.reward
        if event_bus is not None:
            hero_name = str(getattr(hero, "name", "") or "")
            event_bus.emit(
                {
                    "type": GameEventType.QUEST_COMPLETED.value,
                    "quest_id": int(quest.quest_id),
                    "quest_type": str(quest.quest_type),
                    "giver_id": str(quest.giver_id),
                    "reward": int(quest.reward),
                    "hero": hero_name,
                    "hero_id": str(getattr(hero, "hero_id", "") or ""),
                }
            )
            event_bus.emit(
                {
                    "type": GameEventType.HUD_MESSAGE.value,
                    "text": f"{hero_name} completed a quest! (+{int(quest.reward)}g)",
                    "color": (255, 215, 0),
                }
            )

    def _fail(self, quest: Quest, event_bus, *, reason: str) -> None:
        """Escrow stays consumed (PM decision); the giver becomes re-armable."""
        quest.failed = True
        self.total_failed += 1
        if event_bus is not None:
            event_bus.emit(
                {
                    "type": GameEventType.QUEST_FAILED.value,
                    "quest_id": int(quest.quest_id),
                    "quest_type": str(quest.quest_type),
                    "giver_id": str(quest.giver_id),
                    "reward": int(quest.reward),
                    "reason": str(reason),
                }
            )
            event_bus.emit(
                {
                    "type": GameEventType.HUD_MESSAGE.value,
                    "text": "A quest failed — the reward is forfeit.",
                    "color": (220, 20, 60),
                }
            )


def _find_hero(heroes: list, hero_id: str):
    target = str(hero_id)
    for hero in heroes:
        if str(getattr(hero, "hero_id", "")) == target:
            return hero
    return None


def _dist_sq(entity, x: float, y: float) -> float:
    dx = float(getattr(entity, "x", 0.0)) - float(x)
    dy = float(getattr(entity, "y", 0.0)) - float(y)
    return dx * dx + dy * dy
