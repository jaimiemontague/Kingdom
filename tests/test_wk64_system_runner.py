"""WK64 Phase B Wave 0 — system-update characterization tests.

Sprint: wk64_ai_contracts_and_system_runner
Round:  wk64_pb_w0_characterization
Owner:  Agent 11 (QA_TestEngineering_Lead)

Purpose
-------
Pin the CURRENT system-update behavior so Agent 05's Wave-1 ``SystemRunner`` /
widened ``SystemContext`` refactor cannot silently change it. These PASS against
current (post-Phase-A) code with no production changes.

DETERMINISTIC_SIM note
----------------------
``config.DETERMINISTIC_SIM`` defaults to ``0`` (False), so in the default
runtime config ``SimEngine.update()`` does NOT advance ``_sim_now_ms`` -- the
sim-time accounting branch (sim_engine.py ~line 607) is gated on
``DETERMINISTIC_SIM``. The plan's "advances sim time once" test therefore only
holds when deterministic sim time is forced on. We follow the project's
established convention from ``tests/test_engine_sim_boundary.py`` and use
``unittest.mock.patch`` to force ``DETERMINISTIC_SIM=True`` in BOTH ``game.engine``
and ``game.sim_engine`` (the constant is imported into each module at import
time, so both must be patched). With the patch a single ``engine.update(0.05)``
advances sim time by exactly 50ms -- which is precisely the contract the plan
intends to pin. This is the only deviation from the literal plan scaffold and
exists solely to satisfy the non-negotiable "must PASS on current code"
requirement.
"""

import pygame
import pytest
from unittest.mock import patch

from game.engine import GameEngine


def test_sim_update_runs_without_error_and_advances():
    """A single sim update tick completes and advances sim time deterministically.

    Requires DETERMINISTIC_SIM forced on (it defaults off); see module docstring.
    """
    with patch("game.engine.DETERMINISTIC_SIM", True), \
         patch("game.sim_engine.DETERMINISTIC_SIM", True):
        engine = GameEngine(headless=True)
        try:
            before = int(engine.sim._sim_now_ms)
            engine.update(0.05)
            after = int(engine.sim._sim_now_ms)
            assert after - before == 50, f"expected +50ms, got {after - before}"
        finally:
            pygame.quit()


def test_system_context_has_core_fields_today():
    """Documents the CURRENT SystemContext shape. Wave 1 widens it (adds fields);
    these core fields must remain."""
    from game.systems.protocol import SystemContext
    import dataclasses
    names = {f.name for f in dataclasses.fields(SystemContext)}
    for required in ("heroes", "enemies", "buildings", "world", "economy", "event_bus"):
        assert required in names


def test_combat_buff_waveevent_systems_expose_update_ctx():
    """These three are already driven via update(ctx, dt) today and must stay so."""
    from game.systems.combat import CombatSystem
    from game.systems.buffs import BuffSystem
    from game.systems.wave_events import WaveEventSystem
    for cls in (CombatSystem, BuffSystem, WaveEventSystem):
        assert hasattr(cls, "update")


def test_engine_stable_over_120_ticks():
    engine = GameEngine(headless=True)
    try:
        for _ in range(120):
            engine.update(1.0 / 30.0)
        assert isinstance(engine.sim.heroes, list)
        assert isinstance(engine.sim.enemies, list)
    finally:
        pygame.quit()
