# POIs Multi-Sprint Implementation Roadmap

> **Source:** `.cursor/plans/pois_proposal.md` + Jaimie's implementation notes
> **Status:** ACTIVE — WK54 is first sprint
> **Created:** 2026-05-12 (Agent 01)

---

## Scope Decisions (from Jaimie's review)

| Decision | Choice |
|----------|--------|
| **Map size** | Expand to 250×250 (Option B) |
| **Zones** | 3 custom zones only: Darkwood (south, starts 24 tiles), Mountains (north, starts 20 tiles, Ember Peaks stats), Canyon Land (east, starts 22 tiles, Bone Wastes stats) + Castle Town |
| **Renderer integration** | Option A — POIs invisible until hero within discovery range |
| **POI models** | Agent 15 builds all, provides CLI to open in Model Assembler, human revises |
| **POIs excluded** | Mysterious Well, Ruined Outpost, Windmill/Watermill Ruin, Ancient Ruins, Dragon Cave |
| **Underground** | Approach C — Vertical Stacking (physical underground below Y=0 with cutaway) |
| **Terrain flattening** | Required — flatten terrain in prefab footprint so POIs/buildings don't clip through hills |
| **Enterable POIs** | Some large buildings can have interior interactions (rogue steal, rest, buy) using existing overlay system — no new 2D mechanics |

### POIs to Build (12 types)

**Small (1×1–2×2):** Shrine/Altar, Treasure Cache, Hermit Hut, Overgrown Gravestone
**Medium (2×2–3×3):** Abandoned Camp, Druid Grove, Wizard's Tower
**Large (4×4–6×6):** Overgrown Graveyard, Bandit Fortress
**Special:** Cave/Crypt Entrance, Mine Entrance, Demon Portal

---

## Sprint Overview

```
WK54  Map Expansion, Zones & POI Foundation
WK55  POI Prefab Models & Discovery System
WK56  Large POIs, Compound Prefabs & Interactions
WK57  Underground Vertical Stacking
WK58  Zone Atmosphere, Boss Encounters & Polish
```

---

## Sprint 1 — WK54: Map Expansion, Zones & POI Foundation

**Goal:** The 250×250 map works, zones exist and influence terrain, the POI entity architecture is in place, and POIs can be procedurally placed (even before prefab models exist).

| Task | Effort | Key Files |
|------|--------|-----------|
| Expand map to 250×250 (config, heightmap 501×501, fog texture, pathfinding perf) | M | `config.py`, `game/world.py`, `game/graphics/terrain_height.py` |
| Zone system — `world_zones.py` with 4 zones (Castle Town + 3 custom) | M | `game/world_zones.py` (new) |
| Zone-influenced terrain generation (biome density biases per zone) | M | `game/world.py`, `game/graphics/terrain_height.py` |
| Terrain flattening mechanism for building/POI footprints | M | `game/graphics/terrain_height.py`, `game/world.py` |
| POI entity class + POIDefinition data model | S | `game/entities/poi.py` (new) |
| 12 POI definitions registered in config + BuildingFactory | S | `config.py`, `game/building_factory.py` |
| POI placement system (zone-aware, constraint-based) | M | `game/systems/poi_placement.py` (new) |
| Renderer integration Option A (invisible until discovered) | S | `game/graphics/ursina_renderer.py` |
| Camera zoom re-tune for 250×250 | S | `config.py`, `game/graphics/ursina_app.py` |

**Deliverable:** 250×250 map with 3 visually distinct zones. POIs are placed procedurally (placeholder cubes/markers until WK55 prefabs arrive). Terrain flattens under buildings. QA smoke passes.

**Human Gate:** Jaimie walks the 250×250 map — zones feel different, terrain looks right, no perf regression.

---

## Sprint 2 — WK55: POI Prefab Models & Discovery System

**Goal:** All 12 POI types have authored prefab models. Heroes discover POIs via fog of war. Minimap shows discovered POIs.

| Task | Effort | Key Files |
|------|--------|-----------|
| 4 small POI prefabs — Agent 15 builds, provides CLI for Model Assembler | M | `assets/prefabs/buildings/poi_*.json` |
| 3 medium POI prefabs — Agent 15 | M | `assets/prefabs/buildings/poi_*.json` |
| POI discovery mechanic (hero within 5 tiles → discovered) | M | `game/systems/poi_placement.py`, `game/world.py` |
| Fog-of-war interaction (hidden/silhouette/discovered states) | M | `game/graphics/ursina_renderer.py` |
| Minimap POI icons (color-coded by interaction type) | S | `game/ui/minimap.py` or equivalent |
| Replace placeholder markers with authored prefabs | S | `game/building_factory.py` |
| Human review of all 7 small+medium prefabs in Model Assembler | — | Human gate |

**Deliverable:** Heroes explore, discover POIs that render as Kenney-model prefabs. Minimap shows discovered POIs. Small and medium POIs look polished.

**Human Gate:** Jaimie reviews each prefab in Model Assembler. Iterate until approved.

---

## Sprint 3 — WK56: Large POIs, Compound Prefabs & Interactions

**Goal:** Compound prefab system enables 30-80 piece POIs. Heroes interact with POIs via LLM narration. Enterable POIs use interior overlay for tasks.

| Task | Effort | Key Files |
|------|--------|-----------|
| Compound prefab schema v0.6 (sub-prefab refs, repeat patterns, variant slots) | L | `assets/prefabs/` schema, `game/building_factory.py` |
| Runtime mesh merging for compound prefabs (single draw call per large POI) | L | `game/graphics/ursina_renderer.py` or new module |
| 2 large POI prefabs (Graveyard, Bandit Fortress) — Agent 15 | L | `assets/prefabs/buildings/poi_*.json` |
| 3 special POI prefabs (Cave/Crypt, Mine, Demon Portal) — Agent 15 | M | `assets/prefabs/buildings/poi_*.json` |
| LLM hero context — nearby POIs in HeroProfileSnapshot | M | `ai/context_builder.py`, `game/sim/hero_profile.py` |
| Hero personality → POI decisions (bold→danger, curious→knowledge, etc.) | M | `ai/behaviors/`, `ai/basic_ai.py` |
| POI interaction system (approach → trigger → reward/combat) | L | `game/systems/poi_interaction.py` (new) |
| POI interaction types: combat, loot, shrine buff, knowledge reveal, NPC encounter | L | `game/systems/poi_interaction.py` |
| POI depletion, respawn, cooldown mechanics | M | `game/entities/poi.py` |
| Interior overlay for enterable POIs (rogue steal, rest, buy — existing system) | M | `game/ui/building_interior_overlay.py` |
| Human review of large + special prefabs | — | Human gate |

**Deliverable:** Full POI interaction loop — heroes discover, approach, interact, and receive rewards/combat/lore. Large POIs render efficiently via mesh merging. Some POIs are enterable for task-like interactions.

**Human Gate:** Jaimie playtests hero POI interactions. Reviews large prefab models.

---

## Sprint 4 — WK57: Underground Vertical Stacking

**Goal:** Physical underground geometry below Y=0. Cave/mine entrances create holes in surface terrain. Camera can look through cutaways to see underground.

| Task | Effort | Key Files |
|------|--------|-----------|
| Underground terrain mesh at Y=-DEPTH to Y=0 | XL | `game/graphics/terrain_height.py`, new underground module |
| Cave entrance "holes" in surface terrain (dynamic vertex removal) | L | Terrain mesh generation |
| Camera cutaway rendering (transparency shader near cave entrances) | L | `game/graphics/ursina_app.py`, shader files |
| Underground lighting (darker ambient + point lights from torches) | M | Lighting/shader system |
| Underground fog of war (separate visibility grid per underground area) | M | `game/graphics/ursina_terrain_fog_collab.py` |
| Layer-aware pathfinding (heroes navigate between surface and underground) | M | `game/systems/pathfinding.py` |
| Hero descent/ascent animation at cave entrances | S | `game/graphics/ursina_renderer.py` |
| Underground entity spawning (enemies, loot inside caves/mines) | M | `game/systems/lairs.py`, `game/entities/` |
| Performance benchmark (double terrain vertices when both layers visible) | M | Agent 10 |

**Deliverable:** Heroes visibly descend into cave/mine entrances. Underground is rendered as physical 3D space below the surface. Camera supports cutaway view. Underground has its own lighting and fog.

**Human Gate:** Jaimie explores underground areas. Camera behavior feels natural. Performance acceptable.

**Risk:** This is the highest-risk sprint. Vertical stacking requires significant renderer surgery. If it proves too expensive mid-sprint, fallback to Approach A (interior overlay) for caves/mines, defer vertical stacking.

---

## Sprint 5 — WK58: Zone Atmosphere, Boss Encounters & Polish

**Goal:** Zones feel visually distinct. Boss POIs have named encounters. Performance is solid at scale. Full integration pass.

| Task | Effort | Key Files |
|------|--------|-----------|
| Visual zone distinction — fog color tinting per zone | M | `game/graphics/ursina_app.py`, shaders |
| Zone vegetation density (Darkwood = heavy trees, Mountains = sparse + rocks, Canyon = barren + rock formations) | M | `game/world.py` terrain gen |
| Zone ground color overlay (terrain shader multiplies zone tint) | M | Terrain shader |
| Zone elevation profiles (Mountains = high amplitude, Canyon = valleys + ridges, Darkwood = moderate) | S | `game/graphics/terrain_height.py` |
| Named boss spawning at Bandit Fortress + Demon Portal | M | `game/systems/combat.py`, `game/entities/enemy.py` |
| Multi-phase boss encounters (waves, special abilities) | L | `game/systems/combat.py` |
| POI-triggered quest hooks (LLM narration for multi-step quest chains) | M | `ai/`, `game/systems/poi_interaction.py` |
| Performance benchmark at 250×250 with all POIs + underground | M | Agent 10 |
| Full QA pass — smoke tests, screenshot captures, regression check | M | Agent 11 |
| POI interaction UI polish (discovery toast, interaction panel) | M | `game/ui/` |

**Deliverable:** The POI system is complete. Zones are visually immersive. Bosses guard legendary POIs. Underground works. Performance is validated. Ready for player testing.

**Human Gate:** Final playtest — full game loop with POI discovery, interaction, bosses, underground.

---

## Cross-Sprint Dependencies

```
WK54 (Foundation) ──→ WK55 (Models + Discovery) ──→ WK56 (Large POIs + Interactions)
                                                          │
                                                          ▼
                                                     WK57 (Underground)
                                                          │
                                                          ▼
                                                     WK58 (Polish)
```

WK55 and WK56 are sequential (need simple POIs before compound system). WK57 depends on WK56 (cave/mine entrance POIs must exist). WK58 is the final polish pass.

---

## Agent Assignments (Expected)

| Agent | Role | Primary Sprints |
|-------|------|-----------------|
| 01 | Executive Producer / PM | All — sprint plans, coordination |
| 03 | Technical Director | WK54 (map/zones/terrain), WK57 (underground renderer) |
| 05 | Gameplay Systems | WK54 (POI placement), WK56 (interactions), WK58 (bosses) |
| 09 | Art Director | WK55-56 (prefab review), WK58 (zone atmosphere) |
| 10 | Performance & Stability | WK54 (250×250 perf), WK57 (underground perf), WK58 (final) |
| 11 | QA | All — gate checks |
| 15 | Prefab Builder | WK55 (small+medium), WK56 (large+special) — provides CLI for assembler |
| 07 | AI/LLM | WK56 (hero POI context), WK58 (narration polish) |
