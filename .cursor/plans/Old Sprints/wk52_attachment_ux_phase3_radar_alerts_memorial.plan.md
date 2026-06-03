---
name: WK52 Phase 3 Attachment — Radar Minimap, Pin Alerts, Watch Card & Memorial Card
overview: >
  WK52 completes the next meaningful slice of the WK49 Phase 3 Attachment roadmap.
  Four features ship: (1) a live radar minimap; (2) event-driven pin alerts with Recall
  button flash; (3) a pinned-hero watch card that floats above the minimap showing a
  zoomed hero map + HP/XP/Level stats with expand/minimize toggle and dynamic left-panel
  height adjustment; (4) a Memorial Card overlay for fallen pinned heroes.
todos:
  - id: wave0_design
    content: "Wave 0 (parallel): Agent 02 acceptance criteria (low); Agent 04 determinism review (low)."
    status: pending
  - id: wave1_events
    content: "Wave 1: Agent 03 (high) — HERO_LEVEL_UP event, hero_id in all alert payloads, PinAlertWatcher skeleton, tests."
    status: pending
  - id: wave2_ui
    content: "Wave 2: Agent 08 (high) — radar minimap, watch card, recall flash, memorial button + card, alert wiring, screenshot scenario."
    status: pending
  - id: wave3_qa
    content: "Wave 3 (parallel): Agent 11 (medium) QA suite + determinism_guard + screenshots; Agent 10 (low) perf consult."
    status: pending
  - id: human_gate
    content: "Human gate: Jaimie 10-minute playtest using Agent 11's exact checklist."
    status: pending
  - id: pm_close
    content: "PM closeout: PM hub update, CHANGELOG, version bump decision, git commit/push on Jaimie approval."
    status: pending
isProject: false
---

# WK52 — Phase 3 Attachment UX: Radar Minimap, Pin Alerts & Memorial Card

> Sprint plan authored by Agent 01 (PM/ExecutiveProducer). Implementing agents: 02, 03, 04, 08, 10, 11.
> Worker agents: read ONLY your assigned section and the Architecture section. Do not read other agents' sections.

---

## North Star

A pinned hero should feel like *your* hero — someone you're tracking, worrying about, and grieving
when they fall. WK51 gave you the pin and recall. WK52 makes the world respond: you can see where
they are at a glance on the minimap, the game shouts at you when something important happens to them,
and when they die you get a proper send-off.

---

## Locked Scope

### In scope

1. **Radar minimap** — the bottom-bar minimap box (currently empty) becomes a live overhead radar.
   World entities are drawn as proportional colored dots. The pinned hero gets a larger gold dot with
   a soft glow ring. Castle gets a white hollow square. Enemies and lairs are differentiated by color.
   Only fog-revealed entities are shown.

2. **Pin alerts** — when the pinned hero triggers any of the following, a HUD toast fires AND the
   Recall button flashes red 3 times (750 ms total):
   - HP drops to ≤ 25% (polled, 30-second cooldown so it does not spam)
   - Hero levels up (event: `HERO_LEVEL_UP` — new this sprint)
   - Hero enters an inn (event: `HERO_ENTERED_BUILDING`, filtered for `building_type == "inn"`)
   - Hero claims a bounty (event: `BOUNTY_CLAIMED`)

3. **Pinned-hero watch card** — a compact card that floats above/over the minimap in the
   bottom-left corner. When a hero is pinned it rises above the bottom bar showing:
   - A zoomed hero-centered map view (same 2D rendering path as the right-panel hero focus)
   - HP bar with current/max values
   - XP bar with current/max values
   - Level label
   - A greyed-out "Mana: —" row reserved for a future mana stat (do not wire up mana logic
     this sprint — just render the placeholder row)

   The card has a 14 px header strip (hero name + expand/collapse chevron). Clicking the
   chevron or the header toggles between **expanded** (full card visible above the minimap)
   and **minimized** (only the 14 px header peeks above the minimap panel's top edge — the
   body slides behind the bottom bar and is hidden).

   **Left panel dynamic height:** when the watch card is expanded and the left panel is open
   (hero or peasant selected), the left panel's bottom boundary moves up to the watch card's
   top edge so the two never overlap. When the watch card is minimized the left panel reclaims
   the full height (minus the 14 px tab). This adjustment is applied inside
   `_layout_rects_for_screen()` which already owns all layout geometry.

   **Recall button integration:** clicking the Recall button when the watch card is minimized
   also expands it (in addition to the existing camera-pan + selection behavior).

4. **Memorial card** — when the pinned hero falls, a "Memorial" button appears in the bottom HUD
   (to the right of the Recall button). Clicking it pauses the game and shows a full-screen overlay
   card with the hero's name, class, level, career stats, and a generated epitaph. A "Farewell"
   dismiss button closes the card and unpauses.

### Out of scope (defer to WK53+)

- "Finds a lair" alert trigger (no proximity discovery event exists; deferred)
- Multi-pin / cycling through several pinned heroes
- Alert sound effects (Agent 14 work, deferred)
- Save/load persistence of pin or memorial state
- Emotional state display (Phase 5)
- Any changes to AI behavior or LLM prompts

### Determinism invariant (mandatory — read before touching anything)

The pin slot, alert watcher, and memorial card are **pure presentation state**. They must never
write to `SimEngine`, `Hero`, `Bounty`, or any other sim object. They read from `game_state` and
`hero_profiles_by_id` only. Agent 04 will verify this explicitly.

---

## Architecture

```
EventBus (sim layer)
  │
  ├─ HERO_LEVEL_UP ──────────────────────────────────────────┐
  ├─ HERO_ENTERED_BUILDING (inn filter) ─────────────────────┤
  └─ BOUNTY_CLAIMED ─────────────────────────────────────────┤
                                                              ▼
                                                    PinAlertWatcher
                                                    (game/ui/pin_alert_watcher.py)
                                                              │
                                          ┌───────────────────┤
                                          ▼                   ▼
                                  hud.add_message()   hud.trigger_recall_flash()
                                  (toast text)        (_recall_flash_end_ms)

HUD.render() each frame
  ├─ _layout_rects_for_screen()  ← MODIFIED: left panel height shrinks when watch card expanded
  ├─ _render_radar_minimap()     ← NEW (reads game_state heroes/enemies/buildings)
  ├─ _render_watch_card_chrome() ← NEW (header + stats bars; map rect stored for render_coordinator)
  ├─ _render_recall_button()     ← MODIFIED (flash + expands watch card on click)
  ├─ _render_memorial_button()   ← NEW (visible only when _pending_memorial is set)
  └─ memorial_card.render()      ← NEW (full-screen overlay, pauses game)

render_coordinator.py (after hud.render())
  └─ if hud.watch_card_map_rect set:
       _render_hero_minimap(screen, hud.watch_card_map_rect, pinned_hero, snapshot)
       ← reuses the EXISTING zoomed-map renderer — no new renderer code needed

PinAlertWatcher.check_low_health()  ← called each frame from HUD.render()
  (reads hero_profiles_by_id, checks hp%, 30s cooldown stored in PinSlot)
```

---

## Files Touched

| File | Owner | Change |
|------|-------|--------|
| `game/events.py` | Agent 03 | Add `HERO_LEVEL_UP` to `GameEventType` |
| `game/entities/hero.py` | Agent 03 | Add `_event_bus` attr + `set_event_bus()` + emit in `level_up()` |
| `game/engine.py` | Agent 03 | Wire `hero._event_bus` after `self.heroes.append(hero)` |
| `game/entities/buildings/base.py` | Agent 03 | Add `hero_id` field to `HERO_ENTERED_BUILDING` payload |
| `game/sim_engine.py` | Agent 03 | Add `hero_id` to both `BOUNTY_CLAIMED` emit sites |
| `game/ui/pin_slot.py` | Agent 03 | Add `low_health_alerted_ms` and `pinned_name` fields |
| `game/ui/pin_alert_watcher.py` | Agent 03 | **NEW** — event subscriptions + alert dispatch skeleton |
| `game/ui/hud.py` | Agent 08 | Layout, radar, watch card chrome+stats, recall flash, memorial button, watcher wiring |
| `game/engine_facades/render_coordinator.py` | Agent 08 | Render hero map into `watch_card_map_rect` after `hud.render()` |
| `game/ui/memorial_card.py` | Agent 08 | **NEW** — full-screen overlay card |
| `tools/screenshot_scenarios.py` | Agent 08 | New `wk52_pin_alerts` scenario |
| `tests/test_wk52_events.py` | Agent 03 | HERO_LEVEL_UP fires; payloads have hero_id |
| `tests/test_wk52_pin_alerts.py` | Agent 08 | Alert watcher behavior |
| `tests/test_wk52_minimap_radar.py` | Agent 08 | Radar coordinate math |
| `tests/test_wk52_memorial_card.py` | Agent 08 | Memorial record capture + epitaph |
| `tests/test_wk52_watch_card.py` | Agent 08 | Watch card layout math + expand/minimize state |

---

## WAVE 0 — Design Review (Parallel, no code)

### Agent 02 — GameDirector (LOW intelligence)

Read this plan and the WK49 Phase 3 roadmap
(`.cursor/plans/wk49_hero_profile_roadmap_6f3a1b2c.plan.md`, Phase 3 section).

Write acceptance criteria for all three features to your agent log. Specifically confirm:
- The radar minimap entity color scheme feels readable and thematically correct
- The alert messages are toned correctly for the game's voice
- The memorial card epitaph templates match the game's fantasy tone

No code changes. Log only.

### Agent 04 — NetworkingDeterminism (LOW intelligence)

Read the Architecture section of this plan. Confirm:
1. `PinAlertWatcher` never writes to any sim object (SimEngine, Hero, Bounty, World, etc.)
2. `memorial_card.py` only reads from a frozen `MemorialRecord` dataclass — it never queries live sim state
3. The low-health poll reads from `hero_profiles_by_id` (a snapshot) not from live `hero.hp`
4. `pin_slot.low_health_alerted_ms` and `pin_slot.pinned_name` are UI state, not sim state

Log your review verdict to your agent log. No code changes.

---

## WAVE 1 — Event Layer (Agent 03, HIGH intelligence)

### Context

You are Agent 03, TechnicalDirector. WK51 shipped `PinSlot` and the Recall button. WK52 adds
three features that need event and data plumbing before Agent 08 can build the UI. Your job is
entirely in the data/event layer: no HUD rendering, no overlay cards.

### Task 1 — Add `HERO_LEVEL_UP` to the event system

**File:** `game/events.py`

Add one line to `GameEventType`:

```python
HERO_LEVEL_UP = "hero_level_up"
```

Place it after `BOUNTY_CLAIMED` for readability.

**File:** `game/entities/hero.py`

Hero currently has no event bus access. Follow the same pattern buildings use
(`game/entities/buildings/base.py` lines 84, 243–245).

In `Hero.__init__` (after the existing attribute assignments), add:

```python
self._event_bus: object | None = None  # Set by engine after spawn (WK52)
```

Add a method after `__init__`:

```python
def set_event_bus(self, event_bus) -> None:
    """Wire the sim event bus so level-up can emit HERO_LEVEL_UP (WK52)."""
    self._event_bus = event_bus
```

In the existing `level_up()` method (currently at line ~619), emit the event AFTER mutating
level/hp so the listener sees the new level:

```python
def level_up(self):
    """Level up the hero."""
    self.level += 1
    self.max_hp += 20
    self.hp = self.max_hp  # Full heal on level up
    self.xp_to_level = int(self.xp_to_level * 1.5)
    # WK52: notify alert watcher
    if self._event_bus is not None:
        try:
            from game.events import GameEventType
            self._event_bus.emit({
                "type": GameEventType.HERO_LEVEL_UP.value,
                "hero_id": str(self.hero_id),
                "hero_name": str(self.name),
                "new_level": int(self.level),
            })
        except Exception:
            pass  # never let UI wiring break sim
```

**File:** `game/engine.py`

In `spawn_hero()` (around line 667), after `self.heroes.append(hero)`, add:

```python
# WK52: wire event bus so hero can emit HERO_LEVEL_UP
if hasattr(hero, "set_event_bus"):
    hero.set_event_bus(self.event_bus)
```

### Task 2 — Add `hero_id` to event payloads

These changes let `PinAlertWatcher` match events to the pinned hero by ID (more reliable than name).

**File:** `game/entities/buildings/base.py`

In `on_hero_enter()` (around line 255), the `HERO_ENTERED_BUILDING` emit already passes `hero`
as a live object. Add `hero_id` as a string field alongside it so listeners don't need to duck-type:

```python
self._event_bus.emit({
    "type": GameEventType.HERO_ENTERED_BUILDING.value,
    "hero": hero,
    "hero_id": str(getattr(hero, "hero_id", "") or ""),
    "building": self,
})
```

**File:** `game/sim_engine.py`

There are two `BOUNTY_CLAIMED` emit sites. Both need `hero_id`.

**Site 1** (around line 591) — `hero` object is in scope:

```python
{
    "type": GameEventType.BOUNTY_CLAIMED.value,
    "x": float(bounty.x),
    "y": float(bounty.y),
    "reward": bounty.reward,
    "hero": hero.name,
    "hero_id": str(getattr(hero, "hero_id", "") or ""),
}
```

**Site 2** (around line 745) — only `hero_name` is in scope. Look upward in that code block for
the hero object (it will be the loop variable or a lookup result). Extract `hero_id` from it the
same way. If only the name is available, emit `"hero_id": ""` rather than crashing.

### Task 3 — Extend `PinSlot`

**File:** `game/ui/pin_slot.py`

Add two fields to the `PinSlot` dataclass:

```python
@dataclass
class PinSlot:
    hero_id: Optional[str] = None
    pinned_at_ms: int = 0
    fallen_since_ms: Optional[int] = None
    low_health_alerted_ms: int = 0   # WK52: wall-clock ms of last low-health toast
    pinned_name: str = ""            # WK52: cached display name for fallback event matching
```

The `pinned_name` field is updated by HUD each render frame (Agent 08 handles that). You only need
to declare it here.

### Task 4 — Create `PinAlertWatcher` skeleton

**New file:** `game/ui/pin_alert_watcher.py`

This module owns ALL alert-matching logic so Agent 08 only has to call two methods from HUD.

```python
"""WK52: Watches the event bus for pinned-hero events and fires HUD alerts."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.ui.hud import HUD
    from game.ui.pin_slot import PinSlot

LOW_HEALTH_THRESHOLD = 0.25          # 25% HP triggers alert
LOW_HEALTH_COOLDOWN_MS = 30_000      # 30 seconds between repeated low-health toasts


class PinAlertWatcher:
    """
    Subscribes to EventBus and dispatches toast + recall-flash for pinned-hero events.

    Lifecycle:
      1. Instantiated inside HUD.__init__ with a reference to the PinSlot and HUD.
      2. HUD calls subscribe(event_bus) once after the engine wires its event bus
         (engine.__init__ already subscribes HUD_MESSAGE; Agent 03 adds this call there).
      3. HUD.render() calls check_low_health() each frame.
    """

    def __init__(self, pin_slot: "PinSlot", hud: "HUD") -> None:
        self._pin = pin_slot
        self._hud = hud

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def subscribe(self, event_bus) -> None:
        """Attach to EventBus. Safe to call before or after heroes spawn."""
        from game.events import GameEventType
        event_bus.subscribe(GameEventType.HERO_LEVEL_UP, self._on_level_up)
        event_bus.subscribe(GameEventType.HERO_ENTERED_BUILDING, self._on_entered_building)
        event_bus.subscribe(GameEventType.BOUNTY_CLAIMED, self._on_bounty_claimed)

    # ------------------------------------------------------------------
    # Frame poll (low health — not event driven)
    # ------------------------------------------------------------------

    def check_low_health(self, profiles: dict, now_ms: int) -> None:
        """
        Called every HUD render frame. Fires at most once per LOW_HEALTH_COOLDOWN_MS.
        profiles = game_state["hero_profiles_by_id"]
        """
        if self._pin.hero_id is None or self._pin.is_fallen():
            return
        prof = profiles.get(self._pin.hero_id)
        if prof is None:
            return
        health_pct = float(getattr(getattr(prof, "vitals", None), "health_percent", 1.0))
        if health_pct > LOW_HEALTH_THRESHOLD:
            return
        if now_ms - self._pin.low_health_alerted_ms < LOW_HEALTH_COOLDOWN_MS:
            return
        self._pin.low_health_alerted_ms = now_ms
        name = self._pin.pinned_name or "Hero"
        self._fire(f"⚠ {name} is low health! ({int(health_pct * 100)}%)", (255, 80, 80))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_level_up(self, event: dict) -> None:
        if not self._matches(event):
            return
        name = event.get("hero_name") or self._pin.pinned_name or "Hero"
        level = event.get("new_level", "?")
        self._fire(f"⭐ {name} reached Level {level}!", (255, 220, 50))

    def _on_entered_building(self, event: dict) -> None:
        if not self._matches(event):
            return
        building = event.get("building")
        bt = str(getattr(building, "building_type", "") or "").lower()
        if "inn" not in bt:
            return
        name = self._pin.pinned_name or "Hero"
        self._fire(f"\U0001f37a {name} checked into the inn.", (150, 200, 255))

    def _on_bounty_claimed(self, event: dict) -> None:
        if not self._matches(event):
            return
        name = self._pin.pinned_name or event.get("hero") or "Hero"
        reward = int(event.get("reward", 0))
        self._fire(f"✓ {name} claimed a bounty! (+{reward}g)", (100, 255, 150))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _matches(self, event: dict) -> bool:
        """True if the event concerns the currently pinned hero."""
        if self._pin.hero_id is None or self._pin.is_fallen():
            return False
        # Prefer hero_id string field (most events after WK52 patch)
        eid = str(event.get("hero_id", "") or "")
        if eid:
            return eid == self._pin.hero_id
        # Fallback: hero object with hero_id attr (HERO_ENTERED_BUILDING passes object)
        hero_obj = event.get("hero")
        if hero_obj is not None and not isinstance(hero_obj, str):
            oid = str(getattr(hero_obj, "hero_id", "") or "")
            if oid:
                return oid == self._pin.hero_id
        # Last resort: name match (for any payloads not yet updated)
        hname = str(event.get("hero") if isinstance(event.get("hero"), str) else "")
        hname = hname or str(event.get("hero_name", "") or "")
        return bool(hname and hname == self._pin.pinned_name)

    def _fire(self, text: str, color: tuple) -> None:
        """Send toast + flash the Recall button."""
        self._hud.add_message(text, color)
        self._hud.trigger_recall_flash()
```

### Task 5 — Wire `PinAlertWatcher` into the engine

**File:** `game/engine.py`

After the existing line that subscribes `HUD_MESSAGE` (around line 223):
```python
self.event_bus.subscribe(GameEventType.HUD_MESSAGE, self._on_hud_message_event)
```

Add:
```python
# WK52: wire pin alert watcher
if hasattr(getattr(self, "hud", None), "_alert_watcher"):
    try:
        self.hud._alert_watcher.subscribe(self.event_bus)
    except Exception:
        pass
```

### Task 6 — Tests (`tests/test_wk52_events.py`)

Write pytest tests that verify:

```python
# test 1: HERO_LEVEL_UP fires with correct payload
def test_hero_level_up_emits_event():
    from game.events import EventBus, GameEventType
    from game.entities.hero import Hero
    bus = EventBus()
    received = []
    bus.subscribe(GameEventType.HERO_LEVEL_UP, received.append)
    h = Hero(0.0, 0.0, hero_class="warrior", hero_id="test_h1")
    h.set_event_bus(bus)
    h.level_up()
    assert len(received) == 1
    assert received[0]["hero_id"] == "test_h1"
    assert received[0]["new_level"] == 2  # started at level 1

# test 2: no crash when event_bus is None
def test_hero_level_up_no_bus_is_safe():
    from game.entities.hero import Hero
    h = Hero(0.0, 0.0, hero_class="warrior")
    h.level_up()  # must not raise

# test 3: HERO_ENTERED_BUILDING payload contains hero_id
def test_hero_entered_building_has_hero_id():
    # Instantiate a minimal building with a mock event bus
    from game.events import EventBus, GameEventType
    from game.entities.buildings.base import Building
    bus = EventBus()
    received = []
    bus.subscribe(GameEventType.HERO_ENTERED_BUILDING, received.append)
    # ... create minimal building and hero, call on_hero_enter
    # assert received[0]["hero_id"] == hero.hero_id
```

Fill in the building/hero construction using existing patterns from `tests/test_building.py`.

### Verification (Agent 03)

After completing all tasks, run:

```powershell
python -m pytest tests/test_wk52_events.py -v
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_03_TechnicalDirector_Architecture.json
```

All three must pass cleanly before you mark yourself done.

---

## WAVE 2 — UI Layer (Agent 08, HIGH intelligence)

### Context

You are Agent 08, UX/UI Director. Agent 03 has completed the event layer: `HERO_LEVEL_UP` fires,
event payloads carry `hero_id`, `PinAlertWatcher` is scaffolded in `game/ui/pin_alert_watcher.py`,
and `PinSlot` has `low_health_alerted_ms` + `pinned_name`. Your job is all rendering.

Read these files before starting:
- `game/ui/hud.py` (full file — you will edit it extensively)
- `game/ui/pin_slot.py` (the updated version Agent 03 left)
- `game/ui/pin_alert_watcher.py` (the file Agent 03 created)
- `game/ui/widgets.py` (NineSlice, Panel, TextLabel — for button drawing patterns)
- `game/engine_facades/render_coordinator.py` (to understand the existing hero-minimap)
- `config.py` (for `MAP_WIDTH`, `MAP_HEIGHT`, `TILE_SIZE` — world size constants)

### World size reference

```python
from config import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE
WORLD_W = MAP_WIDTH * TILE_SIZE   # 150 * 32 = 4800  (world pixel width)
WORLD_H = MAP_HEIGHT * TILE_SIZE  # 150 * 32 = 4800  (world pixel height)
```

All hero/enemy/building `.x` and `.y` attributes are in these world-pixel coordinates.

---

### Task 1 — Bottom-bar layout update

**File:** `game/ui/hud.py`

Add the memorial button width constant near the top alongside `RECALL_BTN_W`:

```python
MEMORIAL_BTN_W = 90   # WK52: "⚰ Memorial" button, right of Recall
```

In `_layout_rects_for_screen()`, add the memorial rect after `recall`:

```python
minimap = pygame.Rect(margin, bottom.y + margin, minimap_size, minimap_size)
recall  = pygame.Rect(minimap.right + gutter, minimap.y, RECALL_BTN_W, minimap_size)
memorial = pygame.Rect(recall.right + gutter, minimap.y, MEMORIAL_BTN_W, minimap_size)
cmd_x   = memorial.right + gutter
cmd_w   = max(0, speed_rect.left - cmd_x - gutter)
command = pygame.Rect(cmd_x, bottom.y + margin, cmd_w, minimap_size)
return top, bottom, left, right, minimap, command, speed_rect, recall, memorial
```

Update every call-site that unpacks `_layout_rects_for_screen()` / `_compute_layout()` to also
receive `memorial`. There are three unpacking sites — grep for `_layout_rects_for_screen` to find
them all.

Add `memorial_rect: pygame.Rect | None = None` to `HUD.__init__` alongside the existing
`recall_rect`.

---

### Task 2 — Pinned-Hero Watch Card

#### Overview

The watch card is a compact panel that floats above the minimap when a hero is pinned. It shows a
zoomed hero-centered map and vital stats. It can be minimized to a 14 px header tab. The left
panel height adjusts dynamically to avoid overlap.

The rendering is split between two files, following the existing right-panel hero-focus pattern:
- **`hud.py`** renders the card chrome (header, stat bars, border). It also records
  `self.watch_card_map_rect` — the exact pygame.Rect where the live map should go.
- **`render_coordinator.py`** fills that rect with the hero-centered map after `hud.render()`
  returns, reusing the existing `_render_hero_minimap()` call.

#### Constants (add near top of `hud.py` alongside `RECALL_BTN_W`)

```python
WATCH_CARD_HEADER_H = 14    # minimized: only this many px show above the minimap panel
WATCH_CARD_MAP_H    = 56    # height of the zoomed hero-map section inside the card
WATCH_CARD_STATS_H  = 68    # hp row + xp row + level row + mana placeholder + padding
WATCH_CARD_FULL_H   = WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H  # = 138
```

#### New state in `HUD.__init__`

```python
self._watch_card_expanded: bool = True       # True = full card; False = 14px header only
self.watch_card_map_rect: "pygame.Rect | None" = None  # filled each frame; read by render_coordinator
self._watch_card_rect: "pygame.Rect | None" = None     # full card rect this frame (for click detection)
```

#### Layout update in `_layout_rects_for_screen()`

The left panel height must shrink when the watch card is expanded and a pinned hero exists. Add
this at the end of the method, just before `return`, replacing the existing hard-coded left rect:

```python
# WK52: dynamic left-panel height — shrinks when watch card is expanded
left_h = max(0, h - top_h - bottom_h)   # default full height
if self._pin_slot.hero_id is not None:
    # card top when minimized:  minimap.y - WATCH_CARD_HEADER_H
    # card top when expanded:   minimap.y - WATCH_CARD_FULL_H
    card_top = minimap.y - (WATCH_CARD_FULL_H if self._watch_card_expanded else WATCH_CARD_HEADER_H)
    left_h = max(0, card_top - top_h)
left = pygame.Rect(0, top_h, left_w, left_h)
```

Note: `minimap.y` is already computed above this point in the method, so no circular dependency.

#### New method `_render_watch_card_chrome(surface, minimap_rect, game_state)`

Add this method to HUD. It draws the card frame, header, and stats. The map section is left empty
(a dark filled rect) — `render_coordinator` will fill it in afterward.

```python
def _render_watch_card_chrome(
    self,
    surface: "pygame.Surface",
    minimap_rect: "pygame.Rect",
    game_state: dict,
) -> None:
    """
    WK52: Render watch card chrome (header + stats) above the minimap.
    Sets self.watch_card_map_rect to the rect where render_coordinator should paint the hero map.
    Clears watch_card_map_rect to None when card should not be shown.
    """
    import pygame
    from game.sim.timebase import now_ms as sim_now_ms

    self.watch_card_map_rect = None
    self._watch_card_rect = None

    pin = self._pin_slot
    if pin.hero_id is None:
        return

    profiles = game_state.get("hero_profiles_by_id") or {}
    prof = profiles.get(pin.hero_id)

    # Card geometry — always same width as the minimap
    cw = minimap_rect.width
    if self._watch_card_expanded:
        ch = WATCH_CARD_FULL_H
    else:
        ch = WATCH_CARD_HEADER_H
    cx = minimap_rect.x
    cy = minimap_rect.y - ch        # card sits directly above minimap panel
    card_rect = pygame.Rect(cx, cy, cw, ch)
    self._watch_card_rect = card_rect

    # --- Card background ---
    pygame.draw.rect(surface, (18, 18, 28), card_rect, border_radius=4)
    pygame.draw.rect(surface, (70, 65, 90), card_rect, width=1, border_radius=4)

    # --- Header strip (always visible, even when minimized) ---
    header_rect = pygame.Rect(cx, cy, cw, WATCH_CARD_HEADER_H)
    pygame.draw.rect(surface, (35, 30, 50), header_rect, border_radius=4)
    pygame.draw.line(surface, (70, 65, 90), (cx, cy + WATCH_CARD_HEADER_H - 1),
                     (cx + cw, cy + WATCH_CARD_HEADER_H - 1))

    # Hero name (truncated) + chevron
    name = pin.pinned_name or "Hero"
    chevron = "▲" if self._watch_card_expanded else "▼"
    font_tiny = pygame.font.SysFont("arial,sans-serif", 10)
    chevron_surf = font_tiny.render(chevron, True, (160, 155, 180))
    name_max_w = cw - chevron_surf.get_width() - 6
    # Truncate name to fit
    name_surf = font_tiny.render(name, True, (200, 195, 220))
    while name_surf.get_width() > name_max_w and len(name) > 2:
        name = name[:-1]
        name_surf = font_tiny.render(name + "…", True, (200, 195, 220))
    surface.blit(name_surf, (cx + 3, cy + (WATCH_CARD_HEADER_H - name_surf.get_height()) // 2))
    surface.blit(chevron_surf, (cx + cw - chevron_surf.get_width() - 2,
                                cy + (WATCH_CARD_HEADER_H - chevron_surf.get_height()) // 2))

    if not self._watch_card_expanded:
        return   # minimized — nothing else to render

    # --- Map section: dark fill; render_coordinator will paint the live map here ---
    map_rect = pygame.Rect(cx + 2, cy + WATCH_CARD_HEADER_H, cw - 4, WATCH_CARD_MAP_H)
    pygame.draw.rect(surface, (8, 10, 16), map_rect)
    self.watch_card_map_rect = map_rect   # signal to render_coordinator

    # --- Stats section ---
    sy = cy + WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + 4
    bar_w = cw - 10
    bar_h = 6
    font_tiny2 = pygame.font.SysFont("arial,sans-serif", 9)

    if prof is not None:
        vitals = getattr(prof, "vitals", None)
        prog   = getattr(prof, "progression", None)
        idn    = getattr(prof, "identity", None)

        # HP row
        hp     = int(getattr(vitals, "hp",     0) if vitals else 0)
        max_hp = int(getattr(vitals, "max_hp", 1) if vitals else 1)
        hp_lbl = font_tiny2.render(f"HP {hp}/{max_hp}", True, (190, 190, 190))
        surface.blit(hp_lbl, (cx + 4, sy))
        sy += hp_lbl.get_height() + 1
        from game.ui.widgets import HPBar
        HPBar.render(surface, pygame.Rect(cx + 4, sy, bar_w, bar_h), hp, max_hp)
        sy += bar_h + 4

        # XP row
        xp       = int(getattr(prog, "xp",          0)   if prog else 0)
        xp_to_lv = int(getattr(prog, "xp_to_level", 100) if prog else 100)
        xp_lbl = font_tiny2.render(f"XP {xp}/{xp_to_lv}", True, (190, 190, 190))
        surface.blit(xp_lbl, (cx + 4, sy))
        sy += xp_lbl.get_height() + 1
        # XP bar — steel blue fill
        xp_ratio = max(0.0, min(1.0, xp / max(1, xp_to_lv)))
        pygame.draw.rect(surface, (40, 40, 55), pygame.Rect(cx + 4, sy, bar_w, bar_h))
        if xp_ratio > 0:
            pygame.draw.rect(surface, (70, 130, 210),
                             pygame.Rect(cx + 4, sy, int(bar_w * xp_ratio), bar_h))
        pygame.draw.rect(surface, (20, 20, 30), pygame.Rect(cx + 4, sy, bar_w, bar_h), 1)
        sy += bar_h + 4

        # Level row
        level = int(getattr(idn, "level", 1) if idn else 1)
        lv_lbl = font_tiny2.render(f"Lv {level}", True, (220, 200, 120))
        surface.blit(lv_lbl, (cx + 4, sy))
        sy += lv_lbl.get_height() + 3

    # Mana placeholder (greyed — stat not yet implemented)
    mana_lbl = font_tiny2.render("Mana: —", True, (80, 78, 95))
    surface.blit(mana_lbl, (cx + 4, sy))
```

**Important notes for Agent 08:**
- The `sy` pointer advances row by row; adjust padding if the card looks cramped on screen.
- `WATCH_CARD_STATS_H = 68` must accommodate HP label + bar + XP label + bar + level label +
  mana label + spacing. If your font returns slightly different heights, tweak `WATCH_CARD_STATS_H`
  and `WATCH_CARD_FULL_H` constants together so the total card height remains consistent.
- Do **not** wire any mana logic. `mana_lbl` is a grey placeholder only.
- The card must render BEFORE `_render_radar_minimap()` in `HUD.render()`, so the minimap panel
  and radar draw on top of the card body when minimized (the bottom-bar panel acts as the visual
  "hiding" surface that the minimized card tucks behind).

#### Render order in `HUD.render()` (expanded section replacing earlier guidance)

The order matters for z-layering:

```python
# 1. Render watch card chrome FIRST (so minimap panel covers its body when minimized)
self._render_watch_card_chrome(surface, minimap, game_state)

# 2. Render the minimap panel background (existing _panel_minimap.render call — unchanged)
self._panel_minimap.render(surface)

# 3. Render the radar dots over the minimap background
self._render_radar_minimap(surface, minimap, game_state)

# 4. Other bottom-bar elements (recall, memorial, command bar...)
```

#### Click handling for expand/minimize toggle

In HUD's click handler (wherever mouse clicks are processed — search for the existing `recall_rect`
check), add before or after the recall check:

```python
# WK52: watch card header click — toggle expand/minimize
if (getattr(self, "_watch_card_rect", None) is not None
        and self._pin_slot.hero_id is not None):
    header_rect = pygame.Rect(
        self._watch_card_rect.x,
        self._watch_card_rect.y,
        self._watch_card_rect.width,
        WATCH_CARD_HEADER_H,
    )
    if header_rect.collidepoint(pos):
        self._watch_card_expanded = not self._watch_card_expanded
        return None   # consumed; no engine action needed
```

#### Recall button → expand watch card

In the existing `recall_pinned_hero` action handler in `engine.py` (around line 1395), after the
existing camera-pan and selection logic, add:

```python
# WK52: clicking Recall also expands the watch card if it is minimized
pin_slot = getattr(getattr(self, "hud", None), "_pin_slot", None)
if pin_slot is not None and pin_slot.hero_id is not None:
    wc = getattr(self.hud, "_watch_card_expanded", True)
    if not wc:
        self.hud._watch_card_expanded = True
```

#### `render_coordinator.py` update — fill the watch card map rect

In `render_coordinator.py`, in the `render()` method, immediately after the `e.hud.render(...)`
call (the existing block that renders `e.hud.render(e.screen, e.get_game_state())`), add:

```python
# WK52: watch card hero map — fill rect that HUD reserved
watch_map_rect = getattr(e.hud, "watch_card_map_rect", None)
if watch_map_rect is not None:
    pin_slot = getattr(e.hud, "_pin_slot", None)
    pinned_id = getattr(pin_slot, "hero_id", None) if pin_slot else None
    if pinned_id:
        pinned_hero = next(
            (h for h in snapshot.heroes
             if str(getattr(h, "hero_id", "")) == pinned_id
             and int(getattr(h, "hp", 0)) > 0),
            None,
        )
        if pinned_hero is not None:
            self._render_hero_minimap(e.screen, watch_map_rect, pinned_hero, snapshot)
```

This reuses `_render_hero_minimap()` exactly as-is — no new renderer code. The existing method
already handles camera centering on the hero, world tile rendering, and unit dots.

#### `tests/test_wk52_watch_card.py`

```python
def test_watch_card_layout_full_height_when_no_pin():
    """Left panel height is unchanged when no hero is pinned."""
    import pygame
    pygame.init()
    # Construct a minimal HUD and verify layout geometry
    # (use HUD.__init__ with mock theme if needed, or check constants directly)
    # Full height: h - top_h - bottom_h
    h, top_h, bottom_h = 1080, 48, 96
    expected_left_h = h - top_h - bottom_h
    assert expected_left_h == 936   # sanity check constant

def test_watch_card_layout_shrinks_when_expanded():
    """Left panel height shrinks by WATCH_CARD_FULL_H - WATCH_CARD_HEADER_H when expanded."""
    from game.ui.hud import WATCH_CARD_FULL_H, WATCH_CARD_HEADER_H
    # minimap.y = bottom.y + margin = (h - bottom_h) + margin = (1080 - 96) + 8 = 992
    minimap_y = 1080 - 96 + 8
    card_top_expanded  = minimap_y - WATCH_CARD_FULL_H
    card_top_minimized = minimap_y - WATCH_CARD_HEADER_H
    # expanded card top must be lower on screen (higher y value = lower)
    assert card_top_expanded < card_top_minimized
    # difference should equal (WATCH_CARD_FULL_H - WATCH_CARD_HEADER_H)
    assert (card_top_minimized - card_top_expanded) == (WATCH_CARD_FULL_H - WATCH_CARD_HEADER_H)

def test_watch_card_full_h_constant_sum():
    """WATCH_CARD_FULL_H must equal the sum of its three section constants."""
    from game.ui.hud import WATCH_CARD_HEADER_H, WATCH_CARD_MAP_H, WATCH_CARD_STATS_H, WATCH_CARD_FULL_H
    assert WATCH_CARD_FULL_H == WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H

def test_watch_card_expand_collapse_state():
    """Toggle function flips _watch_card_expanded correctly."""
    # Test the boolean logic independently of rendering
    expanded = True
    expanded = not expanded
    assert expanded is False
    expanded = not expanded
    assert expanded is True
```

---

### Task 3 — Radar minimap

**Context:** The bottom-bar minimap panel (`self._panel_minimap`) currently draws a styled empty
box with a "Minimap" text label. Your task is to replace the empty interior with a live radar.

The radar shows proportional dots for all fog-revealed world entities. Think of it as a fantasy
commander's battle map viewed from directly above — you can see your forces, the dangers, and your
pinned champion marked in gold.

**Helper function** (add near the top of `HUD`, after imports):

```python
def _world_to_radar(wx: float, wy: float, inner: "pygame.Rect",
                    world_w: int = 4800, world_h: int = 4800) -> tuple[int, int]:
    """Map a world-pixel coordinate to a radar minimap pixel coordinate."""
    mx = inner.x + int(wx / world_w * inner.width)
    my = inner.y + int(wy / world_h * inner.height)
    # clamp to inner rect so dots at world edge don't overflow
    mx = max(inner.left, min(inner.right - 1, mx))
    my = max(inner.top,  min(inner.bottom - 1, my))
    return (mx, my)
```

**New method:** `_render_radar_minimap(self, surface, minimap_rect, game_state)`:

```python
def _render_radar_minimap(
    self,
    surface: "pygame.Surface",
    minimap_rect: "pygame.Rect",
    game_state: dict,
) -> None:
    """WK52: Render radar overview onto the bottom-bar minimap panel interior."""
    import pygame
    from config import MAP_WIDTH, MAP_HEIGHT, TILE_SIZE

    WORLD_W = MAP_WIDTH * TILE_SIZE   # 4800
    WORLD_H = MAP_HEIGHT * TILE_SIZE  # 4800

    inner = minimap_rect.inflate(-6, -6)
    if inner.width <= 0 or inner.height <= 0:
        return

    # --- Fill background (deep navy, different from panel border) ---
    pygame.draw.rect(surface, (12, 14, 22), inner)

    world = game_state.get("world")
    heroes = game_state.get("heroes") or []
    enemies = game_state.get("enemies") or []
    buildings = game_state.get("buildings") or []
    profiles = game_state.get("hero_profiles_by_id") or {}
    pin = self._pin_slot

    def to_radar(wx, wy):
        return _world_to_radar(float(wx), float(wy), inner, WORLD_W, WORLD_H)

    def is_revealed(x, y):
        """Return True if the world tile at (x,y) has been seen by the player."""
        if world is None:
            return True  # fail-open: show everything if world unavailable
        try:
            from game.sim.snapshot import Visibility
            gx, gy = world.world_to_grid(float(x), float(y))
            if 0 <= gx < world.width and 0 <= gy < world.height:
                return world.visibility[gy][gx] != Visibility.HIDDEN
        except Exception:
            pass
        return True

    # --- Buildings: castle (white hollow square) and lairs (crimson dot) ---
    for b in buildings:
        bx, by = getattr(b, "x", None), getattr(b, "y", None)
        # Use grid center if x/y unavailable
        if bx is None:
            bx = (getattr(b, "grid_x", 0) + getattr(b, "size", (1,1))[0] / 2) * TILE_SIZE
        if by is None:
            by = (getattr(b, "grid_y", 0) + getattr(b, "size", (1,1))[1] / 2) * TILE_SIZE
        if not is_revealed(bx, by):
            continue
        btype = str(getattr(b, "building_type", "") or "").lower()
        is_lair = getattr(b, "is_lair", False) or "lair" in btype or "crypt" in btype
        rx, ry = to_radar(bx, by)
        if btype == "castle":
            # White hollow 5×5 square — recognisable command post
            pygame.draw.rect(surface, (220, 220, 220), pygame.Rect(rx - 3, ry - 3, 6, 6), 1)
        elif is_lair:
            # Crimson filled dot — danger marker
            pygame.draw.circle(surface, (180, 30, 30), (rx, ry), 2)
        else:
            # Neutral buildings: dim teal dot
            pygame.draw.circle(surface, (50, 110, 100), (rx, ry), 1)

    # --- Enemies: orange-red dots ---
    for en in enemies:
        ex, ey = getattr(en, "x", 0.0), getattr(en, "y", 0.0)
        if int(getattr(en, "hp", 1)) <= 0:
            continue
        if not is_revealed(ex, ey):
            continue
        rx, ry = to_radar(ex, ey)
        pygame.draw.circle(surface, (210, 80, 40), (rx, ry), 1)

    # --- Heroes: steel-blue dots; pinned hero gets gold glow dot ---
    pinned_pos = None
    for h in heroes:
        hx, hy = getattr(h, "x", 0.0), getattr(h, "y", 0.0)
        if int(getattr(h, "hp", 1)) <= 0:
            continue
        if not is_revealed(hx, hy):
            continue
        rx, ry = to_radar(hx, hy)
        hid = str(getattr(h, "hero_id", "") or "")
        if pin.hero_id and hid == pin.hero_id:
            pinned_pos = (rx, ry)
        else:
            pygame.draw.circle(surface, (80, 140, 210), (rx, ry), 2)

    # Draw pinned hero last (on top) with gold glow
    if pinned_pos is not None:
        px, py = pinned_pos
        # Soft glow ring: two concentric circles with decreasing alpha
        glow_surf = pygame.Surface((14, 14), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (255, 200, 50, 55), (7, 7), 6)
        pygame.draw.circle(glow_surf, (255, 200, 50, 100), (7, 7), 4)
        surface.blit(glow_surf, (px - 7, py - 7))
        pygame.draw.circle(surface, (255, 200, 50), (px, py), 3)   # solid gold core

    # --- Minimap border (re-draw on top so dots don't bleed into border) ---
    pygame.draw.rect(surface, (60, 65, 80), inner, 1)
```

**In `HUD.render()`:** Replace the existing `TextLabel.render(..., "Minimap", ...)` call (currently
the last line of the render method, around line 929) with a call to the new method:

```python
# WK52: live radar replaces the empty "Minimap" label
self._render_radar_minimap(surface, minimap, game_state)
```

---

### Task 3 — Recall button flash

**In `HUD.__init__`**, add:

```python
self._recall_flash_end_ms: int = 0   # WK52: set to now_ms+750 when an alert fires
```

**New method on HUD:**

```python
def trigger_recall_flash(self) -> None:
    """WK52: Flash the Recall button red 3×250 ms = 750 ms. Called by PinAlertWatcher."""
    from game.sim.timebase import now_ms as sim_now_ms
    self._recall_flash_end_ms = int(sim_now_ms()) + 750
```

**In `_render_recall_button()`**, at the very end of the method, after the label blit, add:

```python
# WK52: flash red on alert
from game.sim.timebase import now_ms as sim_now_ms
now = int(sim_now_ms())
if now < self._recall_flash_end_ms:
    elapsed = max(0, now - (self._recall_flash_end_ms - 750))
    pulse = elapsed // 250   # 0, 1, or 2
    if pulse % 2 == 0:       # pulses 0 and 2 are "lit"; pulse 1 is the gap
        flash_surf = pygame.Surface(
            (recall_rect.width, recall_rect.height), pygame.SRCALPHA
        )
        flash_surf.fill((220, 30, 30, 140))
        surface.blit(flash_surf, recall_rect.topleft)
```

---

### Task 4 — `PinAlertWatcher` integration into HUD

**In `HUD.__init__`**, import and instantiate:

```python
from game.ui.pin_alert_watcher import PinAlertWatcher
self._alert_watcher = PinAlertWatcher(self._pin_slot, self)
```

**In `HUD.render()`**, at the top of the method (before layout), add a frame-level update:

```python
# WK52: update cached pinned-hero name + poll low-health
from game.sim.timebase import now_ms as sim_now_ms
_profiles = game_state.get("hero_profiles_by_id") or {}
if self._pin_slot.hero_id:
    _pprof = _profiles.get(self._pin_slot.hero_id)
    if _pprof is not None:
        _idn = getattr(_pprof, "identity", None)
        if _idn is not None:
            self._pin_slot.pinned_name = str(getattr(_idn, "name", "") or "")
self._alert_watcher.check_low_health(_profiles, int(sim_now_ms()))
```

---

### Task 5 — Memorial card

**New file:** `game/ui/memorial_card.py`

```python
"""WK52: Full-screen Memorial Card overlay for fallen pinned heroes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pygame


@dataclass
class MemorialRecord:
    """Frozen snapshot captured the moment the pinned hero is detected as fallen."""
    hero_id: str
    name: str
    hero_class: str
    level: int
    enemies_defeated: int
    bounties_claimed: int
    gold_earned: int


def _generate_epitaph(r: MemorialRecord) -> str:
    """One sentence of flavour text based on the hero's career highlights."""
    if r.enemies_defeated >= 20:
        return (
            f"A fearless warrior who felled {r.enemies_defeated} foes "
            f"before the kingdom claimed their last breath."
        )
    if r.bounties_claimed >= 5:
        return (
            f"Faithful to every call, they honoured {r.bounties_claimed} "
            f"bounties before falling in service."
        )
    if r.gold_earned >= 500:
        return (
            f"They amassed {r.gold_earned} gold for the realm before "
            f"fortune finally ran dry."
        )
    if r.level >= 5:
        return (
            f"They rose to Level {r.level} — further than most dare to dream — "
            f"and paid the ultimate price."
        )
    return "Gone too soon. The kingdom will not forget."


class MemorialCard:
    """
    Full-screen pause overlay. Show with show(record). Dismiss with the Farewell button.

    Usage in HUD.render():
        if self.memorial_card.visible:
            dismiss = self.memorial_card.render(surface)
            if dismiss:
                self.memorial_card.hide()
                engine.paused = False   # caller is responsible for unpausing
    """

    CARD_W = 480
    CARD_H = 380
    OVERLAY_ALPHA = 180

    def __init__(self) -> None:
        self.visible: bool = False
        self._record: Optional[MemorialRecord] = None
        self._dismiss_rect: Optional[pygame.Rect] = None
        self._overlay: Optional[pygame.Surface] = None
        self._overlay_size: tuple[int, int] = (0, 0)

    def show(self, record: MemorialRecord) -> None:
        self._record = record
        self.visible = True

    def hide(self) -> None:
        self.visible = False
        self._record = None
        self._dismiss_rect = None

    def render(self, surface: pygame.Surface) -> bool:
        """
        Draw the overlay. Returns True when the Farewell button was clicked this frame.
        Caller checks pygame.mouse.get_pressed() externally; this method returns True on
        hover+click detection via stored _dismiss_rect (see handle_click).
        """
        if not self.visible or self._record is None:
            return False

        sw, sh = surface.get_size()

        # --- Full-screen dark overlay ---
        if self._overlay is None or self._overlay_size != (sw, sh):
            self._overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            self._overlay.fill((0, 0, 0, self.OVERLAY_ALPHA))
            self._overlay_size = (sw, sh)
        surface.blit(self._overlay, (0, 0))

        # --- Card background ---
        cx = (sw - self.CARD_W) // 2
        cy = (sh - self.CARD_H) // 2
        card_rect = pygame.Rect(cx, cy, self.CARD_W, self.CARD_H)
        pygame.draw.rect(surface, (22, 20, 30), card_rect, border_radius=8)
        pygame.draw.rect(surface, (100, 90, 60), card_rect, width=2, border_radius=8)

        # --- Header band ---
        hdr = pygame.Rect(cx, cy, self.CARD_W, 56)
        pygame.draw.rect(surface, (40, 32, 20), hdr, border_radius=8)
        pygame.draw.line(surface, (100, 90, 60), (cx, cy + 56), (cx + self.CARD_W, cy + 56))

        r = self._record
        font_title = pygame.font.SysFont("georgia,serif", 22, bold=True)
        font_sub   = pygame.font.SysFont("georgia,serif", 15)
        font_body  = pygame.font.SysFont("georgia,serif", 14)
        font_small = pygame.font.SysFont("arial,sans-serif", 12)

        # --- Hero name + class ---
        title_text = f"{r.name}  —  {r.hero_class.title()}"
        title_surf = font_title.render(title_text, True, (240, 210, 120))
        surface.blit(title_surf, (cx + (self.CARD_W - title_surf.get_width()) // 2, cy + 10))

        level_text = f"Level {r.level}"
        level_surf = font_sub.render(level_text, True, (180, 170, 130))
        surface.blit(level_surf, (cx + (self.CARD_W - level_surf.get_width()) // 2, cy + 34))

        # --- Decorative separator ---
        sep_y = cy + 72
        pygame.draw.line(surface, (80, 72, 48), (cx + 40, sep_y), (cx + self.CARD_W - 40, sep_y))
        skull = font_sub.render("☠", True, (120, 110, 80))
        surface.blit(skull, (cx + (self.CARD_W - skull.get_width()) // 2, sep_y - 9))

        # --- Epitaph ---
        epitaph = _generate_epitaph(r)
        # Word-wrap into lines of max ~52 chars
        words = epitaph.split()
        lines, line = [], ""
        for word in words:
            test = (line + " " + word).strip()
            if len(test) > 52:
                lines.append(line)
                line = word
            else:
                line = test
        if line:
            lines.append(line)
        ey = sep_y + 20
        for ln in lines:
            ls = font_body.render(ln, True, (190, 180, 150))
            surface.blit(ls, (cx + (self.CARD_W - ls.get_width()) // 2, ey))
            ey += 20

        # --- Career stats ---
        stats_y = cy + 200
        pygame.draw.line(surface, (60, 56, 40), (cx + 40, stats_y - 10), (cx + self.CARD_W - 40, stats_y - 10))
        stats = [
            (f"Enemies Defeated", str(r.enemies_defeated)),
            (f"Bounties Claimed",  str(r.bounties_claimed)),
            (f"Gold Earned",       f"{r.gold_earned}g"),
        ]
        for i, (label, val) in enumerate(stats):
            lsurf = font_small.render(label, True, (150, 145, 120))
            vsurf = font_small.render(val,   True, (220, 200, 120))
            row_y = stats_y + i * 26
            surface.blit(lsurf, (cx + 60, row_y))
            surface.blit(vsurf, (cx + self.CARD_W - 60 - vsurf.get_width(), row_y))

        # --- Farewell button ---
        btn_w, btn_h = 140, 36
        btn_x = cx + (self.CARD_W - btn_w) // 2
        btn_y = cy + self.CARD_H - btn_h - 24
        self._dismiss_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        mp = pygame.mouse.get_pos()
        btn_hover = self._dismiss_rect.collidepoint(mp)
        btn_col = (90, 70, 40) if btn_hover else (60, 50, 30)
        pygame.draw.rect(surface, btn_col, self._dismiss_rect, border_radius=5)
        pygame.draw.rect(surface, (120, 100, 60), self._dismiss_rect, width=1, border_radius=5)
        btn_lbl = font_sub.render("Farewell", True, (230, 215, 160))
        surface.blit(btn_lbl, (btn_x + (btn_w - btn_lbl.get_width()) // 2,
                                btn_y + (btn_h - btn_lbl.get_height()) // 2))
        return False   # click handled externally via handle_click()

    def handle_click(self, pos: tuple[int, int]) -> bool:
        """Call from HUD's click handler. Returns True if Farewell was pressed."""
        if self.visible and self._dismiss_rect is not None:
            if self._dismiss_rect.collidepoint(pos):
                return True
        return False
```

---

### Task 6 — Wire `MemorialCard` into HUD

**In `HUD.__init__`:**

```python
from game.ui.memorial_card import MemorialCard, MemorialRecord
self.memorial_card = MemorialCard()
self._pending_memorial: "MemorialRecord | None" = None
self._memorial_shown_for: str = ""   # hero_id we already captured; prevents double-fire
```

**In `HUD.render()`**, after the liveness update block (after `pin.update_liveness(...)` call),
add the memorial capture logic:

```python
# WK52: capture memorial record the moment the pinned hero first falls
if (pin.is_fallen()
        and pin.hero_id is not None
        and pin.hero_id != self._memorial_shown_for):
    _pprof = _profiles.get(pin.hero_id)
    if _pprof is not None:
        from game.ui.memorial_card import MemorialRecord
        _career = getattr(_pprof, "career", None)
        _idn    = getattr(_pprof, "identity", None)
        self._pending_memorial = MemorialRecord(
            hero_id=str(pin.hero_id),
            name=str(getattr(_idn, "name", pin.pinned_name) if _idn else pin.pinned_name),
            hero_class=str(getattr(_idn, "hero_class", "hero") if _idn else "hero"),
            level=int(getattr(_idn, "level", 1) if _idn else 1),
            enemies_defeated=int(getattr(_career, "enemies_defeated", 0) if _career else 0),
            bounties_claimed=int(getattr(_career, "bounties_claimed", 0) if _career else 0),
            gold_earned=int(getattr(_career, "gold_earned", 0) if _career else 0),
        )
        self._memorial_shown_for = str(pin.hero_id)
```

**In `HUD.render()`**, after `self._render_recall_button(surface, recall, game_state)`, add:

```python
# WK52: memorial button
top_, bottom_, left_, right_, minimap_, cmd_, speed_, recall_, memorial_ = \
    self._compute_layout(surface)
self._render_memorial_button(surface, memorial_, game_state)

# WK52: memorial card overlay (rendered last, on top of everything)
if self.memorial_card.visible:
    self.memorial_card.render(surface)
```

**New method `_render_memorial_button`:**

```python
def _render_memorial_button(
    self, surface: "pygame.Surface", memorial_rect: "pygame.Rect", game_state: dict
) -> None:
    """WK52: 'Memorial' button — only visible when a pending memorial record exists."""
    self.memorial_rect = None
    if self._pending_memorial is None:
        return
    if self.memorial_card.visible:
        return   # card is open — hide button while overlay is showing
    self.memorial_rect = pygame.Rect(memorial_rect)
    NineSlice.render(surface, memorial_rect, self._button_tex_normal,
                     border=self._button_slice_border)
    lbl = self.theme.font_small.render("⚰ Memorial", True, (200, 180, 130))
    surface.blit(lbl, (
        memorial_rect.x + (memorial_rect.width  - lbl.get_width())  // 2,
        memorial_rect.y + (memorial_rect.height - lbl.get_height()) // 2,
    ))
```

**In HUD's click handler** (wherever `recall_rect` click is handled — search for
`"recall_pinned_hero"`), add below it:

```python
# WK52: memorial button
if (getattr(self, "memorial_rect", None) is not None
        and self.memorial_rect.collidepoint(pos)):
    self.memorial_card.show(self._pending_memorial)
    return {"action": "open_memorial"}   # or however actions are returned in this code path

# WK52: memorial card dismiss
if self.memorial_card.handle_click(pos):
    self.memorial_card.hide()
    self._pending_memorial = None
    return {"action": "close_memorial_unpause"}
```

**In `engine.py`'s `handle_hud_action()`** (around line 1371, near the existing pin/recall
actions), add:

```python
if action == "close_memorial_unpause":
    self.paused = False
    return
if action == "open_memorial":
    self.paused = True
    return
```

---

### Task 8 — Screenshot scenario

**File:** `tools/screenshot_scenarios.py`

Add a new scenario function and register it in `get_scenario()`.

The scenario should:
1. Run the engine for ~300 ticks with seed 42 to populate heroes
2. Pin the first living hero via `engine.hud._pin_slot.pin(hero.hero_id, now_ms)` and set
   `engine.hud._pin_slot.pinned_name = hero.name`
3. Ensure `engine.hud._watch_card_expanded = True`
4. Capture shot 1: `wk52_watch_card_expanded.png` — bottom-left showing watch card above
   minimap with hero map, HP bar, XP bar, level, and mana placeholder
5. Set `engine.hud._watch_card_expanded = False`
6. Capture shot 2: `wk52_watch_card_minimized.png` — only the 14 px header tab is visible
7. Set `engine.hud._watch_card_expanded = True` again
8. Capture shot 3: `wk52_pin_radar_minimap.png` — confirm radar dots visible below/alongside
   (note: when watch card is expanded the radar is mostly covered — that is correct behaviour)
9. Manually set `engine.hud._pending_memorial = MemorialRecord(...)` with dummy data
10. Show memorial card: `engine.hud.memorial_card.show(engine.hud._pending_memorial)`
11. Capture shot 4: `wk52_memorial_card.png`

Register as `"wk52_pin_alerts"` in `get_scenario()`.

**Run command for QA:**

```powershell
python tools/capture_screenshots.py --scenario wk52_pin_alerts --seed 42 --out docs/screenshots/wk52_pin_alerts --size 1920x1080 --ticks 300
```

---

### Task 8 — Tests

### Task 9 — Tests

**`tests/test_wk52_minimap_radar.py`:**

```python
import pygame
from game.ui.hud import _world_to_radar  # or import as a module-level function

def test_world_origin_maps_to_radar_origin():
    inner = pygame.Rect(5, 5, 80, 80)
    assert _world_to_radar(0.0, 0.0, inner, 4800, 4800) == (5, 5)

def test_world_centre_maps_to_radar_centre():
    inner = pygame.Rect(0, 0, 100, 100)
    rx, ry = _world_to_radar(2400.0, 2400.0, inner, 4800, 4800)
    assert rx == 50 and ry == 50

def test_world_max_clamps_to_radar_edge():
    inner = pygame.Rect(0, 0, 64, 64)
    rx, ry = _world_to_radar(4800.0, 4800.0, inner, 4800, 4800)
    assert rx <= inner.right - 1
    assert ry <= inner.bottom - 1
```

**`tests/test_wk52_pin_alerts.py`:**

```python
def test_watcher_fires_level_up_toast(monkeypatch):
    """PinAlertWatcher calls hud.add_message when HERO_LEVEL_UP matches pin."""
    from game.ui.pin_slot import PinSlot
    from game.ui.pin_alert_watcher import PinAlertWatcher
    messages = []
    flashes = []

    class FakeHUD:
        def add_message(self, text, color): messages.append(text)
        def trigger_recall_flash(self): flashes.append(True)

    pin = PinSlot()
    pin.pin("hero_abc", 0)
    pin.pinned_name = "Aldric"
    watcher = PinAlertWatcher(pin, FakeHUD())
    watcher._on_level_up({"hero_id": "hero_abc", "hero_name": "Aldric", "new_level": 3})
    assert any("Level 3" in m for m in messages)
    assert len(flashes) == 1

def test_watcher_ignores_other_heroes(monkeypatch):
    from game.ui.pin_slot import PinSlot
    from game.ui.pin_alert_watcher import PinAlertWatcher
    messages = []

    class FakeHUD:
        def add_message(self, t, c): messages.append(t)
        def trigger_recall_flash(self): pass

    pin = PinSlot()
    pin.pin("hero_abc", 0)
    watcher = PinAlertWatcher(pin, FakeHUD())
    watcher._on_level_up({"hero_id": "hero_xyz", "hero_name": "Other", "new_level": 5})
    assert len(messages) == 0

def test_low_health_cooldown_prevents_spam():
    from game.ui.pin_slot import PinSlot
    from game.ui.pin_alert_watcher import PinAlertWatcher, LOW_HEALTH_COOLDOWN_MS
    messages = []

    class FakeHUD:
        def add_message(self, t, c): messages.append(t)
        def trigger_recall_flash(self): pass

    class FakeVitals:
        health_percent = 0.10

    class FakeProf:
        vitals = FakeVitals()

    pin = PinSlot()
    pin.pin("h1", 0)
    watcher = PinAlertWatcher(pin, FakeHUD())
    profiles = {"h1": FakeProf()}
    watcher.check_low_health(profiles, now_ms=1000)       # fires
    watcher.check_low_health(profiles, now_ms=5000)       # too soon — should not fire
    watcher.check_low_health(profiles, now_ms=1000 + LOW_HEALTH_COOLDOWN_MS + 1)  # fires again
    assert len(messages) == 2
```

**`tests/test_wk52_memorial_card.py`:**

```python
def test_memorial_record_captures_fields():
    from game.ui.memorial_card import MemorialRecord, _generate_epitaph
    r = MemorialRecord("h1", "Aria", "warrior", 7, 25, 3, 800)
    assert r.level == 7
    epitaph = _generate_epitaph(r)
    assert isinstance(epitaph, str) and len(epitaph) > 10

def test_epitaph_high_kills():
    from game.ui.memorial_card import MemorialRecord, _generate_epitaph
    r = MemorialRecord("h2", "Bran", "ranger", 4, 22, 0, 100)
    assert "22" in _generate_epitaph(r)

def test_memorial_card_show_hide():
    from game.ui.memorial_card import MemorialCard, MemorialRecord
    card = MemorialCard()
    r = MemorialRecord("h3", "Cal", "mage", 3, 5, 2, 200)
    assert not card.visible
    card.show(r)
    assert card.visible
    card.hide()
    assert not card.visible
    assert card._record is None
```

---

### Verification (Agent 08)

```powershell
python -m pytest tests/test_wk52_pin_alerts.py tests/test_wk52_minimap_radar.py tests/test_wk52_memorial_card.py tests/test_wk52_watch_card.py -v
python tools/qa_smoke.py --quick
python tools/capture_screenshots.py --scenario wk52_pin_alerts --seed 42 --out docs/screenshots/wk52_pin_alerts --size 1920x1080 --ticks 300
```

**Inspect all four screenshots manually:**

1. `wk52_watch_card_expanded.png` — watch card must be visible above the minimap. It must show:
   a compact card with a header (hero name + ▲ chevron), a dark map section (hero-centered world
   tiles visible), HP bar with value, XP bar with value, level label, and greyed "Mana: —" row.
   No text clipping. Left panel (if open) must not overlap the watch card.
2. `wk52_watch_card_minimized.png` — only a 14 px header strip showing above the minimap panel
   top edge. Hero name visible. ▼ chevron visible. The card body must be hidden behind/under
   the minimap panel. Radar dots visible in the minimap area.
3. `wk52_pin_radar_minimap.png` — radar dots present (castle square, hero dots, enemy dots).
   Gold hero dot visible. When watch card is expanded this screenshot will mostly show the watch
   card on top — that is correct and expected.
4. `wk52_memorial_card.png` — full-screen overlay centered, hero name, career stats table, epitaph,
   Farewell button. No text clipping.

If any screenshot looks wrong: fix → re-run → re-inspect before marking done.

Update your agent log with screenshot filenames + one-line assessment of each.

---

## WAVE 3 — QA & Performance (Parallel)

### Agent 11 — QA (MEDIUM intelligence)

**Run the full suite:**

```powershell
python -m pytest tests/ -v --tb=short 2>&1 | tee docs/wk52_qa_run.txt
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
python tools/determinism_guard.py
```

**Determinism check — this is mandatory for WK52:**

The determinism guard must pass with no new failures. Confirm that `PinSlot`,
`PinAlertWatcher`, and `MemorialCard` do not appear in any sim-state hash path.

**Screenshot review:**

Open the two screenshots Agent 08 produced:
- `docs/screenshots/wk52_pin_alerts/wk52_pin_radar_minimap.png`
- `docs/screenshots/wk52_pin_alerts/wk52_memorial_card.png`

Write a one-line verdict on each in your agent log: "PASS — dots visible, gold glow present,
no overlap" or "FAIL — [specific issue]".

**Write your human-gate playtest checklist** in your agent log. The checklist Jaimie will use:

```
1. python main.py --provider mock   (or python main.py --no-llm)
2. Wait for 2-3 heroes to spawn.
3. Click a hero to select them. Confirm Pin button (📌) appears on the HeroPanel header.
4. Click Pin. Confirm Recall button appears in the bottom HUD with the hero's name.

5. WATCH CARD (expanded): confirm a card appears ABOVE the minimap in the bottom-left corner.
   It must show: hero name + ▲ in the header, a small live map centred on the hero, HP bar
   with numbers, XP bar with numbers, a "Lv N" label, and a greyed "Mana: —" row.
6. WATCH CARD (minimize): click the card header (or the ▲ chevron). The card must collapse
   to just a 14 px header strip above the minimap. The radar dots in the minimap become
   visible again. Left panel (if open) should expand to fill the extra height.
7. WATCH CARD (expand via Recall): while the card is minimized, click the Recall button.
   Confirm: (a) the camera pans to the hero, (b) the watch card expands back to full size.
8. WATCH CARD (expand via header): while minimized, click the ▼ header. Card expands.

9. LEFT PANEL HEIGHT: pin a hero, open their hero panel (left panel), then toggle the watch
   card between expanded and minimized. The bottom of the left panel must visibly shift —
   it should stop short of the watch card when expanded, and extend lower when minimized.
   The two panels must never overlap.

10. RADAR: confirm the minimap shows colored dots when the watch card is minimized.
    Gold dot = pinned hero. White hollow square = castle. Crimson dots = lairs/enemies.

11. ALERT: let the hero take damage below 25% HP.
    Confirm: (a) toast "⚠ [Name] is low health!" appears,
             (b) Recall button flashes red three times.
12. LEVEL-UP: confirm "⭐ [Name] reached Level X!" toast + Recall flash when hero levels.
13. INN: confirm "🍺 [Name] checked into the inn." toast when hero enters an inn.
14. BOUNTY: place a bounty near the pinned hero (press B). Confirm "✓ [Name] claimed a
    bounty!" toast fires when they claim it.

15. MEMORIAL: let the pinned hero die. Confirm:
    (a) "⚰ Memorial" button appears to the right of the (now grayed-out) Recall button.
    (b) Clicking Memorial pauses the game and shows the full-screen card.
    (c) Clicking Farewell closes the card and unpauses.

16. python tools/qa_smoke.py --quick   → must exit 0.
```

### Agent 10 — Performance (LOW intelligence)

Run the performance benchmark:

```powershell
python tools/perf_benchmark.py --ticks 1800 --seed 99
```

Compare FPS to the WK51 baseline. The radar minimap runs every render frame. Flag if frame time
regressed by more than 2 ms at default 1920×1080. The dots are `pygame.draw.circle` calls over
a small surface — they should be negligible. Log your finding.

---

## Human Gate

Jaimie: run Agent 11's exact 11-step checklist above using:

```powershell
cd "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom"
python main.py --provider mock
```

Report any failures back to Agent 01. Do NOT push until this gate passes.

---

## PM Closeout (Agent 01)

After Jaimie confirms the human gate passes:

1. Read agent logs for 03, 08, 11, 10.
2. Update PM hub with sprint status, evidence, and next-actions.
3. Confirm Agent 10's perf verdict is acceptable.
4. Ask Jaimie if they want a version bump (likely v1.5.5).
5. On confirmation: coordinate Agent 13 (or handle as PM-allowed ops) for CHANGELOG + README.
6. Ask Jaimie explicitly before committing/pushing:
   ```powershell
   git add -A
   git commit -m "WK52: Radar minimap, pin alerts, memorial card"
   git push
   ```

---

## Orchestrator Command (Local-to-Cloud)

### Dry-run first:

```powershell
$env:CURSOR_API_KEY = "crsr_..."
cd "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom"
npm run studio --prefix tools/ai_studio_orchestrator -- validate --sprint wk52_attachment_phase3_radar_alerts_memorial --round wk52_r1_kickoff
npm run studio --prefix tools/ai_studio_orchestrator -- run --sprint wk52_attachment_phase3_radar_alerts_memorial --round wk52_r1_kickoff --dry-run
```

### Live run:

```powershell
npm run studio --prefix tools/ai_studio_orchestrator -- run `
  --sprint wk52_attachment_phase3_radar_alerts_memorial `
  --round wk52_r1_kickoff `
  --cloud-repo-url https://github.com/jaimiemontague/Kingdom.git `
  --auto-push `
  --mode auto_until_human_gate
```

---

## Send List (for manual activation if not using orchestrator)

| Agent | Role | Wave | Intelligence | Notes |
|-------|------|------|-------------|-------|
| 02 | GameDirector | 0 (parallel) | LOW | Acceptance criteria review only — no code |
| 04 | Determinism | 0 (parallel) | LOW | Architecture review only — no code |
| 03 | TechnicalDirector | 1 | HIGH | Event layer, hero_id payloads, PinAlertWatcher skeleton |
| 08 | UX_UI_Director | 2 | HIGH | All rendering: radar, flash, memorial card |
| 11 | QA | 3 (parallel) | MEDIUM | Full test suite + determinism guard + screenshots |
| 10 | Performance | 3 (parallel) | LOW | Perf benchmark consult only |

Do NOT send to: 01, 05, 06, 07, 09, 12, 13, 14, 15.

---

## Definition of Done

- [ ] `python tools/qa_smoke.py --quick` exits 0
- [ ] `python tools/validate_assets.py --report` exits 0
- [ ] `python tools/determinism_guard.py` exits 0 with no new failures
- [ ] All WK52 pytest tests pass (`test_wk52_events`, `test_wk52_pin_alerts`, `test_wk52_minimap_radar`, `test_wk52_memorial_card`, `test_wk52_watch_card`)
- [ ] Screenshot `wk52_watch_card_expanded.png` — card visible above minimap with map, HP, XP, level, mana placeholder; left panel not overlapping
- [ ] Screenshot `wk52_watch_card_minimized.png` — only 14 px header tab visible; radar dots visible
- [ ] Screenshot `wk52_pin_radar_minimap.png` — radar dots present (gold hero, castle square, lairs)
- [ ] Screenshot `wk52_memorial_card.png` — full card centered, name, stats, epitaph, Farewell button
- [ ] Jaimie's 16-step playtest passes end-to-end
- [ ] Agent logs for 03, 08, 11, 10 all valid JSON at `sprints["wk52_attachment_phase3_radar_alerts_memorial"].rounds["wk52_r1_kickoff"]`
