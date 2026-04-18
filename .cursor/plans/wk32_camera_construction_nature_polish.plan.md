---
name: ""
overview: ""
todos: []
isProject: false
---

# WK32 — Camera Nav, Construction Phases, Nature Polish, Darker Non-Retro, Spawn Spacing

> **Single sprint, six workstreams.** Shipping in one round (`wk32_r1_execution`) under PM hub sprint `wk32-camera-construction-nature-polish`. The six workstreams below are independent enough to ship in parallel; the only internal dependency is that Agent 03's construction-phase renderer hook needs Agent 05's `construction_progress` field to land first.

**PM hub:** `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json` → `sprints["wk32-camera-construction-nature-polish"].rounds["wk32_r1_execution"]`

**Depends on:** WK31 Part A (perf + pack-scale tooling) and Part B (economy prefabs) closed green — `inn_v1`, `farm_v1`, `food_stand_v1`, `gnome_hovel_v1` shipped, `qa_smoke --quick` PASS as of sprint open.

**Gates (all must hold):**

- `python tools/qa_smoke.py --quick` → **PASS**
- `python tools/validate_assets.py --report` → **exit 0** (pre-existing warnings acceptable)
- `tools/determinism_guard` expectations unchanged
- No `config.py` footprint edits (shrink prefabs, never grow tile counts)
- No CHANGELOG / version bump unless Jaimie explicitly requests

---

## Human input (Jaimie, 2026-04-18)

1. **Camera nav in-game** — Ursina's built-in camera (pan/orbit/zoom with mouse), like model viewer / assembler. Currently WASD-only; no rotate, no mouse pan.
2. **Construction appearance** — buildings look 100% built the moment they're placed. Need staged visuals: empty plot → 20% built → 50% built → 100% final, progressing as peasants work.
3. **Grass looks bad** — new models + more density.
4. **Nature populations** — add bushes, rocks, other Nature Kit doodads to the terrain.
5. **Darken non-Retro Kenney packs ~40%** — Survival, Nature, Fantasy Town, Graveyard all read too light / washed out. Retro Fantasy Kit stays as-is.
6. **Auto-spawned buildings** — must leave at least a 1-tile gap between neighbours on auto-placement.

All six ship together as the WK32 polish/feel pass.

---

## Workstream A — In-game camera navigation (Ursina EditorCamera parity)

### A.1 Objective

Replace / augment the current custom WASD+Q/E camera path in `game/graphics/ursina_app.py::_setup_ursina_camera_for_castle` with the same feel the model viewer and assembler already have (Ursina `EditorCamera` — middle-mouse/right-mouse orbit, wheel zoom, keyboard pan, shift-pan faster). Keep WASD as a *supplement* so existing muscle memory still works.

### A.2 Scope (Agent 03, **HIGH** intelligence)

- Adopt Ursina's `EditorCamera` (or a minimally-wrapped variant) as the default in-game camera for `--renderer ursina`.
- Preserve existing zoom sync to `engine.zoom` (HUD / tile math) — if EditorCamera fights `engine.zoom`, pick one source of truth and document it in the log.
- Keep WASD pan, F to re-frame castle, existing screenshot hotkeys working.
- Gate behind an env var only if risk demands it (`KINGDOM_URSINA_EDITORCAMERA=1`). Preferred: **default-on** with a fallback flag if playtest hates it.
- Determinism / smoke unaffected; camera is render-side.

### A.3 Consult (Agent 08 UX/UI, **LOW**)

- Short feel review after 03 lands it: pan speed, zoom rate, orbit sensitivity, initial framing on castle. Produce a one-paragraph note in Agent 08's log with any tuning requests (numbers only; 03 applies).

### A.4 Reference code

- `tools/model_viewer_kenney.py` — `EditorCamera()` instantiation around line 721.
- `tools/model_assembler_kenney.py` — same pattern.
- `game/graphics/ursina_app.py::_setup_ursina_camera_for_castle` — current custom path.
- `game/graphics/ursina_app.py::_sync_ursina_camera_fov_from_zoom` — FOV↔zoom coupling.

### A.5 Definition of Done (A)

- [ ] Mouse orbit/pan/zoom work in-game equivalently to the assembler.
- [ ] WASD still pans; existing hotkeys still function.
- [ ] Castle framing on startup unchanged (or improved).
- [ ] Agent 08 feel note logged.
- [ ] Smoke PASS.

---

## Workstream B — Construction-phase visuals (plots + partials + finals)

### B.1 Objective

Buildings should visually evolve as peasants build them. The simulation already has `construction_started` (binary). We extend it to a continuous `construction_progress ∈ [0.0, 1.0]` and the renderer picks the right prefab based on thresholds.

### B.2 Prefab ladder (per building)

| Stage | Threshold | Prefab |
|-------|-----------|--------|
| Plot (0%) | `construction_progress == 0.0` OR just placed | Size-based empty plot (`plot_1x1_v1`, `plot_2x2_v1`, `plot_3x3_v1`) |
| Early (20%) | `0.20 <= progress < 0.50` | `<building>_build_20_v1.json` |
| Mid (50%) | `0.50 <= progress < 1.0` | `<building>_build_50_v1.json` |
| Final (100%) | `progress >= 1.0` OR `construction_started == False and built` | existing `<building>_v1.json` |

**Fallback rule (critical):** if a specific intermediate prefab is missing, renderer falls back to the **nearest lower-stage prefab that exists**, in this order: final → mid 50% → early 20% → size-matched empty plot. This lets us ship the **system + plots + MVP intermediates** this sprint and backfill intermediates building-by-building in follow-up sprints without breaking anything.

### B.3 MVP prefab set for this sprint (Agent 15, **HIGH**)

**Shared empty plots (always required):**

- `assets/prefabs/buildings/plot_1x1_v1.json` — small dirt/cleared square, stakes/rope, maybe a shovel prop. Footprint 1×1.
- `assets/prefabs/buildings/plot_2x2_v1.json` — Footprint 2×2. Scaffolding hint at one corner.
- `assets/prefabs/buildings/plot_3x3_v1.json` — Footprint 3×3. Foundation stones, larger scaffold.

**Pilot intermediate prefabs (MVP — three buildings only):**

1. `peasant_house_small_build_20_v1.json`, `peasant_house_small_build_50_v1.json`
2. `castle_build_20_v1.json`, `castle_build_50_v1.json`
3. `warrior_guild_build_20_v1.json`, `warrior_guild_build_50_v1.json`

Three is intentional: most-visible building (peasant house — many), tallest silhouette (castle), representative guild (warrior). Remaining buildings (inn, farm, food_stand, gnome_hovel, ranger_guild, rogue_guild, wizard_guild) use the plot → final fallback this sprint and get their intermediates in a later sprint.

Agent 15 authoring notes:

- 20%: foundation + partial walls (~25% of final piece count), scaffolding pieces allowed. Keep piece count ≤ 60% of final.
- 50%: walls up + partial roof (~50–60% of final). Scaffolding still visible.
- Use Retro Fantasy scaffolding/wood pieces where available; fallback to Survival wood / Nature logs.
- `footprint_tiles` must exactly match the final prefab for that building.
- `ground_anchor_y = 0.0`; `attribution[]` complete.
- `--open` round-trip through `tools/model_assembler_kenney.py`.

### B.4 Simulation changes (Agent 05, **MEDIUM**)

- Add `construction_progress: float` to `Building` (0.0 at placement, 1.0 when done). If an equivalent already exists by a different name, normalize — do not duplicate.
- Derive from existing peasant-build time elapsed / total; expose via `get_game_state()` snapshot so the renderer can read it.
- `construction_started` semantics preserved for back-compat. `construction_progress` is strictly additive.
- Deterministic: identical to current build-time math; no RNG introduced.

### B.5 Renderer changes (Agent 03, **HIGH** — bundled with A)

- In `game/graphics/ursina_renderer.py`, the building-prefab resolver picks stage by `construction_progress` thresholds (see B.2) with the B.2 fallback rule.
- Plot prefab name derived from footprint: `plot_{w}x{h}_v1` (fallback to `plot_1x1_v1` if odd sizes appear).
- Swapping prefabs when progress crosses a threshold is the simplest path (destroy+respawn the building's Ursina group). Agent 03 judges whether that's cheap enough; if not, a hide/show subgroup approach is acceptable.

### B.6 Manifest (Agent 12, **LOW**)

- Add the 3 plot prefabs + 6 pilot intermediates to `tools/assets_manifest.json` under `prefabs.buildings` as **optional** entries (not REQUIRED) so a missing intermediate does not fail `validate_assets --report`.
- Add one REQUIRED entry for `plot_1x1_v1` / `plot_2x2_v1` / `plot_3x3_v1` only if Agent 03 confirms the plot fallback needs at least size-1x1 present.

### B.7 Definition of Done (B)

- [ ] `construction_progress` on Building; game-state snapshot exposes it.
- [ ] Three plot prefabs exist and round-trip.
- [ ] Six pilot intermediate prefabs exist and round-trip.
- [ ] Renderer swaps prefab at thresholds; buildings without intermediates degrade gracefully via fallback (no crash, no missing entity).
- [ ] Manifest updated; `validate_assets --report` exit 0.
- [ ] Human playtest: place peasant house → see plot → watch it reach 20% then 50% then 100%.
- [ ] Smoke PASS.

---

## Workstream C — Grass upgrade (models + density)

### C.1 Agent 15 (**MEDIUM**)

- Identify 2–4 higher-quality grass/tuft/wildflower GLBs (Nature Kit candidates, e.g. `Grass.glb`, `Grass_Large.glb`, `Flower_Red*.glb`, `Flower_*`; Retro Fantasy ground props if any read better). Prefer variety over one "hero" tuft.
- Save the chosen set under `assets/models/environment/` with a stable, documented naming scheme (coordinate with Agent 12 if a manifest entry is needed).
- Log: before/after screenshots of the base meadow, same camera.

### C.2 Agent 03 (**MEDIUM**, bundled with A/B)

- Expand grass scatter in `game/graphics/ursina_renderer.py` to pick from the 2–4 new models (deterministic hash on `(tx, ty)` so it reads as variety, not flicker).
- Bump density — previous stride was widened for FPS; tighten it back toward 1 per tile if Agent 10 says budget allows, else 1 per 2 tiles with multiple per tile in clumps.
- Keep all grass doodad placement off path / water / building tiles as today.

### C.3 Consult — Agent 10 (**MEDIUM**)

- Re-run the same perf bench as WK31 Part A baseline; confirm that higher density + varied models stays within the WK31 budget. If not, back off density and log the ceiling for Agent 03 / PM.

### C.4 DoD (C)

- [ ] New grass GLBs present and attributed.
- [ ] Renderer samples from variety; density improved.
- [ ] Agent 10 confirms FPS within WK31 Part A baseline ±15%.

---

## Workstream D — Nature doodads (bushes, rocks, props)

### D.1 Agent 15 (**MEDIUM**, bundled with C)

- Source bushes (small + large), additional rock variants, mushrooms / logs / stumps from Nature Kit. Aim for 6–10 GLBs total added under `assets/models/environment/`.
- Log: inventory + screenshots.

### D.2 Agent 03 (**MEDIUM**, bundled with B/C)

- Extend the environment spawner in `ursina_renderer.py` with a **deterministic** second scatter pass for non-grass nature (bushes/rocks/logs) at a lower density than grass. Avoid path / water / tile-occupied cells. Use `_grass_scatter_jitter`-style hashing so seeds match across runs.
- Existing rock spawn code is the reference — broaden it into a generic "nature doodad" pass that picks from the expanded model pool.

### D.3 Consult — Agent 09 (**LOW**)

- Cohesion check: the varied foliage should still read as the same *kingdom* visually. Flag any out-of-pack models that stick out.

### D.4 DoD (D)

- [ ] 6–10 nature doodad models shipped and placed.
- [ ] Deterministic scatter; no placement on buildings / path / water.
- [ ] Agent 09 note: cohesion OK or enumerated flags with proposed fixes.

---

## Workstream E — Darken non-Retro packs ~40%

### E.1 Objective

Non-Retro Kenney packs (Survival, Nature, Fantasy Town, Graveyard, Blocky Characters) currently read too light / washed out under our lighting. Apply a **material color multiplier** of ~0.6 (≈ 40% darker) to every piece from those packs at **load time**. Retro Fantasy Kit GLBs stay untouched.

### E.2 Agent 12 (**MEDIUM**)

- Extend the existing pack classifier / loader (as used for pack-scale defaults in WK31 Part A) to emit a `pack_color_multiplier` alongside `pack_scale_multiplier`.
- Default table (tune after review):
  - Retro Fantasy Kit: **1.00** (unchanged, explicit)
  - Survival Kit: **0.60**
  - Nature Kit: **0.60**
  - Fantasy Town Kit: **0.60**
  - Graveyard Kit: **0.60**
  - Blocky Characters: **0.60**
- Apply as a uniform `color` tint / material base-color multiplier during Ursina entity instantiation (single source of truth: same helper used by viewer / assembler / game renderer).
- Document in `.cursor/plans/kenney_gltf_ursina_integration_guide.md` (short note near the pack-scale section).

### E.3 Agent 09 (**LOW**, consult)

- Cohesion check: does the darker tint read as "grounded" or as "muddy"? If muddy, recommend a different multiplier (e.g. 0.70) — 12 applies.

### E.4 DoD (E)

- [ ] Non-Retro GLBs render ~40% darker in-game, viewer, and assembler.
- [ ] Retro Fantasy GLBs unchanged (A/B screenshot).
- [ ] Integration guide updated.
- [ ] Smoke PASS; `validate_assets --report` exit 0.

---

## Workstream F — Auto-spawn 1-tile spacing rule

### F.1 Agent 05 (**LOW**)

- In whichever spawner logic auto-places buildings at world init / time-based events, add a "no neighbour within 1 tile (Chebyshev distance)" check against existing buildings + other auto-placement candidates this tick.
- Must be deterministic under the current seed.
- Do **not** alter `config.py` footprints or manual-placement rules; this is spawner-only.
- Log before/after: a seed that used to pack buildings tightly vs. the same seed with the new rule.

### F.2 DoD (F)

- [ ] Spawner respects ≥ 1-tile gap between any two auto-placed buildings.
- [ ] Deterministic; qa_smoke scenarios unaffected (or updated if intentionally).
- [ ] Smoke PASS.

---

## Agent roster (WK32)

| Agent | Role | Status | Intelligence | Primary workstream(s) |
|------|------|--------|----------------|-----------------------|
| 01 PM | Coordinates, prompts, closeout | active | — | All |
| 03 TechnicalDirector | Camera nav + construction-phase resolver + nature spawner | active | **HIGH** | A, B, C, D |
| 05 GameplaySystems | `construction_progress` + auto-spawn spacing | active | **MEDIUM** | B, F |
| 12 ToolsDevEx | Pack color multiplier in loader / classifier | active | **MEDIUM** | E |
| 15 ModelAssembler | Plot prefabs, pilot intermediates, grass + nature model sourcing | active | **HIGH** | B, C, D |
| 08 UX/UI | Camera feel tuning review | consult | **LOW** | A |
| 09 ArtDirector | Cohesion review (nature + darker tint) | consult | **LOW** | D, E |
| 10 PerformanceStability | FPS check with new doodads/density | consult | **MEDIUM** | C, D |
| 11 QA | Gate runs | consult | **LOW** | All |
| 02, 04, 06, 07, 13, 14 | — | silent | — | — |

---

## Integration order (recommended)

1. **05** lands `construction_progress` field (no-ops for visuals; unblocks 03).
2. **15** ships plot prefabs (1x1, 2x2, 3x3) and starts pilot intermediates in parallel.
3. **03** lands EditorCamera + construction-phase resolver (fallback to final if intermediates absent) so the system works even if 15 is still authoring.
4. **15** finishes 6 pilot intermediates + starts grass/nature sourcing.
5. **12** lands pack color multiplier.
6. **03** wires nature doodad expanded scatter once 15's models land.
7. **05** ships auto-spawn spacing rule.
8. **10** perf pass over grass + nature density; recommends stride if needed.
9. **09** cohesion note (tint + foliage).
10. **08** camera feel note → **03** applies tuning.
11. **11** final gate run.

---

## Out of scope (explicit)

- Intermediate build-stage prefabs for buildings *other than* the pilot set (peasant_house_small, castle, warrior_guild). Remaining buildings use fallback; follow-up sprint fills them in.
- Construction visual effects / particles (dust puffs, scaffolding animation). Later.
- Destruction / demolition visual staging. Later.
- Pack darkening policy changes for Retro Fantasy Kit. Out.
- `config.py` footprint edits. Forbidden.
- Prefab baker. Still not opened unless perf baseline breaks in this sprint.

---

## Combined Definition of Done

- [ ] A — EditorCamera nav default-on, WASD preserved, 08 feel note logged.
- [ ] B — `construction_progress` shipped; 3 plots + 6 pilot intermediates round-trip; renderer swaps on thresholds with fallback; playtest watches peasant house cycle plot → 20% → 50% → 100%.
- [ ] C — 2–4 new grass models; density improved; Agent 10 perf note.
- [ ] D — 6–10 nature doodads deterministically scattered; Agent 09 cohesion note.
- [ ] E — Non-Retro packs render ~40% darker; Retro unchanged; integration guide updated.
- [ ] F — Auto-spawn spacing ≥ 1 tile; deterministic.
- [ ] `python tools/qa_smoke.py --quick` **PASS**.
- [ ] `python tools/validate_assets.py --report` **exit 0**.
- [ ] No `config.py` footprint edits; no CHANGELOG bump (unless Jaimie asks).

---

## Related docs

- `.cursor/plans/wk31_kingdom_perf_and_economy.plan.md` — prior sprint (perf + economy prefabs).
- `.cursor/plans/wk30_buildings_pipeline.plan.md` — generalized prefab loader.
- `.cursor/plans/kenney_gltf_ursina_integration_guide.md` — shader classifier + pack-scale defaults (extend here for color multiplier).
- `.cursor/plans/kenney_assets_models_mapping.plan.md` — pack inventory reference for Agent 15.
- `assets/prefabs/schema.md` — prefab JSON contract.
- `.cursor/rules/agent-01-pm-onboarding.mdc` — PM workflow & send-list / intelligence-tag rules.
