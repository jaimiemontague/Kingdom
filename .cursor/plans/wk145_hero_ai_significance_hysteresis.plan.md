# WK145 Hero AI Significance + Hysteresis

**Owner:** Agent 01 (ExecutiveProducer_PM)
**Sprint ID:** `wk145_hero_ai_significance_hysteresis`
**Created:** 2026-06-16
**Status:** Complete / final gates passed
**Scope Type:** Non-quest stabilization during the WK144 playtest pause.

## Player Problem

Jaimie's WK144 behavior playtest was broadly good, but heroes sometimes flicker between behaviors as if they are being tugged by several small motives every frame. The intended feel is more confident:

- A hero should usually continue the current behavior.
- A new behavior should take over only when it is meaningfully more significant than the current behavior.
- Small score noise should not cause visible 30x/second target/intent switching.
- Critical survival still wins instantly. Low health in or near danger must override any existing commitment.

## Product Goal

Give base AI a significance/hysteresis layer so heroes feel determined rather than wishy-washy.

The player-facing outcome is not "heroes never change their mind." The outcome is:

- routine ambient motives are sticky for a short, understandable window,
- a stronger motive can still overwhelm the current one,
- urgent danger/critical health bypasses hysteresis,
- behavior traces show a sane number of switches over time.

## Ownership

Agent 01 may edit this plan and PM logs only.

Agent 06 owns implementation and AI-focused tests.

Agent 11 may verify after Agent 06 if needed.

## Agent 06 Scope

Files you MAY edit:

- `ai/**`
- `tests/test_wk145_hero_ai_significance_hysteresis.py`
- existing AI tests only if needed to adapt assertions
- `.cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json`

Files you MUST NOT edit:

- `game/**`
- `tools/**`
- `assets/**`
- `config.py`
- `main.py`
- version/changelog files
- `.cursor/plans/**` except your own Agent 06 log

## Implementation Guidance

Start with `ai/behaviors/daily_life.py`; it already has:

- per-hero ambient memory in `_AMBIENT_MEMORY`,
- motive scores via `score_daily_life_candidate`,
- commit windows via `commit_until_ms`,
- candidate application via `_apply_ambient_candidate`,
- continuation via `_reapply_ambient_target`.

The likely fix is a small significance/hysteresis layer around ambient motive selection, not a broad rewrite.

Recommended design:

- When a hero has an active ambient motive in memory, calculate an approximate "current behavior significance" each time daily life evaluates.
- Compare the best new candidate score against the current behavior's significance.
- If the current commit window is still valid, continue current behavior unless:
  - current target is invalid/completed/dead,
  - the new best candidate exceeds current significance by a meaningful threshold,
  - urgent survival/danger bypass applies.
- Record enough trace data in ambient memory to prove behavior changes over time:
  - `active_motive`
  - `active_target_key`
  - `active_significance`
  - `last_switch_ms`
  - `switch_count`
  - a bounded `behavior_trace` list of `{t, from, to, reason, significance_delta}`.
- Keep the trace deterministic and small. Suggested cap: last 20 entries.
- Do not introduce wall-clock time or global RNG. Use sim time and existing deterministic score functions.
- Do not block critical safety. A critically low-health hero should switch immediately to safety/rest/retreat behavior even if a previous motive was committed.

Suggested constants:

- minimum ambient switch threshold: around `6.0` score points.
- minimum ambient dwell time before non-urgent switching: around `8_000` sim ms.
- critical health bypass threshold: `health_percent <= 0.25`.
- low health in danger bypass threshold can use existing behavior if already present; do not overconstrain the value if current systems already define it.

Important: preserve WK67 determinism. The daily-life layer already has an activation gate at 6 seconds; do not remove it.

## Required Test Design

Create `tests/test_wk145_hero_ai_significance_hysteresis.py`.

The test should include a behavior trace over time, not just a one-shot decision.

Minimum tests:

1. **No flicker under near-tie pressure**
   - Build a deterministic view with one hero and several plausible daily-life candidates.
   - Tick `daily_life.try_daily_life` through a sequence of sim timestamps, such as 20_000, 20_500, 21_000, ... 30_000.
   - Mutate the view slightly or use candidate scores that would previously invite small motive changes.
   - Assert the hero does not switch behavior repeatedly within the dwell window.
   - Assert memory `switch_count` remains low, for example `<= 1` for the window.
   - Assert `behavior_trace` timestamps are monotonic and contain no rapid A/B/A flicker.

2. **Significant new motive can overwhelm current behavior**
   - Start a hero on a safe/rest/social/roam ambient behavior.
   - Introduce a clearly stronger non-critical candidate, such as a rescue/revenge/monster opportunity with much higher score.
   - Advance time enough or ensure the score delta exceeds the threshold.
   - Assert the hero switches exactly once and the trace records the switch with positive `significance_delta`.

3. **Critical health bypasses hysteresis instantly**
   - Start a hero on an exploration or monster/road motive.
   - Set `hp/max_hp` to critical while a safe rest/home candidate exists.
   - Without waiting for dwell time or commit expiry, call `try_daily_life`.
   - Assert the hero switches to `safe_rest` or an equivalent safety motive immediately.
   - Assert the trace reason records an urgent/safety bypass.

4. **Existing WK144 spread still holds**
   - Either run or rely on existing `tests/test_wk144_hero_agency_daily_life.py`.
   - Do not make everyone sticky to the same starting activity.

## Verification Commands

Agent 06 must run from repo root, PowerShell:

```powershell
python -m pytest tests/test_wk145_hero_ai_significance_hysteresis.py -q
python -m pytest tests/test_wk144_hero_agency_daily_life.py tests/test_wk144_bounty_commitment.py -q
python -m pytest tests/test_wk140_hero_daily_life_ai.py tests/test_wk140_hero_ambient_distribution.py tests/test_wk140_hero_urgent_behavior_preserved.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python -m json.tool .cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json
```

PM final verification should include:

```powershell
python tools/qa_smoke.py --quick
```

If visible behavior needs screenshot evidence, rerun:

```powershell
python tools/capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs/screenshots/wk145_hero_ai_significance --size 1920x1080 --ticks 1800
```

## Definition Of Done

- A deterministic behavior-trace test proves ambient behavior does not flicker under near-tie pressure.
- A stronger motive can still switch behavior when it overwhelms the current one.
- Critical low-health safety bypass switches immediately.
- Existing WK140/WK144 hero-agency and bounty tests still pass.
- WK67 passes.
- Agent 06 log is updated and valid JSON.
- PM runs `qa_smoke --quick` before commit if code changed.
- No quest content, quest templates, version bump, or changelog release bump is added.

## Closeout

WK145 is complete after Agent 06 implementation and PM verification:

- `tests/test_wk145_hero_ai_significance_hysteresis.py` added timestamped behavior-trace coverage.
- `python -m pytest tests\test_wk145_hero_ai_significance_hysteresis.py -q` passed with `4 passed`.
- WK144 hero agency/bounty gates passed with `7 passed`.
- WK140 daily-life/ambient/urgent gates passed with `11 passed`.
- WK67 passed with `10 passed`.
- `python tools\capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs\screenshots\wk145_hero_ai_significance --size 1920x1080 --ticks 1800` wrote and PM inspected two readable PNGs.
- `python tools\qa_smoke.py --quick` passed; unit suite reported `1990 passed, 5 skipped, 1 xfailed`, and all smoke scenarios exited 0.
- No quest content, quest template, version, or changelog release bump was added.
