# WK124 — Hero Kits (Wizard Spells / Cleric Heals), Ranger Idle Fix, + UI/Render Polish

**Sprint owner:** Agent 01 (ExecutiveProducer_PM)
**Created:** 2026-06-03
**Renderer in scope:** Ursina (3D) — the default `python main.py` path (plus pygame for the building-menu panels, which are shared)
**Version target:** patch (gameplay/UX features + bug fixes — no version bump unless Jaimie asks)

> **OUTCOME (2026-06-03): COMPLETE & VERIFIED, pending Jaimie playtest + commit.** All 6 tickets shipped.
> Full suite **1537 passed / 5 skipped / 0 failed**; **WK67 AI-decision digest byte-identical (no
> re-baseline)**; determinism guard + `qa_smoke --quick` PASS. PM Ursina captures confirm T1 (tax `$N` on
> top), T3 (wizard staff cast + purple magic orb), T4 (cleric → wounded-ally green heal orb), and the T5
> peasant fix is proven by clip test. Nothing committed (concurrent WK123 session shares this tree).

---

## Goal

Six Sovereign-requested items, batched into one sprint. Each has a precise root cause (PM investigation
below) so the implementing agents do minimal guessing:

1. **Tax-gold `$N` overlay must draw on top of ALL buildings** (hold-`G`). It already exists but some
   labels still hide behind taller/nearer buildings. (Continuation of WK122-BUG-A2 — the prior fix was
   self-cancelling.) — **Agent 09**
2. **Guild / Inn / Market building menus must show HP** like the guardhouse does. — **Agent 08**
3. **Wizards attack with a visible spell** (cast pose + magic projectile), reusing the existing
   projectile/VFX plumbing. — **Agent 05 (combat) + Agent 06 (kiting) + Agent 09 (VFX)**
4. **Clerics heal wounded allied heroes and move to support them**, with a visible heal effect. —
   **Agent 05 (heal system) + Agent 06 (support behavior) + Agent 09 (VFX)**
5. **Peasant "circle-with-a-P" bug when attacked** — builder-peasants fall back to the placeholder
   sprite. — **Agent 09**
6. **Rangers go idle / "seize up" after ~10 min** — they run out of nearby fog and get pinned near the
   castle. — **Agent 06**

Visual items (1, 3, 4, 5) are **screenshot-verified by the PM (Agent 01) on the GPU box** via
`tools/run_ursina_capture_once.py`; headless agents ship code behind import/seam/digest gates + verbatim
diff (per `.cursor/rules/11-fps-performance-guardrails.mdc` and the Ursina deferred-screenshot rule).

---

## ⚠️ CENTRAL CONSTRAINT — DO NOT BREAK THE WK67 AI-DECISION DIGEST

`tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable` hashes 300 ticks of a fixed
3-hero scenario: **warrior "Aldous", ranger "Brina", cleric "Cora"** near the castle, seed 3, **no
enemies** (patrol/idle/journey only, heroes stay full-HP). The expected sha256 is
`b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.

**This digest MUST stay byte-identical. Do NOT re-baseline it.** That means every behavior change in
this sprint must be **inert in that scenario**:

- **Cleric (Cora) is in the digest.** Therefore the cleric heal system and the cleric support/follow
  behavior **must only act when a friendly hero is wounded (`health_percent < threshold`) OR an ally is
  in combat (`state == FIGHTING`)**. In the digest scenario nobody is wounded and there is no combat, so
  the cleric falls through to her *existing* default behavior → digest unchanged. (Peacetime
  "always-escort-the-nearest-hero" is intentionally **deferred** because it WOULD move Cora and change
  the digest; see Out-of-scope.)
- **Ranger (Brina) is in the digest.** The new distant-frontier/re-roam behavior **must only fire when
  the LOCAL frontier scan returns empty.** In 300 ticks (≈5 sim-seconds) the local fog around Brina is
  never exhausted, so the new branch never fires → digest unchanged.
- **No wizard is in the digest**, so wizard combat/AI changes are digest-safe — BUT the wizard changes
  must be **`hero_class == "wizard"`-gated** so they never alter the ranger's (`is_ranged_attacker`) or
  any other class's behavior (e.g. do NOT change ranger `attack_range` or add a ranger `get_ranged_spec`
  that fires in combat).

**Mandatory gate for Agents 05 and 06 (and 09 if it touches sim/AI):**
```
python -m pytest tests/test_wk67_ai_boundary.py -q
```
If it FAILS, your gating is too loose — tighten it so the new behavior is inert in the digest scenario.
**Do not edit `_AI_DECISION_DIGEST`.** If you believe a digest change is unavoidable, STOP and report to
the PM; do not re-baseline.

---

## Root-cause analysis (PM investigation — for the implementing agents)

### Feature 1 — tax-gold `$N` hides behind buildings (Ursina)
- File: `game/graphics/ursina_unit_overlays.py::configure_ks_overlay` (the shared helper used by every
  world-space overlay: HP bars, name labels, hero `$N`/`Zzz`, tax-collector gold, and the building
  tax-gold `$N`).
- **Self-cancelling bug:** the helper calls `ent.set_bin("fixed", 60)` and THEN `ent.always_on_top = True`.
  Ursina's `always_on_top` setter internally runs `set_bin("fixed", 0)`, **clobbering the sort-60 bin
  back to sort 0.** Net render state ends at `fixed,0` while buildings are at `fixed,1` → with depth-test
  off, draw ORDER decides, and the label (0) draws *before* buildings (1), so buildings paint over it.
- The `ent.render_queue = 2` line is a **no-op for `Text`** (Text has no `.model`; the setter only acts on
  `self.model`). It only ever affected the HP-bar quads.

### Feature 2 — Guild/Inn/Market menus don't show HP
- **Not a data bug.** All buildings get `hp = max_hp = 200` from `game/entities/buildings/base.py:79-80`
  (guardhouse overrides to `GUARDHOUSE_MAX_HP` in `defensive.py:22-24`). Guild/Inn/Market all have valid HP.
- **The selected-building MENU renderers simply omit the HP row.** The dispatcher
  (`game/ui/building_renderers/__init__.py:111-143`) routes guardhouse → `DefensivePanelRenderer`
  (`defensive_panel.py:14-37` `_render_hp_block`, drawn unconditionally) but routes guilds →
  `GuildPanelRenderer` (`guild_panel.py`, **no HP code**) and inn/market/blacksmith/trading-post →
  `EconomicPanelRenderer` (`economic_panel.py`, **no HP code**).
- The damage-gated HP element the Sovereign noticed ("only after damage") is the *separate* world-space
  floating bar (`ursina_building_ui.py:164-181`, shown only when `hp < max_hp`). That is NOT the click menu
  and is working as intended — leave it alone.

### Feature 3 — Wizards attack as melee, no spell visual
- Wizard is `hero_class == "wizard"` on the single `Hero` class (`game/types.py`, `game/entities/hero.py`).
  Currently melee: `is_ranged_attacker` is True only for ranger (`hero.py:202`); attack_range branch only
  gives ranger range (`hero.py:131-134`).
- The wizard **already plays a staff cast-pose body animation on attack** via `Hero.on_attack_landed`
  (`hero.py:545-550` → `"attack"` clip; 12 real frames exist in `assets/sprites/heroes/wizard/attack/`).
  What's missing is a **magic projectile** flying at the target.
- Reusable plumbing (same as ranger/guardhouse arrows):
  `combat.py:182-202` emits `GameEventType.RANGED_PROJECTILE` (only when `is_ranged_attacker`, and it
  calls `hero.get_ranged_spec()` if that method exists) → `VFXSystem._spawn_projectile` builds a
  `ProjectileVFX` (`vfx.py:24-45,190-237`) → `snapshot.vfx_projectiles` → Ursina billboard in
  `ursina_misc_props_sync.py::sync_snapshot_projectiles:51-89`.
- Assets present but unused: `assets/sprites/vendor/tiny_rpg_pack_v1_03/Magic(Projectile)/Wizard-Attack01_Effect.png`
  (1000×100 = 10 frames @100×100) and `Wizard-Attack02_Effect.png` (7 frames). Optional stretch.

### Feature 4 — Clerics never heal
- Cleric is `hero_class == "cleric"`; mechanically a re-skinned warrior (no special behavior). A generic
  `Hero.heal(amount)` exists (`hero.py:343-345`) but nothing ever calls it on another hero. The temple
  (`game/content/buildings.py:120-123`) hires clerics.
- Buffs system exists for system-level passes (`game/systems/buffs.py`) and systems are registered in
  `game/sim_engine.py:131-141`. Event/VFX path: emit a new `HERO_HEAL` event → `VFXSystem._emit_event`
  (`vfx.py:93-129`, subscribed `"*"` in `engine.py:230`) → particle burst (pygame auto) + a 3D billboard.
- Heal sprite available to borrow: `.../tiny_rpg_pack_v1_03/Magic(Projectile)/Priest-Heal_Effect.png`
  (4 frames). Cleric runtime frames exist (`assets/sprites/heroes/cleric/...`) but there is no `heal/`
  action folder yet.
- AI dispatch is `ai/task_router.py::update_hero`; the move-toward pattern to copy is
  `ai/behaviors/defense.py` (`engage()` / `defend_home_building`), using `hero.set_target_position(x,y)` +
  `hero.state = HeroState.MOVING` and the `_commit_until_ms` anti-thrash window. Friendly heroes are in
  `view.heroes`.

### Feature 5 — Peasant "circle-with-a-P" when attacked
- The affected unit is the **BuilderPeasant** (`render_worker_type == "peasant_builder"`). On taking
  damage it queues a one-shot `"hurt"` clip (`peasant.py:87-94`), and death queues `"dead"`.
- **Asset gap:** `assets/sprites/workers/peasant_builder/` has only `idle/ walk/ work/` — **no `hurt/` or
  `dead/`.** So `WorkerSpriteLibrary.clips_for("peasant_builder")` builds those clips from
  `_procedural_frames` = the letter-on-circle placeholder (`worker_sprites.py:248-267` draws the "P";
  fallback at `:91-95`). Those placeholder frames get packed into the unit atlas, so when a builder is hit
  it visibly becomes the P-circle for ~0.24s (and freezes as a P-circle on death). Intermittent because
  builders are a small, transient population usually away from combat.

### Feature 6 — Rangers idle / seize up after ~10 min
- Map is 250×250 tiles (`config.py:130-131`); ranger frontier scan radius is only
  `RANGER_FRONTIER_SCAN_RADIUS_TILES = 10` (`config.py`). After ~10 min the near-castle fog "bubble" is
  fully revealed, so `_find_black_fog_frontier_tiles` (`exploration.py:40-106`) returns `[]`.
- The ranger then falls to the **wander** branch (`exploration.py:155-161`), which recenters on a **fixed
  patrol zone assigned once at 6-10 tiles from the castle** (`zones.py:23-57`, never reset). So rangers
  oscillate in a small cleared pocket near base and never travel the ~10+ tiles to reach distant fog →
  looks "seized up." Compounded: bounties are player-placed only (no auto-spawn,
  `bounty.py:214-219`), enemies are only "seen" within 5 tiles, and the no-LLM idle fallback just calls
  `explore()` again.

---

## Tickets

### WK124-T1 — Tax-gold `$N` always on top (owner: Agent 09)
- **File (edit):** `game/graphics/ursina_unit_overlays.py` (`configure_ks_overlay`).
- **Fix:** reorder so the high bin is set LAST (after `always_on_top`), and drop the dead `render_queue`
  line. Concretely the body should set, in this order: `billboard = True`; `always_on_top = True`
  (its setter resets bin→fixed,0 and disables depth — let it); then re-assert
  `set_depth_test(False)` + `set_depth_write(False)`; then **`set_bin("fixed", 110)` LAST** (110 also beats
  the instanced-unit "inside" geom at fixed,100 so `$N` wins over units too). Wrap each call in
  `try/except` exactly as today. Example shape:
  ```python
  ent.billboard = True
  try: ent.always_on_top = True        # NOTE: setter internally calls set_bin("fixed", 0)
  except Exception: pass
  try: ent.set_depth_test(False)
  except Exception: pass
  try: ent.set_depth_write(False)
  except Exception: pass
  try: ent.set_bin("fixed", 110)       # MUST be last; > buildings(1) and instanced units(100)
  except Exception: pass
  # (removed: ent.render_queue = 2  — no-op for Text, model is None)
  ```
- **Regression watch:** this helper is shared by HP bars, unit name labels, hero `$N`/`Zzz`, tax-collector
  gold. They all *should* be on top too, so this is net-positive — but verify in the PM captures that HP
  bars / name labels still look right (not doubled, not z-fighting).
- **Headless gate (add):** an assertion test that after `configure_ks_overlay(ent)` the entity's bin draw
  order is 110 (e.g. via Panda `ent.getBinDrawOrder()` or `ent.model`/node bin state). Put it in
  `tests/test_wk124_overlay_bin.py`. This catches the self-cancelling bug deterministically without a GPU.
- **Acceptance:** PM capture with overlapping/tall buildings shows **no occluded `$N`**; bin-order test green.

### WK124-T2 — Guild/Inn/Market menus show HP (owner: Agent 08)
- **Files (edit):** `game/ui/building_renderers/guild_panel.py`, `economic_panel.py`, and (preferred)
  promote a shared `render_hp_block(panel, surface, building, y) -> int` helper into
  `game/ui/building_renderers/__init__.py` (mirror the existing `render_occupants` shared helper), reusing
  the logic from `DefensivePanelRenderer._render_hp_block` (`defensive_panel.py:14-37`). Call it at the
  TOP of `GuildPanelRenderer.render` and `EconomicPanelRenderer.render` (so inn, marketplace, blacksmith,
  trading-post all get it). Show HP **unconditionally** (not damage-gated) to match the guardhouse menu.
- **Do NOT** change building stats/config or the world-space floating bar.
- **Headless gate (add):** mirror `tests/test_wk61_r5_guardhouse_hp_panel.py` with
  `test_guild_panel_shows_hp`, `test_inn_panel_shows_hp`, `test_marketplace_panel_shows_hp` (construct the
  entity, select it on a `BuildingPanel`, assert the HP text color `COLOR_WHITE` and bar color
  `COLOR_GREEN` appear in the clipped panel region). File: `tests/test_wk124_building_hp_panels.py`.
- **Acceptance:** the three new tests pass; PM capture of a guild/inn/market menu shows an HP row+bar.

### WK124-T3 — Wizard spell attack (owners: Agent 05 combat, Agent 06 kiting, Agent 09 VFX)
- **Agent 05 (`game/entities/hero.py`, `config.py`):**
  - Add `WIZARD_ATTACK_RANGE_TILES` (e.g. `4.5`) and `WIZARD_SPELL_*` color/size constants to `config.py`.
  - In `Hero.__init__`, **wizard-gate** the ranged identity: extend the attack_range branch
    (`hero.py:131-134`) with `elif self.hero_class == "wizard": self.attack_range = TILE_SIZE * WIZARD_ATTACK_RANGE_TILES`
    and set `self.is_ranged_attacker = True` for wizard at `hero.py:202` (so the existing
    `combat.py:182-202` projectile-emit branch fires). **Do NOT touch ranger's values.**
  - Add `Hero.get_ranged_spec(self)` returning, **for wizard only**, e.g.
    `{"kind": "magic", "color": (170, 90, 230), "size_px": 4}`; return `None`/omit for every other class
    (so ranger arrows are unchanged — combat only calls this when `is_ranged_attacker`, and ranger must
    keep its current arrow visuals; if returning None is awkward, return the existing arrow spec for
    ranger to preserve exact behavior). The key: **wizard gets `kind:"magic"`, nothing else changes.**
- **Agent 06 (`ai/basic_ai.py` / `ai/behaviors/`):** make wizard engage at spell range (stand off / kite)
  instead of walking into melee, mirroring the ranger's ranged engagement. **Gate on
  `hero_class == "wizard"`**; do not alter ranger/cleric/warrior pathing. (No wizard is in the digest, so
  this is digest-safe — but keep it class-gated to be certain.)
- **Agent 09 (`game/graphics/vfx.py`, `ursina_misc_props_sync.py`):** thread a `kind` field through
  `ProjectileVFX` (`vfx.py:24-45`), `_spawn_projectile` (`:190-237`), `_emit_event` (`:93-129`). In
  `sync_snapshot_projectiles` (`ursina_misc_props_sync.py:51-89`), when `kind == "magic"` render a
  **magic billboard** (MVP: a tinted/animated glowing orb via a new `get_magic_billboard_surface()` in
  `vfx.py` modeled on `get_projectile_billboard_surface():419-433`, purple/arcane palette; STRETCH: slice
  `Wizard-Attack01_Effect.png` frames). Keep the arrow path unchanged for `kind != "magic"`.
- **Acceptance:** (headless) wizard emits a `ranged_projectile` event with `kind:"magic"` that reaches the
  snapshot (unit test); `qa_smoke --quick` green; **WK67 digest green**. (visual, PM) capture shows the
  wizard's cast pose + a magic projectile traveling to the target.

### WK124-T4 — Cleric heals & supports wounded allies (owners: Agent 05 system, Agent 06 behavior, Agent 09 VFX)
- **Agent 05 (`config.py`, new `game/systems/cleric_heal.py`, `game/entities/hero.py`, `game/events.py`,
  `game/sim_engine.py`):**
  - `config.py`: `CLERIC_HEAL_RADIUS_TILES = 4`, `CLERIC_HEAL_AMOUNT = 8`, `CLERIC_HEAL_COOLDOWN_MS = 2500`,
    `CLERIC_HEAL_MIN_TARGET_PCT = 0.85` (only heal allies below 85% HP).
  - `game/events.py`: add `HERO_HEAL = "hero_heal"` to `GameEventType`.
  - `game/entities/hero.py`: init `self._heal_cooldown_until_ms = 0` in `__init__` (doesn't affect digest;
    digest hashes only x,y,state,intent,target-type,gold).
  - New `game/systems/cleric_heal.py::ClericHealSystem(GameSystem)`, modeled on `CombatSystem._run_combat`
    (`combat.py:108`). **Deterministic — no RNG, use `from game.sim.timebase import now_ms as sim_now_ms`.**
    Each tick, for each alive cleric off cooldown: find the nearest **wounded** ally
    (`health_percent < CLERIC_HEAL_MIN_TARGET_PCT`, within radius, `ally is not cleric`), stable tiebreak
    `(round(dist,3), ally.hero_id)`; if found, `best.heal(CLERIC_HEAL_AMOUNT)`, set cooldown, emit
    `HERO_HEAL` `{x,y,from_x,from_y,amount}`. **If no wounded ally → do nothing (no state change).**
  - Register + tick it in `game/sim_engine.py:131-141` following the existing `combat_system`/`buff_system`
    pattern. (Agent 03 consult — this is the one sim-core touch; keep it to the minimal 2-line register +
    tick mirroring the existing systems.)
- **Agent 06 (new `ai/behaviors/support.py`, `ai/task_router.py`, `ai/basic_ai.py`):** add
  `cleric_seek_and_support(ai, hero, view) -> bool` modeled on `defense.defend_home_building`. **Only acts
  when** there is a friendly hero within sight that is **wounded** (`health_percent < threshold`) **or in
  combat** (`state == FIGHTING`); then move toward the nearest such ally
  (`hero.set_target_position`, `state = MOVING`, `_commit_until_ms` anti-thrash). **Returns False (no
  takeover) when no ally needs support** → cleric keeps her existing default behavior. Wire as a
  **`hero_class == "cleric"`-gated** priority branch in `task_router.py` right after the warrior branch
  (`:66-68`). This is what keeps Cora inert in the digest scenario (nobody wounded / no combat there).
- **Agent 09 (`game/graphics/vfx.py` + Ursina sync; optional cleric `heal/` sprite):** add `_spawn_heal(x,y)`
  (green/gold particles, modeled on `_spawn_big:170-188`, keep the deterministic position-seeded RNG) and a
  `"hero_heal"` case in `_emit_event`. For 3D readability add a short-lived green heal-burst billboard over
  the healed target (reuse the projectile billboard surfacing path) and/or a "+N" green flash. STRETCH:
  slice `Priest-Heal_Effect.png` into `assets/sprites/heroes/cleric/heal/` and add `"heal"` to the action
  list (`hero_sprites.py:53-59`).
- **Acceptance:** (headless) unit test: a cleric heals a wounded warrior in range by `CLERIC_HEAL_AMOUNT`,
  cooldown blocks a 2nd heal, `HERO_HEAL` emitted, out-of-range/full-HP ally → no heal; follow test: cleric
  moves toward a wounded ally. `qa_smoke --quick` green; **WK67 digest green**. (visual, PM) capture shows
  the cleric beside a low-HP ally with a green heal burst and the ally's HP bar rising.

### WK124-T5 — Peasant "circle-with-a-P" fallback fix (owner: Agent 09)
- **File (edit):** `game/graphics/worker_sprites.py` (`clips_for`). When an action has no PNG frames, fall
  back to **this same unit's real `idle` clip** instead of `_procedural_frames` (the P-circle). Only keep
  the procedural fallback when the unit has NO art at all. This fixes `peasant_builder` `hurt`/`dead`
  (they'll show the green builder idle art during those one-shots instead of the placeholder). Clips are
  cached → no per-frame cost. Snippet (from the scout):
  ```python
  # after building `clips` from real frames, collect missing actions:
  if missing_actions:
      base_clip = clips.get("idle") or (next(iter(clips.values())) if clips else None)
      if base_clip is None:
          # truly no art -> keep legacy procedural P-circle for this type
          ... existing _procedural_frames path ...
      else:
          for action in missing_actions:
              meta = actions[action]
              clips[action] = AnimationClip(frames=list(base_clip.frames),
                                            frame_time_sec=meta["frame_time"], loop=meta["loop"])
  ```
- **Headless gate (add):** `tests/test_wk124_peasant_builder_clips.py` asserting
  `WorkerSpriteLibrary.clips_for("peasant_builder")["hurt"].frames == [...]["idle"].frames` (i.e. NOT the
  procedural placeholder), and that regular `"peasant"` is unaffected (still has its own hurt art).
- **Acceptance:** test green; PM capture of a builder peasant taking a hit shows the builder art, never the
  P-circle.

### WK124-T6 — Ranger late-game roam fix (owner: Agent 06)
- **Files (edit):** `ai/behaviors/exploration.py` (and read new consts from `config.py`, which **Agent 05
  adds** — Agent 06 does NOT edit `config.py`).
- **Fix:** when the **local** frontier scan returns empty (`exploration.py:155-161` wander branch), first
  try a **coarse whole-map frontier scan** (`_find_distant_frontier_tile`, stride ~8 tiles) and send the
  ranger toward the nearest distant UNSEEN-adjacent-to-SEEN tile with a longer commit
  (`RANGER_REROAM_COMMIT_MS`). If the whole reachable map is revealed, give a productive roam
  (re-scout / move toward known lairs) rather than near-castle wander. **Deterministic:** use `ai._ai_rng`
  and `sim_now_ms()` only — no `random.random()`/`time.time()`. Clear `_frontier_commit_until_ms` if
  stuck-recovery drops the target so re-decision keeps firing.
- **Config constants (added by Agent 05, read by Agent 06):** `RANGER_GLOBAL_FRONTIER_STRIDE_TILES = 8`,
  `RANGER_REROAM_COMMIT_MS = 8000`.
- **DIGEST SAFETY:** the new branch must fire **only when the local scan is empty**, which never happens in
  the 300-tick digest window → digest stays byte-identical. Verify with the digest gate.
- **Headless gate (add, owner Agent 11):** `tests/test_wk124_ranger_idle_soak.py` — headless engine,
  ~6 rangers, run ~18000 ticks (≈10 sim-min), assert over the last 3 sim-min: ranger "idle-ish" fraction
  `< 0.4` and mean max distance-from-castle `> 15` tiles (proves they leave the bubble). Set
  `DETERMINISTIC_SIM=1`, dummy SDL drivers. Should FAIL pre-fix, PASS post-fix.
- **Acceptance:** soak test green; WK67 digest green; `qa_smoke --quick` green.

---

## File ownership / lanes (each file has exactly ONE owning agent this sprint)

| Ticket | Agent | Files MAY edit | MUST NOT edit |
|---|---|---|---|
| T2 | 08 UX/UI | `game/ui/building_renderers/{guild_panel,economic_panel,__init__}.py`, `tests/test_wk124_building_hp_panels.py` | graphics, sim, ai, config, entities |
| T1, T5 | 09 Art (wave 1) | `game/graphics/ursina_unit_overlays.py`, `game/graphics/worker_sprites.py`, `tests/test_wk124_overlay_bin.py`, `tests/test_wk124_peasant_builder_clips.py` | ui, sim, ai, config, vfx.py (wave 2) |
| T3a, T4a, config | 05 Gameplay | `config.py` (ALL new consts incl. ranger), `game/entities/hero.py`, `game/events.py`, `game/systems/cleric_heal.py` (new), `game/sim_engine.py` (register only), `tests/test_wk124_cleric_heal.py` | graphics, ai, ui |
| T3b, T4b, T6 | 06 AI | `ai/behaviors/exploration.py`, `ai/behaviors/support.py` (new), `ai/task_router.py`, `ai/basic_ai.py` | config.py (READ only), graphics, ui, entities, sim_engine |
| T3c, T4c | 09 Art (wave 2) | `game/graphics/vfx.py`, `game/graphics/ursina_misc_props_sync.py`, `assets/sprites/heroes/cleric/heal/*` (optional), `tools/assets_manifest.json` (only if assets added) | ui, sim, ai, config |
| T6-soak, sweep | 11 QA | `tests/test_wk124_ranger_idle_soak.py` (new), runs all gates | production code |

**No two agents in the same wave touch the same file.** `config.py` is owned solely by Agent 05 this
sprint; Agent 06 reads the constants 05 adds (hence 05 before 06).

## Integration / wave order

- **Wave 1 (parallel — disjoint files):** Agent 08 (T2), Agent 09 (T1+T5), Agent 05 (T3a+T4a + all config
  consts + cleric system + events + hero fields). 05 defines the contracts (`kind:"magic"`, `HERO_HEAL`,
  config consts) that Wave 2 consumes.
- **Wave 2 (parallel — disjoint files, after Wave 1):** Agent 06 (T6 + T3b + T4b), Agent 09 wave-2
  (T3c + T4c VFX). Both depend on Wave-1 contracts.
- **Wave 3 (verification):** Agent 11 soak test + full regression sweep; PM (Agent 01) runs the Ursina
  captures for T1/T3/T4/T5 and iterates with the owning agent until visuals pass.

## Gates (every implementing agent, headless — copy/paste from repo root)
```
python tools/qa_smoke.py --quick
python -m pytest tests/test_wk67_ai_boundary.py -q        # Agents 05, 06 (digest MUST stay green)
python -m pytest tests/test_wk124_overlay_bin.py -q       # T1
python -m pytest tests/test_wk124_building_hp_panels.py -q # T2
python -m pytest tests/test_wk124_cleric_heal.py -q       # T4
python -m pytest tests/test_wk124_peasant_builder_clips.py -q # T5
python -m pytest tests/test_wk124_ranger_idle_soak.py -q  # T6 (Agent 11)
python tools/validate_assets.py --report                  # only if assets/ changed (Agent 09 stretch)
python -c "import game.graphics.vfx, game.graphics.ursina_misc_props_sync, game.graphics.ursina_unit_overlays"  # import smoke
```

## PM live verification (Agent 01, on GPU box)
```
python tools/run_ursina_capture_once.py --scenario wk61_hold_g_tax_overlay --ticks 720 --out docs/screenshots/wk124_tax_after   # T1
python tools/run_ursina_capture_once.py --scenario ursina_melee_combat --out docs/screenshots/wk124_combat                       # T3/T5 baseline
```
(Plus bespoke captures for wizard-cast, cleric-heal, and builder-hit — the PM will add small capture
patches or extend `ursina_melee_combat` as needed.) Inspect PNGs; iterate fix→recapture until: tax `$N`
never occluded; wizard shows a magic projectile + cast pose; cleric shows a green heal burst + ally HP
rising; builder peasant never shows the P-circle when hit.

## Send list (intelligence)
- Agent 05 — GameplaySystems (**high** — new deterministic heal system + wizard ranged identity + sim
  registration; digest-safety reasoning)
- Agent 06 — AIBehaviorDirector (**high** — ranger late-game roam, cleric support behavior, wizard kiting;
  digest-safety reasoning)
- Agent 09 — ArtDirector (**medium** — overlay bin reorder, worker-sprite fallback, magic/heal billboards
  following known VFX plumbing)
- Agent 08 — UX/UI (**medium** — add the HP block to two panel renderers following the defensive renderer)
- Agent 11 — QA (**medium** — ranger soak test author + full regression sweep)
- Agent 03 — TechnicalDirector (**low** — consult only: review the `sim_engine.py` cleric-system register)
- Do NOT send: 02, 04, 07, 10, 12 (no asset pipeline change in MVP), 13, 14, 15
- **DO NOT COMMIT. DO NOT run git. Stay in your lane. Update your own agent log only.**

## Out-of-scope (explicit — guard against creep)
- Peacetime "cleric always escorts the nearest hero" (would move Cora and change the WK67 digest →
  deferred; offer to Jaimie as a follow-up that re-baselines the digest with his sign-off).
- Full Tiny-RPG spell/heal **sprite-sheet export pipeline** (Agent 12 + manifest). MVP uses
  procedural/tinted billboards; real sprite sheets are a STRETCH only if cheaply sliceable at load.
- Wizard/cleric balance retuning, new buildings, new enemy types, anything not in the six tickets.

## Definition of Done
- All headless gates green, including **WK67 digest byte-identical (no re-baseline)** and the five new
  WK124 tests.
- PM Ursina captures confirm: (1) tax `$N` on top of all buildings; (3) wizard magic projectile + cast
  pose; (4) cleric green heal burst + ally HP rising; (5) builder peasant never reverts to the P-circle.
- Building menu HP visible on guild/inn/market (test + capture).
- Ranger idle-soak test passes (rangers leave the near-castle bubble late-game).
- PM hub + this plan updated; Jaimie shown before/after screenshots and the deferred-scope note.
