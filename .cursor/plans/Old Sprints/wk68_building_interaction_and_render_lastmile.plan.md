# WK68 Sprint Plan — Building Interaction Fixes + Hire-Hero + Render-DTO Last-Mile (kill L1) + Determinism-Hygiene

**Author:** Agent 01 (ExecutiveProducer_PM)
**Date:** 2026-05-29
**Sprint goal (DoD gate):** all tests pass + the building-menu buttons work + a Hire-Hero button exists on all 5 hirable buildings + renderers consume DTOs (live entity tuples deleted from the snapshot) + the WK67 AI-decision digest stays byte-identical.
**Predecessors:** WK66 Round A-1 (render boundary), WK67 Round A-2 (AI boundary).
**Reference docs:** `.cursor/plans/codebase_audit_2026-05-28_finding_inventory.md`, `.cursor/plans/GPT 5.5 Codebase Improvements Recommendations.md`, `.cursor/plans/wk66_round_a1_render_boundary.plan.md`, `.cursor/plans/wk67_round_a2_ai_boundary.plan.md`.

---

## 0. TL;DR for the next Agent 01 (your replacement PM)

This sprint is a **bundle of two independent tracks** the user explicitly asked to run together in WK68:

- **TRACK G — Gameplay/UX (player-facing, urgent).** A playtest found that **building-menu buttons aren't working, "Enter Building" in particular.** Fix the wiring and **add a "Hire Hero" button to the 4 player guilds + the Temple** (all 5 are hirable). *Functional fix only* — do NOT refactor the stringly-typed HUD-action dispatch (that's Round B); just make the buttons work and lock them with regression tests + screenshots.
- **TRACK R — Refactor (finishes Round A).** Migrate the **remaining renderers onto the WK66 render DTOs and DELETE the live entity tuples from `RenderSnapshot`** (kills boundary-leak **L1**). Land a **determinism-hygiene** pass first (so screenshot captures are byte-reproducible), and a small **chat-path purity** fix.

The two tracks touch almost-disjoint files (see §6 File Ownership). They run in parallel and meet at one shared verification gate (Wave V). The headline invariant for Track R is the same one WK66/WK67 held: **the WK67 AI-decision digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` must stay byte-identical** — the game must play exactly the same.

**You (PM) do not write code.** Dispatch role-onboarded `claude-opus-4-8` subagents, gate each wave (tests + greps + screenshots), and loop fixes. This doc does the reasoning for them so they don't have to guess.

---

## 1. Why this sprint

Two drivers landed at once and the user chose to bundle them:

1. **Player-facing regression.** Building-menu buttons don't work; you can't enter buildings. On a Steam Early-Access title this is a ship-quality bug and jumps the queue. We *also* want the long-requested per-building Hire-Hero affordance (today you can only hire via the `H` hotkey or the bottom command-bar button — there's no button on the guild's own panel).
2. **Finish Round A.** WK66 built the render DTOs and migrated the pygame *hero/enemy/building draw* paths; WK67 closed the AI boundary. But `RenderSnapshot` still carries **both** the frozen DTO tuples **and** the live entity tuples — the Ursina renderer and the pygame remainder (guards/peasants/tax-collector/bounties/minimap) still read live entities and key their entity maps on `id(obj)`. That is leak **L1** ("`SimStateSnapshot` is `@frozen` but every element is a live mutable entity"). Killing it completes the structural keystone and unblocks the Round B renderer/HUD splits (the audit's Move 11 explicitly "depends on 3 so split modules consume DTOs").

---

## 2. What we verified up front (so agents don't re-discover it)

### 2a. The building-button bug is a guard/positioning issue, NOT a missing consumer

The PM traced the full chain (with Explore-agent corroboration). **The `enter_building` dispatch is fully wired and the `"type"` strings all match:**

```
building_panel.handle_click  → returns {"type":"enter_building","building":b}   (building_panel.py:148-151)
  → input_handler.handle_mousedown result block                                  (input_handler.py:621-643)
  → elif result.get("type")=="enter_building":  bio.show(building);              (input_handler.py:634-641)
       apply_hud_pin_action("open_building_interior")  → engine.paused=True       (engine.py:1378-1381)
  → BuildingInteriorOverlay renders                                              (building_interior_overlay.py:53-92)
```

Every other panel button (`demolish_building`, `open_build_catalog`, marketplace/library/blacksmith research, palace upgrade, Close) also has a matching consumer in `input_handler.py:622-643`. **No orphaned action strings.** So the break is one of the guards/ordering below. **Ranked root-cause hypotheses (Agent 08 must CONFIRM which, with evidence, in Wave G0 before fixing):**

- **H1 — modal-pause guard swallows the click.** `input_handler.py:421-427`:
  ```python
  if c.paused and not c.pause_menu.visible:
      mc = getattr(c.hud, "memorial_card", None)
      bio = getattr(c.hud, "building_interior_overlay", None)
      mem_vis = mc is not None and getattr(mc, "visible", False)
      bio_vis = bio is not None and getattr(bio, "visible", False)
      if event.button != 1 or not (mem_vis or bio_vis):
          return          # ← every panel click is dropped here while paused, no modal open
  ```
  If the game is paused for any reason (speed-control pause, a stale `paused=True`) and no memorial/interior overlay is open, **every building-menu button silently no-ops.** This best matches "buttons … aren't working properly" (plural, general).
- **H3 — the hit-rect is `None` or offset.** `enter_building_button_rect` is reset to `None` every frame (`building_panel.py:276`) and only re-set if `_render_enter_building_button` actually draws (`building_panel.py:502-507`), computing the screen rect as `self.panel_x + local_rect.x, self.panel_y + local_rect.y`. If `panel_x/panel_y` (set at render time from `left_rect`, which the render-coordinator now supplies — `render_coordinator.py:103-107`) don't match where the button is *visually* drawn into the panel sub-surface, `collidepoint` misses and you get a silent `return True` (consumed at `input_handler.py:642`). **This is a plausible regression from the WK66/WK67 render-boundary refactor** and best matches "Enter Building wasn't working in particular."
- **H2 — broad `try/except Exception: pass`** around the HUD click ladder (`input_handler.py:445-537`) masks any error raised while building `gs = c.get_game_state()` or in `hud.handle_click`, so a real exception looks like "nothing happened." Lower likelihood but it's why this is hard to diagnose — Agent 08 should *temporarily* narrow/log this except during diagnosis.

**Enterable gate** (`building_panel.py:472-477`): a building shows the Enter button iff `max_occupants > 0 AND is_constructed AND type != "castle"`. Per `config.BUILDING_MAX_OCCUPANTS`: the 4 guilds, marketplace, blacksmith, inn, temples, and several POIs are enterable.

### 2b. Hire-Hero is a clean 3-edit add (mirror the Enter/Demolish buttons)

- `engine.try_hire_hero(self)` **already exists** (`engine.py:960-1030`) — takes **no args**, auto-selects `self.selected_building` if it's a hirable guild else scans `self.buildings`, checks `guild.can_hire()` cap + `economy.can_afford_hero()`, then `economy.hire_hero()` (deducts `HERO_HIRE_COST = 100`, `config.py:419`), `guild.hire_hero()`, spawns the `Hero`, emits `hero_hired`.
- Hirable set (`allowed`, `engine.py:962`): `{"warrior_guild","ranger_guild","rogue_guild","wizard_guild","temple"}`. Guild→class map (`engine.py:1006-1012`): warrior/ranger/rogue/wizard → same class; temple → cleric.
- `hiring_mixin.HiringBuilding` (`hiring_mixin.py:32-51`) provides `can_hire()` (`heroes_hired < max_heroes`), `hire_hero()` (increment), `on_hero_death()` (free a slot). Used by the 4 guilds + Temple.
- **No per-building hire button today.** Today: `H` hotkey (`input_handler.py:322-324`) and the command-bar button (`command_bar.py:64-69`) both call no-arg `try_hire_hero()`.
- **Decision (from the user): the button goes on all 5 hirable buildings (4 guilds + Temple), shows `$100` and `Heroes: hired/max`, and is visually disabled when at the cap or when `gold < 100`.**

### 2c. Render last-mile: snapshot still carries live entity tuples

`game/sim/snapshot.py` `RenderSnapshot` carries **both**:
- live entity tuples: `heroes, enemies, peasants, guards, buildings, bounties, tax_collector` (7 fields), AND
- WK66 frozen DTO tuples: `hero_dtos, enemy_dtos, peasant_dtos, guard_dtos, building_dtos, bounty_dtos, tax_collector_dto` (7 fields, value-type, in `game/sim/render_dto.py`).

Current readers of the **live** tuples (these must migrate to DTOs, then the live tuples get deleted):
- **pygame** (`game/graphics/pygame_renderer.py`): already on DTOs for hero/enemy/building **draws** (`:89-101`); still reads live `guards` (`:106`), `peasants` (`:109`), `tax_collector` (`:113`), `bounties` (`:149`), and live `heroes/enemies/buildings` for minimap/fog overlays (`:123,141-143,234-236`).
- **Ursina** (`game/graphics/ursina_renderer.py`): every `_sync_snapshot_*` reads `getattr(snapshot, "heroes"/"enemies"/...)` and keys its entity dict on **`id(h)`** (`:1282-1303` etc.), passing the **live** entity into `get_or_create_entity`. Only `bounty_dtos` is migrated (`:1672`).
- **instanced** (`game/graphics/instanced_unit_renderer.py`): reads live entities in its pack loop.

**Gap to close in Wave R1:** `UnitDTO` is missing fields the Ursina path reads — at minimum **`layer`** (used for underground layer-gating, `ursina_renderer.py:1286`). Audit the full read surface and add any missing fields *additively*.

### 2d. Determinism-hygiene: 3 confirmed global-state leaks + entity counters

Confirmed present (grep-verified 2026-05-29):
- `ai/basic_ai.py:34` `_AI_RNG = get_rng("ai_basic")` — module global, **not reseeded per build**; every `BasicAI` aliases it (`:91`).
- `game/entities/buildings/base.py:37` `RESEARCH_UNLOCKS = {...}` — module-global dict, **mutated in place** (`:65`) and never reset per build.
- `tests/perf_ursina_stress.py:24` and `tests/perf_stress_test.py:22` set `os.environ["SIM_SEED"] = "42"` **at import time** — pytest collection imports these, polluting `config.SIM_SEED` for the whole session.
- Entity-ID counters: `Peasant._spawn_counter` (already reset in WK67 — `sim_engine.py:90`). Audit for siblings (other class-global counters) and fold them into the same reset.

The WK67 digest test (`tests/test_wk67_ai_boundary.py:214-234`) already proves the *correct reset recipe* (reseed `_AI_RNG`, set all `RESEARCH_UNLOCKS` False) — Wave R0 moves that recipe into production as a **sim-owned per-build reset**, with the digest as the guardrail.

---

## 3. Scope — IN, and explicitly OUT

**IN (WK68):**
- **G1** Fix building-menu button functionality (Enter Building + verify all other panel buttons).
- **G2** Add Hire-Hero button to the 5 hirable buildings (cost + cap shown, cap/affordability-disabled).
- **G3** Regression tests (headless click→action dispatch per button; hire flow) + screenshots.
- **R0** Determinism-hygiene: one sim-owned per-build reset (`_AI_RNG`, `RESEARCH_UNLOCKS`, entity counters) + test-side `SIM_SEED`-at-import fix.
- **R1** Extend render DTOs additively (`layer` + any missing Ursina read fields); build in `build_snapshot`.
- **R2** Migrate Ursina + instanced + pygame-remainder renderers onto DTOs; key on stable `entity_id`, not `id(obj)`.
- **R3** Delete the 7 live entity tuples from `RenderSnapshot`; fix test/tool constructors; grep-completeness check (kills L1).
- **R4** Chat-path purity: migrate `direct_prompt_exec`'s chat caller to `build_ai_view()`.

**OUT (explicitly deferred — do NOT do these here):**
- **Typed HUD-action dispatch / `HudAction` enum** (audit ui-hud/input findings). User chose *functional fix only*. → Round B HUD/input split.
- **`UiGameView`** (split the UI `get_game_state` dict + rehome HUD `engine` reads). → pairs with the `hud.py` split in Round B.
- **Removing the live `world` from the snapshot** (terrain/fog ownership, L10 remainder). → Round B world.py split. Keep `world`, `trees`, `log_stacks`, `castle`, `vfx_projectiles`, `underground_areas`, `rubble_records` on the snapshot as-is this sprint.
- **The `ursina_renderer.py` / `hud.py` god-file splits** (Move 11). → Round B. (We migrate the renderer's *data source*; we do not split the file.)
- **Making `RESEARCH_UNLOCKS` an injectable per-sim object** (`research_state.py`). → Round B. WK68 does the lighter per-build *reset* only.

---

## 4. Definition of Done

A sprint is DONE only when ALL of these are PM-verified (not just agent-claimed):

- **A.** `python -m pytest` → **all pass** (current baseline 601 passed / 4 skipped / 0 failed; new tests add to "passed").
- **B.** `python tools/determinism_guard.py` → clean.
- **C.** The **WK67 AI-decision digest is byte-identical**: `tests/test_wk67_ai_boundary.py` digest pin still equals `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`. (If R0 forces a *justified* change, see §8 R0 — requires explicit PM sign-off + re-pin rationale; default expectation is UNCHANGED.)
- **D.** **Grep-completeness for L1:** after R3, a repo-wide search for production reads of `snapshot.heroes|snapshot.enemies|snapshot.peasants|snapshot.guards|snapshot.buildings|snapshot.bounties|snapshot.tax_collector` (and the `getattr(snapshot,"heroes",…)` Ursina variants) returns **zero** hits in `game/graphics/**` and `game/**` production code. Renderers read only `*_dtos`/`*_dto`.
- **E.** **Enter Building works** — a headless regression test posts a left-click at the Enter button's hit-rect on a selected, constructed guild and asserts `building_interior_overlay.visible` becomes `True`. Plus a screenshot of the open interior.
- **F.** **Every other building-menu button works** — headless click→action tests for demolish, build-catalog (castle), marketplace/library/blacksmith research, palace upgrade, Close — each asserts the expected side effect.
- **G.** **Hire-Hero button works** — on each of the 5 hirable buildings: button renders (screenshot), shows `$100` + `Heroes: x/max`, is disabled at cap / when broke, and a click hires (gold −100, `heroes_hired +1`, a new `Hero` in `engine.heroes`, `hero_hired` event). A headless test asserts the full effect.
- **H.** **Visual parity (Track R):** before/after screenshots for **every** render path in **both** renderers (heroes, enemies, peasants, guards, tax-collector, buildings, bounties, fog/minimap) show no regression — units don't flicker, duplicate, or disappear after the `id()`→`entity_id` keying change. pygame: `ui_panels`, `base_overview`. Ursina: `base_overview`, `ursina_melee_combat`.
- **I.** `python tools/qa_smoke.py --quick` → green.
- **J.** Each participating agent has updated **its own** department log; Agent 01's PM hub records the close.

---

## 5. Critical design rules (read before touching code)

**Track R (refactor) — behavior-preserving:**
1. **The snapshot is the ONLY data the renderer sees. No write-back.** DTOs are frozen value types; never stamp state onto a sim entity from the renderer (WK66 already removed `_render_anim_trigger` write-back — keep it removed; the DTO carries `anim_trigger` + `anim_trigger_seq` read-only).
2. **Stable-ID keying, consistently.** When migrating Ursina/instanced, key the entity dict on `dto.entity_id` (a stable string), not `id(obj)`. The key must be stable across frames and unique across entities — verify with screenshots that nothing flickers/duplicates.
3. **Additive → migrate → delete, in that order across waves.** R1 only ADDS fields (nothing reads them yet). R2 flips readers. R3 deletes the live tuples. Never delete a field a reader still touches.
4. **Determinism is sacred.** No change may alter iteration order, RNG call order, or `now_ms()` usage. The digest (gate C) is the tripwire. The anim clock already derives from `sim_tick_id` under `DETERMINISTIC_SIM` (WK67) — keep that; the DTO carries `anim_trigger_seq` so the clip plays on a *counter increase*, never on wall-clock state stamped to the entity.
5. **Keep `SimStateSnapshot` as the back-compat alias** for `RenderSnapshot`. Tests reference it.

**Track G (gameplay) — functional, minimal blast radius:**
6. **Functional fix only.** Do NOT introduce a typed action enum or restructure the dispatch ladder. Fix the specific broken guard/positioning and add tests. The stringly-typed refactor is Round B (deferred — see §3 OUT).
7. **Mirror the existing button idiom.** The Hire button copies the shape of `_render_enter_building_button` + the `handle_click` branch + the `input_handler` consumer. Do not invent a new dispatch path.
8. **Don't change hire economics.** Reuse `engine.try_hire_hero` / `economy.hire_hero` / `guild.can_hire` exactly. The only allowed engine change is letting the panel target a *specific* selected guild (set `selected_building` before calling, or add an optional `guild=` param) — preserve the existing no-arg behavior for the hotkey/command-bar callers.

**Both tracks:**
9. **Screenshot-verify every visual change** (memory: agents must capture + give a visual verdict; review broad coverage, not one narrow scenario; check alignment/layering before styling).
10. **DO NOT COMMIT** and **do not iterate after `status=done`** (memory: WK53 lesson). Agents report done; PM gates and decides commits.

---

## 6. File ownership (prevents the two tracks from colliding)

| File / area | Track | Owner | Notes |
|---|---|---|---|
| `game/ui/building_panel.py` | G | 08 | Hire button render + hit-rect + handle_click branch; Enter-button positioning fix |
| `game/input_handler.py` | G | 08 | Pause-guard / dispatch fix; add `hire_hero` consumer in result block (621-643) |
| `game/ui/hud.py` (handle_click only) | G | 08 | Only if the fix requires it; coordinate — do not touch render-coordinator regions |
| `game/ui/building_renderers/guild_panel.py` | G | 08 | Cap/cost label source (already shows `Heroes: x/max`) |
| `game/engine.py` **lines ~960-1030** (try_hire_hero) | G | 08 | Optional `guild=` param; keep no-arg path intact |
| `game/engine.py` **lines ~1540-1608** (build_presentation_frame / snapshot assembly) | R | 03 | **Different region** from G's edits — safe, but 03 & 08 must not edit the same method |
| `game/sim/snapshot.py` | R | 03 | R1 add DTO fields; R3 delete live tuples |
| `game/sim/render_dto.py` | R | 03 | R1 add `layer` + missing fields + builders |
| `game/sim_engine.py` **build_snapshot** | R | 03 | Populate new DTO fields |
| `game/sim_engine.py` **__init__ reset** (~79-90) | R | 04 | Per-build determinism reset (extends the existing `Peasant._spawn_counter=0`) |
| `game/graphics/ursina_renderer.py` | R | 09 | Migrate `_sync_snapshot_*` to DTOs; `id()`→`entity_id` |
| `game/graphics/instanced_unit_renderer.py` | R | 10 | Migrate pack loop to DTOs |
| `game/graphics/pygame_renderer.py` | R | 09 | Migrate guards/peasants/tax_collector/bounties + minimap reads |
| `ai/basic_ai.py`, `game/entities/buildings/base.py` (reset hooks) | R | 04 | Reseed `_AI_RNG`; reset `RESEARCH_UNLOCKS` (called from the sim reset) |
| `game/sim/direct_prompt_exec.py` (+ chat caller) | R | 06 | Migrate chat path to `build_ai_view()` |
| `tests/perf_ursina_stress.py`, `tests/perf_stress_test.py` | R | 04 | Move `SIM_SEED`-at-import into a fixture/main-guard |
| `tests/test_wk68_*.py` (new) | both | 11 | Regression tests for both tracks |
| screenshots under `docs/screenshots/wk68_*` | both | 11 | Capture + visual verdict |

**Only genuine overlap: `game/engine.py`.** Track G edits `try_hire_hero` (~960-1030); Track R edits the snapshot/frame assembly (~1540-1608). Different methods → safe. If either must touch the other's region, route through PM.

---

## 7. Wave DAG

```
                 ┌─────────────────────────── TRACK G (gameplay) ───────────────────────────┐
   G0 diagnose ─► G1 fix buttons ─► G2 hire button ─────────────────────────────────────────┐
   (08)           (08)              (08)                                                      │
                                                                                              ▼
                 ┌─────────────────────────── TRACK R (refactor) ───────────────────────┐   Wave V
   R0 determinism-hygiene (04) ──┬─► R1 extend DTOs (03) ─► R2 migrate renderers ─► R3 delete │  (11)
   [LANDS FIRST — de-risks caps] │                          (09 + 10)                tuples   │  full suite
                                 └─► R4 chat purity (06) ─────────────────────────────► (03)  │  + digest
                                                                                              │  + screenshots
                 G3 regression tests + screenshots (11) runs alongside G1/G2 ─────────────────┘
```

- **R0 lands first** (independent; stabilizes in-process determinism so R2's screenshot captures are byte-reproducible).
- **R1 → R2 → R3 strictly ordered** (additive → migrate → delete).
- **R4 parallel** after R0.
- **Track G fully parallel to Track R** (disjoint files per §6).
- **Wave V** is the single shared gate; nothing commits until V is green.

---

## 8. Per-wave tasks (with code shapes + exact verification)

> Every agent: onboard via `.cursor/rules` for your agent #, read the PM-hub log entry for your task, follow this plan. Use `claude-opus-4-8`. Update your own department log at the end. **DO NOT COMMIT.**

### Wave R0 — Determinism-hygiene (Agent 04, lands first)

**Goal:** one sim-owned per-build reset so two in-process builds with the same seed produce identical AI behavior, and pytest collection stops polluting `SIM_SEED`.

**Tasks:**
1. In `SimEngine.__init__` (next to the existing `Peasant._spawn_counter = 0` at `sim_engine.py:90`), add a single private `_reset_global_sim_state()` that:
   - Reseeds `ai.basic_ai._AI_RNG` to the state a *fresh-process* build with the active seed would have (use the same `get_rng("ai_basic")` derivation from the active `config.SIM_SEED`). Reference recipe: `tests/test_wk67_ai_boundary.py:214-234`.
   - Resets every key in `game/entities/buildings/base.RESEARCH_UNLOCKS` to `False`.
   - Resets any sibling class-global entity counters you find (grep `_spawn_counter`, `_counter`, `_next_id`, `_id_counter` in `game/entities/**`).
2. Move the `os.environ["SIM_SEED"] = "42"` lines out of import scope in `tests/perf_ursina_stress.py:24` and `tests/perf_stress_test.py:22` — put them inside the `if __name__ == "__main__":` guard (or a fixture), so importing the module during pytest collection no longer mutates the env.

**The digest guardrail (critical — read carefully):**
- The WK67 digest `b73961…` was computed in a **pinned-env subprocess** (clean globals). In a fresh process the *first* build is already clean, so a correctly-implemented per-build reset is a **no-op on the first build** → **the digest must stay `b73961…`**.
- **Tiered DoD for R0:**
  - **Tier 1 (required):** Test-side `SIM_SEED` fix + entity-counter audit + the `RESEARCH_UNLOCKS` per-build reset land, and the digest is **unchanged**.
  - **Tier 2 (target):** The `_AI_RNG` per-build reseed also lands with the digest **unchanged** (i.e., reseeding to the fresh-process state preserves first-build behavior). Prove it by adding a test that builds two `SimEngine`s **in one process** with the same seed and asserts their 300-tick AI digests are **equal to each other AND equal to `b73961…`**.
  - **If the `_AI_RNG` reseed cannot be made digest-preserving** (reseeding changes first-build behavior), **STOP and report to PM.** Do NOT silently re-pin. Default decision: defer the `_AI_RNG` production reseed to the Round B `research_state.py`/RNG-injection refactor; land Tier 1 only. PM decides.

**Verify:**
```powershell
python -m pytest tests/test_wk67_ai_boundary.py -q          # digest pin must stay b73961…
python -m pytest tests/perf_stress_test.py -q --collect-only # collection must not set SIM_SEED
python tools/determinism_guard.py
```
Plus the new in-process two-build digest-equality test.

### Wave R1 — Extend render DTOs additively (Agent 03)

**Goal:** the DTOs carry every field the *remaining* renderers (Ursina, instanced, pygame guards/peasants/tax/minimap) read from live entities — so R2 can flip them with zero behavior change.

**Tasks:**
1. Audit the live-entity reads in `ursina_renderer.py` `_sync_snapshot_{heroes,enemies,peasants,guards,tax_collector}`, `instanced_unit_renderer.py`, and `pygame_renderer.py` (guards/peasants/tax_collector + minimap). Make a field list.
2. Add the missing fields to `UnitDTO`/`BuildingDTO` **additively** (defaults preserve current behavior). Known gap: **`layer: int = 0`** (read at `ursina_renderer.py:1286` for underground gating). Add any others the audit surfaces (e.g. fields the minimap dot overlay needs).
3. Populate them in the `build_snapshot` builders (`render_dto.py` `unit_dto_from`/`building_dto_from` + the `sim_engine.build_snapshot` call sites), reading the live entity exactly as the renderers do today (same getattr defaults).
4. Extend the WK66 DTO field-parity pin (`tests/test_wk66_render_boundary.py::test_render_dto_field_parity`) to cover the new fields.

**Code shape (additive — note the defaults):**
```python
@dataclass(frozen=True)
class UnitDTO:
    # ... existing fields ...
    layer: int = 0           # WK68 R1: underground layer gate (ursina_renderer.py:1286)
    # + any other field the Ursina/instanced/minimap paths read from the live entity
```

**Verify:** `python -m pytest tests/test_wk66_render_boundary.py -q` (parity pin green); DTOs build without error; nothing reads the new fields yet (grep confirms additive).

### Wave R2 — Migrate the remaining renderers onto DTOs (Agents 09 + 10)

**Goal:** no renderer reads a live entity tuple; all key on stable `entity_id`.

**Agent 09 — Ursina (`ursina_renderer.py`) + pygame remainder (`pygame_renderer.py`):**
- For each `_sync_snapshot_{heroes,enemies,peasants,guards,tax_collector}`: iterate the matching `*_dtos` tuple instead of `getattr(snapshot,"heroes",())`; read `dto.x/dto.y/dto.hero_class/dto.is_alive/dto.layer/…`; **key `self._entities` on `dto.entity_id`** instead of `id(h)`; change `get_or_create_entity(h, …)` to take the DTO (or its scalar fields). The buildings sync already has `building_dtos` — switch it too.
- pygame: switch `:106` guards, `:109` peasants, `:113` tax_collector, `:149` bounties, and the minimap/fog reads at `:123,141-143,234-236` to the DTO tuples (or DTO-derived position lists). The HUD radar/minimap needs only positions/kinds — feed it from DTOs.
- **The `id()`→`entity_id` change is the riskiest part.** Verify with screenshots that units track frame-to-frame (no flicker, no ghosts, no duplicates). Pay attention to culling/re-enable paths (`ursina_renderer.py:1294-1305`) that currently use `id(h)`.

**Agent 10 — instanced renderer (`instanced_unit_renderer.py`) + perf:**
- Migrate the pack loop to read `*_dtos`; key on `entity_id`.
- Confirm no per-frame perf regression on the DTO path (the DTOs are built once in `build_snapshot`; the renderer just reads them). Run `tools/perf_benchmark.py` before/after. **Per memory: NO tree-density/grass-stride cuts — gains/parity come from the data path, not content reduction.**

**Verify (both):**
```powershell
python -m pytest -q
python tools/determinism_guard.py
# pygame visual:
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk68_pygame_base --size 1920x1080 --ticks 480
python tools/capture_screenshots.py --scenario ui_panels --seed 3 --out docs/screenshots/wk68_pygame_panels --size 1920x1080 --ticks 480
# Ursina visual (both renderers must agree visually with pre-migration):
python tools/run_ursina_capture_once.py --scenario base_overview --ticks 480 --no-llm --out docs/screenshots/wk68_ursina_base
python tools/run_ursina_capture_once.py --scenario ursina_melee_combat --ticks 240 --no-llm --out docs/screenshots/wk68_ursina_combat
```
Each agent captures BEFORE (current `main`) and AFTER (their branch) and gives a per-path visual verdict.

### Wave R3 — Delete the live entity tuples (Agent 03) — KILLS L1

**Goal:** remove `heroes, enemies, peasants, guards, buildings, bounties, tax_collector` from `RenderSnapshot`. The grep-completeness check IS the proof migration is complete.

**Tasks:**
1. Remove the 7 live fields from `RenderSnapshot` (`snapshot.py`) and stop populating them in `build_snapshot`.
2. Fix every constructor/reader that breaks: `sim_engine.build_snapshot`, any test/tool that builds a `RenderSnapshot` with those kwargs, and any straggler reader.
3. **Completeness grep (gate D):**
   ```powershell
   # must return ZERO production hits (game/** excluding tests):
   ```
   Use Grep for `snapshot\.(heroes|enemies|peasants|guards|buildings|bounties|tax_collector)\b` and `getattr\(snapshot,\s*["'](heroes|enemies|peasants|guards|buildings|bounties|tax_collector)` across `game/`. Renderers read only `*_dtos`/`*_dto`.
4. Keep `world, trees, log_stacks, castle, vfx_projectiles, underground_areas, rubble_records` (out of scope — §3).

**Verify:** full `pytest`, `determinism_guard`, the grep returns zero production hits, and re-run the R2 screenshots to confirm deletion changed nothing visually.

### Wave R4 — Chat-path purity (Agent 06, parallel after R0)

**Goal:** the LLM chat caller consumes a pure `AiGameView`, not the live `get_game_state` dict (finishes Move 5).

**Tasks:** find the chat-path caller in `game/sim/direct_prompt_exec.py` (and its caller) that still reads `game_state.get("sim"/"world"/"economy")`; route it through `SimEngine.build_ai_view()` (the WK67 view). Add/extend an AI-view-purity pin asserting the chat path holds no live `sim/world/economy/engine` ref.

**Verify:** `python -m pytest tests/test_wk67_ai_boundary.py -q` + a new chat-purity assertion; digest unchanged.

> R4 is the **lowest-priority** item — if R2/R3 run long, PM may cut it to a WK69 follow-up. It must not block Wave V.

### Wave G0 — Diagnose the button break (Agent 08)

**Goal:** confirm which root cause (H1 pause-guard / H3 hit-rect / H2 masked exception) with **evidence**, before fixing.

**Tasks:** write a throwaway headless repro (becomes the G3 regression test): build an engine, place + select a constructed guild, render the building panel once (to populate hit-rects), then synthesize a left-`MOUSEBUTTONDOWN` at the center of `enter_building_button_rect` and route it through the real input handler. Observe where the click dies:
- Is `c.paused` True at click time? → H1. Log `c.paused`, `pause_menu.visible`, `bio.visible` at `input_handler.py:421`.
- Does `enter_building_button_rect` exist and does its rect match where the button visually draws? Compare the rect to the panel sub-surface blit origin. → H3.
- Does an exception fire inside the `try` at `input_handler.py:445`? Temporarily log it. → H2.

Report the confirmed cause + exact line(s) to PM before Wave G1. **Do not guess-fix.**

### Wave G1 — Fix the buttons (Agent 08)

**Goal:** Enter Building works, and every other panel button works.

**Tasks:** apply the *minimal* fix for the confirmed cause:
- If **H1**: the panel-button path must run even when `paused` for non-modal reasons. Narrow the guard at `input_handler.py:421-427` so left-clicks that land on a visible building panel's buttons are processed (e.g. allow the click through when `c.building_panel.visible` and the pos is within the panel), while still blocking world interaction. Keep the existing memorial/interior allowances.
- If **H3**: fix the hit-rect origin so `enter_building_button_rect` (and the other button rects) are computed in the same coordinate space they're drawn in (reconcile `panel_x/panel_y` + `local_rect` vs. the panel sub-surface blit origin, accounting for the render-coordinator `left_rect`). Verify visually that the clickable region overlaps the drawn button.
- If **H2**: fix the underlying exception; narrow the bare `except` to log (functional-fix scope: log + re-raise in dev, don't restructure the ladder).

**Verify:** the G0 repro now passes (interior opens); manually/headlessly exercise demolish, build-catalog, research, upgrade, Close — each fires its effect.

### Wave G2 — Hire-Hero button (Agent 08)

**Goal:** a Hire-Hero button on the 4 guilds + Temple, cost + cap shown, cap/affordability-disabled, click hires.

**Three edits (mirror Enter/Demolish):**
1. **Render + hit-rect** — new `_render_hire_hero_button(self, surface, building, y)` in `building_panel.py`, called right after the enter button (`building_panel.py:303`). Gate: `self._building_type_key(building) in {"warrior_guild","ranger_guild","rogue_guild","wizard_guild","temple"} and getattr(building,"is_constructed",True)`. Show `Hire Hero — $100` and `Heroes: {heroes_hired}/{max_heroes}`; render **disabled** (greyed, no hit-rect or a no-op hit-rect) when `not building.can_hire()` or `economy.player_gold < HERO_HIRE_COST`. Add `self.hire_hero_button_rect` next to `enter_building_button_rect` (`:56`) and reset it to `None` each frame next to `:276`. Add the hover entry in `update_hover` (`:203-226`).
   ```python
   def _render_hire_hero_button(self, surface, building, y):
       self.hire_hero_button_rect = None
       if self._building_type_key(building) not in _HIRABLE_TYPES:
           return y
       if not getattr(building, "is_constructed", True):
           return y
       can_hire = (not hasattr(building, "can_hire")) or building.can_hire()
       affordable = self._economy.player_gold >= HERO_HIRE_COST  # source economy as the panel already does
       enabled = can_hire and affordable
       # ... draw button (greyed if not enabled), label "Hire Hero  $100", sublabel "Heroes: h/max"
       if enabled:
           local_rect = pygame.Rect(...)            # SAME coord convention as _render_enter_building_button
           self.hire_hero_button_rect = pygame.Rect(self.panel_x+local_rect.x, self.panel_y+local_rect.y,
                                                     local_rect.width, local_rect.height)
       return y + row_h
   ```
2. **handle_click branch** — in `building_panel.handle_click`, before the final `return True` (`:201`):
   ```python
   if self.hire_hero_button_rect and self.hire_hero_button_rect.collidepoint(mouse_pos):
       building = self.selected_building
       if building and getattr(building, "is_constructed", True) and (
           (not hasattr(building, "can_hire")) or building.can_hire()
       ):
           return {"type": "hire_hero", "building": building}
   ```
3. **Consumer** — in `input_handler.py` result block, after the `enter_building` branch (`:641`):
   ```python
   elif isinstance(result, dict) and result.get("type") == "hire_hero":
       building = result.get("building")
       if building is not None:
           c.selected_building = building      # target THIS guild
       c.try_hire_hero()
       return
   ```
   (Keep `try_hire_hero` no-arg; setting `selected_building` is enough since it auto-targets it. Optionally add `try_hire_hero(self, guild=None)` defaulting to the current behavior — do NOT break the hotkey/command-bar callers.)

Define `_HIRABLE_TYPES = frozenset({"warrior_guild","ranger_guild","rogue_guild","wizard_guild","temple"})` once (reuse the engine's `allowed` set if cleanly importable; otherwise a local constant with a comment pointing at `engine.py:962` as the source of truth).

**Verify:** screenshot each of the 5 buildings' panels showing the button (enabled and — for one — disabled-at-cap). Headless test: click hires (gold −100, `heroes_hired +1`, hero count +1, `hero_hired` event), and the disabled state blocks the hire.

### Wave G3 — Regression tests + screenshots (Agent 11, alongside G1/G2)

**Tasks:**
1. New `tests/test_wk68_building_buttons.py`: a headless harness that, for a selected constructed building, posts a left-click at each button's hit-rect through the real input handler and asserts the effect:
   - Enter → `building_interior_overlay.visible` True (gate E).
   - Demolish → `demolish_confirm_overlay.visible` True.
   - Build-catalog (castle) → catalog opens.
   - Research (marketplace/library/blacksmith), Palace upgrade, Close → their effects (gate F).
   - **Pause-state regression:** if H1 was the cause, add a test that a panel-button click works while the sim is paused for a non-modal reason.
2. New `tests/test_wk68_hire_button.py`: hire flow + cap-disabled + broke-disabled (gate G).
3. Screenshots (gate H + E + G): pygame `ui_panels`/`base_overview`, the open interior, and each of the 5 hire panels. Give a written visual verdict (check alignment/layering first, then label/cost text).

**Verify:** the new tests pass; screenshots captured and reviewed.

### Wave V — Shared verification gate (Agent 11, after both tracks)

Run the full DoD §4 A–I. Specifically:
```powershell
python -m pytest                                   # all pass (gate A)
python tools/determinism_guard.py                  # clean (gate B)
python -m pytest tests/test_wk67_ai_boundary.py -q # digest == b73961… (gate C)
python tools/qa_smoke.py --quick                   # green (gate I)
# gate D grep (zero production hits), gates E/F/G/H from the new tests + screenshots
```
Compile a one-page verdict for PM with the digest value, test totals, the gate-D grep output, and the before/after screenshot comparison verdicts. **Nothing commits until V is green and PM signs off.**

---

## 9. Risk assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| `id()`→`entity_id` keying makes Ursina units flicker/ghost/duplicate | **Med-High** | R0 lands first (stable captures); R2 requires before/after screenshots per unit kind; check the cull/re-enable paths; verify entity_id uniqueness+stability |
| `_AI_RNG` per-build reseed changes the digest | **Med** | Tiered R0 DoD: digest is the tripwire; if reseed isn't digest-preserving, STOP → PM → defer to Round B (land Tier 1 only) |
| Deleting live tuples breaks a hidden test/tool consumer | **Med** | Gate-D grep across the whole repo (incl. tests/tools) before deletion; fix constructors in R3 |
| Button fix (H1) over-narrows the pause guard and lets world clicks through while paused | **Med** | Scope the allowance to clicks within the visible building panel only; G3 adds a "paused world-click is still blocked" assertion |
| Hire button hit-rect has the SAME coordinate bug as the Enter button (if H3) | **Med** | Fix H3 first (G1) so the shared coordinate convention is correct, THEN add the hire button on top of it |
| Two tracks collide in `engine.py` | **Low** | §6 ownership: G edits ~960-1030, R edits ~1540-1608; PM routes any cross-region need |
| Ursina capture flakiness (CAP-001: `run_ursina_capture_once` registers limited scenarios) | **Low-Med** | Use `base_overview` + the WK67-registered `ursina_melee_combat`; if a building-panel Ursina shot is needed, note pygame panels are the panel system (Ursina shares the HUD texture) |

---

## 10. Success criteria (one-liner)

WK68 is a success when: **you can click into buildings again, every guild and the temple has a working Hire-Hero button, the renderers read only DTOs (L1 dead), the determinism leaks are reset per build, and the AI-decision digest is byte-for-byte the same as WK67** — proven by a green full suite, a clean determinism guard, the gate-D grep, and before/after screenshots in both renderers.

---

## 11. Follow-up backlog (NOT this sprint — for Round B / future)

- **Round B render/HUD splits** (Move 11): split `ursina_renderer.py` (1985) and `hud.py` (2477) behind compat shims now that they consume DTOs.
- **`UiGameView`** — split the UI `get_game_state` dict + rehome HUD `engine` reads (pairs with the `hud.py` split).
- **Typed HUD-action dispatch** — replace the stringly-typed `input_handler`/`hud.handle_click` ladders with a `HudAction` enum/table (audit ui-hud + input findings); deferred per user (functional-fix-only this sprint).
- **Remove live `world` from the snapshot** (L10 remainder) — terrain/fog ownership move, with the `world.py` split.
- **`RESEARCH_UNLOCKS` → injectable per-sim object** (`research_state.py`) — the proper fix behind WK68's lighter per-build reset.
- **`_AI_RNG` production reseed** — if R0 deferred it (Tier 1 only), land it with the RNG-injection refactor.
- **Round C registries** (Move 10): `BuildingDef` single source (kills L7 + the ~17 "WK34 REMOVED" zombie keys), `visual_specs` adoption, `HERO_CLASS_COLORS`.

---

## 12. Kickoff appendix (for PM)

**Agent roster for WK68:**
- **03 TechnicalDirector** — R1 (extend DTOs), R3 (delete live tuples / kill L1).
- **04 NetworkingDeterminism** — R0 (per-build reset + digest guardrail + SIM_SEED-at-import fix).
- **06 AIBehaviorDirector** — R4 (chat-path purity).
- **08 UX/UI** — G0 (diagnose), G1 (fix buttons), G2 (Hire-Hero button).
- **09 ArtDirector** — R2 (Ursina + pygame-remainder DTO migration).
- **10 PerformanceStability** — R2 (instanced renderer migration + perf parity).
- **11 QA** — G3 (regression tests + screenshots), Wave V (shared gate).
- **05 GameplaySystems** — consult on hire economics correctness (G2) if the engine path needs a `guild=` param.

**Dispatch order:** fire **R0 (04)** + **G0 (08)** first (both are prerequisites within their tracks). When R0 is green, fire **R1 (03)** and **R4 (06)**. When G0 reports the confirmed cause, fire **G1 (08)** then **G2 (08)**, with **G3 (11)** alongside. R1→**R2 (09+10)**→**R3 (03)**. Everything converges at **Wave V (11)**.

**Universal prompt reminders for every subagent:** onboard via `.cursor/rules` for your agent #; you are agent #NN; read your PM-hub task entry; follow this plan exactly; use `claude-opus-4-8`; screenshot-verify any visual change with a written verdict (alignment/layering before styling); update your own department log when done; **DO NOT COMMIT** and do not iterate after `status=done`.
