# Changelog

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






