# WK139 Boss Encounter Core + Elite Affixes

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-14  
**Roadmap parent:** `.cursor/plans/future_hero_quest_boss_deepening.plan.md`  
**Previous sprint:** WK138 Adventure Ledger Foundation, committed/pushed as `f77a950`  
**Sprint status:** Kicked off / implementation delegated  

## Mission

Create the reusable foundation for named boss encounters and elite enemies.

The player-facing goal is that the early Goblin Warchief stops feeling like only a larger goblin with a name. He should become the first true boss encounter: visible identity, at least two phases, one readable special ability, one reinforcement/rally moment, deterministic memory facts, and a compact boss status UI.

The systems goal is to build the boss/elite machinery that later sprints can reuse for Bandit Lord, Bone King, Dragon, Demon Portal, and boss-ending quest chains.

## Vision

Bosses in Kingdom should be memorable because they change the story:

- A named boss has a visible identity and current phase.
- A dangerous ability has a tell before the consequence lands.
- A boss can remember killing or being defeated by a hero.
- An elite enemy is not just more HP; it has a readable modifier and a tactical reason to prioritize it.
- All of this remains deterministic and cheap when no boss encounter is active.

Use the Goblin Warchief because WK137 already shipped his stats, render scale, name label, atlas coverage, and early wave. Do not build the Dragon yet.

## Current Baseline

Already available:

- `goblin_warchief` enemy type with boss stats/name/scale.
- Initial Goblin Warband wave at 30 sim-sec.
- Boss-sized rendering support for warchief, bandit lord, demon, and dragon.
- QuestChainSystem and read-model patterns from WK138.
- Existing UI/HUD patterns and screenshot tools.

Missing:

- Reusable boss encounter data model.
- Boss phase runtime.
- Boss ability cooldown/telegraph event path.
- Elite affix selection and readable elite facts.
- Boss/elite read-model facts for UI/render/AI.
- Boss status UI.
- Deterministic tests for boss phases, elite affixes, memory, visuals, and perf.

## In Scope

- Add boss content definitions for one true boss: **The Goblin Warchief**.
- Add `BossEncounterSystem` or equivalent existing-pattern system.
- Add data shapes equivalent to:
  - `BossDef`
  - `BossPhaseDef`
  - `BossAbilityDef`
  - `EliteAffixDef`
- Implement a Warchief encounter with at least two phases:
  - **War Banner:** nearby goblins receive a small deterministic attack/courage bonus while the warchief is alive and in this phase.
  - **Rally:** at or below a configured HP threshold, the warchief emits a telegraph event and calls a small capped reinforcement if goblin count is low.
- Implement at least three elite affixes:
  - `banner_bearer`
  - `ironhide`
  - `frenzied`
- Roll elite affixes deterministically only when enemies are created/spawned, never every tick.
- Expose primitive boss/elite snapshots for UI/render/AI.
- Add compact boss status UI and visual markers/telegraph proof.
- Add deterministic tests and screenshot verification.

## Out Of Scope

- Dragon fight.
- Bandit Lord quest chain.
- Rescue/revenge dynamic situations.
- New models/assets unless existing visuals are unreadable.
- Audio unless Agent 14 is explicitly added later.
- Random roaming bosses.
- Full Nemesis-style boss evolution.

## Definition Of Done

WK139 is done only when all of these are true:

- A deterministic test can create or activate The Goblin Warchief encounter, tick it across phase thresholds, and verify phase state.
- The Rally ability telegraphs before reinforcement/spawn effect and respects cooldown/caps.
- Elite affixes are deterministic for a fixed seed and do not roll on every tick.
- At least three elite affixes have stat/effect data, readable names, and snapshot/UI/render facts.
- Boss memory records at least defeated-by and killed-hero facts when the corresponding events are simulated.
- No-boss/no-elite startup remains behaviorally unchanged and WK67 digest remains byte-identical.
- Boss/elite snapshots expose primitive/read-only facts only.
- UI shows a compact boss status with boss name, phase, HP status, and ability tell/status without hiding core controls.
- Visual screenshot proof shows boss marker/status and at least one elite marker or ability telegraph.
- `python tools/qa_smoke.py --quick` passes.
- `python tools/mythos_tick_bench.py --ticks 900 --warmup 180 --heroes 24 --buildings 24 --enemies 80` shows no alarming regression; Agent 10 should interpret if needed.
- Active workers update their own logs with files, commands, evidence, blockers, and follow-ups.

## Integration Order

1. Agent 03 defines boss/elite primitive contracts, event names, read-model fields, and sim registration hooks.
2. Agent 05 implements boss/elite gameplay content/runtime and deterministic tests.
3. Agent 09 adds visual marker/telegraph rendering in the graphics lane.
4. Agent 08 adds compact boss/elite status UI.
5. Agent 11 runs integrated QA, screenshots, WK67, `qa_smoke`, and perf sanity.
6. Agent 10 is added only if Agent 11 or Agent 09 sees render/tick regression.

## Worker Model

Use **gpt-5.4-mini with xhigh reasoning effort** for every WK139 subagent, per Jaimie's autonomous sprint instruction.

## Agent 03 Assignment

Task: Add boss/elite sim/view contracts and register an empty-default boss encounter lane without implementing gameplay balance.

Files you MAY edit:
- `game/sim/**`
- `game/sim_engine.py`
- `game/events.py`
- `tests/test_wk139_boss_contract.py`
- `tests/test_wk139_boss_ai_view.py`
- your Agent 03 log

Files you MUST NOT edit:
- `game/systems/boss_encounter.py` unless Agent 05 already created it and PM sends a follow-up registration prompt
- `game/entities/**`
- `game/ui/**`
- `game/graphics/**`
- `ai/**`
- `assets/**`
- `config.py` unless PM explicitly expands scope

Implementation guidance:
- Follow the WK138 pattern: immutable/primitive snapshots, empty tuple default fields, no live object refs.
- Suggested snapshot facts:
  - boss id/type/name/status/current_phase/current_phase_title/hp_pct/position/target hero id/latest telegraph/memory summaries.
  - elite id/base type/name/affixes/status/position.
- Suggested event names:
  - `boss_encounter_started`
  - `boss_phase_changed`
  - `boss_ability_telegraphed`
  - `boss_ability_resolved`
  - `boss_defeated`
  - `elite_spawned`
- `SimEngine` may have `boss_encounter_system = None` until Agent 05 creates the system, or instantiate it after Agent 05. Empty read model must still work.
- No-boss path must not consume RNG or mutate state.

Commands:
```powershell
python -m pytest tests/test_wk139_boss_contract.py tests/test_wk139_boss_ai_view.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

## Agent 05 Assignment

Task: Implement boss encounter gameplay and deterministic elite affixes for The Goblin Warchief.

Files you MAY edit:
- `game/systems/**`
- `game/entities/**`
- `game/content/**`
- `config.py` only for clearly named tuning constants if unavoidable
- `tests/test_wk139_boss_encounters.py`
- `tests/test_wk139_elite_affixes.py`
- `tests/test_wk139_boss_memory.py`
- your Agent 05 log

Files you MUST NOT edit:
- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `tools/**`
- `assets/**`

Implementation guidance:
- Prefer new content modules such as `game/content/bosses.py` and `game/content/elite_affixes.py`.
- Prefer new runtime module such as `game/systems/boss_encounter.py`.
- Do not duplicate combat math. Boss abilities should layer on existing enemy/enemy-spawn/combat primitives.
- `BossEncounterSystem.update` must early-return if no active boss encounters.
- Roll elite affixes only at enemy creation/spawn time. Use existing deterministic RNG patterns or a named stream such as `boss_encounters`.
- Ability cooldown/telegraph must use sim time, not wall-clock time.
- Warchief phase design:
  - Phase 1 `war_banner`: active above 50% HP. Small capped nearby goblin bonus or courage fact. Must be testable.
  - Phase 2 `rally`: starts at or below 50% HP. Emits telegraph, then spawns/calls at most a small capped reinforcement if nearby goblin count is below cap.
- Memory facts should be primitive records, e.g. `{"event": "defeated_by", "hero_id": 12, "hero_name": "Astra", "time_ms": 12345}`.

Commands:
```powershell
python -m pytest tests/test_wk139_boss_encounters.py tests/test_wk139_elite_affixes.py tests/test_wk139_boss_memory.py -q
python -m pytest tests/test_wk137_initial_wave.py tests/test_wk137_boss_scale.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

## Agent 09 Assignment

Task: Add readable boss/elite visual markers and ability telegraph rendering without violating Mythos performance guardrails.

Files you MAY edit:
- `game/graphics/**`
- `tests/test_wk139_boss_visuals.py`
- `tests/test_wk139_elite_visuals.py`
- screenshot outputs under `docs/screenshots/wk139_*`
- your Agent 09 log

Files you MUST NOT edit:
- `game/systems/**`
- `game/entities/**`
- `ai/**`
- `game/ui/**` unless PM coordinates with Agent 08
- `assets/**`
- `config.py` unless PM explicitly expands scope

Implementation guidance:
- Use primitive boss/elite/telegraph snapshot facts from Agent 03/05.
- Reuse instanced renderer patterns. No unbounded per-frame entity creation.
- Boss marker must not obscure labels/HP bars.
- Elite marker should be visible at normal zoom but restrained.
- Telegraph visuals should appear before the ability resolves and clear afterward.

Commands:
```powershell
python -m pytest tests/test_wk139_boss_visuals.py tests/test_wk139_elite_visuals.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/wk139_boss_encounter_showcase --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
```

## Agent 08 Assignment

Task: Add compact boss/elite status UI.

Files you MAY edit:
- `game/ui/**`
- `tests/test_wk139_boss_ui.py`
- screenshot outputs under `docs/screenshots/wk139_*`
- your Agent 08 log

Files you MUST NOT edit:
- `game/systems/**`
- `game/entities/**`
- `ai/**`
- `game/graphics/**`
- `assets/**`

Implementation guidance:
- Keep it compact and operational. No large hero panel or decorative splash.
- Show boss name, current phase, HP status, and ability telegraph/status if present.
- If elite facts are present, show no more than a short line/count/marker hint; avoid clutter.
- Must fit with existing HUD at 1920x1080 and not hide core controls.

Commands:
```powershell
python -m pytest tests/test_wk139_boss_ui.py -q
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/wk139_boss_ui --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
```

## Agent 11 Assignment

Task: Verify WK139 end to end.

Files you MAY edit:
- `tests/**`
- deterministic screenshot/scenario files only if existing ownership allows; otherwise file a PM request for Agent 12
- `docs/screenshots/wk139_*`
- your Agent 11 log

Files you MUST NOT edit:
- production game code unless PM sends a separate fix prompt
- `assets/**`

Required commands:
```powershell
python -m pytest tests/test_wk139_boss_contract.py tests/test_wk139_boss_ai_view.py -q
python -m pytest tests/test_wk139_boss_encounters.py tests/test_wk139_elite_affixes.py tests/test_wk139_boss_memory.py -q
python -m pytest tests/test_wk139_boss_visuals.py tests/test_wk139_elite_visuals.py tests/test_wk139_boss_ui.py -q
python -m pytest tests/test_wk137_initial_wave.py tests/test_wk137_boss_scale.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/wk139_boss_encounter_showcase --size 1920x1080 --ticks 900
python tools/mythos_tick_bench.py --ticks 900 --warmup 180 --heroes 24 --buildings 24 --enemies 80
```

Final report must include:
- PASS/FAIL for boss contract, boss gameplay, elite affixes, boss memory, visuals, UI, screenshot, WK67, `qa_smoke`, and perf.
- Screenshot paths inspected and visual verdict.
- Owner-specific repro/follow-up prompts for any failure.

## PM Close Checklist

- Read all active agent logs.
- Personally inspect latest screenshot proof.
- Confirm no worker touched outside lane without explaining it.
- Confirm `qa_smoke` and WK67 passed after all implementation.
- Commit and push before planning WK140 First Epic Boss Quest.
