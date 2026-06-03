# WK114 Round B — purge the 8 WK34 "zombie" building types

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk114_round_b_zombie_building_purge`
**Version target:** minor (removes 8 dead/unfinished building types — Sovereign-authorized 2026-05-31: "you can delete those old buildings")
**Verification class:** HEADLESS. **WK67-digest-SAFE** (see §1) — none of the 8 spawn at default startup / spawner / worldgen, none are placeable, so a fresh headless engine never creates one → the AI-decision digest must stay byte-identical. No screenshots needed (deletion of never-rendered types; the kept types are untouched).
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR

Delete the 8 building types flagged `purge_candidate=True` in `game/content/buildings.py`:
`gnome_hovel`, `elven_bungalow`, `dwarven_settlement`, `ballista_tower`,
`wizard_tower`, `fairgrounds`, `library`, `royal_gardens`. They are WK34 stubs —
defined + partially wired but **never spawned, never placeable**. The Sovereign
ruled keep-vs-purge = PURGE.

This is a **cross-cutting deletion across ~22 code files + 4 test files**, done
**atomically by ONE agent** (Agent 05) so no intermediate state leaves a dangling
import. Agent 11 then updates the 4 hard-pinned test files, writes the purge seam
test, and runs the full DoD.

**DO NOT touch `poi_wizard_tower`** — it is a separate POI (`is_poi=True`), KEPT.
For every SHARED list/branch/renderer, remove ONLY the zombie members; KEEP the
co-resident kept types (`guardhouse`, `palace`, the guilds, temples, etc.).

**DO NOT COMMIT. DO NOT `git add`/`commit`/`push`.** PM (Agent 01) owns the commit.

---

## 1. Why this is digest-safe (verified by the grounding sweep)

- `STARTING_BUILDINGS` (config.py L16–22) = `warrior_guild, ranger_guild, marketplace,
  food_stand, guardhouse` — NONE of the 8. The startup placement loop
  (`sim_engine.py` ~L329–337) iterates exactly that list.
- `game/systems/spawner.py` and `game/worldgen.py`: ZERO references to any of the 8.
- None of the 8 have `placeable=True`, so neither the player build-menu nor the AI
  build path can create them.
- ⇒ A fresh `GameEngine(headless=True)` never instantiates one. The WK67 digest
  (`b73961340c…d148ded`, headless engine + 3 seeded heroes, 300 ticks) must stay
  **byte-identical**. It is a HARD gate this sprint — if it shifts, STOP and report
  (it would mean something unexpected iterated `BUILDING_DEFS` for ordering).

---

## 2. Wave 1 — Agent 05 (Gameplay): the atomic code purge

Do ALL of the following in one pass. After each group, keep the tree import-clean.
**Legend:** ❌ = remove · ✅KEEP = must remain.

### A. Registry, enum, entity classes (the core — atomic)

**`game/content/buildings.py`**
- ❌ The 8 `BUILDING_DEFS` entries (L135–137 dwellings; L143–144 ballista/wizard;
  L146–148 fairgrounds/library/royal_gardens). Also remove the now-orphaned
  `# Phase 3 … zombies` / `# Phase 5 … zombies` comment lines if they leave a bare comment.
- ❌ The 8 entries in `_CLASS_NAMES` (L201–209): `GnomeHovel, ElvenBungalow,
  DwarvenSettlement, BallistaTower, WizardTower, Fairgrounds, Library, RoyalGardens`.
- ✅KEEP `assert_building_type_coverage()` — it now passes (enum + defs both drop the 8).
- ✅KEEP `poi_wizard_tower` (L170) and ALL other entries.

**`game/entities/buildings/types.py`** (the `BuildingType` enum)
- ❌ Members `GNOME_HOVEL, ELVEN_BUNGALOW, DWARVEN_SETTLEMENT` (L26–28) and
  `BALLISTA_TOWER, WIZARD_TOWER, FAIRGROUNDS, LIBRARY, ROYAL_GARDENS` (L30–34).
- ✅KEEP `poi_wizard_tower`'s enum member if present (POI). Edit types.py + buildings.py together (coverage assert couples them).

**`game/entities/buildings/dwellings.py`**
- ❌ Classes `GnomeHovel`, `ElvenBungalow`, `DwarvenSettlement` (L10–31).
- If, after removal, the file has NO remaining class/function defs (only a docstring/imports),
  DELETE the file AND remove its import line in `__init__.py` (next item). If it still
  holds shared content, keep the file (just the 3 classes gone).

**`game/entities/buildings/defensive.py`**
- ❌ `BallistaTower` (L104–183), `WizardTower` (L186–225).
- ✅KEEP `Guardhouse` (L17–101) and the FILE.

**`game/entities/buildings/special.py`**
- ❌ `Fairgrounds` (L12–39), `Library` (L42–141), `RoyalGardens` (L144–163).
- ✅KEEP `Palace` (L166–216) and the FILE.

**`game/entities/buildings/__init__.py`**
- ❌ From L9 imports: `BallistaTower, WizardTower`; L10: `DwarvenSettlement,
  ElvenBungalow, GnomeHovel` (remove whole line if dwellings.py was deleted); L14:
  `Fairgrounds, Library, RoyalGardens`. ❌ The 8 names from `__all__` (L52–60).
- ✅KEEP `Guardhouse`, `Palace`, and all other imports/exports.

**`game/entities/__init__.py`**
- ❌ The 8 from the L10–12 re-exports (and any `__all__`). ✅KEEP the rest.

### B. Dispatch & systems

**`game/sim_engine.py`**
- ❌ The 3 standalone `elif` branches in `_update_buildings` (≈L896–901):
  `ballista_tower → update(dt, self.enemies)`, `wizard_tower → update(dt, self.enemies)`,
  `fairgrounds → update(dt, self.economy, self.heroes)`.
- ✅KEEP the SHARED research-advance loop (≈L885–888, used by Blacksmith/Marketplace)
  and the SHARED `_last_ranged_event` collection loop (≈L918–923, used by Guardhouse).
  Those key off attributes/`advance_research`, not the zombie type names.

**`game/systems/buffs.py`**
- ❌ The `royal_gardens` aura block in `BuffSystem.update` (≈L46–67): the
  `if building_type != "royal_gardens": continue` guard through the
  `apply_or_refresh_buff(name="royal_gardens_aura", …)` loop. It is the SOLE aura
  producer → fully dead once royal_gardens is gone.
- ✅KEEP the generic buff infrastructure (`Buff`, `apply_or_refresh_buff`,
  `remove_expired_buffs`) and the rest of `BuffSystem`.

**`game/entities/peasant.py`** (≈L171–175)
- ❌ The `gnome_bonus = any(… building_type == "gnome_hovel" …)` detection; make the
  movement speed unconditional: replace the `speed_mult = 1.5 if gnome_bonus else 1.0`
  with `speed_mult = 1.0` (and delete the now-unused `gnome_bonus` line). Preserve the
  surrounding movement logic exactly otherwise.

### C. Config (`config.py`) — edit MEMBERS of shared collections only

- ❌ `BUILDING_CONSTRAINTS` (L193–195): the 3 dwelling entries — the dict becomes empty
  → leave it as `BUILDING_CONSTRAINTS = {}` (keep the name + type).
- ❌ `BUILDING_PREREQUISITES` (L200): the `"ballista_tower": ["dwarven_settlement"]` entry.
- ❌ `TAX_STASH_BUILDING_TYPES` (L344–346): the 3 dwellings — ✅KEEP all other members.
- ❌ `NON_TAX_STASH_BUILDING_TYPES` (L358–362): `ballista_tower, wizard_tower, fairgrounds,
  library, royal_gardens` — ✅KEEP all other members.
- ✅KEEP `STARTING_BUILDINGS` (none of the 8 are in it).

### D. AI / read-model

**`ai/decision_moments.py`** (≈L113, `_inside_recovery_building`)
- ❌ `elven_bungalow, dwarven_settlement, gnome_hovel` from the recovery-building set.
- ✅KEEP `castle, inn, house, farm`, and all other members.

**`game/sim/hero_profile.py`** (`PROFILE_DISCOVERY_BUILDING_TYPES`, ≈L96–117)
- ❌ `wizard_tower, ballista_tower, fairgrounds, royal_gardens, gnome_hovel,
  elven_bungalow, dwarven_settlement, library`.
- ✅KEEP `poi_wizard_tower` (≈L61, POI), guilds, economic types, palace, all others.

### E. UI panels

**`game/ui/building_renderers/__init__.py`** — edit the SHARED routing sets:
- ❌ `_GUILD_TYPES` (≈L111–119): the 3 dwellings — ✅KEEP the 4 guilds.
- ❌ `_DEFENSIVE_TYPES` (≈L130): `ballista_tower, wizard_tower` — ✅KEEP `guardhouse`.
- ❌ `_SPECIAL_TYPES` (≈L131): `fairgrounds, library, royal_gardens` — ✅KEEP `palace`.
- Verify `PANEL_RENDERERS` (≈L133–140) has no explicit per-zombie entry left.

**`game/ui/building_renderers/special_panel.py`**
- ❌ `_render_fairgrounds` (≈L14), `_render_royal_gardens` (≈L101), `_render_library`
  (≈L231), and their dispatch lines (≈L229–234 for fairgrounds/library/royal_gardens).
- ✅KEEP `_render_palace` (≈L235) and the renderer CLASS.

**`game/ui/building_renderers/defensive_panel.py`**
- ❌ `_render_ballista_tower` (≈L56), `_render_wizard_tower` (≈L77), and their dispatch
  (≈L118–121). ✅KEEP `guardhouse` rendering and the CLASS.

**`game/ui/building_panel.py`**
- ❌ The `library` research click handling (`library_research_rects`, ≈L221–227) and the
  `library` panel branch (≈L271). Self-contained library UI.

**`game/ui/hud.py`** (≈L656–658)
- ❌ The stale controls-overlay text fragments for the 8 (Gnome/Elf/Dwarf/Ballista/
  Wizard Tower/Fairgrounds/Library/Royal Gardens). Cosmetic strings only.

**`game/ui/pause_menu.py`** (≈L143–151)
- ❌ The keybind-help list strings for the 8. Cosmetic only.

**`game/input/keyboard.py`** (≈L153–155)
- ❌/update the stale comment documenting the WK34-removed hotkeys (no active wiring).

### F. Render (cosmetic label maps — authorized cross-domain mechanical removal)

**`game/graphics/renderers/building_renderer.py`**
- ❌ The 8 center-label map entries (≈L38–46: `GNOMES, ELVES, DWARVES, BALLISTA,
  WIZ TOWER, FAIR, LIBRARY, GARDENS`). ❌ The `ballista_tower` attack-range circle
  special-case (≈L178–188).

**`game/graphics/ursina_renderer.py`** (≈L150–157)
- ❌ The 8 label-map entries (`ballista_tower→"BALLISTA"`, `wizard_tower→"WIZ TOWER"`,
  `gnome_hovel→"GNOMES"`, `library→"LIBRARY"`, …). ✅KEEP `poi_wizard_tower` if it is a
  separate entry (POI).

### G. Assets (optional)
- `assets/prefabs/buildings/gnome_hovel_v1.json` becomes orphaned. Leave it OR delete it
  (cosmetic; not imported by code). ✅KEEP `poi_wizard_tower_v1.json`.

### Wave-1 self-verify (Agent 05 — paste raw output; DO NOT COMMIT)
1. Import smoke — all must succeed:
   `python -c "import config; import game; import game.content.buildings; import game.entities; import game.entities.buildings; import ai.decision_moments; import game.sim.hero_profile; import game.systems.buffs; import game.sim_engine; import game.ui.building_renderers; import game.ui.building_panel; import game.graphics.renderers.building_renderer; import game.graphics.ursina_renderer"`
2. Coverage assert: `python -c "from game.content.buildings import assert_building_type_coverage as a; a(); print('coverage OK')"`.
3. `purge_candidate` is GONE: `grep -rn "purge_candidate" game/ ai/ config.py` → ZERO hits.
4. No dangling type/class references in ACTIVE code (grep each of the 8 type strings AND
   the 8 class names across `game/`, `ai/`, `config.py`); the ONLY acceptable residue is
   `poi_wizard_tower` and unrelated sprite-cache classes like `BuildingSpriteLibrary`.
   Report any remaining hit with its file:line so PM can adjudicate.
5. Kept types intact: `python -c "from game.content.buildings import BUILDING_DEFS as D; print('guardhouse' in D, 'palace' in D, 'warrior_guild' in D, 'marketplace' in D); print('zombies gone:', not any(t in D for t in ['gnome_hovel','elven_bungalow','dwarven_settlement','ballista_tower','wizard_tower','fairgrounds','library','royal_gardens']))"` → `True True True True` then `zombies gone: True`.
6. Report the new `len(BUILDING_DEFS)` and `len(BUILDING_REGISTRY)` (from `game/building_factory.py`).

Update the Agent 05 log; report to PM. **The full pytest suite will be RED after Wave 1
(the 4 pinned test files); that is expected — Wave 2 fixes them.**

---

## 3. Wave 2 — Agent 11 (QA): fix pinned tests, add purge seam test, run DoD

### Test files to UPDATE (must reflect the purge)
1. **`tests/test_wk70_building_registry.py`** — RECOMPUTE the snapshot dicts from the LIVE
   post-purge code (do NOT hand-edit by arithmetic): remove the 8 keys from
   `EXPECTED_COSTS/SIZES/COLORS/MAX_OCCUPANTS/REGISTRY_CLASSNAMES`, and update the exact
   length asserts in `test_snapshot_self_consistency` (≈L293–301) to the new counts
   (COSTS 42→34, SIZES 47→39, COLORS 47→39, MAX_OCCUPANTS 42→34, REGISTRY_CLASSNAMES 27→19
   — but CONFIRM each by printing `len(...)` from the live modules, don't trust these numbers
   blindly). Keep the byte-identical `config.BUILDING_COSTS == EXPECTED_COSTS` assertion
   semantics (it must pass against the regenerated snapshot).
2. **`tests/test_buffs.py`** — remove/rewrite the `royal_gardens` + `royal_gardens_aura`
   tests (≈L24/34/44/64). If the file has other generic buff tests, keep those; if the
   whole file was only the aura test, replace it with a generic `Buff`/`apply_or_refresh_buff`
   unit test so buff infrastructure stays covered.
3. **`tests/test_wk61_r6_tax_gold_overlay_data.py`** — remove the `DwarvenSettlement,
   ElvenBungalow, GnomeHovel, Fairgrounds, Library` imports (≈L11–13/22) and their rows in
   the parametrized tax-overlay table (≈L37–39/50–51). Keep the kept-type rows.
4. **`tests/test_wk68_building_buttons.py`** — remove the `Library` import + the library
   research-click portion (≈L315/L373–375). KEEP `Palace`.
5. **`tests/test_hero_profile_contract.py`** (soft) — the `place_type="library"` profile-row
   fixture (≈L200–201) is generic, not registry-coupled; rename to a kept type (e.g.
   `marketplace`/`palace`) for cleanliness so no stale "library" lingers.

### NEW seam test — `tests/test_wk114_zombie_building_purge.py`
Pin the post-purge invariant:
- The 8 type strings are NOT in `BUILDING_DEFS` (parametrized).
- The 8 enum members are NOT in `BuildingType` (use `getattr(BuildingType, NAME, None) is None`).
- The 8 classes are NOT importable from `game.entities` nor `game.entities.buildings`
  (assert `not hasattr(...)`).
- `building_factory.BUILDING_REGISTRY` excludes the 8 class names; its length == the
  live value (record it).
- KEPT types present: assert `{"guardhouse","palace","warrior_guild","ranger_guild",
  "marketplace","temple","house","farm"} ⊆ set(BUILDING_DEFS)`.
- `assert_building_type_coverage()` passes (enum ⊆ defs).
- No `purge_candidate=True` remains: read `game/content/buildings.py` source (utf-8-sig)
  and assert `"purge_candidate" not in src`.

### DoD (Agent 11 — paste raw output; DO NOT COMMIT)
1. `python -m pytest -q` → **0 failed** (record passed/skipped).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q`
   → GREEN, digest STILL `b73961340c…d148ded` (the load-bearing safety gate — proves the
   purge did not perturb the headless AI scenario).
4. `python tools/qa_smoke.py --quick` → DONE: PASS.
5. `python -m pytest tests/test_wk114_zombie_building_purge.py tests/test_wk70_building_registry.py tests/test_buffs.py -q` → all green.
Update the Agent 11 log; report a PASS/FAIL table to PM.

---

## 4. PM gates (Agent 01 — before commit)

- **No-dangling-refs grep:** for each of the 8 type strings AND class names, grep `game/`,
  `ai/`, `config.py`, `tools/` — confirm the only residue is `poi_wizard_tower`, unrelated
  `*SpriteLibrary` classes, and any intentionally-left asset/comment; nothing in active code.
- **Digest:** re-confirm WK67 digest byte-identical (independent run).
- **Full DoD** re-run as needed.

## 5. Definition of done

- [ ] All 8 types gone from `BUILDING_DEFS`, `BuildingType`, `_CLASS_NAMES`, factory registry,
      and every shared list/branch (members removed, kept types intact).
- [ ] `dwellings.py` handled (file deleted if emptied, import removed); `defensive.py` keeps
      `Guardhouse`; `special.py` keeps `Palace`; `buffs.py` aura block gone.
- [ ] `purge_candidate` appears nowhere; no dangling type/class ref in active code.
- [ ] `tests/test_wk114_zombie_building_purge.py` green; the 4 pinned test files updated + green.
- [ ] full `pytest -q` 0 failed; determinism clean; **WK67 digest byte-identical**; qa_smoke PASS.
- [ ] Import smoke + coverage assert pass.
- [ ] Agent 05 + 11 logs updated. PM commits (scoped add of every touched file + plan + PM hub
      + agent logs) and pushes. (If `dwellings.py` and/or the prefab JSON are deleted, use
      `git add -A` ONLY on those explicit paths via `git rm` — never a blanket `-A`.)

## 6. Grounding for NEXT sprint (WK115)

Resume `ursina_app.py` decomposition (now 961 LOC): the **input/pointer cluster**
(`_install_ursina_input_hook`, `_pixel_hits_opaque_ui`, `_engine_screen_pos_for_pointer`,
`_sidebar_split_drag_active`, `_virtual_screen_pos`, `_pointer_event_pos`,
`_queue_pointer_motion_event`, `_handle_ursina_input`, +`_is_chat_active`) → new
`game/graphics/ursina_app_input.py`, owner-arg pure-move (WK113 pattern). Note the
intra-cluster call chain + the closure in `_install_ursina_input_hook` + cross-cluster
calls into the WK113 camera wrappers (`owner._reset_camera_to_default()` etc. stay).
Camera features are playtest-confirmed working (Sovereign 2026-05-31), so WK113 is closed.
