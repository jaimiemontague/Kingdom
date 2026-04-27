# Master Plan: 3D Graphics Integration (Target v1.5)

**Kenney glTF / Ursina integration (pitfalls, unlit vs PBR, baseColorFactor):** see [kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md). Apply those lessons when wiring `Entity(model=…)` and materials in `game/graphics/ursina_renderer.py`.

## 1. Mission Statement
> "Transition the Kingdom project to a fully 3D, low-poly stylized aesthetic suitable for a $15-$20 commercial Steam release. Emphasize visual cohesion, prioritize high-performance flat-shaded geometry over complex textures, and establish a scalable pipeline for importing static and animated 3D assets using Ursina."

**v1.5 release scope (locked as of 2026-04):** **v1.5 ships when Phase 1 and Phase 2 are complete** — static 3D environment, static kitbash buildings, and the prefab/loader stack are production-ready. **Phase 3 (animated 3D units) is optional:** it may land in a **1.5.x** patch or a **later** version, or never on a fixed schedule. Billboards (or the current unit presentation) can remain the shipping solution for v1.5 if animation work is deferred.

## 2. Versioning & Commit Protocol
* **Target Release Version:** **v1.5** = **3D static world + static buildings (Phase 1–2) stable**, not a hard dependency on Phase 3 animated units.
* **1.5.x (optional):** May include Phase 3 progress, more prefabs, perf, or art passes — TBD.
* **Commit Convention:** Commits for 3D milestone work use: `"3D Graphics Phase #.#: …"` (e.g. `3D Graphics Phase 2.5: …`) as milestones are hit.

## 3. Core Rules & Pipeline Overhaul
Before changing how meshes are loaded or shaded, read **[kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)** (defaults entity shader, `baseColorFactor`-only materials, why naive `setShaderAuto` breaks scenes).

Structural pipeline is owned by the Directors; **current shipped behavior** (2026) includes:

* **3D asset validation:** `tools/assets_manifest.json` and `tools/validate_assets.py` support **3D meshes** (`.glb` / `.gltf` / `.obj`) and texture file checks — extended across WK25+.
* **Renderer:** `game/graphics/ursina_renderer.py` drives a **3D Ursina** presentation: terrain floor, static props, fog-of-war, prefab building assembly, and **lair** environment meshes. Dynamic units may still use **billboards** until Phase 3; that does **not** block v1.5.
* **Scale & collision:** `config.py` `footprint_tiles` is authoritative; prefabs and lairs are reconciled to it (Agent 05 audits; Agent 15 adjusts prefab JSON, not sim sizes without PM).

**Standards added after the first Phase 2 sprints (use on every new prefab or kit work):**

| Standard | Where | Purpose |
|--------|--------|--------|
| **Prefab texture override** | [prefab_texture_override_standard.md](./prefab_texture_override_standard.md) | Flat Fantasy Town / Graveyard / Survival pieces get **in-repo `texture_override` PNGs** and runtime path in `game/graphics/prefab_texture_overrides.py` — do not edit Kenney GLBs. |
| **Kit screenshot review (first)** | `assets/models/*Kit*.PNG` etc. (list in §4 Phase 2 below) | **Before** kitbashing, review the pack sheet PNGs so piece picks match silhouette and art direction. |
| **Model assembler** | `tools/model_assembler_kenney.py` | 1×1 grid placement, rotate, nudge, **per-piece scale** (**`-` / `=`** to shrink/grow, **Shift** = finer step), save prefab JSON; logical `scale` stays in JSON, pack extent multiplier applied at runtime only. |
| **Model viewer** | `tools/model_viewer_kenney.py` | Debug materials, **focus-prefab**, optional screenshots for review loops — iterate with the texture-override standard. |

## 4. Implementation Phases (High-Level Roadmap)
Phases stay sequential for **static** work. **Do not block shipping v1.5 on animated units.**

### Phase 1: Static Environments & Asset Pipeline Foundations
* **Goal:** 3D tooling, rules, and static environment (ground, props, basic lighting) before complex buildings and **before** animated units.
* **Lighting/Shaders:** **Agent 09** — Ursina basic lighting and flat shading; follow **[kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)** for factor-only and vertex-colored assets.

**Shipped in practice (incl. WK25–26, WK32, WK33):** Base **green/plane** evolved to **tiled grass albedo** (`floor_ground_grass.png` and tuning); **3D path/water/terrain** integration; **scatter** (grass clumps, trees, rocks) with **deterministic** placement; **3D fog-of-war** with explored vs unseen behavior; **camera** controls suitable for play; **performance** work so meadow + heroes stay playable. Asset manifest/validator understand **environment** and **prefab** entries.

**Original sprint labels (for history):** 1.1 tooling/rules, 1.2 base terrain, 1.3 static props.

**Success Criteria (met for v1.5 static env path):** `qa_smoke.py --quick` and `validate_assets.py --report` pass; Ursina shows 3D ground and static environmental props at acceptable FPS; no reliance on 2D **environment** billboards for shipped biomes.

> **Jaimie — quick visual pass (`python main.py --renderer ursina --no-llm`):** Ground reads continuous (tiled albedo, no huge seams); trees/rocks are 3D props, not rotating billboards; no pink/black checkers; FPS acceptable when panning the meadow.

### Phase 2: Static Buildings & Grid Alignment
* **Goal:** Static buildings in the new layout; **kitbash prefab JSON** + loader; scaling matches **grid footprints**.

#### Pipeline pivot (as of 2026-04-16) — current

The original “one `.glb` per building in `assets/models/environment/`” approach is **deprecated** for most buildings. Kingdom uses **kitbash-and-load**:

1. **Pieces** — Kenney pieces under `assets/models/Models/…`. See [kenney_assets_models_mapping.plan.md](./kenney_assets_models_mapping.plan.md).
2. **Assembler** — `tools/model_assembler_kenney.py` (**Agent 12 / 15**). Human kitbashes on a grid; **placement fine-tuning**, **per-piece scale nudge** (`-` / `=`, Shift fine) — see sprint notes WK33 midsprint. Saves **`assets/prefabs/buildings/<prefab_id>.json`**.
3. **Prefab JSON** — [assets/prefabs/schema.md](../../assets/prefabs/schema.md): `footprint_tiles`, `pieces[]`, optional **`texture_override`** per piece.
4. **Loader** — `ursina_renderer.py` instantiates pieces; `tools.model_viewer_kenney._apply_gltf_color_and_shading` and texture override path must stay aligned.
5. **Footprint reconciliation** — match `config.py`; if visuals overshoot, **shrink the prefab**, not the sim.
6. **Required texture overrides** for flat town/graveyard/survival pieces — **[prefab_texture_override_standard.md](./prefab_texture_override_standard.md)** (PM-enforced; **Agent 15** onboarding).
7. **Screenshot / kit review first** — Before selecting pieces, review these pack overviews: `assets/models/Fantasy Town Kit.PNG`, `Graveyard Kit.PNG`, `Blocky Characters.PNG`, `Nature Part 1–4.PNG`, `Retro Fantasy Kit.PNG`, `Survival Kit.PNG` (and any new kit sheets added to `assets/models/`). **Tool-first proof:** `model_viewer_kenney.py` and assembler passes before calling a prefab “done”.

#### Status today (loader, perf, workflow) — supersedes WK29-only notes

- **Loader (post-WK30):** Prefabs are **default-on** when `assets/prefabs/buildings/<building_type>_v1.json` (or the project’s `_PREFAB_BUILDING_TYPE_TO_FILE` entry) exists. **`KINGDOM_URSINA_PREFAB_TEST=0`** forces the **legacy** billboard/primitive path for A/B or rollback; **unset or non-zero** uses prefabs. The WK29-era **“house only + require `=1`”** behavior is **historical** — see `wk30_buildings_pipeline.plan.md`.
- **First house:** `peasant_house_small_v1.json` remains the first end-to-end kitbash; same pipeline as castle, guilds, and economy buildings.
- **Perf:** After prefab scale-up, **Agent 10** has not treated **>30%** FPS regression from the prefab path as a release blocker; a **prefab baker** (JSON → single `.glb`) stays **backlog** until instance count / profiling demands it.
- **Each new building tranche:** (a) **Agent 15** + Jaimie kitbash in the assembler, (b) **Agent 03** extends loader / prefab map as needed, (c) **Agent 05** footprint audit, (d) **Agents 09 / 10 / 11** consult on cohesion, FPS, and gates.

#### Phase 2 sprint map (`3D Graphics Phase 2.#` — see `git log --grep="Phase 2"`)

Commits use the **`3D Graphics Phase 2.x: …`** convention. Rough mapping to studio weeks and **master-plan** labels:

| Phase | Sprint / window | What shipped (summary) | Plan / anchor |
|-------|------------------|-------------------------|----------------|
| **2.0** | WK28 → early assembly | Kenney **assembler + schema** mature; first building kitbashes underway | `wk28_assembler_spike_41c2daeb.plan.md`; `3ae0a34` |
| **2.1** | **WK30** | **Default-on** prefab loader (generalizes WK29); **castle + warrior / ranger / rogue** guild prefabs (wizard optional); manifest + `validate_assets` **prefabs.buildings** | `wk30_buildings_pipeline.plan.md` — **replaces deprecated** `wk27_sprint_2_1_buildings.plan.md`; `b51d679` |
| **2.2** | **WK31** + economy follow-on | **First half** of **economy / living** buildings into the game (Inn, Farm, Food Stand, Gnome Hovel, plots, etc. per PM order); overlaps **Part B** of perf + economy plan | `wk31_kingdom_perf_and_economy.plan.md` Part B; `cad0d71` |
| **2.3** | **WK32** | **3D camera**, **3D fog-of-war**, **Inn v2** / construction & nature polish, **hero-spawn FPS** mitigation | `wk32_camera_construction_nature_polish.plan.md`; `ba2b2c6` |
| **2.4** | Focused texture pass | **Food stand** (and related) **backfill** of **texture overrides** under [prefab_texture_override_standard.md](./prefab_texture_override_standard.md) | `ba9f40c` |
| **2.5** | **WK33** (+ midsprint) | **Tiled grass** albedo, **Graveyard lair** mesh, **marketplace / blacksmith / trading_post / farm** prefabs + **construction-stage** JSONs; **assembler** per-piece **`-` / `=`** scale (Shift fine) | `wk33_3d_sprint_plan_6e616891.plan.md`; `assembler_scale_hotkeys_177ca989.plan.md`; `f9e7dff` |

*Hash column in git history is the source of truth if two commits share the same phase number (e.g. a **2.2** midsprint save vs the main **2.2** economy tranche).*

**Sprint 2.X (perf hedge, on-demand):** **Agent 12** prefab **baker** only if **Agent 10** flags a regression at scale — not on the calendar by default.

**Milestones already demonstrated (roll-up):** Military district (**2.1**), economy/living first tranche (**2.2**), camera/FOW/Inn/perf (**2.3**), override standard applied to food stand (**2.4**), terrain + lair + core economy prefabs + assembler scale (**2.5**).

**Success Criteria (v1.5 bar for Phase 2):** Buildings and **lair** read as 3D kitbash where prefabbed; footprints match; textures/overrides and gates **PASS**; Jaimie playtest on Ursina.

> **Jaimie:** Kitbash with **Agent 15** (`python tools/model_assembler_kenney.py --open <prefab_id>`). In-game: **scale** vs trees, **ground line** (no float/sink), **clipping** (units path around walls, not through), **textured vs factor-only** looks intentional (overrides per standard).

### Phase 3: Animated Units (Entity Rigging) — **OPTIONAL; NOT REQUIRED FOR v1.5**
* **Goal:** If pursued: dynamic units in 3D with **Idle / Walk / Attack** (or equivalent) driven by sim state.
* **Scheduling:** **Not in the v1.5 milestone.** May appear in **1.5.x** or a later version; **PM decides** when to activate **Agent 03 / 09** for rigging. Until then, **Ursina can keep billboards (or current unit rendering)** for heroes/enemies/workers.

**Sprints outline (unchanged, only if Phase 3 is greenlit):** 3.1 animation framework in `ursina_renderer.py`; 3.2 workers; 3.3 heroes; 3.4 enemies.

**Success Criteria (if Phase 3 runs):** Billboard path removable or feature-flagged for units that have 3D; animation state matches sim; **qa_smoke** passes.

> **Jaimie (only if Phase 3 starts):** Pick character `.gltf` names; playtest walk/attack/camera-facing.

### Phase 4: Polish, Lighting, & Release Packaging
* **Goal:** For **v1.5 ship**: final passes on what Phase 1–2 already use — lighting feel, FOW, construction/build feedback, **perf**, CHANGELOG, store-facing readiness. If Phase 3 is skipped, this phase is **“make static 3D shippable and wow enough”**, not “wait for rigs.”

**Typical tranches (order flexible):** lighting & atmosphere; **VFX** where render-only and cheap; **Agent 10** FPS passes and perf knobs; remove confusion from obsolete 2D docs if any; optional **prefab baker** (Agent 12) **only** if instancing cost demands it.

**Success Criteria:** Playtester signoff; FOW and perf acceptable on target hardware; version and **CHANGELOG** updated when Jaimie cuts the release.

> **Jaimie:** `python main.py --renderer ursina` — lighting feels cohesive; FOW hides what it should; zoomed-out FPS is playable; first-impression “Steam $15” vibe, or a short list of what still janks.

## 5. Changelog
Update **`CHANGELOG.md`** when Jaimie bumps the version; this master plan is the **roadmap**, not the patch-notes source.

## 6. See Also
- [kenney_gltf_ursina_integration_guide.md](./kenney_gltf_ursina_integration_guide.md)
- [prefab_texture_override_standard.md](./prefab_texture_override_standard.md)
- Phase 2 sprints: [wk30_buildings_pipeline.plan.md](./wk30_buildings_pipeline.plan.md) (2.1), [wk31_kingdom_perf_and_economy.plan.md](./wk31_kingdom_perf_and_economy.plan.md) (2.2 Part A/B), [wk32_camera_construction_nature_polish.plan.md](./wk32_camera_construction_nature_polish.plan.md) (2.3), [wk33_3d_sprint_plan_6e616891.plan.md](./wk33_3d_sprint_plan_6e616891.plan.md) (2.5), [assembler_scale_hotkeys_177ca989.plan.md](./assembler_scale_hotkeys_177ca989.plan.md) (2.5 midsprint)
- `assets/prefabs/schema.md`
