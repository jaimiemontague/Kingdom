## WK3 — Build B (Endweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.X (Build B / Endweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **Pixel art pass**: heroes, enemies, and buildings now render with pixel art sprites (fallbacks remain for missing frames).
- **Consistent visual identity**: cohesive style across units and UI (CC0/open-license allowed with clean attribution).
- **Validation & stability**: asset presence checks and regressions to keep `qa_smoke --quick` green.

### Visuals
- Sprite directories populated under `assets/sprites/` for current heroes/enemies/buildings (per loader conventions).

### Performance & Stability
- `python tools/qa_smoke.py --quick` must pass.
- Manual 10-minute smoke (mock/no-LLM): verify sprites load, no missing-texture spam, no crashes.

### Credits / Attribution
- See `assets/ATTRIBUTION.md` (added/updated as packs are ingested).

### Known Issues (fill from QA)
- (Placeholder) ________________________________________
- (Placeholder) ________________________________________


