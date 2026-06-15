# WK142 Dynamic Rescue & Revenge

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-15  
**Roadmap source:** `.cursor/plans/future_hero_quest_boss_deepening.plan.md` Sprint D  
**Status:** Kickoff ready  
**Execution model:** multi-agent sprint. Use `gpt-5.4-mini` with `xhigh` effort for active implementation/QA agents unless Jaimie explicitly changes the studio model.

---

## Player Outcome

Heroes should stop feeling like ten units scattering in tiny loops around town. WK140 gave them broader day-to-day intent variety; WK142 gives the world stronger reasons for that variety to matter:

- A hero can be captured by one specific boss/POI template instead of simply disappearing into a generic failure.
- The kingdom can surface a real rescue opportunity from that captured hero state.
- Another hero can decide to attempt the rescue, travel to the danger, resolve a rescue phase, and create a visible ledger/memory outcome.
- If a named boss kills a hero, the kingdom can surface a revenge quest that points at the actual boss and actual fallen hero.
- AI context exposes captured-hero and revenge facts so heroes can talk and act around them without inventing state.

This sprint should make the kingdom feel closer to fantasy literature: Beowulf-style vendettas, Robin Hood prisoner rescues, Darkest Dungeon expedition consequences, and Shadow of Mordor-style enemy memory, while preserving Majesty-style indirect control. The player posts opportunities and raises rewards; heroes choose.

---

## Current Grounding

Already shipped:

- WK138: `QuestChainSystem`, chain instances, Adventure Ledger foundation, phase/history view contracts.
- WK139: `BossEncounterSystem`, named boss runtime facts, elite affixes, boss UI/visual language.
- WK140: daily-life hero AI variety, bounty stickiness, anti-tight-loop conviction.
- WK141: Blackbanner's Toll, Rusk Blackbanner, toll-taker elite, AI/UI/visual integration for the first epic boss quest.

WK142 must build on those systems. Do not replace them and do not create a separate one-off rescue system that the next sprint cannot reuse.

---

## Design Pillars

1. **Failure becomes a hook, not a dead end.** A bad boss fight can create a rescue or revenge story.
2. **Only real state becomes a quest.** If the ledger says Hero A is captured by Rusk, Hero A must have a captured status/fact and a resolvable location.
3. **Start with one excellent template.** Implement capture/rescue for the Blackbanner/Bandit Fortress family first. Do not make every POI capture heroes.
4. **Heroes regain world-scale purpose.** Rescue/revenge facts should influence AI beyond the town square: seek POIs, visit the castle/Herald's Post, choose monster/boss pressure, rest before dangerous attempts.
5. **Determinism remains sacred.** No wall-clock time, no global RNG, no renderer mutation of sim state, no LLM-authoritative state changes.

---

## Feature Scope

### In Scope

- Add or wire a reusable `rescue_hero` quest phase type.
- Add capture/imprisoned state for exactly one template: Blackbanner/Bandit Fortress/Rusk.
- Add a deterministic capture trigger that can be tested without relying on flaky full combat.
- Add boss kill memory for named bosses: `boss_id`, `boss_name`, `fallen_hero_id`, `fallen_hero_name`, time, location if available.
- Add a revenge quest offer/chain sourced from a named boss killing a hero.
- Add cleanup rules so rescue/revenge situations do not duplicate forever and do not outlive invalid targets.
- Add AI context and behavior policy for:
  - captured hero facts,
  - rescue opportunity facts,
  - revenge opportunity facts,
  - boss danger and retreat gates.
- Expand AI daily-life behavior enough that rescue/revenge opportunities pull different hero classes into visibly different choices instead of local wandering loops.
- Add Adventure Ledger/HUD readability for captured/rescue/revenge status.
- Add tests and screenshot proof where player-visible UI or world graphics change.

### Out Of Scope

- General party formation.
- Captures for every POI.
- Permanent trauma/psychology system.
- Full memorial hall UI.
- Large new visual asset packs.
- Direct player command to force a specific hero to rescue/revenge.
- LLM-created bosses, captures, deaths, or quest facts.

---

## Gameplay Design

### Rescue Loop: Blackbanner Captives

First implementation target:

1. **Trigger:** A hero fighting Rusk Blackbanner, the toll-taker elite, or the Blackbanner fortress danger can enter `captured` instead of ordinary defeat under a bounded condition.
2. **State:** Captured hero becomes unavailable for normal daily AI, combat targeting, and new quest acceptance. They have a known captor and location.
3. **Offer:** The Herald's Post or Adventure Ledger creates a rescue opportunity: "Break the Blackbanner Cells."
4. **Phase 1 - Reach Fortress:** Rescuer travels to the Bandit Fortress / Blackbanner location.
5. **Phase 2 - Break The Guard:** Rescuer defeats a jailor/guard or resolves a `clear_guards`/`rescue_hero` handler.
6. **Phase 3 - Free Captive:** Captive state clears; rescued hero becomes available again, preferably with a small recovery/rest intent.
7. **Outcome:** Ledger records rescue history. Rescuer gets reward/renown. Captive records "rescued from Rusk Blackbanner" memory.

Implementation can collapse Phases 2 and 3 internally if the current phase engine needs a smaller slice, but the data model should not paint itself into a corner. Leave room for future "escort home" and "stealth jailbreak" variants.

### Revenge Loop: Fallen By A Named Boss

First implementation target:

1. **Trigger:** A named boss kills a hero, or a deterministic test hook records a named boss death event.
2. **Memory:** The game records a bounded boss kill memory: "Rusk Blackbanner killed Mira the Ranger."
3. **Offer:** A revenge chain appears, likely "Avenge Mira" or "Blood Debt: Rusk Blackbanner."
4. **Phase 1 - Reckon:** Hero accepts after evaluating danger/reward/personality.
5. **Phase 2 - Hunt:** Hero travels to boss location or active boss encounter.
6. **Phase 3 - Slay Named Boss:** Existing `slay_named_boss` phase resolves.
7. **Outcome:** Ledger/memory marks revenge fulfilled; duplicate revenge offers for the same fallen hero/boss close or suppress.

If the boss was already killed before the revenge offer is accepted, the offer should expire/complete cleanly rather than leaving a stale quest.

### AI Feel Target

The user specifically called out that earlier versions around v1.4 had more robust hero AI and that current hero starts can look like ten heroes wandering in tight loops near town. WK140 improved the base daily-life router; WK142 should build on that by giving heroes stronger long-distance motivations and more varied downtime:

- Fighters/paladins should be more likely to check monster pressure, bosses, bounties, and revenge offers.
- Rangers/rogues should be more likely to scout POIs, track a rescue target, or roam roads between discovered locations.
- Clerics/support-flavored heroes should be more likely to visit castle/Herald's Post, rest, or answer rescue situations.
- Injured/low-confidence heroes should rest, go home, or visit safe places before high-danger rescue/revenge.
- A hero who just completed or failed a dangerous quest should not instantly re-enter the same tiny wander loop.

Do not overfit this sprint into a huge personality system. Add modest, deterministic weighted intent support around the new rescue/revenge facts and preserve the WK140 anti-loop and urgent behavior gates.

---

## Suggested Data Contracts

Agents should adapt to current code; these shapes are guidance, not a mandate to create these exact classes.

```python
@dataclass
class HeroCaptureState:
    hero_id: int
    captor_boss_id: int | None
    captor_name: str
    location_id: int | None
    source_chain_id: int | None
    captured_at_ms: int
    status: str  # captured | rescued | lost | expired

@dataclass(frozen=True)
class BossKillMemory:
    boss_id: int
    boss_name: str
    boss_type: str
    fallen_hero_id: int
    fallen_hero_name: str
    location_id: int | None
    killed_at_ms: int
    revenge_chain_id: int | None = None
```

Recommended facts on quest chain instances:

```python
facts = {
    "captive_hero_id": captured.hero_id,
    "captive_hero_name": hero.name,
    "captor_boss_id": boss.id,
    "captor_name": "Rusk Blackbanner",
    "target_poi_id": fortress.id,
    "source": "boss_capture",
}
```

Recommended objective constants:

```python
OBJECTIVE_RESCUE_HERO = "rescue_hero"
OBJECTIVE_AVENGE_HERO = "avenge_hero"
```

`avenge_hero` may initially be represented as a chain tag/source plus a `slay_named_boss` phase if that matches existing WK138/WK141 code better.

---

## Agent Assignments

### Agent 03 - Technical Director / Architecture

**Task:** Add or verify the sim/view contracts that let capture, rescue, and revenge exist as first-class deterministic facts.

**Files you MAY edit:**

- `game/sim/**`
- `game/sim_engine.py`
- `game/engine.py`
- `game/game_commands.py`
- architecture-facing tests under `tests/**`
- your agent log

**Files you MUST NOT edit:**

- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `assets/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Prefer adding contract/view fields to existing WK138/WK139 structures instead of inventing a parallel data bus.
- Ensure `AiGameView` or equivalent AI snapshot exposes compact facts:
  - `captured_heroes`
  - `rescue_opportunities`
  - `boss_kill_memories` or `revenge_opportunities`
- Use primitive IDs/names/status strings in views. Do not pass live entity objects into AI/UI.
- Ensure empty-default behavior is unchanged: if there are no captures/revenge facts, the new lists are empty and no RNG is consumed.
- If Agent 05 already has enough contract surface, write focused tests proving it and avoid unnecessary code churn.

**Acceptance:**

- Tests prove captured hero and revenge facts can be represented in sim/view snapshots.
- Tests prove empty-default snapshots remain stable and do not expose fake captures.
- No player-visible change required from Agent 03 alone.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk142_dynamic_rescue_contract.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

### Agent 05 - Gameplay Systems Designer

**Task:** Implement the actual rescue/revenge gameplay loop and cleanup rules.

**Files you MAY edit:**

- `game/entities/**`
- `game/systems/**`
- `game/content/**`
- balance/tuning files if existing systems put quest/boss tuning there
- gameplay tests under `tests/**`
- your agent log

**Files you MUST NOT edit:**

- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `tools/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Add a bounded capture source for the Blackbanner/Rusk family only.
- Captured heroes must be excluded from normal task routing/availability by state, not by deleting them.
- Use a deterministic test helper or event path to create capture/revenge situations. Do not rely on probabilistic combat in tests.
- Rescue completion should:
  - clear the captured state,
  - make the rescued hero available again,
  - append phase/history/memory facts,
  - prevent duplicate active rescue chains for the same captive.
- Revenge completion should:
  - connect to the real named boss identity,
  - complete when the boss dies,
  - expire/cleanup if the boss is already dead or invalid,
  - prevent duplicate active revenge chains for the same boss/fallen hero pair.
- Keep all new ticking cheap. Early-return when no active captures/revenge opportunities exist.
- Do not use wall-clock time or global RNG.

**Acceptance:**

- A deterministic test can create a captured Blackbanner captive and complete a rescue.
- A deterministic test can record named boss killing a hero and create/complete a revenge chain.
- Cleanup tests prove duplicates/stale offers are suppressed.
- Existing WK138-WK141 quest/boss tests still pass.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk142_boss_revenge.py tests/test_wk142_dynamic_cleanup.py -q
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_chain.py tests/test_wk141_blackbanner_boss.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

### Agent 06 - AI Behavior Director / LLM

**Task:** Teach hero AI and prompt context to reason about rescue/revenge opportunities while further reducing tight local wandering.

**Files you MAY edit:**

- `ai/**`
- AI tests under `tests/**`
- your agent log

**Files you MUST NOT edit:**

- `game/systems/**`
- `game/entities/**`
- `game/ui/**`
- `game/graphics/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Preserve WK140 urgent behavior priority: survival/retreat/critical tasks beat story ambition.
- Add rescue/revenge facts to LLM prompt context only from structured game view. The LLM may decide intent/flavor, not facts.
- Expand deterministic non-LLM behavior weights so heroes do a broader variety of day-to-day actions:
  - roam beyond town when safe,
  - explore discovered/nearby POIs,
  - seek monsters/boss pressure,
  - consider rescue/revenge offers,
  - rest at home or safe buildings,
  - visit the castle/Herald's Post after major events.
- Add class/personality-ish bias using existing hero fields only. Do not create a huge new psychology schema in this sprint.
- Avoid "everyone sees rescue, everyone runs there." Use caps, cooldown/stickiness, class bias, danger checks, and reward/renown weighting.
- Respect captured hero unavailability. Captured heroes should not route themselves to normal daily-life tasks.

**Concrete policy examples:**

```text
If rescue_opportunities is non-empty and hero is healthy:
  - ranger/rogue/fighter: can propose travel_to_rescue_target or accept_rescue_chain
  - cleric/support: can propose visit_castle_or_herald, prepare/rest, or rescue if danger is moderate
  - low health/fear/cooldown: rest_home or safe_roam, not reckless rescue

If revenge_opportunities is non-empty:
  - high combat confidence: may pursue revenge
  - low combat confidence: may train/rest/seek safer bounty
  - never invent that the boss killed a hero; only repeat provided facts
```

**Acceptance:**

- Tests prove prompt context includes captured/rescue/revenge facts when present and omits them when absent.
- Tests prove urgent survival behavior is preserved.
- Tests prove a 10-hero startup distribution does not collapse into all heroes choosing the same tight local roam when rescue/revenge/POI facts exist.
- Tests prove captured heroes do not choose ordinary active tasks.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk142_rescue_ai_policy.py tests/test_wk142_rescue_prompt_context.py tests/test_wk140_hero_daily_life_ai.py tests/test_wk140_hero_ambient_distribution.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

### Agent 08 - UX/UI Director

**Task:** Make rescue/revenge state readable in the Adventure Ledger/HUD without clutter.

**Files you MAY edit:**

- `game/ui/**`
- UI tests under `tests/**`
- screenshot output under `docs/screenshots/wk142_*`
- your agent log

**Files you MUST NOT edit:**

- `game/systems/**`
- `ai/**`
- `game/graphics/**`
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- Use the existing Adventure Ledger visual language from WK138/WK141.
- Show concise status text:
  - captured hero name,
  - captor/boss name,
  - target location if known,
  - current phase,
  - rescued/avenged completion state.
- Keep text fitted in narrow HUD widths. Do not let long hero/boss names overlap adjacent elements.
- If current UI already renders generic chain facts well, add tests and only minimal labels/badges.
- Do not add a new large panel unless existing ledger cannot carry the state.

**Acceptance:**

- UI tests prove rescue/revenge facts render in active and completed states.
- Screenshots are captured and inspected if the visible UI changes.
- Narrow HUD layout remains legible.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk142_rescue_ui.py tests/test_wk141_blackbanner_ui.py -q
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk142_rescue_revenge_ui --size 1920x1080 --ticks 600
python tools/qa_smoke.py --quick
```

If `ui_panels` cannot display active rescue/revenge chains, report that gap and coordinate Agent 11/12 for a deterministic scenario rather than claiming screenshots prove something they do not show.

### Agent 09 - Art Director / Pixel Animation / VFX

**Task:** Verify or minimally improve visible signals for captives, rescue targets, and revenge bosses.

**Files you MAY edit:**

- `game/graphics/**`
- graphics tests under `tests/**`
- screenshot output under `docs/screenshots/wk142_*`
- your agent log

**Files you MUST NOT edit:**

- `game/systems/**`
- `game/ui/**`
- `ai/**`
- `assets/**` unless you coordinate asset validation and keep scope tiny
- `.cursor/plans/**` except your own log

**Implementation guidance:**

- First check whether WK139/WK141 boss/elite markers already cover revenge bosses and target enemies. If yes, prefer tests and screenshot proof over new visuals.
- Captive state can be represented with existing icon/label/marker language if available. Do not create a large asset pack.
- Any visible new marker must be deterministic and readable at gameplay zoom.
- Renderer must not mutate rescue/revenge state.

**Acceptance:**

- Either screenshot evidence proves existing visuals are sufficient, or minimal visual markers are added and screenshot-verified.
- Visual tests cover boss/captive/revenge marker data where practical.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk142_rescue_visuals.py tests/test_wk141_blackbanner_visuals.py -q
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/wk142_rescue_revenge_boss --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
```

### Agent 11 - QA / Test Engineering Lead

**Task:** Final independent verification after implementation waves.

**Files you MAY edit:**

- `tests/**`
- `docs/screenshots/wk142_*`
- your agent log

**Files you MUST NOT edit:**

- gameplay/AI/UI/graphics source unless PM explicitly asks for a tiny test-only fix within your lane
- `.cursor/plans/**` except your own log

**Verification responsibilities:**

- Validate logs for Agents 03/05/06/08/09 as applicable.
- Run all WK142 focused tests.
- Run key WK138-WK141 regressions.
- Run WK67.
- Run `qa_smoke`.
- Inspect screenshot PNGs for actual visible rescue/revenge proof, not just file existence.
- Report PASS/FAIL with blockers and exact reproduction commands.

**Run from repo root:**

```powershell
python -m pytest tests/test_wk142_dynamic_rescue_contract.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk142_boss_revenge.py tests/test_wk142_dynamic_cleanup.py tests/test_wk142_rescue_ai_policy.py tests/test_wk142_rescue_prompt_context.py tests/test_wk142_rescue_ui.py tests/test_wk142_rescue_visuals.py -q
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk139_boss_encounters.py tests/test_wk140_hero_daily_life_ai.py tests/test_wk141_blackbanner_chain.py tests/test_wk141_blackbanner_boss.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

If screenshots are required, inspect:

```powershell
Get-ChildItem docs\screenshots\wk142_* -Recurse -Filter *.png
```

---

## Integration Order

### Wave 1 - Contracts + Gameplay

Run in parallel:

- Agent 03: sim/view contracts.
- Agent 05: capture/rescue/revenge gameplay.

PM gate after Wave 1:

```powershell
python -m pytest tests/test_wk142_dynamic_rescue_contract.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk142_boss_revenge.py tests/test_wk142_dynamic_cleanup.py -q
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_chain.py tests/test_wk141_blackbanner_boss.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
```

### Wave 2 - AI + UI + Visuals

Run after Wave 1 facts exist:

- Agent 06: AI policy, prompt context, daily-life variety integration.
- Agent 08: Adventure Ledger/HUD readability.
- Agent 09: visual proof or minimal markers.

PM gate after Wave 2:

```powershell
python -m pytest tests/test_wk142_rescue_ai_policy.py tests/test_wk142_rescue_prompt_context.py tests/test_wk142_rescue_ui.py tests/test_wk142_rescue_visuals.py -q
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_wk140_hero_ambient_distribution.py tests/test_wk141_blackbanner_ai_policy.py tests/test_wk141_blackbanner_ui.py tests/test_wk141_blackbanner_visuals.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
```

### Wave 3 - Final QA

Run after Wave 2 lands:

- Agent 11: final gate, screenshot inspection, logs, `qa_smoke`.

---

## Definition Of Done

- One deterministic capture/rescue loop exists for the Blackbanner/Bandit Fortress template.
- One deterministic named-boss revenge loop exists.
- Captured heroes are unavailable for ordinary AI and become available again after rescue.
- Duplicate/stale rescue and revenge offers are suppressed or cleaned up.
- Hero AI sees rescue/revenge facts and makes more varied, world-scale decisions while preserving retreat/survival gates.
- LLM prompt context uses structured facts only.
- Adventure Ledger/HUD exposes the state clearly enough for the player to understand who is captured, who killed whom, and what current phase matters.
- Visual evidence is screenshot-verified if visible presentation changes.
- WK138/WK139/WK140/WK141 focused regressions pass.
- WK67 passes.
- `python tools/qa_smoke.py --quick` passes before close.

---

## Risk Register

- **Risk:** Captured heroes keep acting like normal heroes.  
  **Mitigation:** Agent 05 state gate plus Agent 06 tests proving captured heroes do not route to ordinary tasks.

- **Risk:** Revenge offers duplicate every tick after a boss kill.  
  **Mitigation:** Pair key `(boss_id, fallen_hero_id)` and cleanup tests.

- **Risk:** Every hero stampedes to the same rescue.  
  **Mitigation:** Agent 06 class bias, caps, cooldowns, danger thresholds, and WK140 anti-loop preservation.

- **Risk:** UI says a rescue exists but target is gone.  
  **Mitigation:** cleanup/expiry tests and UI empty/expired-state tests.

- **Risk:** Scope grows into a general nemesis system.  
  **Mitigation:** only Blackbanner capture and one named-boss revenge path in WK142.

---

## PM Notes For Closeout

If WK142 lands cleanly, the roadmap can continue to Sprint E Dragon Hunt. Dragon Hunt should reuse the new failure hooks: scouting the dragon cave can create rescue/revenge stakes, but the first dragon sprint should still focus on the dragon's preparation/hunt/boss phases rather than expanding capture broadly.
