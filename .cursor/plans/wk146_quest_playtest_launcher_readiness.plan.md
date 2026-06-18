# WK146 Quest Playtest Launcher Readiness

Date: 2026-06-18
Owner: Agent 01 ExecutiveProducer_PM
Status: Kickoff plan

## Goal

Make the existing multi-phase quest work genuinely playtestable from the live game, without adding new quest content before Jaimie's playtest pause is complete.

The player-facing target is simple:

- Build/select a constructed Herald's Post.
- Open a clear playtest/quest-chain launcher.
- Start one of the existing shipped chains:
  - Relic of the Old Shrine
  - Blackbanner's Toll
  - Ashwing's Hoard
- Immediately see the chain in the quest ledger/board.
- Have spawned heroes and relevant POIs/enemies close enough that Jaimie can test the quest feel in minutes, not after waiting for a whole town to develop.

This sprint is **not** a new content sprint. It is a playtest-readiness sprint for already-built WK138-WK143 systems plus WK144/WK145 hero agency fixes.

## Current Grounding

What exists now:

- `game/systems/quest_chain.py` already exposes real chain methods:
  - `offer_relic_of_the_old_shrine`
  - `start_relic_of_the_old_shrine`
  - `offer_blackbanners_toll`
  - `start_blackbanners_toll`
  - `offer_ashwings_hoard`
  - `start_ashwings_hoard`
- `game/sim_engine.py` owns both `QuestSystem` and `QuestChainSystem`.
- `game/ui/building_panel.py` already shows a `Create Quest` button for constructed Herald's Posts.
- `game/ui/quest_create_panel.py` already has a modal and an embedded active-quest board via `QuestViewPanel`.
- `game/ui/quest_view_panel.py` already knows how to render active quest-chain snapshots.
- Existing screenshot scenarios prove components, but not all of the live player path:
  - `boss_encounter_showcase`
  - `dragon_hunt_showcase`
  - `hero_agency_showcase`
  - `wk133_quest_ui`

The main gap:

- The live Herald's Post flow only creates one-shot WK126 quests.
- The named multi-phase chains are mostly reachable through tests/programmatic setup, not through a player-friendly live trigger.
- `dragon_hunt_showcase` currently uses a synthetic/simple quest-chain snapshot for ledger proof. That is acceptable visual staging, but it is not enough evidence that the same path Jaimie will click in the game works.

## Product Decision

Expose a **Playtest Chains** section inside the Herald's Post quest modal, not a global cheat/debug button.

Reasoning:

- Herald's Post is already the fictionally correct place for quest offers.
- It avoids scattering debug controls across the HUD.
- It lets existing quest-board UI immediately prove the launched chain is visible.
- It keeps the feature useful later: this can evolve into a real quest-chain offer board after playtest.

Recommended UI wording:

- Keep the existing one-shot flow titled `Create Quest`.
- Add a compact second section titled `Story Chains` or `Quest Chains`.
- Buttons:
  - `Relic`
  - `Blackbanner`
  - `Ashwing`
- Each button should show a short prerequisite/status line below it:
  - `Needs Ancient Ruins or falls back to known map target`
  - `Needs Bandit Fortress/Bandit Camp or falls back gracefully`
  - `Needs Dragon Cave or falls back gracefully`
- If a chain is already active, the button should read something like `Active` and not create duplicates.

Avoid in-app explanatory essays. The UI should be clear and compact; the detailed test instructions live in this plan and in Jaimie's checklist, not on screen.

## Scope

In scope:

- Engine action for starting existing quest chains from a constructed Herald's Post.
- Herald's Post UI controls for launching those existing chains.
- Deterministic live-playtest screenshot scenarios that set up:
  - a full-ish town,
  - constructed Herald's Post,
  - 10 heroes,
  - relevant POIs discovered,
  - heroes positioned near POIs,
  - chain started through the same engine action the UI uses.
- Focused tests for failure cases and regressions.
- Manual test script for Jaimie.

Out of scope:

- New quest templates.
- New boss chains.
- New Ashwing/Blackbanner phases.
- Version bump, changelog release header, git tag, or `Prototype vX.Y.Z` language.
- Rewriting hero daily-life AI beyond defects found while proving quest playtest readiness.

## Architecture

### 1. Engine Action

Agent 03 should add a method on `SimEngine`, suggested shape:

```python
def start_quest_chain_from_post(
    self,
    giver_id: str,
    chain_type: str,
    hero_id: str | None = None,
    *,
    auto_accept: bool = True,
):
    ...
```

The exact name may differ if it fits local style better, but the method must be a clear engine action analogous to `create_quest`.

Responsibilities:

- Validate `giver_id` belongs to an active constructed Herald's Post/QuestGiver.
- Validate `chain_type` is one of the player-triggerable existing chains:
  - `relic_of_the_old_shrine`
  - `blackbanners_toll`
  - `ashwings_hoard`
- Build a `SystemContext` from current sim state.
- Resolve `hero_id` when provided.
- Start/offer the chain via `QuestChainSystem`, not by building fake snapshots.
- Return the live `QuestChainInstance`, or `None` if invalid/unavailable.
- Prevent duplicates by returning an existing offered/active chain of that type.
- Use deterministic sim time only.

Important duplicate rule:

```python
for chain in self.quest_chain_system.chains:
    if chain.chain_type == normalized_chain_type and chain.status in ("offered", "active"):
        return chain
```

Do not suppress rescue/revenge chains; the explicit launcher only covers the three player-triggerable chains.

### 2. UI Hook

Agent 08 should extend the existing Herald's Post modal instead of building a new modal.

Preferred implementation:

- In `QuestCreatePanel`, add a compact `Story Chains` section above or beside the active board.
- Add hit rects for each story-chain button.
- On click, call the new `SimEngine` method from Agent 03.
- Show short feedback on failure:
  - `Story chain unavailable.`
  - `Already active.`
  - `Quest system unavailable.`
- On success, keep the modal open and let the active quest board show the chain immediately.

Do not make the user pick a reward tier for story chains in this sprint. The chain definitions already have reward profiles. Avoid treasury escrow unless Agent 03 explicitly implements it as part of the engine action.

### 3. Live Playtest Scenarios

Agent 12 should add deterministic screenshot scenarios that use the real engine action.

Suggested scenarios:

- `quest_chain_launcher_ui`
  - constructed Herald's Post selected,
  - modal open,
  - story-chain buttons visible,
  - active board empty or showing current chain state.

- `quest_chain_live_blackbanner`
  - full-ish town,
  - 10 heroes,
  - constructed Herald's Post,
  - discovered Bandit Fortress or Bandit Camp,
  - heroes placed near town and at/near the fortress,
  - chain launched via `SimEngine.start_quest_chain_from_post`,
  - screenshot shows world plus quest ledger proving `Blackbanner's Toll` is live.

- `quest_chain_live_ashwing`
  - full-ish town,
  - 10 heroes,
  - constructed Herald's Post,
  - discovered Dragon Cave,
  - Ashwing/dragon encounter visible if possible,
  - chain launched via the same engine action,
  - screenshot shows cave/dragon plus quest ledger proving `Ashwing's Hoard` is live.

- Optional if time allows: `quest_chain_live_relic`
  - discovered Ancient Ruins + Shrine,
  - chain launched through engine action,
  - screenshot shows ledger target/phase.

These scenarios should be fast to capture and deterministic. Their goal is not to simulate a full organic playthrough; their goal is to put the live game into a testable state quickly so Jaimie can see and judge the work.

### 4. QA Verification

Agent 11 should verify both code and screenshots.

Minimum gates:

```powershell
python -m pytest tests/test_wk146_quest_chain_launcher.py -q
python -m pytest tests/test_wk126_quest_create_panel.py tests/test_wk138_quest_chain_ui.py tests/test_wk141_blackbanner_ui.py tests/test_wk143_dragon_ui.py -q
python -m pytest tests/test_wk141_blackbanner_chain.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk143_dragon_hunt.py -q
python tools/capture_screenshots.py --scenario quest_chain_launcher_ui --seed 3 --out docs/screenshots/wk146_quest_chain_launcher_ui --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario quest_chain_live_blackbanner --seed 3 --out docs/screenshots/wk146_quest_chain_live_blackbanner --size 1920x1080 --ticks 900
python tools/capture_screenshots.py --scenario quest_chain_live_ashwing --seed 3 --out docs/screenshots/wk146_quest_chain_live_ashwing --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
```

If assets/manifests change unexpectedly:

```powershell
python tools/validate_assets.py --report
```

## Failure Cases To Design For

### Missing Herald's Post

Case: UI or tool calls the engine action with a bogus `giver_id`.

Expected:

- returns `None`,
- creates no chain,
- no exception,
- tests cover this.

### Herald's Post Under Construction

Case: post exists but `is_constructed` is false.

Expected:

- UI button is disabled or launch returns `None`,
- creates no chain,
- player gets concise feedback.

### Duplicate Clicks

Case: Jaimie clicks `Blackbanner` five times.

Expected:

- one live `blackbanners_toll` chain,
- subsequent clicks return/show the existing chain,
- no duplicate bosses/toll-takers if already spawned.

### Missing POI

Case: no Dragon Cave, no Bandit Fortress, no Ancient Ruins.

Expected:

- No crash.
- Prefer graceful fallback if `QuestChainSystem` already supports one.
- If a chain would be meaningless without the POI, return `None` and show feedback.
- Tests should cover at least one missing-target path.

### Undiscovered POI

Case: POI exists but is not discovered.

Expected:

- For playtest launcher, prefer to allow launch if the POI exists. This is a playtest/debug-like affordance inside Herald's Post.
- For future real content, discovery gating can be stricter. Do not overbuild that now.

### No Heroes

Case: Jaimie starts a chain before hiring heroes.

Expected:

- Chain may be offered/unassigned and visible, or launch returns `None` with feedback.
- Whichever behavior Agent 03 chooses must be tested and documented.
- Preferred for playtest: allow offered/unassigned chain so Jaimie can then spawn heroes and watch uptake.

### Specific Hero Assignment

Case: UI/tool passes a hero id.

Expected:

- The chain's `assigned_hero_id` matches that hero when auto-accepted.
- If hero is dead/missing/captured, return `None` or create unassigned based on current `QuestChainSystem` contract; do not assign invalid heroes.

### Existing Rescue/Revenge Chains

Case: Blackbanner rescue/revenge already active.

Expected:

- The story-chain launcher should not delete or suppress rescue/revenge opportunities.
- Launching `blackbanners_toll` should only duplicate-check the same root chain type.

### Save/Load Or Long Session

Case: player starts chain after town has been running a while.

Expected:

- Uses live sim state.
- No assumptions about initial world generation.
- No wall-clock based behavior.

### UI Overflow

Case: 1280x720 and 1920x1080, quest modal with existing one-shot controls plus new story-chain section.

Expected:

- Text does not overlap.
- Buttons remain clickable.
- Active quest board remains visible enough to prove the chain started.
- Screenshots must be inspected, not just generated.

### 3D/Ursina Difference

Case: Pygame screenshot tool passes but live `python main.py --no-llm` feels different.

Expected:

- Pygame capture is required automated proof.
- Jaimie manual playtest still required before more quest content resumes.
- If a bug appears only in live 3D, file it as a follow-up with screenshot/repro.

## Human Playtest Script For Jaimie

After the agents finish and QA is green:

```powershell
python main.py --no-llm
```

Recommended manual sequence:

1. Start a fresh game.
2. Build or use a Herald's Post.
3. Hire/spawn roughly 10 heroes.
4. Select the Herald's Post.
5. Click `Create Quest`.
6. Start `Relic`, `Blackbanner`, or `Ashwing` from the new story-chain section.
7. Confirm the active quest board immediately shows the chain.
8. Watch 5-10 minutes:
   - heroes should not all circle town,
   - heroes should pick varied activities,
   - quest/bounty heroes should commit instead of flickering,
   - named boss/elite moments should be readable,
   - chain phase text should make sense.

Fast visual verification, if Jaimie wants proof before launching:

```powershell
python tools/capture_screenshots.py --scenario quest_chain_launcher_ui --seed 3 --out docs/screenshots/wk146_quest_chain_launcher_ui --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario quest_chain_live_blackbanner --seed 3 --out docs/screenshots/wk146_quest_chain_live_blackbanner --size 1920x1080 --ticks 900
python tools/capture_screenshots.py --scenario quest_chain_live_ashwing --seed 3 --out docs/screenshots/wk146_quest_chain_live_ashwing --size 1920x1080 --ticks 900
```

## Agent Assignments

### Agent 03 TechnicalDirector Architecture

Task: Add the engine action that starts/returns real quest chains from a Herald's Post.

Files you MAY edit:

- `game/sim_engine.py`
- `game/sim/**` only if a typed contract is truly needed
- `tests/test_wk146_quest_chain_launcher.py`

Files you MUST NOT edit:

- `game/ui/**`
- `ai/**`
- `tools/**`
- `assets/**`
- `config.py`
- version/changelog/git metadata

Acceptance:

- Explicit engine method starts/returns existing Relic, Blackbanner, and Ashwing chains.
- Constructed Herald's Post validation works.
- Duplicate launches do not create duplicate root chains.
- Optional `hero_id` assignment works.
- Missing/unconstructed post returns `None`.
- Focused tests pass.

Commands:

```powershell
python -m pytest tests/test_wk146_quest_chain_launcher.py -q
python -m pytest tests/test_wk138_quest_chain_core.py tests/test_wk141_blackbanner_chain.py tests/test_wk143_dragon_hunt.py -q
python tools/qa_smoke.py --quick
```

### Agent 08 UX/UI

Task: Add the Herald's Post story-chain launcher UI.

Files you MAY edit:

- `game/ui/quest_create_panel.py`
- `game/ui/building_panel.py` only if routing/hit rects require it
- focused UI tests under `tests/`

Files you MUST NOT edit:

- `game/sim_engine.py`
- `game/systems/**`
- `ai/**`
- `tools/**`
- `assets/**`
- version/changelog/git metadata

Acceptance:

- Constructed Herald's Post modal shows compact story-chain buttons.
- Buttons call Agent 03's engine action.
- Chain appears in the existing active quest board without closing/reopening the modal.
- Duplicate active chain displays feedback instead of spawning duplicates.
- 1280x720 and 1920x1080 screenshots do not show overlap.

Commands:

```powershell
python -m pytest tests/test_wk126_quest_create_panel.py tests/test_wk138_quest_chain_ui.py tests/test_wk141_blackbanner_ui.py tests/test_wk143_dragon_ui.py -q
python tools/capture_screenshots.py --scenario quest_chain_launcher_ui --seed 3 --out docs/screenshots/wk146_quest_chain_launcher_ui --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario quest_chain_launcher_ui --seed 3 --out docs/screenshots/wk146_quest_chain_launcher_ui_720p --size 1280x720 --ticks 480
python tools/qa_smoke.py --quick
```

### Agent 12 Tools DevEx

Task: Add deterministic live quest-chain screenshot scenarios that use the same engine action as the UI.

Files you MAY edit:

- `tools/screenshot_scenarios.py`
- `tools/capture_screenshots.py` only if scenario registration requires it
- focused scenario tests under `tests/`

Files you MUST NOT edit:

- `game/ui/**`
- `game/sim_engine.py`
- `game/systems/**`
- `ai/**`
- `assets/**` unless unavoidable and then coordinate with Agent 09/15
- version/changelog/git metadata

Acceptance:

- `quest_chain_launcher_ui` shows the actual UI affordance.
- `quest_chain_live_blackbanner` launches the live chain through the engine action and shows ledger/world proof.
- `quest_chain_live_ashwing` launches the live chain through the engine action and shows ledger/world proof.
- Scenario metadata records chain type, active phase, hero count, and target POI id/name.
- Screenshot manifest files include the scenario metadata.

Commands:

```powershell
python -m pytest tests/test_wk146_quest_chain_launcher.py tests/test_wk146_quest_chain_scenarios.py -q
python tools/capture_screenshots.py --scenario quest_chain_launcher_ui --seed 3 --out docs/screenshots/wk146_quest_chain_launcher_ui --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario quest_chain_live_blackbanner --seed 3 --out docs/screenshots/wk146_quest_chain_live_blackbanner --size 1920x1080 --ticks 900
python tools/capture_screenshots.py --scenario quest_chain_live_ashwing --seed 3 --out docs/screenshots/wk146_quest_chain_live_ashwing --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
```

### Agent 05 Gameplay Systems Review

Task: Review the live quest-chain launcher for gameplay correctness after Agent 03/08/12 land.

Files you MAY edit:

- Only focused gameplay-system fixes if a blocker is found and PM explicitly authorizes the follow-up.
- Otherwise log/review only.

Acceptance:

- Blackbanner root chain, rescue, and revenge do not collide.
- Dragon chain does not bypass boss-system invariants.
- Relic chain remains low-risk foundation content.
- No new quest content was added.

Commands:

```powershell
python -m pytest tests/test_wk141_blackbanner_chain.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk143_dragon_hunt.py -q
python tools/qa_smoke.py --quick
```

### Agent 06 AI Behavior Review

Task: Review hero behavior in the new live scenarios, especially the "ants around town" failure Jaimie called out.

Files you MAY edit:

- Only `ai/**` and focused AI tests if a blocker is found and PM explicitly authorizes the follow-up.
- Otherwise log/review only.

Acceptance:

- In the seeded live scenarios, heroes do not all cluster in tiny loops around town.
- Quest/bounty commitments remain sticky enough to be readable.
- Critical safety behavior still interrupts.

Commands:

```powershell
python -m pytest tests/test_wk145_hero_ai_significance_hysteresis.py tests/test_wk144_hero_agency_daily_life.py tests/test_wk144_bounty_commitment.py -q
python tools/capture_screenshots.py --scenario hero_agency_showcase --seed 3 --out docs/screenshots/wk146_hero_agency_regression --size 1920x1080 --ticks 1800
python tools/qa_smoke.py --quick
```

### Agent 11 QA

Task: Final independent verification and screenshot review.

Files you MAY edit:

- QA tests under `tests/`
- own agent log

Files you MUST NOT edit:

- gameplay/UI/tool implementation files unless PM assigns a follow-up fix.

Acceptance:

- All focused WK146 tests pass.
- Relevant WK138-WK145 regressions pass.
- Required screenshots exist, are nonblank, and visibly show the launched chains.
- `qa_smoke --quick` passes.
- Manual playtest checklist for Jaimie is updated or confirmed.

Commands:

```powershell
python -m pytest tests/test_wk146_quest_chain_launcher.py tests/test_wk146_quest_chain_scenarios.py -q
python -m pytest tests/test_wk126_quest_create_panel.py tests/test_wk138_quest_chain_ui.py tests/test_wk141_blackbanner_ui.py tests/test_wk143_dragon_ui.py -q
python -m pytest tests/test_wk141_blackbanner_chain.py tests/test_wk142_dynamic_rescue_gameplay.py tests/test_wk143_dragon_hunt.py tests/test_wk145_hero_ai_significance_hysteresis.py -q
python tools/capture_screenshots.py --scenario quest_chain_launcher_ui --seed 3 --out docs/screenshots/wk146_quest_chain_launcher_ui --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario quest_chain_live_blackbanner --seed 3 --out docs/screenshots/wk146_quest_chain_live_blackbanner --size 1920x1080 --ticks 900
python tools/capture_screenshots.py --scenario quest_chain_live_ashwing --seed 3 --out docs/screenshots/wk146_quest_chain_live_ashwing --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick
```

## Send List

Wave 1:

- Agent 03 TechnicalDirector Architecture: high intelligence, GPT-5.5 high effort.

Wave 2, after Agent 03 lands:

- Agent 08 UX/UI: high intelligence, GPT-5.5 high effort.
- Agent 12 Tools DevEx: high intelligence, GPT-5.5 high effort.

Wave 3, after Agent 08 and Agent 12 land:

- Agent 05 Gameplay Systems review: medium intelligence, GPT-5.5 high effort.
- Agent 06 AI Behavior review: medium intelligence, GPT-5.5 high effort.
- Agent 11 QA final verification: high intelligence, GPT-5.5 high effort.

Do not send to:

- Agent 02, 04, 07, 09, 10, 13, 14, 15 unless a specific blocker emerges.

## Definition Of Done

WK146 is ready for Jaimie playtest when:

- The Herald's Post live UI can launch the three existing root chains.
- Duplicate launches do not spam duplicate chains/bosses.
- The active quest board visibly updates immediately.
- Deterministic screenshot scenarios prove the UI and live chain state.
- `qa_smoke --quick` passes.
- Jaimie receives exact manual playtest steps and screenshot command options.

Do not mark this sprint complete merely because the UI buttons exist. The sprint is complete only when the launcher path, chain state, screenshots, and manual test path all line up.
