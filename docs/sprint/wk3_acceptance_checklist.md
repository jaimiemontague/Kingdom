# WK3 Acceptance Checklist (UI + 1080p Borderless + Pixel Art)

## Build A (Midweek) — Manual Smoke (Windows, ~10 minutes)

### 1) Launch mode + resolution (borderless fullscreen)
- Run (no LLM):
  - `python main.py --no-llm`
- **Expected**
  - Window opens **borderless fullscreen**.
  - If display is **>= 1920×1080**: target is **1920×1080**.
  - If display is **smaller**: uses the display’s current resolution (still borderless).
  - Smaller-than-1080 fallback **must not crash** and must not produce catastrophic clip/scale errors (e.g., invalid scale targets, negative rects, out-of-bounds blits).
  - No black screen / no “window off-screen” issues.

### 2) UI readability at runtime resolution
- **Expected**
  - Top bar readable (gold / key status) without overlapping playfield excessively.
  - Bottom command bar visible and clickable; tooltips/hotkeys (if present) do not spam.
  - Right info panel readable when selecting a hero/building.
  - Minimap region exists (if in Build A scope) and does not obscure core play area.
  - No obvious layout break when resolution is not exactly 1920×1080 (layout uses actual `screen_w/screen_h`).

### 3) Stability smoke — no-LLM path
- Continue `python main.py --no-llm` for ~10 minutes.
- **Expected**
  - No crashes/softlocks.
  - No obvious UI redraw/flicker issues.

### 4) Stability smoke — mock provider path
- Run:
  - `python main.py --provider mock`
- Play ~10 minutes.
- **Expected**
  - No crashes/softlocks.
  - Same UI behavior/readability as above.

### 5) UI manageability (P0 polish)
- **Quit button**
  - **Expected**: a clearly labeled **Quit** button exists in the HUD (top-left or top-right) and **exits the game reliably** when clicked.
- **Hero details panel close (X)**
  - Steps: click/select a hero to open the hero details panel → click the panel’s **X** close button.
  - **Expected**: panel closes immediately; no crash.
- **Debug/perf UI close (X)**
  - Steps: open debug/perf UI (FPS readout / debug window, if enabled) → click the UI’s **X** close button.
  - **Expected**: debug/perf UI closes immediately; no crash.
- **Perf overlay placement**
  - **Expected**: FPS/perf overlay is positioned so it does **not** fight/overlap key HUD regions (top bar and right panel); choose a less-intrusive corner by default.

## Build A (Midweek) — Automated Gate (required)
- Run:
  - `python tools/qa_smoke.py --quick`
- **Expected**
  - Exit code 0 (PASS).

## Asset validation policy (locked)
- **Build A**: validator is **report-only** (no failing gate yet).
- **Build B**: validator becomes **strict/failing gate** (plus attribution checks).

## Optional (Build A) — Asset validator (non-blocking)
- Run (report-only):
  - `python tools/validate_assets.py --report`
- **Expected**
  - Exit code 0 and a human-readable report (no gate failures in Build A).

## Build B (Endweek) — Automated Gates (required)
- **Baseline regression gate (always-on)**
  - Run:
    - `python tools/qa_smoke.py --quick`
  - **Expected**: exit code 0 (PASS).
- **Asset validation gate (strict + attribution)**
  - Run:
    - `python tools/validate_assets.py --strict --check-attribution`
  - **Expected**:
    - Exit code 0 (PASS)
    - Missing required sprite states/frames for any manifest entry => **FAIL**
    - If any `assets/third_party/<pack>/` exists:
      - Require `assets/ATTRIBUTION.md` (rollup) and per-pack `LICENSE*.txt` (and README if available)


