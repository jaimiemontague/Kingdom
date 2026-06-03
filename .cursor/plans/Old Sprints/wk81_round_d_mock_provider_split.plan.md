# WK81 Sprint Plan — Round D-1: mock_provider.py → ai/providers/mock/ package

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the 519-LOC MockProvider split into an `ai/providers/mock/` package behind delegating wrappers; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-80. **Roadmap:** Round D (AI), and the audit's mock_provider split. Chosen now because it's headless + perfectly digest-guarded.

## 0. TL;DR
`ai/providers/mock_provider.py` (519 LOC) conflates 4 unrelated mock LLM responders + a prompt sniffer in one class. WK81 extracts the responder bodies into `ai/providers/mock/` modules using the proven pure-move pattern (functions take the `MockProvider` as `provider`; the methods become 1-line delegating wrappers), keeping `MockProvider` at `ai/providers/mock_provider.py` so the provider registry import is unchanged. **The AI-decision digest USES this mock to drive hero decisions, so it is a PERFECT guard** — any change to a mock response (autonomous/decision path) breaks `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`. Also qa_smoke's direct_prompt/conversation scenarios exercise the other responders. Headless, no screenshots. PM writes no code.

## 1. Scope
**IN:** create `ai/providers/mock/` and move the responder bodies into modules as functions taking `provider`:
- `ai/providers/mock/autonomous.py`: `mock_autonomous_decision(provider, user_prompt)` ← `_mock_autonomous_decision` (mock_provider.py:111-194, incl. the nested `pick`).
- `ai/providers/mock/direct_prompt.py`: `mock_direct_prompt(provider, user_prompt)` ← `_mock_direct_prompt` (195-364, incl. nested `find_place`/`base`). Also the module helpers `_hero_ctx_from_prompt_blob`/`_emit_validated_direct` if used only here (else keep them in a shared `_helpers.py`).
- `ai/providers/mock/legacy_decision.py`: `make_decision(provider, ...)` ← `_make_decision` (365-484).
- `ai/providers/mock/conversation.py`: `mock_conversation_response(provider, system_prompt, user_prompt)` ← `_mock_conversation_response` (485-519).
- `ai/providers/mock/__init__.py` (empty or docstring).
- `MockProvider` STAYS in `ai/providers/mock_provider.py` as the facade: keep `name`, `complete` (the dispatcher — leave its prompt-sniffing/format-detection logic in place), the module helper `_norm_msg`, and a 1-line delegating wrapper for each moved responder (`def _mock_autonomous_decision(self, user_prompt): from ai.providers.mock import autonomous; return autonomous.mock_autonomous_decision(self, user_prompt)`). `complete()` keeps calling `self._mock_autonomous_decision(...)` etc. (now wrappers) — so the dispatch is unchanged.

**OUT:** changing the dispatch/sniffing logic in `complete()`; touching the other providers (openai/grok/anthropic); any change to a mock response's output. **Move responder bodies VERBATIM (self.->provider.).**

## 2. Pattern (WK75-79, verbatim)
```python
# ai/providers/mock/autonomous.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports the method used ...
if TYPE_CHECKING:
    from ai.providers.mock_provider import MockProvider

def mock_autonomous_decision(provider: "MockProvider", user_prompt: str) -> str:
    # EXACT body, self.->provider.  (nested helpers like `pick` move with it)
    ...
```
```python
# ai/providers/mock_provider.py
def _mock_autonomous_decision(self, user_prompt):
    from ai.providers.mock import autonomous
    return autonomous.mock_autonomous_decision(self, user_prompt)
```
TYPE_CHECKING-only MockProvider import; no cycle; copy each method's leaf imports (the module helpers `_norm_msg`/`_hero_ctx_from_prompt_blob`/`_emit_validated_direct`, validator imports, etc.); preserve output EXACTLY.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **758 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (PERFECT guard — the digest's hero decisions come from this mock).
- **D.** `qa_smoke.py --quick` green (its direct_prompt_integration + conversation scenarios exercise the moved responders).
- **E.** `ai/providers/mock/{autonomous,direct_prompt,legacy_decision,conversation,__init__}.py` exist; `MockProvider` still importable from `ai/providers/mock_provider.py` with the 4 responder names as delegating wrappers; mock_provider.py smaller (~519 → ~180); no import cycle.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 06):** extract the package + wrappers. Verify suite + digest + qa_smoke.
- **W2 (Agent 11):** seam test (modules exist + wrappers delegate + MockProvider still imports from the old path) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A responder's output changes subtly → digest breaks | Med | move VERBATIM; the digest is a PERFECT guard (catches any change in the autonomous/decision path); qa_smoke catches direct_prompt/conversation |
| Import cycle (mock submodule ↔ mock_provider) | Med | TYPE_CHECKING-only import (proven WK75-79) |
| A shared module helper (_hero_ctx/_emit_validated) referenced from two responders | Low-Med | put shared helpers in a mock/_helpers.py imported by both; or keep them in mock_provider.py and call via provider/module |
| Provider registry import breaks | Low | MockProvider stays at ai/providers/mock_provider.py |

## 6. Success
The 4 mock responders live in focused `ai/providers/mock/` modules behind a thin MockProvider facade, the mock LLM returns byte-identical responses — proven by 758+ green tests, clean determinism guard, unchanged digest (the definitive proof, since the digest's decisions ARE the mock's output), and green qa_smoke.

## 7. Kickoff
Roster: 06 AIBehaviorDirector (extraction W1), 11 (verify + DoD W2), 03 (consult). Order: 06 W1 → PM gate (suite + digest + qa_smoke) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, behavior-preserving, keep wrapper names + MockProvider's import path, TYPE_CHECKING-only import; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: the AI behavior splits (basic_ai/context_builder/direct_prompt_validator/bounty_pursuit/exploration) + ai/vocab.py + TaskRouter (rest of Round D); the BIG presentation splits (hud/ursina_renderer body/ursina_app); Move 9; world.py; config package; clusters 3/4; Round E audit; zombie purge.
