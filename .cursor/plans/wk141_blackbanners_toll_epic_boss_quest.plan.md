# WK141 Blackbanner's Toll - First Epic Boss Quest

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-15  
**Previous sprint:** WK140 Hero Daily Life AI, committed/pushed as `80daf2d`  
**Roadmap source:** `.cursor/plans/future_hero_quest_boss_deepening.plan.md` Sprint C  
**Sprint status:** Planned / ready for implementation delegation  

## Mission

Connect the WK138 Adventure Ledger and WK139 Boss Encounter Core into the first memorable multi-phase boss quest:

**Blackbanner's Toll**: a bandit-fortress adventure where a hero scouts the fortress, intercepts a gold-thief elite, assaults the gate, defeats the Bandit Lord **Rusk Blackbanner**, and claims a reward.

The player-facing goal is that the game finally produces a small fantasy story, not just a contract. A hero should appear to discover a threat, pursue a lead, fight through a named faction, and face a boss climax with readable phase state.

## Current Capability Baseline

Already shipped:

- WK138: `QuestChainSystem`, quest-chain read models, AI policy/context, Adventure Ledger UI, and the three-phase "Relic of the Old Shrine" foundation.
- WK139: `BossEncounterSystem`, boss/elite read models, Warchief phases/telegraph, elite affixes, compact boss UI, visual markers, screenshot scenario coverage.
- WK140: stronger hero daily-life AI, bounty stickiness, and conviction/anti-loop logic.

WK141 should build on these systems. Do not replace them.

## Product Design

Blackbanner's Toll should feel like a short siege:

1. **Scout Fortress**
   - The chain points a hero toward a Bandit Fortress or fallback bandit camp/lair.
   - Completing the scout phase reveals Rusk Blackbanner and his toll operation.

2. **Intercept Gold Thief Elite**
   - Spawn or designate one deterministic elite bandit: "Blackbanner Toll-Taker" or similar.
   - The elite carries/stashes stolen gold as a primitive quest fact.
   - Defeating/intercepting the elite completes the phase and weakens or unlocks the gate assault.

3. **Assault Gate**
   - The hero reaches the fortress/gate area and clears a small guard group or survives/holds position.
   - This phase should be deterministic and cheap; avoid a whole new siege subsystem.

4. **Defeat Rusk Blackbanner**
   - Rusk uses the existing boss encounter infrastructure.
   - He should have at least two readable phases or one new Bandit-Lord-specific ability layered onto the WK139 boss core.
   - Suggested flavor: `Toll Banner` buffs guards in phase 1; `Smoke Retreat` or `Last Stand` triggers below 50 percent HP.

5. **Claim Reward**
   - MVP reward: gold payout plus an Adventure Ledger completion record.
   - If safe and already supported, add a primitive "outpost vision" or "armory loot" fact, but do not block the sprint on a new outpost system.

## Non-Negotiables

- Preserve empty/default determinism: no active Blackbanner chain must mean no RNG draws and no WK67 digest drift.
- Do not create a new quest system. Extend WK138 chain content/phase handlers.
- Do not create a new boss system. Extend WK139 boss content/encounter mechanics.
- The LLM can choose accept/continue/retreat from structured facts only. It cannot invent the fortress, stolen gold, boss death, or reward.
- Keep all state primitive/read-only in views and snapshots.
- Use existing elite-affix machinery where possible.
- No new art/audio unless a current marker is unreadable. Use existing bandit/boss visual vocabulary.
- Avoid broad balance work. Tune enough for deterministic tests and a short playtest loop.

## Definition Of Done

WK141 is done only when all are true:

- A deterministic test can offer/activate **Blackbanner's Toll** and complete phases in order: scout -> intercept elite -> assault gate -> slay boss -> reward/complete.
- Rusk Blackbanner appears as a named boss encounter using WK139 infrastructure, not just a renamed normal enemy.
- The gold-thief elite is deterministic and linked to the chain phase.
- Hero AI sees the active chain facts and treats the current phase as a committed adventure, while still retreating for hard survival gates.
- Adventure Ledger / quest UI shows the chain name, current phase, completed phases, boss identity when revealed, and completion.
- Boss UI/visuals show Rusk's name/phase/elite or boss marker clearly enough for the player to read the climax.
- Empty/default path keeps WK67 stable.
- `python tools/qa_smoke.py --quick` passes.
- UI/visual changes have screenshot evidence or a documented reason why existing WK139 screenshots are sufficient.

## Agent 03 - TechnicalDirector Architecture

Task: Wire any missing sim/view contracts for Blackbanner's Toll without changing empty-default behavior.

Files you MAY edit:

- `game/sim/**`
- `game/sim_engine.py`
- `game/events.py` if event definitions live there
- `tests/test_wk141_blackbanner_contract.py`
- `tests/test_wk141_blackbanner_ai_view.py`
- `.cursor/plans/agent_logs/agent_03_TechnicalDirector_Architecture.json`

Files you MUST NOT edit:

- `ai/**`
- `game/systems/**` except minimal registration if PM/Agent05 proves it belongs there
- `game/ui/**`
- `game/graphics/**`
- `assets/**`
- `tools/**`

Implementation guidance:

- First inspect WK138/WK139 contracts and reuse existing snapshot/read-model shapes.
- Add only missing primitive facts for a chain-linked boss/elite: chain id, phase id, boss id/name, elite id/name, target positions, status strings.
- Empty-default startup must expose empty tuples/None fields and must not mutate or consume RNG.
- If the current contracts already support everything, do not invent fields; add tests proving Blackbanner facts flow through.

Acceptance:

- AI/view tests can see Blackbanner chain phase facts and revealed Rusk boss facts without live object refs.
- No-chain/no-boss path remains empty/default.
- WK67 passes.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_contract.py tests/test_wk141_blackbanner_ai_view.py -q
python -m pytest tests/test_wk138_quest_chain_ai_view.py tests/test_wk139_boss_ai_view.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_03_TechnicalDirector_Architecture.json
```

## Agent 05 - GameplaySystemsDesigner

Task: Implement the Blackbanner's Toll quest-chain content, phase detectors, Rusk boss encounter hook, elite phase, and reward completion.

Files you MAY edit:

- `game/systems/**`
- `game/entities/**`
- `game/content/**`
- `config.py` only for clearly named tuning constants if unavoidable
- `tests/test_wk141_blackbanner_chain.py`
- `tests/test_wk141_blackbanner_boss.py`
- `tests/test_wk141_blackbanner_elite.py`
- `.cursor/plans/agent_logs/agent_05_GameplaySystemsDesigner.json`

Files you MUST NOT edit:

- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `tools/**`
- `assets/**`

Implementation guidance:

- Prefer declarative content such as `game/content/quest_chains.py` and `game/content/bosses.py`.
- Reuse WK138 `QuestChainSystem` and WK139 `BossEncounterSystem`.
- Add one chain definition with stable id such as `blackbanners_toll`.
- Suggested phase ids: `scout_fortress`, `intercept_toll_taker`, `assault_gate`, `slay_blackbanner`, `claim_reward`.
- Use existing POI/lair/building concepts for the fortress target. If Bandit Fortress is not available in a fixture, use a deterministic fallback bandit camp/lair but keep the player-facing chain text as fortress/toll.
- The toll-taker elite should be generated/designated once per chain, not every tick.
- Rusk should be a boss encounter with at least two phase states or one special ability beyond stats.
- Completion should clean active phase state and add a history record.

Acceptance:

- Focused tests complete the whole chain in order and assert phase history.
- Elite phase is deterministic with same seed.
- Boss phase/ability state changes are deterministic.
- Reward/completion cleanup leaves no dangling active phase, elite, or boss reference.
- Empty/default WK67 path remains stable.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_chain.py tests/test_wk141_blackbanner_boss.py tests/test_wk141_blackbanner_elite.py -q
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk139_boss_encounters.py tests/test_wk139_elite_affixes.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_05_GameplaySystemsDesigner.json
```

## Agent 06 - AIBehaviorDirector LLM

Task: Teach hero AI and prompt context to understand Blackbanner's Toll phases, Rusk risk, elite interception, and press-on/retreat decisions.

Files you MAY edit:

- `ai/**`
- `tests/test_wk141_blackbanner_ai_policy.py`
- `tests/test_wk141_blackbanner_prompt_context.py`
- `.cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json`

Files you MUST NOT edit:

- `game/systems/**`
- `game/entities/**`
- `game/ui/**`
- `game/graphics/**`
- `tools/**`
- `assets/**`
- `config.py`

Implementation guidance:

- Reuse WK138 quest-chain commitment and WK140 conviction behavior.
- Active Blackbanner phases should outrank ambient daily-life motives.
- Survival gates still win: badly wounded/no supplies heroes can retreat.
- Prompt context must be structured: chain name, phase, objective, known boss name, elite target, reward/stakes, recent phase history.
- LLM/mock actions should remain bounded: accept_chain, continue_phase, retreat_to_heal, prepare_supplies, decline_chain.
- No network calls in tests.

Acceptance:

- AI policy tests show a suitable hero accepts/continues the chain and a badly wounded hero retreats/prepares.
- Prompt snapshot includes Blackbanner/Rusk/elite facts once revealed.
- No-chain path remains unchanged and WK67 passes.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_ai_policy.py tests/test_wk141_blackbanner_prompt_context.py -q
python -m pytest tests/test_wk138_quest_chain_ai_policy.py tests/test_wk140_hero_daily_life_ai.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json
```

## Agent 08 - UX UI Director

Task: Make Blackbanner's Toll readable in the Adventure Ledger and boss UI using existing UI patterns.

Files you MAY edit:

- `game/ui/**`
- `tests/test_wk141_blackbanner_ui.py`
- `docs/screenshots/wk141_*`
- `.cursor/plans/agent_logs/agent_08_UX_UI_Director.json`

Files you MUST NOT edit:

- `game/systems/**`
- `ai/**`
- `game/graphics/**`
- `tools/**`
- `assets/**`
- `config.py`

Implementation guidance:

- Use the existing WK138 Adventure Ledger phase timeline and WK139 compact boss UI.
- Show: chain name, active phase, completed phase markers, assigned hero, revealed boss name, and reward/completion state.
- Keep the interface operational and compact; no landing-page style panels.
- Text must not overlap at 1920x1080 or smaller supported captures.

Acceptance:

- UI test proves Blackbanner phases render as current/completed/upcoming.
- Boss UI shows Rusk clearly when encounter is active.
- Screenshot capture is inspected and latest image shows the chain state.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_ui.py tests/test_wk138_quest_chain_ui.py tests/test_wk139_boss_ui.py -q
python tools/capture_screenshots.py --scenario quest_chain_foundation --seed 3 --out docs/screenshots/wk141_blackbanner_ui --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_08_UX_UI_Director.json
```

## Agent 09 - ArtDirector Pixel Animation VFX

Task: Verify or add readable Rusk/elite/boss-phase visual markers using WK139 visual language.

Files you MAY edit:

- `game/graphics/**`
- `tests/test_wk141_blackbanner_visuals.py`
- `docs/screenshots/wk141_*`
- `.cursor/plans/agent_logs/agent_09_ArtDirector_Pixel_Animation_VFX.json`

Files you MUST NOT edit:

- `game/systems/**`
- `ai/**`
- `game/ui/**` unless PM coordinates with Agent 08
- `tools/**`
- `assets/**`
- `config.py`

Implementation guidance:

- First inspect WK139 boss/elite visuals. If Rusk and the toll-taker are already readable through existing markers, add/adjust tests and report no production visual change.
- If a change is needed, keep it tiny: marker tint, label, phase tell, or telegraph reuse.
- Do not add per-frame allocations or broad renderer changes.

Acceptance:

- Rusk and the toll-taker are distinguishable in tests/screenshot.
- Any phase/ability tell appears before effect and clears after.
- Screenshot is inspected if visuals changed.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_visuals.py tests/test_wk139_boss_visuals.py tests/test_wk139_elite_visuals.py -q
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/wk141_blackbanner_boss --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_09_ArtDirector_Pixel_Animation_VFX.json
```

## Agent 11 - QA TestEngineering Lead

Task: Verify the complete Blackbanner's Toll adventure loop.

Files you MAY edit:

- `tests/**`
- `docs/screenshots/wk141_*`
- `.cursor/plans/agent_logs/agent_11_QA_TestEngineering_Lead.json`

Files you MUST NOT edit:

- production code unless PM sends a separate fix prompt
- `assets/**`

Verification requirements:

- Run all WK141 focused tests.
- Run WK138/WK139/WK140 regression tests relevant to chain/boss/AI.
- Run WK67 and qa_smoke.
- Verify screenshot evidence if UI/visuals changed.
- Report whether the chain feels like a connected adventure by evidence: phase history, visible boss, elite phase, reward cleanup.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_contract.py tests/test_wk141_blackbanner_ai_view.py tests/test_wk141_blackbanner_chain.py tests/test_wk141_blackbanner_boss.py tests/test_wk141_blackbanner_elite.py -q
python -m pytest tests/test_wk141_blackbanner_ai_policy.py tests/test_wk141_blackbanner_prompt_context.py tests/test_wk141_blackbanner_ui.py tests/test_wk141_blackbanner_visuals.py -q
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk139_boss_encounters.py tests/test_wk140_hero_daily_life_ai.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_11_QA_TestEngineering_Lead.json
```

## Integration Order

1. **Wave 1 parallel:** Agents 03 and 05.
   - 03 ensures contracts/views are sufficient.
   - 05 implements core chain/boss/elite gameplay.
2. **PM gate:** targeted 03/05 tests, WK67, smoke if feasible.
3. **Wave 2 parallel:** Agents 06, 08, 09.
   - 06 AI/prompt.
   - 08 UI.
   - 09 visuals/readability.
4. **Wave 3:** Agent 11 verification.
5. **PM close:** final gates, screenshots if applicable, commit/push.

## PM Notes

- If Agent 03 reports no contract changes are needed, do not force architecture churn.
- If Agent 09 reports existing WK139 visual language is enough, do not force art churn.
- If Agent 08 needs a screenshot scenario that does not exist, ask Agent 11 if existing `quest_chain_foundation` or `boss_encounter_showcase` can cover it before involving Agent 12.
- Keep this sprint focused on Bandit Lord / Blackbanner. Dragon Hunt remains Sprint E.
