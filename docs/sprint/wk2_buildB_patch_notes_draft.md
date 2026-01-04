## WK2 — Build B (Endweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.4 (Build B / Endweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **Real hero animations**: Warrior/Ranger/Rogue/Wizard now have full sprite sets (idle/walk/attack/hurt/inside).
- **Readable intent via animation**: hero states visually match behavior (less jittering between states).
- **Stability + perf polish**: final pass to keep frame time stable with new animations and debug tooling.

### Visuals
- New hero sprite frame sets under `assets/sprites/heroes/<class>/...` (idle/walk/attack/hurt/inside).
- Timing polish to match combat cadence and hit reactions.

### UI/UX
- (If shipped) “inside” indicator visuals align with inside state (no combat while inside).

### Performance & Stability
- Verify sprite loading has no missing-folder fallbacks for the 4 core classes.
- Confirm no new per-frame allocations/regressions tied to animation state switching.

### How to test (quick)
- `python tools/qa_smoke.py --quick`
- Manual 10-minute smoke (mock/no-LLM): verify all 4 classes display correct animations in each state (idle/walk/attack/hurt/inside).

### Known Issues (fill from QA)
- (Placeholder) ________________________________________
- (Placeholder) ________________________________________







