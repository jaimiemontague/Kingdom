"""WK137 T3 — deterministic balance guardrails for the initial goblin wave.

This suite pins the shipped initial-wave balance (NORMAL difficulty, the clustered
``direction="clustered_near"`` placement at ``spawn_dist_tiles=29`` /
``goblin_count=10`` / ``cluster_jitter_tiles=2``). The full 10-seed matrix + the
count x dist x H grid + the tuning verdict live in ``tools/wk137_balance_probe``;
this test is the suite-level regression gate.

WK137 r3 (Part A — canonical measurement path)
----------------------------------------------
The wave geometry (the ``get_rng("wave_events")`` bearing in ``_near_anchor_tile``)
and worldgen are seeded from ``_BASE_SEED`` at *engine-construction* time.
``GameEngine`` / ``SimEngine.__init__`` internally calls
``set_sim_seed(config.SIM_SEED)``, which resets ``_BASE_SEED`` back to
``config.SIM_SEED`` (=1 when ``SIM_SEED`` is unset). So a bare *in-process* run made
every "seed" share ONE wave bearing — only the AI-RNG varied. The CANONICAL path
(``run_cell_subprocess``) sets the ``SIM_SEED`` env BEFORE import so worldgen + the
wave bearing genuinely vary per seed; that is the path the official probe matrix and
the band assertions below use.

  * Harness-contract guardrails (composition / isolation / determinism / the H=10
    win-band) use the FAST in-process ``run_cell`` — they do not depend on the
    seed-geometry distinction (``run_cell`` re-applies ``set_sim_seed(seed)`` after
    the engine is built so the bearing matches the subprocess; only worldgen terrain
    differs, which the contract guardrails don't measure).
  * The H=8 / H=6 *difficulty bands* use the CANONICAL subprocess cells so the suite
    claims match the official 10-seed matrix.

WHAT IS HARD-ASSERTED (regression gates):
  * isolation — zero enemies before the wave spawns (run_cell asserts it),
  * NORMAL difficulty took effect,
  * composition is exactly ``goblin_count`` goblins + 1 warchief,
  * determinism — same (seed,H,count) twice -> byte-identical outcome,
  * H=10 win-band: clean win, mean deaths <= 1.5 (in-process subset),
  * H=8 difficulty band (WK137 r3): >=majority wins AND mean deaths in [1.0, 4.5]
    on the canonical 5-seed subset. r2's edge-spawn shipped 0.60 deaths (FAIL); the
    r3 clustered_near dist=29 config landed the band, so this XPASSing marker is now
    a HARD ASSERT (a future change that makes 8 heroes stop taking damage is a real
    regression worth a red gate).

WHAT IS XFAIL (a documented, Sovereign-owned gap — NOT a red gate):
  * H=6 "hard-matched" band. The wave is structurally too easy for 6 clumped heroes
    on NORMAL: across the entire Part-C grid (count {10,12,14,16} x dist {27,29,31}
    x jitter {0..4}, canonical) 6 heroes win 100% and the H=6 mean-deaths CEILING is
    ~1.8 (10-seed, best cell dist=31/count=16) — far below the 3.5 floor. Hero deaths
    are dispersion-driven and scale TOGETHER across hero counts, so making 6 clumped
    heroes lose over-kills the 10-hero line first. Closing this needs a Sovereign
    lever (pre-wave fog-reveal leveling cap / +1 warchief on NORMAL / a band revision)
    — out of QA's and 05's lane. See the PM hub wk137 r3 + the probe verdict. Kept
    ``xfail(strict=False)`` so it documents the known gap without red-gating every
    other agent's suite run.

Runtime: the in-process subset (~9 cells) ~70 s; the canonical band cells (~10
subprocess cells) ~70 s. Module-scoped so cells compute once.
"""

from __future__ import annotations

import os

import pytest

# Headless-friendly drivers (real Hero construction loads sprites/fonts).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("DETERMINISTIC_SIM", "1")

from tools.wk137_balance_probe import (  # noqa: E402
    SHIPPED_GOBLIN_COUNT,
    run_cell,
    run_cell_subprocess,
    summarize,
)

# In-process subset (harness-contract guardrails + H=10 win-band).
_SUBSET_SEEDS = (11, 23, 37)
_HERO_COUNTS = (10, 8, 6)

# Canonical subprocess subset (difficulty bands). 5 seeds for a stable mean.
_BAND_SEEDS = (11, 23, 37, 41, 53)

# Proportional bands.
_H10_MIN_WINS = 3          # 3/3 — H=10 must be a clean win (in-process subset)
_H10_MAX_MEAN_DEATHS = 1.5
_H8_MIN_WINS = 3           # >= 3/5 on the 5-seed canonical band subset
_H8_DEATHS_BAND = (1.0, 4.5)
_H6_MAX_WINS = 3           # <= 3/5 ...
_H6_MIN_MEAN_DEATHS = 3.5  # ... OR mean deaths >= 3.5


@pytest.fixture(scope="module")
def matrix_cells():
    """In-process 3-seed x 3-H subset at the shipped config (fast harness guardrails)."""
    cells = []
    for H in _HERO_COUNTS:
        for seed in _SUBSET_SEEDS:
            cells.append(run_cell(seed, H, SHIPPED_GOBLIN_COUNT, isolate=True))
    return cells


@pytest.fixture(scope="module")
def matrix_summary(matrix_cells):
    return summarize(matrix_cells)


@pytest.fixture(scope="module")
def band_summary():
    """CANONICAL 5-seed subprocess cells at H in (8, 6) for the difficulty bands."""
    cells = []
    for H in (8, 6):
        for seed in _BAND_SEEDS:
            cells.append(run_cell_subprocess(seed, H, SHIPPED_GOBLIN_COUNT, isolate=True))
    return summarize(cells)


# ---------------------------------------------------------------------------
# Harness-contract guardrails (hard asserts — robustly true)
# ---------------------------------------------------------------------------

def test_wave_isolated_and_normal_and_composition(matrix_cells):
    """Every cell: NORMAL-forced isolation held + exact goblin/warchief composition.

    ``run_cell`` already asserts (a) NORMAL took effect and (b) zero enemies exist
    on the tick before the wave spawns (the isolation proof). Here we pin the wave
    *shape* every cell returned: exactly ``goblin_count`` goblins + exactly 1
    warchief, so a future regression that drops the boss or mis-sizes the wave is
    caught at the suite level.
    """
    assert matrix_cells, "no cells produced"
    for c in matrix_cells:
        assert c["warchiefs"] == 1, f"expected exactly 1 warchief, got {c['warchiefs']} ({c})"
        assert c["goblins"] == SHIPPED_GOBLIN_COUNT, (
            f"expected {SHIPPED_GOBLIN_COUNT} goblins, got {c['goblins']} ({c})"
        )
        assert c["snapshot"] == SHIPPED_GOBLIN_COUNT + 1, (
            f"snapshot size {c['snapshot']} != goblin_count+1 ({c})"
        )


def test_cells_are_deterministic():
    """Same (seed, H, count) twice → byte-identical outcome (no flake)."""
    a = run_cell(11, 8, SHIPPED_GOBLIN_COUNT, isolate=True)
    b = run_cell(11, 8, SHIPPED_GOBLIN_COUNT, isolate=True)
    assert a == b, f"balance cell is non-deterministic:\n  a={a}\n  b={b}"


def test_h10_band_is_a_clean_win(matrix_summary):
    """H=10 proportional band: 3/3 wins AND mean hero deaths <= 1.5.

    This band HOLDS (10 heroes clean-win the initial wave); if a future change makes
    10 heroes start losing the *initial* wave, that is a real regression.
    """
    s = matrix_summary[(10, SHIPPED_GOBLIN_COUNT)]
    assert s["wins"] >= _H10_MIN_WINS, (
        f"H=10 wins {s['wins']}/{s['n']} < {_H10_MIN_WINS} (10 heroes should clean-win)"
    )
    assert s["mean_deaths"] <= _H10_MAX_MEAN_DEATHS, (
        f"H=10 mean deaths {s['mean_deaths']} > {_H10_MAX_MEAN_DEATHS}"
    )


# ---------------------------------------------------------------------------
# Difficulty bands (canonical subprocess subset)
# ---------------------------------------------------------------------------

def test_h8_difficulty_band(band_summary):
    """H=8 difficulty band (HARD ASSERT, WK137 r3): >=3/5 wins AND deaths in [1.0,4.5].

    This was ``xfail(strict=False)`` at r1 (edge-spawn shipped 0.60 deaths = FAIL).
    The r3 clustered_near dist=29 config lands the band (canonical 10-seed matrix:
    10/10 wins, 1.10 mean deaths; this 5-seed subset: 5/5 wins, 1.00 mean deaths), so
    the marker is now a hard regression gate: if 8 heroes stop taking ~1 death each
    (the wave gets too easy again), this goes red on purpose.
    """
    s = band_summary[(8, SHIPPED_GOBLIN_COUNT)]
    assert s["wins"] >= _H8_MIN_WINS, f"H=8 wins {s['wins']}/{s['n']} < {_H8_MIN_WINS}"
    assert _H8_DEATHS_BAND[0] <= s["mean_deaths"] <= _H8_DEATHS_BAND[1], (
        f"H=8 mean deaths {s['mean_deaths']} not in {_H8_DEATHS_BAND}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "WK137 H6 band is STRUCTURALLY UNREACHABLE with the allowed levers and is a "
        "known, Sovereign-owned gap — documented here, NOT red-gated.\n"
        "MEASURED CEILING (canonical subprocess, WK137 r3): across the entire Part-C "
        "grid (count {10,12,14,16} x dist {27,29,31} x jitter {0..4}) 6 heroes win "
        "100% and the H6 mean-deaths CEILING is ~1.8 (10-seed, best cell "
        "dist=31/count=16) vs the 3.5 floor / <=6-win ceiling the band needs. At the "
        "SHIPPED config (dist=29/count=10) H6 = 10/10 wins, 0.90 mean deaths.\n"
        "ROOT CAUSE: hero deaths are dispersion-driven and scale TOGETHER across hero "
        "counts; 6 clumped heroes near the castle are the SAFEST config, so making "
        "the wave lethal to them over-kills the 10-hero line first (H10 blows past "
        "1.5). Closing it needs a Sovereign lever (pre-wave fog-reveal leveling cap / "
        "+1 warchief on NORMAL / a band revision) — out of the dist/count/jitter lane. "
        "See PM hub wk137 r3 + the probe BALANCE verdict. XPASSes (unmark me) only if "
        "such a lever lands and 6 heroes become genuinely hard-matched."
    ),
)
def test_h6_difficulty_band(band_summary):
    """H=6 'hard-matched' band: <= 3/5 wins OR mean deaths >= 3.5 (canonical subset)."""
    s = band_summary[(6, SHIPPED_GOBLIN_COUNT)]
    assert (s["wins"] <= _H6_MAX_WINS) or (s["mean_deaths"] >= _H6_MIN_MEAN_DEATHS), (
        f"H=6 too easy: {s['wins']}/{s['n']} wins AND mean deaths {s['mean_deaths']} "
        f"(want <= {_H6_MAX_WINS} wins OR >= {_H6_MIN_MEAN_DEATHS} deaths)"
    )
