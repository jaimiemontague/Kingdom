# WK110 Round B — ai/vocab.py: consolidate the scattered AI action/intent vocabulary

**Sprint key:** `wk110_round_b_ai_vocab`
**Plan author:** Agent 01 (Executive Producer / PM)
**Predecessor:** WK109 (`e3212e2`, fog-overlay finale — the #1 god-file fully decomposed). FIRST non-render headless slice of the marathon.
**Verification class:** **fully headless** (NO deferred screenshots) — pytest + determinism_guard + WK67 keystone digest + qa_smoke. This is a clean break from the ursina render slices.

---

## 0. SUMMARY

The AI tool-action / direct-intent vocabulary is defined in 6+ scattered places that have begun to drift (audit cluster "AI tool-action vocabulary", `ai-core/medium/stringly_typed`). Consolidate the canonical strings into a new LEAF module `ai/vocab.py` as `ToolAction(str, Enum)`, `DirectIntent(str, Enum)`, and place-grouping `frozenset`s. The existing modules then DERIVE their public collections from the enums and **re-export the exact same names with byte-identical values**, so (a) the WK67 keystone digest stays byte-identical *by construction*, and (b) NO caller or test needs to change.

**CRITICAL INVARIANTS:**
1. **WK67 digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` MUST stay byte-identical.** The decision path hashes hero state every tick; the vocabulary feeds validation/membership checks. Because `class ToolAction(str, Enum)` makes `ToolAction.MOVE_TO == "move_to"` and `ToolAction.MOVE_TO.value == "move_to"`, every membership test and string comparison behaves identically. This is provable: run the digest test before and after.
2. **Re-export legacy names with identical type/members/ORDER.** Tests + callers import `VALID_ACTIONS`, `TOOL_ACTIONS`, `SUPPORTED_DIRECT_INTENTS`, `DEFERRED_COMBAT_INTENTS` BY NAME from their current modules — those names MUST remain importable from those modules, with the same collection type and (where the collection is ordered / iterated for prompt text) the same iteration order, so prompt strings are byte-identical too.
3. **`ai/vocab.py` is a LEAF** — it imports ONLY stdlib (`from __future__ import annotations`, `from enum import Enum`). It MUST NOT import anything from `ai.*` or `game.*` (avoids the circular-import hazard the audit flags around `ai/context_builder.py`).
4. **SCOPE OUT TaskRouter** (the `ai/basic_ai.py update_hero` priority-ladder → `ai/task_router.py`). That reorders the live decision flow and is digest-fragile — it is a SEPARATE later sprint (roadmap Move 12). This sprint is vocabulary data ONLY.

---

## 1. CURRENT STATE (grounded — read each before editing)

| File:line | Symbol | Current form | Imported-by (must keep importable) |
|---|---|---|---|
| `ai/prompt_templates.py:5` | `VALID_ACTIONS` | collection of action strings (incl. `move_to`; may include `accept_bounty`) | tests `test_wk65_ai_characterization.py` etc. |
| `ai/prompt_templates.py:16` | `TOOL_ACTIONS` | collection: `leave_building, move_to, fight, retreat, buy_item, use_potion, explore` | `ai/direct_prompt_validator.py:12` |
| `ai/direct_prompt_validator.py:15` | `SUPPORTED_DIRECT_INTENTS` | collection of intent strings | `ai/prompt_packs.py:10`, `tests/test_wk50_phase2b_direct_prompt_contracts.py:9`, `tests/test_wk65_ai_characterization.py` |
| `ai/direct_prompt_validator.py:29` | `DEFERRED_COMBAT_INTENTS` | collection | `tests/test_wk50_phase2b_direct_prompt_contracts.py:8`, ref `test_wk65...:484` |
| `ai/direct_prompt_validator.py:38` | `_PLACE_TYPE_TO_MOVE_TARGET` | dict/mapping (module-private) | read at `direct_prompt_validator.py:77` |
| `ai/direct_prompt_validator.py:45` | `_PLAYER_HOME_TYPES` | frozenset (module-private) | read at `direct_prompt_validator.py:79-80` |
| `ai/arrival_handlers.py:123` | inline place tuples | inline | (optional — see §4 scope) |

**Agent 09 MUST read the EXACT current literal values of each of these and preserve them byte-for-byte** (same strings, same membership, same collection type, same order). Do NOT guess — open the files and copy the values.

---

## 2. THE NEW MODULE — `ai/vocab.py`

```python
"""Canonical AI action/intent vocabulary (WK110 consolidation of scattered string contracts).

Single source of truth for the LLM tool-action names, the direct-prompt intent names,
and the place-type groupings that were previously duplicated across prompt_templates.py,
direct_prompt_validator.py, prompt_packs.py, decision_moments.py and arrival_handlers.py.

LEAF MODULE: imports ONLY stdlib. Must NOT import from ai.* or game.* (kept upstream of
the whole ai package to avoid import cycles). Downstream modules derive their existing
public collections (VALID_ACTIONS, TOOL_ACTIONS, SUPPORTED_DIRECT_INTENTS, ...) from these
enums and re-export them under the SAME names with BYTE-IDENTICAL values, so the WK67 AI
decision digest stays byte-identical and no caller/test moves.

``str, Enum`` is deliberate: ``ToolAction.MOVE_TO == "move_to"`` and
``ToolAction.MOVE_TO.value == "move_to"`` are both True, so every existing string
membership/equality check behaves identically.
"""
from __future__ import annotations

from enum import Enum


class ToolAction(str, Enum):
    # values MUST equal the current TOOL_ACTIONS strings, verbatim:
    LEAVE_BUILDING = "leave_building"
    MOVE_TO = "move_to"
    FIGHT = "fight"
    RETREAT = "retreat"
    BUY_ITEM = "buy_item"
    USE_POTION = "use_potion"
    EXPLORE = "explore"
    # (Agent 09: reconcile against the ACTUAL current TOOL_ACTIONS/VALID_ACTIONS literals —
    #  add any member present there, e.g. accept_bounty, with its exact string value.)


class DirectIntent(str, Enum):
    # values MUST equal the current SUPPORTED_DIRECT_INTENTS strings, verbatim (copy from source).
    ...


# place-type groupings (values copied verbatim from the current frozensets/dicts):
# PLAYER_HOME_TYPES = frozenset({...})       # from direct_prompt_validator._PLAYER_HOME_TYPES
# PLACE_TYPE_TO_MOVE_TARGET = {...}          # from direct_prompt_validator._PLACE_TYPE_TO_MOVE_TARGET
# (Agent 09: name these so the validator can import and alias to its existing private names.)
```

---

## 3. RETARGET THE EXISTING MODULES (derive + re-export; keep names + byte-identical values)

The pattern for each: import from `ai.vocab`, then BIND the existing public name to a collection built from the enum that is **equal in type, members, and order** to the original literal.

- `ai/prompt_templates.py`:
  ```python
  from ai.vocab import ToolAction
  # keep the EXACT original type/order. If TOOL_ACTIONS was a tuple in this order, do:
  TOOL_ACTIONS = (ToolAction.LEAVE_BUILDING.value, ToolAction.MOVE_TO.value, ...)  # same order as before
  # VALID_ACTIONS: reproduce its exact original membership/type (it differs slightly from TOOL_ACTIONS —
  # e.g. may add "accept_bounty" / omit "leave_building"); build it explicitly to match the original literal.
  ```
  Match the ORIGINAL collection type exactly (tuple vs set vs frozenset vs list). If unsure whether order matters, preserve it — it is cheap insurance for prompt-text stability.
- `ai/direct_prompt_validator.py`:
  ```python
  from ai.vocab import DirectIntent, PLAYER_HOME_TYPES, PLACE_TYPE_TO_MOVE_TARGET
  SUPPORTED_DIRECT_INTENTS = (...)        # derived from DirectIntent, same type/order as original
  DEFERRED_COMBAT_INTENTS = (...)         # derived, same as original
  _PLAYER_HOME_TYPES = PLAYER_HOME_TYPES  # alias the relocated frozenset to the existing private name
  _PLACE_TYPE_TO_MOVE_TARGET = PLACE_TYPE_TO_MOVE_TARGET
  ```
  The read sites at `:77` and `:79-80` keep using `_PLACE_TYPE_TO_MOVE_TARGET` / `_PLAYER_HOME_TYPES` unchanged (now aliases).

**Do NOT** change any logic, comparison, or control flow in these modules — only the DEFINITION of the constants (now derived from vocab). Keep `TOOL_ACTIONS` importable from `prompt_templates` (validator imports it at `:12`).

---

## 4. SCOPE (what is IN vs OUT this sprint)
- **IN:** create `ai/vocab.py`; retarget `prompt_templates.py` (VALID_ACTIONS, TOOL_ACTIONS) and `direct_prompt_validator.py` (SUPPORTED_DIRECT_INTENTS, DEFERRED_COMBAT_INTENTS, the 2 place groupings).
- **OPTIONAL (only if trivial & byte-identical):** `prompt_packs.py:67` hardcoded action-list string → regenerate from `ToolAction` (ONLY if the regenerated string is byte-identical, else leave). `ai/decision_moments.py:151-264` five inline `allowed_actions` tuples → reference `ToolAction.*.value` (ONLY if byte-identical; otherwise LEAVE for a follow-up — keep blast radius small).
- **OUT (explicitly):** TaskRouter / `ai/basic_ai.py update_hero` rewrite (Move 12, later sprint); any validator control-flow refactor; `arrival_handlers.py` inline tuples (follow-up).

---

## 5. AGENT TASKS

### Agent 06 (AI Behavior Director / LLM) — W1: the consolidation
**Why Agent 06:** this is `ai/` vocabulary, the AI domain. Onboard via `.cursor/rules/` (find the Agent 06 onboarding file; if none, onboard as "AI Behavior Director, owner of `ai/`"). Read this plan + PM hub sprint `wk110_round_b_ai_vocab`.
**Do:** §2 (create `ai/vocab.py` — FIRST read the exact current literals from `prompt_templates.py` + `direct_prompt_validator.py` and copy values verbatim) + §3 (retarget the 2 modules to derive + re-export). Keep `ai/vocab.py` a stdlib-only leaf.
**Self-verify (run ALL; paste output to log):**
- `python -c "import ai.vocab; print('vocab ok')"`
- `python -c "from ai.prompt_templates import VALID_ACTIONS, TOOL_ACTIONS; from ai.direct_prompt_validator import SUPPORTED_DIRECT_INTENTS, DEFERRED_COMBAT_INTENTS; print('reexports ok')"`
- **Byte-identical proof** — BEFORE you start, capture the originals: `git show HEAD:ai/prompt_templates.py` / `HEAD:ai/direct_prompt_validator.py`; AFTER, run a small ad-hoc check that the post-refactor `VALID_ACTIONS`, `TOOL_ACTIONS`, `SUPPORTED_DIRECT_INTENTS`, `DEFERRED_COMBAT_INTENTS`, `_PLAYER_HOME_TYPES`, `_PLACE_TYPE_TO_MOVE_TARGET` are EQUAL (same type, same members, same order for ordered types) to the original literal values. Paste the comparison.
- `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → MUST pass (digest byte-identical).
- `python -m pytest tests/test_wk50_phase2b_direct_prompt_contracts.py tests/test_wk65_ai_characterization.py -q` → must pass (the by-name importers).
- `python -c "import ai.vocab, ast; t=ast.parse(open('ai/vocab.py').read()); import_names=[n.module for n in ast.walk(t) if isinstance(n, ast.ImportFrom)]; print('vocab imports:', import_names)"` → must show ONLY stdlib (`__future__`, `enum`) — no `ai`/`game`.
**DO NOT COMMIT. DO NOT edit tests.** Touch ONLY `ai/vocab.py` (new) + `ai/prompt_templates.py` + `ai/direct_prompt_validator.py` (+ optionally prompt_packs.py/decision_moments.py per §4, ONLY if byte-identical). Update the Agent 06 log, then STOP.

### Agent 11 (QA) — W2: characterization seam test + full DoD
Onboard `.cursor/rules/agent-11-qa-onboarding.mdc`. Read §5–6 + PM hub.
**Do:** create `tests/test_wk110_ai_vocab.py`:
1. **vocab module shape:** `ToolAction`/`DirectIntent` are `str`-Enums; `ToolAction.MOVE_TO == "move_to"` and `.value == "move_to"` (string-enum behavior).
2. **byte-identical-value characterization (the key net):** PIN the original literal values (copy them from `git show HEAD:ai/prompt_templates.py` / `HEAD:ai/direct_prompt_validator.py`) and assert the CURRENT `ai.prompt_templates.VALID_ACTIONS`, `.TOOL_ACTIONS`, `ai.direct_prompt_validator.SUPPORTED_DIRECT_INTENTS`, `.DEFERRED_COMBAT_INTENTS`, `._PLAYER_HOME_TYPES`, `._PLACE_TYPE_TO_MOVE_TARGET` equal those pinned originals (same type + members + order). This guarantees zero drift.
3. **re-export presence:** the by-name imports tests rely on still resolve from the original modules.
4. **leaf guard (AST):** `ai/vocab.py` has NO `import`/`from` of any `ai.*` or `game.*` module (only stdlib).
5. **enum↔collection consistency:** every `ToolAction` value appears in the appropriate derived collection; every `DirectIntent` value in `SUPPORTED_DIRECT_INTENTS`.
**Then run full DoD (§6); paste output. DO NOT COMMIT.** Touch ONLY the new test file. Update agent_11 log.

---

## 6. DEFINITION OF DONE (Agent 11 runs; Agent 01 re-verifies)
1. `python -m pytest -q` → ALL pass, 0 failed (~1316+).
2. `python tools/determinism_guard.py` → clean.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q` → pass, digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` byte-identical. **(Primary safety gate for this slice.)**
4. `python tools/qa_smoke.py --quick` → green.
5. New seam test `tests/test_wk110_ai_vocab.py` passes.
6. `ai/vocab.py` is a stdlib-only leaf (AST guard).
7. **Agent 01 re-verify:** independently re-run the digest test + diff `git show HEAD:` originals' values vs current to confirm byte-identical collections.
8. No screenshots (non-render slice).

---

## 7. COMMIT (Agent 01 only) — scoped add; NEVER `git add -A`; NEVER the 2 root user PNGs.

## 8. FOLLOW-UPS (sequenced)
- **WK111 = WK34 zombie-type purge** (8 building types: gnome_hovel, elven_bungalow, dwarven_settlement, ballista_tower, wizard_tower, fairgrounds, library, royal_gardens — flagged `purge_candidate=True` in `game/content/buildings.py:135-148`). NOT clean deletion: live wiring in `peasant.py:172`, `sim_engine.py:896-900` (building update dispatch), `systems/buffs.py:48,62` (royal_gardens_aura), entity classes (dwellings/defensive/special), renderers, panels, `decision_moments.py:113`, `world_zones.py`. Run as a per-type grep-proven guarded removal BEHIND the WK67 digest; may shift the digest (peasant/buffs feed hero state) → prove or adjust carefully.
- **WK112 = `ai/direct_prompt_validator.py` split** (`validate_direct_prompt_output` L140 → per-intent handler table). Gated by WK67 chat-purity pins; preserve the deferred-combat early-return, critical-HP redirect, and the two obey/defy passes verbatim.
- **Later / RISKY (defer): TaskRouter (Move 12)** and **Move 9 SystemRunner** — both reorder the live decision/update flow; most digest-fragile; land last with extra gating.
- Also pending (small): `world.py:60` `_currently_visible: list`→`set` type fix (latent `.discard()` issue) — prove determinism-neutral. De-slop dead `WATCH_MINIMAP_SIZE` (hud.py).
- NOTE for the record: the audit doc LOC figures are STALE — config registry unified, world.py fog extracted, sim_engine Moves 7-8 done, hero/input/mock_provider splits done, context_builder legacy path deleted. Much of the original audit is already complete.
