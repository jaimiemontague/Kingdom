"""WK65 Round 0 — snapshot-no-mutation guard.

Pins that building a read-only render snapshot via the engine's renderer-facing
entry point (`GameEngine.build_snapshot()`) does NOT mutate any live sim entity.

Why this matters (Round 0 / Round A precondition):
- `SimStateSnapshot` shallow-copies the engine's entity *lists* (so list membership
  is frozen) but the individual entities are the same live objects the sim mutates.
  Renderers are contractually read-only consumers. This test is the bracket that
  proves the snapshot build path itself never writes back to entity fields
  (positions / hp / level / gold / xp / state / flags), and stays GREEN before and
  after the Wave-2 render-code deletions.

Entry point used: `engine.build_snapshot()` (game/engine.py) — the zero-arg
renderer entry point, which delegates to `engine.sim.build_snapshot(**frame_kwargs)`
(game/sim_engine.py). The sim-level method requires per-frame kwargs, so the engine
method is the real renderer contract (see tests/test_renderer_snapshot_contract.py).

Mirrors the existing contract test style: `GameEngine(headless=True)` + `pygame.quit()`.
"""

from __future__ import annotations

import pygame

from game.engine import GameEngine


# Sentinel for "attribute not present on this entity" so the digest is stable
# regardless of which exact fields each entity type exposes.
_MISSING = "<missing>"

# Fields a renderer reads off entities. Position + health + the per-entity state
# that drives sprite/animation/HUD selection. Read-only — never written here.
_ENTITY_FIELDS = (
    "x",
    "y",
    "hp",
    "max_hp",
    "level",
    "gold",
    "xp",
    "state",
    "target",
    "is_alive",
    "is_constructed",
    "construction_progress",
    "building_type",
    "enemy_type",
)


def _entity_digest(entity) -> tuple:
    """A hashable, comparable snapshot of one entity's renderer-visible fields.

    `state`/`target`/`building_type` may be enums or object references; coerce to a
    stable string so equality compares value, not identity-of-a-mutated-object.
    """
    out: list = []
    for field in _ENTITY_FIELDS:
        if not hasattr(entity, field):
            out.append((field, _MISSING))
            continue
        try:
            value = getattr(entity, field)
        except Exception:  # property that raises for this entity kind
            out.append((field, _MISSING))
            continue
        # Coerce floats to rounded values so trivial fp noise (there should be none,
        # since we don't tick the sim) never makes the test flaky.
        if isinstance(value, float):
            value = round(value, 6)
        elif isinstance(value, (int, bool, str, type(None))):
            pass
        else:
            # Enums (HeroState), entity refs (target), enum-valued building_type, etc.
            value = repr(value)
        out.append((field, value))
    return tuple(out)


def _digest(engine: GameEngine) -> dict:
    """Digest every live entity the renderer draws, keyed by list + index.

    Heroes / enemies / buildings get a full per-entity field digest. Peasants and
    guards are length-pinned so a stray append/clear during snapshot is also caught.
    """
    return {
        "heroes": tuple(_entity_digest(h) for h in engine.heroes),
        "enemies": tuple(_entity_digest(e) for e in engine.enemies),
        "buildings": tuple(_entity_digest(b) for b in engine.buildings),
        "peasants_len": len(engine.peasants),
        "guards_len": len(engine.guards),
        "gold": int(getattr(engine.economy, "player_gold", 0)),
    }


def test_build_snapshot_does_not_mutate_entities():
    """`engine.build_snapshot()` is read-only w.r.t. sim entities."""
    engine = GameEngine(headless=True)
    try:
        # Sanity: there must be entities worth checking (castle at minimum).
        assert len(engine.buildings) >= 1, "expected at least the castle building"

        before = _digest(engine)

        snap = engine.build_snapshot()

        # Touch the snapshot exactly like a renderer would (read-only iteration of
        # the renderer-consumed lists). This is the access pattern we are pinning as
        # side-effect-free. WK68 R3: the live entity tuples were deleted; renderers
        # now read the frozen *_dtos tuples, so iterate those.
        _ = [(getattr(h, "x", None), getattr(h, "y", None)) for h in snap.hero_dtos]
        _ = [(getattr(e, "x", None), getattr(e, "hp", None)) for e in snap.enemy_dtos]
        _ = [(getattr(b, "building_type", None), getattr(b, "hp", None)) for b in snap.building_dtos]
        _ = list(snap.peasant_dtos)
        _ = list(snap.guard_dtos)
        _ = list(snap.bounty_dtos)

        after = _digest(engine)

        assert before == after, "build_snapshot() mutated live sim entities"
    finally:
        pygame.quit()


def test_build_snapshot_lists_are_copies_not_aliases():
    """The snapshot's render-DTO tuples must be independent of the engine lists.

    Guards the other half of the read-only contract: even if a renderer (or this
    test) appended to a snapshot-derived sequence, it must not reach back into the
    engine's live lists. WK68 R3: the snapshot no longer carries the live entity
    tuples — it carries frozen value-type DTO tuples, which are by construction
    distinct objects from the engine's live lists. Assert that, plus that the DTOs
    cover exactly the live entities (same count + stable ids) at snapshot time.
    """
    engine = GameEngine(headless=True)
    try:
        snap = engine.build_snapshot()

        # The DTO tuples are distinct objects from the engine's live lists.
        assert snap.hero_dtos is not engine.heroes
        assert snap.enemy_dtos is not engine.enemies
        assert snap.building_dtos is not engine.buildings

        # Same membership at snapshot time (one DTO per live entity, stable ids).
        assert [d.entity_id for d in snap.hero_dtos] == [
            str(getattr(h, "hero_id", None) or getattr(h, "entity_id", None) or id(h))
            for h in engine.heroes
        ]
        assert [d.entity_id for d in snap.enemy_dtos] == [
            str(getattr(e, "entity_id", None) or id(e)) for e in engine.enemies
        ]
        assert [d.entity_id for d in snap.building_dtos] == [
            str(getattr(b, "entity_id", None) or id(b)) for b in engine.buildings
        ]
    finally:
        pygame.quit()
