# Sprint WK56 — POI Interaction Depth & Gameplay Impact

> **Status:** COMPLETE — all waves delivered, 307 tests pass, QA smoke PASS
> **Version target:** v1.6.2
> **Theme:** Transform POI interactions from stubs into meaningful gameplay events
> **Roadmap:** `.cursor/plans/pois_multisprint_roadmap.md` (Sprint 3 of 5)
> **Depends on:** WK55 (POI discovery, prefabs, AI awareness — COMPLETE)
> **Execution:** Claude Code Agent 01 orchestrating sub-agents

---

## Context: What WK54-55 Already Delivered

The overnight WK54-58 run + WK55 polish delivered the foundation:
- 12 POI definitions in `game/entities/poi.py` + 12 prefab JSONs
- POI placement system (`game/systems/poi_placement.py`) — zone-aware, constraint-based
- Discovery mechanic in `game/sim_engine.py` (`_check_poi_discovery`, 5-tile range)
- Binary visibility: hidden until discovered, full render after (`ursina_renderer.py`)
- Basic interaction system: 7 handlers in `game/systems/poi_interaction.py`
- POI cooldowns + depletion tracking
- LLM hero context with nearby POIs (`ai/behaviors/poi_awareness.py`)
- Personality-driven POI visits (`maybe_visit_poi` in exploration behavior)
- Boss spawning at boss-type POIs (BanditLord, DemonOverlord)
- HUD discovery toast notifications + minimap POI icons

## Problem: Interactions Are Stubs

While the interaction *system* works (proximity check → handler dispatch → cooldown), most handlers do almost nothing:

| Handler | Current Behavior | Gap |
|---------|-----------------|-----|
| `_handle_combat` | Emits `poi_combat_triggered` event | **No enemies spawn.** Hero walks up, nothing happens. |
| `_handle_knowledge` | Calls `world._reveal_circle()` | Only reveals fog. Doesn't reveal nearby hidden POIs. |
| `_handle_npc` | Marks as interacted | **No dialogue, trade, or narrative.** |
| `_handle_dungeon` | Marks as interacted | **Nothing happens.** (WK57 placeholder, but needs flavor.) |
| `_handle_shrine` | Heals to full HP, sets cooldown | Decent, but no temporary buff. |
| `_handle_loot` | Gives 20-50 gold | Gold doesn't scale with risk/difficulty. |
| `_handle_boss` | Spawns BanditLord/DemonOverlord | Best handler — actually does something. |

Additionally:
- **No HUD feedback** when interactions resolve (player sees nothing beyond discovery toast)
- **No interaction toasts** like "Elena found treasure! +42 gold"

## Goal

Make POI interactions *feel real*. When a hero visits a combat POI, enemies should appear. When they loot a cache, the player should see how much gold they found. When they pray at a shrine, they should get a temporary combat advantage. Every interaction produces visible, meaningful gameplay effects and clear player feedback.

---

## Scope

### In scope
1. **Combat POI spawns enemies** — 2-4 enemies at POI location, scaled to difficulty tier
2. **Knowledge POI reveals hidden POIs** — discover the nearest undiscovered POI within 15 tiles
3. **Shrine POI buffs** — temporary attack bonus (+2/+3/+5 by tier) for 90 seconds on top of full heal
4. **Loot POI scaling** — gold scales with difficulty tier (tier 1: 20-50, tier 3: 60-120, tier 5: 100-200)
5. **NPC POI narrative** — emit event with descriptive flavor text for HUD display
6. **Dungeon POI placeholder** — emit "sealed entrance" flavor text (meaningful WK57 hook)
7. **HUD interaction toasts** — contextual messages for all 7 interaction types
8. **Test coverage** — unit tests for all enhanced handlers
9. **QA gate** — `python tools/qa_smoke.py --quick` MUST PASS

### Out of scope
- Interior overlay for enterable POIs (moved to WK57/58 — needs visual verification)
- Compound prefab schema v0.6 (defer to WK58 polish sprint)
- Runtime mesh merging (defer to WK58)
- Underground vertical stacking (WK57)
- Multi-phase boss encounters (WK58)
- Zone fog tinting (WK58)
- New POI types beyond existing 12

---

## Technical Design

### Combat POI Enemy Spawning

When `_handle_combat` fires, spawn enemies at the POI location:
- Use existing enemy classes from `game/entities/enemy.py`
- Enemy count: `max(2, difficulty_tier)` enemies
- Enemy types by zone: match the zone's `enemy_palette` if available, else use generic (Goblin/Bandit)
- Spawn position: random offsets within POI footprint (±1 tile from center)
- After spawning, mark `poi.is_interacted = True` so it doesn't re-trigger
- Enemies are added via the `boss_spawned` or `poi_combat_triggered` event pattern

Key constraint: `_handle_combat` currently only has access to `hero, poi, world, economy, event_bus, cooldown_key`. Enemy spawning requires the enemy list or sim reference. The event bus approach (emit + sim picks up) is the cleanest path — sim_engine already listens for `boss_spawned`.

### Knowledge POI Cascade Reveal

When `_handle_knowledge` fires:
1. Reveal fog in 15-tile radius (already works)
2. Find nearest undiscovered POI within 15 tiles of THIS POI
3. Set that POI's `is_discovered = True` and emit discovery event
4. This creates a "chain discovery" mechanic — finding a gravestone might reveal a nearby cave

### Shrine Buff

When `_handle_shrine` fires:
1. Heal to full HP (already works)
2. Apply a temporary attack buff: `hero.apply_or_refresh_buff(...)` if available
3. Buff values: tier 1 → +2 ATK for 90s, tier 3 → +3 ATK, tier 5 → +5 ATK
4. Fallback if buff system not available: directly increment hero.attack temporarily

### Loot Scaling

Scale gold by `difficulty_tier`:
```
tier 1: 20-50 gold (unchanged)
tier 2: 40-80 gold
tier 3: 60-120 gold
tier 4: 80-160 gold
tier 5: 100-200 gold
```
Formula: `base_min = 20 * tier`, `base_max = 50 * tier * 0.8`

### HUD Interaction Toasts

The HUD already handles discovery toasts. Add interaction toasts using the same mechanism:
- Listen for `poi_interaction` events on the event bus
- Format message by interaction type:
  - shrine: "[HeroName] prayed at [POI]. HP restored!"
  - loot: "[HeroName] found treasure! +[gold] gold"
  - combat: "Enemies emerge from [POI]!"
  - knowledge: "[HeroName] reads ancient text. A hidden location is revealed!"
  - npc: "A hermit beckons [HeroName] closer..."
  - dungeon: "[HeroName] peers into the darkness..."
  - boss: "[BossName] appears at [POI]!"

---

## Waves

### Wave 1 — Interaction Handler Enhancement

**File:** `game/systems/poi_interaction.py`
**Role:** Agent 05 (Gameplay Systems)

Enrich all 7 interaction handlers:

1. `_handle_combat`: Emit `poi_combat_triggered` with `spawn_count` and `enemy_types` in payload. Add spawn info derived from `poi_def.difficulty_tier`.
2. `_handle_knowledge`: After fog reveal, find nearest undiscovered POI within 15 tiles, set `is_discovered = True`, emit discovery event for it.
3. `_handle_shrine`: After heal, apply temp buff via hero if `apply_or_refresh_buff` exists. Buff: `+2 * ceil(tier/2)` ATK for 90 seconds.
4. `_handle_loot`: Scale gold by tier: `min = 20 * tier`, `max = 40 + 10 * tier`. Round to int.
5. `_handle_npc`: Emit event with `narrative` field containing flavor text from `poi_def.description`.
6. `_handle_dungeon`: Emit event with `narrative` field: "The entrance is dark and sealed. Something stirs below."
7. All handlers: Ensure event payload includes `hero_name`, `poi_name`, `interaction_type` for HUD consumption.

**Acceptance:**
- `_handle_combat` event payload includes `spawn_count >= 2`
- `_handle_knowledge` discovers at least one nearby undiscovered POI (when one exists)
- `_handle_shrine` calls buff system when available
- `_handle_loot` gold scales with tier (tier 3 gives more than tier 1)
- All events include hero_name, poi_name, interaction_type

### Wave 2 — Sim Engine Combat Wiring

**File:** `game/sim_engine.py`
**Role:** Agent 05 (Gameplay Systems)

Wire the `poi_combat_triggered` event to actually spawn enemies:

1. In `SimEngine.__init__`, register an event listener for `poi_combat_triggered`
2. Handler creates enemies at POI location using existing enemy classes
3. Enemy count from event payload `spawn_count`
4. Enemy type: pick from common types (Goblin, Bandit, Skeleton) based on difficulty tier
5. Add spawned enemies to `self.enemies` list
6. Enemies appear at random positions within POI footprint

**Acceptance:**
- When hero walks to an Abandoned Camp (combat POI), 2+ enemies appear near the POI
- Enemies are alive, targetable, and participate in normal combat
- POI marked `is_interacted = True` — enemies don't re-spawn on subsequent visits

### Wave 3 — HUD Interaction Toasts

**File:** `game/ui/hud.py`
**Role:** Agent 08 (UX/UI)

Add interaction feedback using existing toast/notification system:

1. In the HUD's event handling, listen for `poi_interaction`, `poi_combat_triggered`, `boss_spawned` events
2. Format contextual toast messages per interaction type
3. Use existing `_notify_poi_toast` or `show_toast` method pattern
4. Toast color matches minimap icon color for the POI type

**Acceptance:**
- Player sees "Elena found treasure! +35 gold" when a hero loots a cache
- Player sees "Gareth prayed at Shrine. HP restored!" for shrines
- Player sees "Enemies emerge from the Abandoned Camp!" for combat POIs
- Toasts don't stack/overlap with discovery toasts

### Wave 4 — Tests & QA

**Files:** `tests/test_poi_interaction.py` (new), `tests/test_ai_poi_awareness.py` (existing)
**Role:** Agent 11 (QA)

1. Write unit tests for enhanced interaction handlers:
   - Test loot gold scales by tier
   - Test shrine calls buff method when available
   - Test knowledge handler discovers nearby POI
   - Test combat handler emits spawn_count in event
   - Test all events include hero_name, poi_name, interaction_type
2. Run `python tools/qa_smoke.py --quick` — MUST PASS
3. Run `python -m pytest tests/test_poi_interaction.py tests/test_ai_poi_awareness.py -v`
4. Verify no import errors or circular dependencies

**Acceptance:**
- All new tests pass
- qa_smoke passes
- No regressions in existing POI awareness tests

---

## Definition of Done

1. All 7 interaction handlers produce meaningful gameplay effects (not stubs)
2. Combat POIs spawn enemies when hero interacts
3. Knowledge POIs cascade-discover nearby hidden POIs
4. Shrine POIs heal + grant temporary attack buff
5. Loot POIs scale gold with difficulty tier
6. HUD shows contextual toast for every interaction type
7. Unit tests exist and pass for all enhanced handlers
8. `python tools/qa_smoke.py --quick` PASSES
9. No regressions in existing POI tests

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Enemy spawning at POIs may collide with lair spawner | POI combat is one-time (is_interacted gate), not ongoing like lairs |
| Buff system may not have the interface we expect | Fallback: skip buff, just heal (already works) |
| HUD toast stacking (interactions + discoveries at once) | Use existing toast queue with delay between messages |
| Knowledge cascade may create infinite chain | Only discover 1 nearest POI per knowledge interaction, and only undiscovered ones |

---

## Human Gate

After all waves complete, Jaimie playtests:
```powershell
python main.py
```

Walk heroes toward POI locations. Confirm:
- Combat POI: enemies appear, fight happens
- Shrine: hero heals, toast appears
- Treasure Cache: gold awarded, toast shows amount
- Knowledge POI: nearby hidden POI gets discovered
- All interactions produce HUD toasts

---

## Files Touched

| File | Owner | Change |
|------|-------|--------|
| `game/systems/poi_interaction.py` | Wave 1 | Enhance all 7 handlers |
| `game/sim_engine.py` | Wave 2 | Wire combat event → enemy spawning |
| `game/ui/hud.py` | Wave 3 | Interaction toast messages |
| `tests/test_poi_interaction.py` | Wave 4 | New test file |
| `tests/test_ai_poi_awareness.py` | Wave 4 | Verify no regressions |
