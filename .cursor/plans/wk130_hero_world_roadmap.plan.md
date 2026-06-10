# WK130–WK134 Roadmap — "Hero World": Sidebar UX, Items, POIs, Quests, LLM

**Roadmap owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-09 (immediately after the v1.6.0 release, main @ 4922557)
**Sovereign directive (Jaimie, verbatim intent):** complete a roadmap built from
`.cursor/plans/future_hero_development_ideas.md` items 1 (POIs additions, per
`.cursor/plans/pois_proposal.md`), 2 (Items & Inventory — "basically nothing yet, its time has
come"), and the *beginning* of 3 (basic quests, kept simple, with a player-placed quest-giving
building/NPC). When those land, take a pass at the LLM↔AI connection to confirm heroes follow
commands. Also: make the left side menu work better — entire left menu ~10% wider, the chat window
is too small, and the resize/minimize/maximize behaviors are buggy and need standardizing.
Execute autonomously, sprint by sprint, commit+push per sprint; Jaimie tests at the end.

---

## Mission & vision (read this if you have no other context)

Kingdom is a Majesty-like indirect-control RTS prototype (Python, pygame HUD composited onto an
Ursina/Panda3D 3D renderer, deterministic fixed-dt sim). Heroes are autonomous agents driven by a
heuristic AI with optional LLM consults (OpenAI by default) for flavor decisions and a
player↔hero chat. This roadmap turns the world from "buildings, lairs and empty space" into a
place heroes have *reasons* to journey through: discoverable POIs that drop **items**, heroes that
carry and reason about **inventory**, a player-placed **Herald's Post** that hands out **quests**
heroes accept or decline via the LLM, and a **left sidebar/chat** good enough to actually talk to
heroes. Each sprint stands alone, lands green, and is committed+pushed as a save-state.

## Hard rails (every sprint inherits these)

1. **WK67 digest stays byte-identical** — `tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable`,
   sha `b73961…`. The digest scenario (3 heroes, no enemies/POIs/quests/items beyond defaults) must
   be structurally unreachable by new code: early-return before ANY `ai._ai_rng` draw or state
   mutation when the new feature's data is empty/default. Never re-baseline.
2. **Gates:** `python tools/qa_smoke.py --quick` must PASS before any commit. New features ship
   with their own `tests/test_wk1NN_*.py` headless tests.
3. **Determinism:** sim time only via `game.sim.timebase.now_ms()`; RNG only via
   `game.sim.determinism.get_rng(name)`. No wall clock, no bare `random`.
4. **FPS guardrails:** `.cursor/rules/11-fps-performance-guardrails.mdc` (incl. Mythos addendum).
   No per-frame re-raster — dirty-gate every new overlay/panel. Never cut tree/grass density.
   New unit-like entities (Quest-Giver NPC) must work with the instanced renderer
   (`game/graphics/instanced_unit_renderer.py`) or use the classic overlay path deliberately.
5. **Subagents do NOT commit/push** — the PM (Agent 01 session) commits, staging **by path**
   (concurrent sessions can share the tree; never `git add -A`).
6. **Visual work is screenshot-verified** before a sprint closes: headless pygame via
   `python tools/capture_screenshots.py --scenario <s> --out docs/screenshots/<dir> --seed 3`
   and live Ursina via `python tools/run_ursina_capture_once.py --scenario <s> --ticks N --out <dir>`
   (PM runs the Ursina ones on the GPU box).

## Sprint sequence

| Sprint | Theme | Why this order |
|---|---|---|
| **WK130** | Left sidebar + chat UX overhaul | Self-contained UI work; ships first so later sprints' chat/LLM testing happens in the fixed UI. |
| **WK131** | Items & Inventory core | Foundation for POI loot and quest rewards; biggest "nothing exists yet" gap. |
| **WK132** | POIs round-out | Completes the pois_proposal leftovers and wires POIs into items (loot) and the LLM context. |
| **WK133** | Quests vertical slice | Executes the already-written `.cursor/plans/wk126_quest_giving_npcs.plan.md` (Herald's Post + NPC + LLM accept/decline + "!"). |
| **WK134** | LLM connection verification | End-to-end audit that heroes follow chat commands and the new context (items/POIs/quests) reaches prompts. |

---

## WK130 — Left Sidebar & Chat UX Overhaul

**Goal:** the left column is ~10% wider, the chat window is comfortably usable, and
resize/minimize/maximize behaviors are standardized and predictable.

Current state (scouted 2026-06-09):
- Width is a single authoritative constant `LEFT_COL_W = 224` in `game/ui/hud_layout.py:19`
  (minimap `RADAR_MINIMAP_W` aliases it). Chat rects inset to `width - 8`.
- Chat surfaces: `game/ui/chat_panel.py` (`ChatPanel`) renders (1) the in-column hero-menu chat
  popup (`hud.py:1002`, rect from `hud_left_layout.py::hero_menu_chat_split_rects:429-449`,
  min/preferred heights `HERO_MENU_CHAT_MIN_H=152` / `_PREFERRED_H=220`, capped at 38% of column)
  and (2) the pinned watch-card band `WATCH_CARD_CHAT_H=150` (`hud_watch_card.py:36-46`).
- Resize machinery: `game/ui/hud_left_layout.py` — `layout_left_column_segments` (L65-168),
  drag handlers `handle_sidebar_split_pointer_*` (L189-244), fractions in `hud._left_split_fracs`.
- Known defects found in code review: pointer-down hit-tests the 4px visual bar instead of the 8px
  `LEFT_SPLIT_HANDLE_HIT_H`; `virtual_pointer_in_hud_chrome` (L325-400) duplicates layout geometry
  separately from the render path (drift); first-frame fallback sizing pop (L103-105);
  WK121 shrink-priority cascade is hand-tuned with three clamps (L87-120).

**Scope:**
1. `LEFT_COL_W` 224 → **246** (+10%; minimap follows automatically). Audit every consumer of
   `LEFT_COL_W`/`RADAR_MINIMAP_W` and right-edge math for hardcoded 224 assumptions.
2. Chat window bigger: raise `HERO_MENU_CHAT_MIN_H` → 190, `HERO_MENU_CHAT_PREFERRED_H` → 280,
   height cap 38% → 45%; `WATCH_CARD_CHAT_H` 150 → 190. Input row tall enough for comfortable
   typing; verify wrap width uses the new column width.
3. Standardize adjust/min/max:
   - drag hit-testing uses `LEFT_SPLIT_HANDLE_HIT_H` (8px) everywhere;
   - single source of geometry: `virtual_pointer_in_hud_chrome` must call the same layout
     functions the render path uses (no independently rebuilt rects);
   - clamp invariants under drag: main panel ≥ `HERO_MENU_HERO_MIN_H`, watch card never evicts
     the main menu (keep WK121 contract + its test green), no overlapping rects at any drag
     position (property-style test sweeping drag positions);
   - minimize/maximize (watch-card chevron, close buttons, hero-card collapse) leave the layout
     in a consistent state — re-expand restores sane fractions, no floating handles.
4. Update layout tests pinned to 224/old heights (`test_wk115_left_menu_polish.py`,
   `test_wk61_r9/r10/r11*`, `test_wk99/100/101/103*`, `test_wk121_watch_card_no_evict.py`,
   `test_wk96/97/98*`) — preserve each test's *contract*, re-derive constants from `hud_layout.py`
   instead of literals where possible.
5. Screenshot verification across EVERY visual path: default HUD, hero selected (menu+chat
   popup), pinned watch card expanded/collapsed, watch-card chat open, building selected, drag
   mid-resize, 1920x1080 and a smaller window. Alignment/layering first: left edges flush, no
   panel overlap.

**Definition of Done:** qa_smoke green; all layout tests green (updated, contracts preserved);
new `tests/test_wk130_sidebar_overhaul.py` covering width propagation, chat heights, 8px hit
band, geometry-unification, drag-sweep no-overlap; screenshots captured and PM-reviewed for the
full matrix above; WK67 digest untouched (UI-only sprint — no sim/ai edits at all).

---

## WK131 — Items & Inventory Core

**Goal:** heroes find, buy, auto-equip, carry, and use items; loot drops exist; the LLM can see
inventory. Minimal but real — per `future_hero_development_ideas.md` §2.

Current state (scouted): `hero.weapon`/`hero.armor` are single dicts (`game/entities/hero.py:110-113`),
potions are a counter; shops have hardcoded item lists (`game/entities/buildings/economic.py:38-57`);
purchases flow `ai/behaviors/shopping.py` → `HeroPurchaseCommand` (`game/sim/hero_commands.py:39`) →
`hero_economy.buy_item` (`game/entities/hero_economy.py:108-145`); LLM sees
`HeroInventorySnapshot` (`game/sim/hero_profile.py:189-198`). No item registry, no loot, no
accessory slot, no inventory UI beyond stat lines.

**Scope:**
1. **Item registry** `game/content/items.py` (new): `ItemDef` dataclass — id, name, slot
   (`weapon|armor|accessory|consumable`), stat mods (attack/defense/speed/max_hp), rarity
   (`common|uncommon|rare|legendary`), buy/sell price, flavor text. Author ~20-25 items
   (tiered weapons/armor that subsume today's hardcoded shop dicts, 3-5 accessories,
   consumables: healing potion + 1-2 new). Keep today's dict shape available via an adapter so
   `hero.weapon["attack"]` call sites keep working OR migrate those call sites — owner's choice,
   tests prove combat math unchanged for the same stats.
2. **Hero inventory:** equip slots weapon/armor/**accessory** (new) + consumable bag (potions
   counter stays, generalized). `hero.equip(item)` with auto-equip-if-better default;
   `hero.sell_value()` etc. Backpack cap small (4-6).
3. **Loot drops:** seeded loot tables (`game/systems/loot.py`, new) — POI loot caches roll an
   item chance in `poi_interaction.py` loot handler (in addition to gold); bosses
   (BanditLord/DemonOverlord) drop rare+; regular enemies small chance of common drops.
   Determinism: `get_rng("loot")`. **Digest guard:** the digest scenario has no enemies/POIs, so
   loot code must be unreachable there; no RNG draws outside kill/interaction events.
4. **Shops:** Marketplace/Blacksmith `get_available_items()` source from the registry (same
   visible stock as today at minimum); heroes sell loot they can't use when shopping
   (`do_shopping` extension); sell pays `add_gold` (25% tax applies naturally).
5. **UI:** hero panel (`game/ui/hero_panel.py`) shows equipped items (3 slots + bag) as compact
   rows/icons under stats; watch card stats band shows weapon/armor names. Dirty-gated like
   existing panel content.
6. **LLM context:** extend `HeroInventorySnapshot` (+ accessory, + bag list) and ensure it
   survives `_compact_profile_dict` into prompts; shopping context includes affordable upgrade
   candidates from the registry.

**Definition of Done:** qa_smoke green; WK67 digest byte-identical; new
`tests/test_wk131_items.py` (registry validation, equip/auto-equip, loot determinism — same seed
same drops, shop buy/sell round-trip incl. tax, snapshot carries items); existing combat/shopping
tests green; screenshots of hero panel + watch card showing items; a 10-sim-min headless soak
where heroes demonstrably loot, equip, and sell at least once (seeded, with enemies + a loot POI).

---

## WK132 — POIs Round-Out

**Goal:** finish the high-value remainder of `.cursor/plans/pois_proposal.md` now that items exist.

Current state (scouted 2026-06-09): 12/17 POI types live with real handlers
(`game/entities/poi.py::POI_DEFINITIONS`, `game/systems/poi_interaction.py`); 4 zones with terrain
bias consumed for trees+elevation; minimap dots + gray "?"; underground descent works.
NOT done: 5 POI types (Mysterious Well, Ruined Outpost, Windmill Ruin, Ancient Ruins, Dragon
Cave), `nearby_pois` computed (`ai/context_builder.py:170-172`) but dropped before prompt
serialization (`ai/profile_context_adapter.py:100-115`, `ai/prompt_packs.py:79-87`), no item loot
from POIs (WK131 adds the system; this sprint tunes per-POI tables), `rock_density` zone bias has
no consumer, no per-zone fog/ground tint, NPC handler is flavor-text-only.

**Scope:**
1. **5 new POI types** with definitions, handlers, prefab JSONs (Model Assembler kitbash per
   pois_proposal §4 model lists), zone-palette + rarity wiring:
   - *Mysterious Well* (1×1, random outcome: gold/item/monster/reveal — seeded),
   - *Ruined Outpost* (3×3, combat + permanent vision radius once cleared),
   - *Windmill Ruin* (2×2, knowledge/flavor MVP — repair-quest hook deferred),
   - *Ancient Ruins* (5×5, knowledge + loot + cascade reveal),
   - *Dragon Cave* (3×3, boss arena — reuse boss-spawn pipeline with a new high-tier boss or a
     buffed DemonOverlord variant; legendary loot).
2. **LLM sees POIs:** serialize a compact `nearby_pois` block (≤4 entries: name, type, distance,
   tier, discovered?) into BOTH the autonomous decision context (`_compact_situation`) and the
   chat prompt blob — token-budgeted, only when non-empty (digest scenario has no POIs → inert).
3. **POI loot tables:** per-type item tables on top of WK131 (`loot.py`) — caches/wells common,
   ruins uncommon+, bosses rare/legendary.
4. **Zone polish:** consume `rock_density` in worldgen scatter; optional cheap per-zone fog color
   lerp by camera position (`pois_proposal` §2.4 item 4) behind `KINGDOM_ZONE_FOG_TINT` default ON
   only if screenshots look good.
5. **Rendering check:** large POIs (Ancient Ruins) render acceptably; if a 5×5 prefab hurts FPS,
   reduce piece count rather than building the compound-prefab system (explicitly out of scope).

**Definition of Done:** qa_smoke + `validate_assets.py --report` green; WK67 digest
byte-identical; `tests/test_wk132_pois.py` (new types place/interact/deplete, well outcome
determinism, outpost vision unlock, prompt serialization includes/excludes nearby_pois correctly);
Ursina captures of each new POI prefab + a fog-tint A/B; loot tables proven by seeded soak.

---

## WK133 — Quests Vertical Slice (executes the WK126 plan)

**The full spec already exists: `.cursor/plans/wk126_quest_giving_npcs.plan.md`. Read it
end-to-end before working.** That plan is authoritative for this sprint — data model, digest
guards (RNG-ordering rules!), file ownership lanes, tickets T1-T10, config constants, gates.

Sprint-level decisions taken by the PM (2026-06-09, per the Sovereign's "keep this simple" +
standing autonomy):
- Ship **all four quest types** (raid_lair, slay_enemy_type, find_poi, explore_far) in one sprint —
  the completion detectors are additive and the plan's Phase 1/Phase 2 split was a de-risking
  option, not a requirement. If the sprint runs hot, cut to raid_lair only (Phase 1) and note it.
- **Quest rewards are gold-only this roadmap** (item rewards deferred; the WK126 plan already
  defers them). WK131's items exist, but keep the quest MVP simple per the directive.
- Failure/refund choice (plan T7 open question): **escrow consumed on failure** (MVP), giver
  re-armable. Documented here as the decision of record.
- The Quest-Giver NPC renders via the classic (non-instanced) unit path with the "!" overlay per
  plan T8; confirm no FPS regression with the dirty-gate pattern.

**Definition of Done:** exactly the WK126 plan's DoD (all gates incl. the RNG-position
digest-safety test, 15-sim-min decline cooldown proven, four quest types complete+pay, "!"
marker on top of buildings and off after accept, create dialog escrow + affordability), plus
Ursina captures reviewed by the PM.

---

## WK134 — LLM Connection Verification Pass

**Goal:** confirm the whole LLM↔AI stack works as intended and that heroes can be expected to
follow Sovereign commands; fix what's broken; close known dead ends.

Current state (scouted): pipeline is `ai/llm_brain.py` (daemon worker) → providers
(`ai/providers/`: openai default via `LLM_PROVIDER`, claude pinned to `claude-3-haiku-20240307`
with no env override, gemini, grok, mock fallback) → 5 decision moments (all wired) →
`apply_llm_decision` (`ai/behaviors/llm_bridge.py:92-234`): 7 actions wired, **`accept_bounty` is
a dead no-op (L180-181)**. Chat path: `game/ui/chat_panel.py` → `engine.py:739` →
`request_conversation` → `direct_prompt_validator` → `direct_prompt_exec` → same
`apply_llm_decision`.

**Scope:**
1. **Wire `accept_bounty`** for real (route to `bounty_pursuit` commit, mirroring the heuristic
   path) — it's offered in IDLE_SEEKING_ACTIVITY and currently lies to the LLM.
2. **Add `accept_quest`/`decline_quest` and POI awareness** end-to-end checks: after WK132/133,
   verify nearby_pois + quest-offer context actually appear in real serialized prompts (add a
   prompt-snapshot test that renders a full prompt for a rich scenario and asserts the blocks).
3. **Provider audit:** Claude model gets `ANTHROPIC_MODEL` env override (default a current model);
   provider failures fall back to mock loudly (one-line HUD/system message, not silent); confirm
   `LLM_TIMEOUT` behavior doesn't stall heroes (pending-decision flag always cleared).
4. **Command-following E2E:** headless tests with seeded `MockProvider` driving every
   direct-prompt `tool_action` (move_to each named place, explore each compass, fight, retreat,
   buy_item, use_potion, leave_building, accept_bounty, accept_quest) asserting the hero's
   state/target actually changes, plus the obey/defy path. Then a live-ish soak with the real
   provider OFF (`--no-llm` parity: heroes never stall when llm_brain=None).
5. **Docs:** a short `docs/llm_connection.md` — how to configure providers, what heroes will and
   won't obey, known limits — so Jaimie can test with real API keys.

**Definition of Done:** qa_smoke + digest green; `tests/test_wk134_llm_e2e.py` covering every
tool_action round-trip + prompt-snapshot assertions; accept_bounty no longer a no-op (both-ways
test); provider fallback visible; doc written; PM does one live chat session on the GPU box with
a real provider configured (if a key is present in `.env`) and records the transcript in the PM hub.

---

## Process per sprint (the loop this roadmap runs on)

1. PM updates the PM hub (`.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`) with the
   sprint round: `pm_status_summary`, `pm_next_actions_by_agent`, `pm_agent_prompts` (self-contained,
   with verification commands), `pm_send_list_minimal`.
2. PM dispatches subagents (claude-fable-5, medium effort). Each prompt: "Onboard as Agent NN via
   `.cursor/rules/agent-NN-*-onboarding.mdc` + `01-studio-onboarding.mdc`, then execute your
   assignment in the PM hub at sprints[<sprint>].rounds[<round>]." Agents update their own logs,
   run their gates, **DO NOT COMMIT**, and report back with evidence (test output, screenshot paths).
3. PM reviews (screenshots for anything visual — broad coverage, alignment/layering first),
   loops fixes with the owning agent until DoD holds.
4. PM runs full qa_smoke, stages **by path**, commits `wk1NN: <summary>`, pushes to main.
5. Next sprint.
