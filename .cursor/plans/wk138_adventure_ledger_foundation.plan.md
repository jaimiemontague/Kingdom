# WK138 Adventure Ledger Foundation

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-14  
**Roadmap parent:** `.cursor/plans/future_hero_quest_boss_deepening.plan.md`  
**Sprint status:** Kicked off / implementation delegated  

## Mission

Build the first playable multi-phase quest foundation for Kingdom without touching boss phases yet.

The player-facing outcome is simple: a hero should be able to accept a named adventure chain, progress through multiple clear phases, and leave the player with an understandable mini-story instead of a one-objective errand.

The implementation outcome is more important than content volume: create the reusable adventure ledger/state-machine layer that later sprints can use for named bosses, rescue/revenge hooks, dragon hunts, and elite enemies.

## Vision

Kingdom should preserve Majesty-style indirect control. The player funds opportunities and improves the kingdom; heroes decide whether they are brave, prepared, greedy, or cautious enough to attempt them.

In this sprint, the quest should feel like a small expedition:

1. The hero learns or scouts a location.
2. The hero obtains a concrete relic/item/fact from that location.
3. The hero returns or delivers it for reward and story memory.

No fake narrative is allowed. If the UI says a relic exists, the sim must have a real quest fact/item/state for it. If the board says phase 2 is active, there must be explicit phase state proving that.

## Current Baseline

The current game already has:

- Herald's Post / Quest-Giver NPC flow.
- One-shot quest types: raid lair, slay enemy type, find POI, explore far.
- Item registry, inventory, loot, reward escrow, quest UI, and LLM accept/decline behavior.
- POIs including Ancient Ruins, Shrine-like destinations, Dragon Cave, Bandit Fortress, Demon Portal, and others.
- A WK137 worktree with Goblin Warchief / initial wave work that must not be reverted.

The current game does not yet have:

- A chain state machine.
- Explicit phase history.
- Phase timeline UI.
- Long-lived hero commitment to a multi-phase adventure.
- Prompt context for active chain phase facts.
- Boss phase mechanics. Bosses are intentionally out of scope for WK138.

## In Scope

- Add a reusable `QuestChainSystem` or equivalent existing-pattern system.
- Add content definitions for one chain: **Relic of the Old Shrine**.
- Implement three phase types:
  - `scout_location`
  - `collect_item`
  - `deliver_item`
- Register and snapshot active chain state so AI/UI can read it.
- Add structured prompt/context facts so the LLM can discuss only authoritative chain state.
- Teach hero AI to continue a chain across phases instead of treating each phase as unrelated.
- Update quest board/HUD so a player can see completed/current/upcoming phases.
- Add deterministic tests and screenshot verification.

## Out Of Scope

- Named boss phases.
- Elite affixes.
- Rescue/revenge branches.
- Dragon hunt content.
- Multi-hero party formation.
- Broad quest-system rewrites.
- New assets unless a placeholder visual is unreadable.

## Definition Of Done

WK138 is done only when all of these are true:

- A deterministic test can create **Relic of the Old Shrine**, assign/accept it, complete all three phases, and verify completion/reward/history.
- The no-chain/default path remains behaviorally unchanged and the WK67 AI boundary digest remains byte-identical.
- AI prompt/context snapshots include active chain id/name/current phase/objective/history when a chain exists, and include no extra chain data when none exists.
- A hero with an active chain has a stable reason to continue the next phase, while still being allowed to retreat for hard survival rules.
- The quest board/HUD shows a three-phase timeline with completed/current/upcoming state.
- Screenshot capture proves the quest chain UI is readable at 1920x1080.
- `python tools/qa_smoke.py --quick` passes.
- Each active worker updates their own agent log with files touched, commands, evidence, blockers, and follow-ups.

## Integration Order

1. Agent 03 creates/readies the architecture contract: empty default snapshot fields, events/DTOs, sim registration hooks if needed.
2. Agent 05 implements the gameplay state machine and content chain using Agent 03's contract or existing safe extension points.
3. Agent 06 wires AI/prompt behavior once chain facts exist.
4. Agent 08 wires the UI timeline once the read model exists.
5. Agent 11 verifies the integrated system, adds missing tests/scenario coverage, runs gates, and reports defects.

Agents may work in parallel only where their write sets do not collide. They must not revert the WK137 worktree.

## Worker Model

Use **gpt-5.4-mini with xhigh reasoning effort** for every WK138 subagent, per Jaimie's instruction.

## Commands Required By The Sprint

From repo root in Windows PowerShell:

```powershell
python -m pytest tests/test_wk138_quest_chain_core.py -q
python -m pytest tests/test_wk138_quest_chain_ai_view.py -q
python -m pytest tests/test_wk138_quest_chain_ai_policy.py -q
python -m pytest tests/test_wk138_quest_chain_ui.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

Screenshot loop:

```powershell
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk138_quest_chain_ui_panels --size 1920x1080 --ticks 480
```

If `ui_panels` cannot show an active chain, Agent 11 should create or request the smallest deterministic scenario needed, then run:

```powershell
python tools/capture_screenshots.py --scenario quest_chain_foundation --seed 3 --out docs/screenshots/wk138_quest_chain_foundation --size 1920x1080 --ticks 900
```

## Agent 03 Assignment

Task: Add/readify the sim/view contracts needed for multi-phase quest chains without changing behavior when no quest chains exist.

Scope:
- In scope: primitive DTO/view fields, event names/payload contracts, system registration in sim update cadence if needed, snapshot/AiGameView exposure for active chain facts.
- Out of scope: phase completion rules, reward balance, AI decision policy, UI rendering.

Files you MAY edit:
- `game/sim/**`
- `game/sim_engine.py`
- `game/events.py` if event definitions live there
- `tests/test_wk138_quest_chain_ai_view.py`
- `tests/test_wk138_quest_chain_contract.py`
- your own Agent 03 log

Files you MUST NOT edit:
- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `assets/**`
- `config.py` unless PM explicitly expands scope

Implementation guidance:
- Add empty-default chain snapshot fields as tuples/lists so no-chain startup stays unchanged.
- Use primitive snapshots only: chain id, name, phase id/title, objective type, target id/name/position, status, assigned hero id, history summaries.
- Do not expose mutable live objects to AI/UI.
- If registering a new system, call it from the existing sim cadence and make its empty update path a fast early return.
- Events should include stable ids and human-readable names when possible.

Acceptance:
- Existing startup with no chains has empty active-chain view fields.
- WK67 digest remains byte-identical.
- Import order does not create cycles.
- Tests prove the DTO/view shape is available to AI/UI without requiring live mutable object access.

Commands:
```powershell
python -m pytest tests/test_wk138_quest_chain_ai_view.py tests/test_wk138_quest_chain_contract.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

## Agent 05 Assignment

Task: Build the gameplay state machine for one three-phase quest chain while preserving deterministic empty-path behavior.

Scope:
- In scope: `QuestChainSystem`, phase definitions/instances, phase detectors for `scout_location`, `collect_item`, `deliver_item`, one chain definition named `Relic of the Old Shrine`, reward/history cleanup, focused gameplay tests.
- Out of scope: bosses, elite affixes, LLM wording, UI panels, renderer work, broad quest-system replacement.

Files you MAY edit:
- `game/systems/**`
- `game/entities/**`
- `game/content/**` if content registries already live there or this sprint creates one
- `tests/test_wk138_quest_chain_core.py`
- `tests/test_wk138_quest_chain_cleanup.py`
- your own Agent 05 log

Files you MUST NOT edit:
- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `tools/**`
- `assets/**`

Implementation guidance:
- Prefer adding a layered system that coexists with the existing one-shot quest system.
- Keep content data declarative. Suggested fields: `chain_type`, `display_name`, `difficulty_tier`, `phases`, `reward_profile`, `tags`.
- Runtime instances should store stable ids and primitive facts, not live object refs.
- Phase history records should be small dictionaries such as `{"event": "phase_completed", "phase_id": "collect_relic", "hero_id": 12, "time_ms": 12345}`.
- `QuestChainSystem.update` must early-return when no chains are offered/active.
- Use sim time and existing deterministic RNG patterns. Do not introduce wall-clock time or global `random`.
- If a real item object is too risky for this slice, represent the relic as a quest fact first, but leave a clear path to item integration. The UI/prompt must not claim more than the sim stores.

Acceptance:
- A deterministic test completes all three phases in order and records phase history.
- Reward/completion cleanup leaves no dangling active phase.
- Empty/default path is digest-stable.
- Failure/abandon cleanup has at least a minimal test, even if richer failure branches wait for later sprints.

Commands:
```powershell
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk138_quest_chain_cleanup.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

## Agent 06 Assignment

Task: Teach hero AI and prompt context to understand active quest chains without letting the LLM invent authoritative state.

Scope:
- In scope: AI scoring for accepting/continuing a chain phase, hard survival retreat gate, prompt/context facts for current phase/history/objective, mock-provider tests.
- Out of scope: gameplay phase completion, UI rendering, boss behavior.

Files you MAY edit:
- `ai/**`
- `tests/test_wk138_quest_chain_ai_policy.py`
- `tests/test_wk138_quest_prompt_context.py`
- your own Agent 06 log

Files you MUST NOT edit:
- `game/systems/**`
- `game/entities/**`
- `game/ui/**`
- `game/graphics/**`
- `config.py` unless PM explicitly expands scope

Implementation guidance:
- Prompt data must be structured and bounded: chain id/name, current phase, objective, known target, reward/stakes, phase history.
- Add no authoritative facts in prose that are not backed by the view/sim snapshot.
- Early-return before any AI RNG draw when there are no eligible quest chains.
- LLM choices should be bounded verbs such as `accept_chain`, `decline_chain`, `continue_phase`, `retreat_to_heal`.
- Hard survival rules should precede LLM flavor. Low health/no supplies/high danger can force retreat.
- Use mock providers only. No network calls in tests.

Acceptance:
- Prompt snapshot with active chain includes current phase and history.
- Prompt snapshot with no chain is unchanged or proves no chain facts are injected.
- Deterministic mock accept/continue/retreat maps to expected hero intent/state.
- WK67 digest remains byte-identical.

Commands:
```powershell
python -m pytest tests/test_wk138_quest_chain_ai_policy.py tests/test_wk138_quest_prompt_context.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

## Agent 08 Assignment

Task: Make active multi-phase quests readable in the existing HUD/quest board.

Scope:
- In scope: phase timeline, current objective text, assigned hero/reward/status display, readable completion/failure messages, screenshot loop.
- Out of scope: gameplay state mutation, LLM policy, boss bars, VFX/audio.

Files you MAY edit:
- `game/ui/**`
- `tests/test_wk138_quest_chain_ui.py`
- screenshot outputs under `docs/screenshots/wk138_*`
- your own Agent 08 log

Files you MUST NOT edit:
- `game/systems/**`
- `ai/**`
- `game/graphics/**`
- `assets/**`
- `config.py` unless PM explicitly expands scope

Implementation guidance:
- Use the existing HUD/quest-board visual language. This is an operational sim UI, not a landing page.
- The player must be able to see completed/current/upcoming phases at a glance.
- Long quest names and phase names must wrap/truncate without overlap at 1920x1080 and smaller supported screenshots if feasible.
- Follow existing dirty-gated panel patterns; avoid per-frame surface churn.

Acceptance:
- UI test covers at least completed/current/upcoming phase states.
- Screenshot capture shows the three-phase chain board clearly.
- Latest inspected screenshot has no text overlap, hidden controls, or incoherent toast stacking.

Commands:
```powershell
python -m pytest tests/test_wk138_quest_chain_ui.py -q
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk138_quest_chain_ui_panels --size 1920x1080 --ticks 480
python tools/qa_smoke.py --quick
```

## Agent 11 Assignment

Task: Verify WK138 end to end, harden missing tests/scenarios, and provide the final gate report.

Scope:
- In scope: deterministic positive/cleanup tests, AI boundary digest, `qa_smoke`, screenshot capture/inspection, owner recommendations for defects.
- Out of scope: production gameplay fixes unless PM sends a follow-up fix prompt.

Files you MAY edit:
- `tests/**`
- deterministic screenshot/scenario files only if existing ownership allows; otherwise file a request to Agent 12/PM
- `docs/screenshots/wk138_*`
- your own Agent 11 log

Files you MUST NOT edit:
- production game code unless PM explicitly assigns a QA-owned fix
- `assets/**`

Implementation guidance:
- Every new mechanic needs a deterministic positive test and at least one cleanup/no-op guard.
- Include a no-chain digest guard.
- Screenshots must be inspected, not just generated. If the latest PNG does not show the active chain UI, verification failed.
- Report failures with owner, exact repro command, expected, actual, and suggested next round.

Acceptance:
- Final report states PASS/FAIL for quest chain core, AI view, AI policy, UI, screenshot, WK67 digest, and qa_smoke.
- Any failure has a clear owner and next prompt recommendation.

Commands:
```powershell
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk138_quest_chain_cleanup.py -q
python -m pytest tests/test_wk138_quest_chain_ai_view.py tests/test_wk138_quest_chain_ai_policy.py tests/test_wk138_quest_prompt_context.py -q
python -m pytest tests/test_wk138_quest_chain_ui.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk138_quest_chain_ui_panels --size 1920x1080 --ticks 480
```

## PM Review Checklist

- Read each active agent log.
- Confirm no agent touched files outside their lane without reporting it.
- Confirm no worker reverted WK137 changes.
- Run or inspect final command evidence.
- Inspect latest screenshots personally if UI changed.
- If gates fail, send targeted follow-up only to the owning agent.
- If gates pass, commit and push WK138 before planning WK139 Boss Encounter Core + Elite Affixes.
