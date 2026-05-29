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
        # side-effect-free.
        _ = [(getattr(h, "x", None), getattr(h, "y", None)) for h in snap.heroes]
        _ = [(getattr(e, "x", None), getattr(e, "hp", None)) for e in snap.enemies]
        _ = [(getattr(b, "building_type", None), getattr(b, "hp", None)) for b in snap.buildings]
        _ = list(snap.peasants)
        _ = list(snap.guards)
        _ = list(snap.bounties)

        after = _digest(engine)

        assert before == after, "build_snapshot() mutated live sim entities"
    finally:
        pygame.quit()


def test_build_snapshot_lists_are_copies_not_aliases():
    """The snapshot's entity tuples must be independent copies of engine lists.

    Guards the other half of the read-only contract: even if a renderer (or this
    test) appended to a snapshot-derived sequence, it must not reach back into the
    engine's live lists. `SimStateSnapshot` stores tuples, so they are by construction
    distinct objects from the engine's lists; assert that explicitly.
    """
    engine = GameEngine(headless=True)
    try:
        snap = engine.build_snapshot()

        # Tuples are immutable + a distinct object from the live list.
        assert snap.heroes is not engine.heroes
        assert snap.enemies is not engine.enemies
        assert snap.buildings is not engine.buildings

        # Same membership at snapshot time (shallow copy contract).
        assert list(snap.heroes) == list(engine.heroes)
        assert list(snap.enemies) == list(engine.enemies)
        assert list(snap.buildings) == list(engine.buildings)
    finally:
        pygame.quit()
