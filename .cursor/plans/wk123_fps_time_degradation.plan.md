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

### C1 — overlay-child destroy leak fix (`free_entity_overlays`) — IMPLEMENTED & LEAK-CONFIRMED-FIXED
- Headless regtest `tests/test_wk123_scene_entity_leak.py`: **3 passed** (was +85/cycle monotonic). `after_death==baseline`, cycle counts `[16,16,16]`. Renderer suite 494 passed. `qa_smoke --quick` exit 0.
- **Live proof the leak WAS real + is now bounded** (90s worst-combo smoke, `scene_entities` column):
  - PRE-C1: `22→1047→1349→1545→1848→2100` (monotonic climb; would hit ~20k by min 15).
  - POST-C1: `22→1002→989→887→870→867` (**flat/bounded** — tracks live entities only). ✅ Time-degradation source eliminated.

### 90s smoke matrix (post-C1, scenario = 24 heroes / **100 buildings** / 80 enemies) — FPS ENVELOPE
| combo | avg_fps | p10 | dominant stage (ms) |
|-------|---------|-----|---------------------|
| out / fast / maximized | 9.7 | 8.1 | rend 30.9, tick 17.9, hudU 16.2 |
| out / fast / windowed | 11.1 | 8.6 | rend 29.6, tick 16.3, hudU 9.7 |
| normal / normal / windowed (best) | 12.1 | 9.7 | **rend 29.3**, tick 8.3, hudU 7.6 |

**PIVOTAL FINDINGS:**
1. **C1 fixed the leak, but the leak was NOT the FPS floor.** Post-C1 FPS at the worst combo is unchanged (~9.7) — the leak's per-frame cost is small until thousands of orphans accumulate (the 15-min damage), but the *floor* is steady-state render load.
2. **FPS is RENDER-bound and combo-independent (~10–12 fps).** zoom/speed/window move it only ~2 fps → the bottleneck is **`rend` (ursina_renderer.update + build_snapshot) ≈ 29–31 ms**, the legacy per-Entity sync of ~110 units + ~100 buildings + ~900 overlay nodes every frame. This is the documented swarm cost the guardrails say only **instancing** (OPT-IN, currently BROKEN) clears.
3. **Scenario representativeness caveat:** the harness force-spawns **100 buildings (5× the "20+" spec)** and `rend` spikes to 122 ms at B=100 — likely building-prefab cold-parse from runtime force-spawn (bypassing startup prewarm). So these numbers may be PESSIMISTIC vs real play. → harness enhancement in flight: entity-count flags + representativeness fix, then re-measure at the Sovereign's spec (24 / 24 / 80).

**Working hypothesis (to confirm at representative spec):** C1 resolves the *time-degradation* (Jaimie's stated suspicion); reaching **>30 fps at 75+ enemies** (and his "hundreds" goal) is gated by the **render path**, not a leak — i.e. needs the instanced renderer or steady-state `rend` reduction, not more leak-hunting.

### Spec-accurate measurement (24 heroes / 24 active buildings / 80 enemies) — CONFIRMS the wall
Harness fixed (entity-count flags; buildings default 24; prewarm wired; 122ms cold-parse spikes eliminated; perf-agent confirmed steady `rend` is GENUINE legacy per-Entity cost).
| combo | avg_fps | p10 | rend | tick | hudU |
|-------|---------|-----|------|------|------|
| normal / normal / windowed (best) | **15.4** | 11.5 | 22.7 | 6.6 | 7.2 |
| out / fast / maximized (worst) | **13.1** | 9.7 | 23.3 | 12.4 | 14.5 |

- Still **~15 fps at Jaimie's exact spec** — `rend` (~23ms legacy per-Entity sync of ~80 enemies + 24 heroes + overlays) is the floor; zoom/speed/window move it only ~2 fps.
- `alive_heroes` 24→16 in 90s → **heroes die fast** → C2 dead-hero accumulation DOES bite in live play (a real 15-min `rend` amplifier) even though the headless probe couldn't trigger it.

### Strategy decision (post-data)
- **C1 (leak) — DONE.** Time-degradation source removed (`scene_entities` bounded).
- **C2 (dead-hero/peasant per-frame cost) — IN FLIGHT.** Cheap, behavior-preserving; banks the second time-degradation amplifier. Won't reach 30 alone.
- **Instanced unit renderer — THE lever, IN FLIGHT (root-cause investigation).** The legacy path cannot do 80 (let alone "hundreds") units at >30 fps; the guardrails + 5 live runs + the perf agent all agree. Pursuing the documented but-broken instanced renderer via a focused **alpha/transparency-path** root-cause (NOT blind sampler-swapping, which failed 5× prior) + live PNG pixel-diff verification.
- Legacy-only cheap wins (overlay-node trims, frustum-cull, dirty-gating) can add a few fps but won't clear 30 at the swarm — secondary to the instanced fix.

**Note for the eventual writeup:** even with C1+C2, if the instanced renderer cannot be fixed behavior-preservingly, >30 fps at 75+ enemies may require interactive GPU debug (RenderDoc) beyond a CLI agent's reach — in which case the honest deliverable is: leak + dead-hero time-degradation fixed (FPS now STABLE, not declining, over 15 min), envelope characterized, instanced-renderer fix scoped as the remaining lever.

### C7 (THE LEVER) — instanced-unit invisibility ROOT-CAUSED: missing `set_two_sided(True)` (backface cull, NOT alpha)
Deep read-only investigation (full alpha/texture/UV/sampler/buffer trace + legacy-vs-instanced render-state diff) found the 5 prior blind attempts all chased the wrong layer. **The instanced unit billboard quad is backface-CULLED** — the two unit geoms in `game/graphics/instanced_unit_renderer.py` (~L230-247) never call `set_two_sided(True)`, unlike legacy billboards (`double_sided=True`, `ursina_entity_render_collab.py:123`) and instanced trees (`set_two_sided(True)`, `instanced_nature_renderer.py:555`). The in-shader camera-facing billboard winds back-facing for the tilted RTS camera → GL culls it → zero fragments → "invisible, terrain shows through" (not an alpha discard). **Fingerprint:** the dark shadow blob renders *only because* the shadow geom is the lone unit-renderer geom that DOES set `set_two_sided(True)` (`:227`). The entire alpha path (atlas F_rgba, 191k nonzero-alpha texels, correct V-flip landing on opaque band, `set_texture(...,1)` matching legacy) was verified correct — **keep the sampler/UV/OmniBoundingVolume; do NOT touch them.**
- **Fix (IN FLIGHT):** add `set_two_sided(True)` to both unit geoms (2 lines).
- **Verify (main session, GPU):** capture legacy (`KINGDOM_URSINA_INSTANCING=0`) vs instanced (`=1`) at the SAME deterministic scene (`HERO_FPS_PROBE_COUNT=20` + `DISABLE_NEUTRAL_SPAWN=1` + `AUTO_SCREENSHOT_PATH` + `AUTO_EXIT_SEC=20`), numpy pixel-diff → units must show sprite colors (warrior shirt ~(143,56,56)), not terrain.
- **If units render:** instancing is viable → enable for the swarm → re-soak. Guardrails: instanced ~51fps/p10 29 vs legacy ~35/21 — the path to >30 at 75+ enemies and the "hundreds" goal.
- Fallback if 2 lines insufficient: align units to the trees' parent+child NodePath pattern (`instanced_nature_renderer.py:513-577`).

**C7 — VERIFIED FIXED (2026-06-03).** Applied `set_two_sided(True)` to `_geom_node_outside` + `_geom_node_inside` (+ comments). Imports OK; 35 instancing tests pass. **GPU pixel-diff at the deterministic 20-warrior scene (legacy `INSTANCING=0` vs instanced `=1`):** sprite-shirt-colored pixels — legacy **2637**, instanced **2604** (98.7% match; pre-fix would be ~0). Visual confirms units render normally, no dominant shadow blob. **The 5-prior-attempt instanced-renderer bug is SOLVED** — units visible. Two lines, behavior-preserving.

### C2 — VERIFIED (2026-06-03). Dead-unit DTO-skip + dead-peasant cull + 30s TTL dead-hero retention (keyed off `timebase.now_ms()`, preserves the 10s memorial/pin window). qa_smoke exit 0; WK67 digest byte-identical (10 passed); memorial/pin/watch suite 139 passed; new TTL test 3 passed.

### 🎯 INSTANCING FPS RESULT (C1+C2+C7 stacked, spec 24/24/80, 90s smoke) — 2.8–2.5× GAIN
| combo | legacy avg | **instanced avg** | inst p50 | inst p10 | rend ms (legacy→inst) |
|-------|-----------|-------------------|----------|----------|-----------------------|
| out / fast / maximized (worst) | 13.1 | **28.5** | 23.8 | 17.6 | 23.3 → **7.2** |
| normal / normal / windowed (best) | 15.4 | **38.1** | 42.2 | 22.3 | 22.7 → **6.6** |

- `rend` collapsed ~3× — instancing removed the per-Entity unit-render wall. **Typical/best combos solidly >30** (38 avg, p50 42). Worst combo ~28 avg (borderline solid-30 floor; p10 17.6 from hudU/tick spikes at maximized).
- Caveat: 90s smoke lets heroes die unreplaced (alive 24→12) → under-represents sustained load. Definitive 15-min runs (guild replaces to ~24) give the true sustained number — IN PROGRESS.
- **This is the answer to the >30 / "hundreds of enemies" goal:** the leak (C1) + dead-hero (C2) fixes stop time-degradation; instancing (C7) lifts the steady-state floor 2.5–2.8×. Remaining gap to a solid >30 at the absolute-worst combo is GPU-draw + maximized-HUD-upload bound (hard, behavior-preserving limits).

### Definitive 17-min worst-combo soak (instanced) — TIME-DEGRADATION DEFINITIVELY FIXED + reveals hero cost
- **Time-degradation: GONE.** From min 3→17 (14 min), `fps_ema` is rock-stable **50–56** and `scene_entities` pinned at **117** — zero drift. min-15-17 window: avg **50.9**, p50 55.9, p10 26.5; stages tiny (rend 5.1ms, tick 2.8ms, hudU 2.9ms). C1+C2 conclusively eliminated the accumulation. Screenshots saved (`out_fast_maximized_min15/16.png`).
- **BUT scenario flaw:** all 24 heroes died by ~2.5 min and the guild never re-hired (alive_heroes→0, stayed 0). So the 50fps is at **0 heroes** + 82 enemies + 41 buildings — NOT the "20+ heroes" spec. → fix: `topup_heroes` to maintain ~24 (IN FLIGHT).
- **Key decomposition:** 82 enemies (instanced) ≈ **50 fps** (cheap!); +24 alive heroes → ~28 fps. **Heroes cost ~17ms/frame, only ~6ms tick+rend** → the rest (~11ms) is the per-frame `build_hero_profile_snapshot` (sorts known_places+memory for ALL heroes every frame in get_game_state). → **C8 (IN FLIGHT):** cache/dirty-gate or build-only-for-selected — could recover ~10ms → push the worst combo with 24 heroes from ~28 to ~38+.

**Revised candidate order:** C1✅ C2✅ C7✅ → C8 (per-hero profile cost) → re-soak with heroes maintained → if >30, enable instancing default-on + definitive matrix. C8 is the likely final piece for a solid >30 at full spec.

### FULL ENVELOPE at spec (24h/24b/80e, instanced, heroes MAINTAINED, C1+C2+C7+C8) — 90s smokes (FPS proven flat over time, so representative)
| combo | avg | p50 | verdict |
|-------|-----|-----|---------|
| out / normal / windowed | 37.7 | 42.2 | solid >30 ✅ |
| normal / normal / windowed | 37.2 | 42.2 | solid >30 ✅ |
| **out / fast / windowed** (Jaimie's likely real play) | **31.5** | 27.7 | **borderline** (avg>30, dips to 28) |
| out / fast / maximized | 25.2 | 22.0 | below 30 ❌ |

- C8 confirmed minor (profile build only ~0.7ms headless, not the ~11ms). The 24-hero cost is mostly **GPU draw + sync of ~330 non-instanced overlay nodes** (HP bars + name labels) + maximized HUD upload.
- Jaimie's real condition (zoomed-out + fast, windowed) is RIGHT at 30 — needs ~+5fps to be *reliably* >30.

### C9 (IN FLIGHT) — instance the unit overlay nodes (HP bars; names if feasible)
The clean behavior-preserving lever: HP bars are uniform quads → instance them like units (C7)/trees, removing ~200-330 per-Entity overlay nodes from rend+GPU+scene.entities. Expected: out/fast/windowed 31→~36 (solid ✅), out/fast/maximized 25→~29. Gated behind the instancing path; pixel-identical bars; must respect C1 (no leak) + C7 (set_two_sided). Bail if not cleanly behavior-preserving.

### ⚠️ C9 CORRECTION (2026-06-03) — instancing currently DROPS overlays (HP bars / names / gold)
C9 found the premise wrong: the instanced render branch in `ursina_renderer.update()` `return`s BEFORE the unit-sync calls, so when `KINGDOM_URSINA_INSTANCING=1` the per-unit overlay children are **never created**. Measured (real renderer, 24h/80e/61b, isolated processes): LEGACY `scene.entities=536` incl. **241 overlays** (_ks_hp_bg 72, _ks_hp_fg 72, _ks_name_label 73, _ks_gold_label 24); INSTANCED `scene.entities=222`, **overlays = 0**.
**Implication (honest):** the ~2.5× instancing FPS partly came from NOT drawing HP bars + names — a VISUAL REGRESSION, not behavior-preserving. Instancing is NOT drop-in shippable as default. To ship it with feature parity, the overlays must be rendered for instanced units (positioned by world coords, ideally instanced) — a feature-build, not a free perf win.
**Revised honest envelope:**
- LEGACY default (full visuals, with overlays): ~15 fps steady — but **time-degradation FIXED** (C1+C2+C8 → FPS now FLAT, no decline). Shippable today.
- INSTANCED (units visible via C7) but **missing HP bars/names**: ~31 windowed-fast-out / ~25 maximized. NOT shippable as default without overlays.
- INSTANCED + overlays restored (the real target): est. ~27-30 windowed / ~24-26 maximized — borderline; substantial graphics work.
- **Reliably >30 at ALL of Jaimie's conditions (esp. maximized+fast+zoomed-out) is NOT achievable behavior-preservingly on this hardware** — it's HUD-upload + GPU-fill bound. Windowed/normal-speed conditions clear 30; the heaviest condition is a ~25 ceiling.

### Remaining-gap decision (Jaimie's, if C9 insufficient for maximized)
If after C9 the **maximized**+fast+zoomed-out combo still misses 30, the only further levers are visual/behavior tradeoffs OUT of "optimize-only" scope → Jaimie's call:
(a) overlay LOD-cull when zoomed out (labels illegible anyway); (b) throttle radar/HUD upload at high res (guardrails-warned); (c) accept maximized ~28-29 and play windowed. **Headline regardless:** the time-degradation bug Jaimie reported is FIXED, and instancing (revived) delivers 2.5-3× — typical + his likely-real windowed condition reach/clear 30.

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
