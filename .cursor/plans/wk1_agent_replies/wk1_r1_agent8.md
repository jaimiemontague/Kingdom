### Status
**Assignment:** WK1 R1 — UX/UI clarity (Agent 8: UX_UI_Director). Deliver UI copy + layout rules for **hero intent/last decision** and **bounty responders/attractiveness**, kept readable and non-spammy, and safe in mock/no-LLM.

### Deliverables
- **Hero inspect UI (FS-1)**:
  - Show **Current intent** (single, stable label).
  - Show **Last decision** (action + short reason + age), with safe placeholder if none yet.
  - Must work in **LLM + mock + no-LLM**.
- **Bounty legibility UI (FS-2)**:
  - Each bounty displays **Responders: N**.
  - Each bounty displays **Attractiveness: Low/Med/High** (or compact icon/text).
  - Deterministic computation; no extra LLM calls.
- **Low-risk HUD clarity**:
  - Reduce always-on “wall of controls” via **toggleable help**.
  - Show a small **mode banner** when placing a building.

### Proposed UI copy (player-facing)
- **Hero panel**
  - `Intent: <Idle | Moving | Engaging enemy | Pursuing bounty | Shopping | Returning to safety | Resting>`
  - `Last decision: <action> → <target> (<age>s ago) — <short reason>`
  - Placeholder: `Last decision: (none yet)`
  - Notes:
    - Keep reason to ~1 short clause, truncate with ellipsis if needed.
    - “Age” should be based on **sim-time** (tick/sim clock), not wall-clock.

- **Bounty marker**
  - `R:<N>  <Low|Med|High>`
  - Optional expanded tooltip later: `Responders: N` / `Attractiveness: <tier>`

- **Placement mode banner**
  - `Placing: <Building Name> (LMB: place, ESC: cancel)`

- **Help toggle hint**
  - When hidden: `F3: Help`
  - Header: `Controls (F3 to hide)`

### UI layout rules (readability)
- **Prioritize “now” info**:
  - Always-visible: gold / counts / wave + small mode banner when applicable.
  - On-demand: the full control list (help overlay).
- **Avoid spam**:
  - Toast messages should be short and non-repeating.
  - Prefer persistent labels for state (intent/banner) over repeated popups.
- **Truncation/overflow**:
  - Never overflow panels; truncate long reasoning lines.
  - Keep bounty labels compact; avoid multi-line text in world space.
- **Color semantics**
  - Attractiveness tiers: Low=gray, Med=gold, High=green.
  - Keep text readable over fog-of-war; use high contrast.

### Acceptance criteria (for UX slice)
- Selecting a hero shows **Intent** and **Last decision** (or safe placeholder).
- Last decision shows **age** derived from sim-time (or blank if unavailable).
- Each bounty shows **Responders** and **Attractiveness tier**.
- No crashes if hero has no decision yet / no heroes exist / no bounties exist.
- UI additions do not allocate heavily per frame (keep text generation lightweight).

### Risks
- **Mismatch between UI “intent” and future intent taxonomy**: mitigate by keeping labels stable and mapping from real fields when they exist.
- **Perf regression** from per-frame string work: mitigate by keeping computations lightweight and capped; avoid per-frame allocations where possible.
- **Visual clutter** if too much overlay text: keep bounty markers compact and help toggleable.

### Dependencies / coordination notes
- **Agent 3 (Architecture)**: eventual stable contract for `hero.intent` and `hero.last_decision` will replace UI-side inference.
- **Agent 6 (AIBehaviorDirector_LLM)**: align naming for intent labels and ensure “reason” strings stay short.
- **Agent 9 (Art/VFX)**: optional iconography for attractiveness tiers; must remain readable over fog-of-war.

### Questions back to PM (max 3)
- Should help overlay default to **ON** for Build A to support onboarding, or **OFF** to reduce clutter?
- Should attractiveness reflect **global** risk/reward or be **class-aware** (align with AI scoring) in future?
- Any preferred copy tone: more “Majesty-like” flavor or strictly utilitarian labels for now?

### Recommended next actions
- Hook future `hero.intent`/`hero.last_decision` contract into UI when available (remove inference).
- Add hover tooltips for bounty markers (optional) and/or a tiny legend for Low/Med/High.
- Add a “bounty placement mode” (toggle B, click to place, ESC cancel) if misfires become common.


