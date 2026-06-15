# WK143 Dragon Hunt Showcase

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-15  
**Roadmap source:** `.cursor/plans/future_hero_quest_boss_deepening.plan.md` Sprint E  
**Status:** Kickoff ready after WK142 push `f6caf02`  
**Execution model:** multi-agent sprint. Use `gpt-5.4-mini` with `xhigh` effort for every active subagent unless Jaimie explicitly changes the model.

---

## Mission

Make Dragon Cave the first mythic encounter showcase: a preparation-heavy, high-risk, highly readable dragon hunt that feels different from bandits and war chiefs.

The player-facing fantasy is:

> A hero hears of Ashwing's hoard, scouts the Dragon Cave, learns a weakness, prepares with a shrine/item/scale clue, survives a telegraphed fire attack, defeats a named dragon, claims legendary loot, and earns a title.

This sprint should reuse the WK138-WK142 foundation:

- WK138 quest-chain phases and Adventure Ledger history.
- WK139 boss encounter runtime and telegraph concepts.
- WK140/WK142 hero AI variety and world-scale behavior.
- WK141 first epic boss quest patterns.
- WK142 consequence hooks: if Ashwing kills a hero, revenge memory can exist; do **not** add dragon capture in this sprint.

---

## Design Pillars

1. **Preparation matters.** A dragon hunt is not "walk to monster, trade hits." Heroes should scout, learn danger, consider a weakness, and decide whether to prepare or retreat.
2. **The fire must be fair.** Dragon fire needs a visible/audible telegraph before danger, a deterministic payload, and tests proving the warning exists before the hit.
3. **Mythic reward.** Victory grants hoard reward, legendary loot, and a hero title such as `Ashwing-Bane`.
4. **Indirect control remains intact.** The player funds/posts opportunities; heroes choose based on danger, readiness, reward, personality/class bias, and survival.
5. **Do one dragon well.** Build Ashwing as the first polished template, not a generic dragon ecosystem.

---

## In Scope

- `ASHWINGS_HOARD` / "Ashwing's Hoard" quest-chain content.
- Dragon Cave chain phases:
  - `scout_location` or equivalent reaches/reveals Dragon Cave.
  - `prepare_hunt` or equivalent phase that can be satisfied by one bounded preparation action.
  - `slay_named_boss` against Ashwing.
  - `claim_hoard` / reward completion using existing reward/loot mechanisms where possible.
- Named dragon boss `Ashwing the Red` using `BossEncounterSystem`.
- Telegraphed fire attack with deterministic cooldown/telegraph/payload.
- Phase transition at a clear health threshold.
- Legendary loot table and victory title/memory.
- AI/prompt policy for preparation, danger, retreat, and victory/revenge facts.
- Adventure Ledger/HUD readability for Dragon Hunt phases, Ashwing identity, weakness/prep, fire warning, victory title/loot.
- Visual proof of telegraph/fire/boss readability.
- Audio proof for roar/fire/phase SFX using existing audio system or minimal new audio metadata.
- Deterministic screenshot/capture scenario `dragon_hunt_showcase` if it does not already exist.
- Performance sanity for the showcase.

---

## Out Of Scope

- General party formation.
- Multiple dragon species.
- Dragon capture/rescue.
- Fully dynamic elemental weakness system.
- New large asset pack or licensed audio pack.
- Direct player order to force a named hero to fight Ashwing.
- LLM-authoritative facts about dragon death, loot, or weakness.

---

## Recommended Content Shape

Agents should adapt to current systems rather than copying these shapes blindly.

```python
ASHWINGS_HOARD_PHASES = (
    QuestPhaseDef(
        phase_id="scout_dragon_cave",
        title="Scout the Dragon Cave",
        objective_type="scout_location",
        target_ref="dragon_cave",
        next_on_success="prepare_against_fire",
    ),
    QuestPhaseDef(
        phase_id="prepare_against_fire",
        title="Prepare Against Ashwing's Fire",
        objective_type="prepare_hunt",
        target_ref="fire_weakness",
        optional=False,
        next_on_success="slay_ashwing",
    ),
    QuestPhaseDef(
        phase_id="slay_ashwing",
        title="Slay Ashwing the Red",
        objective_type="slay_named_boss",
        target_ref="ashwing",
        next_on_success="claim_hoard",
    ),
    QuestPhaseDef(
        phase_id="claim_hoard",
        title="Claim Ashwing's Hoard",
        objective_type="claim_hoard",
        target_ref="dragon_hoard",
    ),
)
```

Suggested boss phases:

- **Sleeping Hoard:** Ashwing is revealed; scout/prep facts become available.
- **Air And Fire:** fire breath telegraphs before damage. Heroes may retreat if unprepared or wounded.
- **Wounded Fury:** below threshold, fire cooldown changes or Ashwing adds a roar/fear tell, but keep the first implementation bounded.

Suggested fire attack contract:

```python
BossAbilityDef(
    ability_id="ashwing_fire_breath",
    display_name="Fire Breath",
    trigger="cooldown",
    cooldown_ms=9000,
    telegraph_ms=1400,
    payload={
        "shape": "cone",
        "range": 9.0,
        "damage": 24,
        "status": "scorched",
        "warning_event": "dragon_fire_telegraph",
        "impact_event": "dragon_fire_impact",
    },
)
```

Rules:

- Telegraph event must occur before damage event in deterministic tests.
- Use sim time / named RNG only. No wall-clock/global RNG.
- If no active dragon encounter exists, the boss system returns cheaply and consumes no RNG.
- Fire payload should be testable without full renderer or probabilistic combat.

---

## Agent Assignments

### Agent 05 - Gameplay Systems Designer

**Task:** Implement Ashwing mechanics, chain content, loot/title reward, and deterministic gameplay tests.

**Files you MAY edit:**

- `game/entities/**`
- `game/systems/**`
- `game/content/**`
- gameplay tests under `tests/**`
- your agent log

**Files you MUST NOT edit:**

- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `game/audio/**`
- `tools/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Reuse `QuestChainSystem` and `BossEncounterSystem`; do not create a one-off dragon quest runner.
- Add `ASHWINGS_HOARD` as content and runtime facts.
- Add a bounded preparation objective. Prefer using existing items/shrine/POI facts; if a new prep fact is needed, keep it primitive and deterministic.
- Implement Ashwing's fire telegraph as a boss ability with explicit event/fact before damage.
- Add legendary loot and title/memory on victory. Use existing loot/title/memory systems where possible.
- Hook boss kill memory into existing WK142 revenge support if Ashwing kills a hero, but do not broaden revenge beyond named-boss facts already supported.
- Tests must not depend on random full combat. Use deterministic helper setup/events.

**Acceptance:**

- A deterministic test completes Ashwing's Hoard through scout/prep/slay/claim.
- A deterministic test proves fire telegraph appears before fire impact/damage.
- A deterministic test proves legendary loot/title/memory after victory.
- Existing WK139/WK141/WK142 boss/quest tests still pass.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_hunt.py tests/test_wk143_dragon_fire_telegraph.py tests/test_wk143_dragon_rewards.py -q
python -m pytest tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_boss.py tests/test_wk142_boss_revenge.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

### Agent 12 - Tools / DevEx

**Task:** Add deterministic screenshot/capture scenario support for Dragon Hunt if missing.

**Files you MAY edit:**

- `tools/**`
- tool/scenario tests under `tests/**`
- docs screenshot output under `docs/screenshots/wk143_*`
- your agent log

**Files you MUST NOT edit:**

- `game/entities/**`, `game/systems/**`, `ai/**`, `game/ui/**`, `game/graphics/**`, `game/audio/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Current PM check found no `dragon_hunt_showcase` scenario. Add one only if still missing.
- Prefer adapting the existing `boss_encounter_showcase` scenario shape.
- Scenario should deterministically seed Ashwing, the Dragon Cave, active chain state, and a fire telegraph/impact visual state if possible.
- Keep scenario code presentation-only/test-helper oriented; do not mutate production sim rules from tools.

**Acceptance:**

- `python tools/capture_screenshots.py --scenario dragon_hunt_showcase ...` works for pygame capture if supported.
- If Ursina-only capture is required, `python tools/run_ursina_capture_once.py --scenario dragon_hunt_showcase ...` works or a clear documented fallback exists.
- Manifest and PNG outputs are produced under `docs/screenshots/wk143_dragon_hunt_showcase`.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_capture_scenario.py -q
python tools/capture_screenshots.py --scenario dragon_hunt_showcase --seed 3 --out docs/screenshots/wk143_dragon_hunt_showcase --size 1920x1080 --ticks 1200
python tools/qa_smoke.py --quick
```

### Agent 06 - AI Behavior Director / LLM

**Task:** Teach heroes and prompt context to prepare for Ashwing, respect danger, retreat intelligently, and celebrate/remember victory.

**Files you MAY edit:**

- `ai/**`
- AI tests under `tests/**`
- your agent log

**Files you MUST NOT edit:**

- `game/**`
- `tools/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Use structured facts from the quest/boss view only: dragon identity, cave location, known weakness/prep state, fire danger, active phase, hero readiness, and victory/revenge memory.
- LLM can choose tone/intent but must not invent weakness learned, dragon killed, or hoard claimed.
- Preserve survival/retreat gates. An injured/unprepared hero should prefer rest, shrine/item prep, or retreat over reckless dragon fight.
- Tie into WK140/WK142 daily-life variety: dragon facts can pull some heroes toward scouting/prep and others toward rest/training/safer opportunities.

**Acceptance:**

- Prompt context includes dragon hunt facts only when structured facts exist.
- AI policy tests prove prepared/high-confidence heroes may hunt, while wounded/unprepared heroes rest/prepare/retreat.
- Captured/rescue/revenge behavior from WK142 still passes.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_ai_policy.py tests/test_wk143_dragon_prompt_context.py -q
python -m pytest tests/test_wk142_rescue_ai_policy.py tests/test_wk142_rescue_prompt_context.py tests/test_wk140_hero_daily_life_ai.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

### Agent 08 - UX / UI Director

**Task:** Make Ashwing's Hoard readable in Adventure Ledger/HUD.

**Files you MAY edit:**

- `game/ui/**`
- UI tests under `tests/**`
- docs screenshots under `docs/screenshots/wk143_*`
- your agent log

**Files you MUST NOT edit:**

- `game/systems/**`
- `ai/**`
- `game/graphics/**`
- `tools/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Reuse WK141/WK142 Adventure Ledger patterns.
- Show chain name, current phase, Ashwing identity, known weakness/prep status, fire warning if exposed, hoard reward, and victory title.
- Keep narrow card layouts readable.
- Screenshot-verify active and completed states.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_ui.py tests/test_wk142_rescue_ui.py -q
python tools/capture_screenshots.py --scenario dragon_hunt_showcase --seed 3 --out docs/screenshots/wk143_dragon_hunt_ui --size 1920x1080 --ticks 1200
python tools/qa_smoke.py --quick
```

### Agent 09 - Art Director / Graphics

**Task:** Make Ashwing, fire telegraph, and hoard/phase visuals readable.

**Files you MAY edit:**

- `game/graphics/**`
- graphics tests under `tests/**`
- docs screenshots under `docs/screenshots/wk143_*`
- your agent log

**Files you MUST NOT edit:**

- `game/systems/**`
- `ai/**`
- `game/ui/**`
- `game/audio/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Reuse existing boss/elite visual systems where possible.
- Add only minimal renderer-side markers/VFX needed for a dragon-scale encounter: boss label/scale, fire telegraph shape, impact readability, hoard marker if available.
- Renderer must not mutate sim state.
- Screenshot loop is mandatory.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_visuals.py tests/test_wk142_rescue_visuals.py -q
python tools/capture_screenshots.py --scenario dragon_hunt_showcase --seed 3 --out docs/screenshots/wk143_dragon_hunt_visuals --size 1920x1080 --ticks 1200
python tools/qa_smoke.py --quick
```

### Agent 14 - Sound Director / Audio

**Task:** Add or wire roar/fire/phase SFX feedback for the Dragon Hunt.

**Files you MAY edit:**

- `game/audio/**`
- audio tests under `tests/**`
- asset manifests only if audio assets are added and attribution/license is clear
- your agent log

**Files you MUST NOT edit:**

- `game/systems/**`
- `game/graphics/**`
- `ai/**`
- `tools/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Prefer existing audio assets/events first. If adding assets, they must be license-clean and `python tools/validate_assets.py --report` must pass.
- Audio is presentation-only and may use wall-clock cooldowns if existing audio system does, but must not mutate sim state.
- Required cues: dragon roar/phase start, fire telegraph/impact if supported.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_audio.py -q
python tools/validate_assets.py --report
python tools/qa_smoke.py --quick
```

### Agent 10 - Performance Stability Lead

**Task:** Performance sanity consult after mechanics/visuals/tooling land.

**Files you MAY edit:**

- performance tests/docs only if needed
- your agent log

**Files you MUST NOT edit:**

- production gameplay/AI/UI/graphics/audio source unless PM sends a separate repair prompt

**Verification focus:**

- Dragon telegraph/VFX must not add continuous heavy per-frame work when no dragon encounter is active.
- Showcase capture should be nonblank and reasonably stable.
- If a perf regression is suspected, report exact scenario/metrics and owner handoff.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_visuals.py tests/test_wk143_dragon_hunt.py -q
python tools/qa_smoke.py --quick
```

### Agent 11 - QA

**Task:** Final integrated verification.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk143_dragon_hunt.py tests/test_wk143_dragon_fire_telegraph.py tests/test_wk143_dragon_rewards.py tests/test_wk143_dragon_ai_policy.py tests/test_wk143_dragon_prompt_context.py tests/test_wk143_dragon_ui.py tests/test_wk143_dragon_visuals.py tests/test_wk143_dragon_audio.py tests/test_wk143_dragon_capture_scenario.py -q
python -m pytest tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_chain.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk142_rescue_ai_policy.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/validate_assets.py --report
python tools/qa_smoke.py --quick
```

Inspect screenshots under `docs/screenshots/wk143_*` and report whether fire telegraph, Ashwing identity, ledger phases, and victory/hoard state are actually visible.

---

## Integration Order

### Wave 1 - Mechanics + Capture Tooling

Run in parallel:

- Agent 05: gameplay/chain/boss/fire/reward.
- Agent 12: deterministic `dragon_hunt_showcase` capture scenario.

PM gate:

```powershell
python -m pytest tests/test_wk143_dragon_hunt.py tests/test_wk143_dragon_fire_telegraph.py tests/test_wk143_dragon_rewards.py tests/test_wk143_dragon_capture_scenario.py -q
python -m pytest tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_boss.py tests/test_wk142_boss_revenge.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
```

### Wave 2 - AI + UI + Visual + Audio

Run after Wave 1 facts/tooling exist:

- Agent 06: AI/prompt policy.
- Agent 08: ledger/HUD.
- Agent 09: dragon/fire visuals.
- Agent 14: audio cues.

PM gate:

```powershell
python -m pytest tests/test_wk143_dragon_ai_policy.py tests/test_wk143_dragon_prompt_context.py tests/test_wk143_dragon_ui.py tests/test_wk143_dragon_visuals.py tests/test_wk143_dragon_audio.py -q
python tools/capture_screenshots.py --scenario dragon_hunt_showcase --seed 3 --out docs/screenshots/wk143_dragon_hunt_pm_gate --size 1920x1080 --ticks 1200
python -m pytest tests/test_wk67_ai_boundary.py -q
```

### Wave 3 - Perf Consult

- Agent 10 reviews perf risk after visual/audio work lands.

### Wave 4 - Final QA

- Agent 11 runs full final gate and screenshot inspection.

---

## Definition Of Done

- Ashwing's Hoard chain can complete deterministically through prep, fight, and hoard reward.
- Ashwing is a named boss using boss encounter infrastructure.
- Fire attack has a deterministic telegraph before damage.
- Victory grants legendary loot and a hero title/memory.
- Hero AI sees dragon/prep/danger facts from structured context and behaves sensibly.
- Adventure Ledger/HUD makes Dragon Hunt state readable.
- Dragon/fire visuals are screenshot-verified.
- Dragon roar/fire/phase audio is verified or clearly uses existing audio events with tests.
- Dragon showcase capture scenario exists and produces usable PNG evidence.
- Perf consult finds no obvious no-dragon idle overhead or documents a fix ticket.
- WK139/WK141/WK142 regressions pass.
- WK67 passes.
- `python tools/validate_assets.py --report` passes if assets/manifests changed.
- `python tools/qa_smoke.py --quick` passes before close.

---

## Closeout Rule

If this sprint ships, commit with a WK sprint message only:

```powershell
git commit -m "wk143: Dragon Hunt Showcase"
```

Do not use `Prototype v1.6.x` naming unless Jaimie explicitly authorizes that version bump.
