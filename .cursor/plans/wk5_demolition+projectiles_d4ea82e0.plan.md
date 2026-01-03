---
name: WK5 Demolition+Projectiles
overview: Next sprint adds building destruction + player demolish, introduces visible ranged projectiles (arrow pixels) with a generic pipeline for future ranged attackers, and replaces peasant/tax-collector symbol renders with proper pixel sprites—keeping determinism, validators, and visual snapshots green.
todos:
  - id: wk5-impl-demolish
    content: Auto-demolish buildings at 0 HP (except castle) with reference cleanup in engine
    status: completed
  - id: wk5-ui-demolish-button
    content: Add player demolish button in building panel + engine action handler (instant, no refund)
    status: completed
    dependencies:
      - wk5-impl-demolish
  - id: wk5-projectile-events
    content: Add generic ranged attack event emission from combat (from/to positions, projectile_kind)
    status: completed
  - id: wk5-vfx-arrows
    content: Extend VFXSystem to render 1–2 px arrow/bolt projectiles deterministically
    status: completed
    dependencies:
      - wk5-projectile-events
  - id: wk5-ranger-bow
    content: Update ranger attack visuals to read as bow shooting (sprite cue + projectile coherence)
    status: in_progress
    dependencies:
      - wk5-vfx-arrows
  - id: wk5-workers-assets
    content: Add workers category to assets_manifest + validate_assets + CC0 placeholder generator outputs
    status: completed
  - id: wk5-workers-render
    content: Switch peasant and tax collector render paths to worker sprites (no glyphs)
    status: completed
    dependencies:
      - wk5-workers-assets
  - id: wk5-snapshots
    content: Add Visual Snapshot scenarios for worker sprites + ranged projectiles; rebuild gallery
    status: completed
    dependencies:
      - wk5-vfx-arrows
      - wk5-workers-render
  - id: wk5b-projectile-readability
    content: Build B — Slow down and slightly enlarge ranged projectiles for in-game readability (keep deterministic + low overhead)
    status: completed
    dependencies:
      - wk5-vfx-arrows
  - id: wk5b-building-debris
    content: Build B — Leave debris/rubble behind when a building is destroyed/demolished (visual-only decal/VFX, deterministic)
    status: completed
    dependencies:
      - wk5-impl-demolish
---

# WK5 — Building Demolition + Ranged Projectiles + Worker Pixel Sprites

## Goals (what we’re shipping)

- **Buildings auto-demolish at 0 HP** (all buildings **except castle**, which continues to trigger game over as today).
- **Player demolish button** inside the building UI (instant, **no refund**).
- **Ranged combat readability**:
- **Rangers visibly shoot a bow** (sprite/pose cue).
- **All ranged attackers (present and future) emit visible projectiles** (1–2 px “arrow”/bolt) using a generic, low-overhead pipeline.
- **Build B polish**:
- **Projectiles are readable in live play** (slower travel + slightly larger pixels; still visual-only and deterministic).
- **Destroyed/demolished buildings leave debris/rubble behind** (visual-only; does not block movement).
- **Workers are pixel sprites, not symbols/letters**:
- Peasants
- Tax Collectors

## Non-goals (explicitly out of scope)

- Projectile physics / collision (projectiles are **visual only** on the first pass).
- Refund/worker-timed demolish (you chose instant/no refund).
- Rebalancing economy systems beyond minimal tuning if needed.

## Current code anchors (where changes will land)

- **Building HP and damage**: [`game/entities/building.py`](game/entities/building.py)
- **Main loop + centralized cleanup**: [`game/engine.py`](game/engine.py)
- **Combat events (best place to emit ranged attack events)**: [`game/systems/combat.py`](game/systems/combat.py)
- **VFX system (extend to render arrow/bolt particles)**: [`game/graphics/vfx.py`](game/graphics/vfx.py)
- **Ranged enemy exists already**: `skeleton_archer` in [`game/entities/enemy.py`](game/entities/enemy.py)
- **Building UI panel (add demolish button + click action)**: [`game/ui/building_panel.py`](game/ui/building_panel.py)
- **Worker renders today (symbol-based)**: [`game/entities/peasant.py`](game/entities/peasant.py), [`game/entities/tax_collector.py`](game/entities/tax_collector.py)
- **Asset pipeline + strict gate**: [`tools/assets_manifest.json`](tools/assets_manifest.json), [`tools/validate_assets.py`](tools/validate_assets.py), [`tools/generate_cc0_placeholders.py`](tools/generate_cc0_placeholders.py)

## Implementation plan (Build A)

### 1) Building destruction: auto-demolish at 0 HP

- Add a **central cleanup pass** in [`game/engine.py`](game/engine.py) that:
- Removes any building with `hp <= 0` and `building_type != "castle"`.
- If removed building is a lair (e.g., `is_lair`), remove from `lair_system.lairs` too.
- Clears references to destroyed buildings:
    - `selected_building` / `building_panel.selected_building`
    - `hero.target` if it points to a destroyed building
    - `enemy.target` if it points to a destroyed building
    - `peasant.target_building` and `tax_collector.target_guild` if those point to destroyed buildings
- Ensures pathing/blocking reflects removal (navigation already reads from the `buildings` list).

### 2) Player demolish button in building panel

- Extend [`game/ui/building_panel.py`](game/ui/building_panel.py):
- Add a **red “Demolish” button** when a building is selected.
- Disabled/hidden for `castle`.
- On click, return an action like `{"type": "demolish_building", "building": selected_building}`.
- In [`game/engine.py`](game/engine.py) click handling:
- Consume the action and remove the building immediately (no refund).
- Emit a HUD message (e.g., “Demolished: Market”).

### 3) Generic ranged projectile pipeline (present + future)

- Define a small “ranged attack metadata” standard carried through combat events:
- For any ranged attack, emit an event that includes:
    - `from_x`, `from_y`, `to_x`, `to_y`
    - `projectile_kind` (e.g., `arrow`, `bolt`)
    - optional `color`/`size_px`
- Update [`game/systems/combat.py`](game/systems/combat.py) to:
- Distinguish ranged vs melee attackers via a simple interface:
    - `attacker.is_ranged_attacker` boolean OR `attacker.get_ranged_spec()` method.
- When damage is applied, generate a **ranged projectile event** in addition to `hero_attack` / `enemy_attack`.
- Extend [`game/graphics/vfx.py`](game/graphics/vfx.py):
- Add an **arrow/bolt VFX primitive** (1–2 px) that travels from `from_` to `to_` over a short lifetime (e.g., 80–140ms).
- Deterministic spawn: seed any jitter from event fields (not wall-clock).
- Render in world-space (already integrated in [`game/engine.py`](game/engine.py)).

### 4) Rangers “shoot visible bows”

- Ensure Ranger attack visuals read as “bow shot” even at 32×32:
- Update procedural fallback sprite generation for ranger attack pose (if used), and/or
- Add/adjust placeholder PNG frames for Ranger `attack` to include a bow silhouette.
- This work is coordinated with the projectile VFX so “bow + arrow” reads clearly together.

### 5) Worker pixel sprites (Peasant + TaxCollector)

- Add a new validated sprite category:
- `assets/sprites/workers/peasant/{idle,walk,work,hurt,dead}/frame_000.png`
- `assets/sprites/workers/tax_collector/{idle,walk,collect,return}/frame_000.png`
- Update [`tools/assets_manifest.json`](tools/assets_manifest.json) and [`tools/validate_assets.py`](tools/validate_assets.py) to validate `workers`.
- Extend [`tools/generate_cc0_placeholders.py`](tools/generate_cc0_placeholders.py) to generate worker frames (simple silhouettes consistent with the existing CC0 placeholder style).
- Update rendering:
- [`game/entities/peasant.py`](game/entities/peasant.py) uses worker sprites instead of letters/shapes.
- [`game/entities/tax_collector.py`](game/entities/tax_collector.py) uses worker sprites instead of the `$` glyph.

## Build B (polish)

- Tune projectile readability so it’s visible during normal play (not just a single “fire flash”):
- Increase travel time (target: ~250–450ms) so projectiles render for multiple frames even under mild FPS drops.
- Increase on-screen footprint slightly (target: default 2px, optional 3px “tip+shaft+trail” variant) while staying crisp/pixel-aligned.
- Keep determinism: any jitter must be seeded from event fields (no wall-clock); avoid per-frame allocations.
- Add building debris:
- When a building is destroyed (HP reaches 0) or player-demolished, leave rubble/debris behind at the footprint center.
- Debris is visual-only (no collision/pathing impact). Deterministic placement/pattern seeded from building coords/type.
- Prefer a lightweight in-engine decal/VFX solution first; add assets only if needed (and update validator/manifest if so).

## Acceptance (done means)

- **Functional**
- Any non-castle building that reaches `hp == 0` is removed from the map and no longer blocks pathing.
- Player can demolish any non-castle building via the building panel button.
- Ranged attacks show a visible projectile traveling from attacker to target **and it is readable in live play** (not just 1 frame).
- Rangers visually read as archers (bow cue) when attacking.
- Peasants and tax collectors render as pixel sprites (no glyphs).
- When a building is destroyed/demolished, debris/rubble remains visible afterward.
- **Gates**
- `python tools/qa_smoke.py --quick` (PASS)
- `python tools/validate_assets.py --strict --check-attribution` (PASS)
- **Visual Snapshot System**
- Add/extend scenarios to include:
    - worker sprites (peasants + tax collectors)
    - ranged projectile showcase (at least one shot where projectile is mid-flight)
- Rebuild comparison gallery against `.cursor/plans/art_examples`.

## One unified prompt for all agents (copy/paste)

You are participating in **WK5 — Building Demolition + Ranged Projectiles + Worker Pixel Sprites**.**Global constraints**

- Keep sim deterministic: no wall-clock time in sim logic; avoid global `random.*` for sim.
- Projectiles are **visual only** (no physics/collision).
- Buildings: auto-demolish at 0 HP **except castle**.
- Player demolish: **instant, no refund**.
- Keep gates green: `qa_smoke --quick` and `validate_assets --strict --check-attribution`.

**Write your reply under** your agent log JSON:`sprints["wk5-demolition-projectiles-workers"].rounds["wk5_r5"]`

### Agent 03 — TechnicalDirector_Architecture

- Propose the cleanest architecture for:
- building removal + reference cleanup
- generic ranged projectile events from combat → VFX
- Call out risk points (target references, pathing, UI selection) and suggest safe ordering.
- Recommend minimal interfaces (`get_ranged_spec()` etc.) that scale to future ranged attackers.

### Agent 05 — GameplaySystemsDesigner

- Define “ranged attacker” classification rules (heroes, enemies, towers).
- Propose initial projectile timing (travel time) and readability knobs.
- Provide demolish UX gameplay considerations (e.g., allow demolish while under attack?).

### Agent 08 — UX_UI_Director

- Specify the building panel demolish button placement, label, color language, and any guardrails.
- Provide microcopy for demolish + auto-demolish messaging.

### Agent 09 — ArtDirector_Pixel_Animation_VFX

- Provide sprite briefs for:
- Ranger bow/attack readability
- Arrow/bolt projectile (1–2 px) with palette/outline guidance
- Peasant + TaxCollector silhouettes (readable at 32×32)
- Ensure alignment with the pixel style guide (contrast, outline, light direction).
- **Build B**: Specify projectile readability targets (bigger/slower) and debris/rubble visual direction (palette + shape language).

### Agent 11 — QA_TestEngineering_Lead

- Draft an execution checklist covering:
- building auto-demolish edge cases
- player demolish cases
- projectile visibility checks
- regression risks (selection cleanup, pathing, lair system)
- Recommend a minimal deterministic snapshot shot list for this sprint.
- **Build B**: Add a check that projectiles remain visible under simulated low FPS (dt spikes) and that debris appears after building destruction.

### Agent 12 — ToolsDevEx_Lead

- Specify updates needed for:
- `assets_manifest.json` (add workers category)
- `validate_assets.py` (validate workers)
- `generate_cc0_placeholders.py` (generate worker frames + ranger cue if needed)
- Visual Snapshot scenarios for workers + ranged projectiles
- **Build B**: Adjust `ranged_projectiles` scenario tick counts if needed to ensure at least one capture is mid-flight with the new slower timings.

### Agent 10 — PerformanceStability_Lead (consult)

- Review the projectile VFX approach to ensure it stays cheap (avoid per-frame allocations, avoid O(N^2)).

## Implementation todos

- **wk5-impl-demolish**: Add auto-demolish cleanup pass in engine and ensure reference cleanup.
- **wk5-ui-demolish-button**: Add demolish button to building panel + engine action handling.
- **wk5-projectile-events**: Add ranged-attack event plumbing from combat.
- **wk5-vfx-arrows**: Implement arrow/bolt VFX rendering in VFXSystem.