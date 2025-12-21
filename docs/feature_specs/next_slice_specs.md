# Feature Specs — Next Slice (Proposed)

These specs are intentionally small and acceptance-criteria driven, so they can be implemented in PR-sized increments.

## FS-1: “Why did they do that?” — Hero Intent + Last Decision Inspect

### Problem
Players can’t consistently tell **why** heroes choose actions, which makes autonomy feel random instead of satisfying.

### Proposal
Expose a lightweight “intent” and “last decision” view for heroes:
- Current high-level intent (examples): *shopping*, *pursuing bounty*, *returning to safety*, *engaging enemy*, *idle/patrolling*.
- Last “important decision” snapshot: action chosen + short reason + timestamp/age.

### Acceptance criteria
- Selecting a hero shows **current intent** in the UI panel (single line).
- If LLM/basic AI makes an “important decision”, store a **last decision** record (action + reason + age).
- Works in both **LLM** and **no-LLM/mock** modes.
- If no decision exists yet, UI shows a neutral placeholder (no errors).

---

## FS-2: Bounty Clarity — Make Incentives Legible

### Problem
Bounties are the core player lever, but players need better feedback on **who is responding** and **how attractive** a bounty is.

### Proposal
Improve bounty feedback:
- Show a “responders” count (heroes that have chosen/pinned that bounty).
- Show a simple “attractiveness” hint (e.g., low/med/high) based on hero risk/strength vs threat.

### Acceptance criteria
- A bounty has a displayed responder count (0..N).
- Attractiveness is computed deterministically from available state (no extra LLM call).
- If no heroes exist, the system behaves gracefully (0 responders, no crash).

---

## FS-3: Early Session Pacing Guardrail — Reduce Dead Air

### Problem
If the first minutes have too little pressure or too little economy movement, the game feels idle rather than “alive.”

### Proposal
Add a pacing guardrail that ensures early activity without spiking difficulty:
- Ensure at least one meaningful event/decision occurs within the first few minutes (e.g., early bounty target, small raid, or clear prompt to build/hire).

### Acceptance criteria
- New game: within 3 minutes, there is at least one clear player-facing prompt/decision point (visible in HUD/log).
- Does not require external APIs; works in mock/no-LLM mode.
- Does not create unavoidable failure spikes (still recoverable with reasonable play).



