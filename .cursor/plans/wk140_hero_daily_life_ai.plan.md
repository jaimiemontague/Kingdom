# WK140 Hero Daily Life AI Variety

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-15  
**Inserted because:** Jaimie playtest/product request after WK139  
**Previous sprint:** WK139 Boss Encounter Core, committed/pushed as `5901505`  
**Sprint status:** Kicked off / implementation delegated  
**PM update:** 2026-06-15 after Jaimie noted the AI felt more robust in earlier v1.4-era builds.

## Mission

Make hired heroes look like people living in a fantasy kingdom instead of ten units scattering into tight local loops around town.

The player-facing goal is simple: when Jaimie starts a new game, spawns around ten heroes, and watches the first few minutes, the heroes should visibly diversify. Some should roam the kingdom, some should explore farther out, some should look for POIs, some should patrol or seek monsters, and some should spend downtime at safe/social places like the castle, inn, market, or home-like buildings.

This sprint intentionally changes default autonomous hero behavior. Do not treat the old early-game movement digest as sacred if it conflicts with the goal. The sacred boundary is **determinism and AI/sim separation**: changed behavior must be deterministic for a fixed seed, tested, and explainable.

## Current Problem

Observed player issue:

- Start game.
- Spawn about 10 heroes.
- Heroes scatter into small, repetitive movement loops around the town.
- The behavior reads as swarmy and artificial, like ants, not adventurers.

Why this matters:

- The game fantasy depends on heroes feeling independent.
- WK138/WK139 added quest chains and bosses, but those systems will feel flat if idle heroes lack believable ambient life.
- The player should enjoy simply watching heroes choose different daily motives.

## v1.4-Era Behavior To Recover

Jaimie's follow-up is important: the desired outcome is not only "add something new"; it is also "restore the kind of hero agency the game already used to have around the 1.4 days."

Agent 06 must perform an AI archaeology pass before implementing:

1. Inspect the v1.4-era changelog and commits:
   - `git log --oneline --decorate --all --grep "v1.4"`
   - `git show c701973:CHANGELOG.md`
   - `git show 0df555a:CHANGELOG.md`
   - `git show c67f3fc:CHANGELOG.md`
   - Use `git ls-tree <commit>:ai` and `git show <commit>:ai/<path>` to inspect old AI files without checking them out.
2. Look specifically for behavior from v1.3.3 through v1.4.4 that created stronger hero agency:
   - v1.3.3: heroes spend realistic time inside buildings, rest at Inns, sometimes get a drink when idle.
   - v1.3.4: heroes prefer nearby monsters over the Inn unless critically low HP.
   - v1.4.1: warriors defend farms/food stands and castle defense has urgent priority.
   - v1.4.2: Hero Conviction System / hysteresis prevents immediate task churn.
   - v1.4.3: physical separation reduces synchronous clumping.
   - v1.4.4: hero agency fixes around physical actions and blacksmith targeting.
   - v1.2.7-v1.2.8: Rangers pursue far/unrevealed bounties and are more prone to black-fog exploration.
3. Do not blindly copy old code. Compare old policy against the current ai/behavior module structure, then modernize the best ideas.
4. Record an "AI archaeology note" in the Agent 06 log:
   - old commit(s)/files inspected
   - behavior patterns recovered
   - behavior patterns intentionally rejected
   - how the modern implementation preserves determinism

The most important v1.4 concept to recover is **conviction**: once a hero chooses a meaningful activity, they should commit long enough for the player to perceive it unless a higher-priority need interrupts. The current ant-like loop is probably not just "bad target selection"; it is also weak commitment and weak target diversity.

## Product Vision

Heroes should have a light daily-life motive layer that chooses what kind of thing they want to do when they are not forced by urgent needs.

Examples:

- A ranger says, effectively: "I am going to range beyond the farms and uncover fog."
- A warrior says: "I will patrol the road and challenge nearby monsters."
- A rogue says: "I will nose around that ruin and maybe find something valuable."
- A low-health hero says: "I am going to rest somewhere safe."
- A social or cautious hero says: "I will linger at the castle or inn for a bit."
- A greedy hero says: "I will check posted quests, bounties, POIs, and loot chances."

This should not become direct player control. The player still funds opportunities; heroes choose.

## Behavior Palette

Implement a small, deterministic palette of ambient motives. Names can differ in code, but the behavior should cover these concepts:

1. `kingdom_roam`
   - Hero travels to a different building, road-adjacent area, or visible kingdom landmark.
   - Should avoid immediately retargeting the same tiny area.

2. `wilderness_explore`
   - Hero chooses a farther fog/frontier target.
   - Rangers should score this higher.

3. `poi_scout`
   - Hero chooses a known/discovered POI or suspected POI direction.
   - Rogues/rangers/curious personalities should score this higher.

4. `monster_patrol`
   - Hero moves toward known nearby enemies, lairs, or dangerous frontier edges if not badly wounded.
   - Warriors should score this higher.

5. `safe_rest`
   - Hero goes to castle, inn, home-like building, shrine/temple, or other safe recovery point.
   - Low health, low morale, recent combat, or long outing should score this higher.

6. `social_linger`
   - Hero spends a short deterministic dwell period at castle/inn/market/guild-like buildings.
   - Should create visible non-combat life and reduce constant jitter.

7. `opportunity_check`
   - Hero drifts toward Herald's Post, bounty source, market, blacksmith, or quest-giver when idle.
   - Greedy/equipped heroes can score this higher.

8. `home_or_guild_time`
   - Hero returns to their guild/home-like safe base for a deterministic rest, training, prayer, study, or social pause.
   - Should not mean "everyone goes home immediately"; it is a downtime motive with cooldown and low score when active opportunities exist.

9. `road_watch`
   - Hero wanders along roads, kingdom edges, or routes between buildings, making the kingdom feel patrolled instead of only orbiting a single origin.
   - Warriors and guards-adjacent personalities can score this higher.

## Non-Negotiable Design Rules

- Urgent survival still wins: combat, fleeing, healing, hunger/critical needs, active quests, and accepted bounties should not be overridden by ambient life.
- Bounty commitment must be fixed/preserved: when a hero accepts a bounty, ambient daily-life choices must not immediately reprioritize over it and send the hero home.
- Recover v1.4-style conviction/hysteresis: heroes should not churn tasks every few ticks, and ambient tasks need minimum commitment windows.
- No wall-clock time and no global random.
- Use existing AI RNG/deterministic named RNG patterns.
- Avoid per-frame broad scans. Cache or score at decision moments/cooldowns.
- Do not let all heroes make the same ambient choice at the same time.
- Add anti-loop memory: recent targets/tiles/motives should cool down per hero.
- Add spacing pressure: if several heroes are already near a candidate area, reduce its score.
- Ambient choices should have minimum dwell/travel commitments so heroes do not twitch between choices.
- LLM may describe motives if relevant, but sim/AI code owns the behavior.

## Intended Implementation Shape

Primary owner is Agent 06 in `ai/**`.

Suggested architecture:

- Add an ambient motive scorer module such as `ai/behaviors/daily_life.py` or equivalent.
- Keep scoring data-driven and small:
  - hero class
  - health/supplies/recent combat
  - nearby enemies/lairs
  - known POIs
  - buildings/safe places
  - recent motive/target history
  - hero id/name/personality seed
- Add per-hero lightweight memory fields only if needed:
  - last ambient motive
  - last ambient target tile/entity
  - motive cooldown until sim-ms
  - recent target ring/list

Suggested scoring shape:

```python
# Example only; Agent 06 should fit current code style.
candidate = AmbientCandidate(
    motive="wilderness_explore",
    target_xy=(x, y),
    base_score=20,
    urgency_rank="ambient",
    commit_ms=25000,
)
score = base_score
score += class_bias(hero, motive)
score += personality_bias(hero, motive)
score += distance_band_bonus(hero, target_xy)
score -= recent_target_penalty(hero, target_xy)
score -= crowding_penalty(other_hero_targets, target_xy)
score -= danger_penalty_if_wounded(hero, target_xy)
```

The exact data structure can differ, but each score should be explainable in tests. Prefer a small list of scored candidates over deeply nested if/else blocks.

If Agent 06 needs non-AI state support that belongs outside `ai/**`, they must report the exact need. Agent 05 may then add minimal hero/entity support. Do not let Agent 06 casually edit gameplay/entity files.

## Scope

In scope:

- A richer no-LLM/base autonomous ambient behavior layer.
- Deterministic variation across 10 heroes in early-game conditions.
- Class/personality weighting.
- Anti-loop and spacing heuristics.
- POI/enemy/frontier/safe-place target selection using existing read-model facts.
- Tests proving variety and determinism.
- Screenshot or observe-style verification that early heroes spread into multiple meaningful activities.

Out of scope:

- New buildings.
- Full Sims-style needs.
- Romance/friendship systems.
- Party formation.
- New quest content.
- New art.
- LLM-only behavior that does nothing in `--no-llm`.

## Definition Of Done

WK140 is done only when all are true:

- In a deterministic test with around 10 heroes, early idle heroes choose at least 4 distinct ambient motive categories within the first few in-game minutes.
- No more than a small majority of heroes choose the same tiny local target cluster unless an urgent event justifies it.
- Heroes can choose visible farther targets: fog/frontier, POI, enemies/lairs, and safe/social buildings.
- Accepted bounty heroes continue pursuing their bounty unless a truly higher-priority condition interrupts; ambient life must not send them home immediately.
- Conviction/hysteresis is demonstrable: an ambient hero keeps a selected motive/target for a meaningful travel/dwell window instead of retargeting in a tight loop.
- Low-health heroes prefer safe_rest over monster_patrol/explore.
- Warriors bias toward patrol/monster work, rangers toward frontier/explore, rogues toward POI/opportunity work, while still allowing overlap.
- Anti-loop memory prevents immediate repeated retargeting to the same small tile/area.
- Existing urgent behaviors remain intact: combat, healing, active quest-chain continuation, boss/quest handling, shopping, accepted bounties.
- Behavior is deterministic for a fixed seed.
- Any WK67 digest change is explicitly explained as expected behavior change, not accidental nondeterminism. If a digest pin must update, Agent 06/11 must prove repeated deterministic stability and record old/new evidence.
- `python tools/qa_smoke.py --quick` passes.
- Agent 06 log includes an AI archaeology note for v1.4-era behavior reviewed and recovered/adapted.

## Required Verification Commands

```powershell
python -m pytest tests/test_wk140_hero_daily_life_ai.py -q
python -m pytest tests/test_wk140_hero_ambient_distribution.py -q
python -m pytest tests/test_wk140_hero_urgent_behavior_preserved.py -q
python -m pytest tests/test_wk140_bounty_commitment_regression.py -q
python -m pytest tests/test_wk138_quest_chain_ai_policy.py tests/test_wk139_boss_ai_view.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

If screenshot/observe support exists for early hero behavior:

```powershell
python tools/capture_screenshots.py --scenario hero_daily_life_showcase --seed 3 --out docs/screenshots/wk140_hero_daily_life --size 1920x1080 --ticks 1200
```

If that scenario does not exist, Agent 11 should provide a deterministic observe report or request Agent 12 to add a small scenario.

## Agent 06 Assignment

Task: Replace the lame early-game idle swarm with a deterministic hero daily-life motive layer.

Files you MAY edit:

- `ai/**`
- `tests/test_wk140_hero_daily_life_ai.py`
- `tests/test_wk140_hero_ambient_distribution.py`
- `tests/test_wk140_hero_urgent_behavior_preserved.py`
- your Agent 06 log

Files you MUST NOT edit:

- `game/entities/**`
- `game/systems/**`
- `game/sim/**`
- `game/ui/**`
- `game/graphics/**`
- `tools/**`
- `config.py`

Implementation guidance:

- First do the v1.4-era AI archaeology pass described above. This is mandatory, because Jaimie specifically remembers earlier hero AI feeling more robust.
- Then identify the current idle/default behavior path and add the ambient motive layer there.
- Do not disturb urgent handlers unless required to make priority ordering explicit.
- Preserve/fix bounty commitment: accepting a bounty should create a committed pursuit that ambient motives cannot immediately overwrite.
- Recover/modernize conviction/hysteresis from v1.4.2 so heroes commit long enough to read as intentional.
- Use motive cooldowns and per-hero recent target memory.
- Use class/personality weighting.
- Use spacing pressure to avoid all heroes picking the same local target.
- Use existing movement/intents; do not invent new sim commands if existing move/explore/patrol primitives can express the behavior.
- Keep target choice deterministic. If a random tie-break is needed, use existing AI deterministic RNG patterns and draw only when an ambient decision is actually made.
- Expose motive names in a debug/test-friendly way if existing intent/reason fields support it.

Acceptance:

- Agent 06 log contains the AI archaeology note with old commits/files inspected and recovered behavior decisions.
- Tests show 10 heroes split across at least 4 motive categories.
- Tests show accepted bounty heroes do not immediately reprioritize home/ambient behavior.
- Tests show conviction/hysteresis prevents rapid retarget loops.
- Tests show low-health heroes avoid dangerous motives.
- Tests show class bias without hard-locking each class.
- Tests show repeated same-seed runs choose the same motive/target summary.
- Existing quest/boss AI tests still pass.

Commands:

```powershell
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_wk140_hero_ambient_distribution.py tests/test_wk140_hero_urgent_behavior_preserved.py -q
python -m pytest tests/test_wk140_bounty_commitment_regression.py -q
python -m pytest tests/test_wk138_quest_chain_ai_policy.py tests/test_wk139_boss_ai_view.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python -m json.tool .cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json
```

## Agent 05 Conditional Assignment

Only activate Agent 05 if Agent 06 reports that minimal non-AI support is required.

Possible support:

- lightweight hero ambient-memory fields if they belong on hero entities
- safe-place classification if existing building facts are insufficient
- small test fixtures for hero home/rest/safe social targets

Agent 05 must not change AI scoring policy. Agent 06 owns the behavior.

## Agent 11 Assignment

Task: Verify that heroes visibly behave less like ants.

Files you MAY edit:

- `tests/**`
- `docs/screenshots/wk140_*`
- your Agent 11 log

Files you MUST NOT edit:

- production game code unless PM sends a separate fix prompt
- `ai/**` unless a QA-only test helper pattern already exists and is clearly allowed

Verification requirements:

- Run the required WK140 tests.
- Run `qa_smoke`.
- Compare early-game distribution: around 10 heroes should produce several different motives/targets.
- Verify the bounty-commitment regression: accepted bounty heroes do not instantly abandon bounty pursuit for home/ambient behavior.
- Verify conviction/hysteresis: a hero does not constantly retarget the same tiny local loop when no urgent condition exists.
- If WK67 digest changes, verify deterministic repeated result and report whether the change matches the sprint's intentional behavior change.
- If screenshot scenario exists, capture and inspect it. If not, provide an observe-style text report with motive counts and representative hero targets.

Commands:

```powershell
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_wk140_hero_ambient_distribution.py tests/test_wk140_hero_urgent_behavior_preserved.py -q
python -m pytest tests/test_wk140_bounty_commitment_regression.py -q
python -m pytest tests/test_wk138_quest_chain_ai_policy.py tests/test_wk139_boss_ai_view.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

Final report must say:

- PASS/FAIL for variety, anti-looping, class bias, urgent behavior preservation, determinism, WK67, and qa_smoke.
- PASS/FAIL for bounty commitment and v1.4-style conviction/hysteresis.
- Whether the first few minutes look less swarmy by evidence, not vibes.
- Any owner-specific follow-up.

## PM Close Checklist

- Read Agent 06 and Agent 11 logs.
- Confirm tests prove behavior variety, not just code existence.
- Confirm any digest change is intentional and deterministic.
- Commit and push before returning to WK141 First Epic Boss Quest.
