# WK125 — Heroes freeze after long app uptime / pause (wall-clock timebase bug)

**Sprint owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-03
**Owner agent:** Agent 10 (PerformanceStability_Lead) — timebase/pause/dt stability, same class as WK123. **Consult:** Agent 03 (sim contract).
**Version target:** patch (stability bugfix — no version bump unless Jaimie asks)

> **OUTCOME (2026-06-03): FIXED & VERIFIED, pending Jaimie live confirm + commit.** `now_ms()` is now a
> pause-frozen monotonic sim clock in all modes. Regression test fails pre-fix (`now_after_jump=3,601,383`)
> / passes post-fix (`527`, 6/6 heroes move). Full suite **1538 passed / 5 skipped / 0 failed**; WK67 digest
> byte-identical; determinism guard clean; WK124 ranger soak green. Uncommitted pending go-ahead.

---

## Symptom (Sovereign playtest)
After the game has been **open a long time (~1 hr), ALL heroes** (every class) end up stuck mostly idle /
standing still. Reproduced by leaving the game **PAUSED for an hour** then hitting play → basically all
heroes stand still. Also develops during long **playing** sessions. The unifying variable is **real
wall-clock time since the app launched — it does not matter whether that time was paused or playing.**
This is NOT the WK124 ranger fog bug (sim-progression based, fixed); this is broader and time-of-uptime
based, and triggers with **zero sim progression** (paused).

## Root cause (confirmed: 5-scout investigation + empirical headless repro + 2 adversarial reviews)
In shipped/real play, `config.py:123` defaults `DETERMINISTIC_SIM = 0`. In that mode
`SimEngine.update()` (`game/sim_engine.py:689-694`) calls `set_sim_now_ms(None)` **every tick**, which makes
the AI clock `now_ms()` fall back to **`pygame.time.get_ticks()`** — a real wall clock
(`game/sim/timebase.py:40-44`).

- That wall clock **advances while paused** (the Ursina/pygame render loop keeps running) and **grows
  unbounded with app uptime**, while `SimEngine.update()` — the only `set_sim_now_ms` caller — is **skipped
  while paused** (`game/engine_facades/lifecycle.py:57-61` returns False at multiplier 0 / paused).
- Every hero AI timestamp is stamped against this same clock but only refreshed on a sim tick:
  `last_progress_ms`, `next_meal_due_ms` (`game/entities/hero.py:192,202`), bounty `started_ms`, and all
  `*_commit_until_ms` windows.
- After long real uptime (paused OR played), `now_ms()` is huge while stored stamps are stale, so **every
  "staleness" gate trips at once for ALL heroes**: stuck-recovery flags `now_ms - last_progress_ms >=
  STUCK_TIME` (`ai/behaviors/stuck_recovery.py:62`), `hunger_urgent` is permanently True
  (`hero.py:395-397`), bounty pursuit times out instantly (`ai/behaviors/movement.py:87-95`), and
  anti-oscillation commit windows read expired. Net: heroes churn / stand still.

**Empirical proof (full headless GameEngine, +1 hr `get_ticks` jump):** with `DETERMINISTIC_SIM=0` the jump
leaks into `now_ms()` (→ ~3,600,000) and hero activity collapses; with `DETERMINISTIC_SIM=1` the **same
jump is harmless** (`now_ms()` stays sim-time ~17 ms) and all heroes move vigorously. **The only variable is
which clock backs `now_ms()`.** Tests never caught this because the WK67 digest + all unit tests pin
`DETERMINISTIC_SIM=1`.

### Adversarial nuance (honored)
One reviewer showed parts of the *terminal* latch self-heal in **open terrain** (a hero that displaces
≥8 px re-anchors `last_progress_ms`; eating re-anchors hunger), so the wall-clock bug can present as
*transient* degradation there. But the **fix eliminates the wall-clock-vs-stale-stamp divergence at its
source**, so it is correct and necessary regardless of how far the symptom escalates in any given terrain
(in a crowded town, heroes that can't displace ≥8 px/tick never self-heal and churn — exactly the reported
permanent freeze). Both reviewers + the synthesis agree the fix below is **correct, safe, and
digest-neutral**.

---

## The fix (Agent 10)

### Ticket WK125-T1 — make `now_ms()` a pause-frozen monotonic sim clock in ALL modes
File: `game/sim_engine.py`, `SimEngine.update()` lines 689-694. Replace the `if DETERMINISTIC_SIM … else
set_sim_now_ms(None)` with **always** advancing + publishing the accumulator:
```python
# Sim-time accounting: ALWAYS drive a monotonic, pause-frozen sim clock so now_ms()
# never falls back to the real wall clock (pygame.time.get_ticks()). update() is the
# ONLY set_sim_now_ms caller and is skipped while paused (lifecycle returns False),
# so this clock freezes on pause and never jumps on resume / with app uptime.
# DETERMINISTIC_SIM now governs ONLY RNG/order determinism, not the clock — DET=1
# already used exactly this accumulator, so the WK67 digest stays byte-identical.
self._sim_now_ms += int(round(float(dt) * 1000.0))
set_sim_now_ms(self._sim_now_ms)
```
- Update the stale WK123-C2 comment near `game/sim_engine.py:838-844` ("`_sim_now_ms` stays 0" / diverges)
  and let any dead-hero TTL there read `self._sim_now_ms` consistently.

### Ticket WK125-T2 — publish the clock at construction (gap #1)
Heroes/buildings constructed BEFORE the first `update()` stamp timestamps from `now_ms()`. Ensure
`self._sim_now_ms` is initialized (it already is for DET=1 — confirm `__init__` sets it, e.g. `= 0`) and
**call `set_sim_now_ms(self._sim_now_ms)` at the end of `SimEngine.__init__`** so the very first stamps come
from sim-time (0), not the wall clock. (Avoids a harmless-but-untidy negative stuck-delta / delayed first
meal on the first tick.)

### Ticket WK125-T3 — audit non-sim `now_ms()` callers (gap #2)
With the clock now frozen while paused, HUD/cosmetic timers that call `timebase.now_ms()` (e.g. bounty hint,
recall flash, memorial/toast dismiss, some audio timing) will **freeze during pause** instead of advancing.
Audit every non-sim caller of `now_ms()`:
- If it uses `now_ms()` only as a **delta vs another `now_ms()` stamp** → safe (deltas are consistent), and
  freezing during pause is acceptable/expected (pause should freeze UI timers). Leave it; just note it.
- If any caller genuinely needs **real wall-clock that advances while paused** (most likely none; possibly
  an audio crossfade) → switch that specific call site to `pygame.time.get_ticks()` directly (as
  `game/engine.py:726` conversation cooldown already does).
Update the `game/sim/timebase.py` module docstring + `now_ms()`/`set_sim_now_ms()` docstrings to state that
`now_ms()` is the **pause-frozen sim clock in all modes** and UI wanting real wall time must call
`pygame.time.get_ticks()` directly.

### Ticket WK125-T4 — deterministic regression test (fails pre-fix, passes post-fix)
New `tests/test_wk125_walltime_freeze.py`, headless (no GPU), fast (~10 s). It must exercise the **non-
deterministic (shipped) path** — do this by monkeypatching `game.sim_engine.DETERMINISTIC_SIM = False`
(the flag is imported at module load, so setting `os.environ` after import won't take; patch the module
attr). Then:
1. Build a headless `GameEngine(headless=True)` with `BasicAI(llm_brain=None)`, dummy SDL drivers,
   `set_sim_seed(1)`. Neutralize spawner/lair. Spawn ~6 heroes.
2. Run a few `engine.update(dt)` ticks (warm up), record hero positions.
3. **Inject the time condition:** `orig = pygame.time.get_ticks; monkeypatch pygame.time.get_ticks ->
   lambda: orig() + 3_600_000` (== sat paused 1 hr; no sim ticks elapsed).
4. Run one `engine.update(dt)`.
5. **Load-bearing assertion:** `timebase.now_ms()` is **sim-time, NOT the wall-clock jump** — e.g.
   `assert timebase.now_ms() < 60_000` (pre-fix returns ~3,600,000 → FAILS; post-fix stays small → PASSES).
6. Secondary: run ~8 sim-seconds after the jump and assert heroes still **decide + move** (net displacement
   > 50 px for most; not all-IDLE-with-null-target).
- Keep `DETERMINISTIC_SIM=1` paths (WK67 digest, WK124 soak) untouched and green.

---

## Gates (Agent 10, from repo root — all must pass)
```
python tools/qa_smoke.py --quick
python -m pytest tests/test_wk67_ai_boundary.py -q                 # digest MUST stay byte-identical (DET=1 path)
python -m pytest tests/test_wk124_ranger_idle_soak.py -q           # ranger fix still holds
python -m pytest tests/test_wk125_walltime_freeze.py -q            # new regression
python -m pytest tests/ -q                                         # full suite green
python tools/determinism_guard.py
```
Do NOT edit `_AI_DECISION_DIGEST`. If the digest changes, STOP and report — but it should not (DET=1 already
used the accumulator clock).

## PM verification (Agent 01)
- Re-run the full sweep on the combined tree.
- Confirm the new test FAILS on the pre-fix code and PASSES post-fix (proves it's a real regression guard).
- Live: ask Jaimie to re-test the exact repro (`python main.py`, pause ~a few min or 1 hr, hit play → heroes
  should resume moving normally). The deterministic test is the authoritative gate; the live test is the
  human confirmation.

## Definition of Done
- `now_ms()` is a pause-frozen monotonic sim clock in all modes; never falls back to `get_ticks()` from
  `update()`.
- New regression test fails pre-fix, passes post-fix; full suite green; WK67 digest byte-identical;
  determinism guard clean; WK124 ranger soak still green.
- Non-sim `now_ms()` callers audited (cosmetic-freeze-on-pause accepted or converted to `get_ticks()`).
- PM hub + plan updated; Jaimie shown the result and asked to confirm via the live pause/resume repro.

## Honest residual note (for Jaimie)
This is the confirmed wall-clock-correlated root cause and the fix is verified correct + safe. If — after
this lands — heroes STILL freeze under the exact live repro, there may be a residual geometric/deadlock
vector (a hero that cannot displace enough to self-heal); we'd chase that next with per-hero live logging.
But the timebase fix removes the divergence that makes every hero trip its staleness gates at once, which is
the mechanism matching all three clues (paused-counts, all-heroes, ~1 hr onset).
