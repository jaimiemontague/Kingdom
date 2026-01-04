## Early Access Content Backlog (Draft)

This backlog is scoped for **replayability + goals** with minimal engine disruption. Priorities assume “small PR-sized” increments.

Legend:
- **P0**: ships with first scenario layer
- **P1**: next content patch
- **P2**: later / needs more systems

---

## P0 — Scenarios + a tiny victory layer

- **Scenario: Frontier Hold**
  - Survive timer goal + HUD objective text
  - Uses existing wave spawner + existing lose condition

- **Scenario: Lairbreaker**
  - Clear-all-lairs victory (uses existing `lair_cleared` events)

- **Scenario: Prosperous Kingdom**
  - Gold target victory (choose one canonical gold metric)

- **Starter event table (content-only)**
  - Harvest Festival, Market Boom, Bandit Raid, Drought (as design-only until wired)

---

## P1 — Replayability multipliers (low-risk)

- **Scenario modifiers (“mutators”)**
  - Examples: “Double Lairs”, “No Edge Waves (lairs only)”, “High Taxes / Low Starting Gold”
  - Implement as scenario presets, not a new system

- **New objective types**
  - Hire N heroes
  - Build 1 Trading Post (or 1 Guardhouse)

- **Map seeds surfaced**
  - CLI arg or UI debug option to set seed for repeatable runs

---

## P2 — Richer world content (needs more plumbing)

- **New neutral sites**
  - “Ruins” (one-time loot), “Shrine” (temporary buff), “Caravan” (moving reward)

- **Wave variety**
  - Additional enemy types in edge waves (wolves/skeletons) with cadence rules

- **Story beats**
  - Simple narrative “chapters” with 3–5 objective steps (requires objective UI panel)

---

## Dependencies / coordination notes

- **Gold metric**: agree with GameplaySystemsDesigner on whether victory uses:
  - economy/castle gold, or
  - total taxed gold collected, or
  - total gold earned by heroes
- **Seed + determinism**: coordinate with NetworkingDeterminism_Lead for RNG seeding/time sources.







