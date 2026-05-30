"""WK68 Round R0 — per-build determinism-reset pin (Agent 04 NetworkingDeterminism).

This pin proves the WK68 R0 production change: the sim-owned per-build reset
``SimEngine._reset_global_sim_state()`` (game/sim_engine.py) makes two same-seed
``GameEngine`` builds **inside one process** produce byte-identical AI behavior,
WITHOUT moving the WK67 keystone AI-decision digest
``b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded``.

WHY THIS MATTERS (the leak it closes)
-------------------------------------
Several sim subsystems keep module/class-global mutable state that survives across
``GameEngine`` constructions in one process:

* ``ai.basic_ai._AI_RNG`` — the shared AI patrol/wander RNG, created once at import
  and aliased by every ``BasicAI``; never re-seeded per build, so its stream keeps
  advancing from where the previous build's tick loop left off.
* ``game.entities.buildings.base.RESEARCH_UNLOCKS`` — module-global dict mutated in
  place by ``unlock_research()``; never reset.
* the monotonic ``_next_*_id`` entity-ID counters + ``Peasant._spawn_counter``.

Before R0 those carry-overs made two same-seed in-process builds DIVERGE (the WK67
PM NOTE documents three distinct digests over three back-to-back builds). The WK67
keystone worked around this by computing the digest in a FRESH SUBPROCESS (clean
globals). R0 moves the reset into production so in-process builds are deterministic
too — which is what de-risks WK68's byte-reproducible render/screenshot captures.

WHY A SUBPROCESS HERE TOO
-------------------------
Like the WK67 keystone, this pin is computed in a fresh interpreter with the env
pinned to the digest seed. ``config.SIM_SEED`` is read from the env at import and
``SimEngine`` re-applies it during construction, so any suite module that mutates
the shared process env (historically ``tests/perf_*stress*.py`` set
``SIM_SEED=42`` at import — fixed in R0) could otherwise shift the digest by
collection order. Pinning the env in a subprocess makes this pin order-independent.
The two builds happen IN THAT ONE SUBPROCESS, so it is a genuine in-process test of
the production reset (the subprocess is just the controlled, clean process).

Crucially, the two builds rely ONLY on the production ``_reset_global_sim_state``
(no test-side ``_AI_RNG.seed`` / ``RESEARCH_UNLOCKS`` reset) — unlike the WK67
``_build_digest_engine`` helper, which does those resets in the test. That is the
whole point: this pin fails if production does not self-reset.
"""

from __future__ import annotations

import os
import subprocess
import sys

# The golden WK67 AI-decision digest. MUST stay byte-identical (the WK68 R0
# per-build reset is a no-op on the first build in a fresh process, and the
# `_AI_RNG` reseed mirrors the WK67 reference recipe `.seed(SIM_SEED)`).
_AI_DECISION_DIGEST = "b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded"
_AI_DIGEST_SEED = 3
_D1_MARKER = "WK68_RESET_D1="
_D2_MARKER = "WK68_RESET_D2="

# Inline driver run in the fresh subprocess: builds two GameEngines back-to-back
# in ONE process and prints both 300-tick AI digests. It reuses the WK67 scenario
# helpers (`_seed_digest_heroes`, `_ai_digest`) but does NOT reuse the test-side
# resets in `_build_digest_engine` — determinism must come from production alone.
_SUBPROCESS_DRIVER = f"""
import tests.test_wk67_ai_boundary as t
from game.engine import GameEngine
from ai.basic_ai import BasicAI


def _build_and_digest():
    # GameEngine.__init__ -> SimEngine.__init__ -> _reset_global_sim_state():
    # this is the production per-build reset under test (reseeds _AI_RNG,
    # clears RESEARCH_UNLOCKS, zeroes the entity counters). No test-side reset.
    engine = GameEngine(headless=True)
    engine.ai_controller = BasicAI(llm_brain=None)  # aliases the reseeded _AI_RNG
    t._seed_digest_heroes(engine)
    try:
        return t._ai_digest(engine, t._AI_DIGEST_TICKS)
    finally:
        import pygame
        pygame.quit()


d1 = _build_and_digest()
d2 = _build_and_digest()
print("{_D1_MARKER}" + d1)
print("{_D2_MARKER}" + d2)
"""


def _two_build_digests_in_subprocess() -> tuple[str, str]:
    """Run two in-process GameEngine builds in a fresh, env-pinned interpreter.

    Returns ``(digest_build_1, digest_build_2)``. Mirrors the WK67 keystone's
    subprocess pattern (pinned ``SIM_SEED`` + ``DETERMINISTIC_SIM=1``) so the pin
    is independent of suite/collection order.
    """
    env = dict(os.environ)
    env["DETERMINISTIC_SIM"] = "1"
    env["SIM_SEED"] = str(_AI_DIGEST_SEED)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_DRIVER],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        cwd=repo_root,
    )
    d1 = d2 = None
    for line in proc.stdout.splitlines():
        if line.startswith(_D1_MARKER):
            d1 = line[len(_D1_MARKER):].strip()
        elif line.startswith(_D2_MARKER):
            d2 = line[len(_D2_MARKER):].strip()
    if d1 is None or d2 is None:
        raise AssertionError(
            "subprocess did not print both WK68 reset digests.\n"
            f"returncode={proc.returncode}\nstdout(tail)={proc.stdout[-2000:]}\n"
            f"stderr(tail)={proc.stderr[-2000:]}"
        )
    return d1, d2


def test_per_build_reset_makes_in_process_builds_deterministic():
    """Two same-seed GameEngine builds in ONE process produce equal AI digests.

    Relies ONLY on the production ``SimEngine._reset_global_sim_state``. If the
    per-build reset regresses (e.g. ``_AI_RNG`` stops being reseeded), the second
    build's AI stream drifts and the two digests diverge — failing this test.
    """
    d1, d2 = _two_build_digests_in_subprocess()
    assert d1 == d2, (
        "Two in-process same-seed GameEngine builds produced DIFFERENT AI digests "
        "— the per-build determinism reset (SimEngine._reset_global_sim_state) "
        f"regressed. build1={d1} build2={d2}"
    )


def test_per_build_reset_preserves_wk67_digest():
    """The in-process build digest equals the WK67 keystone golden (digest unchanged).

    Tier-2 guardrail: the per-build reset (incl. the ``_AI_RNG`` reseed) is
    digest-preserving. The production reset mirrors the WK67 reference recipe
    ``_AI_RNG.seed(SIM_SEED)``, so the keystone value ``b73961…`` is byte-identical.
    """
    d1, d2 = _two_build_digests_in_subprocess()
    assert d1 == _AI_DECISION_DIGEST, (
        "In-process build digest diverged from the WK67 keystone golden — the "
        "per-build reset moved AI behavior. "
        f"got={d1} golden={_AI_DECISION_DIGEST}"
    )
    assert d2 == _AI_DECISION_DIGEST, (
        "Second in-process build digest diverged from the WK67 keystone golden. "
        f"got={d2} golden={_AI_DECISION_DIGEST}"
    )
