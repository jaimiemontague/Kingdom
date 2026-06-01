# WK120 Round B — Move 12 (TaskRouter), faithful form: extract `update_hero` → `ai/task_router.py`

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk120_round_b_task_router_extract`
**Version target:** patch (behavior-preserving owner-arg pure-move)
**Verification class:** HEADLESS. **WK67-digest-GUARDED (HIGH confidence):** unlike the ursina render moves, `update_hero` is EXACTLY the path the WK67 AI-decision digest exercises (300 headless ticks, 3 seeded heroes). A faithful relocation that keeps the digest byte-identical is therefore *provably* behavior-preserving with strong headless coverage. No screenshots.
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. Scope decision (read first)

Roadmap **Move 12** as written = replace `BasicAI.update_hero`'s priority ladder with a
**competitive `propose() -> TaskProposal` router** (all behaviors propose; router picks
max priority). That is a **behavior-changing design** (it changes *when* each behavior
runs and the `_AI_RNG` draw order) → it would SHIFT the WK67 digest that has been the
byte-identical invariant for 50+ sprints. Changing the pinned AI behavior is a
**gameplay decision**, not de-slop.

**WK120 does the SAFE structural half of Move 12:** relocate `update_hero`'s dispatch
verbatim into a new `ai/task_router.py` (the "task router" module the roadmap names),
behind a 1-line delegating wrapper on `BasicAI` — the proven owner-arg pure-move,
**digest-byte-identical**. This creates the `ai/task_router.py` module + slims
`ai/basic_ai.py` (~415 → ~290 LOC) without any behavior risk.

**DEFERRED (flag to Sovereign):** the competitive-`propose()` re-architecture is a
separate, behavior-affecting enhancement that would move the WK67 digest and so needs an
explicit re-baseline decision. It is NOT attempted here. PM records this as the one
remaining roadmap item requiring a Sovereign go-ahead.

**DO NOT COMMIT** — PM owns the commit.

---

## 1. The move (Agent 06 — Wave 1)

Create `ai/task_router.py`. Move the BODY of `BasicAI.update_hero` (HEAD `ai/basic_ai.py`
L205–335) into a module function `update_hero(ai, hero, dt, view)` (owner-arg; the BasicAI
instance is the `ai` param). Copy the body VERBATIM; the ONLY change is `self.` → `ai.`
everywhere. Keep the docstring + all comments. No logic/ordering/literal changes.

Then replace `BasicAI.update_hero` (L205–335) with the wrapper:
```python
def update_hero(self, hero, dt: float, view):
    """Update AI for a single hero."""
    from ai import task_router
    return task_router.update_hero(self, hero, dt, view)
```
Leave `BasicAI.update` (L192–203, the all-heroes loop calling `self.update_hero`)
UNCHANGED — it still calls `self.update_hero(hero, dt, view)` (the wrapper).

Everything the body calls that is a method/attr on BasicAI stays `ai.<name>` (e.g.
`ai.refresh_intent`, `ai.stuck_recovery_behavior`, `ai.defense_behavior`,
`ai.hunger_behavior`, `ai.llm_bridge_behavior`, `ai._finalize_deferred_task`,
`ai.handle_resting`, `ai.send_home_to_rest`, `ai._is_committed_destination`,
`ai._debug_log`, `ai.llm_brain`, `ai.handle_idle/handle_moving/handle_fighting/
handle_retreating/handle_shopping`). Do NOT rewrite those to direct calls — they live on
the class.

---

## 2. New-module skeleton (`ai/task_router.py`)

```python
"""WK120 (roadmap Move 12, faithful form): the per-hero AI decision dispatch ("task
router") extracted verbatim from BasicAI.update_hero. BasicAI keeps a 1-line delegating
wrapper; this function takes the BasicAI instance as ``ai``. Byte-faithful move — no
behavior change (WK67 digest byte-identical).

NOTE: the roadmap's competitive propose()->TaskProposal re-architecture is a separate,
behavior-affecting enhancement (it would shift the WK67 digest) and is intentionally NOT
done here — see the WK120 plan §0."""
from __future__ import annotations

from ai.behaviors.view_compat import as_ai_view, view_to_legacy_context
from ai.context_builder import ContextBuilder
from ai.prompt_templates import get_fallback_decision
from config import TILE_SIZE
from game.entities.hero import HeroState
from game.sim.direct_prompt_commit import (
    clear_direct_prompt_commit,
    expire_direct_prompt_commit_if_timed_out,
)


def update_hero(ai, hero, dt: float, view) -> None:
    """Update AI for a single hero."""
    ...  # verbatim body of BasicAI.update_hero, self -> ai
```

**Import-set rule:** these 6 import lines are EXACTLY the module-level names `update_hero`
references (grep-confirmed: `as_ai_view`, `view_to_legacy_context`, `ContextBuilder`,
`get_fallback_decision`, `TILE_SIZE`, `HeroState`, `clear_direct_prompt_commit`,
`expire_direct_prompt_commit_if_timed_out`). Do NOT import `route_to_building`,
`BuildingType`, `get_rng`, `sim_now_ms`, or the `ai.behaviors` block — `update_hero`
does not reference them. Add an import ONLY if a body line references the name.

**Acyclic:** `ai/task_router.py` must NOT import `ai.basic_ai` at module top. The `ai`
param is left untyped (or TYPE_CHECKING-only if a hint is wanted). `basic_ai` imports
`task_router` LAZILY inside the wrapper. The seam test's fresh-subprocess both-import-
orders check (§5) is the guard. (view_compat / context_builder / prompt_templates /
direct_prompt_commit must not import basic_ai at top — confirm via the no-cycle test.)

Agent 06 self-verify (paste raw output; DO NOT COMMIT):
- `python -c "import ai.basic_ai; import ai.task_router"` → no error.
- `python -c "import ast,io; t=ast.parse(io.open('ai/task_router.py',encoding='utf-8').read()); print('self count =', sum(1 for n in ast.walk(t) if isinstance(n,ast.Name) and n.id=='self'))"` → `self count = 0`.
- `python -c "import ai.task_router as m, inspect; print(list(inspect.signature(m.update_hero).parameters))"` → `['ai', 'hero', 'dt', 'view']`.
- `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable tests/test_wk82_basic_ai_handlers.py tests/test_wk85_handle_idle_split.py -q` → green (digest byte-identical is the key signal).
- Report new `ai/basic_ai.py` line count (expect ~290).
- Update the Agent 06 log; report to PM.

---

## 3. PM verbatim-diff gate (Agent 01 — before commit)

AST-extract `BasicAI.update_hero`'s body from HEAD `ai/basic_ai.py` and the body of
`ai/task_router.py::update_hero`. Canonicalize whole-word `self`/`ai`→`@`, line-diff.
**Expected: IDENTICAL** (pure `self`→`ai` rename; no allowed structural diffs — every
body line must match after canonicalization). Any diff = STOP, bounce to Agent 06.
(The digest gate in §5 is the runtime corroboration; the verbatim gate is the static proof.)

---

## 4. Wave 2 — Agent 11: seam test + DoD

Create `tests/test_wk120_task_router.py`:
- **Existence + signature:** `ai.task_router.update_hero` exists, callable, signature
  `(ai, hero, dt, view)` (first param `ai`).
- **Wrapper delegation:** spy+monkeypatch `task_router.update_hero`; build a bare
  `BasicAI`-ish caller — simplest: `from ai.basic_ai import BasicAI; b = BasicAI(llm_brain=None)`
  (it constructs cheaply headless) and call `b.update_hero(hero_stub, 0.05, view_stub)` with
  the module fn monkeypatched to a spy; assert the spy got `(b, hero_stub, 0.05, view_stub)`
  and the wrapper returned its result. (If constructing a real BasicAI is heavy, use
  `object.__new__(BasicAI)` and call the unbound wrapper.)
- **AST no-cycle:** `ai/task_router.py` has no module-top `import ai.basic_ai` / `from ai.basic_ai import`.
- **fresh-subprocess BOTH import orders** (`ai.task_router` ↔ `ai.basic_ai`) → OK.
- **Source guard:** `ai/basic_ai.py` source references `task_router.update_hero`.

Then full DoD (paste raw output; DO NOT COMMIT):
1. `python -m pytest -q` → 0 failed (record counts; expect 1493+N).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py -q` → ALL green (the full WK67 suite, incl. the keystone digest + reproducibility — this is the load-bearing behavior proof for an AI-path move). Digest `b73961340c…d148ded`.
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk120_task_router.py tests/test_wk82_basic_ai_handlers.py tests/test_wk83_movement_dispatcher.py tests/test_wk84_zones_extract.py tests/test_wk85_handle_idle_split.py -q` → all green (the AI-extraction seam suite).
Update the Agent 11 log; report a PASS/FAIL table.

---

## 5. Definition of done (PM gate)

- [ ] `ai/task_router.py`: `update_hero(ai, hero, dt, view)`; ZERO `self` code-identifiers (AST).
- [ ] `ai/basic_ai.py`: `update_hero` is the 1-line delegating wrapper; body relocated; ~290 LOC; `update()` loop unchanged.
- [ ] PM verbatim-diff gate: task_router body == HEAD update_hero body, IDENTICAL after self→ai canonicalization.
- [ ] `tests/test_wk120_task_router.py` green; the WK82–85 AI-seam suite green.
- [ ] full `pytest -q` 0 failed; determinism clean; **full WK67 suite green + digest byte-identical** (the decisive proof for an AI-path move); qa_smoke PASS.
- [ ] both fresh-import orders OK.
- [ ] Agent 06 + 11 logs updated. PM commits (scoped add: `ai/basic_ai.py`, `ai/task_router.py`, `tests/test_wk120_task_router.py`, plan + PM hub + agent logs) + pushes.

---

## 6. Roadmap status after WK120

With Move 12's structural half done, the GPT-5.5 recommendations + audit inventory are
**complete except for one explicitly-deferred behavior-design item**:
- **Move 12 propose() re-architecture (DEFERRED, needs Sovereign go-ahead):** converting
  the relocated `update_hero` priority ladder into a competitive `propose()->TaskProposal`
  model. This WOULD change AI behavior and move the WK67 digest (a 50+-sprint invariant),
  so it requires an explicit decision to re-baseline. PM will surface this at the
  checkpoint as the one remaining roadmap item that is a gameplay change, not de-slop.

Tiny optional headless items remaining (any is a clean future sprint):
- `world.py:60` `_currently_visible: list` → `set` (prove determinism-neutral via the
  WK67 fog-revision pin + determinism_guard).
- `ursina_app.__init__` scene-construction split (render-deferred; diminishing returns).

PM recommendation: the roadmap is substantially complete; the marathon's de-slop/refactor
scope is essentially exhausted. Surface the Move-12-propose() deferral + the tiny optional
items to the Sovereign at the next checkpoint rather than auto-attempting the behavior-
changing re-architecture.
