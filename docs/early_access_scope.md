# Kingdom Sim — Early Access Scope (Proposed)

This is a **scope gate**: it clarifies what we ship first to deliver a satisfying “Majesty-like” session, and what we explicitly defer.

## Experience targets (what “good” feels like)
- **First 5 minutes**: player can place core buildings, hire heroes, and understand what bounties do.
- **First 15 minutes**: economy loop is visible (gold in/out, taxes), heroes buy/upgrade, pressure escalates.
- **30–45 minutes**: player can stabilize (or collapse) through incentive choices, not micro.
- **Outcome clarity**: player can explain losses (bad incentives, insufficient defenses, overreaching).

## Must-have (EA “core loop is real”)
- **Indirect control loop**: build → hire → place bounties → heroes act → combat → rewards → economy/taxes.
- **Readability**: clear feedback for danger, hero intent, and why behavior happens.
- **Stable sim**: no common softlocks; performance is acceptable at expected entity counts.
- **Mock/no-LLM playability**: the game is still fun/functional without external APIs.

## Should-have (high leverage, but cuttable)
- **More hero variety**: at least 2–3 distinct archetypes that play differently (risk, range, spend).
- **Lairs/POIs**: a non-wave pressure source that creates decisions and map interest.
- **Meaningful midgame decisions**: defenses vs economy vs hero power.
- **More incentive tools**: bounty types or priority tuning that increases player expression.

## Explicit cuts / not now (protect focus)
- Campaign, story, narrative progression.
- Multiplayer implementation (only “ready later” design guardrails).
- Huge building roster breadth without clear roles/tuning.
- Deep crafting trees / sprawling tech trees.

## Scope guardrails (how we avoid feature creep)
- Add content only if it introduces a **new decision** or **new counterplay**, not just “more stuff.”
- Any new “smart” behavior must come with: **reason visibility** (debug/tooltip) + **failure-safe** fallback.


