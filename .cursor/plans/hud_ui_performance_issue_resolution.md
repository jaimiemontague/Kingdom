# HUD/UI Performance Issue Resolution

**Date:** 2026-05-17
**Sprint:** v1.6 Round 5 — HUD Texture Pipeline & World-Space UI
**Prerequisite:** v1.6.4 (Rounds 1-4 shipped: atlas, pathfinding budget, frustum culling, fixed-rate sim, linear interpolation, smoothness monitor)
**Blocking Issue:** `hud_texture_upload` stage takes **49ms P90** (65ms max), dropping 10% of frames to 11-15 FPS

---

## EXECUTIVE SUMMARY

### The Problem

The FPS probe data from three separate Ursina captures tells a clear story:

```
                          0 heroes    5 heroes    10 heroes
hud_texture_upload avg     6.75ms     17.72ms      13.37ms
hud_texture_upload P90    47.39ms     49.52ms      49.37ms
hud_texture_upload max    65.04ms     58.24ms      67.03ms
```

Every time the pygame HUD surface changes, `_refresh_ui_overlay_texture()` in `ursina_app.py:735` converts the entire 1920x1080 surface (8MB RGBA) through this pipeline:

```
pygame.Surface → pygame.image.tobytes() → PIL.Image.frombytes() → PIL.transpose(FLIP) → PIL.tobytes() → Texture.setRamImageAs() → GPU
```

PIL is used solely as an intermediate container for one operation: flipping the image vertically (pygame and Panda3D use opposite Y-axis conventions). This adds ~15-30ms of Python overhead for object construction, memory allocation, and the vertical flip — all of which can be done directly on the raw byte buffer.

### What This Plan Fixes

1. **Phase 1 (PIL Bypass):** Replace `PIL.Image.frombytes() → transpose → tobytes()` with a direct byte-level vertical flip, then upload straight to Panda3D's `Texture.setRamImageAs()`. Expected: per-upload cost drops from ~49ms to ~5-15ms.

2. **Phase 2 (World-Space UI as Native Ursina Entities):** Add building labels, hero names, health bars, and damage numbers as native Ursina Billboard entities — NOT as pygame HUD drawings. This is a **feature addition**: these elements currently do NOT exist in 3D mode. Adding them as pygame drawings would re-create the upload problem; building them natively avoids it entirely.

3. **Phase 3 (Dirty-Region Upload — IF NEEDED):** Roadmap for uploading only the changed rectangle of the HUD surface instead of the full 1920x1080. Implement only if Phase 1 doesn't bring `hud_texture_upload` P90 below 10ms.

### Critical Context for All Agents

**In Ursina mode, `skip_pygame_world=True` (set at `ursina_app.py:136`).** This means `PygameRenderer._draw_world_layers()` is never called. The pygame surface `engine.screen` contains ONLY screen-space HUD elements:

- Top bar (gold, heroes, wave counter)
- Bottom bar (Build / Hire / Bounty buttons)
- HUD messages and toast notifications
- Perf overlay (smoothness monitor)
- Pause menu, build catalog, building panel (when visible)

**There are NO health bars, NO building labels, NO hero names, NO damage numbers, NO VFX particles in 3D mode.** These features exist only in `--renderer pygame` mode via `_draw_world_layers()`. This sprint adds them properly as native Ursina entities.

---

## PHASE 1: PIL BYPASS IN HUD TEXTURE UPLOAD

**Assigned to:** Agent 03 (Technical Director / Architecture)
**Scope:** Modify one method in one file
**Risk:** LOW — purely mechanical change to data pipeline, no behavioral change
**Priority:** IMPLEMENT IMMEDIATELY

### What Agent 03 Must Understand

The method `_refresh_ui_overlay_texture()` at `game/graphics/ursina_app.py:735` is the sole path from pygame HUD to GPU. It runs on any frame where the HUD surface has changed (detected by CRC32 fingerprinting). The current implementation uses PIL as an intermediary, but PIL is doing nothing that can't be done with a simple byte buffer reversal.

The Ursina `Texture` class (at `C:\Users\Jaimie Montague\AppData\Roaming\Python\Python313\site-packages\ursina\texture.py`) wraps Panda3D's `Texture` object. When you call `tex.apply()`, it does:

```python
def apply(self):
    from PIL import Image
    self._texture.setRamImageAs(
        self._cached_image.transpose(Image.FLIP_TOP_BOTTOM).tobytes(),
        self._cached_image.mode
    )
```

This means every `.apply()` call does ANOTHER PIL transpose + tobytes. So the cost is doubled: once in `_refresh_ui_overlay_texture()` to create the PIL image, then again in `tex.apply()` to flip and extract bytes.

### Exact Changes Required

**File:** `game/graphics/ursina_app.py`

**Step 1:** Add a helper function at module level (outside the class, near the top of the file after imports):

```python
def _flip_surface_bytes_vertical(raw_rgba: bytes, width: int, height: int) -> bytes:
    """Flip RGBA pixel data vertically (reverse row order).

    Pygame's Y-axis points down; Panda3D's points up. PIL.Image.transpose(FLIP_TOP_BOTTOM)
    does this, but PIL adds ~15-30ms of Python overhead for the 8MB allocation + object
    construction. This function does the same operation directly on the byte buffer.
    """
    row_stride = width * 4
    # Build reversed row list — each slice is a memoryview into the original buffer,
    # so this allocates only the final joined result, not N intermediate copies.
    mv = memoryview(raw_rgba)
    return b"".join(mv[i * row_stride : (i + 1) * row_stride] for i in range(height - 1, -1, -1))
```

**Step 2:** Replace the body of `_refresh_ui_overlay_texture()` (lines 735-795). Here is the complete replacement method. The agent MUST replace the entire method body, not just parts of it:

```python
def _refresh_ui_overlay_texture(self) -> None:
    """Upload pygame HUD to GPU, bypassing PIL entirely (R5 perf fix).

    Previous path: pygame.tobytes → PIL.Image.frombytes → PIL.transpose → PIL.tobytes → setRamImageAs
    New path:      pygame.tobytes → _flip_surface_bytes_vertical → setRamImageAs
    """
    scale = (camera.aspect_ratio, 1)
    if self._last_ui_overlay_scale != scale:
        self.ui_overlay.scale = scale
        self._last_ui_overlay_scale = scale

    surf = self.engine.screen
    sz = surf.get_size()

    try:
        quick = self._hud_quick_fingerprint(surf)
    except Exception:
        quick = None

    force_upload = bool(getattr(self.engine, "_ursina_hud_force_upload", False))
    if force_upload:
        setattr(self.engine, "_ursina_hud_force_upload", False)

    if (
        not force_upload
        and quick is not None
        and self._hud_composite_texture is not None
        and self._hud_composite_size == sz
        and self._hud_quick_sig is not None
        and quick == self._hud_quick_sig
    ):
        return

    raw_data = pygame.image.tobytes(surf, "RGBA")

    try:
        self._hud_quick_sig = self._hud_quick_fingerprint(surf)
    except Exception:
        self._hud_quick_sig = zlib.crc32(raw_data) & 0xFFFFFFFF

    flipped = _flip_surface_bytes_vertical(raw_data, sz[0], sz[1])

    from panda3d.core import Texture as PandaTexture

    if self._hud_composite_texture is None or self._hud_composite_size != sz:
        panda_tex = PandaTexture()
        panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
        panda_tex.setRamImageAs(flipped, "RGBA")
        self._hud_composite_texture = Texture(panda_tex)
        self._hud_composite_size = sz
        self.ui_overlay.texture = self._hud_composite_texture
        self._sync_hud_texture_filter_mode(self._hud_composite_texture)
    else:
        panda_tex = self._hud_composite_texture._texture
        if int(panda_tex.getXSize()) != int(sz[0]) or int(panda_tex.getYSize()) != int(sz[1]):
            panda_tex = PandaTexture()
            panda_tex.setup2dTexture(sz[0], sz[1], PandaTexture.TUnsignedByte, PandaTexture.FRgba)
            panda_tex.setRamImageAs(flipped, "RGBA")
            self._hud_composite_texture = Texture(panda_tex)
            self._hud_composite_size = sz
            self.ui_overlay.texture = self._hud_composite_texture
            self._sync_hud_texture_filter_mode(self._hud_composite_texture)
        else:
            panda_tex.setRamImageAs(flipped, "RGBA")
```

**Why this works:**

- `pygame.image.tobytes(surf, "RGBA")` produces raw RGBA bytes with row 0 at the top (pygame convention).
- `_flip_surface_bytes_vertical()` reverses the row order so row 0 is at the bottom (Panda3D/OpenGL convention).
- `panda_tex.setRamImageAs(flipped, "RGBA")` uploads the bytes directly to GPU memory.
- We skip PIL entirely: no `Image.frombytes()`, no `Image.transpose()`, no `Image.tobytes()`.
- We also skip Ursina's `tex.apply()` (which internally does another PIL transpose), going directly to the Panda3D texture's `setRamImageAs()`.
- The `Texture(panda_tex)` constructor wraps the raw Panda3D texture in an Ursina Texture object, which is required for `self.ui_overlay.texture =` assignment.

**What NOT to change:**

- Do NOT modify `_hud_quick_fingerprint()` — it works on the pygame surface and is unaffected.
- Do NOT modify `_sync_hud_texture_filter_mode()` — it operates on the Ursina Texture wrapper, which still exists.
- Do NOT remove the `Texture` import from ursina — it's needed for the wrapper.
- Do NOT change any other method in the class.

### How Agent 03 Verifies Their Work

**Test 1 — Unit tests pass:**
```bash
python -m pytest tests/ -x -q --tb=short
```
Expected: 307 passed. If any fail, the change broke something — revert and investigate.

**Test 2 — Visual verification with Ursina capture:**
```bash
python tools/run_ursina_capture_once.py --seconds 12 --subdir r5_pil_bypass --stem after_bypass --no-llm --fps-probe --hero-fps-probe-count 5 --fps-warmup-sec 8
```
Then examine the output:
1. Open the PNG screenshot — the HUD (top bar, bottom bar, perf overlay) must be visible and correctly rendered. Text must be readable, not upside-down, not garbled, not offset.
2. Check the `[fps-probe-stage] hud_texture_upload` line in stdout. **The P90 must be lower than the 49ms baseline.** Target: P90 < 20ms. If the P90 is still >40ms, the bypass didn't work — the old PIL path is probably still being called somewhere.

**Test 3 — Window resize doesn't crash:**
The method handles window resize by recreating the texture when `sz != self._hud_composite_size`. This is tested implicitly by the capture tool (which may resize the window on startup). If the capture succeeds, resize handling works.

**Test 4 — Compare visual output:**
```bash
python tools/run_ursina_capture_once.py --seconds 12 --subdir r5_pil_bypass --stem before_bypass --no-llm --fps-probe --hero-fps-probe-count 5 --fps-warmup-sec 8
```
Run this BEFORE making changes (on the current codebase). Save the screenshot. Then make the changes and run the "after" capture. Compare the two screenshots side by side. The HUD layout, text, colors, and transparency must be identical.

### Expected Performance Improvement

**Before (measured):**
```
hud_texture_upload: avg=17.7ms  P90=49.5ms  max=58.2ms
```

**After (expected):**
```
hud_texture_upload: avg=3-8ms  P90=5-15ms  max=15-25ms
```

The savings come from:
- Eliminating PIL.Image.frombytes() (~3-5ms for 8MB)
- Eliminating PIL.Image.transpose(FLIP_TOP_BOTTOM) (~5-10ms for 8MB)
- Eliminating PIL.Image.tobytes() (~2-3ms for 8MB)
- Eliminating Ursina's tex.apply() which does ANOTHER PIL transpose internally (~10-15ms)

---

## PHASE 2: WORLD-SPACE UI AS NATIVE URSINA ENTITIES

### Context for All Phase 2 Agents

**In Ursina 3D mode, the game currently has NO world-space UI.** No health bars, no building labels, no hero names, no damage numbers. This is because `skip_pygame_world=True` prevents `PygameRenderer._draw_world_layers()` from running, and no Ursina-native equivalents were ever built.

These features DO exist in `--renderer pygame` mode, where they're drawn by the following renderers:

| Feature | Pygame Renderer File | Pygame Function |
|---------|---------------------|-----------------|
| Hero health bars | `game/graphics/renderers/hero_renderer.py:141-152` | `HeroRenderer.render()` |
| Hero names + gold | `game/graphics/renderers/hero_renderer.py:154-165` | `HeroRenderer.render()` |
| Hero "Zzz" rest indicator | `game/graphics/renderers/hero_renderer.py:169-172` | `HeroRenderer.render()` |
| Enemy health bars | `game/graphics/renderers/enemy_renderer.py:103-114` | `EnemyRenderer.render()` |
| Building labels (27 types) | `game/graphics/renderers/building_renderer.py:97-176` | `BuildingRenderer.render()` |
| Building HP bars (damaged) | `game/graphics/renderers/building_renderer.py:85-94` | `BuildingRenderer._draw_base()` |
| Building gold/tax displays | `game/graphics/renderers/building_renderer.py:139-175` | `BuildingRenderer.render()` |
| Peasant/Guard/TC health bars | `game/graphics/renderers/worker_renderer.py` | Various `_render_*()` methods |
| Tax collector gold/state | `game/graphics/renderers/worker_renderer.py:202-214` | `_render_tax_collector()` |
| Bounty flag + reward text | `game/graphics/renderers/bounty_renderer.py:27-103` | `render_bounty()` |

**Your job is to create Ursina-native equivalents using Billboard entities.** These must be 3D entities in the Panda3D scene graph that Ursina manages — NOT pygame drawings uploaded via the HUD texture. Ursina handles the 3D math of keeping Billboards facing the camera and correctly positioned relative to their parent entities.

**Architectural rule:** The pygame HUD surface (`engine.screen`) must contain ONLY screen-space UI (top bar, bottom bar, menus, perf overlay). Any UI element that moves with the camera or is attached to a world-space entity MUST be a native Ursina entity.

### Round 1 — Parallel Phase 2 Tasks

Phase 2 is split across three agents working in parallel. Each agent owns a distinct set of files and features with no overlap.

---

### Agent 03: Building Labels & Building HP Bars

**Scope:** Create native Ursina text entities for all 27 building types, plus HP bar quads for damaged buildings.

**Where to add code:** `game/graphics/ursina_renderer.py` inside the existing `_sync_snapshot_buildings()` method (line 603+). This method already iterates all buildings in the snapshot and creates/updates their 3D entities. You will add label and HP bar child entities to each building's Ursina Entity.

**Implementation — Building Labels:**

For each building, create a child `Text` entity (Ursina's built-in text system) attached to the building's 3D entity. The text should be billboard-mode (always faces camera).

```python
from ursina import Text

# Inside the building sync loop, after the building entity `ent` exists:
label_ent = getattr(ent, '_ks_label', None)
if label_ent is None:
    label_ent = Text(
        text=building_type.upper(),
        parent=ent,
        origin=(0, 0),
        scale=15,
        color=color.white,
        billboard=True,
        y=1.2,  # offset above building model
    )
    label_ent.background = True
    label_ent.background_color = color.color(0, 0, 0, 0.5)
    ent._ks_label = label_ent
```

**Label text mapping** (use the building type from the snapshot, matching the pygame labels):

| `building_type` | Label Text | Font Scale |
|-----------------|-----------|------------|
| `castle` | `CASTLE` | 18 |
| `warrior_guild` | `WARRIORS` | 15 |
| `ranger_guild` | `RANGERS` | 15 |
| `rogue_guild` | `ROGUES` | 15 |
| `wizard_guild` | `WIZARDS` | 15 |
| `market` | `MARKET` | 15 |
| `blacksmith` | `SMITH` | 15 |
| `inn` | `INN` | 15 |
| `trading_post` | `TRADE` | 15 |
| `guard_tower` | `GUARDS` | 14 |
| `house` | `HOUSE` | 14 |
| `farm` | `FARM` | 14 |
| `palace` | `PALACE L{level}` | 18 |
| All temples | Temple name (e.g., `AGRELA`) | 14 |
| `ballista_tower` | `BALLISTA` | 14 |
| `wizard_tower` | `WIZ TOWER` | 14 |
| `fairground` | `FAIR` | 14 |
| `library` | `LIBRARY` | 14 |
| `gardens` | `GARDENS` | 14 |
| `gnome_hovel` | `GNOMES` | 14 |
| `elven_bungalow` | `ELVES` | 14 |
| `dwarven_settlement` | `DWARVES` | 14 |

Store the label mapping in a `_BUILDING_LABEL_MAP` dict at module level so it's not reconstructed per frame.

**Implementation — Building HP Bars:**

Only show HP bars for damaged buildings (`hp < max_hp`). Create a child Entity with a colored quad:

```python
hp_bar_ent = getattr(ent, '_ks_hp_bar', None)
hp = getattr(b, 'hp', 0)
max_hp = getattr(b, 'max_hp', 1)

if hp < max_hp and max_hp > 0:
    if hp_bar_ent is None:
        hp_bar_ent = Entity(
            parent=ent,
            model='quad',
            color=color.green if hp / max_hp > 0.5 else color.red,
            scale=(1.0 * (hp / max_hp), 0.05, 1),
            y=1.5,
            billboard=True,
            unlit=True,
        )
        ent._ks_hp_bar = hp_bar_ent
    else:
        ratio = hp / max_hp
        hp_bar_ent.scale_x = ratio
        hp_bar_ent.color = color.green if ratio > 0.5 else color.red
        hp_bar_ent.enabled = True
elif hp_bar_ent is not None:
    hp_bar_ent.enabled = False
```

**Building Gold/Tax Display:**

Create a second text child below the label showing gold/tax when applicable:

```python
gold_ent = getattr(ent, '_ks_gold_label', None)
stash = int(getattr(b, 'stash_gold', 0) or getattr(b, 'stored_tax_gold', 0) or 0)
if stash > 0:
    text = f"${stash}"
    if gold_ent is None:
        gold_ent = Text(
            text=text,
            parent=ent,
            origin=(0, 0),
            scale=12,
            color=color.color(45, 0.8, 1.0),  # gold yellow
            billboard=True,
            y=0.9,
        )
        ent._ks_gold_label = gold_ent
    else:
        if gold_ent.text != text:
            gold_ent.text = text
        gold_ent.enabled = True
elif gold_ent is not None:
    gold_ent.enabled = False
```

**Frustum culling compatibility:** The existing frustum culling code in `_sync_snapshot_buildings()` sets `ent.enabled = False` for off-screen buildings. When the parent entity is disabled, all children (label, HP bar, gold) are automatically hidden by Panda3D. No extra culling logic needed.

**How Agent 03 verifies:**
1. Run `python -m pytest tests/ -x -q` — 307 passed.
2. Run `python tools/run_ursina_capture_once.py --seconds 15 --subdir r5_building_labels --stem labels --no-llm --fps-probe --hero-fps-probe-count 5 --fps-warmup-sec 8`
3. Open the screenshot. Every visible building MUST have a white text label above it (CASTLE, INN, WARRIORS, etc.). Damaged buildings must show a colored bar above the label.
4. Compare to the pygame-mode screenshot (run `python main.py --renderer pygame` and press F12) to verify label text matches.
5. The `hud_texture_upload` P90 should NOT increase (labels are native Ursina, not pygame).

---

### Agent 08: Hero & Worker World-Space UI

**Scope:** Create native Ursina Billboard entities for hero names, hero gold display, hero rest indicator ("Zzz"), and worker labels (peasant/guard/tax collector symbols and state text).

**Where to add code:** `game/graphics/ursina_renderer.py` inside:
- `_sync_snapshot_heroes()` (line 806+) — for hero name, gold, rest indicator
- `_sync_snapshot_peasants()` (line 909+) — for peasant labels
- `_sync_snapshot_guards()` (line 950+) — for guard labels
- `_sync_snapshot_tax_collector()` (line 987+) — for tax collector gold/state

**Implementation — Hero Name Label:**

Inside the hero sync loop (after the billboard entity `ent` is created/updated and positioned), add a child text entity:

```python
hero_name = getattr(h, 'name', '') or ''
name_ent = getattr(ent, '_ks_name_label', None)
if name_ent is None and hero_name:
    name_ent = Text(
        text=hero_name,
        parent=ent,
        origin=(0, 0),
        scale=12,
        color=color.white,
        billboard=True,
        y=-0.6,  # below the unit billboard
    )
    ent._ks_name_label = name_ent
elif name_ent is not None and name_ent.text != hero_name:
    name_ent.text = hero_name
```

**Position notes:** The unit billboard entity is already positioned at world coordinates by `_sync_unit_atlas_billboard()`. The `y=-0.6` offset places the name below the sprite. You may need to adjust this value based on the `UNIT_BILLBOARD_SCALE` constant (0.62 at line 81). Test visually with the capture tool.

**Implementation — Hero Gold Display:**

```python
hero_gold = int(getattr(h, 'gold', 0) or 0)
hero_taxed = int(getattr(h, 'taxed_gold', 0) or 0)
total_gold = hero_gold + hero_taxed
gold_ent = getattr(ent, '_ks_gold_label', None)
if total_gold > 0:
    gold_text = f"${hero_gold}(+{hero_taxed})" if hero_taxed > 0 else f"${hero_gold}"
    if gold_ent is None:
        gold_ent = Text(
            text=gold_text,
            parent=ent,
            origin=(0, 0),
            scale=10,
            color=color.color(45, 0.8, 1.0),  # gold yellow HSV
            billboard=True,
            y=-0.8,
        )
        ent._ks_gold_label = gold_ent
    else:
        if gold_ent.text != gold_text:
            gold_ent.text = gold_text
        gold_ent.enabled = True
elif gold_ent is not None:
    gold_ent.enabled = False
```

**Implementation — Hero "Zzz" Rest Indicator:**

```python
is_resting = (getattr(h, 'state', '') == 'RESTING')
rest_ent = getattr(ent, '_ks_rest_label', None)
if is_resting:
    if rest_ent is None:
        rest_ent = Text(
            text='Zzz',
            parent=ent,
            origin=(0, 0),
            scale=12,
            color=color.color(210, 0.3, 1.0),  # light blue
            billboard=True,
            y=0.7,
            x=0.3,
        )
        ent._ks_rest_label = rest_ent
    else:
        rest_ent.enabled = True
elif rest_ent is not None:
    rest_ent.enabled = False
```

**Implementation — Worker Labels (Peasant/Guard/Tax Collector):**

For each worker type, add a small identifying text label. These are simpler than hero labels:

```python
# In _sync_snapshot_tax_collector, after billboard sync:
carried = int(getattr(tc, 'carried_gold', 0) or 0)
tc_gold_ent = getattr(ent, '_ks_tc_gold', None)
if carried > 0:
    tc_text = f"${carried}"
    if tc_gold_ent is None:
        tc_gold_ent = Text(
            text=tc_text, parent=ent, origin=(0,0), scale=10,
            color=color.color(45, 0.8, 1.0), billboard=True, y=0.5,
        )
        ent._ks_tc_gold = tc_gold_ent
    else:
        if tc_gold_ent.text != tc_text:
            tc_gold_ent.text = tc_text
        tc_gold_ent.enabled = True
elif tc_gold_ent is not None:
    tc_gold_ent.enabled = False
```

**Performance guard:** Text entities in Ursina use Panda3D's TextNode, which is GPU-rendered. They do NOT go through the pygame → PIL → GPU texture upload pipeline. Creating a Text entity has a one-time cost (~0.5ms); updating `.text` has a small cost (~0.1ms); updating `.enabled` is essentially free. Do NOT recreate Text entities every frame — create once, then toggle `.enabled` and update `.text` only when the value changes.

**How Agent 08 verifies:**
1. Run `python -m pytest tests/ -x -q` — 307 passed.
2. Run `python tools/run_ursina_capture_once.py --seconds 15 --subdir r5_hero_labels --stem heroes --no-llm --fps-probe --hero-fps-probe-count 10 --fps-warmup-sec 8`
3. Open the screenshot. Each hero must have a white name label below their sprite. Heroes with gold must show a gold-colored "$X" or "$X(+Y)" below the name. Resting heroes must show "Zzz" above-right of their sprite.
4. Check that `ursina_renderer` stage P90 did not increase by more than 2ms (text entities are cheap, but too many would add up).

---

### Agent 09: Health Bars for All Entity Types

**Scope:** Create native Ursina Billboard quads for health bars on heroes, enemies, peasants, and guards.

**Where to add code:** `game/graphics/ursina_renderer.py` inside the same sync methods as Agent 08, but focusing exclusively on health bar quads (not text labels).

**Implementation Pattern (same for all entity types):**

Each health bar consists of two child entities parented to the unit billboard:
1. A dark background quad (full width)
2. A colored foreground quad (width proportional to HP ratio)

```python
# After the billboard entity `ent` exists and is positioned:
hp = int(getattr(entity_obj, 'hp', 0) or 0)
max_hp = int(getattr(entity_obj, 'max_hp', 1) or 1)

hp_bg = getattr(ent, '_ks_hp_bg', None)
hp_fg = getattr(ent, '_ks_hp_fg', None)

if max_hp > 0 and hp > 0 and hp < max_hp:
    ratio = hp / max_hp
    bar_w = 0.8   # world units wide (adjust per entity type)
    bar_h = 0.04  # thin bar
    bar_y = 0.45  # above sprite (adjust per entity type)

    if hp_bg is None:
        hp_bg = Entity(
            parent=ent, model='quad', color=color.color(0, 0, 0.25),
            scale=(bar_w, bar_h, 1), position=(0, bar_y, -0.01),
            billboard=True, unlit=True,
        )
        hp_bg.set_depth_test(False)
        ent._ks_hp_bg = hp_bg

    if hp_fg is None:
        hp_fg = Entity(
            parent=ent, model='quad', color=color.green,
            scale=(bar_w * ratio, bar_h, 1),
            position=(-(bar_w * (1 - ratio) / 2), bar_y, -0.02),
            billboard=True, unlit=True,
        )
        hp_fg.set_depth_test(False)
        ent._ks_hp_fg = hp_fg
    else:
        hp_fg.scale_x = bar_w * ratio
        hp_fg.x = -(bar_w * (1 - ratio) / 2)
        hp_fg.color = color.green if ratio > 0.5 else color.red

    hp_bg.enabled = True
    hp_fg.enabled = True

elif hp == max_hp:
    # Full health — hide bars
    if hp_bg is not None:
        hp_bg.enabled = False
    if hp_fg is not None:
        hp_fg.enabled = False
else:
    # Dead — hide bars
    if hp_bg is not None:
        hp_bg.enabled = False
    if hp_fg is not None:
        hp_fg.enabled = False
```

**Per-entity-type sizing:**

| Entity Type | `bar_w` | `bar_h` | `bar_y` | Color Threshold |
|-------------|---------|---------|---------|-----------------|
| Hero | 0.8 | 0.04 | 0.50 | Green if >50%, else red |
| Enemy | 0.6 | 0.03 | 0.40 | Green if >50%, else red |
| Peasant | 0.5 | 0.03 | 0.35 | Green if >50%, else red |
| Guard | 0.7 | 0.03 | 0.45 | Green if >50%, else red |

**Foreground bar positioning math:** The foreground bar must be left-aligned with the background. Since Ursina quads are center-anchored, when we scale the foreground to `bar_w * ratio`, we need to shift it left by `bar_w * (1 - ratio) / 2` to keep its left edge aligned with the background's left edge.

**Performance guard:** Each health bar is 2 quads (background + foreground). At 30 heroes + 50 enemies + 10 peasants + 5 guards = 95 entities × 2 quads = 190 additional scene graph nodes. Since most entities have full health, most bars are hidden (`.enabled = False`), costing zero Panda3D traversal. Only damaged entities have visible bars.

**How Agent 09 verifies:**
1. Run `python -m pytest tests/ -x -q` — 307 passed.
2. Run `python tools/run_ursina_capture_once.py --seconds 20 --subdir r5_health_bars --stem bars --no-llm --fps-probe --hero-fps-probe-count 10 --fps-warmup-sec 10`
3. Open the screenshot. Look for heroes or enemies in combat — damaged entities must show a colored bar above their sprite (green above 50%, red below). Full-health entities should NOT show bars.
4. If no combat is visible in the screenshot (heroes haven't found enemies yet), increase `--seconds` to 30 or 40 to give the AI time to engage.
5. Check that `ursina_renderer` P90 increased by less than 3ms from baseline.

---

## PHASE 2 ROUND 2 — CLEANUP & INTEGRATION

After Round 1 tasks are complete and verified, the following cleanup task runs.

### Agent 10: Profiling Pass & World-Space Rendering Guard

**Scope:** Run before/after profiling comparisons, add a safety guard to prevent world-space UI from being accidentally drawn on the pygame surface in Ursina mode, and assess whether Phase 3 (dirty-region upload) is needed.

**Task 1 — Before/After Profiling:**

Run the following capture command on the final codebase (with all Phase 1 + Phase 2 changes):

```bash
python tools/run_ursina_capture_once.py --seconds 20 --subdir r5_final_perf --stem final --no-llm --fps-probe --hero-fps-probe-count 10 --fps-warmup-sec 8
```

Record the `[fps-probe-stage]` output. Compare against these baseline numbers:

```
BASELINE (before this sprint):
  hud_texture_upload: avg=13.4ms  P90=49.4ms  max=67.0ms
  ursina_renderer:    avg=6.6ms   P90=7.6ms   max=30.5ms
  tick_simulation:    avg=1.7ms   P90=3.7ms   max=15.7ms
  pygame_hud_render:  avg=2.0ms   P90=2.5ms   max=5.0ms
```

**Success criteria:**
- `hud_texture_upload` P90 must be **below 15ms** (from 49ms baseline)
- `ursina_renderer` P90 must remain **below 12ms** (world-space UI adds some cost)
- Overall avg FPS must **increase** (from 30.8 baseline with 10 heroes)

**Task 2 — Phase 3 Assessment:**

If `hud_texture_upload` P90 is still above 10ms after Phase 1, write a brief note in the plan file recommending Phase 3 implementation. If P90 is below 10ms, write a note saying Phase 3 is not needed.

**Task 3 — Verify World-Space UI Visual Quality:**

Take a screenshot with 10 heroes and compare against a pygame-mode screenshot:
```bash
# Ursina mode:
python tools/run_ursina_capture_once.py --seconds 20 --subdir r5_final_visual --stem ursina --no-llm --hero-fps-probe-count 10 --fps-warmup-sec 12

# Pygame mode (manual — run, wait 20 seconds, press F12):
python main.py --renderer pygame --no-llm
```

Check that:
- Building labels are present and readable in Ursina mode
- Hero names appear below hero sprites
- Health bars appear on damaged entities
- All text is correctly oriented (not upside-down or mirrored)

---

## PHASE 3: DIRTY-REGION UPLOAD (ROADMAP — IMPLEMENT ONLY IF NEEDED)

### When to Implement

Implement Phase 3 ONLY if the Agent 10 profiling pass shows `hud_texture_upload` P90 still exceeds 10ms after Phase 1 (PIL bypass). If Phase 1 brings P90 below 10ms, this phase is unnecessary.

### Concept

Instead of uploading the entire 1920x1080 surface (8MB) when the HUD changes, track which rectangular region changed and upload only that region using Panda3D's `Texture.load_sub_image()` API.

### How It Would Work

1. **Before and after fingerprinting:** Instead of one CRC32 of the full surface, divide the surface into a grid (e.g., 8×6 = 48 cells of 240×180 each). Compute a fingerprint per cell.

2. **Identify changed region:** Compare per-cell fingerprints. Compute the bounding rectangle of all changed cells.

3. **Extract sub-image bytes:** Use `pygame.Surface.subsurface(rect)` to get only the changed region, then `pygame.image.tobytes()` on that sub-surface.

4. **Upload sub-image:** Use Panda3D's `Texture.load_sub_image()` to upload only the changed rectangle:
   ```python
   from panda3d.core import PNMImage
   sub_img = PNMImage(sub_w, sub_h, 4)  # RGBA
   # Fill sub_img from bytes...
   panda_tex.load_sub_image(sub_img, offset_x, offset_y)
   ```

5. **Expected gain:** If only the perf overlay (300×200px) changed, upload is ~240KB instead of ~8MB — a 33× reduction. At the same upload speed, this would take ~1.5ms instead of ~49ms.

### Why This Is A Roadmap, Not An Implementation

- `Texture.load_sub_image()` takes a `PNMImage`, not raw bytes. Converting to PNMImage adds overhead.
- The grid fingerprinting adds per-frame cost even when nothing changed.
- If Phase 1 brings the upload cost to ~5-10ms, the complexity of dirty-region tracking is not worth the marginal improvement.
- The implementation requires careful handling of the Y-flip (Panda3D's sub-image coordinate system may differ from pygame's).

### Files That Would Be Modified

- `game/graphics/ursina_app.py` — `_refresh_ui_overlay_texture()` and `_hud_quick_fingerprint()`
- No other files affected.

---

## AGENT DISPATCH SUMMARY

### Round 1 (Parallel)

| Agent | Task | Files Modified | Verification |
|-------|------|---------------|-------------|
| **Agent 03** | PIL bypass in `_refresh_ui_overlay_texture()` | `game/graphics/ursina_app.py` | Unit tests + Ursina capture (P90 < 20ms) |
| **Agent 09** | Health bars for all entity types | `game/graphics/ursina_renderer.py` | Unit tests + Ursina capture (bars visible on damaged entities) |

### Round 2 (Parallel, after Round 1 merged)

| Agent | Task | Files Modified | Verification |
|-------|------|---------------|-------------|
| **Agent 03** | Building labels + HP bars + gold displays | `game/graphics/ursina_renderer.py` | Unit tests + Ursina capture (labels visible on all buildings) |
| **Agent 08** | Hero names, gold, rest indicator, worker labels | `game/graphics/ursina_renderer.py` | Unit tests + Ursina capture (names visible below heroes) |

### Round 3 (Sequential)

| Agent | Task | Files Modified | Verification |
|-------|------|---------------|-------------|
| **Agent 10** | Before/after profiling + Phase 3 assessment | None (read-only profiling) | Compare hud_texture_upload P90 before/after |

### File Ownership (No Conflicts)

- `game/graphics/ursina_app.py` — Agent 03 (Round 1 only)
- `game/graphics/ursina_renderer.py` — Agent 09 (Round 1), then Agent 03 + Agent 08 (Round 2, different methods)
  - Agent 09: `_sync_snapshot_heroes()`, `_sync_snapshot_enemies()`, `_sync_snapshot_peasants()`, `_sync_snapshot_guards()` — health bar code only
  - Agent 03: `_sync_snapshot_buildings()` — labels, HP bars, gold
  - Agent 08: `_sync_snapshot_heroes()`, `_sync_snapshot_tax_collector()` — text labels only

**IMPORTANT for Round 2:** Agent 03 and Agent 08 both modify `ursina_renderer.py` but in different methods. Agent 09's Round 1 health bar code goes in the same methods as Agent 08's Round 2 text labels, but at different insertion points (health bar code goes before the `return` at the end of the loop; text label code goes after the billboard sync call). **Agents must not rewrite each other's additions.** If a merge conflict arises, the orchestrator should resolve by keeping both additions.

---

## DEFINITION OF DONE (SPRINT LEVEL)

- [ ] `hud_texture_upload` P90 is below 15ms (from 49ms baseline) — measured via `--fps-probe`
- [ ] All 307 unit tests pass
- [ ] Building labels visible in Ursina 3D mode (all 27 building types)
- [ ] Hero names visible below hero sprites in Ursina 3D mode
- [ ] Health bars visible on damaged heroes/enemies in Ursina 3D mode
- [ ] Hero gold display visible when heroes have gold
- [ ] "Zzz" indicator visible on resting heroes
- [ ] No visual regression in pygame-only mode (`--renderer pygame`)
- [ ] No increase in `ursina_renderer` P90 beyond 12ms
- [ ] Screenshot comparison: Ursina mode shows world-space UI parity with pygame mode for the features listed above

---

## APPENDIX: KEY FILE LOCATIONS AND LINE NUMBERS

| File | Purpose | Key Lines |
|------|---------|-----------|
| `game/graphics/ursina_app.py` | HUD texture upload pipeline | 735-795 (`_refresh_ui_overlay_texture`) |
| `game/graphics/ursina_app.py` | HUD fingerprint | 253-270 (`_hud_quick_fingerprint`) |
| `game/graphics/ursina_app.py` | UI overlay entity creation | 138-154 |
| `game/graphics/ursina_app.py` | Auto-exit screenshot | 1042-1077 |
| `game/graphics/ursina_renderer.py` | Building sync | 603+ (`_sync_snapshot_buildings`) |
| `game/graphics/ursina_renderer.py` | Hero sync | 806+ (`_sync_snapshot_heroes`) |
| `game/graphics/ursina_renderer.py` | Enemy sync | 863+ (`_sync_snapshot_enemies`) |
| `game/graphics/ursina_renderer.py` | Peasant sync | 909+ (`_sync_snapshot_peasants`) |
| `game/graphics/ursina_renderer.py` | Guard sync | 950+ (`_sync_snapshot_guards`) |
| `game/graphics/ursina_renderer.py` | Tax collector sync | 987+ (`_sync_snapshot_tax_collector`) |
| `game/graphics/ursina_renderer.py` | Billboard sync (interpolation) | 403+ (`_sync_unit_atlas_billboard`) |
| `game/graphics/renderers/hero_renderer.py` | Pygame hero rendering (reference) | 141-172 |
| `game/graphics/renderers/building_renderer.py` | Pygame building rendering (reference) | 85-176 |
| `game/graphics/renderers/worker_renderer.py` | Pygame worker rendering (reference) | 156-253 |
| `game/graphics/renderers/bounty_renderer.py` | Pygame bounty rendering (reference) | 27-103 |
| `tools/run_ursina_capture_once.py` | Ursina capture tool | Entire file |
| `tools/ursina_screenshot.py` | Screenshot path utilities | 30-71 |
| `ursina/texture.py` (site-packages) | Ursina Texture internals | 38-46, 161-167 |

---

## APPENDIX: URSINA TEXT AND ENTITY API REFERENCE

For agents who may not be familiar with Ursina's API:

**Creating a Text entity:**
```python
from ursina import Text, color

label = Text(
    text='CASTLE',       # The string to display
    parent=some_entity,  # Parent in scene graph (inherits position)
    origin=(0, 0),       # Anchor point: (0,0) = center, (-0.5, 0) = left-aligned
    scale=15,            # Font size (world units, not pixels)
    color=color.white,   # Text color
    billboard=True,      # Always faces camera
    y=1.0,               # Y offset from parent (up)
    x=0.0,               # X offset from parent (right)
)
```

**Creating a colored quad (for health bars):**
```python
from ursina import Entity, color

bar = Entity(
    parent=some_entity,
    model='quad',
    color=color.green,
    scale=(0.8, 0.04, 1),   # (width, height, depth)
    position=(0, 0.5, -0.01),  # (x, y, z) offset from parent
    billboard=True,
    unlit=True,  # No lighting (always bright)
)
bar.set_depth_test(False)  # Always visible, not occluded by 3D geometry
```

**Toggling visibility:**
```python
entity.enabled = False  # Hides entity and all children, zero render cost
entity.enabled = True   # Shows entity
```

**Updating text:**
```python
label.text = 'new text'  # Rebuilds TextNode mesh (~0.1ms per update)
```

**Color from HSV:**
```python
color.color(hue, saturation, value)  # Hue in degrees (0-360)
# Gold yellow: color.color(45, 0.8, 1.0)
# Light blue:  color.color(210, 0.3, 1.0)
# Red:         color.color(0, 1.0, 0.8)
# Green:       color.color(120, 1.0, 0.7)
```
