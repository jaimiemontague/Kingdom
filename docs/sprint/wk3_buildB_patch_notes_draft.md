## WK3 — Build B (Endweek) — Patch Notes Draft

### Title
**Kingdom Sim — Prototype v1.2.4 (Build B / Endweek)**

### No API keys required
- Run with mock AI: `python main.py` (default) or `python main.py --provider mock`
- Run without any LLM integration: `python main.py --no-llm`

### Highlights
- **1080p borderless + safer UX**: improved quit/close reliability and polish around UI panels while keeping the sim stable.
- **Pixel art overrides**: heroes, enemies, and buildings now render with PNG sprite overrides (placeholders improved; fallbacks remain safe).
- **Release hygiene**: strict asset + attribution validation is now part of the Build B gate (alongside `qa_smoke --quick`).
- **Visual Snapshot System**: deterministic screenshot capture + local comparison gallery against reference art for faster look/feel iteration.

### Visuals
- Sprite override directories populated under `assets/sprites/` for current heroes/enemies/buildings (per existing loader conventions).

### Performance & Stability
- `python tools/qa_smoke.py --quick` must pass.
- `python tools/validate_assets.py --strict --check-attribution` must pass.
- Manual 10-minute smoke (mock/no-LLM): verify sprites load, no missing-texture spam, no crashes.

### Credits / Attribution
- See `assets/ATTRIBUTION.md` and `assets/third_party/` for full license/provenance.
- Credits (one bullet per pack):
  - Kenney (curated subset) by Kenney — License: CC0 1.0 Universal — Source: `https://kenney.nl/assets` — Used for: heroes/enemies/buildings
  - Kingdom Sim — CC0 Placeholder Sprite Set by Kingdom Sim (Jaimie Montague + AI-assisted tooling) — License: CC0-1.0 — Source: generated in-repo — Used for: heroes/enemies/buildings

### Known Issues (fill from QA)
- None known blocking release.
- Visuals are still **prototype-grade**: sprites are CC0 placeholders meant to be replaced/animated in the next sprint.

---

## Visual Snapshot System (baseline “after” set)

Regenerate rolling “after” snapshots + gallery (overwrite `wk3_baseline_v2_next`, **do not overwrite** `wk3_baseline_v2`):

```bash
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk3_baseline_v2_next/base_overview_seed3 --size 1920x1080 --ticks 0
python tools/capture_screenshots.py --scenario building_catalog --seed 3 --out docs/screenshots/wk3_baseline_v2_next/building_catalog_seed3 --size 1920x1080 --ticks 0
python tools/capture_screenshots.py --scenario enemy_catalog --seed 3 --out docs/screenshots/wk3_baseline_v2_next/enemy_catalog_seed3 --size 1920x1080 --ticks 0
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk3_baseline_v2_next/ui_panels_seed3 --size 1920x1080 --ticks 0
python tools/build_gallery.py --shots docs/screenshots/wk3_baseline_v2_next --refs .cursor/plans/art_examples --out docs/art/compare_gallery.html
```



