# Visual Snapshot System — Shot List + Evaluation Rubric (WK3 prototype)

This document defines what the screenshot scenarios must capture and what we evaluate against the reference folder:
` .cursor/plans/art_examples `

## Global capture standards (deterministic)
- **Resolution**: `1920x1080` (or the size passed to the tool); always record actual size in manifest.
- **Zoom**: use a small fixed set:
  - **Z1**: overview (shows layout readability; target ~40–60 tiles across screen width)
  - **Z2**: gameplay default (target ~25–35 tiles across)
  - **Z3**: close-up (target ~14–20 tiles across; used for per-entity crops)
- **UI layers**:
  - **world_clean**: UI hidden (for composition, terrain, silhouettes)
  - **ui_default**: standard HUD visible
  - **ui_right_panel**: right info panel visible (selected hero/building)
  - **ui_debug**: debug/perf panels visible (debug-only)
- **Stabilization**: advance sim by ticks (e.g., 240 ticks) before capture so animations settle and pathing/VFX state is consistent.

## Must-capture scenarios (initial set)
Tools module names in parentheses are suggested scenario IDs for `tools/screenshot_scenarios.py`.

### 1) Base overview (base_overview)
**Purpose**: Compare “Majesty-like town readability” and overall composition vs references.

Capture:
- `base_overview__Z1__world_clean.png`
- `base_overview__Z1__ui_default.png`

Scene setup:
- Castle in center.
- Place: `marketplace`, `warrior_guild`, `blacksmith`, `inn`, `guardhouse`, `house`, `farm`.
- Add a couple roads/paths if the sim supports it (otherwise rely on existing path tiles).

What “good” looks like:
- Town reads as a **cluster** with clear landmarks (castle, marketplace).
- Buildings are distinguishable at a glance (silhouette/roof color separation).
- UI does not cover the “interesting” playfield center.

### 2) Tight base density (tight_base)
**Purpose**: Compare to “nice tight base” style reference; ensure density still reads.

Capture:
- `tight_base__Z2__world_clean.png`
- `tight_base__Z2__ui_default.png`

Scene setup:
- Arrange 10–14 buildings within a compact radius around castle (2–3 tile gaps max).

Evaluate:
- No “visual mush”: roofs/outlines still separate.
- Path readability doesn’t vanish under dense placement.

### 3) Building catalog grid (building_catalog)
**Purpose**: Verify every building type renders and compare proportional scale/footprint.

Capture:
- `building_catalog__Z1__world_clean.png` (whole grid)
- Per-building close-up crops (Z3): one image per type:
  - `building__<type>__built__Z3.png`
  - `building__<type>__construction__Z3.png`
  - `building__<type>__damaged__Z3.png`

Scene setup:
- Place each `tools/assets_manifest.json:buildings.types` in a grid with padding (at least 1 tile gap).
- Ensure each building can be rendered in each state (if state is simulated, force state flags for capture).

Evaluate:
- Footprints match expected sizes (1x1, 2x2, 3x3).
- Construction/damaged are readable variants (even if initially placeholders).

### 4) Hero lineup (hero_lineup)
**Purpose**: Verify hero silhouettes/colors read and compare class identity vs references.

Capture:
- `hero_lineup__Z3__world_clean.png`
- `hero_lineup__Z3__ui_right_panel.png` (select one hero)

Scene setup:
- Spawn 1 of each: `warrior`, `ranger`, `rogue`, `wizard` standing on path/grass.

Evaluate:
- Class identity reads in 1 second (accent + silhouette).
- Outlines are consistent; no blur/jaggies from scaling.

### 5) Enemy catalog (enemy_catalog)
**Purpose**: Verify enemy silhouettes + “threat readability.”

Capture:
- Per-enemy close-ups (Z3), one per type from `tools/assets_manifest.json:enemies.types`:
  - `enemy__<type>__idle__Z3.png`
  - `enemy__<type>__attack__Z3.png` (can be placeholder)
  - `enemy__<type>__dead__Z3.png`

Scene setup:
- Spawn enemies in a safe “pen” (no combat) for deterministic poses.

Evaluate:
- Enemy types are clearly distinct in silhouette/value.
- Dead state reads as dead (darkened, flattened, etc.).

### 6) Combat micro (combat_micro)
**Purpose**: Compare “combat clarity” (hit feedback, VFX, unit overlap) vs references.

Capture:
- `combat_micro__Z2__world_clean.png`
- `combat_micro__Z2__ui_default.png`

Scene setup:
- 1 hero vs 2–3 goblins near a building edge and near open terrain (two shots if needed).

Evaluate:
- You can tell who is hitting whom (VFX not too noisy).
- HP/intent changes are readable when UI is on.

### 7) UI panels (ui_panels)
**Purpose**: Compare panel ratios and “Majesty-like” clarity of info density.

Capture:
- `ui_panels__hero_selected__Z2.png` (right panel visible)
- `ui_panels__building_selected__Z2.png`
- `ui_panels__debug__Z2.png` (debug panel visible; only if enabled)

Evaluate:
- Right panel width is not oppressive at 1080p.
- Text doesn’t clip; key fields visible (HP, gold, intent, last decision).

### 8) Fog-of-war / minimap (minimap_fog)
**Purpose**: Compare fog readability and minimap legibility vs references.

Capture:
- `minimap_fog__Z2__ui_default.png`

Evaluate:
- Fog states read (unseen vs seen) without destroying world contrast.
- Minimap is legible without being a distraction.

## Reference comparison rubric (what we’re judging)
Use these bullets as the “notes block” per scenario in the HTML gallery.

- **Composition**: town density/landmarks; does it feel like a living base?
- **Scale**: unit vs building vs tile proportions; does anything feel too big/small?
- **Value contrast**: can you read units/buildings on grass/path/water and under fog?
- **Silhouette clarity**: class/enemy type reads instantly at gameplay zoom.
- **UI ratios**: top/bottom/right panels feel “game-like,” not debug; doesn’t cover playfield.
- **Texture/noise budget**: terrain isn’t too speckled; sprites pop.
- **Cohesion**: outline thickness + palette ramps feel consistent (avoid “mix-and-match pack” look).

## Notes on the reference folder
The reference folder includes “Majesty”, “Settlers”, “Warcraft”, “Populus” style images; use them for:
- **UI framing** (panel placement and density)
- **Town readability** (tight base, landmarks)
- **Top-down map legibility** (fog/minimap)


