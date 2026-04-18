---
name: ""
overview: ""
todos: []
isProject: false
---

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

**Reference doc (read before touching assets):** [.cursor/plans/kenney_assets_models_mapping.plan.md](./kenney_assets_models_mapping.plan.md) — merged paths, **Fantasy Town Kit** (`*-fantasy-town.glb`) and **Graveyard Kit** (`*-graveyard.glb`) as the two packs added between sprints, filename suffixes, and per-pack wall/fence families.

#### A.2.1 Agent 12 (tooling)

- Introduce **pack-aware defaults**: per top-level folder or per-pack multiplier so new pieces spawn closer to a **shared grid unit** (**Retro Fantasy Kit** remains the **reference 1.0** convention for calibration unless measurement proves otherwise).
- Align **`model_viewer_kenney`**, **`model_assembler_kenney`**, and **game-time prefab instantiation** (`ursina_renderer` / shared helper) so the same scale policy applies in tools and in-game (document the **single source of truth**).
- **Consume Agent 15’s empirical results:** where wall/fence flush passes prove a stable multiplier per pack (or per filename pattern), encode that in data or code so future pieces inherit it without repeating the full manual pass.

#### A.2.2 Agent 15 — exhaustive wall & fence flush pass (non-Retro packs)

**Scope — packs to treat (Retro explicitly out of scope for this pass):**

| Pack | Merged location (typical) | Notes |
|------|---------------------------|--------|
| **Survival Kit** | `assets/models/Models/GLB format/*.glb` (no suffix) | Fewer modular walls than FT; still scan for anything that reads as **wall / fence / barrier** used in kitbash. |
| **Nature Kit** | `assets/models/Models/GLTF format/*.glb` | Factor-only materials; walls may be `stone_*`, `rock_*`, hedges, or path edges — include pieces intended to **tile or abut** in rows. |
| **Fantasy Town Kit** | `*-fantasy-town.glb` | **New pack (WK31).** Rich **wall-***, **fence-***, road-edge, hedge, and masonry sets — see mapping doc §2 *Fantasy Town Kit*. |
| **Graveyard Kit** | `*-graveyard.glb` | **New pack (WK31).** **brick-wall-***, **stone-wall-***, **fence-***, **iron-fence-*** variants — see mapping doc §2 *Graveyard Kit*. |
| **Blocky Characters** | `character-*.glb` | **Skip** for this pass unless a piece is clearly used as a modular wall (normally N/A). |

Do **not** spend this pass re-proving Retro; use Retro only as a **visual reference** for what “flush” means when two copies sit side by side.

**Where to work (“in game”):**

- Primary acceptance is **in Ursina** so lighting and shaders match shipping: run **`python main.py --renderer ursina`** (or the project’s standard Ursina entry) and place pieces in a **minimal test layout** (empty meadow / dev scenario). If the live sim cannot place arbitrary GLBs without code support, **coordinate with Agent 03** to add a **temporary** dev-only spawn, test map, or reuse the **model assembler** as the same renderer path — the plan still requires **side-by-side duplicates** under real game conditions before marking a model “done.”
- Use a **consistent camera** for before/after comparison (same zoom, same angle per model family). **F12** or the project screenshot tool if available.

**Per-model loop (repeat until the pack’s wall/fence set is done):**

1. **Pick one model file** (e.g. `wall-door-fantasy-town.glb`, `iron-fence-border-graveyard.glb`, a Nature `stone_wall_*` candidate). Build a short **inventory per pack** first (walls, fences, iron fences, brick/stone walls, gates that are meant to chain) so nothing is skipped; the mapping doc lists many FT/Graveyard names to seed the list.
2. **Place at least two instances of the exact same asset** along a straight line — **side by side** in world space (same `rot_y` unless the piece is designed for 90° junctions; document if a piece is **corner-only** or **segment-only** and cannot flush on a straight run).
3. **Capture screenshots** showing whether edges meet **flush** (no crack, no overlap, acceptable vertical alignment) vs **gaps** or **penetration**.
4. **Analyze** the screenshot: decide whether the fix is **uniform scale**, **non-uniform scale**, **rotation** (e.g. 90°), **positional nudge** along X/Z, or a **pack default** that Agent 12 should own.
5. **Apply adjustments** (prefab JSON per-piece fields, assembler default, or pack multiplier — per coordination with Agent 12), then **re-run step 2–3** with new screenshots.
6. **Loop** until two copies are **acceptably flush** with each other for that model; only then move to the **next** wall/fence model.
7. **Repeat the full loop** for every relevant model in the pack until that pack is fully sized/tuned for modular alignment.

**Expectations:**

- This is intentionally **long and exhaustive** — it may require **multiple work sessions** or PM follow-up rounds. **Checkpoint by pack** (e.g. Survival + Nature milestones, then Fantasy Town, then Graveyard) and log progress in **Agent 15’s hub log** so work can pause/resume without losing the inventory.
- Some meshes are **not meant** to tile edge-to-edge (decorative props, broken walls). Log **N/A with reason** instead of forcing flush.

**Deliverables (Agent 15):**

- Per-pack subsection in the agent log: **model path → flush OK / N/A → iterations → final scale/rot/pos notes → screenshot filenames or folder**.
- After Agent 12 lands defaults, **revisit shipped building prefabs** that use non-Retro pieces; tweak **per-piece `scale` / `pos` / `rot` in JSON** only where needed for silhouette and flush, **not** `config.py` footprints.

#### A.2.3 Part A — coordination

- **Agent 09** reviews readability after major pack milestones (optional mid-pass), not only at the end.
- **Agent 03** unblocks **in-game placement** if the sim cannot currently instantiate arbitrary test meshes.

### A.3 Part A — out of scope

- **Prefab baker** — only if Agent 10 proves JSON prefab path cannot hit budget after reasonable fixes; then PM opens a follow-up baker sprint (do not start baker in parallel without PM decision).
- **`config.py` footprint edits** — still forbidden; fix visuals via prefab scale/geometry only.
- **CHANGELOG / version bump** — unless Jaimie requests.

### A.4 Part A — Definition of Done

- [ ] Agent 10 log: baseline numbers + post-fix numbers + short hotspot/mitigation narrative.
- [ ] Agent 03 log: list of code changes tied to Agent 10 findings; determinism + smoke green; note any dev-only test hooks added for Agent 15’s in-game wall/fence pass.
- [ ] Agent 12 log: documented pack scale table + where it is applied (viewer / assembler / runtime); how Agent 15’s flush findings map into defaults.
- [ ] Agent 15 log: **wall/fence flush pass** — per-pack inventory of non-Retro wall/fence candidates; for each model worked: side-by-side Ursina evidence (screenshots), iteration count, final alignment approach (scale/rot/nudge/pack default), N/A entries with reasons; checkpoint milestones; then **shipped prefab touch-up** after defaults land.
- [ ] Agent 09: short cohesion note (walls readable, packs don’t fight each other); optional mid-pass if requested.
- [ ] `python tools/qa_smoke.py --quick` **PASS**; `python tools/validate_assets.py --report` **exit 0** (warnings acceptable if pre-existing).

### A.5 Part A — related code/docs

- `.cursor/plans/kenney_assets_models_mapping.plan.md` — **required** for pack locations, **Fantasy Town** / **Graveyard** suffixes, and wall/fence naming inventory seeds.
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

**Part A:** perf baseline + fixes; pack scale tooling; Agent 15 **non-Retro wall/fence flush pass** (exhaustive, screenshot-driven, per mapping doc + new FT/Graveyard packs); shipped prefab touch-ups; gates PASS.  
**Part B:** four economy prefabs; manifest; audit; playtest; FPS/baker decision; gates PASS.