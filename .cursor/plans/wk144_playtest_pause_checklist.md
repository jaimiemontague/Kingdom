# WK144 Playtest Pause Checklist

**Owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-16
**Status:** Ready for Jaimie playtest
**Related commits:** `0b9bd2d wk144: Hero Agency and Content Tuning`, `f5a88ee wk144: Record Playtest Pause`

## Purpose

This is the required pause after WK144. Do not start WK145 quest/content work from the hero quest/boss roadmap until Jaimie has played the current build and given feedback.

The playtest should answer one question first:

Does the game now feel more like a living kingdom of adventurers, or do heroes still feel like a swarm of identical units looping near town?

## Do Not Do Before This Playtest

- Do not add new quests.
- Do not add new quest templates.
- Do not add new boss-chain content.
- Do not expand Sprint F with the originally proposed 3-5 extra chain definitions.
- Do not bump versions or changelog release numbers without Jaimie's explicit authorization.

Allowed before the playtest:

- Run verification commands.
- Prepare playtest notes/checklists.
- Fix a severe regression if Jaimie or QA finds one.
- Make non-quest stabilization changes only if they are necessary to make the current WK144 build playable.

## Recommended Setup

From repo root, PowerShell:

```powershell
python main.py --no-llm
```

Use a fresh game. Keep the terminal visible if possible so the last lines can be copied if something breaks.

Suggested first run:

- Spawn or hire around 10 heroes.
- Let the game run for 8-12 minutes.
- Use normal player behavior: build a little, place bounty flags when threats appear, open hero panels, inspect the quest board, and watch boss/quest moments if they appear.

Optional second run:

- Repeat with a different seed or a different early build order.
- Try to create more pressure: bounties near monsters/lairs, wounded heroes, and multiple available activities.

## Primary Things To Judge

### 1. Hero Daily Life Feel

Expected:

- Heroes should split into several different activities instead of all circling one tight town area.
- Some heroes should move away from the town/castle bubble toward roads, POIs, fog/frontier, monsters, lairs, or other opportunity spaces.
- Some heroes should behave like people: rest, go home/guild/inn, linger around the castle/town, shop/eat, or recover when wounded.
- Different heroes/classes should not feel perfectly identical.

Possible issue to report:

- "10 heroes still clump or orbit in a tiny area after several minutes."
- "Heroes explore once, then all snap back home."
- "Heroes ignore obvious POIs/monsters/lairs for long stretches."
- "Heroes wander too randomly and ignore survival or threats."

Evidence that helps:

- Approximate time in-game.
- Number of heroes alive.
- Whether enemies/lairs/POIs were visible.
- Screenshot of the map if the clump or weird spread is visible.

### 2. Bounty Flag Commitment

Expected:

- A healthy hero who accepts/responds to a bounty should keep pursuing it long enough to feel committed.
- The hero should not immediately reprioritize home/rest/ambient behavior unless genuinely low health or blocked by a valid urgent condition.
- Critically wounded heroes may still retreat, rest, or heal. That is intended.

Try:

- Place bounty flags near visible enemies or threats.
- Watch one hero who appears to respond.
- Follow that hero for 30-90 seconds.

Possible issue to report:

- "Hero accepts/responds to bounty, then immediately goes home while healthy."
- "Bounty target remains valid, but hero drops it for idle wandering."
- "Multiple heroes start and abandon the same bounty loop repeatedly."

Evidence that helps:

- Hero name/class/health.
- Bounty target location and enemy type.
- What the hero did immediately after accepting.
- Screenshot or terminal tail if there is an obvious state label.

### 3. Existing Quest/Boss Loop Sanity

Expected:

- Existing shipped chains remain understandable and stable:
  - Relic of the Old Shrine.
  - Blackbanner's Toll.
  - Blackbanner Rescue.
  - Blackbanner Revenge.
  - Ashwing's Hoard.
- Quest board/phase text should explain the current objective.
- Boss names/status/telegraphs should be readable enough to understand what is happening.
- Dynamic rescue/revenge should feel like a consequence of real game events, not random story text.

Do not worry about testing every chain exhaustively in one session. Prefer a normal playtest where you notice whether the systems appear coherent.

Possible issue to report:

- "Quest phase stuck after objective was visibly completed."
- "Boss died but quest did not advance."
- "Quest board shows a target that does not exist."
- "Rescue/revenge appeared without a real capture/death event."
- "UI text overlaps badly or hides key controls."

Evidence that helps:

- Chain name.
- Current phase title/objective.
- Hero name.
- Boss/enemy name if relevant.
- Screenshot of quest board or boss UI.

### 4. Elite Enemy Readability

Expected:

- Elite enemies should have readable names/tells/counterplay hooks.
- Affixes should not feel wildly unfair or invisible.
- Elite density should not flood the map.

Possible issue to report:

- "Elite modifier is impossible to understand visually."
- "Too many elites are alive at once."
- "An affix feels unfair or has no counterplay."

Evidence that helps:

- Elite name/affix if visible.
- What happened in the fight.
- Screenshot if the tell is unreadable.

### 5. Performance And UI Feel

Expected:

- The build should remain close to the accepted smooth Mythos/v1.6.0 feel.
- Quest/boss/hero UI should remain readable at normal desktop size.
- No repeated stutter should appear just from 10 heroes choosing daily-life activities.

Possible issue to report:

- "Performance degrades after a specific quest/boss starts."
- "Performance degrades when many heroes are idle."
- "UI text overlaps or important buttons are hidden."

Evidence that helps:

- Approximate time since start.
- Hero/enemy count if known.
- What was happening when the slowdown began.
- Screenshot for UI problems.

## Suggested Notes Format

Use this compact format when reporting:

```text
Build/commit: f5a88ee or current main
Run length:
Heroes:
What felt better:
What still felt wrong:
Worst bug/regression:
Screenshot path(s):
Terminal tail:
```

For each bug:

```text
Title:
Repro:
Expected:
Actual:
How often:
Evidence:
```

## Agent 01 Triage After Playtest

When Jaimie returns with feedback, Agent 01 should not blindly continue the old roadmap. Triage in this order:

1. Severe regressions that block play.
2. Hero agency/bounty feel issues from WK144.
3. Quest/boss correctness bugs in already-shipped chains.
4. UI/readability issues that make playtest evidence hard to interpret.
5. Only after the above are stable: decide whether to resume roadmap content and what the next quest/boss sprint should be.

If feedback says "heroes are still swarmy," assign Agent 06 a narrow non-quest sprint:

- improve long-distance destination selection,
- add stronger anti-clump/cooldown behavior,
- enrich home/guild/inn/castle downtime,
- preserve bounty and urgent survival priority,
- screenshot-verify 10-hero spread.

If feedback says "bounties still fail," assign Agent 06 first, with Agent 11 verification, before any quest-content work.

If feedback says "quests/bosses are buggy," assign the owning agent by file lane:

- Agent 05 for `game/systems/**` gameplay behavior.
- Agent 06 for `ai/**` decision/prompt behavior.
- Agent 08 for `game/ui/**`.
- Agent 09 for `game/graphics/**`.
- Agent 12 for capture/tooling.
- Agent 11 for QA scenarios and regression tests.

## Verification Commands For Agents

Before any post-playtest fix claims done, use the relevant focused tests plus:

```powershell
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

For bounty/AI fixes:

```powershell
python -m pytest tests/test_wk144_bounty_commitment.py tests/test_wk144_hero_agency_daily_life.py -q
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_ai_bounty.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs/screenshots/post_playtest_hero_agency --size 1920x1080 --ticks 1800
```

For quest/boss fixes:

```powershell
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk139_boss_encounters.py tests/test_wk141_blackbanner_chain.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk143_dragon_hunt.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

If the fix changes visible UI/graphics, capture screenshots and inspect the PNGs before closing.
