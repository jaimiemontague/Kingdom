# Future Hero Quest & Boss Deepening Plan

**Owner:** Agent 01 (ExecutiveProducer_PM)  
**Created:** 2026-06-14  
**Status:** Paused for Jaimie playtest after WK144; do not add more quests or quest templates until playtest feedback
**Source docs reviewed:** `.cursor/plans/future_hero_development_ideas.md`, `.cursor/plans/Dynamic_Quests.md`, `.cursor/plans/pois_proposal.md`, `.cursor/plans/pois_multisprint_roadmap.md`, `.cursor/plans/wk126_quest_giving_npcs.plan.md`, `.cursor/plans/wk130_hero_world_roadmap.plan.md`, `.cursor/plans/wk137_initial_goblin_wave.plan.md`, current PM hub and changelog notes.

This plan expands `future_hero_development_ideas.md` items **#3 Multi-Phase Quests** and **#4 Named Bosses & Elite Enemies** into a practical multi-sprint feature program. It assumes the replacement Agent 01 and the worker agents do **not** share this planning context, so the task breakdowns below are intentionally explicit.

If Jaimie activates agents from this plan through the AI Studio flow, use **GPT-5.5 with high effort** for every high-risk implementation or design task called out below.

**Execution note, 2026-06-14:** Jaimie directed autonomous execution using **gpt-5.4-mini with xhigh effort** for subagents. Agent 01 kicked off WK138 as the first implementation sprint in `.cursor/plans/wk138_adventure_ledger_foundation.plan.md` and the PM hub sprint key `wk138_adventure_ledger_foundation`.

**Execution note, 2026-06-15:** WK138-WK144 have shipped and pushed through `0b9bd2d wk144: Hero Agency and Content Tuning`. The pushed program mapping is:

- WK138 / Sprint A: Adventure Ledger Foundation.
- WK139 / Sprint B: Boss Encounter Core.
- WK140: Hero Daily Life AI recovery and bounty commitment foundation.
- WK141 / Sprint C: Blackbanner's Toll epic boss quest.
- WK142 / Sprint D: Dynamic Rescue and Revenge.
- WK143 / Sprint E: Dragon Hunt Showcase.
- WK144 / Sprint F subset plus Sovereign add-on: bounty commitment hardening, hero agency tuning, elite affix kit, content validation, and screenshot proof.

**Playtest hold, 2026-06-15:** Jaimie explicitly directed: after WK144, do not add more quests or quest templates until there is a pause for Jaimie to playtest. The next Agent 01 may run verification, playtest-prep, bugfix, or non-quest stabilization work if needed, but must not launch a new quest-chain/content-template sprint until playtest feedback arrives.

---

## Current Capability Review

The old brainstorm is directionally right, but the game has moved forward:

- **Already shipped in v1.6.1:** items/inventory, loot drops, per-POI loot, five additional POIs including Dragon Cave, nearby POIs in LLM context, Herald's Post, Quest-Giver NPC, four one-shot quest types, LLM accept/decline, reward escrow, active quest board, and quest UI.
- **Currently in WK137 worktree:** an initial Goblin Warband with **The Goblin Warchief**, per-boss render scale/name fixes, and atlas coverage for boss types. Treat this as very relevant but do not assume it is committed until PM closes WK137.
- **Existing boss baseline:** Bandit Lord, Demon Overlord, Dragon, and Goblin Warchief-style named/stat-bosses exist or are being wired. They are mostly stat blocks plus spawn hooks, loot, scale/name presentation, and toasts. They do **not** yet form a reusable boss encounter system.
- **Existing quest baseline:** quests are still **single-objective contracts**. A hero accepts or declines, pursues one target, and gets gold on completion. There is no chain state, phase history, branch, escalation, quest item handoff, boss climax contract, or hero/boss memory loop.
- **Existing dynamic-quest north star remains correct:** dynamic quests must come from real state, stay deterministic, and never let the LLM invent authoritative facts.

### Where The Plans Fall Short Now

- `future_hero_development_ideas.md` says multi-phase quests and bosses are future concepts; they now need to become a concrete adventure engine layered on the shipped Herald's Post, POIs, items, and boss stat infrastructure.
- `Dynamic_Quests.md` identifies the right primitives, especially rescue/revenge/timer pressure, but stops before architecture and agent-ready implementation tasks.
- `pois_proposal.md` and `pois_multisprint_roadmap.md` describe boss arenas and quest hooks, but several assumptions are stale: Dragon Cave is no longer excluded, items exist, quest-givers exist, and the right next step is not more POI foundation. It is **stateful consequences**.
- `wk126_quest_giving_npcs.plan.md` deliberately scoped out quest chains, item rewards, party coordination, and rare-item quests. Those are the exact follow-up surfaces this plan targets.
- `wk137_initial_goblin_wave.plan.md` proves named bosses can have distinctive stats, size, labels, and balance harnesses, but the warchief is still a single-spawn encounter, not a reusable boss kit.

---

## Product Vision

Make heroes feel like they are living fantasy adventure arcs instead of completing errands.

A great epic quest in Kingdom should have:

1. **A reason to begin:** a discovered POI, a boss threat, a captive hero, a cursed relic, a player's funded charter, or a world event.
2. **A reason to prepare:** danger rating, boss identity, recommended supplies, possible companions, item hooks, or a known weakness.
3. **A sequence of phases:** scout, gather, travel, fight, retrieve, deliver, defend, confront, escape.
4. **A named antagonist or danger:** a boss, elite patrol, ritual, curse, or rival force.
5. **A visible consequence:** map reveal, lair weakened, outpost reclaimed, boss empowered, captive lost, portal opens, reward paid.
6. **A memory:** hero title, boss killer/defeated-by facts, quest log history, LLM-visible story facts.

Inspirations to borrow from, without copying directly:

- **Majesty:** keep indirect control. The player funds opportunities; heroes decide whether to risk themselves.
- **The Witcher contracts:** learn the monster, prepare, exploit a weakness, then confront it.
- **The Hobbit / Smaug:** a boss should be a place, a personality, a hoard, and a weakness, not only HP.
- **Beowulf / Grendel:** revenge and reputation matter. Killing a monster changes how the kingdom talks.
- **Shadow of Mordor:** enemies become memorable when they survive, kill heroes, gain titles, and return changed.
- **Darkest Dungeon / Battle Brothers:** expeditions are fun when risk, supplies, retreat, wounds, and reward are legible.
- **Monster Hunter:** the preparation loop is as important as the fight. Tracks, tells, parts, and elemental weaknesses create strategy.

---

## Non-Negotiable Design Rules

1. **No LLM as game master.** The LLM may choose hero intent, tone, and narration only from structured facts already in the sim/view. It must never decide that a boss died, a relic exists, or a hero is captured.
2. **No direct orders.** The player does not command "Elena, do phase 2." The player funds a chain, raises rewards, posts warnings, chats persuasively, or builds supporting infrastructure.
3. **Every quest phase has observable state.** If the board says "Rescue Aldous," then Aldous must really be trapped, dead, rescued, or timed out. No fake flavor-only objectives.
4. **Phase state is explicit, not scripted soup.** Build reusable phase/objective definitions and a small state machine. Do not hand-code one-off branching logic inside random POI handlers.
5. **Boss abilities are deterministic.** Use sim time and named RNG streams only. No wall clock, no global `random`, no per-frame unbounded scans.
6. **Digest stays byte-identical.** New systems must early-return when there are no active chains/boss encounters/elites. Do not consume AI RNG or named sim RNG on empty/default paths.
7. **Fun before volume.** Ship one excellent 4-phase quest and one excellent 3-phase boss before authoring ten shallow templates.

---

## System Architecture Target

Do **not** replace the existing one-shot `QuestSystem`. Add a layered system that can coexist:

- `QuestSystem`: today's one-shot Herald's Post contracts.
- `QuestChainSystem`: new multi-phase adventure ledger. It may create or wrap one-shot quests as phases, but it owns chain state/history.
- `BossEncounterSystem`: new boss/elite ability and phase controller. It owns encounter runtime, not base combat math.
- `AdventureMemory`: lightweight records attached to heroes, bosses, and the kingdom event log for LLM context and UI history.

### Quest Chain Data Shape

Suggested code shape for Agent 05/03 to adapt, not copy blindly:

```python
@dataclass(frozen=True)
class QuestPhaseDef:
    phase_id: str
    title: str
    objective_type: str  # scout_poi | clear_guards | collect_item | deliver_item | rescue_hero | slay_boss | survive_timer
    target_ref: str      # symbolic key resolved at runtime, e.g. "origin_poi", "boss_lair", "shrine"
    optional: bool = False
    time_limit_ms: int | None = None
    success_event: str | None = None
    failure_event: str | None = None
    next_on_success: str | None = None
    next_on_failure: str | None = None
    narrative_hook: str = ""

@dataclass(frozen=True)
class QuestChainDef:
    chain_type: str
    display_name: str
    source: str  # herald_post | poi_discovery | boss_revenge | world_event
    difficulty_tier: int
    phases: tuple[QuestPhaseDef, ...]
    reward_profile: str
    allowed_hero_classes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

@dataclass
class QuestChainInstance:
    chain_id: int
    def_id: str
    source_entity_id: int | None
    accepted_by_hero_id: int | None
    current_phase_id: str
    phase_started_ms: int
    phase_progress: dict[str, int]
    facts: dict[str, object]       # resolved boss_id, relic_item_id, captive_hero_id, target_poi_id
    status: str                    # offered | active | completed | failed | expired
    history: list[dict[str, object]]
```

Implementation guidance:

- Keep `QuestChainDef` data in a content module such as `game/content/quest_chains.py`.
- Keep runtime mutation in `game/systems/quest_chain.py`.
- Let Agent 03 own any `game/sim/**`, snapshot, `AiGameView`, and `sim_engine.py` registration work.
- Let Agent 05 own gameplay state, completion detectors, rewards, and balance.
- Use string enums or constants for objective types. Avoid typo-prone scattered strings.
- Store `facts` as stable IDs and primitive data, not live object refs, unless existing systems already do that safely.
- Phase resolution should be event-driven when possible (`ENEMY_KILLED`, `POI_INTERACTION`, `QUEST_COMPLETED`, `HERO_DIED`) and low-frequency polling only where needed (`survive_timer`, fog reveal).

### Boss Data Shape

```python
@dataclass(frozen=True)
class BossAbilityDef:
    ability_id: str
    display_name: str
    trigger: str        # cooldown | hp_below | phase_start | minion_count_below | hero_clustered
    cooldown_ms: int
    telegraph_ms: int
    payload: dict[str, object]
    max_uses: int | None = None

@dataclass(frozen=True)
class BossPhaseDef:
    phase_id: str
    starts_below_hp_pct: float
    title: str
    abilities: tuple[str, ...]
    on_enter_event: str | None = None
    add_spawn_budget: int = 0

@dataclass(frozen=True)
class BossDef:
    boss_type: str
    display_name_template: str
    base_enemy_type: str
    difficulty_tier: int
    phases: tuple[BossPhaseDef, ...]
    abilities: tuple[BossAbilityDef, ...]
    loot_table_id: str
    weakness_tags: tuple[str, ...] = ()
    memory_tags: tuple[str, ...] = ()
```

Implementation guidance:

- Keep base stats in the existing enemy stat registry or a parallel boss content registry, but do not duplicate combat math.
- `BossEncounterSystem` should only tick active boss encounters. If there are no active encounters, it returns immediately.
- Use ability cooldowns based on `game.sim.timebase.now_ms()`.
- Use a named RNG stream such as `get_rng("boss_encounters")`, and draw only when an ability/spawn event actually fires.
- Telegraph dangerous abilities through explicit events so Agent 09/08 can render warnings without sim mutation from the renderer.

---

## Boss & Elite Design Kit

### Enemy Tiers

- **Elite:** a normal enemy with 1-2 affixes, a short generated title, slightly better loot, and a visible marker. Example: "Skull-Banner Goblin", "Ironhide Bandit".
- **Lieutenant:** named mini-boss attached to a lair, POI, wave, or quest phase. Has one special ability and one memory record.
- **Boss:** named antagonist with phases, ability telegraphs, boss bar, loot table, quest hooks, and memory/title consequences.

### Elite Affix Pool

Start with 8 deterministic affixes. Each affix should have a stat effect, a visible/readable tell, and a counterplay hint.

| Affix | Effect | Tell | Counterplay |
|---|---|---|---|
| Banner-Bearer | Nearby enemies gain small attack bonus | Banner icon/label | Kill elite first |
| Ironhide | Extra defense, slower speed | Gray tint/shield icon | Wizards/strong gear matter |
| Frenzied | Faster attacks below 40% HP | Red pulse | Burst or kite |
| Skirmisher | Short retreat after taking damage | Dash trail | Rangers chase better |
| Gravebound | Summons 1 weak undead on first hit | Bone glyph | Clear adds |
| Venomous | Small poison over sim-time | Green weapon/particles | Cleric/healing matters |
| Gold-Taker | Steals a little hero gold on hit, drops it on death | Coin marker | Revenge/recovery incentive |
| Oathbound | Gains damage if a named boss is nearby | Boss-color aura | Split fight or kill lieutenant |

Rules:

- Cap elite density. Example: at most 1 elite per spawn batch and at most 6 alive elites globally until tuned.
- Roll elites only during enemy creation, not every tick.
- Elites must reuse base enemy behavior unless their affix explicitly changes it.
- Elite names can use deterministic templates. LLM flavor is optional and non-authoritative.

### Boss Phase Examples

Use these as content targets, not all in Sprint 1.

**The Bandit Lord, "Rusk Blackbanner"**
- Phase 1: Gatehouse. Calls 2-3 bandit guards, throws smoke, retreats if isolated.
- Phase 2: Ransom. If a hero is downed or low HP, threatens a captive; creates a rescue/revenge hook.
- Phase 3: Last Stand. Faster attacks, drops armory loot, conquered fortress becomes a vision/outpost reward.

**The Bone King, "Grimjaw of the Barrow"**
- Phase 1: Grave stir. Skeleton adds rise from marked graves.
- Phase 2: Bone shield. Boss is resistant until two grave totems are broken.
- Phase 3: Death curse. Telegraphed cone/area attack; defeat grants "Barrow-Bane" title.

**The Dragon, "Ashwing the Red"**
- Phase 1: Sleeping hoard. Heroes can scout/steal a scale/clue before waking it.
- Phase 2: Air and fire. Telegraph a line/cone of fire before damage; adds fear/retreat checks.
- Phase 3: Wounded fury. Dragon targets buildings or hoard thieves; defeat grants legendary loot and map-wide renown.

**The Demon Portal**
- Phase 1: Ritual anchors. Destroy or disrupt 2-3 anchor objects while waves spawn.
- Phase 2: Portal maw. Elites spill out; heroes can retreat and re-enter.
- Phase 3: Named demon. Final boss, high risk, endgame reward.

**The Goblin Warchief**
- Phase 1: War banner. Goblins near him get courage/attack bonus.
- Phase 2: Rally. At 50% HP he calls a small reinforcement if goblin count is low.
- Phase 3: Coward's gambit. If alone, he tries to run toward the map edge; killing him during flight gives bonus gold/title.

---

## Multi-Phase Quest Template Kit

### Phase Types To Implement

Implement these as reusable objective handlers:

- `scout_location`: hero reaches a POI/lair and reveals its danger/boss fact.
- `clear_guards`: kill spawned guards or clear a combat POI.
- `collect_item`: obtain a quest item from POI, boss, cache, or enemy.
- `deliver_item`: bring item to shrine, castle, Herald's Post, or NPC.
- `rescue_hero`: free a trapped/downed/imprisoned hero.
- `slay_named_boss`: boss instance defeated by accepted hero or party member.
- `survive_timer`: hold out near a location for N sim-seconds.
- `disrupt_ritual`: interact with N anchor objects or kill ritual elites.
- `return_home`: hero reaches a safe building after completion.

### First Five Quest Chains

Build in this order.

1. **The Barrow Oath**
   - Source: Overgrown Graveyard / Ancient Ruins / Herald's Post.
   - Phases: scout graveyard -> clear risen guards -> break grave totems -> slay Bone King -> deliver signet to shrine/castle.
   - Fun: visible skeleton waves, clear boss weakness, hero title "Barrow-Bane".

2. **Blackbanner's Toll**
   - Source: Bandit Fortress or road ambush.
   - Phases: scout fortress -> intercept tax/gold thief elite -> assault gate -> defeat Bandit Lord -> choose reward: loot armory or claim outpost vision.
   - Fun: feels like a small siege; connects economy, gold theft, and conquest.

3. **Ashwing's Hoard**
   - Source: Dragon Cave discovery.
   - Phases: find scale/clue -> prepare by visiting shrine or buying fire-resist item -> enter cave -> survive fire phase -> slay/drive off dragon -> loot hoard.
   - Fun: preparation matters; Dragon is a place/personality/hoard.

4. **The Captive At The Tower**
   - Source: Wizard's Tower trap or failed POI interaction.
   - Phases: hero captured -> post rescue situation -> rescuer reaches tower -> defeat guardian/solve interaction -> escort/free captive -> optional revenge boss.
   - Fun: dynamic consequence from a real hero state.

5. **The Red Moon Portal**
   - Source: Demon Portal or after two bosses defeated.
   - Phases: discover ritual -> gather two anchor clues from POIs -> disrupt anchors -> hold portal for timer -> defeat named demon.
   - Fun: endgame arc that makes the map feel connected.

---

## Sprint Program

Do not run this whole program as one sprint. Run it as a sequence of shippable vertical slices.

**Current execution hold:** Sprints A-E are represented by WK138-WK143, and the safe validation/tuning portion of Sprint F shipped in WK144. Do not continue Sprint F by adding the originally proposed 3-5 additional chain definitions or any new quest templates until Jaimie has playtested the WK144 build. The only acceptable next work before that playtest is verification, playtest-prep documentation, or bugfix/stabilization that does not add quest content.

### Sprint A: Adventure Ledger Foundation

**Goal:** Add `QuestChainSystem` and ship one non-boss 3-phase chain using existing POI/quest/item capabilities.

**Recommended chain:** "Relic of the Old Shrine": scout Ancient Ruins -> collect relic -> deliver to Shrine/Castle.

**In scope:**
- `QuestChainDef`, `QuestPhaseDef`, `QuestChainInstance`.
- `QuestChainSystem` registered in the sim by Agent 03.
- Phase completion for `scout_location`, `collect_item`, `deliver_item`.
- One content definition in `game/content/quest_chains.py`.
- Hero AI sees active chain context and treats current phase as a long-lived commitment.
- Quest board UI shows a phase timeline and current objective.
- LLM prompt includes structured chain facts.

**Out of scope:**
- Boss phases.
- Multi-hero party coordination.
- Dynamic rescue/revenge.
- More than one chain template.

**Primary agents:**
- Agent 03 (high intelligence): sim registration, snapshots, AI view, event contract.
- Agent 05 (high intelligence): chain system, phase detectors, item/reward handoff.
- Agent 06 (high intelligence): AI commitment/press-on/retreat policy and prompt context.
- Agent 08 (high intelligence): quest board phase timeline.
- Agent 11 (high intelligence): tests, soak, screenshot verification.

**Core tests:**
```powershell
python -m pytest tests/test_wk_next_quest_chain_core.py -q
python -m pytest tests/test_wk_next_quest_chain_ai_view.py -q
python -m pytest tests/test_wk_next_quest_chain_ai_policy.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

**Visual verification:**
```powershell
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/quest_chain_foundation_ui --size 1920x1080 --ticks 480
```

If no existing scenario can show the phase board with an active chain, assign Agent 12 or Agent 11 per ownership to add a deterministic screenshot scenario, then capture:

```powershell
python tools/capture_screenshots.py --scenario quest_chain_foundation --seed 3 --out docs/screenshots/quest_chain_foundation --size 1920x1080 --ticks 900
```

### Sprint B: Boss Encounter Core + Elite Affixes

**Goal:** Create reusable boss/elite mechanics independent of quest chains.

**Recommended boss:** upgrade Bandit Lord or Goblin Warchief into the first true phase boss.

**In scope:**
- `BossDef`, `BossPhaseDef`, `BossAbilityDef` content model.
- `BossEncounterSystem` ticking only active boss encounters.
- Elite affix data and deterministic elite roll at spawn time.
- One boss with 2-3 phases and 2 abilities.
- Boss identity/memory facts: killed hero, defeated by hero, title granted.
- Boss bar or compact boss status UI.
- Telegraph event path for a dangerous ability.

**Out of scope:**
- Full Dragon fight.
- New models/assets unless the existing visuals are unreadable.
- Random roaming bosses.

**Primary agents:**
- Agent 05 (high): boss/elite gameplay logic and balance.
- Agent 03 (high): system registration/event contract/snapshot if needed.
- Agent 09 (medium-high): telegraph visuals, boss markers, render guardrails.
- Agent 08 (medium-high): boss bar/status UI.
- Agent 14 (medium): optional boss stinger/phase SFX using permissive assets only.
- Agent 11 (high): ability tests, visual capture, perf sanity.
- Agent 10 (medium): performance consult if ability/telegraph path adds per-frame work.

**Core tests:**
```powershell
python -m pytest tests/test_wk_next_boss_encounters.py -q
python -m pytest tests/test_wk_next_elite_affixes.py -q
python -m pytest tests/test_wk_next_boss_memory.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

**Visual and perf verification:**
```powershell
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/boss_encounter_showcase --size 1920x1080 --ticks 900
python tools/mythos_tick_bench.py --ticks 900 --warmup 180 --heroes 24 --buildings 24 --enemies 80
```

If Ursina live capture is required:

```powershell
python tools/run_ursina_capture_once.py --scenario boss_encounter_showcase --ticks 1200 --out docs/screenshots/boss_encounter_showcase_ursina
```

### Sprint C: First Epic Boss Quest

**Goal:** Connect Sprint A and B into one memorable quest chain with a boss climax.

**Recommended chain:** "Blackbanner's Toll".

**In scope:**
- Chain phases: scout fortress -> clear guards -> defeat Bandit Lord -> claim reward/outpost.
- Boss encounter starts only at the correct phase.
- Failure handling: hero death leaves the chain open, escalates boss memory, and allows another hero to accept.
- Reward includes gold plus item/renown/title if item/title infrastructure is present.
- LLM prompt includes phase history and boss facts.
- UI board shows completed phases, failed attempt, and current boss phase.

**Core tests:**
```powershell
python -m pytest tests/test_wk_next_epic_quest_blackbanner.py -q
python -m pytest tests/test_wk_next_quest_failure_recovery.py -q
python -m pytest tests/test_wk_next_quest_prompt_context.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

**Screenshot loop:**
```powershell
python tools/capture_screenshots.py --scenario epic_quest_blackbanner --seed 3 --out docs/screenshots/epic_quest_blackbanner --size 1920x1080 --ticks 1200
```

Inspect PNGs and iterate until the phase board, boss indicator, and world state are visible and non-overlapping.

### Sprint D: Dynamic Situations - Rescue And Revenge

**Goal:** Turn failures into new quests.

**In scope:**
- `rescue_hero` phase type.
- A trap/capture state for exactly one POI/boss template, likely Wizard's Tower or Bandit Fortress.
- Boss kill memory: if a named boss kills a hero, create a revenge situation/quest offer.
- Hero memorial/title fields if not already available. If memorial system exists, extend it; if not, create minimal state for logs/UI only.
- LLM context: "Boss X killed Hero Y" and "Hero Z is trapped at POI A" as structured facts.

**Out of scope:**
- General party formation.
- Every POI can capture heroes.
- Permanent hero trauma system.

**Core tests:**
```powershell
python -m pytest tests/test_wk_next_dynamic_rescue.py -q
python -m pytest tests/test_wk_next_boss_revenge.py -q
python -m pytest tests/test_wk_next_dynamic_quest_cleanup.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

### Sprint E: Dragon Hunt

**Goal:** Make Dragon Cave the first showcase mythic encounter.

**In scope:**
- "Ashwing's Hoard" chain.
- Preparation phase: scout/learn weakness, optionally visit shrine/buy item/collect scale.
- Dragon boss with telegraphed fire attack, hoard reward, and phase transition.
- Legendary loot table and hero title on victory.
- Strong visual/audio feedback.

**Primary agents:**
- Agent 05 (high): mechanics and balance.
- Agent 06 (high): preparation/retreat LLM policy.
- Agent 08 (medium-high): UI clarity.
- Agent 09 (high): Dragon telegraph/VFX/readability.
- Agent 14 (medium): roar/fire/phase SFX.
- Agent 10 (medium): live FPS consult.
- Agent 11 (high): deterministic harness + screenshot review.

**Core tests and gates:**
```powershell
python -m pytest tests/test_wk_next_dragon_hunt.py -q
python -m pytest tests/test_wk_next_boss_encounters.py -q
python -m pytest tests/test_wk_next_quest_prompt_context.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

**Visual capture:**
```powershell
python tools/run_ursina_capture_once.py --scenario dragon_hunt_showcase --ticks 1500 --out docs/screenshots/dragon_hunt_showcase_ursina
```

### Sprint F: Content Pack + Tuning

**Goal:** Add more templates only after the first loops are fun and stable.

**In scope:**
- 3-5 chain definitions using existing phase handlers.
- 6-8 elite affixes tuned and capped.
- Boss loot/title table.
- Manual playtest checklist and balance matrix.
- Documentation for how to author a new chain/boss without touching systems.

**Core tests:**
```powershell
python -m pytest tests/test_wk_next_quest_chain_content_validation.py -q
python -m pytest tests/test_wk_next_elite_affixes.py -q
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

---

## Agent Handoff Prompts

These are starter prompts for the replacement Agent 01 to adapt into the PM hub. Keep the exact ownership lanes unless a later code review proves a lane is wrong.

### Agent 03 - TechnicalDirector / Architecture

```text
Task: Add the sim/view contracts needed for multi-phase quest chains and boss encounters without changing behavior when no chains or boss encounters exist.

Scope:
- In scope: read-only DTO/view fields, event names/payload contracts, system registration in sim_engine, snapshot/AiGameView exposure for active chains and active boss facts.
- Out of scope: phase completion rules, boss balance, AI decision policy, UI rendering.

Files you MAY edit:
- game/sim/**
- game/sim_engine.py
- game/events.py if event definitions live there
- tests/test_wk_next_quest_chain_ai_view.py
- tests/test_wk_next_boss_encounter_contract.py

Files you MUST NOT edit:
- ai/**
- game/ui/**
- game/graphics/**
- assets/**
- config.py unless PM explicitly assigns shared constants

Implementation guidance:
- Add empty-default tuples for active quest chains and boss encounters. Empty state must be the digest/default path.
- Use primitive snapshots only: ids, names, phase ids, positions, status strings, risk tiers. Do not expose live mutable objects to AI/UI.
- If registering systems in sim_engine, keep the hook minimal and call system.update only from the existing sim update cadence.
- Every new event payload must include stable ids and human-readable names when available.

Acceptance:
- Existing no-chain/no-boss startup has empty view fields.
- WK67 digest remains byte-identical.
- Import order does not create cycles.

Commands (from repo root, PowerShell):
python -m pytest tests/test_wk_next_quest_chain_ai_view.py -q
python -m pytest tests/test_wk_next_boss_encounter_contract.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick

Report back with:
- Files touched
- Commands run + exit codes
- Agent log path + sprint/round entry written
- Any follow-ups / risks
```

### Agent 05 - GameplaySystemsDesigner

```text
Task: Build the gameplay state machines for quest chains, boss encounters, and elite affixes while preserving deterministic empty-path behavior.

Scope:
- In scope: QuestChainSystem, phase detectors, boss ability system, elite affix selection, rewards, boss memory facts, gameplay tests.
- Out of scope: LLM wording, UI panels, renderer VFX, audio, broad refactors.

Files you MAY edit:
- game/systems/**
- game/entities/**
- game/content/quest_chains.py or equivalent content registry
- game/content/bosses.py or equivalent content registry
- config.py only if PM assigns you the shared constants
- tests/test_wk_next_quest_chain_core.py
- tests/test_wk_next_boss_encounters.py
- tests/test_wk_next_elite_affixes.py
- tests/test_wk_next_boss_memory.py

Files you MUST NOT edit:
- ai/**
- game/ui/**
- game/graphics/**
- tools/**
- assets/**

Implementation guidance:
- QuestChainSystem.update must early-return when there are no active/offered chains.
- BossEncounterSystem.update must early-return when there are no active boss encounters.
- Roll elite affixes only at enemy spawn/creation time. Do not scan all enemies every frame looking for upgrades.
- Use sim time via game.sim.timebase.now_ms and named RNG via game.sim.determinism.get_rng.
- Prefer event-driven phase progress. Poll only cheap facts like timer expiration or fog reveal, and only for active phases.
- Store chain/boss history as small primitive records. Example: {"event": "phase_completed", "phase_id": "scout", "hero_id": 12, "time_ms": 12345}.

Acceptance:
- At least one 3-phase chain completes and pays/rewards correctly.
- At least one boss changes phase and uses an ability with cooldown/telegraph.
- Elite affixes are deterministic with the same seed.
- Empty/default path does not change WK67 digest.

Commands (from repo root, PowerShell):
python -m pytest tests/test_wk_next_quest_chain_core.py -q
python -m pytest tests/test_wk_next_boss_encounters.py -q
python -m pytest tests/test_wk_next_elite_affixes.py -q
python -m pytest tests/test_wk_next_boss_memory.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick

Report back with:
- Files touched
- Commands run + exit codes
- Agent log path + sprint/round entry written
- Any follow-ups / risks
```

### Agent 06 - AIBehaviorDirector / LLM

```text
Task: Teach heroes to reason about active quest chains, boss risk, preparation, press-on/retreat decisions, and revenge/rescue hooks without letting the LLM invent state.

Scope:
- In scope: AI scoring for accepting/continuing/retreating from chain phases; prompt context for active chains, boss facts, memories, and phase history; mock-provider tests for accept/decline/press-on outcomes.
- Out of scope: gameplay phase completion, boss ability execution, UI panels, renderer work.

Files you MAY edit:
- ai/**
- tests/test_wk_next_quest_chain_ai_policy.py
- tests/test_wk_next_quest_prompt_context.py
- tests/test_wk_next_boss_prompt_context.py

Files you MUST NOT edit:
- game/systems/**
- game/entities/**
- game/ui/**
- game/graphics/**
- config.py unless PM explicitly assigns it

Implementation guidance:
- Early-return before any ai._ai_rng draw when there are no eligible quest chains/boss facts.
- Prompt context must be structured: current_phase, objective, known_boss, risk, supplies, phase_history, failure_consequence.
- LLM actions should be bounded verbs such as accept_chain, decline_chain, continue_phase, retreat_to_heal, prepare_supplies. The sim remains authoritative.
- Press-on/retreat policy should first check hard survival gates: low health, no potions, severe boss tier gap. LLM can choose within safe options, not override death-prevention rules.
- Use mock-provider deterministic responses in tests. No network calls in tests.

Acceptance:
- A hero with an active chain sees the current phase and boss facts in prompt snapshots.
- A hero with no chains uses the exact previous AI path and leaves the digest unchanged.
- Forced mock accept/continue/retreat actions map to real hero state changes.

Commands (from repo root, PowerShell):
python -m pytest tests/test_wk_next_quest_chain_ai_policy.py -q
python -m pytest tests/test_wk_next_quest_prompt_context.py -q
python -m pytest tests/test_wk_next_boss_prompt_context.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick

Report back with:
- Files touched
- Commands run + exit codes
- Agent log path + sprint/round entry written
- Any follow-ups / risks
```

### Agent 08 - UX/UI Director

```text
Task: Make multi-phase quests and boss encounters readable in the HUD without cluttering the existing left sidebar.

Scope:
- In scope: quest chain phase timeline, active phase status, boss bar/status, failure/escalation messages, affordances on existing quest board/panels.
- Out of scope: gameplay state mutation, LLM policy, boss VFX, audio.

Files you MAY edit:
- game/ui/**
- tests/test_wk_next_quest_chain_ui.py
- tests/test_wk_next_boss_ui.py

Files you MUST NOT edit:
- game/systems/**
- ai/**
- game/graphics/**
- assets/**
- config.py unless PM explicitly assigns UI constants

Implementation guidance:
- Do not create a marketing-style screen. Use the existing operational HUD language: compact, readable, status-first.
- The player must understand: current phase, objective location, hero assigned, reward/stakes, boss name/phase if known, and what failure means.
- Avoid per-frame surface churn. Follow existing dirty-gated panel patterns.
- Text must not overlap at 1024x576 or 1920x1080. Long boss/quest names must wrap or truncate cleanly.

Acceptance:
- Active chain board shows at least 3 phases with completed/current/upcoming state.
- Boss status is readable but does not block core controls.
- Failure/escalation messages are visible and not stacked incoherently with existing toasts.
- Screenshot loop completed and inspected.

Commands (from repo root, PowerShell):
python -m pytest tests/test_wk_next_quest_chain_ui.py -q
python -m pytest tests/test_wk_next_boss_ui.py -q
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/quest_boss_ui_panels --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario quest_chain_foundation --seed 3 --out docs/screenshots/quest_chain_foundation --size 1920x1080 --ticks 900
python tools/qa_smoke.py --quick

Report back with:
- Files touched
- Commands run + exit codes
- Screenshot paths inspected and visual verdict
- Agent log path + sprint/round entry written
- Any follow-ups / risks
```

### Agent 09 - ArtDirector / VFX

```text
Task: Add readable boss/elite visual language and ability telegraphs without violating Mythos performance guardrails.

Scope:
- In scope: elite markers, boss phase visual tells, telegraph quads/overlays for dangerous abilities, boss label readability, sprite/model fallback checks.
- Out of scope: gameplay damage, quest UI panels, AI behavior, broad renderer rewrites.

Files you MAY edit:
- game/graphics/**
- tests/test_wk_next_boss_visuals.py
- tests/test_wk_next_elite_visuals.py

Files you MUST NOT edit:
- game/systems/**
- ai/**
- game/ui/** unless PM coordinates with Agent 08
- config.py unless PM explicitly assigns visual constants

Implementation guidance:
- Reuse existing instanced/default renderer patterns. Do not add per-frame allocations or full-window HUD uploads.
- Telegraph events should create/update pooled visuals, not spawn unbounded new entities.
- Boss/elite marks must be visible at normal zoom and not obscure health bars/name labels.
- If headless cannot verify Ursina, record that PM/Jaimie must perform live capture.

Acceptance:
- Elite marker and boss phase tell are visible in screenshots.
- Ability telegraph appears before damage and clears after.
- No overlay/entity leak in teardown tests.

Commands (from repo root, PowerShell):
python -m pytest tests/test_wk_next_boss_visuals.py -q
python -m pytest tests/test_wk_next_elite_visuals.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/boss_encounter_showcase --size 1920x1080 --ticks 900

Report back with:
- Files touched
- Commands run + exit codes
- Screenshot paths inspected and visual verdict
- Any deferred live Ursina capture need
- Agent log path + sprint/round entry written
```

### Agent 11 - QA TestEngineering Lead

```text
Task: Build deterministic verification for quest chains, boss encounters, elite affixes, visual scenarios, and the full adventure loop.

Scope:
- In scope: focused tests, headless soaks, screenshot scenarios when allowed by ownership, matrix probes, final gate report.
- Out of scope: production gameplay fixes unless PM explicitly assigns a QA-owned test harness or scenario.

Files you MAY edit:
- tests/**
- QA-owned scenario files if existing project ownership allows; otherwise ask PM to involve Agent 12 for tools/**
- docs/screenshots/** outputs
- .cursor/plans/agent_logs/agent_11_QA_TestEngineering_Lead.json

Files you MUST NOT edit:
- production game code unless PM sends a fix prompt
- assets/**

Implementation guidance:
- Every new mechanic gets at least one deterministic positive test and one cleanup/failure test.
- Include a no-op/digest guard test for systems with empty data.
- For balance, measure multiple seeds and report a recommendation instead of silently tuning constants.
- Screenshots must be inspected. If the latest PNG does not show the feature, verification failed.

Acceptance:
- Full gate report states PASS/FAIL for quest chain core, boss system, elite affixes, prompt context, UI screenshots, qa_smoke, digest, and any asset validation.
- Any failure includes owner recommendation and exact repro command.

Commands (from repo root, PowerShell):
python -m pytest tests/test_wk_next_quest_chain_core.py tests/test_wk_next_boss_encounters.py tests/test_wk_next_elite_affixes.py -q
python -m pytest tests/test_wk_next_quest_prompt_context.py tests/test_wk_next_quest_chain_ui.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
python tools/capture_screenshots.py --scenario quest_chain_foundation --seed 3 --out docs/screenshots/quest_chain_foundation --size 1920x1080 --ticks 900
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/boss_encounter_showcase --size 1920x1080 --ticks 900

Report back with:
- Files touched
- Commands run + exit codes
- Screenshot paths inspected and visual verdict
- Gate verdict and owner recommendations for failures
- Agent log path + sprint/round entry written
```

---

## Recommended Send List

For **Sprint A**:
- Agent 03 - TechnicalDirector (**high intelligence**, GPT-5.5 high effort): sim/view contracts.
- Agent 05 - GameplaySystems (**high intelligence**, GPT-5.5 high effort): QuestChainSystem and phases.
- Agent 06 - AIBehavior (**high intelligence**, GPT-5.5 high effort): chain commitment and prompt context.
- Agent 08 - UX/UI (**high intelligence**, GPT-5.5 high effort): phase board/timeline.
- Agent 11 - QA (**high intelligence**, GPT-5.5 high effort): deterministic tests and screenshots.
- Do not send 09/10/12/14/15 unless visual/tooling gaps appear.

For **Sprint B**:
- Agent 05 - GameplaySystems (**high intelligence**, GPT-5.5 high effort): boss/elite mechanics.
- Agent 03 - TechnicalDirector (**high intelligence**, GPT-5.5 high effort): contracts and registration.
- Agent 09 - ArtDirector (**medium-high intelligence**, GPT-5.5 high effort): visual tells.
- Agent 08 - UX/UI (**medium-high intelligence**, GPT-5.5 high effort): boss UI.
- Agent 11 - QA (**high intelligence**, GPT-5.5 high effort): tests/captures.
- Agent 10 - Performance (**medium intelligence**, GPT-5.5 high effort): consult if per-frame/render work changes.
- Agent 14 - Sound (**medium intelligence**, GPT-5.5 high effort): optional audio only after visuals/mechanics are stable.

For **Sprints C-E**:
- Activate the same core set: 03, 05, 06, 08, 09, 11.
- Add 10 for Dragon/Demon live perf work.
- Add 14 for Dragon/Demon audio.
- Add 07 if PM wants a content pass on copy, template names, and scenario variety.

---

## Global Verification Checklist

Every implementing sprint must include:

```powershell
python -m pytest tests/test_wk67_ai_boundary.py -q
python tools/qa_smoke.py --quick
```

If assets, prefabs, audio, or manifest entries changed:

```powershell
python tools/validate_assets.py --report
```

If UI/graphics/player-visible work changed:

```powershell
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/<sprint>_ui_panels --size 1920x1080 --ticks 480
```

Use feature scenarios when they exist:

```powershell
python tools/capture_screenshots.py --scenario quest_chain_foundation --seed 3 --out docs/screenshots/<sprint>_quest_chain --size 1920x1080 --ticks 900
python tools/capture_screenshots.py --scenario boss_encounter_showcase --seed 3 --out docs/screenshots/<sprint>_boss --size 1920x1080 --ticks 900
```

If live Ursina capture is required:

```powershell
python tools/run_ursina_capture_once.py --scenario boss_encounter_showcase --ticks 1200 --out docs/screenshots/<sprint>_boss_ursina
```

If render/per-frame paths changed:

```powershell
python tools/mythos_tick_bench.py --ticks 900 --warmup 180 --heroes 24 --buildings 24 --enemies 80
```

Jaimie manual playtest request template:

```text
Run:
python main.py --no-llm

Duration:
10 minutes.

Do this:
1. Build or select the Herald's Post.
2. Create the test chain named in the sprint.
3. Hire several heroes and let one accept the chain.
4. Watch the phase board advance through at least two phases.
5. Let the hero encounter the named boss or elite.

Verify:
- The quest board explains the current phase and next goal.
- The hero appears to prepare/continue/retreat for understandable reasons.
- The boss has a visible name, phase/tell, and reward/memory outcome.
- No UI text overlaps or hides core controls.
- Performance feels close to the accepted Mythos/v1.6.0 smoothness.

If it fails:
- Copy/paste the last ~30 terminal lines.
- Send the screenshot path or a screenshot of the broken UI/encounter.
- Say which quest phase or boss phase was active.
```

---

## Definition Of Done For The Whole Program

The program is done when:

- At least two multi-phase quest chains can be completed end-to-end.
- At least one chain can fail and produce a valid follow-up rescue or revenge hook.
- At least two named bosses have real phases/abilities, not just higher stats.
- Elites can appear with deterministic affixes and readable visual tells.
- Hero prompt snapshots include quest phase, boss facts, and memory without hallucinated state.
- Quest/boss UI is screenshot-verified at 1920x1080 and a smaller supported viewport.
- Boss/elite visual tells are screenshot-verified or explicitly live-captured in Ursina.
- WK67 digest remains byte-identical throughout.
- `python tools/qa_smoke.py --quick` passes after each sprint.
- Jaimie can play for 10 minutes and describe at least one hero story that emerged from a chain, boss, failure, or revenge loop.
