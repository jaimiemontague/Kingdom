# Sprint WK56 — Large POIs, Compound Prefabs & Interactions

> **Status:** DRAFT
> **Version target:** v1.6.2
> **Theme:** POI interaction system, LLM hero context, compound prefabs for large POIs
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 3 of 5)
> **Depends on:** WK55 (POI prefabs, discovery)

---

## Goal

Heroes interact with discovered POIs — combat encounters, loot collection, shrine buffs, knowledge reveals, NPC conversations. LLM heroes decide which POIs to visit based on personality. Large POIs use compound prefab system for efficient rendering. Some POIs are enterable for task-like interactions.

## Scope

### In scope
- POI interaction system (approach → trigger → resolve)
- 6 interaction types: combat, loot, shrine (buff), knowledge (map reveal), NPC encounter, dungeon gateway
- LLM hero context — nearby POIs in HeroProfileSnapshot
- Hero personality → POI decision biases
- POI depletion/cooldown mechanics
- Interior overlay for enterable POIs (bandit fortress, wizard tower, cave/mine entrance)
- Compound prefab schema v0.6 (stretch — only if time permits)

### Out of scope
- Underground vertical stacking (WK57)
- Boss encounters with special mechanics (WK58)
- Zone fog tinting (WK58)

## Waves

### Wave 1 — POI Interaction System
Agent 05: Create game/systems/poi_interaction.py with interaction resolution for all 6 types.

### Wave 2 — Hero POI AI Integration
Agent 06: Add nearby_pois to HeroProfileSnapshot. Add POI-seeking behavior to AI decision logic.

### Wave 3 — Interior Overlay for POIs
Agent 08: Extend BuildingInteriorOverlay to handle POI types (wizard tower, cave, mine, bandit fortress).

### Wave 4 — Compound Prefab System (stretch)
Agent 03: Extend prefab schema to support sub-prefab references + mesh merging.

### Wave 5 — Verification
Full QA pass.
