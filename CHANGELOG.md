# Changelog

## Prototype v1.2.8 — The Audio Update (Hotfix)

- Fix: Bounty flags now render **on top of black fog** (UNSEEN), so they’re visible even in solid-black fog-of-war.

## Prototype v1.2.7 — The Audio Update

- Audio: Added **ambient loop** + expanded SFX coverage (building place/destroy, bounty place/claim, melee hit, enemy death, lair cleared).
- Audio rule (feel): **You can only hear world sounds for actions that are visible on screen** (inside camera viewport **and** `Visibility.VISIBLE`).
- Build UX: Clicking **Build** now opens a **clickable building list** (click-to-select behaves like hotkeys and enables mouse placement).
- Fog-of-war: Bounties can appear in **black fog**, and Rangers will pursue those bounties even if far away/unrevealed.
- Rangers: Baseline AI is more prone to **exploring black fog**, and Rangers earn a small amount of **XP for revealing new tiles**.

## Prototype v1.2.6 — The Ranged Update

- Combat readability: **visible ranged projectiles** for ranged attackers (heroes/enemies/towers), tuned for readability (slower + larger pixels).
- Rangers: **attack from range** (no more running into melee range first) and **bow-shot cue** in attack frames.
- Buildings: **auto-demolish at 0 HP** (except castle = game over) + **player demolish button** (instant, no refund).
- Destruction: demolished/destroyed buildings leave **rubble/debris** behind (visual-only, deterministic).
- Workers: **Peasants and Tax Collectors render as pixel sprites** (no glyphs).
- Tooling: Visual Snapshot System scenarios updated/added (including `ranged_projectiles` and `building_debris`) and strict asset validation stays green.

## Prototype v1.2.5

- New enemy: **Skeleton Archer** (`skeleton_archer`) — ranged-only instant-hit attacks with kiting behavior.
- Spawns from **Skeleton Crypt** (deterministic 80/20 mix) and is now **guaranteed in Wave 1** near the castle for easy testing.
- Pipeline: strict asset validation and Visual Snapshot System enemy catalog cover the new enemy type.

## Prototype v1.2.4

- WK3 UI polish + UX manageability: 1080p borderless default, Quit button, and closeable panels (X).
- Visual Snapshot System: deterministic screenshot capture + comparison gallery to drive look/feel iteration.
- Pixel-art pass: improved CC0 placeholder sprites for buildings/enemies (native tile-multiple sizes for buildings) while keeping fallbacks safe.
- Perf/determinism guardrails: tooling gates remain green (`qa_smoke --quick`, strict asset + attribution validator).

## Prototype v1.2.3

- Hero AI polish: reduced rapid target/goal oscillation (“spaz loops”) via commitment windows/hysteresis.
- Combat correctness: heroes **cannot apply damage while inside buildings** (hard-gated).
- Stuck recovery: deterministic detection + recovery attempts (repath/nudge/reset) to reduce “frozen in the wild” cases.
- QA gate: `python tools/qa_smoke.py --quick` includes deterministic `hero_stuck_repro` and passes (determinism guard first).
- Debuggability: debug UI exposes stuck snapshot + attack-block reason (debug-only, cache-friendly).

## Prototype v1.2.1

- Hero UI: show **Intent** and **Last decision** (action + short reason + age) in **mock** and **--no-llm** modes.
- Bounty UI: show **responders count** and deterministic **attractiveness** tier (low/med/high).
- Early-session clarity: improved bounty placement discoverability (help + tip).
- Determinism guardrails: `qa_smoke --quick` includes a determinism guard and passes (no wall-clock time in sim logic; no global RNG in sim).

## Prototype v1.2.0

- Pixel-art render pipeline improvements: nearest-neighbor scaling + reduced camera shimmer.
- Procedural pixel sprites for tiles, enemies, and buildings (with fallbacks when no assets exist).
- Combat VFX particles for hits/kills to improve readability.
- Fog-of-war visibility system and overlay rendering.
- Added neutral building system (auto-spawned map structures) and supporting systems.

## Prototype v1.1.0

- Heroes have unique stable IDs (prevents synchronized/clumped behavior from name collisions).
- Enemies retarget attackers when hit while attacking buildings.
- Added Peasants that spawn from the castle, build newly placed buildings, and repair structures (castle repair is top priority).
- Newly placed buildings deploy at 1 HP and are non-targetable until construction begins; unusable until fully built.
- Hero UI panels display potion counts; heroes can buy and carry potions when researched.
- Wave pacing tuned (warmup before first wave + larger, less frequent waves).






