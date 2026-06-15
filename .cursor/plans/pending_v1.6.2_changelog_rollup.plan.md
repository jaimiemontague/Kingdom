# Pending Prototype v1.6.2 Changelog Rollup

**Owner:** Agent 13 (SteamRelease_Ops_Marketing) with Agent 01 PM review  
**Created:** 2026-06-15  
**Status:** Pending human authorization for the next version bump  

This file exists because several sprint save-state commits were mistakenly named like public prototype versions (`Prototype v1.6.2` through `Prototype v1.6.5`). Treat those commit messages as historical save-state labels only. They are **not** authorized public release bumps.

Current live stamp at the time this note was created:

- `config.py`: `PROTOTYPE_VERSION = "1.6.1"`
- `CHANGELOG.md`: top live entry is `Prototype v1.6.1`
- `README.md`: references `Prototype v1.6.1`
- Git tags: no `v1.6.2+` tags found

Jaimie's instruction: the next real version bump is **v1.6.2**. Until Jaimie explicitly authorizes that bump, do not edit `config.py`, README version text, release tags, or live changelog headers to claim v1.6.2 has shipped.

---

## Pending v1.6.2 Candidate Contents

These shipped sprint outcomes should be consolidated into the next approved `Prototype v1.6.2` changelog entry instead of being split into separate `v1.6.2`, `v1.6.3`, `v1.6.4`, and `v1.6.5` releases.

### WK138 - Adventure Ledger Foundation

- Multi-phase quest-chain foundation layered onto the existing Herald's Post quest system.
- Adventure Ledger read model and phase/history state for future long-form quests.
- Deterministic tests for quest-chain state, cleanup, AI-view exposure, and UI foundation.

### WK139 - Boss Encounter Core + Elite Affixes

- Reusable boss encounter runtime for named bosses and active boss facts.
- Elite affix foundation with deterministic elite behavior/read-model support.
- Boss/elite AI and render snapshot facts so future UI/visual systems can read encounters without mutating sim state.

### WK140 - Hero Daily Life AI Variety

- Broader daily-life AI intent layer to reduce early-game tight-loop wandering.
- Deterministic motive variety, class/crowding bias, conviction/anti-loop behavior, and bounty stickiness.
- Regression coverage preserving urgent survival/retreat behavior and WK67 determinism.

### WK141 - Blackbanner's Toll

- First complete epic boss quest using the new quest-chain and boss systems.
- Blackbanner chain phases, Rusk Blackbanner, toll-taker elite, reward/completion flow, AI policy, Adventure Ledger UI readability, and visual verification.

### WK142 - Dynamic Rescue & Revenge

- Bounded Blackbanner/Bandit Fortress capture and rescue loop.
- Named-boss kill memory and revenge quest loop.
- More robust hero daily-life behavior around kingdom roaming, POI exploration, monster/boss pressure, rescue/revenge opportunities, rest/home, and castle/Herald's Post visits.
- Adventure Ledger readability for rescue/revenge state plus screenshot-verified UI and boss visual proof.

### WK143 And Later

- If additional quest/boss roadmap sprints ship before Jaimie authorizes v1.6.2, Agent 13 should add their player-facing bullets here before drafting the final changelog entry.
- Do not publish those sprints as automatic `v1.6.x` releases.

---

## Draft Changelog Shape For Agent 13

Do not copy this into `CHANGELOG.md` until PM confirms final QA and Jaimie authorizes the version bump.

```markdown
## Prototype v1.6.2 — Adventure Stories Update

- Quests: **Adventure Ledger and multi-phase quest chains** — heroes can now follow longer adventure arcs with visible phases, history, and completion state.
- Bosses: **Named boss encounters and elite enemies** — major enemies now carry reusable encounter facts, elite traits, and readable boss/elite presentation hooks.
- Heroes: **Richer daily-life AI** — heroes spread across more believable kingdom activities, from roaming and scouting POIs to resting and pursuing meaningful opportunities.
- Adventure: **Blackbanner's Toll** — a first epic boss quest sends heroes through scouting, elite interception, fortress assault, and a named Bandit Lord showdown.
```

Possible fifth bullet if WK142 ships before release:

```markdown
- Consequences: **Rescue and revenge hooks** — captured heroes and boss-killed heroes can create new story opportunities instead of ending as silent failures.
```

---

## Required Authorization Before Live Release Edits

Before moving this into `CHANGELOG.md`, Agent 13 or Agent 01 must confirm:

- Jaimie explicitly approved bumping to `Prototype v1.6.2`.
- Final included sprint list is known.
- `python tools/qa_smoke.py --quick` passed on the release candidate.
- `python tools/validate_assets.py --report` passed if assets/manifests changed since v1.6.1.
- Manual playtest requirements, if any, are documented.

Recommended final commit message after authorization:

```powershell
git commit -m "wk###: Prepare Prototype v1.6.2 release notes"
```

Use the real WK sprint number for the release-note sprint. Do not name the commit `Prototype v1.6.2` unless Jaimie explicitly requests that exact commit-message style.
