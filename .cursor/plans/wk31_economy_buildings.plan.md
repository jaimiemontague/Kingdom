# WK31 Sprint — Economy & Living Buildings (Phase 2.2) — SKELETON

> **Status: SKELETON / not yet active.** Opens only after WK30 closes green. Held here so the roadmap is visible but no agents are being activated yet.
>
> If Agent 10 flags a >30% FPS regression at the end of WK30, this sprint is **bumped** in favor of a perf-hedge sprint (Agent 12 writes `tools/bake_prefab.py`; Agent 03 adds a "baked-first, JSON-second" resolution). See WK30 plan §7 decision gate.

Sprint label: `wk31-economy-buildings`
Plan file: `.cursor/plans/wk31_economy_buildings.plan.md`
Depends on: `wk30-buildings-pipeline` (closed green).

## 1. Objective

Extend the WK30 default-on prefab renderer to the **economy / living** building family. No new renderer work should be required — Agent 03's generalized loader handles any building type with a present `<building_type>_v1.json`. The sprint is almost entirely Agent 15 + Jaimie at the assembler, with Agents 05 / 09 / 10 / 11 / 12 on consult / light lifting.

Target buildings (exactly what Jaimie called out 2026-04-16):

1. **Inn** (`inn`)
2. **Farm** (`farm`)
3. **Food Stand** (`food_stand`)
4. **Gnome Hovel** (`gnome_hovel`) — racial housing, Majesty-style

**Out of scope for WK31** (roll to WK32+): Marketplace, Blacksmith, Trading Post, Temples, Library, Royal Gardens, Palace, enemy lairs (goblin_camp / wolf_den / skeleton_crypt / spider_nest / bandit_camp), defensive towers, Elven Bungalow, Dwarven Settlement, Fairgrounds.

## 2. Non-goals

- Do **not** edit `config.py` footprints. Shrink prefabs to fit, not the other way round.
- Do **not** touch animated units / rigs. Phase 3 territory.
- Do **not** build a prefab baker UNLESS WK30 §7 row 2 triggered (then this sprint becomes the baker sprint instead).
- Do **not** bump the CHANGELOG.

## 3. Agent roster for this sprint (draft)

| Agent | Role in sprint | Status | Intelligence |
|---|---|---|---|
| 01 PM | Coordinates, writes prompts, tracks, closes sprint. | active | — |
| 15 ModelAssembler | Kitbashes 4 economy prefabs with Jaimie. | active | **high** |
| 12 ToolsDevEx | Adds 4 new entries to `tools/assets_manifest.json` (no new code usually needed). | active | **low** |
| 05 GameplaySystems | Footprint audit for 4 new buildings; no config.py edits. | consult | **low** |
| 09 ArtDirector | Silhouette / palette cohesion review; ensure economy buildings read as "civic / humble" vs guild "military". | consult | **low** |
| 10 PerformanceStability | Full-kingdom FPS with ~10 buildings in view; decide if baker is now needed. | consult | **medium** |
| 11 QA | Post-merge `qa_smoke --quick`. | consult | **low** |
| 03 TechDir | **Usually silent.** Only activated if the generalized loader needs any adjustment for the new types (unlikely). | silent | — |
| 02, 04, 06, 07, 08, 13, 14 | Silent. | silent | — |

## 4. Deliverables (outline — full spec written when sprint opens)

### 4.1 Prefabs (Agent 15 + Jaimie)

- `assets/prefabs/buildings/inn_v1.json` — `building_type: "inn"`, <=14 pieces. Silhouette: warm, larger than a peasant house, chimney motif helpful. Likely Retro Fantasy Kit with Nature Kit accent.
- `assets/prefabs/buildings/farm_v1.json` — `building_type: "farm"`, <=10 pieces. Silhouette: low barn + fence / field accents. Nature Kit props encouraged.
- `assets/prefabs/buildings/food_stand_v1.json` — `building_type: "food_stand"`, <=6 pieces. Small, market-style awning silhouette. This is the smallest building in the game; keep piece count tight.
- `assets/prefabs/buildings/gnome_hovel_v1.json` — `building_type: "gnome_hovel"`, <=10 pieces. Silhouette: squat and mushroom-ish / fairy-tale. Distinct from peasant house.

Every prefab: `footprint_tiles` matches `config.py` exactly, `ground_anchor_y = 0.0`, `attribution[]` complete, `--open <id>` round-trip.

### 4.2 Manifest updates (Agent 12)

Add 4 required entries (`inn_v1`, `farm_v1`, `food_stand_v1`, `gnome_hovel_v1`) to `tools/assets_manifest.json` `prefabs.buildings`. No code changes expected; the validator logic from WK30-FEAT-004 covers these automatically.

### 4.3 Footprint audit (Agent 05)

Extend the WK30 audit log with 4 new rows: `inn | farm | food_stand | gnome_hovel`. Flag mismatches to Agent 15 for shrink.

### 4.4 FPS sanity at scale (Agent 10)

WK31 is the first sprint with a full visible kingdom (~10 prefab buildings: castle + house + 3 guilds + 4 economy + potentially Wizard Guild if it carried over). This is the moment to either clear the prefab JSON approach for the rest of the building library, or trigger the baker.

Decision rule:
- FPS within ~30% of WK30 average → keep JSON-prefab path; open WK32 for the next building batch.
- FPS worse than that → open WK32 as the **baker sprint** (Agent 12 writes `tools/bake_prefab.py`, Agent 03 teaches the renderer to prefer a baked `.glb` when present).

## 5. Definition of Done (draft)

- [ ] 4 new economy prefab JSONs exist and round-trip via the assembler.
- [ ] `tools/assets_manifest.json` updated; `python tools/validate_assets.py --report` exit 0.
- [ ] Footprint audit logged by Agent 05; no `config.py` edits.
- [ ] Human playtest: all 4 new buildings render by default in Ursina; no regression to WK30 buildings.
- [ ] Agent 10 FPS decision recorded (continue or trigger baker).
- [ ] `python tools/qa_smoke.py --quick` PASS.

## 6. When to open this sprint

Open this sprint in a new round on the PM hub (`wk31_r1_execution`) **only after** `wk30_r2_close` is written and shows all gates green AND Agent 10's WK30 FPS check is PASS. If Agent 10's FPS check flagged a regression, scrap this plan in favor of the baker sprint (create `.cursor/plans/wk31_prefab_baker.plan.md` instead).

## 7. Related docs

- [.cursor/plans/wk30_buildings_pipeline.plan.md](./wk30_buildings_pipeline.plan.md) — prior sprint (military district).
- [.cursor/plans/master_plan_3d_graphics_v1_5.md](./master_plan_3d_graphics_v1_5.md) — Phase 2 roadmap with Pipeline pivot subsection.
- [assets/prefabs/schema.md](../../assets/prefabs/schema.md) — prefab JSON contract.
