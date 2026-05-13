# Sprint WK58 — Zone Atmosphere, Boss Encounters & Polish

> **Status:** DRAFT
> **Version target:** v1.6.4
> **Theme:** Visual zone distinction, boss encounters, final polish
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 5 of 5)
> **Depends on:** WK57 (underground system)

---

## Goal

Zones feel visually distinct through fog color tinting, ground color overlay, and vegetation density. Boss POIs have named encounters. Performance validated at full scale. Final integration pass.

## Scope

### In scope
- Per-zone fog color tinting (Darkwood greenish, Mountains blueish, Canyon reddish)
- Zone ground color overlay (terrain shader zone tint)
- Zone elevation profiles (Mountains high amplitude, Canyon ridges, Darkwood moderate)
- Named boss spawning at Bandit Fortress + Demon Portal
- Multi-phase boss encounters (waves, special abilities)
- POI-triggered quest hooks (LLM narration for multi-step quest chains)
- Performance benchmark at 250×250 with all POIs + underground
- Full QA pass — smoke tests, screenshot captures, regression check
- POI interaction UI polish (discovery toast, interaction panel)

### Out of scope
- New POI types beyond the original 12
- Full quest system (this sprint adds hooks, not a quest engine)
- Item/loot system (heroes get gold, not items)

## Waves

### Wave 1 — Zone Atmosphere
Agent 09: Fog color tinting per zone. Ground color overlay. Zone-specific elevation profiles.

### Wave 2 — Boss Encounters
Agent 05: Named boss entities at boss POIs. Multi-phase combat with wave spawning.

### Wave 3 — UI Polish
Agent 08: POI discovery toast notification. Interaction panel for POI encounters.

### Wave 4 — Performance & QA
Agent 10: Full benchmark. Agent 11: QA gates + screenshots.
