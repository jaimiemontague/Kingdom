## WK4 — Build A (Midweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.5 (WK4 Build A / Midweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **New enemy: Skeleton Archer**: a ranged-only, kiting enemy (`skeleton_archer`) with instant-hit attacks (no projectile system).
- **Easy to test**: the first enemy wave now guarantees a Skeleton Archer spawn near the castle so you can validate behavior quickly.
- **Pipelines stay green**: strict asset validator + Visual Snapshot System enemy catalog include the new enemy type.

### Gates (required)
- `python tools/qa_smoke.py --quick`
- `python tools/validate_assets.py --strict --check-attribution`

### Known Issues (fill from QA)
- (Placeholder) ________________________________________
- (Placeholder) ________________________________________






