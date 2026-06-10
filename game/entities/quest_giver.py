"""WK126 — Quest-Giver NPC (spawned beside a constructed Herald's Post).

Modeled on game/entities/tax_collector.py (a placed, self-directed NPC) but
STATIONARY for MVP: it stands beside its post (guardhouse→guard spawn pattern in
``SimEngine._update_buildings``), carries the open-offer flag that drives the
yellow "!" overhead marker (Agent 09), and is the thing heroes walk up to
(Agent 06's ``quest_offer`` target). No roaming FSM, no per-tick logic of its
own — ``SimEngine`` mirrors ``is_open`` from the QuestSystem each tick (only
when givers exist, so the WK67 digest scenario — which has no Herald's Post —
never touches this code).

Exactly ONE QuestGiver per constructed Herald's Post; removed when the post is
destroyed (SimEngine culls givers whose post left ``self.buildings``).
"""
from __future__ import annotations

import math

from config import QUEST_GIVER_INTERACT_PX, TILE_SIZE

# Deterministic spawn offset from the post center (mirrors the guardhouse→guard
# spawn at SimEngine._update_buildings: center_x + TILE_SIZE, center_y).
SPAWN_OFFSET_X = TILE_SIZE
SPAWN_OFFSET_Y = 0.0


class QuestGiver:
    """Stationary quest-offering NPC beside its owning Herald's Post."""

    def __init__(self, post):
        self.post = post  # owning Herald's Post building (live ref, sim-side only)
        # giver_id == owning post id (the stable Building.entity_id, e.g. "b00000007").
        self.giver_id = str(getattr(post, "entity_id", "") or "")
        self.x = float(post.center_x) + SPAWN_OFFSET_X
        self.y = float(post.center_y) + SPAWN_OFFSET_Y

        # Open-offer flag — mirrors whether the post has an open (unaccepted)
        # quest. Synced by SimEngine each tick; drives the "!" marker (T8) and
        # the AI candidate list (T5).
        self.is_open = False
        self.interact_radius = float(QUEST_GIVER_INTERACT_PX)

        # Entity-protocol conveniences (renderer / cleanup parity with other NPCs).
        self.is_alive = True
        self.size = 14
        self.color = (240, 200, 60)  # herald gold
        self._render_anim_trigger: str | None = None
        self._anim_trigger_seq: int = 0

    def distance_to(self, x: float, y: float) -> float:
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    @property
    def render_state(self) -> "QuestGiver":
        """Render accessor used by render-side systems (mirrors TaxCollector)."""
        return self

    def to_ai_info(self):
        """Plain-data, immutable AI snapshot (the T4 boundary contract)."""
        from game.systems.quest import QuestGiverAiInfo

        return QuestGiverAiInfo(
            giver_id=str(self.giver_id),
            x=float(self.x),
            y=float(self.y),
            is_open=bool(self.is_open),
            interact_radius=float(self.interact_radius),
        )
