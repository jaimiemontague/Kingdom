# WK40 — Post-assessor optional tidy (1 agent + backlog)

**Goal:** Address the two “small open items” from the third-party refactor assessor *without* a new sprint, **or** file the second item and move on.

| Item | Action | Who |
|------|--------|-----|
| 1 | Clarify in code that `GameEngine` is the presentation/shell (refactor’s “PresentationLayer”); optional `PresentationLayer` alias | **Agent 03 (Tech)** — LOW intelligence |
| 2 | `building_panel.engine` + `getattr(panel, "engine")` in economic renderers | **Done** (REFACTOR-TECH-001): `BuildingPanel` + `on_request_ursina_hud_upload` + `GameEngine._request_ursina_hud_upload` |

**Do not** mix this with the mechanical 2K-line file split; that is a **separate** future sprint.

---

## Prompt 1 — Agent 03 (Technical Director), LOW intelligence

Copy everything in the block below into a new Cursor chat and run it when Jaimie is ready.

```text
You are Agent 03 (Technical Director). This is a tiny documentation-only (plus optional alias) follow-up to the architecture refactor, per post-assessor notes — no behavior change.

1) Read **only** the relevant bits of `game/engine.py` (top-of-file module docstring, and `class GameEngine` + its class docstring).
2) **Update the module docstring** so it states clearly that this file’s `GameEngine` is the **presentation-side shell** that wraps `SimEngine` and owns the pygame/loop/HUD; call out that the refactor’s design doc refers to this role as *PresentationLayer* but the public class name remains `GameEngine` for import compatibility.
3) **Update the `GameEngine` class docstring** to match (1–2 sentences, not an essay).
4) At the **end of `game/engine.py`**, add a public alias:
   `PresentationLayer = GameEngine`
   and one comment line that `GameEngine` is the name used in imports and tests.
5) Grep: ensure no new circular imports. Do not change any logic, wiring, or `self.building_panel.engine` in this task (separate backlog ticket in PM: REFACTOR-TECH-001).
6) Gates: `python -m pytest tests/` and `python tools/qa_smoke.py --quick` (must pass).
7) Update `.cursor/plans/agent_logs/agent_03_TechnicalDirector_Architecture.json` with what you changed, commands, and exit codes.

Sprint context (optional read): `.cursor/plans/wk40_post_assessor_tidy_prompts.md`
```

---

## Item 2 — No second agent (optional follow-up is already in PM hub)

The assessor’s **moderate** item is **`self.building_panel.engine = self`** in `game/engine.py` and **`getattr(panel, "engine", None)`** in `game/ui/building_renderers/economic_panel.py` (`_request_live_hud_upload_for_ursina`).

Filing it without implementation avoids scope creep. **If you add a second agent later:** send **Agent 08 (UX) — MEDIUM** with **Agent 03 (consult)**, to replace the engine back-reference with an explicit `Callable[[], None]` or similar passed into `BuildingPanel` / renderer setup for the Ursina HUD force-upload path.

**PM hub reference:** `agent_01_ExecutiveProducer_PM.json` → `sprints["wk40-refactor-stage5-cleanup"]` → `sprint_meta.pm_tech_debt` → ticket `REFACTOR-TECH-001`.

---

## Send order

1) **One chat:** paste Prompt 1 → **Agent 03 (LOW).**  
2) **No chat needed** for item 2 if you accept the filed ticket.  
3) (Later) **Agent 11** can re-run `python tools/qa_smoke.py --quick` if you want a post-merge confirmation after 03’s PR lands.
