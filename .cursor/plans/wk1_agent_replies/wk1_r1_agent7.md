### Agent 7 — ContentScenarioDirector (wk1_r1)

#### Status
Completed implementation of the wk1 plan’s **minimal early-game pacing nudge** using existing systems (HUD + bounties + lairs) and sim-time (determinism-friendly).

#### What I implemented (P0 option, low risk)

Goal from sprint plan: **within 3 minutes, create a clear prompt/decision** without building a full scenario framework.

Implemented in `game/engine.py`:

- **Sim-time driven** early pacing hook (uses `dt` accumulation / `_sim_now_ms` pathway; no wall-clock time for sim logic).
- **HUD tip** at ~35 seconds (sim time) *only if* the player has placed **no bounties**:
  - “Tip: Press B to place a bounty and guide heroes.”
  - “Try targeting a lair for big stash payouts.”
- **Optional starter bounty** at ~90 seconds (sim time) *only if*:
  - the player still has **no bounties**, and
  - there is a living lair, and
  - the player can afford it via `EconomySystem.add_bounty()`
  - then the engine places an **`attack_lair`** bounty targeting the **nearest lair** to the castle.

Important safety properties:

- **No free money**: the starter bounty uses `economy.add_bounty(reward)` (normal bounty cost path). If the player can’t afford it, it shows a single non-spammy tip and stops retrying.
- **Doesn’t override player agency**: if the player places any bounty manually before the thresholds, the nudge won’t place anything.
- **Determinism-friendly**: timing is based on sim-time accumulation; no new `pygame.time.get_ticks()` dependency for the nudge.

#### Intended player impact (“Majesty feel”)

- Early session has an explicit, learnable lever (“bounties guide heroes”).
- The starter bounty provides a concrete objective (clear a lair) and teaches the stash payout loop quickly.

#### Acceptance criteria (aligned to sprint plan FS-3)

- Within the first **3 minutes**, if the player does nothing, they see at least one clear guidance prompt.
- If the player does not place bounties, by ~90 seconds a starter lair bounty appears (assuming affordable and lairs exist).
- No crashes/softlocks in `--no-llm` and `--provider mock`.
- Bounty placement does not create gold from nothing (player gold decreases when placed).

#### How to test (manual, 2–3 minutes)

1) Run:
   - `python main.py --no-llm` (or `python main.py --provider mock`)
2) Do **not** place any bounties.
3) Observe:
   - Around **35s**: HUD tip appears.
   - Around **90s**: “Starter bounty placed…” message appears and a bounty is placed at the nearest lair.
   - Player gold decreases by the bounty amount when the starter bounty is created.
4) Control case: place a bounty manually before 90s; confirm the auto-starter bounty never triggers.

#### Risks / edge cases

- If a run has **no lairs** (shouldn’t happen with current defaults), starter bounty won’t place (it will bail safely).
- The “nearest lair” selection uses lair center coords; if lair positions change, it still behaves sensibly.
- If early gold becomes very low in future tuning, the starter bounty may not place; tip still fires and stops retrying.

#### Dependencies / coordination notes

- Uses `LAIR_BOUNTY_COST` from `config.py` (fallback to 75 if missing/0), so balancing/tuning can happen centrally.
- Pairs well with upcoming FS-2 work (bounty responders/attractiveness) and UX copy work (Agent 8).

#### Recommended next actions

- Add a simple toggle (config or CLI) to disable/force the nudge for QA and tuning if needed.
- If FS-2 lands (responders/attractiveness), consider adding a short follow-up HUD hint that references responders count (optional).


