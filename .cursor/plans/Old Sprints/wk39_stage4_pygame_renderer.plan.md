# WK39 — Stage 4: `PygameRenderer` extraction

## Authority

- **Stage 4 (scope, DoD, split list):** [.cursor/plans/master_plan_architecture_refactor.md](master_plan_architecture_refactor.md) — *Stage 4: Render Method Extraction* (~L861–892).
- **Owner:** Agent **03** (Technical Director) — **MEDIUM** intelligence; **Agent 11 (QA)** — **LOW** per gate.
- **Ursina path:** Do not regress 3D + pygame HUD compositing; verify after changes.

## Definition of done (sprint)

- `GameEngine.render()` **delegates world-layer drawing** to a new `PygameRenderer` (or equivalent in `game/graphics/pygame_renderer.py`); world path consumes **`self.build_snapshot()`** / `SimStateSnapshot` per round goals.
- **HUD, building_panel, build_catalog, pause, perf overlay, micro-view hook** stay in `GameEngine` (per master plan).
- **Gates (each round, minimum):** `python -m pytest tests/`; `python tools/qa_smoke.py --quick`; `python tools/validate_assets.py --report` (errors=0; warns baseline OK).

**Manual (R3, Jaimie) — from repo root (PowerShell):**

```powershell
python main.py --no-llm
```

```powershell
python main.py --renderer ursina --no-llm
```

## Rounds

| Round | Focus |
|--------|--------|
| **WK39-R1** | Add `game/graphics/pygame_renderer.py`; move world block from `GameEngine.render` (view surface through world/entities/fog/bounties/blit) without behavior change. Document **building_menu** / **building_list_panel** in-world vs **building_panel** on screen. |
| **WK39-R2** | Snapshot-first iteration where safe; context object; optional **dedupe** with `_render_hero_minimap` shared helper. |
| **WK39-R3** | Hardening: small tests, docs touch if needed; full gates; Jaimie visual parity. |

## Out of scope

- Stage 5 cleanup; **CHANGELOG** version bump (Jaimie’s call); **UrsinaRenderer** refactors not required for parity.

## Risks

- Draw order (fog, bounties, VFX): preserve line order from pre-refactor `render()`.
- `bounty_system.update_ui_metrics`: keep same relative order vs bounty draw.
- `skip_pygame_world` (Ursina) branch: must still work.

See also: [.cursor/plans/wk39_stage_4_pygamerenderer_20c5ad3d.plan.md](wk39_stage_4_pygamerenderer_20c5ad3d.plan.md) for the longer mermaid + risk table (duplicate reference).
