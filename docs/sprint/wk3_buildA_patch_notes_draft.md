## WK3 — Build A (Midweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.X (Build A / Midweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **Borderless 1080p by default**: launches in **1920×1080 borderless fullscreen** (falls back to your display resolution if smaller).
- **Majesty-inspired UI skeleton**: themed layout regions (top bar, bottom command bar, right info panel, minimap).
- **UI readability pass**: typography/spacing improvements and tooltips/hotkey hints where relevant.

### UI/UX
- New themed panels + consistent typography.
- Improved layout for 1080p (no overlap at default resolution).

### Performance & Stability
- `python tools/qa_smoke.py --quick` must pass.
- Manual 10-minute smoke in `python main.py --no-llm` and `python main.py --provider mock`.

### Known Issues (fill from QA)
- (Placeholder) ________________________________________
- (Placeholder) ________________________________________


