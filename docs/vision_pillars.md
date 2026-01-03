# Kingdom Sim — Vision & Design Pillars (Game Director / Product Owner)

This document is the **north star** for decisions and cuts. If a feature doesn’t strengthen these pillars, it’s a “later” (or a “no”).

## Pillars

### 1) Indirect Control First
- The player **influences** the world (buildings, rewards, incentives), but does not micro heroes.
- The player’s skill expression is **strategic placement + economy + prioritization**, not click-speed.

### 2) Readable Incentives & Causality
- A player should be able to answer: **“Why did that hero do that?”**
- Incentives must be visible, consistent, and explainable (UI + debug aids).

### 3) Emergent Hero Stories
- Heroes should feel like individuals: distinct preferences, risk tolerance, spending habits, and grudges.
- The goal is **memorable outcomes** (rescues, last-stand wins, greedy shopping trips) without scripting.

### 4) Moment-to-Moment Clarity (Over Complexity)
- Combat and world state must be legible at a glance: who is fighting, who is fleeing, where the danger is.
- Complexity is allowed only if it remains **readable** and **teachable**.

### 5) Consistent “Majesty Feel”, Modern Expectations
- Majesty feel: autonomy, bounties, economy loop, escalating pressure, and “watching the kingdom work.”
- Modern expectations: stability, responsiveness, clear UI feedback, and debuggability.

### 6) Determinism-Friendly & Debuggable (Future MP Guardrail)
- Even in single-player, prefer patterns that can be deterministic later (seeded randomness, tick-based sim).
- Every “smart” decision should be inspectable (inputs, chosen action, reason).

## Non-goals (for now)
- Direct unit control / RTS micro.
- Deep narrative campaign.
- Large content breadth without a satisfying core loop.
- Multiplayer implementation (we only keep the simulation **compatible** later).

## “Does this feature ship?” rubric
Ship if it:
- Improves **player agency through incentives**, or
- Improves **clarity/teachability**, or
- Improves **hero story variety**, and
- Doesn’t compromise stability/perf.





