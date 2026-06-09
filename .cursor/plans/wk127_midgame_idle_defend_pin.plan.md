# WK127 — Rangers/wizards (then everyone) freeze near their guild after ~15 min of play

**Sprint owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-09
**Owner agent:** Agent 06 (AIBehaviorDirector) — task-router defense gating + idle-shopping loop. **Consult:** Agent 03 (router contract), Agent 11 (regression tests in the same dispatch).
**Version target:** patch (gameplay stability bugfix — no version bump unless Jaimie asks)

> **OUTCOME (2026-06-09): FIXED & VERIFIED, pending Jaimie live confirm + commit.** T1 (threat-gate the
> home/castle defend hijack), T2 (zero-purchase shopping cooldown + predicate alignment), and the r2
> follow-ups (same-disease rest fix in `hero_rest.py` 3×`is_damaged`→`is_under_attack`, castle + rest
> regression tests, review nits) all landed. Full suite **1543 passed / 5 skipped / 0 failed**; WK67 digest
> byte-identical; qa_smoke + determinism guard PASS. 35-sim-min realistic soak: **REPRODUCED_CLASSES=NONE**
> (pre-fix: rangers/wizards idle 0.94–1.00 at 0 px/min from min ~19; post-fix: idle 0.22–0.42 at
> 147–328 px/min). Every regression test proven to fail on its pre-fix condition via flip-and-restore.
> Uncommitted pending go-ahead. Details: PM hub `wk127_midgame_idle_defend_pin` rounds r1+r2.

---

## Symptom (Sovereign playtest — previously misdiagnosed)

Heroes — **particularly rangers and wizards** — go idle and hang out **near their guild hall** after
~15 minutes of gameplay; develops at 10–20 min and **worsens over time**. Not visible in a single
screenshot; requires observing movement across minutes. WK125 (wall-clock timebase) was declared the fix
and was NOT — that bug was real but orthogonal (pause/uptime), and the live symptom persists during
active play on the WK125 tree.

## Root cause (CONFIRMED empirically — 35-sim-min realistic headless soak, branch instrumentation)

**Primary — the damaged-home-building permanent hijack.**
`ai/task_router.py:79-81`: if `hero.home_building.is_damaged` (= `hp < max_hp`,
`game/entities/buildings/base.py:259-261` — ANY missing HP, forever) the router calls
`defend_home_building` and **returns every tick**, before hunger, rest, the idle pipeline, and the WK124
ranger roam are ever reached. With no enemy within 5 tiles of the building,
`ai/behaviors/defense.py:121-126` walks the hero to within 2 tiles of the guild and sets `IDLE` —
a permanent statue. Peasant repairs stall under swarm pressure (measured: ranger guild frozen at 192/200
from sim-min 2, wizard guild at 140/200 from min 6, for 19+ minutes), so the pin never releases.
The castle branch (`task_router.py:60`) has the same flaw: a chipped castle hijacks ALL heroes
(park-at-castle when no enemies, or cross-map chase of the enemy nearest the castle).
Note the irony: `Building.is_under_attack` (`base.py:264-268`) is a 3-second recently-damaged window whose
docstring says it exists to "prevent permanent 'defend forever'" — the router just doesn't use it for
home/castle, it uses `is_damaged`.

Soak evidence (`tmp/wk127_drill2_stdout.log`, `tmp/wk127_soak_stdout_35min.log`): rangers pin from min 3,
wizards from min 7 (each ~1 min after their guild first takes damage); by min 21-35 rangers+wizards are
IDLE 480/480 samples at 0px/min, 0.7–1.9 tiles from the guild; Ranger0 cumulative `defend_home` 24,699
calls vs `handle_idle` 3. Warriors pin the same way later; clerics resist longest (their support branch
runs before the home-damaged branch) but degrade too. Knock-on: pinned heroes can't eat or rest (those
checks are below the defend branch) — wizard observed parked at 32/160 HP.

Why every prior gate missed it: `tests/test_wk124_ranger_idle_soak.py` neutralizes the spawner/lairs and
clears enemies each tick → buildings never take damage → the branch never arms. (It also zeroes hero
gold, which masks the secondary cause below.)

**Secondary — the zero-purchase shopping loop (static analysis, to be confirmed by the post-fix soak).**
Once a full-HP hero has ≥50 gold, 2 potions, and max marketplace gear, the "want" predicates and the buy
rules are mutually unsatisfiable: `wants_to_shop` fires at `potions < 5` (`game/entities/hero_economy.py:170`)
and the no-LLM fallback at `potions < 3` (`ai/prompt_templates.py:85-88`), but `do_shopping` only buys at
`potions < 2` (`ai/behaviors/shopping.py:108-113`) and only strict gear upgrades (`:115-131`);
`_idle_shopping` (`ai/behaviors/exploration.py:359-383`) also has a naked `gold >= 50` blacksmith branch
with no purchasable-upgrade check and no cooldown. Zero-purchase trips end `finalize_deferred_task → IDLE`
(`ai/behaviors/recovery.py:71`), the idle pipeline re-fires shopping (step 4, BEFORE engage/POI/explore at
5-8), and the hero orbits the marketplace forever. Rangers/wizards are hit hardest because they kill at
range and stay full-HP (the `_idle_shopping` gate). Post-shopping journeys can't rescue: they require a
purchase (`ai/behaviors/journey.py:19`) and are clobbered to IDLE by `finalize_deferred_task` anyway.

**Explicitly ruled out:** WK125 timebase as cause (no sim/AI code mixes `now_ms()` with `get_ticks()`
stamps; FAST multiplier pre-scales dt once in `lifecycle.py:141`); wizard kiting stranding (no hero kite
code exists); whole-map fog exhaustion at 15 min (needs hours); commit-window far-future stamps (all
writers add fixed 1.5–8 s).

---

## Tickets

### WK127-T1 — Threat-gate the home/castle defend hijack (owner: Agent 06)
Files: `ai/task_router.py`, `ai/behaviors/defense.py`.
- Add a small helper in `defense.py`, e.g. `building_threatened(view, building, radius_tiles) -> bool`:
  True iff `building.is_under_attack` (the existing 3 s recently-damaged window) OR a live enemy is within
  `radius_tiles` of the building's center. Deterministic, read-only.
- `task_router.py:79-81` (home building): replace the `is_damaged` trigger with
  `building_threatened(view, hero.home_building, 5)` (5 tiles = the radius `defend_home_building` already
  uses to pick its target). No threat → fall through to the normal pipeline (hunger/rest/idle/explore).
- `task_router.py:60` (castle): replace `castle.is_damaged or is_under_attack` with
  `castle.is_under_attack or building_threatened(view, castle, 6)`. (The line-36 urgent branch already
  handles the under-attack case; keep it.) A merely-chipped castle with no enemies near must NOT hijack.
- Keep `defend_castle`/`defend_home_building` bodies functionally intact — when the gate passes, heroes
  must still engage exactly as today (rally, fight, park briefly while the 3 s window is hot). When the
  threat clears, the gate stops firing and heroes resume normal life even if the building is still damaged.
- **DIGEST SAFETY:** the WK67 digest scenario (300 ticks, warrior+ranger+cleric, NO enemies, castle and
  no home guilds damaged) never enters these branches → byte-identical digest. Run the gate to prove it.

### WK127-T2 — Break the zero-purchase shopping loop (owner: Agent 06)
Files: `ai/behaviors/shopping.py`, `ai/behaviors/exploration.py` (`_idle_shopping`),
`ai/prompt_templates.py`, `ai/decision_moments.py`, `game/entities/hero_economy.py` (`wants_to_shop`).
- **Backstop (the load-bearing part):** when a completed shopping trip purchases nothing, stamp a per-hero
  zero-purchase cooldown (e.g. `hero._shop_cooldown_until_ms = sim_now_ms() + 60_000`, sim-time) and make
  `_idle_shopping` + `moment_shopping_opportunity` + the fallback `buy_item` path respect it. Use
  `game.sim.timebase.now_ms` only.
- **Predicate alignment:** `wants_to_shop` potion clause `< 5` → `< 2` (match the buy rule); fallback
  `potions < 3` → `< 2`; `_idle_shopping`'s blacksmith branch must require an actual affordable upgrade
  (or at minimum respect the cooldown above).
- **DIGEST SAFETY:** digest heroes start with 0 potions (both `<5` and `<2` true → same decisions) and the
  cooldown only changes behavior after a zero-purchase trip, which does not occur in 300 ticks. Verify with
  the digest gate; if it shifts, prefer the cooldown-only variant and report.

### WK127-T3 — Regression tests, fail-pre-fix (owner: Agent 06, same dispatch)
New `tests/test_wk127_midgame_idle.py` (headless, dummy SDL, DETERMINISTIC_SIM=1, **seed via `SIM_SEED`
env — `set_sim_seed()` is re-seeded by `SimEngine.__init__`, see soak side-finding**):
1. **Damaged-guild no-pin:** constructed guild + 2-3 heroes (ranger/wizard), chip the guild
   (`hp -= 20`), NO enemies; run ~2-3 sim-min. Pre-fix: heroes pinned IDLE within ~3 tiles of guild
   nearly 100% of late samples. Post-fix assert: idle-near-guild fraction low + heroes travel.
2. **Defense still works:** same setup + a live enemy placed within 4 tiles of the damaged guild →
   heroes must engage it (target/FIGHTING within a few sim-seconds), proving T1 didn't neuter defense.
3. **Zero-purchase cooldown:** hero with 500 gold, 2 potions, best gear, beside the marketplace; run a
   shopping trip; assert no immediate shopping re-fire for the cooldown window (pre-fix: re-fires).

### WK127-T4 — Verification (owner: Agent 01 PM)
- Re-run `tmp/wk127_realistic_soak.py` (35 sim-min, mixed party, spawner+lairs LIVE): the late-window
  (min 15-35) idle-fraction for rangers+wizards must stay far below the pre-fix 0.94-1.00 plateau and
  displacement must stay healthy; no permanent statue heroes.
- Full gates (below). PM hub updated; Jaimie live-confirm prompt provided.

## Gates (from repo root — all must pass)
```
python -m pytest tests/test_wk67_ai_boundary.py -q      # digest byte-identical — DO NOT re-baseline
python -m pytest tests/test_wk127_midgame_idle.py -q    # new regression (fails pre-fix)
python -m pytest tests/test_wk124_ranger_idle_soak.py -q
python -m pytest tests/test_wk125_walltime_freeze.py -q
python -m pytest tests/ -q                              # full suite green
python tools/qa_smoke.py --quick
python tools/determinism_guard.py
```

## Out of scope / follow-ups (do NOT do in this sprint)
- Peasant repair throughput under swarm (guilds staying damaged for 20+ min is its own economy bug —
  the T1 gate makes it non-paralyzing; file for a future sprint).
- Wizards having no real exploration behavior (fixed patrol zone 6-10 tiles, assigned once,
  `ai/behaviors/zones.py:23-27`) — acceptable Majesty flavor for now; revisit if Jaimie still sees
  wizards as boring after T1/T2.
- MAX_ALIVE_ENEMIES=80 cap dynamics, unreachable water-locked frontier targets (H4), hunger cadence (H5).

## Definition of Done
- All gates green, WK67 digest byte-identical, new regression fails on pre-fix code and passes post-fix.
- 35-sim-min realistic soak shows no idle plateau for rangers/wizards.
- PM hub + this plan updated with evidence. NOTHING COMMITTED (Jaimie decides; concurrent-session check
  + stage-by-path rules apply).
