# Sprint WK57 — Underground Vertical Stacking

> **Status:** DRAFT
> **Version target:** v1.6.3
> **Theme:** Physical underground geometry below Y=0, cave entrance holes, cutaway camera
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 4 of 5)
> **Depends on:** WK56 (POI interactions, cave/mine entrances functional)

---

## Goal

Underground terrain rendered as physical 3D space below the surface. Cave/mine entrance POIs create visible holes in the surface terrain. Camera supports cutaway view to see underground. Underground has its own lighting and fog of war.

## Scope

### In scope
- Underground terrain mesh at Y=-DEPTH to Y=0
- Cave entrance "holes" in surface terrain (dynamic vertex removal around entrances)
- Camera cutaway rendering (transparency shader near cave entrances)
- Underground lighting (darker ambient + torch point lights)
- Underground fog of war (separate visibility per underground area)
- Layer-aware pathfinding (heroes navigate between surface and underground)
- Hero descent/ascent animation at cave entrances
- Underground enemy/loot spawning

### Out of scope
- Full dungeon generation (procedural room layouts) — future
- Boss encounters in underground — WK58
- Mine-specific resource gathering minigame — future

## Risk

This is the highest-risk sprint. Vertical stacking requires significant renderer surgery. If it proves too expensive mid-sprint, fallback to Approach A (interior overlay) for caves/mines — which already works from WK56.

## Waves

### Wave 1 — Underground Terrain Architecture
Agent 03: Design underground data model — terrain mesh generation, layer property, cutaway rendering approach.

### Wave 2 — Underground Terrain Mesh
Agent 09: Generate underground terrain mesh below Y=0. Cave entrances create holes in surface mesh.

### Wave 3 — Camera & Lighting
Agent 09: Cutaway camera mode. Underground lighting with torch point lights.

### Wave 4 — Underground Fog & Pathfinding
Agent 05: Layer-aware pathfinding. Underground fog of war grid.

### Wave 5 — Hero Transitions
Agent 05: Hero descent/ascent at cave entrances. Underground enemy spawning.

### Wave 6 — Verification
Performance benchmark (double terrain vertices). QA pass.
