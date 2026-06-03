# WK71 Sprint Plan — Round B-2a: hero.py mixin split

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; `hero.py` (1156 LOC) split into focused mixin modules with an MRO-identical `Hero`, behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68 (Round A), WK69 (sim split), WK70 (building registry). **Roadmap:** Round B-2 (god-file splits, presentation/entity).

## 0. TL;DR
`game/entities/hero.py` is the 1152-LOC entity god-file (audit: 7 responsibilities). WK71 extracts three cohesive clusters into **mixin classes** that `Hero` inherits, so the MRO is identical and **every call site / duck-typed caller is unchanged** (audit-tagged [VERIFIED safe]). Pure mechanical move + delete one flagged duplicate (`set_event_bus`/`_event_bus`). No gameplay/render/AI change; **no screenshots**; the WK67 AI-decision digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` MUST stay byte-identical (the 300-tick digest heavily exercises hero rest/economy/intent — a strong guard). PM writes no code.

## 1. Scope
**IN:** split `game/entities/hero.py` into:
- **`hero.py`** (core, ~450 LOC): `HeroState`, `_allocate_fallback_hero_id`, `Hero.__init__`, combat/buffs (`attack`/`defense`/`apply_or_refresh_buff`/`remove_expired_buffs`/`take_damage`/`on_attack_landed`), `is_alive`/`health_percent`/`render_state`, xp/level (`add_xp`/`grant_tile_exploration_xp`/`level_up`), movement (`set_target_position`/`distance_to`/`move_towards`), `update` (the main per-tick method — KEEP on Hero), descent/ascent, `set_event_bus`, `_queue_render_animation`, `heal`, `hunger_urgent`. Hero's class declaration becomes `class Hero(HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin):`.
- **`hero_rest.py`** `HeroRestMixin` (~170): `should_go_home_to_rest`, `start_resting`, `start_resting_at_building`, `update_resting`, `pop_out_of_building`, `can_rest_at_home`, `finish_resting`, `enter_building_briefly`.
- **`hero_economy.py`** `HeroEconomyMixin` (~160): `add_gold`, `transfer_taxes_to_home`, `use_potion`, `_is_at_food_stand`, `buy_meal_at_food_stand`, `_shop_for_tax_deposit`, `buy_item`, `wants_to_shop`, `get_shopping_context`, `increment_career_stat`.
- **`hero_memory.py`** `HeroMemoryMixin` (~150): `record_profile_memory`, `remember_known_place`, `_trim_known_places_if_needed`, `record_decision`, `get_intent_snapshot`, `get_stuck_snapshot`, `_derive_intent`, `_update_intent_and_decision`, `get_context_for_llm`.
- **Delete the duplicate:** there are TWO `set_event_bus` defs (lines ~221 and ~657) and the audit flags a duplicate `_event_bus`/`set_event_bus` init. Keep ONE `set_event_bus`; delete the redundant one. Verify `__init__` doesn't double-init `_event_bus`.

**OUT (deferred):** moving intent/LLM-context to the `ai/` layer (`ai/intent.py` — a boundary change, not a pure split → later); any behavior change; other entity splits (enemy.py); presentation splits (hud/ursina_renderer).

## 2. The pattern (mixins, MRO-identical)
```python
# hero_rest.py
from __future__ import annotations
from typing import TYPE_CHECKING
# ... same leaf imports the moved methods used ...
class HeroRestMixin:
    """WK71: resting behavior extracted from Hero. Mixed into Hero; accesses self.* set in Hero.__init__."""
    def should_go_home_to_rest(self) -> bool:  # EXACT body, unchanged (self.* still resolves)
        ...
```
```python
# hero.py
from game.entities.hero_rest import HeroRestMixin
from game.entities.hero_economy import HeroEconomyMixin
from game.entities.hero_memory import HeroMemoryMixin
class Hero(HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin):
    def __init__(self, ...): ...   # ALL instance attrs stay here (mixins only hold methods)
```
- Mixins hold ONLY methods; **all instance state stays initialized in `Hero.__init__`.**
- Method bodies move VERBATIM (they already use `self.`). No signature/logic change.
- Mixin order: put them BEFORE any base; `Hero` has no other base today, so MRO = [Hero, HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin, object] — methods resolve identically.
- If a mixin method calls another method now in a different mixin (e.g. economy calls `add_gold`), that's fine — all resolve through `self` on the combined class.
- Watch for module-level imports the moved methods need (copy them into the mixin module); use `TYPE_CHECKING` for `Building`/type-only hints; keep lazy/in-function imports as-is.

## 3. Definition of Done
- **A.** `python -m pytest` all pass (baseline **646 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `hero.py` materially smaller (~1156 → ~450-550); 3 new mixin modules exist; `Hero`'s public method surface UNCHANGED (every method still callable as `hero.<name>(...)`); the duplicate `set_event_bus` removed.
- **F.** No import cycle; MRO verified (a test asserts `Hero.__mro__` includes the 3 mixins and all the moved methods resolve on a `Hero` instance).
- **G.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 03):** do the split + delete the duplicate. Verify the digest after the move + full suite. (Single agent, single file → one wave.)
- **W2 (Agent 11):** add `tests/test_wk71_hero_mixin_split.py` (assert MRO + each moved method resolves + the public surface is intact) + run the full DoD gate.
- Agent 05 (consult): hero-behavior semantics if the digest drifts.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A moved method references a name only imported at hero.py top → NameError | Med | copy each method's imports into its mixin module; full suite catches it |
| Deleting the wrong `set_event_bus` / breaking `_event_bus` init | Low-Med | diff the two defs first; keep the one `__init__`/callers rely on; digest+suite guard |
| MRO/attribute resolution change | Low | mixins hold only methods; all state in Hero.__init__; W2 MRO test |
| Digest drift | Low | verify after the move; if it drifts, a method body was altered — revert+redo |

## 6. Success
`hero.py` ~600 LOC lighter across 3 mixins, `Hero` behaves identically — proven by 646+ green tests, clean determinism guard, unchanged `b73961…` digest, and the MRO test.

## 7. Kickoff
Roster: 03 (split), 11 (MRO test + DoD), 05 (consult). Order: 03 W1 → PM gate (digest+suite) → 11 W2 → PM final → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; behavior-preserving, digest unchanged; NO screenshots; update own log; DO NOT COMMIT.
Follow-ups: `ai/intent.py` boundary move; `enemy.py` ENEMY_STATS table split; presentation splits (hud/ursina_renderer/engine/input_handler); Move 9; zombie-type purge.
