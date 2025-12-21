## WK2 — Build A (Midweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.3 (Build A / Midweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **Less hero jank**: reduced rapid oscillation (“spaz loops”) via tighter target/goal commitment.
- **No combat while inside buildings**: heroes cannot execute attacks/damage while inside (visual + logic consistency).
- **Stuck recovery**: heroes detect common “frozen” states and attempt deterministic recovery (repath / reset goal).

### Gameplay & Balance
- (If shipped) Micro-tuning to ensure anti-jank guardrails don’t reduce bounty responsiveness.

### AI Behavior
- Anti-oscillation guardrails (e.g., minimum commitment window / hysteresis).
- Inside-building combat gating enforced (AI transitions + attack execution).
- Stuck detection and deterministic recovery strategies (sim-time based).

### UI/UX (Debug)
- Debug visibility for stuck events (debug-only): indicator/log to show stuck reason + recovery attempts.

### Performance & Stability
- `python tools/qa_smoke.py --quick` must pass.
- Manual 10-minute smoke in `--no-llm` and `--provider mock`:
  - heroes do not attack from inside buildings
  - heroes recover from common stuck states (no long freezes)
  - reduced oscillation is noticeable in normal play

### Known Issues (fill from QA)
- (Placeholder) ________________________________________
- (Placeholder) ________________________________________


