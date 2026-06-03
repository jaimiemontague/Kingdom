# WK66 Sprint Plan — Round A-1: Render/Snapshot Boundary (Stop Write-Back · Render DTOs · Frame-State Split · World.render Out)

**Sprint id:** `wk66_round_a1_render_boundary`
**Date planned:** 2026-05-29 · **Author:** Agent 01 (ExecutiveProducer_PM) · **Model/effort for all agents:** `claude-opus-4-8[1m]`, max
**Execution mode:** **Claude Code Agent-tool subagents** (NOT the Cursor SDK orchestrator). Each worker is spawned as its studio role on model `claude-opus-4-8`, onboards via `.cursor/rules/01-studio-onboarding.mdc` + its `agent-NN-*.mdc`, then follows its `pm_agent_prompts[NN]` in the PM hub + its section in this plan. Agent 01 (parent) evaluates each wave by running the gates and viewing screenshots, and loops fixes back to the owning agent until the Definition of Done holds.
**Source docs (read these, do not re-derive):**
- `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md` (v2 audit — the synthesized plan; see §"The 12 highest-leverage structural moves" Moves 1–4, the L1/L2/L6/L10 leak table, and §"Round A").
- `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md` (the raw 187-finding dataset with `file:line`).
- `.cursor/plans/wk65_round0_deslop_foundation.plan.md` (the just-closed Round 0 — built the characterization net this sprint relies on).

---

## Why This Sprint (read first)

WK65 (Round 0) deleted dead code and **built a characterization safety net** for exactly this moment. The v2 audit's #1 structural problem is that **the boundaries between sim ↔ render ↔ AI are nominal, not real**: the "frozen" render snapshot holds *live mutable sim entities*, and renderers **write back onto sim state during the render pass**. The audit calls the boundary/DTO chain (Moves 1–6) the **structural keystone** — it's what makes every later god-file split safe and unblocks future replay/save-load/multiplayer.

Round A is large and MED-HIGH risk, so per the PM's scope split (confirmed with Jaimie 2026-05-29) it is delivered as **two sprints**:
- **WK66 (this sprint) = Round A-1: the RENDER boundary** — Moves 1, 3, 4 + leak L10. Make the *render* path consume read-only value-type DTOs and stop mutating sim state. Heavily screenshot-verifiable.
- **WK67 = Round A-2: the AI boundary** — Moves 5, 6 + leak L9. `AiGameView` (stop shipping live `world`/`economy`/`sim`/`engine` to AI) + `HeroCommand` (AI proposes, sim applies). Determinism/behavior-gated.

This sprint is **invisible to the player by design**: when it is done, the game looks and plays *byte-for-byte identical* — but the renderer can no longer corrupt the simulation. The whole sprint is *behavior-preserving extraction behind the WK65 test net + before/after screenshots*, exactly the pattern WK62–65 proved out.

### The four leaks WK66 closes (each a located, concrete problem)
- **L2 — renderer writes back onto sim state during render.** Three sub-cases, all confirmed in code:
  - **Anim one-shot triggers:** `hero_renderer.py:66-68` and `enemy_renderer.py:55-57` do `setattr(entity_state, "_render_anim_trigger", None)`; Ursina `_compute_anim_frame` (`ursina_renderer.py:554-565`) reads `_ursina_anim_trigger`/`_render_anim_trigger` then `setattr(entity, ..., None)` on **both**.
  - **Fog / discovery writes:** `ursina_renderer.py:1017` (`b.is_discovered = True`) and `:1028-1029` (`world.visibility[ty][tx] = 1`) — the renderer mutates **sim fog/discovery state** while drawing.
  - **Bounty UI caches stamped on sim objects:** `bounty_renderer.py:52-103` writes nine `_ui_cache_*` attributes onto the live `Bounty` objects.
- **L1 — the "frozen" snapshot holds live entities.** `snapshot.py:14-33` admits "individual entities are still mutable"; `build_snapshot` ships `tuple(self.heroes)` etc. (`sim_engine.py:466-501`). Renderers read live entities by `getattr`.
- **L6 — presentation state injected into the sim DTO.** `build_snapshot(..., camera_x, camera_y, zoom, paused, running, pause_menu_visible, screen_w, ...)` stuffs camera/window/pause state into `SimStateSnapshot` (`sim_engine.py:445-501`). Camera & pause are *presentation*, not sim truth.
- **L10 — the sim's `World` object owns pygame rendering.** `world.py:4` (`import pygame`), `:74-77` (fog `Surface`s), `:361` (`render`), `:474` (`render_fog`). The headless sim drags a pygame import + Surfaces for nothing.

### Two facts that make this much lower-risk than it sounds
1. **The pygame renderers are already DTO-ready.** Both `hero_renderer.py:12` and `enemy_renderer.py:11` consume via `_state_get(entity_state, key, default)` which does `entity_state.get(key)` if it's a `Mapping` else `getattr(...)`. A frozen dataclass DTO works through the `getattr` path **unchanged** — so swapping live entities for DTOs is mostly "build the DTO and pass it instead of the entity."
2. **The DTO field lists are already known** — they are exactly the fields the renderers read today (enumerated per-renderer in the Agent 03 task below). No guessing.

### What this sprint is NOT (hard non-goals — defer, do not touch)
- **No AI-boundary work (Round A-2 / WK67).** Do **not** create `ai/game_view.py` or `ai/commands.py`. Do **not** remove `"sim": self` (`sim_engine.py:433`), `"world": self.world` (`:431`), `"economy": self.economy` (`:430`), or `gs["engine"]=self`. Do **not** touch `get_game_state()`'s dict contract or any AI/behavior file. `get_game_state()` is the **AI+UI** surface and is out of scope this sprint — WK66 only touches the **render SNAPSHOT** (`build_snapshot`/`SimStateSnapshot`).
- **No god-file splits (Round B).** Do not split `ursina_renderer.py`/`hud.py`/`sim_engine.py`/etc. (We move two methods out of `world.py` for L10 — that is L10, not a Round-B split.)
- **No registries/dedup (Round C).** Do not build `BuildingDef`/`visual_specs` adoption/`HERO_CLASS_COLORS`. (DTOs may *read* existing config maps; do not consolidate them.)
- **Do not delete `SimEngine.selected_*` stubs** (`sim_engine.py:137-140`) — the audit ties those to the `get_game_state` split, which is WK67. Leave them.
- **No behavior changes of any kind.** If a change makes the game look or play differently, or flips a characterization pin or a determinism check, it is wrong — STOP and report. The single visible/measurable outcome of this sprint is *"nothing changed except the renderer can no longer mutate the sim."*
- **No version bump, no commit, no push** by any worker agent.

### PM scope corrections made during planning (agents do NOT need to re-investigate)
- **Move 4 is the SNAPSHOT half only.** Move 4 in the audit also says "remove presentation kwargs from `get_game_state`." In WK66 we apply Move 4 **only to the render snapshot** (`SimStateSnapshot` → `RenderSnapshot` + `PresentationFrameState`, and drop the presentation kwargs from `build_snapshot`). The `get_game_state` dict (AI+UI, with the live `world`/`economy`/`sim` refs) is **deferred to WK67**, where it pairs with Move 5 (`AiGameView`) so that hot surface is touched once, not twice. **Rationale:** the render snapshot and the AI/UI game-state dict are *separate code paths*; WK66 can fully clean the render path without touching the AI contract.
- **L2 fog/discovery write (Ursina `:1017`,`:1028-1029`) is behavior-sensitive and gets an investigate-first treatment.** Agent 03 must first determine whether building-discovery/tile-SEEN marking is *gameplay* state (follows hero vision → belongs in the sim) or *render* state (follows camera view → renderer-owned, but must live in a renderer dict, not on the sim entity), pin it with a fog/discovery digest, and only then change it. See the Agent 03 / Agent 10 tasks. If it proves entangled with the Ursina camera-reveal in a way that risks behavior, Agent 03 reports and we land the rest of Move 1 and defer this one sub-item — it must not force a behavior change.
- **Move 4 has an escape hatch.** Move 4 (the snapshot dataclass split) is the highest-blast-radius wave. If Wave 3 reveals it is too coupled to land safely this sprint, we land Moves 1+3+L10 (which already kill the L2 write-back — the keystone win) and push Move 4 to WK67. This is a PM call at Gate 2/3, not a worker decision.

---

## Goals (Definition of Done)

A. **The renderer no longer mutates sim state (L2 closed).** Zero `setattr(...)` onto sim entities/world from any renderer; zero `b.is_discovered = ...` / `world.visibility[..] = ..` writes from render code. Verified by grep + the snapshot-no-mutation guard staying green with the renderer exercised.
B. **Render DTOs exist and are consumed (L1 begun).** `game/sim/render_dto.py` defines frozen `UnitDTO`/`BuildingDTO`/`BountyDTO`; `build_snapshot` populates them; the pygame renderers (`hero`/`enemy`/`building`/`bounty`/`worker`) and the Ursina unit/building/bounty paths read DTO fields, keyed on stable `entity_id`/`hero_id` (no `id(obj)`).
C. **Presentation state is out of the sim snapshot (L6 closed).** `SimStateSnapshot` is split into `RenderSnapshot` (sim truth) + `PresentationFrameState` (camera/zoom/paused/screen/blend/tick, built by `GameEngine`). `SimEngine.build_snapshot` no longer takes camera/pause/screen kwargs. *(Move 4 — subject to the escape hatch above.)*
D. **`World.render`/`render_fog` are out of the sim (L10 closed).** A `game/graphics/world_terrain_renderer.py` owns terrain + fog drawing + the fog `Surface`s; `world.py` no longer imports `pygame` for rendering. `world.visibility` (and the live grid) is unchanged and still returned live.
E. **The characterization net is GREEN before AND after**, extended with: render-DTO field-parity, anim one-shot semantics, and a fog/discovery digest.
F. **All gates green** and **before/after screenshots are visually identical for every render path** (Ursina primary + pygame): units (idle + attack/hurt one-shots), buildings (built/damaged/construction/lair/neutral/palace), bounties (flag + reward + responder/tier labels), fog/discovery reveal, rubble, base overview.
G. Every worker updated **its own log** with evidence (grep outputs, screenshot verdicts, gate results) and a completion receipt. No commits/pushes by workers.

---

## Critical Design Rules (every agent reads these before any edit)

1. **Behavior-preserving only.** This sprint changes *how data crosses the render boundary*, never *what the game does*. Every wave must keep the full suite, `determinism_guard`, `qa_smoke --quick`, and the characterization pins green, and screenshots identical. A red pin or a changed pixel means the change was not inert — revert and report.
2. **No renderer may write to a sim entity or the world.** After your change, `rg -n "setattr\(" game/graphics` and `rg -n "\.is_discovered\s*=|\.visibility\[[^]]+\]\s*=" game/graphics` must return **zero** writes to sim objects (renderer-owned caches in renderer-owned dicts are fine). Paste the grep into your log.
3. **Key render state on stable IDs, never `id(obj)`.** Use `getattr(e, "hero_id", None) or getattr(e, "entity_id", None) or id(e)` as the transitional key (the `id(e)` fallback is only for fixtures that lack IDs). This is the WK63 stable-ID contract; `registry.py:28-30` currently violates it.
4. **DTOs are frozen value types — scalars and tuples only.** No live object references inside a DTO. The one trap: `HeroRenderer` reads `inside_building` (a *live building ref*, `hero_renderer.py:126`) to get `center_x/center_y` — flatten it to `inside_building_center: tuple[float,float] | None` in the DTO.
5. **Additive first, then migrate, then remove.** Wave 1 adds DTOs *alongside* the live tuples (snapshot grows, nothing breaks). Wave 2 switches renderers to read DTOs. Wave 3 removes the now-unused live tuples and finalizes the split. Never delete the old path until the new one is proven green.
6. **Render/UI changes require before/after screenshots + an explicit verdict** ("identical / not identical"), checking **alignment & layering first** (positions, no overlap/offset), then content. Cover **every** changed render path, not one scene. Ursina is the shipping renderer (`main.py:49 default="ursina"`) → it is the P0 screenshot path; pygame must also be captured (it drives headless capture + tests).
7. **Stay in your lane (file ownership below).** Do not edit a file owned by another agent in your wave. The producer (03) owns sim/snapshot/engine/world; the consumer (10) owns `game/graphics/**`. The only shared symbol is `game/sim/render_dto.py` (03 authors; 10 imports read-only).
8. **Determinism guardrail.** Moving the fog/discovery marking into the sim (Move 1b) touches fog state — Agent 04 signs off determinism at the final gate, and the fog/discovery digest pin must be byte-identical before/after. If the improved code surfaces a pre-existing nondeterminism, **record it for PM** — do not mask it.
9. **DO NOT COMMIT. DO NOT PUSH.** Update your own agent log, run your gates, write your completion receipt, then report. Git is a human gate.

---

## Wave Structure (orchestrator DAG — executed via subagents, PM-gated)

```
Wave 0          ── Gate 0 ──   Wave 1            ── Gate 1 ──   Wave 2           ── Gate 2 ──   Wave 3            ── Gate 3 (final) ──
┌───────────┐                  ┌──────────────┐                ┌─────────────┐                 ┌──────────────┐
│ 11 baseline│                 │ 03 DTOs +    │                │ 10 renderers│                 │ 03 snapshot  │
│  shots +   │   11 verifies   │  sim seq +   │  11 + 04:      │  consume    │  11 + 09 + 04:  │  split +     │  11 + 04 + 09:
│  extend    │   net GREEN     │  sim-side    │  pins GREEN,   │  DTOs +     │  full suite,    │  pygame entry│  full suite,
│  char net  │   on current    │  discovery   │  determinism, │  STOP all   │  determinism,   │  + L10        │  determinism,
│  (no code) │   code          │  (ADDITIVE)  │  no visual    │  write-back │  BROAD screen-  │ 10 ursina    │  qa, assets,
└───────────┘                  │ 10 trivial   │  change yet   │  + id-key   │  shot diff +    │  entry shape │  full screenshot
                               │  comment fix │                │             │  09 cohesion    │ (Move 4+L10) │  diff IDENTICAL
                               └──────────────┘                └─────────────┘                 └──────────────┘
```

**Why this order:**
- **Wave 0** captures the BEFORE baseline *before any code change* (so Wave-2/3 diffs are valid) and extends the net with the three pins this sprint depends on. Green-on-current-code is the precondition.
- **Wave 1 is purely additive** (DTOs added alongside live tuples; sim becomes the *redundant* source of discovery/fog marking while the renderer still marks too). Nothing visible changes → Gate 1 needs no screenshot diff, just green pins + determinism. This de-risks the contract before any consumer flips.
- **Wave 2 flips the consumers and removes the write-back** — the first visible-risk wave → Gate 2 is the broad screenshot diff.
- **Wave 3 does the structural snapshot split + L10** — highest blast radius, last, with the escape hatch.

---

## File Ownership (no write-collisions within a wave)

| Agent | Wave | Files it may EDIT/CREATE |
|---|---|---|
| 11 | W0 | **new** `tests/test_wk66_render_boundary.py`; capture-only into `docs/screenshots/wk66_baseline/**` (no production code) |
| 03 | W1 | **new** `game/sim/render_dto.py`; `game/sim_engine.py` (build_snapshot: add DTO tuples + sim-side anim-trigger seq); `game/world.py` + `game/sim/fog*`/fog-owning code (sim-side discovery/SEEN marking, ADDITIVE); `game/sim/snapshot.py` (add DTO + read-only flag fields, keep existing fields) |
| 10 | W1 | comment-only edits in `game/entities/guard.py:83`, `game/graphics/instanced_unit_renderer.py:111,221` (WK65 follow-up: `_unit_anim_surface`→`_compute_anim_frame`) — **comments only** |
| 11 | G1 | runs gates; no production code |
| 10 | W2 | `game/graphics/renderers/registry.py`, `renderers/hero_renderer.py`, `renderers/enemy_renderer.py`, `renderers/building_renderer.py`, `renderers/bounty_renderer.py`, `renderers/worker_renderer.py`, `game/graphics/ursina_renderer.py`, `game/graphics/instanced_unit_renderer.py`, `game/graphics/pygame_renderer.py` (DTO consumption + stop write-back) |
| 11 | G2 | capture into `docs/screenshots/wk66_after_w2/**`; gates; no production code |
| 09 | G2 | screenshot cohesion verdict; no production code |
| 03 | W3 | `game/sim/snapshot.py` (split → `RenderSnapshot` + `PresentationFrameState`), `game/sim_engine.py` (build_snapshot returns `RenderSnapshot`, drops presentation kwargs; remove now-unused live tuples), `game/engine.py` (build `PresentationFrameState`; pass both to renderer), `game/world.py` (L10: remove `render`/`render_fog` + fog Surfaces + pygame import), **new** `game/graphics/world_terrain_renderer.py`, `game/graphics/pygame_renderer.py` (swap `world.render`→`WorldTerrainRenderer`; accept the two split objects), `game/graphics/render_coordinator.py` (minimap caller of `world.render`) |
| 10 | W3 | `game/graphics/ursina_renderer.py` (accept `RenderSnapshot` + `PresentationFrameState` at the `update()` entry) — **only the snapshot-shape read**, no other edits |
| 11 | G3 | capture into `docs/screenshots/wk66_after/**`; full gates; no production code |
| 04 | G3 | runs `determinism_guard` repo-wide; review only; no production code |

**Collision audit:** W1 → 03 = sim/snapshot/world; 10 = comments in entities/graphics (different files). W2 → only 10 writes (graphics/**). W3 → 03 owns `pygame_renderer.py` (both the Move-4 entry change *and* the L10 swap, same file, single owner); 10 owns only `ursina_renderer.py`. No file is written by two agents in the same wave.

---

# Wave 0 — Baseline + safety net (no production code)

## Agent 11 (QA) — full before-baseline + extend the characterization net (Intelligence: HIGH)

**Why:** the Wave-2/3 screenshot diffs are only valid against a baseline captured *before any change*, and the three new pins are what prove Moves 1/3/4 are inert.

**Task 1 — capture the BEFORE baseline of every render path** into `docs/screenshots/wk66_baseline/`. First enumerate scenarios (`python tools/capture_screenshots.py --help`, `python tools/run_ursina_capture_once.py --help`) and record the list in your log. At minimum capture, for **both** the Ursina (primary) and pygame paths:
```powershell
# Ursina (primary / shipping renderer)
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk66_baseline/ursina_base --no-llm
# + the scenario(s) that exercise: units in combat (attack/hurt one-shots), buildings (built/damaged/construction/lair/neutral/palace), bounty flags, a fog/discovery reveal, rubble, and a mountain/underground view.
# pygame (secondary; drives headless capture + tests)
python tools/capture_screenshots.py --scenario base_overview    --seed 3 --out docs/screenshots/wk66_baseline/pyg_base    --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_panels         --seed 3 --out docs/screenshots/wk66_baseline/pyg_panels  --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_build_catalog  --seed 3 --out docs/screenshots/wk66_baseline/pyg_catalog --size 1920x1080 --ticks 480
```
If a named scenario for "units in combat" or "mountain/underground" does not exist, note it and capture the closest available (the same constraint WK65 hit). Record every exact command in your log.

**Task 2 — `tests/test_wk66_render_boundary.py`** (new). Reuse `tests/conftest.py` fixtures; mirror `tests/test_engine.py` style (`GameEngine(headless=True)`, `engine.update(1/60)` loops). Set `DETERMINISTIC_SIM=1` + a fixed seed for digest tests. Write these pins, **GREEN on current unmodified code**:
- **Render-DTO field-parity (pins Move 3).** Build a small sim, advance a few ticks, then for the first few heroes/enemies/buildings/bounties assert that the values a renderer reads off the live entity match a reference dict you compute. Pattern:
  ```python
  def _hero_view(h):
      return (round(h.x, 3), round(h.y, 3), int(h.hp), int(h.max_hp),
              str(getattr(h, "state", None)), str(h.hero_class), bool(h.is_alive))
  # After WK66 Move 3, an equivalent helper reading the UnitDTO must return the SAME tuple.
  ```
  Phrase the assertions on the *fields the renderers read* (enumerated in the Agent 03 task). This test is the contract both 03 and 10 code against.
- **Anim one-shot semantics (pins Move 1a).** A unit given a one-shot trigger plays it exactly once, then returns to its base clip; a second identical trigger replays it. Test at the registry/renderer level (construct a `HeroRenderer`/`RendererRegistry`, feed a state with a trigger twice with the trigger "changing", assert it re-plays). This pins that moving the trigger off the entity preserves "play once per trigger".
- **Fog / discovery digest (pins Move 1b).** With `DETERMINISTIC_SIM=1`, seed 3, run a headless `GameEngine` for a fixed tick count with a hero revealing terrain, then assert a stable digest of: the count of `is_discovered` buildings, and a checksum of the `world.visibility` grid (e.g. `sum(v==2)`, `sum(v==1)` counts). This digest MUST be byte-identical before and after Move 1b — it is the guardrail that moving discovery/SEEN marking into the sim did not change fog behavior.
- **Snapshot-no-mutation (extend WK65).** Import/extend the WK65 pattern: build a snapshot, *exercise a render pass over it* (call the renderer registry's animate/render against the snapshot entities with a dummy surface, or at minimum read every field a renderer reads), then assert the sim entity digest is unchanged. WK65's `test_wk65_snapshot_no_mutation.py` proved building the snapshot doesn't mutate; this extends it to *consuming* the snapshot doesn't mutate.

**Verify:** `python -m pytest tests/test_wk66_render_boundary.py -q` (GREEN on current code) · `python -m pytest tests/test_wk65_snapshot_no_mutation.py -q` (still GREEN). Update your log with the scenario list + commands + pin descriptions. **DO NOT COMMIT.**

### Gate 0 — Agent 11 confirms the net is green on current code and the baseline is captured. If a pin can't go green on current code, the pin is wrong — fix the pin (it must describe *current* behavior), not the code.

---

# Wave 1 — Additive DTOs + sim-side source-of-truth (no visible change)

> Everything in Wave 1 is **additive**: the snapshot *gains* DTO tuples and read-only flags; the sim *also* becomes a source of discovery/fog marking. The renderers are **unchanged** and keep working off live entities (and keep doing their own redundant discovery marking — idempotent, so behavior is identical). This proves the DTO contract before any consumer flips.

## Agent 03 (TechnicalDirector) — define DTOs, populate them, move discovery/anim source into the sim (Intelligence: HIGH)

**Files you own this wave:** `game/sim/render_dto.py` (new), `game/sim/snapshot.py` (add fields), `game/sim_engine.py` (build_snapshot), `game/world.py` + the sim's fog-update code (sim-side discovery/SEEN marking). **Do not touch `game/graphics/**`** (Agent 10's lane).

**Task 1 — `game/sim/render_dto.py` (new).** Define frozen value-type DTOs. The fields are exactly what the renderers read today — here are the enumerations (verified from the renderer source):

*Hero/enemy/peasant/guard/tax-collector share a unit shape. Read sites:* `hero_renderer.py:54-173` reads `hero_class, x, y, _render_anim_trigger, _anim_lock_one_shot, state(.name), is_inside_building, inside_building(.center_x/.center_y), facing, is_alive, size, hp, max_hp, name, gold, taxed_gold`. `enemy_renderer.py:44-124` reads `enemy_type, x, y, ..., state(.name), facing, is_alive, size, hp, max_hp`. Worker/guard/tax read the same core via `worker_renderer.py`.

```python
"""WK66 Round A-1: frozen value-type DTOs for the render boundary.
Renderers consume these instead of live sim entities so they cannot mutate sim state.
Scalars/tuples only — NEVER a live object reference (see inside_building_center)."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class UnitDTO:
    entity_id: str            # stable id (hero_id/entity_id); used as the render-state key
    kind: str                 # "hero" | "enemy" | "peasant" | "guard" | "tax_collector"
    x: float
    y: float
    facing: int
    is_alive: bool
    hp: float
    max_hp: float
    size: int
    state_name: str           # str(getattr(state, "name", state))
    anim_base: str            # precomputed base clip hint if cheap; else renderer derives from state_name
    anim_trigger: str | None  # the one-shot name (read-only); see anim_trigger_seq
    anim_trigger_seq: int     # monotonic; increments each time the sim sets a new trigger (replaces setattr-clear)
    # hero-only (default-safe for other kinds):
    hero_class: str = "warrior"
    enemy_type: str = "goblin"
    name: str = ""
    gold: int = 0
    taxed_gold: int = 0
    is_inside_building: bool = False
    inside_building_center: tuple[float, float] | None = None   # FLATTENED — never the live building ref

@dataclass(frozen=True)
class BuildingDTO:
    entity_id: str
    building_type: str        # already lowercased/normalized
    world_x: float
    world_y: float
    width: int
    height: int
    hp: float
    max_hp: float
    is_constructed: bool
    construction_progress: float
    color: tuple[int, int, int]
    is_lair: bool
    is_neutral: bool
    stash_gold: int
    stored_tax_gold: int
    level: int
    has_target: bool          # bool(getattr(building, "target", None)) — DO NOT carry the live target
    attack_range: int
    is_discovered: bool       # READ-ONLY (sim-owned after Move 1b)
    tile_visible: bool        # whether the building's tile is currently VISIBLE (sim-computed)

@dataclass(frozen=True)
class BountyDTO:
    bounty_id: str
    x: float
    y: float
    claimed: bool
    reward: int
    responders: int
    attractiveness_tier: str  # "low" | "med" | "high"
```
Add a small builder per type (`unit_dto_from(entity, kind)`, `building_dto_from(b)`, `bounty_dto_from(b)`) in this module so `build_snapshot` and tests construct DTOs identically. For `entity_id`, use `str(getattr(e, "hero_id", None) or getattr(e, "entity_id", None) or id(e))`.

**Task 2 — sim-owned anim-trigger sequence (enables Move 1a without write-back).** Today the renderer clears the trigger by `setattr(entity, "_render_anim_trigger", None)`. To let the renderer consume a trigger **without writing to the entity**, the trigger must be distinguishable per occurrence. Add a sim-owned monotonic counter:
- Grep every site that sets a trigger: `rg -n "_render_anim_trigger\s*=|_ursina_anim_trigger\s*=" game ai` (ignore the renderer *reads*/clears in `game/graphics`). Paste into your log.
- At each sim-side site that sets `entity._render_anim_trigger = "<name>"`, also do `entity._anim_trigger_seq = getattr(entity, "_anim_trigger_seq", 0) + 1`. (If triggers are set in only one or two places, this is a 1-line addition each.) Initialize `_anim_trigger_seq = 0` on the entity base classes if simplest.
- Populate `anim_trigger` + `anim_trigger_seq` into `UnitDTO`. **Do not remove the `_render_anim_trigger` field or the renderer's setattr yet** — Wave 1 is additive; Agent 10 removes the renderer write in Wave 2 and switches to "play when `anim_trigger_seq` increases."
- *If you find triggers are not set on the entity at all but emitted via the EventBus*, document that and tell PM — the seq approach may be unnecessary and a cleaner event-consume path exists; do not guess.

**Task 3 — make the sim the source of discovery/SEEN marking (Move 1b, ADDITIVE + investigate-first).**
- **Investigate first.** Grep `rg -n "is_discovered" game ai` and read `ursina_renderer.py:1010-1035`. Determine: does `b.is_discovered = True` fire when a building enters **hero vision** (gameplay) or **camera view** (render)? Read how `world.visibility` is set in the sim's fog update vs at `ursina_renderer.py:1028-1029`. Write your finding in your log **before** changing anything.
- **If it is gameplay (hero-vision) discovery:** add the marking to the sim's fog/visibility update so the sim sets `b.is_discovered` and the SEEN demotion the renderer currently does. Because the renderer *still* does its (now-redundant) marking in Wave 1, behavior is unchanged (setting True/SEEN twice is idempotent). Populate `BuildingDTO.is_discovered` + `tile_visible` from sim state in `build_snapshot`.
- **If it is render-only ("have I shown this building")**: it is presentation state — it should NOT live on the sim entity. In that case, leave the sim alone, populate `BuildingDTO.is_discovered`/`tile_visible` from the *sim's* visibility grid (which already exists), and tell Agent 10 to keep the "have I shown it" flag in a renderer-owned dict keyed by `entity_id` (Wave 2). Document which path you chose.
- **Guardrail:** Agent 11's fog/discovery digest pin MUST stay byte-identical. Run it after your change.

**Task 4 — populate DTOs in `build_snapshot` (ADDITIVE).** In `sim_engine.py:build_snapshot`, alongside the existing `heroes=tuple(self.heroes)` etc., add DTO tuples: `hero_dtos=tuple(unit_dto_from(h, "hero") for h in self.heroes)`, and likewise `enemy_dtos`, `peasant_dtos`, `guard_dtos`, `tax_collector_dto`, `building_dtos`, `bounty_dtos`. Add the matching fields to `SimStateSnapshot` (Task 5). Keep the existing live tuples — Wave 2 reads the DTOs, Wave 3 removes the live tuples.

**Task 5 — extend `SimStateSnapshot` (`snapshot.py`), additively.** Add the new DTO-tuple fields + read-only flag fields with defaults (so nothing else breaks). Do **not** remove or rename existing fields this wave. Do **not** split the dataclass yet (that's Wave 3).

**Verify (Wave 1):**
```powershell
python -m pytest tests/test_wk66_render_boundary.py -q          # parity + anim + fog digest still GREEN (proves additive change inert)
python -m pytest tests/test_wk65_snapshot_no_mutation.py -q     # still GREEN
python -m pytest -q                                             # full suite GREEN
python tools/determinism_guard.py --paths game/sim_engine.py game/sim/snapshot.py game/sim/render_dto.py game/world.py
python tools/qa_smoke.py --quick
```
Update your log with: the trigger-set grep, the discovery investigation finding + path chosen, the DTO field lists, and gate results. **DO NOT COMMIT.**

## Agent 10 (PerformanceStability) — WK65 trivial follow-up (comments only) (Intelligence: LOW for this wave)

**Why:** these three comments still reference the deleted `_unit_anim_surface`; fixing them now (in your lane, before your Wave-2 work) closes the WK65 follow-up. **Comment text only — no logic changes.**
- `game/entities/guard.py:83`, `game/graphics/instanced_unit_renderer.py:111` and `:221`: update the comment references from `_unit_anim_surface` to `_compute_anim_frame` (the live path).
**Verify:** `python -m pytest -q` (unaffected). Update your log. **DO NOT COMMIT.** (Then prep-read your Wave-2 files; do not edit them yet.)

### Gate 1 — Agent 11 + Agent 04 (Intelligence: 11 HIGH, 04 MEDIUM)
- 11: `python -m pytest -q` (full suite + all `wk66`/`wk65` pins GREEN) · `python tools/determinism_guard.py` (PASS) · `python tools/qa_smoke.py --quick` (PASS). **No screenshot diff needed** — Wave 1 made no visible change (confirm by re-capturing `ursina_base` and eyeballing it equals the baseline). If a pin is red, STOP — Wave 1 was supposed to be inert.
- 04: confirm the fog/discovery digest is byte-identical to Wave 0 and `determinism_guard` is clean after the sim-side discovery marking. Record verdict. **DO NOT COMMIT.**

---

# Wave 2 — Renderers consume DTOs + stop all write-back

## Agent 10 (PerformanceStability) — migrate renderers to DTOs, kill L2 (Intelligence: HIGH)

**Files you own:** `game/graphics/renderers/registry.py`, `renderers/{hero,enemy,building,bounty,worker}_renderer.py`, `game/graphics/ursina_renderer.py`, `game/graphics/instanced_unit_renderer.py`, `game/graphics/pygame_renderer.py`. **Import `render_dto` read-only; do not edit it.**

**Task 1 — `registry.py`: key on stable IDs (kills the `id()` finding).** Change `_key` (`:28-30`):
```python
@staticmethod
def _key(entity: object) -> str:
    return str(getattr(entity, "hero_id", None) or getattr(entity, "entity_id", None) or id(entity))
```
The dict type hints become `dict[str, ...]`. `prune()` (`:157-177`) already uses `_key` so it follows automatically. Verify pruning still drops dead renderers (the WK63 IDs are stable across frames, so the key is now *stable* — a correctness improvement).

**Task 2 — stop the anim-trigger write-back (Move 1a).** The renderers currently consume a one-shot by clearing it on the entity. Switch to "play when the sim's `anim_trigger_seq` increases", tracking the last-seen seq in renderer-owned state keyed by `entity_id`:
- pygame `hero_renderer.py:66-68` and `enemy_renderer.py:55-57`: **delete the `setattr(entity_state, "_render_anim_trigger", None)`**. Instead, the renderer instance keeps `self._last_trigger_seq` and compares `_state_get(entity_state, "anim_trigger_seq", 0)`; if it increased, play `_state_get(entity_state, "anim_trigger", None)`. (The renderer instance is already per-entity via the registry, so `self._last_trigger_seq` is the id-keyed record the audit asks for.)
- Ursina `_compute_anim_frame` (`ursina_renderer.py:554-565`): **delete both `setattr(..., None)` lines**. Track `self._unit_anim_state[obj_id]["last_seq"]` and trigger the clip when the DTO's `anim_trigger_seq` exceeds it. `obj_id` is already the per-unit key here.
- After this, `rg -n "_render_anim_trigger|_ursina_anim_trigger" game/graphics` should show only **reads** (no `setattr`).

**Task 3 — stop the fog/discovery write-back (Move 1b, render side).** Per Agent 03's Wave-1 finding:
- Delete `ursina_renderer.py:1017` (`b.is_discovered = True`) and `:1028-1029` (`_world.visibility[...] = ...`). Read `is_discovered`/`tile_visible` from the `BuildingDTO` instead (and the visibility grid read-only where needed for lair gating at `:1072`,`:1348`).
- **If Agent 03 determined it is render-only "have I shown it" state**, keep that flag in a renderer-owned `dict[str, bool]` keyed by `entity_id` (not on the sim object). Either way: **no writes to the world or the building.**

**Task 4 — bounty caches off the sim object (L2).** `bounty_renderer.py:52-103` stamps nine `_ui_cache_*` attributes on the live `Bounty`. Move them into a `BountyRenderer`-owned `dict` keyed by `bounty_id`:
```python
def __init__(self):
    self._cache: dict[str, dict] = {}   # bounty_id -> {"reward_val":..., "reward_surf":..., ...}
```
Read DTO fields (`reward`, `responders`, `attractiveness_tier`) off `BountyDTO`; cache the rendered `Surface`s in `self._cache[dto.bounty_id]`. No `setattr` on bounties.

**Task 5 — switch the render entry points to read DTO tuples.** Wherever the pygame renderer iterates `snapshot.heroes`/`enemies`/`buildings`/`bounties` and the Ursina renderer iterates the same, read the **DTO tuples** (`snapshot.hero_dtos`, etc.) Agent 03 added in Wave 1. The pygame `renderers/*` already accept `Mapping | object` via `_state_get`, and a frozen dataclass satisfies the `getattr` path — so most call sites change from passing the entity to passing the DTO. For `building_renderer.py` (which uses `getattr` directly, not `_state_get`), the frozen `BuildingDTO` also satisfies `getattr` unchanged. The `inside_building` ref read (`hero_renderer.py:126-129`) switches to `dto.inside_building_center`.

**Screenshot verification (MANDATORY — this is the first visible-risk wave).** Re-capture **every** path Agent 11 baselined, into `docs/screenshots/wk66_after_w2/`, and compare to `docs/screenshots/wk66_baseline/`. Give an explicit per-path verdict in your log (alignment/layering first, then content): **units idle + attack/hurt one-shots animate identically; buildings (built/damaged/construction/lair/neutral/palace) identical; bounty flags + reward + R:/tier labels identical; fog/discovery reveal identical; rubble identical; base overview identical.**
```powershell
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk66_after_w2/ursina_base --no-llm
# + every other Ursina + pygame scenario from Wave 0, same flags/seed/ticks
```
If anything differs, revert that piece and report — do not "fix" by changing behavior.

**Verify (Wave 2):**
```powershell
rg -n "setattr\(" game/graphics                                  # zero writes to sim entities (renderer-owned dicts are local vars, not setattr on entities)
rg -n "\.is_discovered\s*=|\.visibility\[[^]]+\]\s*=" game/graphics  # zero
python -m pytest tests/test_wk66_render_boundary.py tests/test_wk65_snapshot_no_mutation.py -q   # GREEN (now with renderer exercised)
python -m pytest -q                                              # full suite GREEN
python tools/determinism_guard.py --paths game/graphics/ursina_renderer.py game/graphics/pygame_renderer.py game/graphics/instanced_unit_renderer.py
python tools/qa_smoke.py --quick
```
Update your log with the two grep outputs, LOC/site counts, and the per-path screenshot verdict. **DO NOT COMMIT.**

### Gate 2 — Agent 11 + Agent 09 + Agent 04 (Intelligence: 11 HIGH, 09 LOW, 04 MEDIUM)
- 11: full suite GREEN · `determinism_guard` PASS · `qa_smoke --quick` PASS · re-capture and **diff every render path** vs baseline; verdict per path (identical / not). Any diff → report, do not pass the gate.
- 09: independent **visual cohesion** verdict on the Wave-2 screenshots — confirm units/buildings/bounties/fog read identically (this is the broad-coverage second pair of eyes per studio rule). LOW intelligence (fixed-recipe visual compare), but if a difference is ambiguous, escalate to PM.
- 04: `determinism_guard` repo-wide PASS; confirm no masked finding. **DO NOT COMMIT.**

> **PM checkpoint (escape hatch):** L2 is now closed (the keystone win). If Gate 2 is clean, proceed to Wave 3. If Move 4 looks risky given what Wave 2 surfaced, PM may bank Waves 0–2 and defer Move 4 + L10 to WK67.

---

# Wave 3 — Snapshot split (Move 4) + World.render out (L10)

## Agent 03 (TechnicalDirector) — split the frame DTOs + move World rendering out (Intelligence: HIGH)

**Files you own:** `game/sim/snapshot.py`, `game/sim_engine.py`, `game/engine.py`, `game/world.py`, `game/graphics/world_terrain_renderer.py` (new), `game/graphics/pygame_renderer.py`, `game/graphics/render_coordinator.py`.

**Task 1 — split `SimStateSnapshot` (Move 4 / kill L6).** Create two frozen dataclasses in `snapshot.py`:
- `RenderSnapshot` — **sim truth only**: the DTO tuples (`hero_dtos`, `enemy_dtos`, `peasant_dtos`, `guard_dtos`, `tax_collector_dto`, `building_dtos`, `bounty_dtos`), `world`, `trees`, `log_stacks`, `pois`, `fog_revision`, `gold`, `wave`, `castle` (as a `BuildingDTO`/id, not live), `underground_areas`, `rubble_records`, `vfx_projectiles`, `buildings_construction_progress`.
- `PresentationFrameState` — **engine-built presentation**: `camera_x`, `camera_y`, `zoom`, `default_zoom`, `screen_w`, `screen_h`, `paused`, `running`, `pause_menu_visible`, `sim_blend_fraction`, `sim_tick_id`, `selected_hero`/`selected_building` (selection is presentation).
- Keep `SimStateSnapshot` as a thin back-compat shim **only if** any consumer outside the two renderers still imports it — otherwise remove it. Grep `rg -n "SimStateSnapshot" game ai tools tests` first; if the only consumers are the two renderer entries (which 10 updates this wave) + tests (11 updates), you may replace it outright.

**Task 2 — `SimEngine.build_snapshot` returns `RenderSnapshot`, drops presentation kwargs.** Remove `camera_x/camera_y/zoom/default_zoom/paused/running/pause_menu_visible/screen_w/screen_h/selected_hero/selected_building` from the signature (`sim_engine.py:445-462`). The sim does not know about cameras or pause. **Remove the now-unused live tuples** (`heroes=tuple(self.heroes)` etc.) — Wave 2 migrated all readers to the DTO tuples, so these are dead now.

**Task 3 — `GameEngine` builds `PresentationFrameState` and passes both objects.** In `engine.py` (the `build_snapshot` wrapper at `:1487-1503` and the renderer call site), build the `PresentationFrameState` from engine-owned camera/window/pause/selection state and pass `(render_snapshot, frame_state)` to the renderer's `update()`. Coordinate the exact `update()` signature with Agent 10 (Task below) — the contract is `update(render_snapshot: RenderSnapshot, frame: PresentationFrameState)`.

**Task 4 — L10: move `World.render`/`render_fog` out (`world.py` → `world_terrain_renderer.py`).**
- Create `game/graphics/world_terrain_renderer.py` with a `WorldTerrainRenderer` that owns the fog tile `Surface`s (currently `world.py:74-77`) and the two methods (currently `world.py:361 render`, `:474 render_fog`), taking the `world` as an argument:
  ```python
  class WorldTerrainRenderer:
      def __init__(self):
          self._fog_tile_unseen = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA); self._fog_tile_unseen.fill((0,0,0,255))
          self._fog_tile_seen   = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA); self._fog_tile_seen.fill((0,0,0,170))
      def render(self, world, surface, camera_offset=(0,0)): ...      # body moved verbatim from world.render
      def render_fog(self, world, surface, camera_offset=(0,0)): ...  # body moved verbatim from world.render_fog
  ```
- In `world.py`: delete `render`, `render_fog`, the two fog `Surface`s, and — if nothing else in `world.py` needs it — the `import pygame`. **Keep all fog STATE**: `visibility`, `_currently_visible`, `update_visibility`, `_reveal_circle`, `fog_disabled`, `underground_visibility`. Those are sim logic. Keep `TileSpriteLibrary` import only if still used by non-render code (grep; it is used by `render`, so it likely moves to the new module).
- Update the two callers: `pygame_renderer.py` (instantiate one `WorldTerrainRenderer`, call `wtr.render(snapshot.world, surface, cam)` / `wtr.render_fog(...)` where it used to call `world.render(...)`) and `render_coordinator.py` (the minimap caller). Grep `rg -n "\.render_fog\(|world\.render\(|\.render\(surface" game/graphics` to find every call site.
- **`world.visibility` must still be readable live** — 25 files (incl. Ursina `world.visibility[ty][tx]`) read it. You are only moving the *drawing*, not the grid.

**Verify (Wave 3):**
```powershell
rg -n "import pygame" game/world.py                              # ideally gone (or justified non-render use noted)
rg -n "SimStateSnapshot|world\.render\(|world\.render_fog\(" game ai tools   # no stale references
python -c "import game.world"                                    # imports without pygame-render coupling
python -m pytest -q                                              # full suite GREEN
python -m pytest tests/test_wk66_render_boundary.py tests/test_renderer_snapshot_contract.py -q
python tools/determinism_guard.py --paths game/sim_engine.py game/sim/snapshot.py game/world.py game/graphics/world_terrain_renderer.py game/graphics/pygame_renderer.py
python tools/qa_smoke.py --quick
```
Update your log with the split shapes, the L10 call-site grep, and gate results. **DO NOT COMMIT.**

## Agent 10 (PerformanceStability) — adapt the Ursina entry to the split snapshot (Intelligence: MEDIUM)

**File you own:** `game/graphics/ursina_renderer.py` (the `update()` entry only).
- Change the renderer `update()` to accept `(render_snapshot, frame: PresentationFrameState)` per the contract in Agent 03 Task 3. Read camera/zoom/paused/selection from `frame`, sim truth from `render_snapshot`. This is a mechanical read-site change — do not alter any draw logic.
- **Do not touch any other file this wave** (pygame_renderer/world are 03's in Wave 3).

**Verify:** Ursina capture identical to baseline (`python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --out docs/screenshots/wk66_after/ursina_base --no-llm`) + `python -m pytest -q`. Update your log. **DO NOT COMMIT.**

### Gate 3 — FINAL (Agent 11 + Agent 04 + Agent 09) (Intelligence: 11 HIGH, 04 MEDIUM, 09 LOW)
- 11: `python -m pytest -q` (full suite + all wk66/wk65 pins GREEN) · `python tools/determinism_guard.py` (PASS) · `python tools/qa_smoke.py --quick` (PASS) · `python tools/validate_assets.py --report` (errors=0; 46 known warns). Re-capture **every** render path into `docs/screenshots/wk66_after/` and diff vs `docs/screenshots/wk66_baseline/`. Verdict per path: **identical / not identical** (alignment/layering first). Any diff → report, do not close.
- 04: `determinism_guard` repo-wide PASS; confirm the fog/discovery digest is still byte-identical to Wave 0; sign off that moving discovery/fog marking into the sim introduced no nondeterminism. Spot-run `qa_smoke --quick` twice with seed 3 for identical verdicts. **DO NOT COMMIT.**
- 09: final cohesion verdict across all paths.

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| A DTO drops/renames a field a renderer reads → wrong/blank render | Med | Field lists enumerated from renderer source in the Agent 03 task; render-DTO parity pin (Wave 0) is the contract; broad screenshot diff at Gate 2. |
| Moving discovery/fog marking into the sim changes fog behavior | Med | Investigate-first + behavior-preserving requirement; fog/discovery digest pin byte-identical before/after; Agent 04 determinism sign-off; if entangled, defer the sub-item. |
| Anim one-shots play twice / not at all after removing setattr-clear | Med | Sim-owned `anim_trigger_seq` + anim one-shot pin (Wave 0); attack/hurt screenshot sequence at Gate 2. |
| Move 4 snapshot split too coupled to land safely | Med | Escape hatch: bank Waves 0–2 (L2 already closed) and defer Move 4 + L10 to WK67 — a PM call at Gate 2. |
| L10 breaks the minimap or a `world.visibility` reader | Low-Med | Move only the *drawing*; keep the live grid + all fog state; grep every `world.render`/`render_fog` caller + every `.visibility` read; `import game.world` smoke. |
| `id()`→stable-id key regresses renderer pruning | Low | WK63 IDs are stable across frames (improvement, not regression); pruning uses the same `_key`; full suite + screenshots. |
| Screenshot scenario for "units in combat"/"underground" doesn't exist | Low | Agent 11 enumerates via `--help`, captures closest available, notes the gap (same as WK65). |

## Sprint Success Criteria
- [ ] Zero renderer write-back to sim entities/world (grep-clean: `setattr(` and `.is_discovered=`/`.visibility[..]=` in `game/graphics`).
- [ ] `game/sim/render_dto.py` exists; pygame + Ursina render paths consume `UnitDTO`/`BuildingDTO`/`BountyDTO`, keyed on stable IDs.
- [ ] `SimStateSnapshot` split into `RenderSnapshot` + `PresentationFrameState`; `build_snapshot` no longer takes presentation kwargs. *(or explicitly deferred to WK67 via the escape hatch — PM-recorded)*
- [ ] `World.render`/`render_fog` live in `game/graphics/world_terrain_renderer.py`; `world.py` no longer imports pygame for rendering; `world.visibility` still live.
- [ ] 4 characterization pins (parity, anim, fog digest, snapshot-no-mutation-on-consume) GREEN before AND after.
- [ ] Full suite + determinism + qa_smoke + validate_assets all green; **every** render-path screenshot diff = identical (Ursina + pygame).
- [ ] Every worker log updated with grep outputs + screenshot verdicts + receipt; no commits/pushes by workers.

## Follow-Up Backlog (after WK66)
- **WK67 = Round A-2 (AI boundary):** Move 5 (`AiGameView` — drop `sim`/`world`/`economy`/`engine` from `get_game_state`; split it into `UiGameView` + `AiGameView`; finally delete `SimEngine.selected_*` stubs) + Move 6 (`HeroCommand` — AI proposes, sim applies, modeled on `game/sim/direct_prompt_exec.py`) + leak L9 (invert `graphics → tools` runtime imports). + Move 2's "`AiGameView` is JSON-serializable" guard test.
- **WK68 = Round C (registries / single-source):** `BuildingDef` (clusters 1/2/6), `visual_specs` adoption (cluster 3), `HERO_CLASS_COLORS` (4), audio `contract.py` (5), the per-area helper extractions, purge the ~17 "WK34 REMOVED" zombie building keys.
- **If Move 4 was deferred:** fold the `SimStateSnapshot` split into WK67's `get_game_state` work.
- **Carry from WK65 (unrelated to A):** `tests/test_spawner.py` order-dependent global-rebind (Round-E hygiene); presentation wall-clock determinism notes (`engine.py:1133`, `ursina_renderer.py:343`); `timebase.now_ms()` wall-clock fallback.

---

## Kickoff Appendix (ready for Mode-2 transcription — SUBAGENT execution, no orchestrator)

**`pm_send_list_minimal` (waves):**
```
Wave 0:   11 (HIGH)
Gate 0:   11 (HIGH)
Wave 1:   03 (HIGH), 10 (LOW — comments only)        [03 and 10 parallel; different files]
Gate 1:   11 (HIGH), 04 (MEDIUM)
Wave 2:   10 (HIGH)
Gate 2:   11 (HIGH), 09 (LOW), 04 (MEDIUM)
Wave 3:   03 (HIGH), 10 (MEDIUM)                      [03 and 10 parallel; different files]
Gate 3:   11 (HIGH), 04 (MEDIUM), 09 (LOW)
Do NOT send: 02, 05, 06, 07, 08, 12, 13, 14, 15
```
**Intelligence rationale:** 03 high (novel DTO/snapshot contract design, behavior-sensitive fog/discovery move, the high-blast snapshot split + L10). 10 high in Wave 2 (the L2 write-back removal + DTO migration across both renderers is the visible-risk core), medium in Wave 3 (mechanical entry-signature read), low in Wave 1 (comment-only). 11 high throughout (novel render-boundary characterization + broad visual regression). 04 medium (determinism sign-off + fog-digest verification). 09 low (fixed-recipe screenshot cohesion compare; escalate ambiguity to PM).
*Optional:* keep 09 as a standing consult on every screenshot gate for extra visual coverage (studio rule: broad screenshot review, don't rubber-stamp one scene).

**Universal prompt (template):**
```
You are being activated for the wk66_round_a1_render_boundary sprint (Round A-1: render/snapshot boundary).
Onboard first: read .cursor/rules/01-studio-onboarding.mdc and your agent-NN-*.mdc.
Read your assignment in the PM hub:
.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json
 → sprints["wk66_round_a1_render_boundary"].rounds[<the round named in your activation>]
Your full task, code-shape examples, and exact verification + screenshot commands are in:
.cursor/plans/wk66_round_a1_render_boundary.plan.md  (find your agent's section)
Read the "Critical Design Rules" first. This sprint is BEHAVIOR-PRESERVING: the game must look and play
identically; the only change is that the renderer can no longer mutate the sim. No renderer may setattr on a
sim entity or write world.visibility/is_discovered. Additive-first, then migrate, then remove.
After completing your work: (1) update your agent log with evidence (grep outputs, LOC/site counts, gate results,
per-path screenshot verdicts); (2) run your verification gates; (3) write your completion receipt; (4) report status.
DO NOT COMMIT. DO NOT PUSH.
```
**Execution:** Claude Code Agent-tool subagents on `claude-opus-4-8`, role-onboarded; Agent 01 (parent) evaluates each wave by running the gates (`pytest` / `determinism_guard` / `qa_smoke` / `validate_assets`) and viewing screenshots, and loops fixes back to the owning agent until the Definition of Done holds. **Human gates:** Gate-2 visual approval (and the escape-hatch decision), Gate-3 final visual approval, and the commit/push (PM/Jaimie only).
```
```
