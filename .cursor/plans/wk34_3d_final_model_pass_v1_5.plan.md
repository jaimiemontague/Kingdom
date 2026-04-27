# WK34 Sprint Plan — Final 3D Model Pass (Pre-v1.5)

**Sprint Phase:** 3D Graphics Phase 2.6
**Commit convention:** `3D Graphics Phase 2.6: <description>`
**Primary QA gate:** `python tools/qa_smoke.py --quick` + `python tools/validate_assets.py --report` must both pass before the sprint is closed.

---

## Overview

This is the final content and model sprint before v1.5. It covers:

1. **Nature scatter scale-up** — grass, rocks, and other env props 4× larger  
2. **New and updated guild prefabs** — Ranger, Rogue, Wizard get 20%/50% construction stages; Ranger gets a full model rework  
3. **Guardhouse** — full new model + plot + 20%/50% construction stages  
4. **Temple (renamed from "Temple Agrela")** — rename, new model + plot + 20%/50% stages + Cleric unit bug-fix  
5. **Building Line-of-Sight** — all permanent player-built buildings reveal 3 tiles of fog  
6. **Farm/House/Food Stand spawn rebalance** — farms at half rate, first 2 of 4 food stands spawn near market
7. **Market loitering fix** — heroes spend too long in the Marketplace  
8. **Remove deprecated buildings** from the buildable roster (Gnome Hovel, Elven Bungalow, Dwarven Settlement, Ballista Tower, Wizard Tower, Fairgrounds, Library, Royal Gardens)

---

## Agent Assignments

| Agent | Role | Tasks |
|-------|------|-------|
| **Agent 15 (Art Director / Kitbash)** | Build all new/updated prefab JSONs | Nature scale, Ranger/Rogue/Wizard 20+50 stages, Guardhouse full set, Temple full set |
| **Agent 03 (Tech Director / Renderer)** | Wire prefabs into renderer + FOW update | Loader map updates, building LoS, Temple/Cleric renderer |
| **Agent 07 (Game Logic / Simulation)** | Simulation changes | Temple rename + Cleric unit, farm/house rebalance, food stand market proximity, market time fix, remove buildings |
| **Agent 05 (QA / Footprint Audit)** | Footprint verification + smoke gate | Verify every new prefab's `footprint_tiles` vs `config.py BUILDING_SIZES`, run smoke + validate_assets |

---

## Detailed Tasks by Agent

---

### AGENT 15 — Kitbash Lead (Prefab JSON Authoring)

**Your context:** Prefabs live in `assets/prefabs/buildings/`. Each building has up to three stage files:
- `<type>_v1.json` — fully constructed model
- `<type>_build_20_v1.json` — 20% construction stage (just a plot + barely started frame)
- `<type>_build_50_v1.json` — 50% construction stage (mid-construction)

The assembler is `python tools/model_assembler_kenney.py`. The viewer is `python tools/model_viewer_kenney.py`.

**Before picking any pieces, review the kit PNG overview sheets:**  
`assets/models/Fantasy Town Kit.PNG`, `Retro Fantasy Kit.PNG`, `Nature Part 1–4.PNG`, `Graveyard Kit.PNG`, `Survival Kit.PNG`

Pieces are resolved by path in the prefab JSON like:
```json
"model": "Models/GLB format/tower-round.glb"
```
For Nature Kit pieces (no texture, factor-only colors):
```json
"model": "Models/GLTF format/rock_1.glb"
```

**Schema reminder (assets/prefabs/schema.md):** Every JSON needs `footprint_tiles`, `schema_version: "0.2"`, and a `pieces` array. `scale` on each piece is the authored scale in the assembler; the renderer applies a fit-multiplier at runtime to make it fill the footprint. Do NOT set per-type scales in the renderer — use the prefab JSON.

---

#### Task 15-A: Nature Scatter — 4× Scale-Up

**What to do:** Open `game/graphics/ursina_renderer.py` and find the constants at the top of the file (around lines 68–73):

```python
TREE_SCALE_MULTIPLIER = 1.15
ROCK_SCALE_MULTIPLIER = 0.42
GRASS_SCATTER_SCALE_MULTIPLIER = 0.52
```

Change them to:

```python
TREE_SCALE_MULTIPLIER = 4.6      # 4× of original 1.15
ROCK_SCALE_MULTIPLIER = 1.68     # 4× of original 0.42
GRASS_SCATTER_SCALE_MULTIPLIER = 2.08  # 4× of original 0.52
```

**Verify:** Launch `python main.py --renderer ursina --no-llm`, pan around the meadow. Trees, rocks, and grass clumps should appear noticeably bigger/chunkier relative to the ground tiles and buildings. They should not clip through buildings or block visibility in a way that feels broken. If any prop is enormous, reduce its multiplier by 25% and note in your agent log.

---

#### Task 15-B: Ranger Guild — Model Rework + 20% and 50% Stages

The existing `ranger_guild_v1.json` is a placeholder using Survival Kit tent/canvas pieces. It needs a proper camp/outpost feel. Use Retro Fantasy or Survival Kit pieces to build a scouting outpost with:
- A compact wooden structure (use `wall-half.glb`, `wall-door.glb`, `roof-corner.glb` from Retro Fantasy)
- An optional archery target prop or flag (use `structure-canvas.glb` or `tool-*` from Survival Kit as a prop)

Footprint is **2×2** tiles (matches existing `ranger_guild` in `config.py BUILDING_SIZES`).

**New files to create:**
- `assets/prefabs/buildings/ranger_guild_v1.json` ← **overwrite** the weak existing one
- `assets/prefabs/buildings/ranger_guild_build_20_v1.json` ← 20% stage: just `plot_2x2_v1` pieces + 1–2 raw posts/logs to indicate ground-breaking
- `assets/prefabs/buildings/ranger_guild_build_50_v1.json` ← 50% stage: walls up, no roof yet

For the **20% stage**, follow the pattern from `warrior_guild_build_20_v1.json` — just the plot planks + a few upright posts. Example structure:
```json
{
  "schema_version": "0.2",
  "prefab_id": "ranger_guild_build_20_v1",
  "footprint_tiles": [2, 2],
  "pieces": [
    { "model": "Models/GLB format/wood-floor-fantasy-town.glb", "position": [0.0, 0.0, 0.0], "rotation": [0,0,0], "scale": [1.0, 0.2, 1.0] },
    { "model": "Models/GLB format/poles-fantasy-town.glb", "position": [-0.4, 0.1, -0.4], "rotation": [0,0,0], "scale": [0.4, 0.4, 0.4] }
  ]
}
```
(Adjust models and positions as needed for visual fit.)

For the **50% stage,** walls are up but no roof — think open-topped skeleton of the building.

---

#### Task 15-C: Rogue Guild — 20% and 50% Stages

The existing `rogue_guild_v1.json` is already present. It just needs construction stages.

Footprint is **2×2** tiles.

**Files to create:**
- `assets/prefabs/buildings/rogue_guild_build_20_v1.json` — plot + corner stakes
- `assets/prefabs/buildings/rogue_guild_build_50_v1.json` — walls roughed in, no roof

Same approach as Ranger Guild 20/50 stages above. The 20% can reuse plot planks and a few poles. The 50% should show the beginnings of the darker, shadowy aesthetic that fits the rogue theme — think dark timber wall sections.

---

#### Task 15-D: Wizard Guild — 20% and 50% Stages

The existing `wizard_guild_v1.json` is present. Create construction stages.

Footprint is **2×2** tiles.

**Files to create:**
- `assets/prefabs/buildings/wizard_guild_build_20_v1.json` — plot + a lone arcane pillar or stone base to suggest magic ground-breaking
- `assets/prefabs/buildings/wizard_guild_build_50_v1.json` — partial stone tower rising from the ground, no top

For the 50% stage, use `tower-round.glb` or `wall-fortified-*.glb` from Retro Fantasy at partial height (scale Y to ~0.5) to show a tower under construction.

---

#### Task 15-E: Guardhouse — Full New Model + Plot + 20%/50% Stages

**Concept:** A retro painted-tower model with a watchtower top. Think castle guard post — a short stone-walled enclosure with a round tower section on top.

Footprint: **2×2** tiles. (Guardhouse is currently `(1,1)` in `config.py` — update it to `(2,2)` as part of Task 07-D.)

**Recommended pieces from Retro Fantasy Kit:**
- Base: `wall-fortified-corner.glb` × 4 (one per corner), `wall-fortified.glb` for the walls
- Tower top: `tower-round.glb` centered on top — scale it ~0.6–0.7 to sit as a cap, not overwhelm the base
- Optional: `battlement.glb` along the top edge of the perimeter walls for that classic guard look

**Files to create:**
- `assets/prefabs/buildings/guardhouse_v1.json` — full model
- `assets/prefabs/buildings/guardhouse_build_20_v1.json` — plot (`plot_2x2_v1` pieces) + corner stakes
- `assets/prefabs/buildings/guardhouse_build_50_v1.json` — stone walls roughed in, no tower top yet

---

#### Task 15-F: Temple — Full New Model + Plot + 20%/50% Stages

**Concept:** A simple but dignified temple — a small stone building with a prominent peaked/gabled roof and steps at the front. Retro Fantasy Kit is ideal.

Footprint: **2×2** tiles.

**Recommended pieces:**
- Base walls: `wall.glb` × 4 sides, `wall-door.glb` for the front entrance
- Roof: `roof-high.glb` or `roof-gable.glb` from Retro Fantasy (centered on top)
- Steps: `stairs-stone.glb` at the entrance (front-center, slightly offset in Z)
- Optional: `pillar-stone-fantasy-town.glb` × 2 flanking the entrance for grandeur

**Files to create:**
- `assets/prefabs/buildings/temple_v1.json`
- `assets/prefabs/buildings/temple_build_20_v1.json` — plot + foundation stones
- `assets/prefabs/buildings/temple_build_50_v1.json` — walls up, no roof

**Note to Agent 15:** The building type key in the renderer will be `"temple"` (not `"temple_agrela"`) after Agent 07 renames it. Use `prefab_id: "temple_v1"` in the JSON. Agent 03 will register `"temple": "temple_v1.json"` in the renderer's lookup table.

---

### AGENT 03 — Tech Director (Renderer + Engine Integration)

**Your context:** The renderer is `game/graphics/ursina_renderer.py`. The prefab type-to-file lookup is `_PREFAB_BUILDING_TYPE_TO_FILE` (around line 127). Building fog-of-war vision is in `game/engine.py` `_update_fog_of_war()` (around line 265). The `NEUTRAL_VISION` dict currently only covers neutral buildings (`house`, `farm`, `food_stand`). All `is_constructed == True` player buildings also need 3-tile reveal.

---

#### Task 03-A: Register New Prefabs in Renderer Lookup

In `game/graphics/ursina_renderer.py`, find `_PREFAB_BUILDING_TYPE_TO_FILE` (line ~127). Add entries for the new buildings:

```python
_PREFAB_BUILDING_TYPE_TO_FILE: dict[str, str] = {
    # existing entries unchanged ...
    "ranger_guild": "ranger_guild_v1.json",    # overwrite existing
    "temple": "temple_v1.json",                 # NEW (renamed from temple_agrela)
    "guardhouse": "guardhouse_v1.json",         # NEW
}
```

The convention-based fallback (`<building_type>_v1.json`) already handles `rogue_guild` and `wizard_guild`, so they don't need explicit entries — they'll resolve automatically once Agent 15 creates the prefab files.

**Construction stage mapping:** The renderer resolves 20%/50% stage prefabs via a `_resolve_construction_prefab_path` function (or similar). Confirm that for any building type `X` with a `_build_20_v1.json` and `_build_50_v1.json` in the prefabs folder, those stages are loaded when `building.construction_progress` is below the thresholds. If this logic already exists generically for the convention-named files, no change is needed — just confirm it works for the new building types. If it requires explicit registration, add the new types.

---

#### Task 03-B: Building Line-of-Sight (FOW Reveal)

In `game/engine.py`, find `_update_fog_of_war()` (around line 265). Currently it reveals FOW around: Castle (10 tiles), Heroes (7 tiles), Guards (6 tiles), and a small set of neutral buildings.

Add a new loop that makes **all constructed player buildings** reveal 3 tiles around themselves:

```python
# WK34: All constructed player-placed buildings reveal 3 tiles (building LoS).
BUILDING_VISION_TILES = 3
for building in self.buildings:
    if not getattr(building, "is_constructed", False):
        continue
    if getattr(building, "hp", 1) <= 0:
        continue
    # Skip neutral buildings (house/farm/food_stand) — already handled above via NEUTRAL_VISION
    if getattr(building, "is_neutral", False):
        continue
    # Skip castle — already handled with a larger radius above
    btype = str(getattr(getattr(building, "building_type", None), "value",
                        getattr(building, "building_type", "")))
    if btype == "castle":
        continue
    revealers.append((building.center_x, building.center_y, BUILDING_VISION_TILES))
```

Insert this block **after** the existing neutral building block (around line 303) and **before** the guard block. The `revealers` list is what gets passed to `world.update_visibility()`.

**Important:** `building.center_x` and `building.center_y` are pixel coordinates, same as heroes and the castle. The `world.update_visibility(revealers)` function expects `(px_x, px_y, radius_in_tiles)` tuples — confirm this matches existing usage in the file before inserting.

---

#### Task 03-C: Temple Renderer / Prefab Registration 

After Agent 07 renames the building type to `"temple"`, the renderer needs to know:
1. `"temple"` maps to `temple_v1.json` — added in Task 03-A above.
2. Remove any legacy references to `"temple_agrela"` from the renderer. Search `ursina_renderer.py` for `temple_agrela` and update them to `temple`.

---

#### Task 03-D: Remove Deprecated Buildings from Renderer

Search `ursina_renderer.py` for any explicit handling of:
`gnome_hovel`, `elven_bungalow`, `dwarven_settlement`, `ballista_tower`, `wizard_tower`, `fairgrounds`, `library`, `royal_gardens`

If any are in `_PREFAB_BUILDING_TYPE_TO_FILE` or have special rendering branches, **remove those entries**. The renderer should gracefully fall back to a primitive (cube) for unknown types — this is the correct behavior for removed buildings so any pre-existing save data doesn't crash.

---

### AGENT 07 — Game Logic & Simulation

**Your context:** Building types are defined in `game/entities/buildings/types.py`. The building factory maps type strings to classes in `game/building_factory.py`. Input hotkeys are in `game/input_handler.py`. Config has `BUILDING_COSTS`, `BUILDING_SIZES`, `BUILDING_COLORS`, `BUILDING_PREREQUISITES` all in `config.py`. Spawn logic for neutral buildings is in `game/systems/neutral_buildings.py`. Hero task durations are in `ai/behaviors/task_durations.py`.

---

#### Task 07-A: Rename "Temple Agrela" → "Temple" + Add Cleric Unit

The game currently supports multiple temple types (`TEMPLE_AGRELA`, `TEMPLE_DAUROS`, etc.). For v1.5 we consolidate to a single **"Temple"** that spawns **Clerics**.

**Step 1 — Add `TEMPLE` to `BuildingType` enum** in `game/entities/buildings/types.py`:
```python
TEMPLE = "temple"
```
Keep the old `TEMPLE_AGRELA` through `TEMPLE_LUNORD` entries for now (don't remove them — they may still be in saved states or referenced elsewhere). We're just adding the new canonical one that the player can build.

**Step 2 — Add `Temple` class** in `game/entities/buildings/temples.py`:
```python
class Temple(HiringBuilding, Building):
    """Temple — recruits Clerics (healers)."""

    def __init__(self, grid_x: int, grid_y: int):
        super().__init__(grid_x, grid_y, BuildingType.TEMPLE)
        self._init_hiring_state()
```

**Step 3 — Register in `game/building_factory.py`:**
Add to `BUILDING_REGISTRY`:
```python
"temple": Temple,
```
Import `Temple` at the top alongside the other temple imports.

**Step 4 — Register in config.py:**
In `BUILDING_COSTS` dict, add: `"temple": 400`  
In `BUILDING_SIZES` dict, add: `"temple": (2, 2)`  
In `BUILDING_COLORS` dict, add: `"temple": (220, 200, 150)`  (warm stone color)
In `BUILDING_PREREQUISITES` dict, add: `"temple": []`  (no prerequisite)

**Step 5 — Add 'T' hotkey** in `game/input_handler.py`.  
Find the section that handles keyboard building placement (around line 241 where `gnome_hovel` was). Add:
```python
if event.key == 't':
    self.select_building_for_placement("temple")
    return
```
(The 'T' key was previously used for `template_agrela` if at all — confirm there's no conflict.)

**Step 6 — Fix Cleric spawn bug:** The bug is that `TempleAgrela` (and now `Temple`) calls `HiringBuilding._init_hiring_state()` but the engine's `try_hire_hero()` method maps guild type → hero class. Find `try_hire_hero()` in `game/engine.py` (around line 543) — it has a `class_by_guild` dict. Add:
```python
class_by_guild = {
    # ... existing entries ...
    "temple": HeroClass.CLERIC.value,  # or the appropriate class string
}
```
If `HeroClass.CLERIC` doesn't exist yet, check `game/entities/hero.py` for the `HeroClass` enum and add `CLERIC = "cleric"` if missing. The hero class string `"cleric"` is what gets passed to `Hero.__init__()`. Confirm `Hero` can be instantiated with `hero_class="cleric"` — it should since `hero_class` is stored as a plain string.

The **spawn count showing 0** bug is likely because the engine only tracks heroes in `self.heroes` if `hero.guild` matches a recognized building. Confirm that `hire_hero()` (or however the engine registers new heroes after the building hires them) adds them to `engine.heroes`. The building's own `heroes_housed` count is separate from `engine.heroes`. The reported "temple shows 0 heroes" is likely because `engine.heroes` is populated but the panel reads `building.heroes_housed` — check `game/ui/hero_panel.py` or `game/ui/building_panel.py` for how the count is displayed and that `TempleAgrela`/`Temple` properly calls `_init_hiring_state()` and that `engine` registers the link.

---

#### Task 07-B: Farm/House Spawn Rebalance

In `game/systems/neutral_buildings.py`, find the `tick()` method (line 172). The current spawn priority is:
1. Houses (1 per hero)
2. Food stands (1 per 3 heroes)  
3. Farms (1 per hero)

**Change:** Farms should spawn at **half the rate** — change `want_farms` to 1 per 2 heroes:

```python
# Before:
want_farms = max(0, hero_count)

# After (WK34: farms at half rate to prioritize houses):
want_farms = max(0, hero_count // 2)
```

This single line change means for 4 heroes: 4 houses, 1 food stand, 2 farms (instead of 4 farms).

---

#### Task 07-C: First 2 Food Stands Near Market

In `game/systems/neutral_buildings.py`, the current food stand placement uses `_find_spot()` with `min_r=3, max_r=18` radius from the castle. We need the first 2 food stands to spawn within 2–3 tiles of the nearest Marketplace instead.

Add a helper method to `NeutralBuildingSystem`:

```python
def _find_marketplace(self, buildings: list):
    """Return the first constructed marketplace, or None."""
    for b in buildings:
        bt = str(getattr(getattr(b, "building_type", None), "value",
                         getattr(b, "building_type", "")))
        if bt == "marketplace" and getattr(b, "is_constructed", False):
            return b
    return None
```

Then modify the food stand spawn block inside `tick()`:

```python
if cur_food < want_food:
    market = self._find_marketplace(buildings)
    # First 2 food stands: try to place near the market (2–3 tiles away)
    if cur_food < 2 and market is not None:
        # Build a fake "castle" proxy pointing at the market center tile
        market_cx = getattr(market, "grid_x", 0) + getattr(market, "size", (1,1))[0] // 2
        market_cy = getattr(market, "grid_y", 0) + getattr(market, "size", (1,1))[1] // 2

        class _MarketProxy:
            grid_x = market_cx
            grid_y = market_cy
            size = (1, 1)

        spot = self._find_spot(
            castle=_MarketProxy(),
            buildings=buildings,
            size=(1, 1),
            min_r=2,
            max_r=3,
            shuffle_within_ring=True,
        )
    else:
        spot = self._find_spot(
            castle=castle,
            buildings=buildings,
            size=(1, 1),
            min_r=3,
            max_r=18,
            shuffle_within_ring=True,
        )
    if spot:
        buildings.append(FoodStand(*spot))
    return
```

This ensures the first 2 food stands try the ring 2–3 tiles around the market first, and only if no spot is found there do they fall back to the standard castle-relative placement.

---

#### Task 07-D: Market Loitering Fix

In `ai/behaviors/task_durations.py`, the current `"buy_potion"` task duration is `(3, 6)` seconds and `"shopping"` is `(4, 8)` seconds. These seem reasonable on their own but heroes may loop multiple purchase cycles.

Find the AI decision code that determines how long heroes stay in the marketplace. Search `ai/` for `marketplace` and `shopping`:

```powershell
Select-String -Path "ai/**/*.py" -Pattern "marketplace|shopping|buy_weapon|buy_armor|buy_potion" -Recurse
```

The likely culprits are:
1. **Task duration too high** — reduce `"buy_weapon": (6, 12)` → `(4, 7)` and `"buy_armor": (8, 14)` → `(5, 9)` in `task_durations.py`
2. **Heroes re-entering after exiting** — find the AI behavior that decides whether to shop again and increase the cooldown or add a "shopped recently" flag

Update `ai/behaviors/task_durations.py`:
```python
TASK_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "buy_potion": (3, 6),
    "buy_weapon": (4, 7),    # was (6, 12)
    "buy_armor":  (5, 9),    # was (8, 14)
    "shopping":   (3, 6),    # was (4, 8)
    "research":   (10, 15),
    "rest_inn":   (10, 20),
    "get_drink":  (8, 15),
}
```

Also search in `ai/behaviors/` for any `SHOPPING_COOLDOWN` or re-entry logic and increase it. If there is a `min_time_between_shops` or similar, double it.

---

#### Task 07-E: Remove Deprecated Buildings from Player Build Menu

The following buildings must be removed from the player-accessible build menu. They should stay in the codebase as dead code (do not delete the classes — they may still exist in older save states, and we'll re-add them in a future sprint). Just prevent the player from building them.

**In `game/input_handler.py`**, find and **remove or comment out** the hotkey bindings for:
- `gnome_hovel` (key G)
- `elven_bungalow` (key E)
- `dwarven_settlement` (key V)  
- `ballista_tower` (key Y)
- `wizard_tower` (key O)
- `fairgrounds` (key F)
- `library` (key I)
- `royal_gardens` (key R)

Replace the comment block describing those keys with a `# REMOVED in WK34 — will return in future sprint` comment.

**In `game/engine.py`**, find the building update loop (around line 1086) which has special-case `elif` branches for `ballista_tower`, `wizard_tower`, `fairgrounds`. Comment those out with `# WK34 REMOVED — re-enable when re-added` since those buildings can no longer be placed. The engine should not crash if they somehow exist (from old states), so keep the logic but wrapped in a guard:

```python
# WK34: These buildings are temporarily removed from the build menu.
# Keep update logic in case they appear in legacy save data.
elif building.building_type == "ballista_tower" and hasattr(building, "update"):
    building.update(dt, self.enemies)
```

(Keeping the update logic prevents crashes for any pre-existing sessions.)

**In `config.py`**, set `BUILDING_COSTS` for each removed building to `0` and add a comment `# WK34 REMOVED`. This prevents the economy system from referencing a non-zero cost for a building the player can't place. Do not remove the `BUILDING_SIZES` entries — they may be read by save/load code.

**In the `game/ui/build_catalog_panel.py` or equivalent panel** (wherever the build UI grid is rendered), filter out the removed building types from the displayed grid. If there is a `BUILDABLE_TYPES` list or equivalent, remove the 8 deprecated types from it. If the catalog is generated from `BUILDING_COSTS` > 0, the zeroing in config.py above may handle this automatically — check and confirm.

---

#### Task 07-F: Fix Guardhouse Footprint in Config

Change `game/config.py`:
```python
# In BUILDING_SIZES:
"guardhouse": (2, 2),   # was (1, 1) — updated for new tower model
```

Also update `BUILDING_COSTS`:
```python
"guardhouse": 300,   # unchanged unless you want to adjust
```

---

### AGENT 05 — QA / Footprint Audit Lead

**Your context:** You are the final gate before this sprint closes. Your job is to:
1. Verify every new prefab's `footprint_tiles` matches `config.py BUILDING_SIZES`
2. Run the smoke test and asset validator
3. Document pass/fail in your agent log

---

#### Task 05-A: Prefab Footprint Audit

For each new/modified prefab, open the JSON and confirm `footprint_tiles` matches:

| Building | Expected `footprint_tiles` | Config `BUILDING_SIZES` |
|----------|---------------------------|------------------------|
| `ranger_guild_v1.json` | `[2, 2]` | `ranger_guild: (2, 2)` |
| `rogue_guild_v1.json` | `[2, 2]` | `rogue_guild: (2, 2)` |
| `wizard_guild_v1.json` | `[2, 2]` | `wizard_guild: (2, 2)` |
| `guardhouse_v1.json` | `[2, 2]` | `guardhouse: (2, 2)` (updated by Agent 07) |
| `temple_v1.json` | `[2, 2]` | `temple: (2, 2)` (added by Agent 07) |

All `_build_20_v1` and `_build_50_v1` files for each type must have the same `footprint_tiles` as the completed building.

---

#### Task 05-B: QA Gate — Smoke Test + Asset Validation

Run the following after all code changes are merged:

```powershell
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Both must exit with code 0. If any test fails:
1. Identify the failing test
2. If it's a missing asset (new prefab JSON references a model path that doesn't exist), flag Agent 15 to fix the path
3. If it's a Python error (import, attribute, crash), flag Agent 07 or Agent 03 for the appropriate fix
4. Do NOT close the sprint until both commands pass

---

#### Task 05-C: In-Game Visual Spot Check

Launch `python main.py --renderer ursina --no-llm` and verify:

1. **Nature props**: Trees, rocks, grass clumps are visibly 4× larger than before — they should read as real environmental features, not tiny decorations
2. **Ranger Guild**: The new model looks like a scouting outpost, not a tent city
3. **Guardhouse**: The tower model is visible; it has a tower top; it sits on a 2×2 footprint
4. **Temple**: Visible as a small stone temple with a gabled roof
5. **FOW/Buildings**: After placing a Warrior Guild and letting it finish construction, pan the camera far away — the 3 tiles around the guild should remain revealed (light grey "explored" tone, not black)
6. **Cleric hiring**: Build a Temple, wait for construction, press H near it — a Cleric hero should spawn and appear in `engine.heroes`; the Temple's hero count in the building panel should show > 0
7. **Farms**: Observe over 2–3 minutes of game time. Houses should spawn more frequently than farms (roughly 2:1 ratio)
8. **Food stands near market**: Build a Marketplace and wait — the first food stand or two should appear in the tiles immediately adjacent to or very near the market, not randomly scattered far away
9. **Removed buildings**: Press G, E, V, Y, O, F, I, R — none should start a building placement mode; if the game previously assigned those keys to other functions, confirm no unintended behavior

---

## Execution Order & Dependencies

```
Agent 15 (all prefab JSONs) → Agent 03 (loader wiring + FOW)
                             → Agent 05 (footprint audit after 15 + 03 complete)

Agent 07 (all sim changes)  → Agent 05 (smoke gate after 07 complete)
```

All Agent 15 tasks can run in parallel with all Agent 07 tasks.  
Agent 03 tasks 03-A and 03-B can start once Agent 07 confirms `BuildingType.TEMPLE` is ready.  
Agent 05 runs final audits after all other agents finish.

---

## Files Changed Summary

| File | Agent | Change |
|------|-------|--------|
| `game/graphics/ursina_renderer.py` | 03, (15 for scale) | Nature scale multipliers, prefab map additions, remove deprecated renderer branches, temple_agrela → temple |
| `game/engine.py` | 03, 07 | Building LoS in `_update_fog_of_war()`, comment out deprecated building update branches |
| `game/entities/buildings/types.py` | 07 | Add `TEMPLE = "temple"` |
| `game/entities/buildings/temples.py` | 07 | Add `Temple` class |
| `game/building_factory.py` | 07 | Register `"temple": Temple` |
| `config.py` | 07 | Add temple to COSTS/SIZES/COLORS/PREREQS; guardhouse size 2×2; zero costs for removed buildings |
| `game/input_handler.py` | 07 | Add T→temple hotkey, remove/comment deprecated hotkeys |
| `game/systems/neutral_buildings.py` | 07 | Farm rate halved; food stand near-market placement |
| `ai/behaviors/task_durations.py` | 07 | Reduce buy_weapon, buy_armor, shopping durations |
| `assets/prefabs/buildings/ranger_guild_v1.json` | 15 | Overwrite with new model |
| `assets/prefabs/buildings/ranger_guild_build_20_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/ranger_guild_build_50_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/rogue_guild_build_20_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/rogue_guild_build_50_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/wizard_guild_build_20_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/wizard_guild_build_50_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/guardhouse_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/guardhouse_build_20_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/guardhouse_build_50_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/temple_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/temple_build_20_v1.json` | 15 | NEW |
| `assets/prefabs/buildings/temple_build_50_v1.json` | 15 | NEW |

---

## Success Criteria

- [ ] `python tools/qa_smoke.py --quick` exits 0
- [ ] `python tools/validate_assets.py --report` exits 0
- [ ] Nature scatter props are visually 4× larger in Ursina view
- [ ] Ranger Guild has a distinct outpost/camp model (not tent placeholder)
- [ ] Ranger / Rogue / Wizard Guilds show graduated construction stages (plot → partial walls → complete)
- [ ] Guardhouse has a tower-with-top model on a 2×2 footprint, with construction stages
- [ ] Temple appears (renamed from "Temple Agrela"), has a model, has construction stages
- [ ] Temple spawns Cleric heroes when hired; Temple panel shows `heroes_housed > 0` after hiring
- [ ] All constructed player buildings reveal 3 tiles of fog around them
- [ ] Farms spawn roughly half as often as houses over a 5-minute game session
- [ ] The first 2 food stands appear near (2–3 tiles) the Marketplace when one is built
- [ ] Heroes leave the Marketplace in under 10 real-seconds of shopping per visit (at 1× speed)
- [ ] G, E, V, Y, O, F, I, R keys don't trigger any building placement
- [ ] No Python exceptions in the console during a 5-minute game session

---

## Notes for PM (Agent 01)

- The old temple classes (`TempleAgrela`, `TempleDauros`, etc.) are kept as dead code. Do **not** delete them — they protect against crashes if session data references them. We'll clean them up after v1.5 ships.
- `wizard_tower` and `ballista_tower` update logic is preserved in `engine.py` (commented, not deleted) for the same reason.
- The Cleric hero class may not have AI behavior tuned yet (it will inherit base hero behavior). This is acceptable for v1.5 — it means Clerics will act like generic heroes. AI behavior tuning for Clerics is a post-v1.5 task.
- A visual snapshot for this sprint should be taken with `python tools/model_viewer_kenney.py --screenshot-subdir wk34 --auto-exit-sec 5` after Agent 15 completes kitbashing, and committed alongside the prefab JSONs.
