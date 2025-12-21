## Scenario System (Content-First) — Draft

This doc defines a **content-driven scenario layer** for *Kingdom Sim* that adds replayability via:

- **Goals** (victory conditions) and **fail states**
- **Pacing knobs** that map to existing systems (wave spawner, lairs, bounties, economy)
- Optional **event schedule** hooks (festivals/raids/disasters) with deterministic-friendly timing

This is written to be implementable as a **small increment**: content specs now, minimal engine wiring later.

---

## Current integration points (already in code)

- **Lose condition**: `castle_destroyed` combat event pauses the game and prints “GAME OVER - Castle Destroyed!”.
- **Wave pressure**: `EnemySpawner` controls edge-wave goblin spawning with tunables: `spawn_interval`, `initial_no_spawn_ms`, `enemies_per_wave`, `enabled`.
- **Lair pressure + reward**: `LairSystem` spawns initial lairs; `MonsterLair` spawns enemies and grows a **stash** that pays out on clear (`lair_cleared` event).
- **Player incentives**: `BountySystem` already supports typed bounties:
  - `explore`
  - `attack_lair` (targeted)
  - `defend_building` (targeted)
  - `hunt_enemy_type` (string target)

---

## Scenario data shape (proposal)

Keep scenarios as **content-only** data first (JSON), even if implemented in Python later.

```json
{
  "id": "frontier_hold",
  "name": "Frontier Hold",
  "description": "Survive escalating pressure while building a stable economy.",
  "seed": 3,

  "start": {
    "starting_gold": 10000,
    "initial_lairs": 2,
    "spawner": {
      "enabled": true,
      "initial_no_spawn_ms": 5000,
      "extra_spawn_delay_ms": 12000,
      "enemies_per_wave_start": 1
    },
    "starter_bounties": [
      { "type": "attack_lair", "reward": 75, "target": "nearest_lair" }
    ]
  },

  "victory": [
    { "type": "survive_time", "seconds": 600 }
  ],
  "defeat": [
    { "type": "castle_destroyed" }
  ],

  "events": [
    { "at_seconds": 120, "type": "festival", "params": { "tax_bonus_pct": 10, "duration_seconds": 45 } }
  ]
}
```

### Determinism notes (future MP-friendly)

- Prefer scheduling by **tick** (or accumulated sim time) rather than wall-clock.
- Ensure scenario seed is applied early (`random.seed(seed)`), before world/terrain/lairs spawn.
- Avoid querying real-time clocks (e.g., `pygame.time.get_ticks()`) for scenario logic; instead, use sim time accumulation.

---

## Victory/Defeat conditions (minimum viable set)

These are content concepts; implementation can be incremental.

### Defeat

- `castle_destroyed`: already exists via combat events.

### Victory (suggested P0)

- `survive_time(seconds)`: win after N seconds without castle destruction.
- `clear_lairs(count|all)`: win after clearing all initial lairs (or N).
- `reach_gold(amount, mode="kingdom"|"taxed_total")`: win after reaching a gold target.
  - **Note**: today gold is tracked as economy + stored in buildings; pick one canonical metric when implementing.

### Optional (P1)

- `build(building_type, count)` (e.g., “build 1 Trading Post”)
- `hire_heroes(count)`

---

## Three starter scenarios (EA-ready)

These are designed to be fun **with current systems** (spawner + lairs + bounties) and minimal new UI (HUD messages).

### 1) Frontier Hold (Survival)

- **ID**: `frontier_hold`
- **Core loop**: stabilize economy → scale defense → survive.
- **Victory**: survive 10 minutes (\(600\) seconds).
- **Defeat**: castle destroyed.
- **Tuning knobs**:
  - Keep `enemies_per_wave` low early; ramp modestly (already implemented in `EnemySpawner`).
  - Keep `MAX_ALIVE_ENEMIES` safety cap as-is for stability.
- **Suggested starter bounties**:
  - `attack_lair` on nearest lair (teaches player to use bounties to focus heroes).
  - Optional `defend_building` auto-bounty when castle is damaged (future).
- **Acceptance criteria**:
  - A typical run ends in 8–14 minutes (win or loss).
  - Player can clearly understand what “winning” means (HUD text: “Objective: Survive 10:00”).

### 2) Lairbreaker (Clear Objectives)

- **ID**: `lairbreaker`
- **Core loop**: push out, clear lairs for payouts, snowball.
- **Victory**: clear all initial lairs (default 2).
- **Defeat**: castle destroyed.
- **Tuning knobs**:
  - Slightly slower edge-wave spawning to allow targeted play (increase `extra_spawn_delay_ms`).
  - Ensure lair stash payout feels meaningful (tuning lives in `LAIR_STASH_GROWTH_PER_SPAWN`).
- **Suggested starter bounties**:
  - Place one `attack_lair` bounty per lair (reward ~= `LAIR_BOUNTY_COST`).
- **Acceptance criteria**:
  - Clearing a lair feels like a “chapter beat” (HUD message already exists on `lair_cleared`).
  - Victory occurs reliably when both lairs are destroyed, even if wave spawns are ongoing.

### 3) Prosperous Kingdom (Economy Target)

- **ID**: `prosperous_kingdom`
- **Core loop**: scale hero income → tax flow → reach target before being overwhelmed.
- **Victory**: reach kingdom gold target (recommend: **taxed gold collected**, or a stable “economy gold” metric).
- **Defeat**: castle destroyed.
- **Tuning knobs**:
  - Encourage marketplaces/inn/fairgrounds play (optional: reduce early wave intensity slightly).
  - Use neutral buildings (houses/farms/food stands) as passive economy pressure relief (already auto-spawn).
- **Suggested target**:
  - \( \text{goal} = 20{,}000 \) gold (subject to tuning).
- **Acceptance criteria**:
  - Player “feels” that investing in economy matters, not just combat.

---

## Minimal implementation recommendation (optional, P0)

If/when you want this wired in, keep it tiny:

- Add `game/scenarios.py` containing a small `Scenario` dataclass + definitions.
- Add a `ScenarioManager` that:
  - Applies start knobs to existing systems at game start (`EnemySpawner`, lair count, starting gold, optional starter bounties)
  - Tracks sim-time
  - Evaluates victory conditions and emits a HUD message + pauses the game on win

No need for a full “event bus” yet—use existing combat events + a small “scenario update” call from `GameEngine.update()`.

---

## Implemented now (wk1 broad sweep)

As part of the “wk1 broad sweep” sprint plan, a **minimal early pacing nudge** is implemented in `game/engine.py`:

- At ~35s (sim-time) if there are no bounties, the HUD shows a short tip about placing bounties.
- At ~90s (sim-time) if there are still no bounties and the player can afford it, the engine auto-places one **starter `attack_lair` bounty** on the nearest lair and charges the normal bounty cost from the economy.



