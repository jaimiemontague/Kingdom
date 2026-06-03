# WK123 — FPS Time-Degradation Hunt (FPS worsens after 10+ min + 70+ enemies)

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution (autonomous, Sovereign-approved multi-day loop)
**Branch:** `wk123-fps-degradation` (all experiments isolated here; winning fix → main)
**Version target:** patch (perf/stability — no version bump unless Jaimie asks)
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. The bug (Sovereign report)

> "FPS has been greatly improved in the early game, but it still gets much worse once there
> are over 70 enemies on the map (I ultimately want hundreds) and the game has been running
> for 10+ minutes. Could be the number of enemies but I suspect it's more likely some kind
> of **memory leak or similar bug where a design flaw causes FPS to get worse with time.**"

### Why this is a NEW, untested failure mode
The prior FPS work (`perf/fps-floor-recovery`, now on main — see
`.cursor/rules/11-fps-performance-guardrails.mdc`) root-caused and fixed **steady-state,
load-driven** per-frame cost, and validated it with **~2-minute** runs ("min < 20 dips are
rare ~1 frame per 2-min run"). **A 2-minute probe structurally cannot observe a 10–15 minute
degradation.** So a slow accumulation/leak that only bites after many minutes was never
tested for. That is exactly what this sprint hunts: **what grows with time/ticks and is never
bounded** (sim collections, ursina scene-graph nodes, per-frame cost scaling with all-time
state, GC pressure).

---

## 1. Acceptance bar (DEFINITIVE — from the Sovereign directive)

A candidate fix PASSES only when a live soak shows, **reliably across repeats**:

- **Scenario:** ≥20 heroes, ≥20 buildings, **≥75 enemies** on the map simultaneously.
- **Duration:** the game runs a real **15+ minutes**, then FPS is logged **every 15 s between
  minute 15 and minute 17** (a 2-minute confirmation window, ≥8 samples).
- **FPS > 30 for the WHOLE 15–17 window** — not a single lucky sample. Confirmed over
  **several independent runs** so a one-off good run can't be mistaken for success.
- **Matrix** (capture FPS for each, window-maximize included where controllable):
  - zoom **out** × speed **normal**
  - zoom **out** × speed **fast (2×)**
  - zoom **normal** × speed **normal**
  - zoom **normal** × speed **fast (2×)**
  - × **windowed vs maximized** where the window state is programmatically controllable.
- **Screenshots** around the 15-min mark across the 2-min window for visual confirmation.
- The player's real worst case (per guardrails) = **fast speed + zoomed out + the swarm** —
  that combo is the gate that matters most.

> Note: prior accepted bar was "25+ and feels smooth" on a 2-min run. THIS goal raises it to
> a **>30 floor sustained through minute 15–17** under the heavy scenario.

---

## 2. Method — fast screen, then definitive gate

Two feedback loops, cheap-first:

**A. Headless accumulation probe (fast, minutes).** A `GameEngine(headless=True)` ticked to
the equivalent of 10–15 min of sim-time at ≥75 enemies, instrumented to log, every ~1–2 min
of sim-time: process **RSS**, `len()` of every major sim collection, per-hero memory sizes,
and `gc` object counts. **Any collection that grows ~linearly with ticks and never plateaus
is the smoking gun.** Catches all SIM-side leaks without a GPU. (Render-side ursina-node
leaks won't show here — those need loop B.)

**B. Live soak harness (definitive, ~17 min/run).** `tools/wk123_fps_soak.py` (to build):
launches the REAL ursina game with the heavy scenario, runs to ~17 min, logs FPS every 15 s
(timestamped; reuses `KINGDOM_FPS_SLOWLOG` `[frameavg]` + `KINGDOM_URSINA_FPS_PROBE`),
screenshots periodically, auto-exits, and is parameterized for the §1 matrix
(zoom/speed/window) via env/CLI. Watch the per-stage slowlog (tick/rend/hudR/hudU) trend
**upward over 15 min** to attribute the degradation to a stage. *(Exact harness spec filled
in §4 after the infra investigation.)*

---

## 3. Iterative loop protocol (the multi-day grind)

Per candidate (highest-severity first):
1. **Apply** the fix on `wk123-fps-degradation` (dispatch the owning agent; behavior-preserving
   — no gameplay/visual change unless explicitly flagged).
2. **Screen (loop A)** if sim-side: re-run the headless accumulation probe → did the target
   collection stop growing? RSS flat?
3. **Gate (loop B)** if promising: run the live soak matrix → FPS > 30 across the whole
   15–17 window, several repeats?
4. **Decide:**
   - PASS the full §1 bar reliably → **keep**, commit on the branch with evidence.
   - FAIL → `git checkout -- <files>` to revert the candidate **unless it's a clearly
     valuable partial win** (then keep it and stack the next candidate on top).
5. **Record** every run (candidate, matrix, FPS samples, verdict) in §5 results log. Never
   declare success on a single instance — require repeats.
6. Continue until FPS reliably holds **>30 through minute 15–17** under the heavy scenario,
   across the matrix and repeats — either by finding the main leak or by clearing enough
   small ones.

**Each failed/abandoned candidate MUST leave the branch clean** (verify `git status` before
the next candidate) so fixes don't silently stack/confound.

---

## 4. Candidate fixes to try  *(filled from the investigation workflow — see §4a)*

> Ranked, behavior-preserving fixes for the accumulation/leak. Populated after
> `wk123-fps-degradation-investigate` returns (sim-growth + ursina-leak + per-frame-scaling
> hunters + empirical headless measurement). Each entry: site, how it degrades over time,
> the fix, the confirm-signal, and risk.

**Investigation outcome (5-agent workflow, 2026-06-02).** The headless long-sim probe
(`tmp/wk123/leak_probe.py`, 15 sim-min @ fast, ~80 enemies) found **NO sim-side RSS/object
leak** — every collection plateaued (RSS 88→99.8 MB, flat by min 5). **But it is blind to
GPU/Panda scene-graph growth, and its synthetic scenario did not kill heroes.** The
ursina-leak hunter independently **proved** the real leak headlessly. Both point to the
**render layer**. Ranked candidates:

| # | Candidate | Where | How it degrades over time | Fix (behavior-preserving) | Confirm signal | Conf. |
|---|-----------|-------|---------------------------|---------------------------|----------------|-------|
| **C1 (PRIMARY)** | **Dead-unit overlay children never destroyed** | `ursina_renderer.py:722-741` `_destroy_removed_entities` destroys only the parent billboard + `_ks_gold_label`; children `_ks_hp_bg/_ks_hp_fg/_ks_name_label/_ks_rest_label/_ks_tc_gold` (created `parent=ent` in `ursina_unit_overlays.py`) are orphaned because Ursina `destroy.py:39-43` child-recursion is commented out | Orphans pile into `scene.entities`; `main._update` walks `for e in scene.entities` every frame → per-frame cost ∝ cumulative deaths. Needs BOTH 70+ enemies (kills/min) AND 10+ min (accumulate) — matches the report exactly | Add `_free_entity_overlays(ent)` that destroys the known `_ks_*` children (+ iterates `list(ent.children)+ent.loose_children`) BEFORE `destroy(ent)`; call from `_destroy_removed_entities` AND the inline building-destroy at `ursina_building_sync.py:95-101` | `len(scene.entities)` climbs monotonically while `len(renderer._entities)` stays flat; after fix `scene.entities` plateaus + `[frameavg] rend=` stops creeping | **EMPIRICALLY CONFIRMED headlessly** |
| **C2 (SECONDARY)** | **Dead heroes/peasants never culled from `SimEngine.heroes`/`.peasants`** | `sim_engine.py:806-808` culls only enemies+guards; heroes/peasants append-only (`:102`,`:108`). Per-frame `build_hero_profile_snapshot` (sorts known_places/profile_memory) at `:431` + `UnitDTO` at `:608/:610` run for ALL-TIME entities | Per-frame profile/DTO cost scales O(all-time hires), not O(alive); rises with death/replace churn over time | (a) skip dead in the per-frame builds (`if not is_alive: continue` at `:431/:608/:610`) — cheap, behavior-preserving (renderers already skip dead); (b) cull dead **peasants** immediately (mirror enemies/guards); (c) **TTL-cull** dead heroes after the memorial — careful: `hud.py:776/783` memorial + pin-liveness read `hero_profiles_by_id` | `len(heroes)` climbs while alive stays flat in the LIVE soak; `[frameavg] hudR` rises with E flat | code-confirmed; **NOT empirically triggered** (headless run had no hero deaths) |
| C3 | VFX `_debris` never pruned | `vfx.py:72/254`, render loops all every frame `:361` | pygame-path draw cost grows; Ursina = RSS-only (uses bounded `rubble_records`) | FIFO-cap (~200) or TTL in `_spawn_debris`/`update()` | `len(vfx._debris)` over soak | low (Ursina default) |
| C4 | Inline building-destroy leaks `_ks_hp_bar`/`_ks_gold_label` | `ursina_building_sync.py:95-101` | every razed building adds a few permanent orphans | fold into the shared `_free_entity_overlays` helper (C1) | `scene.entities` after demolitions | low |
| C5 | `_tree_growth_by_tile` O(trees) dict rebuilt every tick + DTO churn | `sim_engine.py:679-681`, `:600-624` | GC pressure scales with saturated counts | dirty-gate the tree-dict rebuild (trees-revision int); skip-dead DTOs (overlaps C2) | gen0 gc counts/min; tick-ms | low amplifier |
| C6 | Projectile billboard create/destroy churn (`id(proj)`-keyed) | `ursina_misc_props_sync.py:51-89` | bounded (not a time-leak) but churny + id-reuse smell | pool a small ring of billboards / stable monotonic id | `rend=` spikes on volleys, not trending | low |

**Loop order:** apply **C1 first** (confirmed, default path, highest leverage) → headless `scene.entities`
regression must go green → live soak. If the bar still misses, stack **C2** (skip-dead builds +
peasant cull + hero TTL) → re-soak. Then C3–C6 only if needed. Do NOT chase the headless-ruled-out
sim-RSS angle. The **negative headless result is itself the key clue**: the leak is render-side, exactly
where C1 lives.

### 4b. Live soak harness spec — `tools/wk123_fps_soak.py` (to build; pieces exist)
Reuse existing knobs: `KINGDOM_FPS_SLOWLOG` (`[frameavg]` every 120f: tick/rend/hudR/hudU + `E=/B=`),
`KINGDOM_URSINA_FPS_PROBE`(+`_WARMUP_SEC`) on-exit percentiles, `KINGDOM_URSINA_AUTO_EXIT_SEC`,
`KINGDOM_URSINA_AUTO_SCREENSHOT_PATH`. **Build:** a first-frame hook that (a) force-spawns the heavy
scenario via the promoted `leak_probe.py` helpers (≈24 heroes via `WarriorGuild`+`Hero`, ≈100 buildings
via `building_factory`, 80 enemies ring-spawned + topped up to the `MAX_ALIVE_ENEMIES` cap); (b) locks
speed (`timebase.set_time_multiplier(1.0)` for fast / `0.5` normal, then stub the setter); (c) sets
`engine.zoom = config.ZOOM_MIN` (out) or default (normal); (d) maximizes via Panda
`WindowProperties.setSize(desktop)` (DEFAULT_BORDERLESS already borderless). Run to ~17 min
(`AUTO_EXIT_SEC=1020`, `WARMUP_SEC=20`). Log: FPS (`engine._ursina_window_fps_ema`) every 15 s, densified
to ~2 s in the **15–17 min window**; `len(scene.entities)` & `len(heroes)`/alive every 120 f; periodic
screenshots + forced at 15/16/17 min. **CLI:** `--zoom {out,normal} --speed {normal,fast}
--window {windowed,maximized} --minutes 17`. **Output:** `tmp/wk123/soak_<zoom>_<speed>_<window>.log`
+ parsed CSV(`wall_ts,ema_fps,dt_ms,tick,rend,hudR,hudU,E,B,scene_entities,heroes,alive`) +
`docs/screenshots/wk123_soak/`. Matrix = zoom{out,normal}×speed{normal,fast}×window{windowed,maximized}.

---

## 5. Results log (append every run — never overwrite)

| # | Candidate | Loop | Matrix combo | FPS @15–17min (avg/min samples) | Verdict | Kept? |
|---|-----------|------|--------------|---------------------------------|---------|-------|
| _ | baseline (no fix) | A+B | (establish current degradation curve first) | _ | _ | _ |

---

## 6. Guardrails (hard — from `11-fps-performance-guardrails.mdc`)

- **DO NOT undo** the existing perf fixes on main: sim dt-clamp (`lifecycle.py`), multi-band
  HUD upload (`ursina_app_ui_overlay.py`), `gc.freeze`+thresholds, stationary-pointer cache,
  prefab prewarm, building position/color dirty-gate, zone-fog cache.
- **NEVER** cut tree/grass/forest density or grass stride for perf — perf comes from the
  data/render path, never content reduction.
- **DON'T** add per-frame full-window HUD upload, multiplied uncached `get_game_state()`,
  unbounded per-frame allocation, or remove the dt-clamp.
- Instanced unit renderer = **OPT-IN and currently BROKEN** (units invisible) — not a
  candidate here unless an interactive-GPU-debug fix is in hand; do not blind-iterate it.
- **Test at the player's real conditions** (fast speed + zoomed out + swarm), not normal-speed.
- Balance/pacing knobs (lower `MAX_ALIVE_ENEMIES` / neutral-building cap) **change game feel
  → out of scope** unless Jaimie okays them; he wants MORE enemies (hundreds), not fewer.

## 7. Definition of Done
- The main time-degradation cause is identified (named, with evidence) **or** enough small
  leaks are fixed that the §1 bar holds.
- FPS **>30 sustained through minute 15–17**, ≥75 enemies / ≥20 heroes / ≥20 buildings,
  across the matrix, **confirmed over several repeats**.
- Winning fix(es) committed with evidence (FPS logs + screenshots); branch merged to main.
- `qa_smoke --quick` green; WK67 digest byte-identical; no guardrail violated.
- Guardrails doc updated with the time-degradation finding + how it's now tested (15-min soak).
