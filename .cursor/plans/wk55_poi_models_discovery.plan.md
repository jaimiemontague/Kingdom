# Sprint WK55 — POI Prefab Models & Discovery System

> **Status:** DRAFT
> **Version target:** v1.6.1
> **Theme:** Author POI prefabs, implement discovery mechanic, minimap icons
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 2 of 5)
> **Depends on:** WK54 (map expansion, zones, POI architecture)

---

## Goal

All 12 POI types have authored prefab JSON models using Kenney assets. Heroes discover POIs when walking within range. Minimap shows discovered POIs as colored dots.

## Scope

### In scope
- 4 small POI prefab JSONs (shrine, treasure_cache, hermit_hut, gravestone)
- 3 medium POI prefab JSONs (abandoned_camp, druid_grove, wizard_tower)
- 2 large POI prefab JSONs (graveyard, bandit_fortress) — simpler versions without compound system
- 3 special POI prefab JSONs (cave_entrance, mine_entrance, demon_portal)
- POI discovery mechanic (hero within 5 tiles → is_discovered = True)
- Minimap POI icons (color-coded dots)
- POI prefab rendering through existing building prefab pipeline
- Agent 15 provides CLI command to open each model in Model Assembler

### Out of scope
- Compound prefab system / mesh merging (WK56)
- POI interactions (WK56)
- LLM hero context (WK56)
- Underground (WK57)

## Waves

### Wave 1 — POI Discovery Mechanic
Agent 05: Add discovery check to sim_engine tick. When any hero is within 5 tiles of an undiscovered POI, set is_discovered = True.

### Wave 2 — POI Prefab Models
Agent 15: Create all 12 POI prefab JSONs in assets/prefabs/buildings/ using Kenney model references from the proposal.

### Wave 3 — Minimap POI Icons
Agent 08: Add colored dots to minimap for discovered POIs.

### Wave 4 — Verification
Boot game, verify POIs render, discovery works, minimap shows icons.
