---
name: Assembler scale hotkeys
overview: "Add uniform per-piece scale nudging in [tools/model_assembler_kenney.py](tools/model_assembler_kenney.py) using `-` / `=` (with optional Shift for finer steps), while preserving the existing Keene pack multiplier contract: saved JSON remains logical `scale` triples; on-screen `Entity.scale` stays `logical * pack_extent_multiplier_for_rel(model_rel)`."
todos:
  - id: add-helpers
    content: Add apply_piece_scale_to_entity + _nudge_selected_scale with multiplicative step, clamp, Shift=fine in model_assembler_kenney.py
    status: pending
  - id: wire-input
    content: Map minus/equals in handle_input; update Controls docstring + _refresh_status scale line
    status: pending
  - id: verify-manual
    content: Assembler open/save round-trip + one in-game/viewer size check for farm_v1 piece
    status: pending
isProject: false
---

# Midsprint plan: Assembler `-` / `=` scale nudge (Kenney-safe)

## Why this is safe (contract)

- Each placed piece is a [`PlacedPiece`](tools/model_assembler_kenney.py) with **logical** `scale: (sx, sy, sz)` that is what gets written to prefab JSON (see `PlacedPiece.to_json()`).
- On spawn, [`_spawn_piece_core`](tools/model_assembler_kenney.py) sets:

```text
pf = pack_extent_multiplier_for_rel(rel)   # single source: tools/kenney_pack_scale
entity.scale = (sx*pf, sy*pf, sz*pf)
```

- In-game prefab loading uses the same `pf` in the runtime loader ([`ursina_renderer` prefab path](game/graphics/ursina_renderer.py) via `kenney_pack_scale` + piece `scale` from JSON). So: **any change must only update `PlacedPiece.scale` (logical)** and re-apply the **same** `* pf` to the Ursina `Entity` — do **not** bake `pf` into JSON and do not replace `pf` with a new constant.

## Behavior to implement

| Key | Action |
|-----|--------|
| `-` (and optionally numpad subtract) | Uniformly **shrink** the selected piece |
| `=` | Uniformly **grow** the selected piece |
| `Shift` held | Use a **smaller** step (same pattern as `Shift+WASD` in [`handle_input`](tools/model_assembler_kenney.py) ~1154-1186) |

- **No selection** → no-op (or a one-line toast via existing `_show_toast` if you want parity with “no piece selected” feedback).
- **Multiplicative nudge (recommended):** `sx,sy,sz` each multiplied by `step_factor` (e.g. `1.02` grow / `~0.98` shrink) so non-uniform logical scales in existing JSON (if any) keep their **ratio** when sizing up/down. Alternative (simpler but wrong for anisotropic scales): add a fixed `delta` to all axes — not recommended.
- **Clamp lower bound** on each component (e.g. `max(0.01, s)` or `0.05`) to avoid vanishing or negative scales.
- **Optional upper bound** (e.g. 5.0) to avoid accidental runaway; optional, only if you see problems in practice.

**Constants (top of file, next to `NUDGE_STEP`):** e.g. `SCALE_NUDGE_FACTOR = 1.02` (coarse) and `SCALE_NUDGE_FACTOR_FINE = 1.005` (Shift) — or use a single `SCALE_STEP` like `0.02` and `scale * (1 ± step)`; pick one style and use it in both directions symmetrically: `1/1.02` for shrink if grow uses `1.02`.

## Code changes (single file)

**File:** [tools/model_assembler_kenney.py](tools/model_assembler_kenney.py)

1. **Helper** (private method on the assembler class or module-level function taking `PlacedPiece` + `App`):
   - `apply_piece_scale_to_entity(piece)`:
     - `rel = piece.model_rel`
     - `pf = pack_extent_multiplier_for_rel(rel)`  (already imported)
     - `s = piece.scale`
     - `piece.entity.scale = Vec3(s[0]*pf, s[1]*pf, s[2]*pf)`  
   - Call this at the end of any scale edit so the display always matches the Kenney contract.

2. **New method** e.g. `_nudge_selected_scale(factor: float) -> None`:  
   - If `self.selected` is `None` → return.  
   - Update `self.selected.scale = (s0*factor, s1*factor, s2*factor)` (after clamp).  
   - `apply_piece_scale_to_entity(self.selected)`  
   - `self._refresh_status()`

3. **`handle_input`:** After the existing `]` / `[` block, add:
   - `if key in ("minus", "subtract", "-")` — verify Ursina key string for the main keyboard minus; map both `minus` and numpad `subtract` if needed (same as other tools often do for consistency).
   - `if key in ("equals", "=")` — same for `equals` / numpad `+` is **not** the same as `=`; user asked specifically for `=`; implement `equals` first, add `+` only if you want grow on numpad without shift.

4. **Status line** ([`_refresh_status`](tools/model_assembler_kenney.py) ~1237+): append logical `scale=({sx:.2f},{sy:.2f},{sz:.2f})` for the selected piece so you can see values while tuning the farm.

5. **Module docstring** (lines 28-39 “Controls:”): document `-` / `=` and `Shift` for fine.

## Verification (manual, no new automated test required for this tool)

- Run: `python tools/model_assembler_kenney.py --open farm_v1` (or the farm prefab you are fixing).
- Select a piece, press `=` a few times, `-` a few times; confirm the yellow wireframe shrinks/grows in proportion and the status line updates.
- **Save** prefab, **reopen**; scales must reload identically (already loaded via `_load_from_disk` + `_spawn_piece_core` with `scale=` from JSON).
- **Spot-check in game** (or viewer): open the same JSON in the renderer — visual size should match the assembler (same `logical * pf` contract).

## Ownership and scope

- **Owner:** Agent 12 (Tools) per repo boundaries; one focused PR: only [tools/model_assembler_kenney.py](tools/model_assembler_kenney.py) unless you discover a shared helper worth extracting (prefer keep changes local for midsprint).
- **Out of scope for this item:** `model_viewer_kenney` parity hotkeys, changing `kenney_pack_scale` math, or [game/graphics/ursina_renderer.py](game/graphics/ursina_renderer.py) (unless a bug in contract is found — then file a separate ticket).
