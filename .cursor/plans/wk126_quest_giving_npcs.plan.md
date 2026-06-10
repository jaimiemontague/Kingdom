# WK126 — Player-Placed Quest-Giving NPCs (Herald's Post)

**Sprint owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-07
**Renderer in scope:** Ursina (3D) — the default `python main.py` path (plus pygame for the shared
build/selection panels and the 2D overhead marker)
**Version target:** patch by default (no bump unless Jaimie asks); this is a *minor-feature candidate*
(v1.6.x) given its size — Jaimie's call at close.

> **STATUS: PLANNED — not yet kicked off.** This is a Mode-1 (Plan The Sprint) document. No PM-hub
> kickoff prompts, no agent activation, no code yet. See "Phasing & the decision for Jaimie" at the
> bottom — I recommend shipping **Phase 1 (raid-a-lair vertical slice)** first to prove the whole loop,
> then the other three quest types as Phase 2 on the same contract.

---

## The Sovereign's ask (verbatim intent)

> Player can place **"Quest-giving NPCs"** that help the player achieve goals by **dispatching NPCs who
> offer quests to heroes with rewards (that the player pays for)** in exchange for accomplishing what the
> player wants — raiding a lair, slaying enemies, finding a POI / rare item, exploring far-off lands, etc.
>
> Plus two follow-ups:
> 1. The hero's basic AI should **occasionally (not all the time)** walk up to a quest-giving NPC, and an
>    **LLM call actually decides whether the hero takes the quest**. If the hero declines, the basic AI
>    must **not return to that NPC for at least 15 minutes**.
> 2. Quest-givers must have a **yellow exclamation mark "!" over their heads**.

### Locked design decisions (from Jaimie, 2026-06-07)
- **Form: Building + NPC.** The player places a small **Herald's Post** building; a **Quest-Giver NPC**
  spawns beside it (guardhouse→guard pattern) and is the thing heroes walk up to and that wears the "!".
- **Quest types in scope (all four):** **raid-a-lair**, **slay N of an enemy type**, **find / visit a
  POI**, **explore far lands**. *Rare-item quests are deferred* (no item/loot-drop system exists yet —
  see Out-of-scope).
- **The 15-minute decline cooldown uses SIM-TIME** (`game.sim.timebase.now_ms()`): it freezes while
  paused and scales with FAST speed. Deterministic and digest-safe; matches the house rule that all
  gameplay timing comes from the sim timebase.

---

## Goal (agent-tagged)

1. **Herald's Post placeable building + Quest-Giver NPC** that spawns beside it on construction-complete.
   — **Agent 07** (building def) + **Agent 05** (NPC entity + spawn hook)
2. **A `Quest` data model + `QuestSystem`** that mirrors the existing bounty system: player funds a reward
   (gold escrow at creation), a hero can be assigned, and the system detects completion and pays out.
   — **Agent 05**
3. **Player UI to create a quest** on a selected Herald's Post (pick type → pick target → set reward),
   plus a small **active-quests board / status** surface. — **Agent 08**
4. **Quest-funding in the economy** (escrow at creation, payout on completion, existing 25% hero tax
   applies just like bounties). — **Agent 05**
5. **Heroes occasionally approach a quest-giver, and an LLM call decides accept/decline.** Decline sets a
   **15-min per-hero-per-NPC** "don't come back" cooldown (sim-time). — **Agent 06**
6. **Completion detection for all four quest types**, reusing existing pipelines where possible
   (`LAIR_CLEARED`, `ENEMY_KILLED`, POI proximity, fog reveal). — **Agent 05**
7. **Yellow "!" overhead marker** on quest-givers with an open offer — Ursina billboard + pygame blit,
   following the existing overlay dirty-gate pattern. — **Agent 09**
8. **Headless tests + digest-inert proof + a soak**, and FPS sign-off on the new overlay. — **Agent 11**
   (+ **Agent 10** FPS consult, **Agent 03** boundary consult)

Visual items (1, 3, 7) are **screenshot-verified by the PM (Agent 01) on the GPU box** via
`tools/run_ursina_capture_once.py`; headless agents ship code behind import/seam/digest gates + verbatim
diff (per `.cursor/rules/11-fps-performance-guardrails.mdc` and the Ursina deferred-screenshot rule).

---

## ⚠️ CENTRAL CONSTRAINT — DO NOT BREAK THE WK67 AI-DECISION DIGEST

`tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable` hashes 300 ticks of a fixed
3-hero scenario: **warrior "Aldous", ranger "Brina", cleric "Cora"** near the castle, seed 3, **no
enemies, no buildings beyond the castle, NO quest-givers, NO quests.** Expected sha256:
`b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`. It hashes per hero
`(hero_id, x, y, state, intent, target-type, gold)` + economy log length / total-spent / wave.

**This digest MUST stay byte-identical. Do NOT re-baseline it.** The whole quest system is brand-new
content, so digest-inertness is *structural* — the digest scenario contains zero quest-givers and zero
quests. Every new code path must be a **complete no-op when `view.quest_givers` / `view.quests` are
empty.** "Complete no-op" here is stricter than the WK124 cleric/ranger pattern — it means:

1. **The AI quest branch (`task_router`) must early-return `False` BEFORE it touches anything** if there
   are no eligible quest-givers. In particular it must **NOT draw from `ai._ai_rng`** for the
   "occasionally" probability roll unless an eligible giver actually exists. *Consuming the seeded RNG
   stream shifts every downstream draw and WILL change the digest* even though no hero moved. Order the
   guard so the RNG roll is the **last** gate, after "does an offerable, non-cooldowned giver exist?".
2. **`QuestSystem.update()` must early-return** (no event emission, no RNG, no state mutation) when there
   are no quests/givers.
3. **No new field that the digest hashes.** New hero fields (`_quest_decline_until_ms` dict,
   `_quest_approach_cooldown_until_ms`) are fine — the digest hashes only `x,y,state,intent,target-type,
   gold`. But the quest branch must never set `hero.intent` or a quest `hero.target` in the digest
   scenario — guaranteed by rule (1), since it's never reached.
4. **No spawns / no escrow in the digest.** Quest-Giver NPCs spawn only from a Herald's Post; the digest
   has none. `economy.fund_quest()` is called only from the player UI; the digest never calls it.
5. **The LLM stays off the digest path exactly as today.** The digest builds the AI with `llm_brain=None`
   (deterministic fallback) or the seeded `MockProvider`; either way the quest-offer LLM consult is never
   triggered because no giver is approached (rule 1).

**Mandatory gate for Agents 05, 06, and 03 (anyone touching sim/AI/boundary):**
```
python -m pytest tests/test_wk67_ai_boundary.py -q
```
If it fails, your guard is too loose (most likely an RNG draw or a system tick that isn't fully gated on
"no quests"). Tighten it. **Do not edit `_AI_DECISION_DIGEST`.** If you believe a digest change is
unavoidable, STOP and report to the PM — do not re-baseline.

---

## Architecture (this is a NEW system — design, not root-cause)

The quest system is deliberately a **near-clone of the bounty system** (the closest existing analog),
extended with a placed NPC, an LLM accept/decline gate, and four completion detectors. Build it alongside
bounties, not on top of them.

### Existing parts we reuse (do not re-derive — see the scout maps in the agent logs)
- **Bounty system** as the template: `game/systems/bounty.py` (`Bounty`, `BountySystem`),
  `game/engine_facades/actions.py::place_bounty` (escrow + placement),
  `ai/behaviors/bounty_pursuit.py` (commit window + pick cooldown + scoring),
  `BountySystem.check_claims` ticked at `game/sim_engine.py:900`.
- **Completion pipelines:** `LAIR_CLEARED` routing at `sim_engine.py:1018` (raid); `ENEMY_KILLED`
  events from `combat.py` (slay); POI proximity/interaction `poi_interaction.py` + `"visit_poi"` AI
  target (`ai/arrival_handlers.py:219`, `ai/behaviors/poi_awareness.py:268`) (find-POI); fog/visibility
  reveal (`game/sim/fog.py`, `ai/behaviors/exploration.py`) (explore).
- **Placed-NPC entity template:** `game/entities/tax_collector.py` (a placed, self-directed NPC with its
  own FSM and target list) and the **guardhouse→guard spawn-on-constructed** hook at `sim_engine.py:973`.
- **Economy:** `game/systems/economy.py::add_bounty` (escrow precedent) + `hero_economy.py::add_gold`
  (25% tax payout precedent).
- **LLM async pipeline:** `ai/llm_brain.py` (`request_decision`/`get_decision`, daemon worker, pending
  flag), `ai/behaviors/llm_bridge.py::apply_llm_decision` (the `accept_bounty` slot at line 180 is an
  *unwired no-op* — our pattern to fill), `ai/decision_moments.py` (`IDLE_SEEKING_ACTIVITY` already lists
  `accept_bounty`), `ai/providers/mock_provider.py` (seeded deterministic responses for tests),
  `ai/profile_context_adapter.py` + `ai/prompt_packs.py` (hero personality/profile already in prompts;
  `obey_defy` field already parsed — natural accept/decline carrier).
- **Overhead marker pattern:** `game/graphics/ursina_unit_overlays.py::sync_hero_rest_label` (the "Zzz"
  text billboard) is the closest precedent; `_OVERLAY_CHILD_ATTRS` (teardown) + `_HERO_OVERLAY_ATTRS`
  (facing). Pygame equivalent: the "Zzz" block in `game/graphics/renderers/hero_renderer.py:197-200`
  using `render_text_cached`.
- **Quest scaffold already present (wk14):** `GameEventType.QUEST_STARTED / QUEST_COMPLETED /
  QUEST_HERO_RETURNED` (`game/events.py:30-32`, currently unused), `ViewMode.QUEST` +
  `game/ui/quest_view_panel.py::QuestViewPanel` (placeholder). The design docs to fold in:
  `.cursor/plans/Dynamic_Quests.md` (north star) and `docs/quest_archetypes.md` (archetype copy).

> **Framing note — ON-MAP quests, not "away/travelogue" quests.** The wk14 `quest_archetypes.md` describes
> heroes going *away* into a text-travelogue panel. **This sprint is different:** the player creates a
> quest at a Herald's Post and the hero **physically pursues it on the map** (walks to the lair / POI /
> frontier and does the deed in-world). We **reuse** the wk14 events and *optionally* the QuestViewPanel
> for a status readout, but we are not building the remote-travelogue mode here. Don't conflate them.

### Data model (new)

`game/systems/quest.py` (new) — mirror `bounty.py`:

```python
class Quest:
    _NEXT_ID = 1
    def __init__(self, giver_id, quest_type, target, reward, *, count=1, created_time_ms):
        self.quest_id = Quest._NEXT_ID; Quest._NEXT_ID += 1
        self.giver_id = giver_id            # the Herald's Post / Quest-Giver this offer belongs to
        self.quest_type = quest_type        # "raid_lair" | "slay_enemy_type" | "find_poi" | "explore_far"
        self.target = target                # lair obj | enemy_type str | poi obj | (tile_x, tile_y)
        self.count = count                  # for slay_enemy_type (N kills); else 1
        self.progress = 0                   # kill counter for slay; 0/1 otherwise
        self.reward = reward                # gold the PLAYER funded (escrowed at creation)
        self.funded = True
        self.accepted_by = None             # hero_id once a hero takes it
        self.accepted_time_ms = None
        self.completed = False
        self.failed = False
        self.created_time_ms = created_time_ms
    # is_open(): funded and not accepted and not completed/failed  -> drives the "!" marker
    # accept(hero), is_target_alive()/is_valid(), to_ai_tuple()  (mirror Bounty)

class QuestSystem(GameSystem):
    # holds self.quests; registered on SimEngine like BountySystem
    # update(dt, heroes, enemies, events, ...): EARLY-RETURN if not self.quests  (digest guard)
    #   - progress/expire/complete detection per type (see T7)
    #   - on completion: pay accepted hero via hero.add_gold(reward), emit QUEST_COMPLETED, _emit_hud_message
    #   - on target-gone before accept: mark failed/cleanup, emit QUEST_FAILED
```

### Lifecycle (one quest, happy path)
1. Player places a **Herald's Post** (build hotkey/catalog). Peasant constructs it (1 HP → full, normal).
2. On construction-complete, sim spawns **one Quest-Giver NPC** beside it (guardhouse→guard pattern).
3. Player selects the post → **Quest-Create dialog** → picks type + target + reward tier → confirm.
   `economy.fund_quest(reward)` **escrows** the gold; a `Quest` is created `is_open=True`; emit
   `QUEST_OFFERED`. The NPC now shows the **yellow "!"**.
4. Each tick, eligible idle heroes **occasionally** (seeded prob.) path to the nearest open, non-cooldowned
   giver (committed target `quest_offer`).
5. On arrival, the hero triggers an **LLM accept/decline** decision (async). On the answer:
   - **accept** → `quest.accept(hero)`; hero's target becomes the objective (lair/poi/enemy/frontier);
     emit `QUEST_STARTED`; the "!" turns **off** (offer taken).
   - **decline** → set `hero._quest_decline_until_ms[giver_id] = now_ms + QUEST_DECLINE_COOLDOWN_MS`
     (15 sim-min); emit `QUEST_DECLINED`; hero resumes normal AI; the "!" stays on for *other* heroes.
6. Hero pursues + completes the objective → `QuestSystem` detects it → `hero.add_gold(reward)` (25% tax) →
   emit `QUEST_COMPLETED` + HUD toast. The post can offer a new quest (player re-arms it).

---

## Tickets

### WK126-T1 — Quest data model + `QuestSystem` (owner: Agent 05)
- **Files (new/edit):** `game/systems/quest.py` (new), `game/sim_engine.py` (register + tick the system,
  mirroring `bounty_system` at `:900`/`:916` and the system registry at `:131-141`), `game/events.py`
  (add `QUEST_OFFERED`, `QUEST_ACCEPTED` *(or reuse `QUEST_STARTED`)*, `QUEST_DECLINED`, `QUEST_FAILED`),
  `config.py` (ALL new quest constants — see "Config" below), `game/entities/hero.py` (init the new
  cooldown fields in `__init__`).
- **Build:** `Quest` + `QuestSystem(GameSystem)` per the model above. **Deterministic:** time only from
  `from game.sim.timebase import now_ms as sim_now_ms`; any RNG only via `game.sim.determinism.get_rng`.
  `QuestSystem.update` **must early-return when `not self.quests`** (digest guard #2).
- **Hero fields (init in `Hero.__init__`, not hashed by digest):**
  `self._quest_decline_until_ms: dict[int, int] = {}` and `self._quest_approach_cooldown_until_ms = 0`.
- **Headless gate (add):** `tests/test_wk126_quest_system.py` — create/escrow/accept/complete/payout, and
  an explicit `test_quest_system_noop_when_empty` (no events, no RNG draw with empty quest list).
- **Acceptance:** unit tests green; `qa_smoke --quick` green; **WK67 digest byte-identical.**

### WK126-T2 — Herald's Post building + Quest-Giver NPC entity (owners: Agent 07 def, Agent 05 entity+spawn)
- **Agent 07 (`game/content/buildings.py`):** add a `BuildingDef` `"herald_post"` (a.k.a. Notice Board) —
  `placeable=True`, a free hotkey, a `placeable_order`, `cost = HERALD_POST_COST` (consume from config),
  modest `size`, a distinct `color`, normal HP. Add it to the placeable catalog so it appears in the build
  menu (`build_catalog_panel.PLACEABLE_BUILDINGS` derives from `placeable`). **Do NOT** touch sim/ai.
- **Agent 05 (`game/entities/quest_giver.py` new, `game/sim_engine.py`):** `QuestGiver` entity modeled on
  `game/entities/tax_collector.py` but **stationary** (stands beside its post; no roaming FSM needed for
  MVP — it has a position, a `giver_id == owning post id`, an `interact_radius`, and an `is_open` flag that
  mirrors whether its post has an open quest). Spawn **one per constructed Herald's Post** via a tick hook
  mirroring the guardhouse→guard spawn at `sim_engine.py:973` (only when the post is constructed; cap 1).
  Store in a new `engine.quest_givers` list; clean it up when the post is destroyed (mirror guard cleanup).
- **Headless gate (add):** `tests/test_wk126_quest_giver_spawn.py` — placing+constructing a Herald's Post
  spawns exactly one `QuestGiver` at the expected offset; destroying the post removes it.
- **Acceptance:** tests green; **digest green** (no Herald's Post in the digest → no spawn). PM capture:
  a placed post with the NPC standing beside it.

### WK126-T3 — Economy: quest funding (owner: Agent 05)
- **File (edit):** `game/systems/economy.py` — add `fund_quest(amount)` mirroring `add_bounty` (line 64):
  guard `can_afford`, debit `player_gold`, append a `quest_funded` transaction-log entry. Payout reuses
  `hero.add_gold(reward)` on completion (25% tax already applies, identical to bounty claims) — **no new
  payout path**, call it from `QuestSystem` completion.
- **Headless gate (add):** extend `tests/test_wk126_quest_system.py` — funding debits the treasury;
  insufficient gold blocks creation; completion credits the hero (taxed) and logs.
- **Acceptance:** tests green.

### WK126-T4 — AI boundary: expose quests + givers to the AI view (owners: Agent 03 dataclass, Agent 05 populate)
- **Agent 03 (`game/sim/ai_view.py`):** add `quests: tuple[...] = ()` and `quest_givers: tuple[...] = ()`
  fields to `AiGameView` (mirror the existing `bounties` / `pois` fields at `ai_view.py:93-94`). Read-only
  tuples of plain data (id, type, position, reward, is_open, decline-relevant ids) — **no live object refs
  the AI could mutate**, matching the existing boundary contract.
- **Agent 05 (`game/sim_engine.py::build_ai_view`):** populate the two new tuples from `self.quests` /
  `self.quest_givers` (mirror how `bounties`/`pois` are populated at `:540-541`).
- **Headless gate (add):** `tests/test_wk126_ai_view_quests.py` — `build_ai_view()` carries the new tuples;
  empty when there are none (so the AI no-ops — digest guard #1 relies on this).
- **Acceptance:** tests green; **digest green** (empty tuples in the digest scenario).

### WK126-T5 — AI: occasional approach to a quest-giver (owner: Agent 06)
- **Files (new/edit):** `ai/behaviors/quest_offer.py` (new), `ai/task_router.py` (priority branch),
  `ai/basic_ai.py` (register the behavior + add `"quest_offer"` to `_COMMITTED_DESTINATION_TYPES` at
  `:31-45` + tunables), `ai/contracts.py` (add `QUEST_OFFER = "quest_offer"` target type),
  `ai/arrival_handlers.py` (register a `quest_offer` arrival handler — see T6). **Reads config from
  Agent 05; does NOT edit config.py.**
- **Build `maybe_approach_quest_giver(ai, hero, view) -> bool`** modeled on `bounty_pursuit.maybe_take_bounty`:
  1. **Guard FIRST (digest-critical order):**
     a. `if not view.quest_givers: return False`  (no RNG, no state change — digest guard #1).
     b. health gate (`hero.health_percent >= QUEST_MIN_ACCEPT_HEALTH_PCT`, ~0.65, like bounty).
     c. not already committed; approach-cooldown elapsed
        (`sim_now_ms() >= hero._quest_approach_cooldown_until_ms`).
     d. build the candidate list: open givers (`is_open`) whose `giver_id` is **NOT** in
        `hero._quest_decline_until_ms` with a future timestamp (the 15-min skip), within a sane range.
     e. `if not candidates: return False`  (still no RNG draw).
  2. **"Occasionally" gate — LAST:** draw one value from `ai._ai_rng` and proceed only if
     `< QUEST_APPROACH_CHANCE` (~0.15). This is the *only* RNG draw, and it happens only when a real
     candidate exists, so it never runs in the digest scenario.
  3. Pick the nearest candidate; set `hero.target = {"type": "quest_offer", "giver_id": gid}`,
     `hero.state = MOVING`, `hero.set_target_position(giver.x, giver.y)`, set a commit window
     `hero._quest_offer_commit_until_ms = sim_now_ms() + QUEST_OFFER_COMMIT_MS`, and set the approach
     cooldown so heroes don't spam-path to NPCs. Return `True`.
- **Wire into `task_router.update_hero`** as a **low-priority idle/seeking branch** — below survival,
  defense, hunger, and the existing bounty/exploration tier (so it never overrides anything important).
  It must be reachable only when the hero is otherwise idle and uncommitted.
- **Headless gate (add):** `tests/test_wk126_quest_approach.py` — with a giver present and the RNG forced,
  a hero commits to `quest_offer`; with **no** givers, the function returns `False` **without drawing from
  `ai._ai_rng`** (assert the RNG position is unchanged — this is the digest-safety unit test); a giver on
  this hero's decline-cooldown is skipped.
- **Acceptance:** tests green; **WK67 digest byte-identical** (the RNG-position assertion is the key proof).

### WK126-T6 — AI: LLM accept/decline at the NPC + 15-min per-NPC decline cooldown (owner: Agent 06)
- **Files (edit):** `ai/arrival_handlers.py` (`handle_quest_offer_arrival`, modeled on
  `handle_visit_poi_arrival:219`), `ai/behaviors/llm_bridge.py` (fill the accept/decline mapping — the
  `accept_bounty` no-op at `:180` is the precedent), `ai/decision_moments.py` (new `QUEST_OFFER`
  decision-moment type with `allowed_actions=("accept_quest","decline_quest")` and a cooldown),
  `ai/profile_context_adapter.py` + `ai/prompt_packs.py` (inject the quest-offer context — quest type,
  target description, reward, distance/risk — into the prompt; personality is already included).
- **Flow:** on arrival at the giver, enqueue an LLM decision via `ai.llm_brain.request_decision(...)`
  (async; set `hero.pending_llm_decision = True`). The response is polled in `task_router` exactly like
  existing LLM decisions and routed through `apply_llm_decision`:
  - **`accept_quest`** → look up the quest on the giver, `quest.accept(hero)`, set the hero's target to the
    objective (raid→the lair, find_poi→`{"type":"visit_poi","poi":...}`, slay→hunt target/area,
    explore→frontier point), emit `QUEST_STARTED`. The "!" turns off (T7/T8 read `is_open`).
  - **`decline_quest`** → `hero._quest_decline_until_ms[giver_id] = sim_now_ms() +
    QUEST_DECLINE_COOLDOWN_MS` (**900_000 ms = 15 sim-min**); emit `QUEST_DECLINED`; clear the
    `quest_offer` commit so the hero re-decides normally.
  - The existing **`obey_defy`** field (`llm_brain._parse_response`, default `"Obey"`) is the natural
    accept/decline carrier if you prefer reusing it over new action verbs — pick one and document it.
- **Determinism:** the LLM is async and off the digest path (no giver is approached in the digest). For the
  **headless quest tests**, drive the decision with the seeded `MockProvider` (add a quest-offer responder
  in `ai/providers/mock/`) **or** a `llm_brain=None` deterministic fallback that returns a fixed verdict —
  so accept/decline is assertable without a network call.
- **Headless gate (add):** `tests/test_wk126_quest_llm_decision.py` — forced-accept assigns the quest and
  sets `quest.accepted_by`; forced-decline sets `_quest_decline_until_ms[giver]` ≈ `now + 900_000` and the
  approach selector then **skips that giver for <15 min and re-considers it after** (advance sim clock).
- **Acceptance:** tests green; `qa_smoke --quick` green; **digest green.**

### WK126-T7 — Completion detection for all four quest types (owner: Agent 05)
Implement inside `QuestSystem.update` (and a small hook in `sim_engine` event routing where noted). Each
detector only runs for **accepted** quests; all are no-ops when `not self.quests`.
- **`raid_lair`** — reuse `LAIR_CLEARED` routing at `sim_engine.py:1018`: when a lair is cleared, match any
  accepted quest whose `target is` that lair → complete + pay (exactly like the `attack_lair` bounty match
  already there).
- **`slay_enemy_type`** — **new plumbing (this finishes the never-wired `hunt_enemy_type`):** subscribe to
  `ENEMY_KILLED`; if `killer_hero_id == quest.accepted_by` and `enemy.enemy_type == quest.target`,
  `quest.progress += 1`; when `progress >= quest.count` → complete + pay.
- **`find_poi`** — complete when the accepting hero reaches/interacts with the target POI (reuse the
  `visit_poi` arrival / `poi_interaction` proximity; the hero's target was set to `visit_poi` on accept).
- **`explore_far`** — complete when the target tile (and a small radius, `QUEST_EXPLORE_REVEAL_RADIUS_TILES`)
  becomes `SEEN` in `World.visibility` while the accepting hero is the one nearby (reuse the fog grid;
  poll cheaply in the system tick).
- **Failure/cleanup:** if a target is destroyed/gone before acceptance, or the accepting hero dies, mark
  `failed`, refund-or-not per design (MVP: keep escrow consumed, emit `QUEST_FAILED`, free the giver to be
  re-armed). Document the refund choice with Jaimie.
- **Headless gate (add):** `tests/test_wk126_quest_completion.py` — one test per type proving
  detect→pay→`QUEST_COMPLETED`, plus a slay-counter test (N-1 kills ≠ complete, Nth completes).
- **Acceptance:** tests green; **digest green** (no accepted quests in the digest).

### WK126-T8 — Yellow "!" overhead marker (owner: Agent 09)
- **Ursina (`game/graphics/ursina_unit_overlays.py` + the quest-giver sync call site in
  `ursina_unit_sync.py` / `ursina_renderer.py`):** add a `sync_quest_giver_marker(ent, is_open)` modeled
  **exactly** on `sync_hero_rest_label` (the "Zzz" billboard at `:274-289`):
  - lazily create a child `Text("!")` (or a small quad with an "!" texture) once; `color = yellow`;
    position above the head (e.g. `y≈0.8`).
  - **Configure via `configure_ks_overlay(child)`** so it draws on top (the WK124 bin-order fix: set
    `always_on_top` then re-assert depth-off then `set_bin("fixed", 110)` LAST).
  - Toggle `.enabled = is_open` each frame; **only mutate transform/text when the value changes** (the
    `_ks_last_*` dirty-gate pattern — FPS-safe, no per-frame re-raster).
  - **Register the new child attr in `_OVERLAY_CHILD_ATTRS`** (`:93-102`) so `free_entity_overlays` frees
    it on NPC removal (WK123 leak fix — Ursina `destroy` does not cascade), **and in `_HERO_OVERLAY_ATTRS`**
    (`:296`) if it needs facing un-mirror.
- **Pygame (`game/graphics/renderers/` — add a `quest_giver_renderer.py` or extend the NPC renderer):**
  blit a cached yellow "!" above the sprite when `is_open`, modeled on the "Zzz" block at
  `hero_renderer.py:197-200` using `render_text_cached` (FPS-safe cached surface).
- **Headless gate (add):** `tests/test_wk126_quest_marker_overlay.py` — assert the marker child is created,
  `configure_ks_overlay` puts it at bin draw-order 110 (reuse the WK124 bin assertion), and it's registered
  in `_OVERLAY_CHILD_ATTRS` (freed on teardown — no leak).
- **Acceptance:** bin/leak test green; **PM Ursina capture** shows a yellow "!" floating over the
  quest-giver, on top of buildings, that disappears once the quest is accepted.

### WK126-T9 — Quest-creation dialog + active-quest board (owner: Agent 08)
- **Files (new/edit):** `game/ui/quest_create_panel.py` (new — modal, modeled on
  `game/ui/build_catalog_panel.py::BuildCatalogPanel`), wire **selecting a Herald's Post** to open it
  (selection → panel, following the building-renderer/selection-panel pattern), reuse/extend
  `game/ui/quest_view_panel.py` (the wk14 QUEST-ViewMode placeholder) for an **active-quest status**
  readout, add a left-menu/HUD affordance per `.cursor/plans/wk115_round_b_left_menu_ui_polish.plan.md`
  conventions, and the input wiring in `game/input/keyboard.py` if a hotkey is added.
- **Dialog flow:** (1) pick quest **type** (4 buttons). (2) pick **target**:
  raid→click a *discovered* lair; slay→pick enemy type + count (N); find_poi→click a *discovered* POI;
  explore→click a far map tile. (3) pick **reward tier** (Low/Med/High → `QUEST_REWARD_*`, with cost
  shown and affordability checked against `economy.player_gold`). Confirm → call the engine action that
  runs `economy.fund_quest` + `QuestSystem.create_quest`. Show insufficient-gold feedback like the build
  menu does.
- **Headless gate (add):** `tests/test_wk126_quest_create_panel.py` — open on a selected post, a valid
  selection produces a funded quest (treasury debited, quest `is_open`), invalid/over-budget is blocked.
- **Acceptance:** tests green; **PM capture** of the create dialog and the "!" appearing after confirm.

### WK126-T10 — QA: tests, digest-inert proof, soak, FPS (owner: Agent 11; consults Agent 10, Agent 03)
- **Files (new):** `tests/test_wk126_quest_soak.py` — headless engine with 1–2 Herald's Posts + several
  heroes over ~10 sim-min: assert (a) heroes *do* accept some quests over time, (b) a declined giver is not
  re-approached by that hero for ≥15 sim-min, (c) at least one quest of each in-scope type can complete,
  (d) no quest-marker entity leak (overlay count stable). Set `DETERMINISTIC_SIM=1`, dummy SDL drivers.
- **Run all gates** (below) and the **WK67 digest**; **Agent 10** confirms the new "!" overlay follows the
  dirty-gate pattern and doesn't regress FPS (defer the live Ursina FPS read to the PM per the headless
  rule); **Agent 03** reviews the `sim_engine` system registration + the `ai_view` boundary.
- **Acceptance:** full suite green incl. byte-identical digest; soak green; FPS sign-off.

---

## Config (Agent 05 owns ALL of these — single owner of `config.py` this sprint)
```
HERALD_POST_COST            = 150          # gold to place the building
HERALD_POST_HOTKEY          = "<free key>" # pick an unused build hotkey
QUEST_REWARD_LOW            = 60
QUEST_REWARD_MED            = 140
QUEST_REWARD_HIGH           = 280
QUEST_DECLINE_COOLDOWN_MS   = 900_000      # 15 SIM-minutes; per hero, per giver
QUEST_APPROACH_COOLDOWN_MS  = 25_000       # min sim-time between a hero's approach attempts
QUEST_APPROACH_CHANCE       = 0.15         # "occasionally" — only rolled when a candidate exists
QUEST_OFFER_COMMIT_MS       = 12_000       # anti-thrash commit while walking to the NPC
QUEST_MIN_ACCEPT_HEALTH_PCT = 0.65         # don't go quest-shopping while hurt (matches bounty)
QUEST_GIVER_INTERACT_PX     = <tile-based> # arrival radius at the NPC
QUEST_SLAY_DEFAULT_COUNT    = 5            # default N for slay_enemy_type
QUEST_EXPLORE_REVEAL_RADIUS_TILES = 3      # explore_far completion radius
```

---

## File ownership / lanes (each file has exactly ONE owning agent this sprint)

| Ticket | Agent | Files MAY edit | MUST NOT edit |
|---|---|---|---|
| T1, T3, T7, config, entity, spawn | **05 Gameplay** | `game/systems/quest.py` (new), `game/entities/quest_giver.py` (new), `game/systems/economy.py`, `game/events.py`, `config.py` (ALL consts), `game/sim_engine.py` (register/tick/spawn/completion/`build_ai_view` populate), `game/entities/hero.py` (cooldown fields), `tests/test_wk126_quest_system.py`, `tests/test_wk126_quest_giver_spawn.py`, `tests/test_wk126_quest_completion.py` | ai/, ui/, graphics/, content/buildings.py |
| T2 def | **07 Content** | `game/content/buildings.py` (Herald's Post def only) | everything else |
| T4 dataclass | **03 TechDir** | `game/sim/ai_view.py`, `tests/test_wk126_ai_view_quests.py` | sim_engine.py (05 populates), ai behaviors, ui |
| T5, T6 | **06 AI** | `ai/behaviors/quest_offer.py` (new), `ai/arrival_handlers.py`, `ai/task_router.py`, `ai/basic_ai.py`, `ai/contracts.py`, `ai/decision_moments.py`, `ai/behaviors/llm_bridge.py`, `ai/profile_context_adapter.py`, `ai/prompt_packs.py`, `ai/providers/mock/` (quest responder), `tests/test_wk126_quest_approach.py`, `tests/test_wk126_quest_llm_decision.py` | config.py (READ only), sim/, game/, ui/, graphics/ |
| T8 | **09 Art** | `game/graphics/ursina_unit_overlays.py`, `game/graphics/ursina_unit_sync.py` (call site), `game/graphics/renderers/quest_giver_renderer.py` (new), `tests/test_wk126_quest_marker_overlay.py` | ui/, sim/, ai/, config, vfx core |
| T9 | **08 UX/UI** | `game/ui/quest_create_panel.py` (new), `game/ui/quest_view_panel.py`, selection-panel wiring, `game/input/keyboard.py`, `tests/test_wk126_quest_create_panel.py` | sim/, ai/, graphics/, config, entities |
| T10 | **11 QA** | `tests/test_wk126_quest_soak.py` (new), runs all gates | production code |

**No two agents in the same wave touch the same file.** `config.py` is Agent 05's alone; Agent 06 reads
the constants. `sim_engine.py` is Agent 05's alone; Agent 03 only edits the `ai_view.py` dataclass and
consults on the boundary.

## Integration / wave order
- **Wave 1 (parallel — disjoint files; defines the contracts):** Agent 05 (T1+T3+T7 core: `Quest`,
  `QuestSystem`, `QuestGiver`, economy, events, config, sim hooks), Agent 07 (Herald's Post def),
  Agent 03 (`ai_view` fields). 05 publishes the contracts (quest_type vocab, `QUEST_*` events, config
  consts, `quest_offer` target type expectations) that Waves 2 consume.
- **Wave 2 (parallel — disjoint files; consumes Wave-1 contracts):** Agent 06 (T5+T6 approach + LLM
  accept/decline + 15-min cooldown), Agent 08 (T9 create dialog + board), Agent 09 (T8 "!" marker).
- **Wave 3 (verification):** Agent 11 (T10 soak + full sweep), Agent 10 (FPS consult on the overlay),
  Agent 03 (boundary review); PM (Agent 01) runs the Ursina captures (post+NPC, "!", create dialog,
  accept→"!"-off) and iterates with owners until visuals pass.

## Gates (every implementing agent, headless — copy/paste from repo root)
```
python tools/qa_smoke.py --quick
python -m pytest tests/test_wk67_ai_boundary.py -q            # 05, 06, 03 — digest MUST stay green
python -m pytest tests/test_wk126_quest_system.py -q          # T1/T3
python -m pytest tests/test_wk126_quest_giver_spawn.py -q     # T2
python -m pytest tests/test_wk126_ai_view_quests.py -q        # T4
python -m pytest tests/test_wk126_quest_approach.py -q        # T5 (incl. RNG-position digest-safety assert)
python -m pytest tests/test_wk126_quest_llm_decision.py -q    # T6
python -m pytest tests/test_wk126_quest_completion.py -q      # T7
python -m pytest tests/test_wk126_quest_marker_overlay.py -q  # T8
python -m pytest tests/test_wk126_quest_create_panel.py -q    # T9
python -m pytest tests/test_wk126_quest_soak.py -q            # T10
python tools/validate_assets.py --report                      # only if assets/ changed (Agent 09/15)
python -c "import game.systems.quest, game.entities.quest_giver, ai.behaviors.quest_offer"  # import smoke
```

## PM live verification (Agent 01, on GPU box)
```
# Add a small capture scenario that places a Herald's Post + arms a raid_lair quest, then:
python tools/run_ursina_capture_once.py --scenario wk126_quest_giver --ticks 600 --out docs/screenshots/wk126_quest_giver
```
Inspect PNGs; iterate fix→recapture until: the post + NPC render correctly; the **yellow "!"** floats over
the NPC on top of buildings; a hero is seen walking up; the "!" disappears once a hero accepts; the
create dialog reads clearly.

## Send list (intelligence) — for KICKOFF (Mode 2), not yet issued
- Agent 05 — GameplaySystems (**high** — new deterministic quest system + placed NPC + economy + sim
  wiring + 4 completion detectors; digest-inertness reasoning)
- Agent 06 — AIBehaviorDirector (**high** — occasional-approach gating with strict RNG ordering + async
  LLM accept/decline + 15-min per-NPC cooldown; digest-inertness reasoning)
- Agent 08 — UX/UI (**high** — new quest-creation modal + target-picking interactions + status board)
- Agent 09 — ArtDirector (**medium** — "!" overhead marker following the known overlay/bin pattern +
  pygame blit; FPS-safe dirty-gate)
- Agent 03 — TechnicalDirector (**medium** — `ai_view` boundary fields + review the sim-engine register)
- Agent 07 — Content (**medium** — Herald's Post building def following existing `BuildingDef`s)
- Agent 11 — QA (**high** — soak + per-type completion + the RNG-position digest-safety test + leak check)
- Agent 10 — PerformanceStability (**low**, consult — overlay FPS sign-off)
- Agent 02 — GameDirector (**low–medium**, consult — quest-feel / reward tuning, optional Wave-0 review)
- Agent 14 — SoundDirector (**low**, optional — quest-accept / complete stinger; can be Phase 2)
- Do NOT send: 04 (Networking), 12 (ToolsDevEx), 13 (Steam), 15 (ModelAssembler — reuse an existing NPC
  model for MVP; promote to a real herald model only if Jaimie wants it).
- **DO NOT COMMIT. DO NOT run git. Stay in your lane. Update your own agent log only.**

## Out-of-scope (explicit — guard against creep)
- **Rare-item / loot quests.** There is no item/loot-drop entity system (loot today is gold only). A
  "find a rare item" quest needs a new reward-item concept — **deferred to a follow-up sprint**; the
  `Quest` model leaves room (`reward` could later carry an item id).
- **The wk14 "away/travelogue" remote-quest mode** (dungeon-crawl/diplomatic-mission text panels). We reuse
  its events but do not build that mode here.
- **Party / multi-hero coordination** on a quest (Dynamic_Quests.md stretch). One hero per quest in MVP.
- **Quest *chains* / multi-phase quests** (v1.6.4 roadmap). One-shot quests only.
- **Quest-giver roaming AI** — the NPC is stationary beside its post for MVP (no FSM like the tax
  collector's; it only needs a position + the "!").
- **Re-baselining the WK67 digest.** Not allowed; the system is structurally inert when no quests exist.

## Definition of Done
- All headless gates green, including **WK67 digest byte-identical (no re-baseline)** and the nine new
  WK126 tests — especially the **RNG-position assertion** proving the approach behavior draws no random
  numbers when no quest-giver exists.
- A hero can be observed (headless soak + PM capture) **occasionally** approaching a quest-giver, the **LLM
  deciding** accept/decline, and a **declined giver not being re-approached by that hero for ≥15 sim-min**.
- All four quest types complete and pay out (raid_lair, slay_enemy_type, find_poi, explore_far).
- PM Ursina captures confirm the Herald's Post + NPC, the **yellow "!"** on top of buildings, and the "!"
  turning off on acceptance.
- The quest-create dialog funds gold (escrow) and is affordability-gated like the build menu.
- No overlay entity leak (Agent 11 leak check) and FPS sign-off on the marker (Agent 10).
- This plan + the PM hub updated; Jaimie shown the loop end-to-end before close.

---

## Phasing & the decision for Jaimie

This is a **large** sprint (new sim system + placed NPC + new UI + AI LLM gate + 4 completion detectors +
overhead marker). To de-risk it I recommend an internal phasing on the *same* contract:

- **Phase 1 — Vertical slice (recommended first):** Herald's Post + NPC + **raid_lair** quest only +
  occasional-approach + **LLM accept/decline** + **15-min cooldown** + **yellow "!"** + create dialog.
  This proves the entire loop end-to-end (the Dynamic_Quests.md "one vertical slice" guidance). Tickets
  T1–T6, T8, T9 (raid path), T10.
- **Phase 2 — Fast-follow:** the other three quest types (slay_enemy_type, find_poi, explore_far), which
  are *additive* completion detectors (T7) + target-picker rows in the dialog (T9). Lower risk once the
  contract is proven.

**I'll ask Jaimie at kickoff** whether to run Phase 1 alone first or commit the whole WK126 sprint at once.
Either way, no code starts until Jaimie says "kick off WK126."
