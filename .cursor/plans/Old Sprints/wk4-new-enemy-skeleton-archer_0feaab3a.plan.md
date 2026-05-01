---
name: wk4-new-enemy-skeleton-archer
overview: WK4 AI Studio plan (plan-only) to add a new ranged enemy type `skeleton_archer`, with per-agent prompts, round structure, Build A/B targets, and deterministic + tooling coverage.
todos:
  - id: wk4-r1-prompts
    content: Post wk4_r1 prompts to Agents 03/05/09/11/12 and collect their replies under the correct sprint/round keys.
    status: completed
  - id: wk4-r2-synthesis
    content: Write PM synthesis (tunables, constraints, acceptance tests, integration order) into Agent 01 log under wk4_r2.
    status: completed
    dependencies:
      - wk4-r1-prompts
  - id: wk4-r3-greenlight
    content: After approval, greenlight implementation for Build A and assign the implementing agent(s).
    status: completed
    dependencies:
      - wk4-r2-synthesis
---

# WK4 — New Enemy

: SkeletonArcher (plan-only)

## Sprint identifiers (for agent logs)

- **sprint_id**: `wk4-new-enemy-skeleton-archer`
- **round_id for replies**: `wk4_r1`

Agents must write their replies under:

- `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r1"]`

## Scope

- Add a new enemy type: **`skeleton_archer`** (ranged kiter).
- Visuals: **procedural CC0 placeholder** shipped via the existing generator.
- Spawn source: **Skeleton Crypt** can spawn it (no new lair/building type required).
- Keep first pass simple: **instant-hit ranged** damage (no projectile system required).

## Build targets (planning only)

- **WK4 Build A (midweek) target**: ship `skeleton_archer` end-to-end (enemy class + spawn + placeholders + validation + snapshots).
- **WK4 Build B (endweek) target**: polish pass if needed (tuning, readability, optional projectile/VFX line, perf sanity).

## Agent roster

- **Active agents (must respond in wk4_r1)**
- Agent 03 `TechnicalDirector_Architecture`
- Agent 05 `GameplaySystemsDesigner`
- Agent 09 `ArtDirector_Pixel_Animation_VFX`
- Agent 11 `QA_TestEngineering_Lead`
- Agent 12 `ToolsDevEx_Lead`
- **Consult-only (ping only if needed)**
- Agent 10 `PerformanceStability_Lead`
- Agent 04 `NetworkingDeterminism_Lead`
- Agent 08 `UX_UI_Director`

## Rounds (AI Studio structure)

### wk4_r0 (PM pre-brief)

**Problem**: Add a new enemy that changes combat pacing without breaking determinism, stability, or pipelines.**Non-goals (Build A)**:

- New projectile physics system
- New UI work
- New lair building type

**Gates / evidence required for “done”**:

- `python tools/qa_smoke.py --quick`
- `python tools/validate_assets.py --strict --check-attribution`
- Visual Snapshot System: enemy catalog includes `skeleton_archer` and gallery builds

### wk4_r1 (Agent replies) — copy/paste prompts

#### Prompt: Agent 03 (TechnicalDirector_Architecture)

Write to: `.cursor/plans/agent_logs/agent_03_TechnicalDirector_Architecture.json` under `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r1"]`.

- Define determinism-safe constraints for a ranged/kiting enemy.
- Identify any risky patterns in current enemy code (target selection order, float drift, RNG usage).
- Recommend the safest implementation pattern and file boundaries.

#### Prompt: Agent 05 (GameplaySystemsDesigner)

Write to: `.cursor/plans/agent_logs/agent_05_GameplaySystemsDesigner.json` under `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r1"]`.

- Propose initial tunables for `skeleton_archer`: HP, attack, speed, attack range, min range, cooldown.
- Propose `SkeletonCrypt` spawn mix (e.g., 70/30) that won’t spike difficulty.
- List quick balance failure modes + mitigations.

#### Prompt: Agent 09 (ArtDirector_Pixel_Animation_VFX)

Write to: `.cursor/plans/agent_logs/agent_09_ArtDirector_Pixel_Animation_VFX.json` under `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r1"]`.

- Placeholder silhouette requirements for a readable ranged skeleton (bow/shoot cue) at 32×32.
- Minimum per-state cues for `idle/walk/attack/hurt/dead`.
- Any constraints to stay aligned with `docs/art/wk3_major_graphics_target.md`.

#### Prompt: Agent 11 (QA_TestEngineering_Lead)

Write to: `.cursor/plans/agent_logs/agent_11_QA_TestEngineering_Lead.json` under `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r1"]`.

- Acceptance criteria + repro steps for spawn + kite behavior.
- What to assert for validator + snapshots.
- Any smoke test extension recommendations (keep them non-flaky).

#### Prompt: Agent 12 (ToolsDevEx_Lead)

Write to: `.cursor/plans/agent_logs/agent_12_ToolsDevEx_Lead.json` under `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r1"]`.

- Confirm minimal tooling changes needed (likely: add enemy type to `tools/assets_manifest.json`).
- Confirm snapshot scenarios will auto-include the new enemy (enemy catalog reads manifest).
- Recommend any tiny automation helpers (optional).

### wk4_r2 (PM synthesis)

PM consolidates agent replies into:

- Locked tunables + spawn policy
- Determinism constraints
- Acceptance tests + commands
- Integration order + risk notes

Output location:

- `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json` under `sprints["wk4-new-enemy-skeleton-archer"].rounds["wk4_r2"]`

### wk4_r3 (Implementation greenlight)

**Deferred for now (plan-only)**. When you say “go,” this round becomes the greenlight to implement.

## Planned implementation touchpoints (for later)

- [`config.py`](config.py): add `SKELETON_ARCHER_*` tunables
- [`game/entities/enemy.py`](game/entities/enemy.py): add `SkeletonArcher` class + kite logic
- [`game/entities/lair.py`](game/entities/lair.py): allow `SkeletonCrypt` to spawn it (using lair RNG)
- [`tools/assets_manifest.json`](tools/assets_manifest.json): add `skeleton_archer` to `enemies.types`
- [`tools/generate_cc0_placeholders.py`](tools/generate_cc0_placeholders.py): generate placeholder sprite frames for it
- [`game/graphics/enemy_sprites.py`](game/graphics/enemy_sprites.py): ensure procedural fallback recognizes it
- Snapshots: [`tools/screenshot_scenarios.py`](tools/screenshot_scenarios.py) `scenario_enemy_catalog` already reads the manifest

## Definition of done (when implemented)

- `skeleton_archer` spawns (crypt), attacks from range, and attempts to maintain distance.