# WK144 Hero Agency + Content Tuning

**Owner:** Agent 01 (ExecutiveProducer_PM)
**Sprint ID:** `wk144_hero_agency_content_tuning`
**Created:** 2026-06-15
**Status:** Complete / final gates passed
**Program source:** `.cursor/plans/future_hero_quest_boss_deepening.plan.md` Sprint F plus Sovereign add-on: bounty flags must remain compelling, and idle heroes should roam, explore, seek POIs/monsters, rest, visit home/castle/social spaces, and spread around the kingdom instead of orbiting town in tight loops.

## Product Goal

Make the kingdom feel less like ten identical units scattering in tiny circles and more like a living roster of fantasy adventurers with different daily rhythms.

This sprint is not another epic boss. WK143 just shipped Ashwing. WK144 tunes the connective tissue around the epic systems:

- Player bounty flags should keep priority long enough to matter.
- Idle heroes should split across visibly different activities and destinations.
- The existing quest/boss content should have validation so future agents can safely add more chains.
- Elite affixes should reach the planned eight-affix kit with readable tells/counterplay and deterministic spawn-time behavior.
- A screenshot scenario should prove the spread is visually obvious with 10 spawned heroes.

## Current Grounding

Already present:

- `ai/behaviors/daily_life.py` with ambient motives: `kingdom_roam`, `wilderness_explore`, `poi_scout`, `monster_patrol`, `rescue_hero`, `revenge_hero`, `safe_rest`, `social_linger`, `opportunity_check`, `home_or_guild_time`, and `road_watch`.
- `ai/behaviors/bounty_pursuit.py` with bounty commitment windows and `resume_committed_bounty`.
- `ai/task_router.py` calls `resume_committed_bounty` only inside one rest-priority branch, then later can still run idle/moving state dispatch and low-priority quest-giver approach.
- `game/content/quest_chains.py` has five shipped chain definitions: Relic, Blackbanner's Toll, Blackbanner Rescue, Blackbanner Revenge, Ashwing's Hoard.
- `game/content/elite_affixes.py` currently has three affixes from the planned eight: Banner-Bearer, Ironhide, Frenzied.

Likely bug shape for bounty flags:

- A hero can accept a bounty, then health/rest/home logic or target churn can pull them into `going_home`/rest-style behavior before the bounty feels pursued.
- The fix must preserve survival: critical HP heroes may still retreat/rest. The bug is non-critical heroes dropping a live bounty too easily.

## Non-Negotiables

- Agent 01 does not edit `ai/**`, `game/**`, `tools/**`, `tests/**`, or assets.
- No version bump, no changelog release bump, no `Prototype vX.Y.Z` naming.
- Sovereign direction after kickoff: after WK144, do **not** add more quests or quest templates until Jaimie has a playtest pause. WK144 itself must stay focused on bounty/hero-agency tuning, elite-affix content, validation, and screenshots.
- Determinism boundary stays intact: no wall-clock time, no global RNG in sim/AI logic.
- Do not make heroes immortal, ignore survival, or force all heroes to take bounties.
- Do not add unsupported quest-chain content that cannot actually run.
- Visible behavior changes need screenshot proof.

## Definition Of Done

WK144 is done when:

- A focused bounty test proves a non-critical hero with a live bounty commitment does not immediately go home/rest or get overwritten by ambient daily-life choice.
- Daily-life tests prove a 10-hero roster deterministically splits across a richer set of motives and destinations, including at least kingdom/castle/home/social, POI, wilderness/frontier, monster/lair, and rest/home behavior where appropriate.
- Elite affix content reaches the eight-affix kit from the master plan or a justified close equivalent, with validation for unique IDs, non-empty tells/counterplay, bounded stat modifiers, and deterministic roll/apply behavior.
- Existing chain definitions validate for authoring safety: unique phase IDs per chain, non-empty titles/objective/target refs, positive rewards, tags, and no dangling registry entries.
- A deterministic screenshot scenario demonstrates 10 heroes spread across the kingdom instead of clumping in a tight town loop. The latest PNGs must be inspected.
- Gates pass:
  - `python -m pytest tests/test_wk144_bounty_commitment.py tests/test_wk144_hero_agency_daily_life.py -q`
  - `python -m pytest tests/test_wk144_content_validation.py tests/test_wk144_elite_affix_content.py -q`
  - `python -m pytest tests/test_wk143_dragon_hunt.py tests/test_wk143_dragon_fire_telegraph.py tests/test_wk143_dragon_rewards.py tests/test_wk126_quest_soak.py::test_soak_all_four_quest_types_complete_and_pay -q`
  - `python -m pytest tests/test_wk67_ai_boundary.py -q`
  - `python tools/capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs/screenshots/wk144_hero_agency_showcase --size 1920x1080 --ticks 1800`
  - `python tools/qa_smoke.py --quick`
  - `python tools/validate_assets.py --report` if assets/manifests changed.

## Closeout

WK144 is complete after final PM verification:

- `python tools\qa_smoke.py --quick` passed with `1986 passed, 5 skipped, 1 xfailed`.
- WK144 focused, WK140/AI bounty, WK143/WK126, and WK67 regression gates passed.
- `validate_assets --report` passed with `errors=0` and known warnings only.
- Screenshot proof was captured and inspected under `docs/screenshots/wk144_hero_agency_showcase` and `docs/screenshots/wk144_hero_agency_qa`.
- Per Jaimie's direction, no more quests or quest templates should be added after WK144 until a playtest pause happens.

## Agent 06 - AIBehaviorDirector / LLM

**Intelligence:** high
**Model/effort:** use the active goal instruction, `gpt-5.4-mini` with `xhigh` effort unless PM overrides.

Task: Make bounty commitments and ambient daily-life motives robust enough that ten idle heroes no longer behave like identical tight-loop units.

Files you MAY edit:

- `ai/**`
- AI-focused tests under `tests/**`
- `.cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json`

Files you MUST NOT edit:

- `game/**`
- `tools/**`
- `assets/**`
- `.cursor/plans/**` except your own log
- version/changelog files

Implementation guidance:

- Start by adding failing tests before the fix where practical.
- Prefer small changes in `ai/task_router.py`, `ai/behaviors/bounty_pursuit.py`, and `ai/behaviors/daily_life.py`.
- Bounty behavior should be checked before rest/home/ambient motives for heroes above a safe survival threshold. A critical or retreating hero may still abandon a bounty.
- If a hero has `target={"type": "bounty", ...}` and `_bounty_commit_until_ms` is still live, `resume_committed_bounty` should preserve/reassert `target_position`, `HeroState.MOVING`, and `intent="pursuing_bounty"` or equivalent. It should not silently leave the hero in `going_home`.
- Daily-life tuning should increase destination spread without chaos. Use existing memory/cooldown/crowding mechanics rather than random per-tick wandering.
- The desired visible result with 10 heroes is a mix: some go to POIs/frontier/lairs, some visit/socialize/rest, some patrol roads/kingdom landmarks, and at least a few move well outside the town bubble.
- Keep WK67 digest stable. The existing activation gate in `try_daily_life` is important; do not remove it casually.

Required tests:

- `tests/test_wk144_bounty_commitment.py`
  - A hero with a live bounty commitment, healthy enough to keep going, and `should_go_home_to_rest()` truthy must resume the bounty rather than route home.
  - A critically wounded hero may still rest/retreat, so the test should not overconstrain survival.
  - A stale/claimed/invalid bounty must not be resumed forever.
- `tests/test_wk144_hero_agency_daily_life.py`
  - Deterministic fixed setup with 10 heroes must produce at least 6 distinct motive/target pairs and at least 5 distinct cluster keys after one decision pass.
  - Include buildings for castle, inn, marketplace, homes/guilds, POIs, lairs/enemies, and frontier tiles.
  - Assert at least one non-town/outward target is more than 15 tiles from castle.
  - Assert motives include representatives of rest/home/social, POI/frontier, and monster/lair/opportunity classes.

Verification:

```powershell
python -m pytest tests/test_wk144_bounty_commitment.py tests/test_wk144_hero_agency_daily_life.py -q
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_ai_bounty.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python -m json.tool .cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json
```

Report root cause and exact behavior rules in your log.

## Agent 05 - GameplaySystemsDesigner

**Intelligence:** medium-high
**Model/effort:** use the active goal instruction, `gpt-5.4-mini` with `xhigh` effort unless PM overrides.

Task: Complete the elite-affix content kit and add content validation for quest chains/boss/elite authoring.

Files you MAY edit:

- `game/content/**`
- gameplay/content tests under `tests/**`
- `.cursor/plans/agent_logs/agent_05_GameplaySystemsDesigner.json`

Files you MUST NOT edit:

- `ai/**`
- `game/ui/**`
- `game/graphics/**`
- `game/audio/**`
- `tools/**`
- `assets/**`
- `.cursor/plans/**` except your own log
- version/changelog files

Implementation guidance:

- Expand `game/content/elite_affixes.py` from 3 to 8 affixes matching the master design kit where possible:
  - `banner_bearer`
  - `ironhide`
  - `frenzied`
  - `skirmisher`
  - `gravebound`
  - `venomous`
  - `gold_taker`
  - `oathbound`
- If a full behavior effect would require systems outside `game/content/**`, add safe data fields/tells/counterplay now and file a follow-up in your log. Do not edit combat/AI for affix mechanics in this sprint unless absolutely necessary.
- Keep stat modifiers modest. Avoid one-shotting heroes or creating runaway elite density.
- Add validation tests rather than unsupported new chain templates. The current chain system has hard-coded per-chain runtime in places, so new chain definitions without handlers are not acceptable.
- Content validation should teach future lower-reasoning agents how to author safely through tests.

Required tests:

- `tests/test_wk144_elite_affix_content.py`
  - Exactly or at least 8 affixes are present.
  - IDs unique; display names/tells/counterplay/descriptions non-empty.
  - Modifiers remain bounded: no huge attack/defense, HP multiplier reasonable, speed multiplier positive and not extreme.
  - `roll_elite_affixes` is deterministic for a fixed spawn key/rng.
  - `apply_elite_affixes` preserves boss names and marks normal enemies visibly as elite.
- `tests/test_wk144_content_validation.py`
  - All `all_chain_defs()` entries have unique `chain_type`, display name, positive reward, tags, phases.
  - Phase IDs are unique within a chain, and phase title/objective/target refs are non-empty.
  - All registry entries map back to their chain type.
  - Existing WK138/WK141/WK142/WK143 chain types remain present.

Verification:

```powershell
python -m pytest tests/test_wk144_content_validation.py tests/test_wk144_elite_affix_content.py -q
python -m pytest tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_boss.py tests/test_wk143_dragon_hunt.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python -m json.tool .cursor/plans/agent_logs/agent_05_GameplaySystemsDesigner.json
```

## Agent 12 - ToolsDevEx

**Intelligence:** medium
**Model/effort:** use the active goal instruction, `gpt-5.4-mini` with `xhigh` effort unless PM overrides.

Task: Add a deterministic screenshot scenario proving hero-agency spread.

Files you MAY edit:

- `tools/**`
- screenshot scenario tests under `tests/**`
- `docs/screenshots/wk144_*`
- `.cursor/plans/agent_logs/agent_12_ToolsDevEx_Lead.json`

Files you MUST NOT edit:

- `ai/**`
- `game/**` production code
- `assets/**`
- `.cursor/plans/**` except your own log
- version/changelog files

Scenario requirements:

- Add `hero_agency_showcase` to the capture scenario registry.
- It should spawn or configure around 10 heroes in a deterministic setup and run long enough for daily-life motives to activate.
- It should include visible POI/frontier/lair/road/castle/town destinations where possible.
- Capture should produce at least one world PNG and, if feasible, a small manifest with hero positions/motives or enough state for tests to assert spread.
- The screenshot should make it visually obvious that heroes are not all clumped in town.

Required tests:

- `tests/test_wk144_hero_agency_capture_scenario.py`
  - Scenario name is registered.
  - Capture metadata or scenario output indicates 10 heroes and multiple destination clusters/motives if such metadata is available.

Verification:

```powershell
python -m pytest tests/test_wk144_hero_agency_capture_scenario.py -q
python tools/capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs/screenshots/wk144_hero_agency_showcase --size 1920x1080 --ticks 1800
python -m json.tool .cursor/plans/agent_logs/agent_12_ToolsDevEx_Lead.json
```

Inspect the generated PNG(s) before claiming done.

## Agent 11 - QA_TestEngineering Lead

**Intelligence:** high
**Model/effort:** use the active goal instruction, `gpt-5.4-mini` with `xhigh` effort unless PM overrides.

Task: Final integrated QA after Agents 06, 05, and 12 land.

Files you MAY edit:

- QA tests only if needed for evidence/coverage
- `docs/screenshots/wk144_*` if re-capturing proof
- `.cursor/plans/agent_logs/agent_11_QA_TestEngineering_Lead.json`

Files you MUST NOT edit:

- production source unless PM sends a repair prompt
- version/changelog files

Required verification:

```powershell
python -m pytest tests/test_wk144_bounty_commitment.py tests/test_wk144_hero_agency_daily_life.py tests/test_wk144_content_validation.py tests/test_wk144_elite_affix_content.py tests/test_wk144_hero_agency_capture_scenario.py -q
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_ai_bounty.py -q
python -m pytest tests/test_wk143_dragon_hunt.py tests/test_wk143_dragon_fire_telegraph.py tests/test_wk143_dragon_rewards.py tests/test_wk126_quest_soak.py::test_soak_all_four_quest_types_complete_and_pay -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs/screenshots/wk144_hero_agency_qa --size 1920x1080 --ticks 1800
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Screenshot inspection must mention:

- Whether heroes are visibly split across multiple areas.
- Whether at least some heroes are away from the town/castle bubble.
- Whether UI/camera overlays are readable and nonblank.

## Send List

Wave 1:

- Agent 06: bounty commitment + daily-life agency.
- Agent 05: elite-affix kit + content validation.

Wave 2:

- Agent 12: screenshot scenario after Agent 06 has landed or at least after its motive names/contracts are stable.

Wave 3:

- Agent 11: final QA.

Do not send Agents 03/08/09/10/13/14/15 unless a wave explicitly discovers a cross-owner blocker.
