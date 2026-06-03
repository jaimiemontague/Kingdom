"""WK122-BUG-B1 — guardhouse fires TWO arrows, engine propagates BOTH.

The guardhouse builds a volley of ``GUARDHOUSE_ARROWS_PER_SHOT`` (=2) projectile
events with distinct origin offsets (``_last_ranged_events``), plus keeps the
SINGULAR first arrow in ``_last_ranged_event`` for back-compat. The bug was that
``SimEngine._update_buildings`` collected ONLY the singular event, dropping arrow
#2 — so a single ProjectileVFX spawned and the renderer drew one billboard.

These tests prove the fix end-to-end at the engine level:
  * One in-range enemy + one guardhouse, one building-update tick.
  * Exactly 2 ``ranged_projectile`` events reach the event bus per volley.
  * The two events have DIFFERENT origins (distinct ``from_x``/``from_y``).
  * Those 2 events flow through the VFX system into 2 ``ProjectileVFX``, and
    ``build_snapshot(...).vfx_projectiles`` carries 2 entries.

The singular/plural contract pinned by
``tests/test_wk65_buildings_systems_characterization.py`` (singular still set,
both events aimed exactly at the enemy) is exercised here too, so the fix can't
silently drop it.
"""

from __future__ import annotations

from config import GUARDHOUSE_ARROWS_PER_SHOT
from game.entities.buildings.defensive import Guardhouse
from game.entities.enemy import Goblin
from game.graphics.vfx import VFXSystem
from game.sim_engine import SimEngine


def _engine_with_guardhouse_and_enemy() -> tuple[SimEngine, Guardhouse, Goblin]:
    """A minimal SimEngine carrying exactly one guardhouse and one in-range,
    high-HP enemy. We replace the entity lists directly so no spawner/wave noise
    perturbs the building-update collection path under test."""
    sim = SimEngine()

    gh = Guardhouse(10, 10)
    gh.is_constructed = True
    gh.construction_started = True

    # Enemy sits exactly on the guardhouse center -> distance 0, always in range.
    enemy = Goblin(gh.center_x, gh.center_y)
    # Keep it alive through the volley so it stays a valid target / snapshot
    # entity (is_alive is a read-only property derived from hp > 0).
    enemy.max_hp = 100_000
    enemy.hp = enemy.max_hp

    sim.buildings = [gh]
    sim.enemies = [enemy]
    sim.guards = []
    return sim, gh, enemy


def _collect_ranged_events(sim: SimEngine) -> list[dict]:
    collected: list[dict] = []
    sim.event_bus.subscribe("ranged_projectile", lambda e: collected.append(e))
    return collected


def test_engine_collects_two_arrow_events_per_volley() -> None:
    """One building-update tick produces exactly GUARDHOUSE_ARROWS_PER_SHOT (=2)
    ranged_projectile events on the event bus."""
    sim, gh, enemy = _engine_with_guardhouse_and_enemy()
    collected = _collect_ranged_events(sim)

    # Run the exact method that collects + emits building ranged events.
    sim._update_buildings(dt=0.001)
    sim.event_bus.flush()

    assert GUARDHOUSE_ARROWS_PER_SHOT == 2  # guards the expected-count assertions
    assert len(collected) == GUARDHOUSE_ARROWS_PER_SHOT
    for ev in collected:
        assert ev["type"] == "ranged_projectile"
        assert ev["projectile_kind"] == "arrow"


def test_two_arrow_events_have_distinct_origins() -> None:
    """The two arrows fire from two distinct spots on the guardhouse (distinct
    from_x/from_y) while aiming at the SAME target (exact enemy position)."""
    sim, gh, enemy = _engine_with_guardhouse_and_enemy()
    collected = _collect_ranged_events(sim)

    sim._update_buildings(dt=0.001)
    sim.event_bus.flush()

    assert len(collected) == 2
    a, b = collected[0], collected[1]

    # Distinct origins (the whole point of two visible arrows).
    assert (a["from_x"], a["from_y"]) != (b["from_x"], b["from_y"])

    # Both aimed exactly at the enemy (target unchanged — pins the WK65 contract).
    for ev in (a, b):
        assert ev["to_x"] == float(enemy.x)
        assert ev["to_y"] == float(enemy.y)


def test_singular_event_still_set_and_matches_first_arrow() -> None:
    """Back-compat: the guardhouse still sets the SINGULAR _last_ranged_event to
    the first arrow before the engine clears it. Verify by inspecting the
    building right after its own update() (engine clears it afterwards)."""
    gh = Guardhouse(10, 10)
    enemy = Goblin(gh.center_x, gh.center_y)
    enemy.max_hp = 100_000
    enemy.hp = enemy.max_hp

    gh.update(dt=0.001, guards_list=[], enemies=[enemy])

    assert gh._last_ranged_events  # plural populated
    assert len(gh._last_ranged_events) == GUARDHOUSE_ARROWS_PER_SHOT
    assert gh._last_ranged_event is not None
    assert gh._last_ranged_event == gh._last_ranged_events[0]
    assert gh._last_ranged_event["to_x"] == float(enemy.x)
    assert gh._last_ranged_event["to_y"] == float(enemy.y)


def test_two_projectiles_reach_snapshot_vfx() -> None:
    """The two collected events flow through the VFX system into two
    ProjectileVFX, and build_snapshot(...).vfx_projectiles carries 2 entries."""
    sim, gh, enemy = _engine_with_guardhouse_and_enemy()

    # Wire a real VFX system as an event-bus subscriber, exactly like the
    # presentation layer does, so emitted ranged events spawn projectiles.
    vfx = VFXSystem()
    sim.event_bus.subscribe("ranged_projectile", vfx.on_event)

    sim._update_buildings(dt=0.001)
    sim.event_bus.flush()

    projectiles = vfx.get_active_projectiles()
    assert len(projectiles) == GUARDHOUSE_ARROWS_PER_SHOT

    snapshot = sim.build_snapshot(vfx_projectiles=tuple(projectiles))
    assert len(snapshot.vfx_projectiles) == GUARDHOUSE_ARROWS_PER_SHOT


def test_events_cleared_after_collection_no_double_emit() -> None:
    """After the engine collects a volley it clears BOTH the plural list and the
    singular field, so a follow-up tick (still on cooldown) emits nothing."""
    sim, gh, enemy = _engine_with_guardhouse_and_enemy()
    collected = _collect_ranged_events(sim)

    sim._update_buildings(dt=0.001)
    sim.event_bus.flush()
    assert len(collected) == 2

    # Building's stored events are cleared by the engine after collection.
    assert not getattr(gh, "_last_ranged_events", [])
    assert getattr(gh, "_last_ranged_event", None) is None

    # A second tick well inside the cooldown fires no new volley.
    collected.clear()
    sim._update_buildings(dt=0.001)
    sim.event_bus.flush()
    assert collected == []
