## Status (as of `wk3_r10_major_graphics_execution`)

- **Milestone 0 (style lock)**: **DONE**
- Style addendum: `docs/art/wk3_major_graphics_target.md`
- **Milestone 5 (snapshot gate)**: **DONE**
- Locked baseline (do not overwrite): `docs/screenshots/wk3_baseline_v2/`
- Rolling “after” set (overwrite each PR): `docs/screenshots/wk3_baseline_v2_next/`
- Compare gallery: `docs/art/compare_gallery.html`
- Tooling notes:
  - `tools/capture_screenshots.py` manifest is deterministic across machines (no absolute paths; `schema_version: 1.1`)
  - Capture tool resets selection/UI state per shot to avoid cross-shot contamination
- **Milestone 1 (terrain)**: **ADVANCED (first readability pass shipped)**
- Code: `game/graphics/tile_sprites.py` (6 grass variants, 6 path variants w/ border, 4 tree variants + subtle shadow)
- DoD shots to review (rolling “after”):
  - `docs/screenshots/wk3_baseline_v2_next/base_overview_seed3/base_overview__Z1__world_clean.png`
  - `docs/screenshots/wk3_baseline_v2_next/base_overview_seed3/base_overview__Z2__world_clean.png`
- **Milestone 4 (UI skin)**: **DONE (code-only step 1 shipped)**
- Code: `game/ui/widgets.py`, `game/ui/hud.py`, `game/ui/debug_panel.py`
- DoD shots to review (rolling “after”):
  - `docs/screenshots/wk3_baseline_v2_next/ui_panels_seed3/ui_panels_hero.png`
  - `docs/screenshots/wk3_baseline_v2_next/ui_panels_seed3/ui_panels_debug.png`

## Where to review

- **Compare gallery**: `docs/art/compare_gallery.html`
- **Locked baseline shots**: `docs/screenshots/wk3_baseline_v2/`
- **Rolling “after” shots**: `docs/screenshots/wk3_baseline_v2_next/`

## Baseline problems (what we must fix)

- **World looks like debug prototype**: flat grass + sparse trees, no landmark composition.
- **Buildings/enemies are placeholders**: silhouettes don’t read; everything feels samey.
- **Readability gap vs references** in `.cursor/plans/art_examples`:
- refs use stronger **material/value contrast**, **lighting/shadows**, **dense landmark clusters**, and **consistent silhouettes**.

## Style contract (must lock first)

Use these existing docs as the contract source of truth:

- `docs/art/pixel_style_guide.md` (light direction, outlines, palette ramps)
- `docs/art/animation_vfx_guidelines.md` (folder/actions/states)
- `docs/art/placeholder_sprite_briefs.md` (ready-to-draw briefs)

Add a short addendum (“WK3 Major Graphics Target”) with:

- **Lighting**: top-left, consistent shadow color + opacity
- **Outline thickness**: 1px, selective outline on light-facing edges
- **Scale**: 32px tiles; units 32x32; buildings are tile multiples; define “gameplay zoom”
- **Noise budget**: terrain low-noise; buildings medium; units low; UI clean

## Execution checklist (milestone-based)

### Milestone 0 — Style lock (gfx-0-style-lock)

**Owner(s)**: Art + UI (Agents 09 + 08)

Deliverables:

- 1-page addendum doc with the locked style target (above bullets).
- A small “golden palette” swatch list (as hex) for: grass, path, shadow, outline, UI panel bg.

DoD (snapshot-based):

- Team agrees on a single target look based on `docs/art/compare_gallery.html` refs.

### Milestone 1 — Terrain readability pass (gfx-1-terrain)

**Owner(s)**: Art (09) + Perf consult (10)

Scope:

- Grass tile set: 3–6 deterministic variants.
- Path tile set: straights/corners/T-junction/cross + edge definition.
- Props: 3–6 small set (rocks/shrubs/stumps), deterministic placement optional.
- Trees: at least 3 variants, reduce “copy-paste” feel.

DoD (shots):

- `base_overview__Z1__world_clean.png` reads as a believable world (not debug fill).
- `base_overview__Z2__world_clean.png` has clear path edges and less speckle noise.

### Milestone 2 — Tier-1 buildings (gfx-2-buildings-tier1)

**Owner(s)**: Art (09)

Tier-1 list:

- `castle`, `marketplace`, `inn`, `blacksmith`, `guardhouse`, `house`, `farm`, `food_stand`

For each building type, ship:

- `built`, `construction`, `damaged`

DoD (shots):

- In `building_catalog_seed3/`, each Tier-1 closeup is instantly distinguishable:
- `building_castle_closeup.png` (landmark)
- `building_marketplace_closeup.png`, `building_inn_closeup.png`, etc.
- “construction” reads as construction without losing silhouette.
- “damaged” reads as damaged without becoming noise soup.

### Milestone 3 — Core enemies (gfx-3-enemies-core)

**Owner(s)**: Art (09)

Enemy set:

- `goblin`, `wolf`, `skeleton`, `spider`, `bandit`

For each enemy type, ship actions:

- `idle`, `walk`, `attack`, `hurt`, `dead`

DoD (shots):

- In `enemy_catalog_seed3/`, each closeup reads by silhouette/value alone:
- `enemy_goblin_closeup.png`, `enemy_wolf_closeup.png`, etc.
- Dead pose is obviously dead at gameplay zoom.

### Milestone 4 — UI skin pass (gfx-4-ui-skin)

**Owner(s)**: UI (08) + Art direction (09) + Perf consult (10)

Scope:

- Replace flat debug panels with themed 9-slice frames and consistent button styling.
- Keep readability first; no layout regressions.

DoD (shots):

- `ui_panels_debug.png` and `ui_panels_hero.png` read as “game UI”, not “dev overlay”.
- UI does not dominate the playfield at 1080p (panel ratios feel intentional).

### Milestone 5 — Snapshot review gate (gfx-5-snapshot-gate)

**Owner(s)**: Tools (12) + QA (11)

Process:

- Every art PR updates snapshots + gallery:
- `python tools/capture_screenshots.py ...`
- `python tools/build_gallery.py ...`
- add a short notes section (top 5 deltas vs refs).

DoD:

- Reviewers can open `docs/art/compare_gallery.html` and see “before vs after” progress with deterministic filenames/manifests.

## Owners / roles (recommended)

- **Agent 09 (ArtDirector)**: Milestones 0–3 ownership; coordinates asset sourcing + originals; maintains cohesion.
- **Agent 08 (UX/UI)**: Milestone 0 + 4; ensures UI skin supports readability and doesn’t regress manageability.
- **Agent 12 (ToolsDevEx)**: Milestone 5; scenario + gallery upkeep; add any additional scenarios needed (tight base, hero lineup) once art starts landing.
- **Agent 10 (Performance)**: consult on caching + texture/noise budget; ensure no per-frame allocations creep in.