# WK122 — Tax-Gold Overlay Polish + Guardhouse Two-Arrow Fix

**Sprint owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-02
**Renderer in scope:** Ursina (3D) — the default `python main.py` path
**Version target:** patch (gameplay/UX polish — no version bump unless Jaimie asks)

---

## Goal

Two Sovereign-reported polish items, both on the shipping **Ursina** renderer:

1. **Taxable-gold overlay (hold-`G`)** — already implemented, but it (a) **hovers too high** above
   building roofs and (b) the `$N` **text hides behind other buildings** instead of drawing on a top
   layer. Lower the label to sit just above the roof, and force it to render over ALL world geometry.

2. **Guardhouse two-arrow volley** — the guardhouse is supposed to fire **2 arrows per volley from two
   distinct spots** on the building so both are visible. In practice only **one** arrow renders.

Both must be **screenshot-verified** on the Ursina renderer (Jaimie's explicit ask for the arrows:
"design a test that starts the game with the guard tower firing at an enemy and screenshot to make
sure you see 2 distinct arrows, and reiterate until a screenshot clearly shows it").

---

## Root-cause analysis (PM investigation — for the implementing agents)

### Feature 1 — tax-gold overlay

- File: `game/graphics/ursina_building_ui.py`
- Height: `_building_gold_overlay_world_y(ent, terrain_y, hy)` returns `terrain_y + roof_local + 1.2`,
  where for prefab buildings `roof_local = _prefab_local_top_y(ent) + 0.50`. Net result ≈ **roof + 1.7
  world units** — a large visible gap (confirmed in baseline `docs/screenshots/wk122_baseline_tax/`).
- Layering: the `$N` label is an Ursina `Text(parent=scene, billboard=True)` passed through
  `_configure_ks_overlay` → `game/graphics/ursina_unit_overlays.py::configure_ks_overlay`, which sets
  `set_depth_test(False)` + `always_on_top=True` + `render_queue=2` + nudges `z=-0.02`. That is NOT
  reliably forcing the text into a top render bin, so taller buildings drawn later still paint over it.

### Feature 2 — guardhouse arrows (THE BUG)

The sim **already builds two arrow events with distinct origins**, but the engine **drops the second**:

- `game/entities/buildings/defensive.py::Guardhouse.update()` builds `self._last_ranged_events` — a
  **list** of `GUARDHOUSE_ARROWS_PER_SHOT` (=2, `config.py:31`) projectile events, each with a distinct
  origin offset (`offset_x = (i-0.5)*24` → ±12px, `offset_y = (i-0.5)*8` → ±4px), all aimed at the same
  target. It also keeps `self._last_ranged_event` (**singular**, = the first arrow) for back-compat.
- `game/sim_engine.py:900–905` collects **only the singular** `_last_ranged_event` into
  `building_ranged_events` and emits that to the event bus. **The plural `_last_ranged_events` list is
  never read.** → VFX spawns 1 `ProjectileVFX` → snapshot carries 1 → Ursina draws 1 billboard.
- Downstream is fine: `VFXSystem._emit_event` (`game/graphics/vfx.py:95`) spawns one `ProjectileVFX`
  per event; `game/graphics/ursina_misc_props_sync.py::sync_snapshot_projectiles` renders one billboard
  per distinct `ProjectileVFX`. So once **both** events are collected, both arrows render distinctly.

**Constraint:** `tests/test_wk65_buildings_systems_characterization.py` pins that `Guardhouse.update()`
still sets the **singular** `_last_ranged_event` and deals a 2-arrow damage volley. Keep that intact —
the fix only changes what `sim_engine.py` *collects for emission*, not what the building sets.

---

## Tickets

### WK122-BUG-A1 — tax-gold overlay hovers too high (owner: Agent 09)
- **Repro:** `python main.py`, hold `G` over any tax building (house/guild/marketplace/food_stand).
- **Actual:** `$N` floats well above the roof (≈ roof + 1.7 world units).
- **Expected:** `$N` sits just above the roof (small, readable clearance — target ≈ roof + 0.3–0.5),
  for prefab AND billboard buildings.
- **Acceptance:** post-fix Ursina capture shows the label hugging the roofline, not floating.

### WK122-BUG-A2 — tax-gold text hides behind other buildings (owner: Agent 09)
- **Repro:** hold `G` with buildings clustered/overlapping in screen space.
- **Actual:** some `$N` labels are occluded by nearer/taller building geometry.
- **Expected:** every `$N` renders **on top of all world geometry** (buildings, terrain, trees), always.
- **Fix direction:** make `configure_ks_overlay` force a genuine top overlay bin for the `Text`
  (e.g. Panda `set_bin("fixed", <high>)` + `set_depth_write(False)` + `set_depth_test(False)`), so it
  draws after all opaque geometry regardless of draw order. Keep the change inside `configure_ks_overlay`
  so HP bars / name labels that already use it are not regressed (verify they still look right).
- **Acceptance:** post-fix capture with overlapping buildings shows NO occluded `$N`.

### WK122-BUG-B1 — guardhouse fires only one visible arrow (owner: Agent 03 + Agent 05)
- **Root cause:** `sim_engine.py:900–905` collects only the singular `_last_ranged_event`.
- **Fix:** when a building exposes a non-empty `_last_ranged_events` list, extend `building_ranged_events`
  with ALL of them (and clear the list); otherwise fall back to the singular `_last_ranged_event`. Keep
  setting/clearing the singular field so the characterization tests stay green.
- **Tuning (Agent 05, only if needed for visual separation):** the ±12px origin offsets converge at the
  shared target. If the two arrows are not clearly distinct in flight, widen the lateral separation a bit
  and/or apply a small perpendicular offset to BOTH origin and target so the arrows stay side-by-side
  ("close to each other though, not too big of a gap" — keep it subtle). Do not change damage/cooldown.
- **Acceptance:** (headless) a new unit test proves 2 `ranged_projectile` events are collected/emitted
  per volley and 2 `vfx_projectiles` reach the snapshot; (visual) the capture in WK122-T3 shows 2 arrows.

### WK122-T3 — guardhouse-arrows Ursina capture scenario (owner: Agent 12)
- Build a deterministic Ursina capture, modeled on `tools/wk67_combat_capture_patch.py`:
  - new `tools/wk122_guardhouse_arrows_capture_patch.py`
  - register `"ursina_guardhouse_arrows"` in `tools/screenshot_scenarios.py::URSINA_CAPTURE_SCENARIOS`
- Scene: place ONE guardhouse + ONE enemy inside `GUARDHOUSE_ARROW_RANGE_TILES`, reveal the map, disable
  wave/neutral spawns, keep the enemy alive at full HP, and **hold an in-flight volley** so the captured
  frame always shows the arrows mid-flight (e.g. each tick keep the enemy in range + reset the arrow timer
  so a fresh volley fires, OR re-pin two `ProjectileVFX` at a fixed mid-progress). Frame a fixed
  (non-EditorCamera) oblique camera tightly on the guardhouse→enemy gap. Disable the FPS overlay.
- **Acceptance:** `python tools/run_ursina_capture_once.py --scenario ursina_guardhouse_arrows
  --out docs/screenshots/wk122_guardhouse_arrows` writes a PNG that clearly shows **2 distinct arrow
  billboards** between the guardhouse and the enemy. (PM runs the live capture; agent ships the scenario
  + import smoke since headless agents have no GPU.)

---

## File ownership / lanes

| Ticket | Agent | Files MAY edit | MUST NOT edit |
|---|---|---|---|
| A1+A2 | 09 ArtDirector | `game/graphics/ursina_building_ui.py`, `game/graphics/ursina_unit_overlays.py` | sim, tools, config, tests |
| B1 | 03 + 05 | `game/sim_engine.py`, `game/entities/buildings/defensive.py`, `config.py` (read), `tests/test_wk122_guardhouse_two_arrows.py` (new) | graphics, tools |
| T3 | 12 Tools | `tools/wk122_guardhouse_arrows_capture_patch.py` (new), `tools/screenshot_scenarios.py` | game/**, config |

Files are disjoint → the three tickets run in parallel.

## Gates (every implementing agent, headless)
```
python tools/qa_smoke.py --quick
python -m pytest tests/test_wk65_buildings_systems_characterization.py tests/test_combat.py -q   # B1
python -m pytest tests/test_wk122_guardhouse_two_arrows.py -q                                    # B1 (new)
python -c "import tools.screenshot_scenarios"                                                    # T3 import smoke
```
Ursina graphics changes can't be GPU-verified by a headless agent (see
`.cursor/rules/11-fps-performance-guardrails.mdc`) → ship with the headless gates + a verbatim diff; the
**PM runs the live Ursina captures** below and iterates.

## PM live verification (Agent 01, on GPU)
```
python tools/run_ursina_capture_once.py --scenario wk61_hold_g_tax_overlay --ticks 720 --out docs/screenshots/wk122_tax_after
python tools/run_ursina_capture_once.py --scenario ursina_guardhouse_arrows --out docs/screenshots/wk122_guardhouse_arrows
```
Inspect PNGs; iterate (fix → re-capture) until: tax `$N` hugs the roof and is never occluded; the
guardhouse capture clearly shows 2 distinct arrows.

## Send list (intelligence)
- Agent 09 — ArtDirector (**medium** — scoped Ursina overlay fix following a known pattern)
- Agent 03 — TechnicalDirector (**medium** — small sim-engine collection fix, contract-aware)
- Agent 05 — GameplaySystems (**medium** — defensive.py offset tuning, consult on B1)
- Agent 12 — ToolsDevEx (**medium** — new capture scenario modeled on wk67 patch)
- Do NOT send: 02, 04, 06, 07, 08, 10, 11(consult), 13, 14, 15
- **DO NOT COMMIT. DO NOT run git. Stay in your lane. Update your own agent log only.**

## Definition of Done
- All headless gates green; new B1 test proves 2 arrows collected.
- PM Ursina captures show: tax label hugging roof + on top of all buildings; 2 distinct guardhouse arrows.
- PM hub + plan doc updated; Jaimie shown the before/after screenshots.
