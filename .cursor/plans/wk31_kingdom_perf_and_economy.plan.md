# WK31 — Kingdom Performance, Pack Scale & Economy Buildings (Combined)

> **Single plan:** Part A = FPS + Kenney pack scale; Part B = economy / living prefabs (Inn, Farm, Food Stand, Gnome Hovel).  
> **Recommended order:** finish **Part A** (FPS + pack tooling) before **Part B** (economy prefabs), so new kitbash uses stable perf and scale defaults. PM may still split these into separate hub rounds (`wk31_r1` vs `wk31_r2` / `wk32_r1`).

**PM hub (Part A):** `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json` → `sprints["wk31-perf-fps-and-pack-scale"]`  
**Depends on:** WK30 (military prefabs + generalized loader) closed or far enough along that Ursina prefabs exist.

---

## Part A — FPS Restoration & Kenney Pack Scale Normalization

### A.1 FPS / frame time (human-reported lag)

Ursina has become laggy over the last one or few sprints. Restore a **playable** frame budget on a mid-range PC for a typical kingdom view (multiple prefab buildings + environment).

- **Agent 10** establishes a **baseline** (F2 overlay ms/frame, optional `tools/perf_benchmark.py` for sim separation) and produces a **short prioritized hotspot list** (Ursina entity count, per-frame work, draw path, fog, etc.).
- **Agent 03** implements mitigations with **no determinism regressions** (`determinism_guard` + `qa_smoke --quick` stay green).
- **Scope:** Renderer and simulation hot paths that show up in profiling; **not** a full engine rewrite.

### A.2 Pack scale / grid fit (walls and model builder)

Only **Retro Fantasy Kit** (GLB) pieces feel correctly sized for kitbash; other packs (e.g. Survival, Nature/GLTF) use different native scales. In the **model viewer** and **assembler**, pieces are **centered in the cell** and **uniform-fitted** to `model_max_extent`, which leaves **visible gaps** between intended wall segments.

- **Agent 12** introduces **pack-aware defaults**: e.g. per top-level folder or per-pack multiplier so new pieces spawn closer to a **shared grid unit** (Retro remains the **reference 1.0** convention unless measurement says otherwise).
- Align **`model_viewer_kenney`**, **`model_assembler_kenney`**, and **game-time prefab instantiation** (`ursina_renderer` / shared helper) so the same scale policy applies in tools and in-game (document the single source of truth).
- **Agent 15** revisits existing shipped prefabs after defaults land; tweak **per-piece `scale` in JSON** only where needed for silhouette, not sim footprints.

### A.3 Part A — out of scope

- **Prefab baker** — only if Agent 10 proves JSON prefab path cannot hit budget after reasonable fixes; then PM opens a follow-up baker sprint (do not start baker in parallel without PM decision).
- **`config.py` footprint edits** — still forbidden; fix visuals via prefab scale/geometry only.
- **CHANGELOG / version bump** — unless Jaimie requests.

### A.4 Part A — Definition of Done

- [ ] Agent 10 log: baseline numbers + post-fix numbers + short hotspot/mitigation narrative.
- [ ] Agent 03 log: list of code changes tied to Agent 10 findings; determinism + smoke green.
- [ ] Agent 12 log: documented pack scale table + where it is applied (viewer / assembler / runtime).
- [ ] Agent 15: at least one pass on existing prefabs for obvious gaps after scale defaults (note in log).
- [ ] Agent 09: short cohesion note (walls readable, packs don’t fight each other).
- [ ] `python tools/qa_smoke.py --quick` **PASS**; `python tools/validate_assets.py --report` **exit 0** (warnings acceptable if pre-existing).

### A.5 Part A — related code/docs

- `.cursor/plans/wk30_buildings_pipeline.plan.md` — prior prefab pipeline sprint.
- `.cursor/plans/kenney_gltf_ursina_integration_guide.md` — shader classifier (unchanged unless Agent 03 must relocate helpers).
- `tools/model_viewer_kenney.py` — `_fit_uniform_and_ground`, grid placement.
- `tools/model_assembler_kenney.py` — piece spawn, saved `scale` in JSON.
- `assets/prefabs/schema.md` — prefab JSON contract.

---

## Part B — Economy & Living Buildings (Phase 2.2)

### B.1 Objective

Extend the WK30 default-on prefab renderer to the **economy / living** building family. No new renderer work should be required — Agent 03's generalized loader handles any building type with a present `<building_type>_v1.json`. The work is mostly **Agent 15 + Jaimie** at the assembler, with Agents **05 / 09 / 10 / 11 / 12** on consult / light lifting.

**Open Part B only after Part A is green** (or PM explicitly parallelizes with scope control).

Target buildings (Jaimie 2026-04-16):

1. **Inn** (`inn`)
2. **Farm** (`farm`)
3. **Food Stand** (`food_stand`)
4. **Gnome Hovel** (`gnome_hovel`) — racial housing, Majesty-style

**Out of scope for Part B** (roll to a later sprint): Marketplace, Blacksmith, Trading Post, Temples, Library, Royal Gardens, Palace, enemy lairs (goblin_camp / wolf_den / skeleton_crypt / spider_nest / bandit_camp), defensive towers, Elven Bungalow, Dwarven Settlement, Fairgrounds.

### B.2 Part B — non-goals

- Do **not** edit `config.py` footprints. Shrink prefabs to fit, not the other way round.
- Do **not** touch animated units / rigs. Phase 3 territory.
- Do **not** build a prefab baker UNLESS WK30 §7 / Part A conclusion says JSON path is exhausted (then PM opens a **baker sprint** instead of pushing more prefab JSON).
- Do **not** bump the CHANGELOG.

### B.3 Part B — agent roster (draft)

| Agent | Role | Status | Intelligence |
|------|------|--------|----------------|
| 01 PM | Coordinates, prompts, closeout | active | — |
| 15 ModelAssembler | Kitbash 4 economy prefabs with Jaimie | active | **high** |
| 12 ToolsDevEx | Add 4 entries to `tools/assets_manifest.json` `prefabs.buildings` | active | **low** |
| 05 GameplaySystems | Footprint audit for 4 buildings; no `config.py` edits | consult | **low** |
| 09 ArtDirector | Silhouette / palette; economy reads “civic / humble” vs guild “military” | consult | **low** |
| 10 PerformanceStability | Full-kingdom FPS with ~10 buildings; baker decision if needed | consult | **medium** |
| 11 QA | Post-merge `qa_smoke --quick` | consult | **low** |
| 03 TechDir | Silent unless loader needs adjustment for new types | usually silent | — |
| 02, 04, 06, 07, 08, 13, 14 | Silent | silent | — |

### B.4 Part B — deliverables

#### Prefabs (Agent 15 + Jaimie)

- `assets/prefabs/buildings/inn_v1.json` — `building_type: "inn"`, <=14 pieces. Warm, larger than peasant house; chimney motif helpful. Likely Retro Fantasy + Nature accent.
- `assets/prefabs/buildings/farm_v1.json` — `building_type: "farm"`, <=10 pieces. Low barn + fence / field; Nature Kit props encouraged.
- `assets/prefabs/buildings/food_stand_v1.json` — `building_type: "food_stand"`, <=6 pieces. Smallest building; tight piece count; market awning silhouette.
- `assets/prefabs/buildings/gnome_hovel_v1.json` — `building_type: "gnome_hovel"`, <=10 pieces. Squat, mushroom-ish / fairy-tale; distinct from peasant house.

Every prefab: `footprint_tiles` matches `config.py` exactly, `ground_anchor_y = 0.0`, `attribution[]` complete, `--open <id>` round-trip.

#### Manifest (Agent 12)

Add required entries `inn_v1`, `farm_v1`, `food_stand_v1`, `gnome_hovel_v1` under `prefabs.buildings`. Validator from WK30-FEAT-004 should apply without new code.

#### Footprint audit (Agent 05)

Four new rows: `inn | farm | food_stand | gnome_hovel`. Flag mismatches to Agent 15 for shrink.

#### FPS at kingdom scale (Agent 10)

With castle + house + guilds + 4 economy buildings visible, confirm JSON prefab path still meets budget vs Part A baseline.

**Decision rule:**

- FPS within ~30% of acceptable Part A baseline → keep JSON prefabs; continue building library on this path.
- Worse → PM opens **baker sprint** (Agent 12: `tools/bake_prefab.py`; Agent 03: baked-first resolution in renderer).

### B.5 Part B — Definition of Done

- [ ] Four new economy prefab JSONs exist and round-trip via assembler.
- [ ] `tools/assets_manifest.json` updated; `python tools/validate_assets.py --report` exit 0.
- [ ] Footprint audit logged by Agent 05; no `config.py` edits.
- [ ] Human playtest: all four render by default in Ursina; no regression to WK30/WK31 Part A buildings.
- [ ] Agent 10 FPS / baker decision recorded.
- [ ] `python tools/qa_smoke.py --quick` PASS.

### B.6 Part B — when to activate in the PM hub

Add a new round (e.g. `wk31_r2_economy` or `wk32_r1_economy`) **after** Part A gates are green and WK30 is closed green. If a **baker sprint** is required first, PM defers Part B until after that sprint.

### B.7 Part B — related docs

- `.cursor/plans/wk30_buildings_pipeline.plan.md` — military district prefabs.
- `.cursor/plans/master_plan_3d_graphics_v1_5.md` — Phase 2 roadmap.
- `assets/prefabs/schema.md` — prefab JSON contract.

---

## Combined checklist (both parts)

**Part A:** perf baseline + fixes; pack scale tooling; existing prefab touch-ups; gates PASS.  
**Part B:** four economy prefabs; manifest; audit; playtest; FPS/baker decision; gates PASS.
