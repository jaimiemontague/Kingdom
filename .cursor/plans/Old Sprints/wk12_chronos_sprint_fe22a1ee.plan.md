---
name: wk12 Chronos Sprint
overview: "Sprint 1 of the Immersive Kingdom Initiative: implement 5-tier player-facing speed controls and universal building occupancy tracking. Version target v1.4.0."
todos:
  - id: 1a-time-multiplier
    content: "Agent 03: Add time_multiplier to timebase.py, split engine dt into sim_dt/camera_dt, add speed tier constants to config.py"
    status: pending
  - id: 1b-speed-ui
    content: "Agent 08: Create SpeedControlBar widget, integrate into HUD bottom-right, add [/]/backtick hotkeys"
    status: pending
  - id: 1c-occupancy
    content: "Agent 05: Add occupants list to Building base class, migrate Inn, update all panel renderers, emit EventBus events"
    status: pending
  - id: 1d-qa-determinism
    content: "Agent 11 + 04: Add speed_scaling QA scenario, occupancy assertions, determinism review, perf baseline check"
    status: pending
  - id: pm-hub-update
    content: "Agent 01: Update PM hub log with wk12-chronos sprint, agent prompts, and bug tickets before activation"
    status: pending
isProject: false
---

# wk12: Sprint 1 "Chronos" -- Time Controls + Occupancy Foundation

**Parent roadmap:** [immersive_kingdom_initiative](immersive_kingdom_initiative_1292aeb9.plan.md)
**Version target:** v1.4.0
**Goal:** Players can control simulation speed (5 tiers) and every building properly tracks its occupants.

---

## 1A. Time Multiplier System (Agent 03 -- TechDirector)

### Current State

- [game/sim/timebase.py](game/sim/timebase.py) (40 lines): exposes `set_sim_now_ms()` and `now_ms()`. No speed multiplier concept.
- [game/engine.py](game/engine.py) main loop (lines 1237-1243): computes `dt` from either fixed tick (`1.0 / SIM_TICK_HZ`) or wall-clock (`tick_ms / 1000.0`). No multiplier applied.
- `_prepare_sim_and_camera()` (lines 536-549): advances `_sim_now_ms` by `dt * 1000`, sets sim time, and gates camera updates behind `self.paused`.
- Pause exists as `self.paused` boolean (line 97). When paused, `_prepare_sim_and_camera` returns `False` and `update()` early-returns.

### Changes

**File: `game/sim/timebase.py`** -- Add time multiplier state

- Add module-level `_TIME_MULTIPLIER: float = 1.0`
- Add `set_time_multiplier(m: float)` with clamping to `[0.0, 4.0]`
- Add `get_time_multiplier() -> float`
- Keep `now_ms()` and `set_sim_now_ms()` unchanged -- the multiplier is applied at the engine level, not inside the timebase

**File: `config.py`** -- Add speed tier constants

- Add a `SpeedTier` frozen dataclass or named constants:
  - `SPEED_PAUSE = 0.0`
  - `SPEED_SUPER_SLOW = 0.1`
  - `SPEED_SLOW = 0.25`
  - `SPEED_NORMAL = 0.5`
  - `SPEED_FAST = 1.0`
- `DEFAULT_SPEED_TIER = SPEED_NORMAL` (game starts at half the current pace)
- Add `SPEED_TIER_NAMES` dict mapping multiplier to display name

**File: `game/engine.py`** -- Apply multiplier in main loop

- In `run()` (line 1243): after computing `dt`, apply `dt *= get_time_multiplier()` before calling `self.update(dt)`
- Critical: camera must use wall-clock `dt` for responsiveness. Split into `sim_dt` (multiplied) and `camera_dt` (raw). Pass `sim_dt` to `update()`, use `camera_dt` for `update_camera()`.
- In `_prepare_sim_and_camera()` (line 540): `_sim_now_ms` advancement already uses the `dt` passed in, so it will naturally scale with the multiplier
- When multiplier is `0.0` (pause): `_prepare_sim_and_camera` should return `False` (same as current pause behavior). Remove or merge the separate `self.paused` flag -- speed-tier pause replaces it.
- Initialize engine with `set_time_multiplier(DEFAULT_SPEED_TIER)` in `__init__`

### Key constraint

Camera panning, UI interaction, and menu input must remain at full wall-clock speed regardless of sim speed. Only simulation logic (hero movement, combat, economy, spawning, AI) scales with the multiplier.

### Acceptance criteria

- At `SPEED_FAST` (1.0x), game behaves identically to current v1.3.4
- At `SPEED_PAUSE` (0.0x), world freezes but camera pans, UI clicks, and menus all work
- At `SPEED_SUPER_SLOW` (0.1x), heroes visibly move in slow motion, combat cooldowns stretch proportionally
- No teleporting or snapping at any speed tier
- `--no-llm` and `--provider mock` modes work at all speed tiers

---

## 1B. Speed Control UI (Agent 08 -- UX/UI)

### Current State

- Bottom bar: `y = screen_height - 96`, height 96px ([game/ui/hud.py](game/ui/hud.py) line 167)
- Minimap: bottom-left, 80x80px
- Command bar: after minimap, variable width, holds Build/Hire/Bounty buttons ([game/ui/command_bar.py](game/ui/command_bar.py))
- Bottom-right corner: **free space** between command bar right edge and right panel (or screen edge)
- Widget primitives available: `Button`, `Panel`, `TextLabel`, `NineSlice` ([game/ui/widgets.py](game/ui/widgets.py))
- Theme: [game/ui/theme.py](game/ui/theme.py) provides consistent colors, fonts, spacing

### Changes

**New file: `game/ui/speed_control.py`** -- SpeedControlBar widget

- 5 buttons in a horizontal row: `||`, `>`, `>>`, `>>>`, `>>>>`
- Active tier highlighted (accent color from theme)
- Text label below or beside showing tier name ("Paused", "Super Slow", "Slow", "Normal", "Fast")
- Widget size: ~200px wide x 50px tall (fits in bottom-right gap)
- Clicking a button calls `set_time_multiplier()` from timebase

**File: `game/ui/hud.py`** -- Integrate SpeedControlBar

- In `_compute_layout()` (line 147): compute a `speed_rect` in the bottom-right corner. Position: `x = bottom.right - 210`, `y = bottom.y + margin`, width 200, height ~50
- Shrink command bar width to leave room: `cmd_w = max(0, speed_rect.x - cmd_x - gutter)`
- In `render()` (after line 444, command bar): render `SpeedControlBar`
- Forward click events from HUD to speed bar

**File: `game/input_handler.py`** -- Hotkeys for speed tiers

- Add after zoom controls (~line 222 in `handle_keydown`):
  - `K_BACKQUOTE` (tilde/backtick): toggle pause (set 0.0 or restore previous)
  - `K_1` through `K_5`: **conflict** -- K_1/K_2 are currently building placement hotkeys
  - Use `Numpad 1-5` instead, or bracket keys `[` / `]` to step speed down/up
  - Recommended: `[` = slower, `]` = faster, backtick = pause toggle. Avoids conflicts with existing 1-9 building hotkeys.

### Acceptance criteria

- 5 speed buttons visible in bottom-right, correct labels
- Clicking a button changes sim speed immediately
- Active tier visually distinct (highlighted)
- `[` and `]` hotkeys cycle through speed tiers
- Backtick pauses/unpauses
- Speed bar renders correctly at 1920x1080 and 1280x720 window sizes

---

## 1C. Universal Building Occupancy (Agent 05 -- Gameplay)

### Current State

- [game/entities/buildings/base.py](game/entities/buildings/base.py) `Building` class (lines 55-195): no occupancy tracking
- [game/entities/buildings/economic.py](game/entities/buildings/economic.py) `Inn` class (lines 135-159): only building with `heroes_resting: list[Hero]`, `on_hero_enter()`, `on_hero_exit()`
- [game/entities/hero.py](game/entities/hero.py) lines 284-424: `start_resting_at_building()`, `enter_building_briefly()`, `pop_out_of_building()` all check `hasattr(building, "on_hero_enter/exit")` before calling
- 20+ building subclasses across guilds, temples, economic, defensive, special, castle -- none have occupancy besides Inn
- Only Inn panel renderer ([game/ui/building_renderers/economic_panel.py](game/ui/building_renderers/economic_panel.py) lines 184-229) displays occupants

### Changes

**File: `game/entities/buildings/base.py`** -- Add occupancy to base class

- Add to `Building.__init__()` (after line 73):
  - `self.occupants: list = []` (list of Hero refs)
  - `self.max_occupants: int = 8` (default, overridden per type in config)
- Add methods to `Building`:
  - `on_hero_enter(self, hero) -> None`: append if not present and under max
  - `on_hero_exit(self, hero) -> None`: remove if present (safe)
  - `get_occupant_count(self) -> int`
  - `is_full(self) -> bool`

**File: `game/entities/buildings/economic.py`** -- Migrate Inn

- `Inn.on_hero_enter()`: call `super().on_hero_enter(hero)` instead of manual list management
- `Inn.on_hero_exit()`: call `super().on_hero_exit(hero)` instead of manual removal
- Replace `self.heroes_resting` references with `self.occupants` (or alias `heroes_resting` as a property returning `self.occupants`)
- Keep `Inn`-specific fields (`rest_recovery_rate`, `drink_income_gold`) unchanged

**File: `config.py`** -- Add max_occupants per building type

- Add `BUILDING_MAX_OCCUPANTS` dict: Inn=6, Warrior/Ranger/Rogue/WizardGuild=4, Marketplace=3, Blacksmith=2, Temple*=4, etc.
- Castle, defensive buildings, and special buildings: 0 (not enterable in Sprint 2)

**File: `game/entities/hero.py*`* -- No changes needed

- Hero methods already use `hasattr(building, "on_hero_enter")` -- since base class now has it, all buildings will be called. This is backwards-compatible.

**File: `game/ui/building_renderers/`** -- Show occupants on all building panels

- Extract the Inn's occupant display logic (economic_panel.py lines 184-210) into a shared helper
- Call the helper from every building renderer that has `max_occupants > 0`
- Show: "Heroes inside: N/max" + hero name list

**EventBus integration:**

- Emit `"hero_entered_building"` and `"hero_exited_building"` events from `Building.on_hero_enter/exit`
- Events carry `{hero, building}` payload
- Sprint 2 will consume these for interior view updates

### Acceptance criteria

- All building types track occupants via base class
- Inn renderer still works identically (no visual regression)
- Guild, Marketplace, Blacksmith panels now show "Heroes inside: N"
- Hero enter/exit lifecycle works at all 5 speed tiers
- `qa_smoke --quick` passes (no regressions)

---

## 1D. QA + Determinism (Agent 11 + Agent 04)

### Agent 04 (Determinism) -- Consult

- Review: `time_multiplier` is applied in engine.py, not inside timebase.py. Confirm no wall-clock leaks into sim boundary.
- Review: `set_time_multiplier()` stores state in timebase module. Confirm this is safe for future lockstep (multiplier would be a local client setting, not synced).
- Scan: `python tools/determinism_guard.py` must still PASS after all Sprint 1 changes.

### Agent 11 (QA) -- Primary

**New headless scenario: `speed_scaling`**

- Add to [tools/qa_smoke.py](tools/qa_smoke.py):
  - Profile that runs `observe_sync` at each speed tier (0.1, 0.25, 0.5, 1.0)
  - At each tier: verify enemies spawn, heroes move, bounties claimable, no assertion failures
  - Skip `0.0` (pause) -- headless can't advance when paused
- Add to [tools/observe_sync.py](tools/observe_sync.py):
  - `--speed-multiplier N` CLI flag that sets `set_time_multiplier(N)` before the run

**Occupancy assertions:**

- Add assertion: after hero enters building, `building.get_occupant_count() >= 1`
- Add assertion: after hero exits, hero not in `building.occupants`

**Regression:**

- All existing profiles (`base`, `intent_bounty`, `hero_stuck_repro`, `no-enemies`, `mock-LLM`) must still PASS
- Manual smoke: 5 minutes at each of the 3 middle speed tiers (super slow, slow, normal)

### Agent 10 (Performance) -- Consult

- Run `python tools/perf_benchmark.py` at `SPEED_FAST` (1.0x) -- must match current baseline
- Spot-check: at `SPEED_SUPER_SLOW` (0.1x), CPU usage should drop proportionally (fewer effective ticks/sec)
- No new per-frame allocations from speed control UI

---

## Agent Assignments Summary

- **Agent 03** (Primary): 1A -- time multiplier in timebase, engine loop split (sim_dt vs camera_dt), speed tier constants
- **Agent 08** (Primary): 1B -- SpeedControlBar widget, HUD integration, hotkeys
- **Agent 05** (Primary): 1C -- base class occupancy, Inn migration, config max_occupants, panel renderers, EventBus events
- **Agent 04** (Consult): 1D -- determinism review of time multiplier
- **Agent 11** (Primary): 1D -- speed_scaling QA scenario, occupancy assertions
- **Agent 10** (Consult): 1D -- perf baseline check at all tiers

## Integration Order

1. **Agent 03 first** -- time multiplier must land before Agent 08 can wire UI to it
2. **Agent 05 in parallel with 03** -- occupancy is independent of time system
3. **Agent 08 after 03** -- speed UI depends on time multiplier API
4. **Agent 11 after 03 + 05** -- QA scenarios need both features landed
5. **Agent 04 + 10 consult** -- review after all code lands, before release

## Universal Activation Prompt (for Jaimie to send)

```
You are being activated for the wk12 "Chronos" sprint (Sprint 1 of the Immersive Kingdom Initiative).

Read your assignment in the PM hub:
.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json
-> sprints["wk12-chronos"].rounds["wk12_r1"]

Your specific prompt is under pm_agent_prompts[YOUR_AGENT_NUMBER].
Feature specs are in the sprint plan: .cursor/plans/wk12_chronos_sprint_[hash].plan.md

After completing your work:
1. Update your agent log
2. Run: python tools/qa_smoke.py --quick (must PASS)
3. Report status back

Send to: Agents 03, 05, 08, 11 (primary). Agents 04, 10 (consult only).
```

