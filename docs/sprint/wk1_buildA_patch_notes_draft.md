## Build A (Midweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.1 (Build A / Midweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **Hero clarity**: Hero panel now exposes **Current intent** + **Last decision** (action + short reason + age).
- **Bounty clarity**: Bounties show **Responders: N** and a deterministic **Attractiveness** tier (Low/Med/High).
- **Debuggability**: Added safe instrumentation/logging so you can answer “why did that hero do that?” without guesswork.

### Gameplay & Balance
- Bounties use reward tiers (default/Shift/Ctrl) so you can signal “how urgent” a task is.

### AI Behavior
- Introduced/standardized intent labels (e.g., `idle`, `pursuing_bounty`, `shopping`, `returning_to_safety`, `engaging_enemy`, `defending_building`, `attacking_lair`).
- Last-decision record now stores a short reason string and a sim-time “age” value (works in **LLM**, **mock**, and **--no-llm**).

### UI/UX
- Hero panel: shows **Intent** and **Last decision** with a safe placeholder when none exists yet.
- Bounty overlay/UI: shows **Responders** and **Attractiveness** in a compact, non-spammy format.
- Help/controls: clarified **how to place bounties** (B places at mouse cursor; Shift/Ctrl for higher rewards).

### Visuals
- (Optional) Small iconography/shape language for bounty attractiveness tiers (placeholder-friendly).

### Performance & Stability
- No new crashes/softlocks in `--no-llm` and `--provider mock`.
- Guardrail: new “age/time since decision” uses **sim-time/ticks**, not wall-clock.

### Known Issues
- Duplicate hero names may appear in logs (non-fatal; behavior is still keyed by stable IDs).
- Some heroes may show “No decision yet” briefly after spawn (expected).

### How to test (quick)
- `python tools/qa_smoke.py --quick`
- Manual 10-minute smoke: boot → place a building → observe peasants build → hire a hero → place a bounty → confirm responders + intent/decision fields update → pause/resume → quit.


