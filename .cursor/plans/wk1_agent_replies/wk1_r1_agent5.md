## Agent 5 (GameplaySystemsDesigner) — wk1_r1 Response

### Summary
Delivered a **small, low-risk gameplay tuning pass** focused on **bounties + lairs + early pacing**, aligned to the wk1 plan:
- Defined **bounty reward bands** (low/med/high) and implemented tiered placement controls.
- Tuned **lair bounty cost vs expected lair stash payout** so clearing a lair feels like a “chapter beat”.
- Tuned early pressure with **slightly slower lair spawn intervals** (still active).
- Fixed a critical logic issue: **`attack_lair` bounties previously paid out by proximity**, so heroes did not reliably clear lairs. Now lair bounties pay out on **`lair_cleared`** instead.

### What I changed (implementation)

#### Bounty reward bands (player-paid)
- Added constants in `config.py`:
  - `BOUNTY_REWARD_LOW = 25`
  - `BOUNTY_REWARD_MED = 60`
  - `BOUNTY_REWARD_HIGH = 150`
- Updated bounty placement in `game/engine.py`:
  - `B` places **Low**
  - `Shift+B` places **Medium**
  - `Ctrl+B` places **High**

#### Lair bounty completion correctness (critical)
Goal: `attack_lair` bounties should represent “clear the lair” (completion), not “walk near it”.
- `game/systems/bounty.py`: only `explore` bounties are proximity-claimed.
- `ai/basic_ai.py`: when a hero reaches an `attack_lair` bounty goal, they transition into attacking the lair (approach an adjacent tile; then CombatSystem handles lair damage).
- `game/engine.py`: on combat event `lair_cleared`, if there is an active `attack_lair` bounty targeting that lair, the engine pays the bounty to the clearing hero.

#### Lair stash / pressure tuning
- `config.py`:
  - `LAIR_BOUNTY_COST`: **75 → 90**
  - `LAIR_STASH_GROWTH_PER_SPAWN`: **6 → 8**
- `game/entities/lair.py`:
  - Slightly increased base `stash_gold` per lair type
  - Slightly slowed `spawn_interval_sec` per lair type (keeps pressure “alive” but reduces runaway cap pressure)

#### Economy baseline (so bounty pricing matters)
- `config.py`: `STARTING_GOLD` **10000 → 1500**
  - Still enough to build early, but forces meaningful tradeoffs (buildings vs bounties vs defenses).

#### Small compatibility helper
- `game/entities/building.py`: added `x`/`y` properties mapping to building center (`center_x`/`center_y`) for safer “target distance” handling when something treats a building like an entity.

### Tuning guidance (player-facing)
Stored in: `docs/sprint/wk1_gameplay_tuning.md`
- Early bounty tiers:
  - Low: **25**
  - Med: **60**
  - High: **150**
- Lair bounty default: **90**
- Lair stash: increased slightly + grows a bit faster per spawn to keep the clear reward satisfying.

### Acceptance criteria (for my slice)
- Placing a bounty is a meaningful decision (gold cost has weight).
- Starter `attack_lair` bounty (engine early nudge) causes heroes to **attack and clear** a lair, then receive bounty payout on clear.
- Clearing a lair feels like a “chapter beat”: you see the clear message + meaningful gold gain (stash + bounty).

### Risks / tradeoffs
- `STARTING_GOLD=1500` may be too tight for some EA onboarding expectations; if so, we can bump to ~2000–3000 while keeping bounty tiering intact.
- Other typed bounties (`defend_building`, `hunt_enemy_type`) are not yet completion-hooked; they should be implemented similarly (completion-based, not proximity-based).

### Dependencies
- None required to ship these changes (self-contained).
- Nice-to-have from Agent 8: UI hint for bounty tier modifiers (`B` / `Shift+B` / `Ctrl+B`).
- Nice-to-have from Agents 3/8: responders + attractiveness UI/logic (separate workstream).

### How to test
- Automated: `python tools/qa_smoke.py --quick`
- Manual (10 min):
  - Start game, do nothing.
  - At ~35s: see bounty tip.
  - At ~90s: starter lair bounty appears (if you haven’t placed any bounties).
  - Hire a hero; observe they move to lair and attack it; on destruction, you see lair clear message and the bounty payout is applied.







