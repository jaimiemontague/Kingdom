# WK61 Sprint Plan — Playtest Feedback: Polish, Balance & New Features

**Created:** 2026-05-20 | **PM:** Agent 01 | **Current version:** Prototype v1.5.8 (post-WK60 R1)
**Goal:** Address 13 items from Jaimie's first playtest of the WK60 "Make It Fun" features. Mix of bug fixes, balance tuning, and new features that make the game feel polished and fun.
**Plan doc:** `.cursor/plans/wk61_playtest_polish.plan.md`

---

## Playtest Feedback (Raw → Tickets)

| # | Jaimie's Note | Type | Ticket ID | Owner |
|---|---------------|------|-----------|-------|
| 1 | Names often showing reversed/backwards | Bug | WK61-BUG-001 | Agent 03 |
| 2 | Remove names from buildings | Feature | WK61-FEAT-001 | Agent 03 |
| 3 | Enemies should make sounds (wolves bark, spider hiss, etc.) | Feature | WK61-FEAT-002 | Agent 14 |
| 4 | Heroes spend too long in market — halve the time | Tuning | WK61-TUNE-001 | Agent 05 |
| 5 | Taxable gold should only show over buildings while holding "G" key | Feature | WK61-FEAT-003 | Agent 03 |
| 6 | Marketplace and blacksmith don't show taxable gold in building menus | Bug | WK61-BUG-002 | Agent 08 |
| 7 | Buildings indestructible at 0 HP — should destroy + leave rubble for 2 min | Bug+Feat | WK61-BUG-003 / WK61-FEAT-004 | Agent 05 (gameplay) + Agent 03 (rendering) |
| 8 | Add chat button to hero menu, popup below like on hero card | Feature | WK61-FEAT-005 | Agent 08 |
| 9 | Guardhouse should fire 2 arrows at a time | Tuning | WK61-TUNE-002 | Agent 05 |
| 10 | Click on enemies for an info menu where hero menu goes | Feature | WK61-FEAT-006 | Agent 08 |
| 11 | Heroes heal 5x faster in guild, 7x faster in inn | Tuning | WK61-TUNE-003 | Agent 05 |
| 12 | Enemies near town chase heroes away — should prioritize buildings | Feature | WK61-FEAT-007 | Agent 05 |
| 13 | Heroes too strong — reduce HP by 40% | Tuning | WK61-TUNE-004 | Agent 05 |

---

## Round Structure

### R1 — All Parallel (no cross-agent file collisions)

| Agent | Role | Intelligence | Items |
|-------|------|-------------|-------|
| **05** | GameplaySystemsDesigner | HIGH | #4, #7 (gameplay), #9, #11, #12, #13 |
| **03** | TechnicalDirector | HIGH | #1, #2, #5, #7 (rendering) |
| **08** | UX_UI_Director | MEDIUM | #6, #8, #10 |
| **14** | SoundDirector_Audio | MEDIUM | #3 |

### R2 — QA + Visual Consult (after R1)

| Agent | Role | Intelligence | Items |
|-------|------|-------------|-------|
| **11** | QA_TestEngineering | LOW | Full gate pass |
| **09** | ArtDirector | LOW | Visual cohesion review of rubble, enemy menus, gold overlay |

### File Ownership (no collisions)

| Agent | Edits These Files | Does NOT Edit |
|-------|-------------------|---------------|
| 05 | `config.py`, `game/entities/enemy.py`, `game/entities/hero.py`, `game/entities/buildings/defensive.py`, `game/entities/buildings/hiring_mixin.py`, `game/entities/buildings/economic.py`, `game/cleanup_manager.py`, `game/sim_engine.py`, `game/sim/snapshot.py`, `ai/behaviors/task_durations.py`, `game/entities/rubble.py` (new) | `game/graphics/*`, `game/ui/*`, `game/audio/*` |
| 03 | `game/graphics/ursina_renderer.py`, `game/graphics/ursina_units_anim.py` | `config.py`, `game/entities/*`, `game/ui/*` |
| 08 | `game/ui/*`, `game/input_handler.py` (enemy click routing only), `game/engine.py` (click selection only) | `game/graphics/ursina_renderer.py`, `game/entities/*`, `config.py` |
| 14 | `game/audio/*`, `assets/audio/*` | Everything else |

---

## Rubble Data Contract (shared between Agent 05 and Agent 03)

Agent 05 creates the data. Agent 03 renders it. Both work to this contract:

```python
# game/entities/rubble.py (NEW FILE — Agent 05 creates this)
from dataclasses import dataclass

@dataclass
class RubbleRecord:
    record_id: int        # unique ID (use incrementing counter)
    center_x: float       # world pixel position (same as building.center_x was)
    center_y: float       # world pixel position (same as building.center_y was)
    grid_x: int           # grid tile position
    grid_y: int           # grid tile position
    width_tiles: int      # footprint width in tiles (2 or 3)
    height_tiles: int     # footprint height in tiles (2 or 3)
    building_type: str    # e.g. "house", "farm", "warrior_guild"
    created_ms: int       # sim_now_ms() when rubble was spawned
    duration_ms: int = 120_000  # 2 minutes before rubble disappears
```

**Agent 05 provides:** `snapshot.rubble_records: tuple[RubbleRecord, ...]` in SimStateSnapshot.
**Agent 03 reads:** iterates `snapshot.rubble_records` in the renderer update loop. Creates/destroys entities based on record_id presence.

---

## Agent 05 — GameplaySystemsDesigner (HIGH Intelligence)

You own 6 items: config tuning (#4, #9, #11, #13), building destruction (#7 gameplay side), and enemy AI (#12).

### FILES YOU EDIT
- `config.py`
- `ai/behaviors/task_durations.py`
- `game/entities/buildings/defensive.py`
- `game/entities/buildings/hiring_mixin.py`
- `game/entities/buildings/economic.py`
- `game/entities/hero.py`
- `game/entities/enemy.py`
- `game/cleanup_manager.py`
- `game/sim_engine.py`
- `game/sim/snapshot.py`
- `game/entities/rubble.py` (NEW — you create this)

### FILES YOU DO NOT EDIT
- `game/graphics/*` (Agent 03 owns rendering)
- `game/ui/*` (Agent 08 owns UI)
- `game/audio/*` (Agent 14 owns audio)

---

### Item #13 — Hero HP -40% (WK61-TUNE-004)

**What:** Reduce all hero base HP from 100 to 60.

**File:** `config.py`, HeroConfig class (line ~48)

**Change:**
```python
# BEFORE:
base_hp: int = 100

# AFTER:
base_hp: int = 60
```

All hero classes share this single `base_hp` value — there are no per-class HP overrides. The change propagates everywhere via the `HERO_BASE_HP` alias.

**Note:** Heroes gain +20 HP per level-up (hero.py line 660). At level 1 a hero has 60 HP; at level 3 it has 100 HP (same as the old base). This makes early heroes fragile but experienced heroes tough — good gameplay.

**Verify:**
```powershell
python -c "from config import HERO_BASE_HP; print(f'HERO_BASE_HP = {HERO_BASE_HP}')"
# Expected: HERO_BASE_HP = 60
```

---

### Item #4 — Market Visit Duration Halved (WK61-TUNE-001)

**What:** Heroes spend too long shopping. Halve all marketplace/blacksmith visit durations.

**File:** `ai/behaviors/task_durations.py`, lines 8-16

**Change:**
```python
# BEFORE:
TASK_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "buy_potion": (3, 6),
    "buy_weapon": (4, 7),
    "buy_armor": (5, 9),
    "shopping": (3, 6),
    ...
}

# AFTER:
TASK_DURATION_RANGES: dict[str, tuple[int, int]] = {
    "buy_potion": (2, 3),
    "buy_weapon": (2, 4),
    "buy_armor": (3, 5),
    "shopping": (2, 3),
    ...
}
```

Leave `"research"`, `"rest_inn"`, and `"get_drink"` unchanged — those are non-market activities.

**Verify:**
```powershell
python -c "from ai.behaviors.task_durations import TASK_DURATION_RANGES as T; print({k: T[k] for k in ('buy_potion','buy_weapon','buy_armor','shopping')})"
# Expected: all ranges roughly halved
```

---

### Item #9 — Guardhouse Fires 2 Arrows (WK61-TUNE-002)

**What:** Guardhouse should fire 2 arrows per volley instead of 1.

**File:** `config.py` — add new config value:
```python
GUARDHOUSE_ARROWS_PER_SHOT = 2
```

**File:** `game/entities/buildings/defensive.py`, Guardhouse class, `update()` method.

Currently (lines ~55-81), the guardhouse finds the nearest enemy and fires ONE projectile. Change it to fire `GUARDHOUSE_ARROWS_PER_SHOT` projectiles in a loop.

**Current code pattern** (approximate):
```python
# In Guardhouse.update():
if best_target and elapsed >= self.arrow_cooldown_sec:
    best_target.take_damage(self.arrow_damage)
    self._last_arrow_time = now
    # ... stores one ranged_projectile event
```

**New code:**
```python
from config import GUARDHOUSE_ARROWS_PER_SHOT

# In Guardhouse.update():
if best_target and elapsed >= self.arrow_cooldown_sec:
    for i in range(GUARDHOUSE_ARROWS_PER_SHOT):
        best_target.take_damage(self.arrow_damage)
    self._last_arrow_time = now
    # Store projectile events — fire 2 arrows with slight visual offset
    for i in range(GUARDHOUSE_ARROWS_PER_SHOT):
        offset_x = (i - 0.5) * 8  # spread arrows slightly (8px apart)
        self._pending_projectiles.append({
            "start_x": self.center_x + offset_x,
            "start_y": self.center_y,
            "end_x": best_target.x,
            "end_y": best_target.y,
            # ... same fields as current projectile event
        })
```

Adapt the above to match the exact projectile event structure already used in the Guardhouse class. The key change: loop `GUARDHOUSE_ARROWS_PER_SHOT` times for both damage and visual events.

**Verify:**
```powershell
python -m pytest tests/ -x -q -k "guardhouse or defensive"
python tools/qa_smoke.py --quick
```
Also verify visually: launch the game, let enemies approach the pre-built guardhouse. You should see 2 arrows fire per volley.

---

### Item #11 — Hero Healing 5x Guild / 7x Inn (WK61-TUNE-003)

**What:** Heroes should heal 5x faster in guilds and 7x faster in inns.

**Background — current healing system:**
- Heroes heal via `update_resting()` in `game/entities/hero.py` (lines 504-559)
- Formula: `self._rest_heal_progress += recovery_rate * 50.0 * dt`
- `recovery_rate` is read from the building: `float(getattr(rest_building, "rest_recovery_rate", 0.01))`
- Current guild rate: 0.01 (fallback default — guilds don't set this attribute) → ~0.5 HP/sec
- Current inn rate: 0.02 (set in economic.py line 216) → ~1.0 HP/sec
- There is a 30 HP per-session cap (hero.py line 555) — hero stops resting after healing 30 HP, then re-enters rest if still hurt

**New rates (5x and 7x the current values):**
- Guild: 0.01 × 5 = **0.05** → ~2.5 HP/sec (full 60 HP hero healed in ~24s, or 12s per 30 HP session)
- Inn: 0.02 × 7 = **0.14** → ~7.0 HP/sec (full 60 HP hero healed in ~8.5s, or 4.3s per 30 HP session)

**File: `config.py`** — add new config values after the existing guardhouse configs:
```python
# WK61: Hero rest recovery rates (5x guild, 7x inn from WK60 baseline)
GUILD_REST_RECOVERY_RATE = 0.05
INN_REST_RECOVERY_RATE = 0.14
```

**File: `game/entities/buildings/hiring_mixin.py`** — In `HiringMixin.__init__()`, add:
```python
from config import GUILD_REST_RECOVERY_RATE
# ... inside __init__:
self.rest_recovery_rate = GUILD_REST_RECOVERY_RATE
```
This makes ALL guild buildings (Warriors, Rangers, Rogues, Wizards) use the boosted rate, because they all use HiringMixin.

**File: `game/entities/buildings/economic.py`** — line 216, change Inn's rate:
```python
# BEFORE:
self.rest_recovery_rate = 0.02

# AFTER:
from config import INN_REST_RECOVERY_RATE
self.rest_recovery_rate = INN_REST_RECOVERY_RATE
```

**Verify:**
```powershell
python -c "from config import GUILD_REST_RECOVERY_RATE, INN_REST_RECOVERY_RATE; print(f'Guild={GUILD_REST_RECOVERY_RATE}, Inn={INN_REST_RECOVERY_RATE}')"
# Expected: Guild=0.05, Inn=0.14
python -m pytest tests/ -x -q -k "hero or heal or rest"
```

---

### Item #12 — Enemy AI Prioritize Buildings (WK61-FEAT-007)

**What:** Enemies near town chase heroes away. Instead, when enemies are near player buildings, they should attack the buildings instead of chasing fleeing heroes.

**Background — current targeting in `game/entities/enemy.py`, `find_target()` (lines 134-184):**
- Enemies scan four pools in order: peasants, heroes, guards, buildings
- Selects the nearest valid target overall (pure distance-based)
- Buildings get slight biases: castle distance × 0.8, neutral buildings × 0.9
- Heroes near enemies are always candidates if alive and not inside a building
- Result: enemies near buildings will chase a hero who runs past, pulling the enemy away from town

**Desired behavior:** When an enemy is near player buildings, strongly prefer attacking buildings. Only target a hero if the hero is VERY close (e.g., actively engaging the enemy).

**Implementation — add a "near town" building-preference mode:**

At the top of `find_target()`, determine if the enemy is near any player building:

```python
# Add at the beginning of find_target():
BUILDING_PRIORITY_RANGE = 10 * TILE_SIZE  # 10 tiles = 320 pixels

near_town = False
for b in buildings:
    if b.hp > 0 and b.is_targetable:
        if self._distance_to(b) < BUILDING_PRIORITY_RANGE:
            near_town = True
            break
```

Then modify the building evaluation section to use much stronger biases when `near_town` is True:

```python
# In the building evaluation block:
if near_town:
    castle_bias = 0.3    # buildings STRONGLY preferred
    neutral_bias = 0.3
    other_bias = 0.4     # even non-neutral buildings preferred
else:
    castle_bias = 0.8    # original values
    neutral_bias = 0.9
    other_bias = 1.0

# Then in the distance comparison:
# For castle:
if b_is_castle and dist < best_dist * castle_bias:
    ...
# For neutral buildings:
elif b_is_neutral and dist < best_dist * neutral_bias:
    ...
# For other buildings (guilds, markets, etc.):
elif dist < best_dist * other_bias:
    ...
```

**Effect:** When an enemy is within 10 tiles of a building, a building at 300px distance is treated as if it were 90px away (0.3 bias). A hero would need to be closer than 90px (less than 3 tiles) to win the distance comparison. This means enemies in town attack buildings and only switch to heroes that are right on top of them.

**Also modify `game/systems/combat.py` retarget-on-hit behavior** (line 148-149): Currently when a hero hits an enemy targeting a building, the enemy retargets to the hero. KEEP this behavior — it's correct (heroes defending buildings should draw aggro). The `near_town` change only affects idle/patrolling target selection.

**Add the `BUILDING_PRIORITY_RANGE` config to `config.py`:**
```python
ENEMY_BUILDING_PRIORITY_RANGE_TILES = 10  # tiles within which enemies prefer buildings
```

**Verify:**
```powershell
python -m pytest tests/ -x -q -k "enemy or combat or target"
python tools/qa_smoke.py --quick
```
Also test manually: launch the game, wait for enemies to approach town. Observe that they attack buildings rather than chasing heroes who walk past. Confirm heroes can still draw aggro by attacking enemies directly.

---

### Item #7 (Gameplay Side) — Building Destruction + Rubble System (WK61-BUG-003 / WK61-FEAT-004)

This is the biggest item. Two parts: (A) fix buildings stuck at 0 HP, (B) add rubble that persists 2 minutes.

#### Part A — Bug Investigation: Buildings stuck at 0 HP

**Background:** `game/cleanup_manager.py` has `cleanup_destroyed_buildings()` (lines 19-119) which removes buildings at hp <= 0 (except castle). It's called from `game/engine.py` line 1394-1395, `_cleanup_after_combat()`.

**Diagnostic checklist — investigate these in order:**

1. Is `_cleanup_after_combat()` being called each tick? Add a temporary debug print if needed.
2. Does the cleanup correctly find buildings with `hp <= 0`? The check on line 28 collects `[b for b in buildings if b.hp <= 0 and not isinstance(b, Castle)]`.
3. Does `enemy.py` `_needs_new_target()` (lines 109-117) properly detect dead buildings? It checks `target.is_alive == False`, but Building may not have an `is_alive` attribute. If the attribute is missing, `getattr` might not return False. **Check whether `Building` has `is_alive` — if not, add `@property is_alive` that returns `self.hp > 0`.**
4. Are buildings actually being removed from `engine.buildings` list? Step through the cleanup.

**Most likely fix:** Add an `is_alive` property to `game/entities/buildings/base.py` if it doesn't exist:
```python
@property
def is_alive(self) -> bool:
    return self.hp > 0
```

And ensure `_needs_new_target()` in enemy.py handles building targets the same as hero targets — if target hp <= 0, drop it.

#### Part B — Rubble System

**Step 1: Create `game/entities/rubble.py`** (new file):
```python
from dataclasses import dataclass

@dataclass
class RubbleRecord:
    record_id: int
    center_x: float
    center_y: float
    grid_x: int
    grid_y: int
    width_tiles: int
    height_tiles: int
    building_type: str
    created_ms: int
    duration_ms: int = 120_000  # 2 minutes

_next_rubble_id = 0

def make_rubble_id() -> int:
    global _next_rubble_id
    _next_rubble_id += 1
    return _next_rubble_id
```

**Step 2: Spawn rubble in `game/cleanup_manager.py`**

In `cleanup_destroyed_buildings()`, after removing the building entity but before clearing references, create a RubbleRecord:

```python
from game.entities.rubble import RubbleRecord, make_rubble_id
from game.engine_facades.sim_clock import sim_now_ms

# After removing building from engine.buildings (around line 54-57):
rubble = RubbleRecord(
    record_id=make_rubble_id(),
    center_x=building.center_x,
    center_y=building.center_y,
    grid_x=building.grid_x,
    grid_y=building.grid_y,
    width_tiles=building.width,
    height_tiles=building.height,
    building_type=building.building_type,
    created_ms=sim_now_ms(),
)
engine.rubble_records.append(rubble)
```

**Step 3: Add rubble list to SimEngine**

In `game/sim_engine.py`, `__init__()`:
```python
self.rubble_records: list[RubbleRecord] = []
```

In `tick()`, add rubble expiry check (after combat cleanup):
```python
# Expire old rubble
now = sim_now_ms()
self.rubble_records = [
    r for r in self.rubble_records
    if now - r.created_ms < r.duration_ms
]
```

**Step 4: Add rubble to SimStateSnapshot**

In `game/sim/snapshot.py`, add to the SimStateSnapshot dataclass:
```python
from game.entities.rubble import RubbleRecord

# Add field:
rubble_records: tuple[RubbleRecord, ...] = ()
```

Where the snapshot is built (find the snapshot construction site in `sim_engine.py`), add:
```python
rubble_records=tuple(self.rubble_records),
```

**Verify:**
```powershell
python -m pytest tests/ -x -q
python tools/qa_smoke.py --quick
```
Manual test: launch with dev mode (`$env:KINGDOM_DEV_MODE='1'`), build a house or farm, let enemies destroy it. Confirm:
1. Building disappears when HP hits 0
2. Console shows "{building_name} destroyed" message (already existed)
3. (Agent 03 renders rubble — you just provide the data)

---

## Agent 03 — TechnicalDirector_Architecture (HIGH Intelligence)

You own 4 items: reversed names fix (#1), building name removal (#2), taxable gold "G" key toggle (#5), and rubble rendering (#7 render side).

### FILES YOU EDIT
- `game/graphics/ursina_renderer.py`

### FILES YOU DO NOT EDIT
- `config.py`, `game/entities/*`, `game/ui/*`, `game/engine.py`, `game/sim_engine.py`

---

### Item #1 — Fix Reversed/Backwards Names (WK61-BUG-001)

**Root Cause:** When a hero faces left, `_unit_facing_direction()` returns -1. This is multiplied into the hero entity's `scale_x` (line ~1301: `sx = sy * facing`). Since hero name labels, gold labels, rest labels, and HP bars are **parented to the hero entity**, they inherit the negative `scale_x` and render mirrored/backwards.

**The fix:** After the hero entity's scale is set, counter-flip all child text/UI entities so they remain readable regardless of parent facing direction.

**File:** `game/graphics/ursina_renderer.py`

Find the section where hero entity scale is applied. It's in the hero sync loop, around line 1300-1306, where:
```python
facing = _unit_facing_direction(h)
sx = sy * facing
# ... later:
ent.scale = scale_xyz  # at line ~579 via _sync_unit_atlas_billboard
```

**After** the line that sets `ent.scale` (or after the `_sync_unit_atlas_billboard` call returns for heroes), add:

```python
# WK61-BUG-001: Counter-flip child text entities so they don't mirror
# when the parent hero entity faces left (negative scale_x).
# Math: rendered_scale = parent.scale_x * child.scale_x
# We want rendered_scale > 0 always, so child.scale_x must match
# the sign of parent.scale_x (negative * negative = positive).
for attr in ('_ks_name_label', '_ks_gold_label', '_ks_rest_label',
             '_ks_hp_bg', '_ks_hp_fg'):
    child = getattr(ent, attr, None)
    if child is not None:
        child.scale_x = abs(child.scale_x) * facing
```

The variable `facing` (+1 or -1) is already computed earlier in the loop for the current hero. Reuse it. Do NOT recompute `_unit_facing_direction` — just reference the same `facing` variable.

**IMPORTANT:** This fix must also apply to **enemy** entities if they have child entities (HP bars). Check the enemy sync loop (around lines 1460-1470) for a similar `facing_e = _unit_facing_direction(e)` pattern. Apply the same counter-flip to enemy child entities:

```python
# In the enemy sync section, after enemy entity scale is set:
for attr in ('_ks_hp_bg', '_ks_hp_fg'):
    child = getattr(ent, attr, None)
    if child is not None:
        child.scale_x = abs(child.scale_x) * facing_e
```

**Verify:**
```powershell
python tools/qa_smoke.py --quick
```
Visual test: launch game (`python main.py --no-llm`), hire heroes, watch them move left and right. Names and HP bars should NEVER appear mirrored/backwards. Specifically:
1. Hero walks right → name reads normally (e.g., "Sir Galahad")
2. Hero walks left → name STILL reads normally (not "dahalaG riS")
3. HP bars maintain correct fill direction regardless of facing

Use the screenshot tool to capture evidence:
```powershell
python tools/run_ursina_capture_once.py --reveal-map
```

---

### Item #2 — Remove Names from Buildings (WK61-FEAT-001)

**What:** Buildings currently display floating name labels ("CASTLE", "WARRIORS", "MARKETPLACE", etc.) above them in 3D. Remove these.

**File:** `game/graphics/ursina_renderer.py`, function `_sync_building_worldspace_ui()` (lines ~142-160)

**Current behavior:** The function looks up the building type in `_BUILDING_LABEL_MAP` (lines 109-139) and creates a Text entity stored as `ent._ks_label`.

**Change:** Skip label creation entirely. Find the block that creates/manages `ent._ks_label` and disable it:

```python
# In _sync_building_worldspace_ui():
# REMOVE or SKIP the entire label creation/update block.
# If label already exists from a prior frame, hide it:
if hasattr(ent, '_ks_label') and ent._ks_label:
    ent._ks_label.enabled = False
# Do NOT create new labels. Remove or comment out the code that does:
#   label_text = _BUILDING_LABEL_MAP.get(bts, bts.upper())
#   ent._ks_label = Text(text=label_text, ...)
```

**IMPORTANT:** Leave the gold label code (`ent._ks_gold_label`) in this same function INTACT — the gold text above buildings is a separate feature (gated by "G" key, see Item #5 below).

**Verify:**
```powershell
python tools/qa_smoke.py --quick
```
Visual test: launch game, look at buildings. No text labels ("CASTLE", "WARRIORS", etc.) should appear above any building. Gold text (when "G" is held) should still work.

---

### Item #5 — Taxable Gold Only Shows While Holding "G" Key (WK61-FEAT-003)

**What:** Taxable gold amounts currently always appear as floating text above buildings. Change: only show this text while the player holds down the "G" key.

**File:** `game/graphics/ursina_renderer.py`, function `_sync_building_worldspace_ui()` (lines ~181-195)

**Current behavior:** If `stash > 0` (building has taxable gold), a gold-colored Text entity is created/shown at y=0.9 above the building.

**Change:** Gate the gold label visibility on whether the "G" key is currently held:

```python
from ursina import held_keys

# In _sync_building_worldspace_ui(), in the gold label section:
stash = int(getattr(b, 'stash_gold', 0) or getattr(b, 'stored_tax_gold', 0) or 0)
g_held = held_keys.get('g', False)

if stash > 0 and g_held:
    # Show gold label (create if needed, update text, set enabled=True)
    if not hasattr(ent, '_ks_gold_label') or ent._ks_gold_label is None:
        ent._ks_gold_label = Text(
            text=f"${stash}",
            parent=ent,
            origin=(0, 0),
            scale=12,
            color=color.rgb(1.0, 0.8, 0.2),
            billboard=True,
            y=0.9,
        )
    else:
        ent._ks_gold_label.text = f"${stash}"
        ent._ks_gold_label.enabled = True
else:
    # Hide gold label if it exists
    if hasattr(ent, '_ks_gold_label') and ent._ks_gold_label:
        ent._ks_gold_label.enabled = False
```

**Note on hero gold labels:** Jaimie said "taxable gold should only show over buildings". The hero gold labels (`ent._ks_gold_label` on hero entities, at lines 1376-1395) should be LEFT UNCHANGED — they show the hero's personal gold and are a different feature. Only gate the BUILDING gold labels on "G".

**Note on the "G" key:** The "G" key was previously mapped to gnome_hovel placement but was removed in WK34. It is currently unmapped and falls through the input handler with no effect. You do NOT need to add any keybinding — `held_keys['g']` in Ursina works automatically for any key regardless of whether it's bound in the input handler.

**Verify:**
```powershell
python tools/qa_smoke.py --quick
```
Visual test: launch game, look at buildings that have tax gold.
1. Without pressing G: no gold numbers above buildings
2. Hold G: gold amounts appear above buildings with stored tax gold
3. Release G: gold amounts disappear
4. Hero gold labels always visible regardless of G key

---

### Item #7 (Render Side) — Rubble Rendering (WK61-FEAT-004)

**What:** When a building is destroyed, Agent 05's code creates `RubbleRecord` entries in the game snapshot. You render those as scattered stone/debris models in 3D.

**File:** `game/graphics/ursina_renderer.py`

**Step 1: Add rubble entity cache** in `UrsinaRenderer.__init__()`:
```python
self._rubble_entities: dict[int, list] = {}  # record_id -> list of Entity
```

**Step 2: Add `_sync_snapshot_rubble()` method:**

```python
def _sync_snapshot_rubble(self, snapshot):
    """Create/destroy rubble entity groups from snapshot.rubble_records."""
    active_ids = {r.record_id for r in snapshot.rubble_records}
    
    # Remove expired rubble
    for rid in list(self._rubble_entities.keys()):
        if rid not in active_ids:
            for ent in self._rubble_entities[rid]:
                destroy(ent)
            del self._rubble_entities[rid]
    
    # Create new rubble
    for r in snapshot.rubble_records:
        if r.record_id in self._rubble_entities:
            continue  # already rendered
        
        entities = []
        # Convert grid position to world position for Ursina
        # Use the same coordinate system as buildings
        wx, wy, wz = self._grid_to_world(r.grid_x, r.grid_y)
        
        # Place 2-3 small rock models scattered within footprint
        import random
        rng = random.Random(r.record_id)  # deterministic per rubble
        
        footprint_px = r.width_tiles * TILE_SIZE
        for i in range(3):
            offset_x = rng.uniform(-footprint_px * 0.3, footprint_px * 0.3)
            offset_z = rng.uniform(-footprint_px * 0.3, footprint_px * 0.3)
            rock_model = rng.choice([
                'rock_smallA', 'rock_smallB', 'rock_smallC',
                'rock_smallD', 'rock_smallE', 'rock_smallF',
            ])
            rock = Entity(
                model=f'assets/models/environment/{rock_model}.glb',
                position=(wx + offset_x, 0.1, wz + offset_z),
                scale=rng.uniform(0.8, 1.5),
                rotation_y=rng.uniform(0, 360),
                color=color.rgb(0.6, 0.55, 0.5),  # dusty gray-brown
            )
            entities.append(rock)
        
        self._rubble_entities[r.record_id] = entities
```

**IMPORTANT adaptation notes:**
- The `_grid_to_world` helper may not exist with that exact name. Look at how `_sync_snapshot_buildings` converts building grid positions to Ursina world coordinates and follow the same pattern. Search for how `building.grid_x` / `building.center_x` maps to Entity position.
- The rock model paths must match what's actually on disk. The environment rocks are at `assets/models/environment/rock_smallA.glb` through `rock_smallF.glb`. Verify these paths exist before using them. If the renderer loads models differently (e.g., via a model registry), follow that pattern.
- If the game uses a coordinate transform (e.g., isometric or y-up vs z-up), apply the same transform here.

**Step 3: Call from update():**

Find where the other `_sync_snapshot_*` methods are called (near the end of the `update()` method, alongside `_sync_snapshot_heroes`, `_sync_snapshot_enemies`, `_sync_snapshot_buildings`, `_sync_snapshot_bounties`, etc.) and add:

```python
self._sync_snapshot_rubble(snapshot)
```

**Verify:**
```powershell
python tools/qa_smoke.py --quick
```
Visual test with dev mode: build a farm or house, let enemies destroy it. Observe:
1. Building disappears when HP reaches 0
2. Small rock/stone models appear at the building's former location
3. After ~2 minutes, the rocks disappear
4. Multiple destroyed buildings each get their own rubble cluster

---

## Agent 08 — UX_UI_Director (MEDIUM Intelligence)

You own 3 items: building menu taxable gold (#6), chat button in hero menu (#8), and enemy click menu (#10).

### FILES YOU EDIT
- `game/ui/building_renderers/economic_panel.py` (taxable gold)
- `game/ui/hero_panel.py` (chat button)
- `game/ui/enemy_panel.py` (NEW — enemy info panel)
- `game/ui/hud.py` (enemy panel rendering hookup)
- `game/input_handler.py` (enemy click routing in selection cascade)
- `game/engine.py` (enemy selection state + `try_select_enemy()`)

### FILES YOU DO NOT EDIT
- `game/graphics/ursina_renderer.py` (Agent 03)
- `game/entities/*` (Agent 05)
- `config.py` (Agent 05)

---

### Item #6 — Marketplace and Blacksmith Show Taxable Gold in Building Menus (WK61-BUG-002)

**What:** When you click a marketplace or blacksmith, their building info panel should show "Taxable Gold: $X" — currently only guild panels show this.

**Root cause:** The `EconomicPanelRenderer` in `game/ui/building_renderers/economic_panel.py` handles marketplace, blacksmith, inn, and trading_post panels. It does NOT display taxable gold. Meanwhile, `GuildPanelRenderer` in `guild_panel.py` (lines 28-33) already shows "Taxable Gold: $X".

**Fix:** In `game/ui/building_renderers/economic_panel.py`, add a taxable gold display line in the `render()` method, following the exact pattern from `guild_panel.py`:

```python
# Copy this pattern from guild_panel.py lines 28-33:
tax_gold = int(getattr(building, 'stored_tax_gold', 0))
if tax_gold > 0:
    y = draw_text(surface, f"Taxable Gold: ${tax_gold}", x, y, 
                  font=theme.font_body, color=(255, 215, 0))  # gold color
```

Add this after the existing info sections (occupants, items, etc.) but before any action buttons. Apply it for marketplace AND blacksmith building types specifically. The inn and trading_post can also get it if they have `stored_tax_gold`.

**Also verify:** `game/ui/building_renderers/__init__.py` lines 82-89 has a `GenericPanelRenderer` that shows taxable gold. Check that marketplace/blacksmith route to `EconomicPanelRenderer` (they do — confirmed in `__init__.py` lines 133-146 `PANEL_RENDERERS` dict).

**Verify:**
```powershell
python -m pytest tests/ -x -q -k "ui or building or panel"
python tools/qa_smoke.py --quick
```
Visual test: click on the pre-built marketplace and any blacksmith. Both should show "Taxable Gold: $X" in their info panels (after tax collectors have visited or gold has accumulated).

---

### Item #8 — Chat Button in Hero Menu (WK61-FEAT-005)

**What:** Add a "Chat" button to the hero info panel. When clicked, it opens the same chat popup that appears on hero cards, positioned below the hero menu.

**Key files and how they work:**
- **Hero panel:** `game/ui/hero_panel.py`, class `HeroPanel`. The main render method is `_render_standard_hero()` (line 383). The panel renders on the left column (224px wide). Currently it has NO action buttons — it's info-only (name, class, HP, ATK, DEF, gold, gear, intent, stats, memory).
- **Chat panel:** `game/ui/chat_panel.py`, class `ChatPanel`. Already instantiated in `HUD.__init__` as `self._chat_panel` (hud.py line 224).
- **How chat starts:** The input_handler.py (lines 466-475) processes `{"type": "start_conversation", "hero": hero}` action dicts by calling `chat_panel.start_conversation(hero)`.
- **Widget toolkit:** `game/ui/widgets.py` has a `Button` class with hover/pressed states.

**Implementation — 3 steps:**

**Step 1:** In `game/ui/hero_panel.py`, `_render_standard_hero()`, at the bottom of the render method (after all the info sections, before the method returns), add a "Chat" button:

```python
# At bottom of _render_standard_hero(), before return:
from game.ui.widgets import Button

chat_btn_rect = pygame.Rect(x + 10, y + 8, LEFT_COL_W - 20, 30)
chat_btn = Button(
    rect=chat_btn_rect,
    text="Chat",
    font=self._theme.font_body,
    color=(60, 120, 200),        # blue accent
    hover_color=(80, 150, 240),
    text_color=(255, 255, 255),
)
chat_btn.draw(surface)
y += 42
```

Adapt the above to match the exact Button API in widgets.py. The key is: render a clickable button with the text "Chat" at the bottom of the hero panel.

**Step 2:** In the hero panel's `handle_click()` method (or wherever click handling occurs for the panel), detect clicks on the chat button rect and return the action dict:

```python
if chat_btn_rect.collidepoint(mouse_pos):
    return {"type": "start_conversation", "hero": self._current_hero}
```

The existing `input_handler.py` already handles `"start_conversation"` action dicts (lines 466-475), so the chat panel will open automatically.

**Step 3:** The chat panel (`ChatPanel`) renders as an overlay managed by the HUD. When `start_conversation(hero)` is called, it appears. The hero panel and chat panel can coexist (chat renders below/overlapping the left panel area). No additional positioning code needed — the existing chat panel positioning should work. If it overlaps badly, adjust the chat panel's y-position to start below the hero panel.

**Verify:**
```powershell
python -m pytest tests/ -x -q
python tools/qa_smoke.py --quick
```
Visual test: click on a hero to open their info panel. Confirm:
1. "Chat" button is visible at the bottom of the hero info panel
2. Clicking "Chat" opens the conversation popup (text input + responses)
3. Can type a message and get a hero response (requires --no-llm flag to be OFF, or mock response)
4. Closing the chat doesn't break the hero panel
5. Clicking a different hero updates the panel and closes any open chat

---

### Item #10 — Click on Enemies for Info Menu (WK61-FEAT-006)

**What:** Players should be able to click on enemy units and see an info panel where the hero menu normally appears (left column, 224px wide).

**This is the most complex UI item.** Three parts: selection logic, panel rendering, HUD integration.

**Current click cascade** (game/input_handler.py lines 613-637):
```
try_select_hero → try_select_tax_collector → try_select_guard → 
try_select_peasant → try_select_building → clear all
```
Enemies are NOT in this cascade. You will add them.

**Current selection methods** (game/engine.py):
- `try_select_hero()` at line 686: checks `hero.distance_to(wx,wy) < hero.size * 1.5`
- `try_select_building()` at line 786: inflated rect hit test
- Selection state: `self.selected_hero`, `self.selected_building`, `self.selected_peasant`

#### Step 1: Add enemy selection to engine.py

In `GameEngine.__init__()`, add:
```python
self.selected_enemy = None
```

Add a new method following the `try_select_hero` pattern:
```python
def try_select_enemy(self, wx: float, wy: float) -> bool:
    """Try to select an enemy at world coordinates. Returns True if found."""
    best = None
    best_dist = float('inf')
    for enemy in self.enemies:
        if not enemy.is_alive:
            continue
        d = enemy.distance_to(wx, wy)
        if d < enemy.size * 1.5 and d < best_dist:
            best = enemy
            best_dist = d
    if best:
        self.selected_enemy = best
        self.selected_hero = None
        self.selected_building = None
        self.selected_peasant = None
        return True
    return False
```

Also clear `selected_enemy` in the other `try_select_*` methods when they succeed, and in the "clear all" path.

#### Step 2: Add enemy to click cascade in input_handler.py

In `handle_mousedown()` (lines 613-637), insert enemy selection after guard/peasant but BEFORE building:

```python
# Existing cascade (approximate):
if engine.try_select_hero(wx, wy):
    pass
elif engine.try_select_tax_collector(wx, wy):
    pass
elif engine.try_select_guard(wx, wy):
    pass
elif engine.try_select_peasant(wx, wy):
    pass
# ADD THIS:
elif engine.try_select_enemy(wx, wy):
    pass
elif engine.try_select_building(wx, wy):
    pass
else:
    engine.clear_selection()  # also clear selected_enemy here
```

#### Step 3: Create enemy info panel

Create `game/ui/enemy_panel.py` following the structure of `hero_panel.py`. It renders on the LEFT column (same 224px region as the hero panel — they never show simultaneously).

```python
class EnemyPanel:
    def __init__(self, theme):
        self._theme = theme
    
    def render(self, surface, enemy, panel_rect):
        """Render enemy info panel in the left column."""
        x = panel_rect.x + 10
        y = panel_rect.y + 10
        
        # Enemy type name (large, red-tinted)
        enemy_name = enemy.__class__.__name__  # "Wolf", "Goblin", "SkeletonArcher", etc.
        # Format SkeletonArcher as "Skeleton Archer"
        display_name = ''.join(
            f' {c}' if c.isupper() and i > 0 else c 
            for i, c in enumerate(enemy_name)
        ).strip()
        y = draw_text(surface, display_name, x, y,
                      font=theme.font_title, color=(220, 80, 80))
        
        # HP bar
        hp_pct = enemy.hp / enemy.max_hp if enemy.max_hp > 0 else 0
        y = draw_hp_bar(surface, x, y, width=200, 
                        current=enemy.hp, maximum=enemy.max_hp,
                        color=(220, 50, 50))
        y = draw_text(surface, f"HP: {enemy.hp}/{enemy.max_hp}", x, y,
                      font=theme.font_body, color=(255, 255, 255))
        
        # Attack damage
        atk = getattr(enemy, 'attack_damage', getattr(enemy, 'base_attack', '?'))
        y = draw_text(surface, f"Attack: {atk}", x, y,
                      font=theme.font_body, color=(255, 200, 200))
        
        # Current target
        target = getattr(enemy, 'target', None)
        if target is not None:
            target_name = getattr(target, 'name', 
                          getattr(target, 'building_type', 
                          target.__class__.__name__))
            y = draw_text(surface, f"Target: {target_name}", x, y,
                          font=theme.font_body, color=(255, 180, 100))
        else:
            y = draw_text(surface, "Target: None (wandering)", x, y,
                          font=theme.font_body, color=(150, 150, 150))
        
        # Speed
        speed = getattr(enemy, 'speed', '?')
        y = draw_text(surface, f"Speed: {speed}", x, y,
                      font=theme.font_body, color=(200, 200, 255))
```

Adapt the above to use the actual drawing helpers from the codebase. Look at how `HeroPanel._render_standard_hero()` draws text, HP bars, and stat lines — use the same helpers and patterns:
- Text rendering likely uses a helper or direct `pygame.font.Font.render()`
- HP bars likely use the `HPBar` widget from `game/ui/widgets.py`
- The theme object has `font_title` (28px), `font_body` (20px), `font_small` (16px)

#### Step 4: Hook into HUD rendering

In `game/ui/hud.py`, instantiate the enemy panel in `HUD.__init__()`:
```python
from game.ui.enemy_panel import EnemyPanel
self._enemy_panel = EnemyPanel(theme=self._theme)
```

In `HUD.render()` (line ~1721), alongside the hero panel rendering (line ~1784), add:
```python
# After the hero panel block:
if engine.selected_enemy and not engine.selected_hero and not engine.selected_building:
    self._enemy_panel.render(surface, engine.selected_enemy, left_rect)
```

This ensures: enemy panel shows when an enemy is selected, hero panel shows when a hero is selected, building panel shows when a building is selected — mutually exclusive.

#### Step 5: Add close button

Add a close "X" button to the enemy panel (top-right corner) that clears `selected_enemy` on click, following the same pattern as the hero panel close button at `HUD._render_left_close_button()` (hud.py line 1796).

**Verify:**
```powershell
python -m pytest tests/ -x -q
python tools/qa_smoke.py --quick
```
Visual test: launch game, wait for enemies to spawn near town.
1. Click on a wolf → enemy panel appears on left with "Wolf", HP bar, attack, target
2. Click on a goblin → panel updates to show "Goblin" info
3. Click on a hero → hero panel replaces enemy panel
4. Click on empty space → all panels hidden
5. Click the X button on enemy panel → panel closes
6. Enemy panel shows correct live HP (damage updates in real-time)

---

## Agent 14 — SoundDirector_Audio (MEDIUM Intelligence)

You own 1 item: enemy-specific sounds (#3).

### FILES YOU EDIT
- `game/audio/` directory
- `assets/audio/` for new sound assets

### FILES YOU DO NOT EDIT
- `game/entities/*`, `game/graphics/*`, `game/ui/*`, `config.py`

---

### Item #3 — Enemy-Specific Sounds (WK61-FEAT-002)

**What:** Each enemy type should have distinct combat/ambient sounds: wolves bark, spiders hiss, goblins grunt, skeletons rattle, bandits shout.

**Enemy types in the game:** Goblin, Wolf, Skeleton, SkeletonArcher, Spider, Bandit

**Sound design per enemy type:**

| Enemy Type | Attack Sound | Idle/Ambient Sound | Death Sound |
|-----------|-------------|-------------------|-------------|
| Wolf | Bark / snarl | Low growl | Whimper/yelp |
| Spider | Loud hiss / screech | Soft chittering | Squish |
| Goblin | Battle cry / grunt | Mumbling | Screech |
| Skeleton | Bone clash / rattle | Quiet clatter | Bone collapse |
| SkeletonArcher | Bow twang + bone rattle | Same as Skeleton | Same as Skeleton |
| Bandit | Shout / war cry | Grumble | Groan |

**Implementation approach:**

1. **Find or generate sound assets.** Check `assets/audio/` and `assets/sounds/` for any existing enemy sounds. If none exist, use short procedural/synthesized sounds or find royalty-free SFX that match the above descriptions. Keep sounds SHORT (0.2-0.8 seconds for combat, 1-2 seconds for ambient).

2. **Wire into the audio system.** Look at `game/audio/audio_system.py` for how existing sounds are played. The game likely uses the EventBus to trigger sounds on events. Key events to hook into:
   - `enemy_attack` or combat hit events → play attack sound
   - `enemy_death` → play death sound
   - Enemy idle/movement → play ambient sound on a cooldown (every 5-10 seconds, randomized, to avoid cacophony)

3. **Map enemy types to sound files.** Create a mapping dict:
```python
ENEMY_SOUNDS = {
    "goblin": {
        "attack": "assets/audio/enemies/goblin_attack.wav",
        "death": "assets/audio/enemies/goblin_death.wav",
        "ambient": "assets/audio/enemies/goblin_ambient.wav",
    },
    "wolf": { ... },
    ...
}
```

4. **Volume and spatialization.** Enemy sounds should be quieter when the enemy is far from the camera and louder when close. If the audio system supports positional audio, use it. If not, scale volume by distance from camera center.

5. **Ambient sound frequency.** Don't play ambient sounds every frame — use a random cooldown (5-15 seconds per enemy) so the soundscape is varied, not a wall of noise. Cap simultaneous enemy sounds (e.g., max 3 enemy sounds playing at once).

**Verify:**
```powershell
python tools/qa_smoke.py --quick
```
Audio test: launch game, wait for enemies. Confirm:
1. Wolves make bark/growl sounds when attacking
2. Spiders make hiss sounds
3. Each enemy type has a distinct sound identity
4. Sounds aren't overwhelming or too frequent
5. Sound volume scales with distance from camera
6. No sound-related errors in console

---

## R2 Agents — QA and Visual Consult

### Agent 11 — QA_TestEngineering (LOW Intelligence)

Run the full gate suite and report results:
```powershell
python tools/qa_smoke.py --quick
python -m pytest tests/ -x -q
python tools/validate_assets.py --report
```

Capture screenshots for visual verification:
```powershell
python tools/run_ursina_capture_once.py --reveal-map
```

Check specifically:
- [ ] Names on heroes are NEVER backwards (watch heroes walk left and right)
- [ ] No text labels on buildings
- [ ] Gold numbers appear over buildings ONLY while holding G
- [ ] Rubble appears when buildings are destroyed, disappears after ~2 minutes
- [ ] Enemy sounds play for different enemy types
- [ ] Enemy info panel appears when clicking enemies
- [ ] Chat button works in hero menu
- [ ] Marketplace/blacksmith show taxable gold in panels
- [ ] Guardhouse fires 2 arrows per volley
- [ ] Heroes heal noticeably faster in guilds and inns
- [ ] Heroes feel fragile at level 1 (60 HP)
- [ ] Enemies attack buildings instead of chasing heroes out of town

### Agent 09 — ArtDirector (LOW Intelligence)

Visual cohesion review of:
- Rubble appearance (do the scattered rocks look natural? right scale? right color?)
- Enemy info panel styling (consistent with hero panel?)
- Chat button placement (balanced in the hero menu layout?)
- Gold overlay when holding G (readable? right color? right position?)

---

## Deferred Items (from WK60 R2 — pick up in WK62 if not done here)

These were planned for WK60 R2 but never executed. They're NOT required for WK61 but can be added if time allows:

- Wave warning HUD toasts ("INCOMING: Goblin Raid!" + countdown)
- Difficulty selector menu in ESC/pause menu (Easy/Normal/Hard + Lock button)
- "[DEV MODE]" HUD label when dev mode is active
- Horn SFX for wave warnings
- Guild "N/8" hero count display in guild panels

---

## Definition of Done (WK61)

- [ ] Hero names never appear backwards regardless of facing direction
- [ ] No name labels float above buildings
- [ ] Holding G shows taxable gold amounts over buildings; releasing hides them
- [ ] Marketplace and blacksmith show taxable gold in their info panels
- [ ] Buildings at 0 HP are destroyed and replaced with stone rubble
- [ ] Rubble persists ~2 minutes then disappears
- [ ] Hero menu has a working Chat button that opens conversation popup
- [ ] Clicking enemies opens an info panel with type, HP, attack, and target
- [ ] Guardhouse fires 2 arrows per volley
- [ ] Heroes heal ~5x faster in guilds, ~7x faster in inns
- [ ] Enemies near town prioritize attacking buildings over chasing heroes
- [ ] Hero base HP is 60 (was 100)
- [ ] Market visit durations are approximately halved
- [ ] Each enemy type has distinct combat sounds
- [ ] `python tools/qa_smoke.py --quick` PASS
- [ ] `python -m pytest tests/ -x -q` PASS
- [ ] Game playable for 15+ minutes without crashes
