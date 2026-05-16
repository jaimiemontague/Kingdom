# Sprint WK55 — POI Discovery System & Quality Polish

> **Status:** ACTIVE
> **Version target:** v1.6.1
> **Theme:** Restore real POI discovery, visibility states, UX polish, prefab quality
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 2 of 5)
> **Depends on:** WK54 (map expansion, zones, POI architecture — SHIPPED as v1.6.0)

---

## Context: What's Already Done (v1.6.0 Overnight Run)

The overnight WK54-58 run shipped the full POI system in a single session:
- 12 POI definitions in `game/entities/poi.py`
- 12 POI prefab JSONs in `assets/prefabs/buildings/poi_*.json`
- POI placement system (`game/systems/poi_placement.py`) — just reworked for better distribution
- POI interaction system (`game/systems/poi_interaction.py`) — 6 types working
- Discovery toast notifications in HUD (`game/ui/hud.py` lines 304-378)
- Minimap POI icons — colored dots by interaction type (`game/ui/hud.py` lines 1205-1233)
- Underground system (`game/graphics/underground.py`)
- Boss encounters in combat system

## What's Broken / Bypassed

**CRITICAL: Discovery mechanic is BYPASSED.**

`game/graphics/ursina_renderer.py` lines 400-401:
```python
# POIs are always visible — discovery still triggers interactions
if getattr(b, "is_poi", False) and not b.is_discovered:
    b.is_discovered = True
```

This force-discovers ALL POIs the moment they render. Consequences:
1. Heroes never explore/discover POIs — everything is pre-revealed
2. Discovery toasts fire simultaneously on game start (all 14+ POIs at once)
3. No hidden/silhouette/discovered visibility progression
4. No sense of exploration reward
5. Minimap shows all POIs immediately instead of gradually

## Goal

Restore the intended POI discovery progression: POIs are **hidden** in unexplored fog, show as **mystery markers** in explored-but-not-discovered areas, and fully **reveal** when a hero walks within discovery range. Fix the UX around this — proper toast timing, gradual minimap population, and a satisfying exploration loop.

---

## Scope

### In scope
- Remove force-discover hack from `ursina_renderer.py`
- Implement 3-state POI visibility: HIDDEN (fog UNSEEN) → MYSTERY (fog SEEN, not discovered) → REVEALED (hero within 5 tiles)
- Mystery state rendering: dark/desaturated prefab with "?" marker floating above
- Discovery event fires properly from sim tick, not renderer
- Toast notifications fire one-at-a-time as heroes actually explore
- Verify minimap only shows discovered POIs (code exists but was masked by force-discover)
- Hero AI POI awareness: include nearby discovered/undiscovered POIs in LLM context
- POI interaction feedback: brief visual cue when hero interacts (gold sparkle for loot, blue glow for shrine, etc.)
- Prefab quality review: ensure all 12 POIs look good, add pieces where sparse

### Out of scope
- New POI types beyond existing 12
- Compound prefab system / mesh merging
- Underground rendering changes
- Full quest system (interactions already work)
- Item/loot inventory system (heroes get gold, not items)

---

## Technical Design

### Discovery State Machine (in sim_engine tick)

```
POI created → is_discovered = False
              ↓
Hero within DISCOVERY_RANGE (5 tiles)
              ↓
is_discovered = True
event_bus.emit("POI_DISCOVERED", poi=poi, hero=hero)
HUD.notify_poi_discovered(poi_name)
```

The sim engine (or world.py tick) must check hero proximity to undiscovered POIs each tick. This logic likely exists in `poi_interaction.py` or `sim_engine.py` but the renderer was bypassing it.

### Renderer Visibility States

| Fog State | Discovery State | Rendering |
|-----------|----------------|-----------|
| UNSEEN | any | **Not rendered** (hidden completely) |
| SEEN | `is_discovered = False` | **Mystery marker** — dark tinted prefab at 30% opacity + floating "?" sprite |
| SEEN | `is_discovered = True` | **Full render** — normal prefab |
| VISIBLE | `is_discovered = False` | **Mystery marker** (same as SEEN, hero not close enough yet) |
| VISIBLE | `is_discovered = True` | **Full render** — normal prefab with name label |

### Key Files

| File | Change Required |
|------|----------------|
| `game/graphics/ursina_renderer.py` | Remove force-discover hack (L400-401). Implement 3-state visibility for POI entities. Mystery state = `color=(0.3,0.3,0.4)` + reduced alpha + "?" billboard. |
| `game/sim_engine.py` or `game/world.py` | Ensure discovery range check runs each tick. Emit event on discovery. |
| `game/entities/poi.py` | No changes needed (already has `is_discovered` flag). |
| `game/ui/hud.py` | Toast logic already exists — verify it fires correctly when discovery happens naturally (not all at once). |
| `game/graphics/ursina_environment.py` | May need "?" marker billboard entity creation. |
| `ai/behaviors/bounty_pursuit.py` or `ai/context_builder.py` | Add nearby POI context to hero AI decisions. |

---

## Waves & Agent Assignments

### Wave 1 — Core Discovery Fix (PARALLEL)

**Agent 03 (Technical Director) — Renderer Discovery States**
- Remove force-discover hack from `ursina_renderer.py` lines 400-401
- Implement 3-state POI visibility:
  - UNSEEN fog: POI entity hidden (`enabled = False`)
  - SEEN fog + undiscovered: Mystery render (dark tint + "?" billboard above POI center)
  - SEEN/VISIBLE + discovered: Normal full-color prefab render
- The "?" marker should be a small billboard text entity floating 2 units above the POI
- Ensure POI entities are created but gated by fog state (similar to lair visibility logic at L407-419)

**Agent 05 (Gameplay Systems) — Discovery Mechanic in Sim**
- Verify/fix the discovery range check in the sim tick loop
- Ensure `check_poi_discovery()` runs each tick for all living heroes vs all undiscovered POIs
- On discovery: set `is_discovered = True`, `discoverer_hero_id = hero.id`
- Emit event (EventBus or direct callback) so HUD can fire toast
- Verify all 6 interaction types still work after discovery is real (hero must discover BEFORE interacting)
- Add interaction feedback: brief log message or event when hero completes a POI interaction

### Wave 2 — UX & AI Polish (PARALLEL)

**Agent 08 (UX/UI Director) — Toast & Minimap Polish**
- Verify toast notifications fire one-at-a-time as heroes discover POIs naturally
- Add a subtle sound cue on discovery (use existing audio system, pick a "chime" or "reveal" sound)
- Verify minimap icons appear only for discovered POIs (code exists at hud.py L1215-1233)
- Add a brief "glow" or "pop" animation when a new minimap icon appears
- Consider: should undiscovered-but-SEEN POIs show as gray "?" on minimap? (Small addition if yes)

**Agent 06 (AI/LLM) — Hero POI Awareness**
- Add nearby POIs to hero LLM context when making decisions
- Discovered POIs: include name, type, distance, difficulty, description
- Undiscovered POIs in SEEN tiles: include as "Unknown Structure" at distance
- Hero personality affects POI pursuit: bold→danger POIs, curious→knowledge POIs, greedy→loot POIs
- Wire into existing `ai/behaviors/bounty_pursuit.py` or hero decision-making

### Wave 3 — Verification & QA

- Boot game, confirm POIs are hidden at start
- Walk heroes toward POI locations, confirm discovery fires at ~5 tiles
- Confirm toast appears, minimap icon appears
- Confirm mystery "?" markers visible in explored but undiscovered areas  
- Confirm interactions only work after discovery
- Confirm LLM context includes POI info
- Run `python tools/qa_smoke.py --quick` — must PASS
- Screenshot verification of all states

---

## Acceptance Criteria

1. **POIs are NOT visible at game start** — only castle-area buildings render initially
2. **Mystery markers appear** when fog reveals a POI tile but hero hasn't been within 5 tiles
3. **Discovery fires at 5 tiles** — toast notification, minimap icon appears, prefab renders full color
4. **Toasts are staggered** — one per discovery event, not all at once
5. **Interactions blocked until discovered** — hero can't interact with undiscovered POI
6. **Minimap shows only discovered POIs** — colored dots appear one by one as heroes explore
7. **Hero AI knows about POIs** — personality-driven exploration decisions
8. **All QA gates pass** — qa_smoke, validate_assets

---

## Risks

- Removing force-discover may reveal bugs in the placement system (POIs placed in unreachable locations)
- Discovery range of 5 tiles may feel too short — tune if needed (hero vision is 7)
- Mystery markers need to be unobtrusive but noticeable — balance opacity/size
- LLM context addition increases token cost per hero decision

---

## Human Gate

Jaimie playtests after all waves complete:
```powershell
python main.py
```
Walk the map. Confirm: POIs hidden → mystery markers in explored areas → full reveal on approach → toast + minimap. Check that exploration feels rewarding.
