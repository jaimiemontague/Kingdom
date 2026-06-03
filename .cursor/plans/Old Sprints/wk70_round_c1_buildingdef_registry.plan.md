# WK70 Sprint Plan — Round C-1: BuildingDef single-source registry (Move 10, kills L7)

**Author:** Agent 01 (ExecutiveProducer_PM)
**Date:** 2026-05-30
**Sprint goal (DoD gate):** all tests pass; one `BUILDING_DEFS` registry is the single source of truth for building static data, and the 4 config maps + the factory registry + the catalog/hotkey lists are DERIVED from it as byte-identical back-compat views; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68 (Round A complete), WK69 (Round B-1 sim split).
**Roadmap:** Round C (registries / single-source-of-truth, Move 10 + dedup clusters). This is **Round C-1: the building registry.**
**Grounding:** a full read-only inventory of all 6 parallel registries was produced (see §2); this plan encodes its exact findings.

---

## 0. TL;DR

Building static data is fragmented across **6+ parallel string-keyed maps with measured drift** (the audit's "most severe" dedup, leak **L7**): `config.BUILDING_COSTS` (42 keys), `BUILDING_SIZES` (47), `BUILDING_COLORS` (47), `BUILDING_MAX_OCCUPANTS` (42), `BuildingFactory.BUILDING_REGISTRY` (27), the `BuildingType` enum (30), plus **three byte-identical copies** of the placeable list + hotkeys (build_catalog_panel.py, building_list_panel.py, input_handler.py if/elif). Adding/changing a building means editing all of them in lockstep.

WK70 introduces **one** `BUILDING_DEFS: dict[str, BuildingDef]` and **derives every other map from it** as a back-compat view, so all ~10 current readers keep working unchanged. **This is purely behavior-preserving** — the derived views must have byte-identical keys AND values to the current maps (a snapshot test guards this). No gameplay, render, or AI change; no screenshots; the digest `b73961…` stays byte-identical.

**Deferred (NOT this sprint):** actually DELETING the 8 WK34 zombie types (gnome_hovel, elven_bungalow, dwarven_settlement, ballista_tower, wizard_tower, fairgrounds, library, royal_gardens) from the enum/factory/classes — that's a guarded deletion sprint. WK70 INCLUDES them in `BUILDING_DEFS` (marked as purge candidates) so the consolidation is 100% behavior-preserving.

**You (PM) write no code.** Dispatch role-onboarded `claude-opus-4-8` subagents, gate on the snapshot test + digest + suite, loop fixes.

---

## 1. Why this sprint

The audit calls building-data fragmentation "the most severe slop class" (Cluster 1 = leak L7). The 6 maps already drift (lairs in SIZES/COLORS but not COSTS/OCCUPANTS; 8 zombie types with cost=0 sentinels still occupying every map; the hotkey chain uses lowercase `t`/`u` while the dicts use `T`/`U`). One source of truth + derived views removes the drift class permanently and makes the next building change a one-line edit. It's mostly headless (config/registry), verifiable by a snapshot-equality test + the digest, and is the audit's highest-leverage Round-C item.

---

## 2. The verified inventory (encode this exactly)

**The 8 WK34 zombie types** (cost=0 + `# WK34 REMOVED` comment at config.py:195-205; still in enum + SIZES + COLORS + OCCUPANTS + factory): `gnome_hovel, elven_bungalow, dwarven_settlement, ballista_tower, wizard_tower, fairgrounds, library, royal_gardens`. → **Include in BUILDING_DEFS with current values, flagged `purge_candidate=True`; do NOT delete this sprint.**

**Lairs (5)** — `goblin_camp, wolf_den, skeleton_crypt, spider_nest, bandit_camp`: in SIZES + COLORS ONLY (absent from COSTS, OCCUPANTS, enum, factory). Constructed as `MonsterLair(Building)` subclasses in `game/entities/lair.py`; they hit `Building.__init__` fallback cost=100/occupants=8. → **Include with `is_lair=True`, `cls=<LairClass>`; the derived `BUILDING_COSTS`/`BUILDING_MAX_OCCUPANTS` views MUST EXCLUDE lairs (preserve current absence so they keep hitting the base default), while `BUILDING_SIZES`/`BUILDING_COLORS` views INCLUDE them.**

**POIs (12)** — `poi_*`: in all 4 config maps but NOT enum/factory; have their own `POI_DEFINITIONS` (game/entities/poi.py) and route via the factory's POI branch. → **Leave POIs in `POI_DEFINITIONS`; the 4 config-map views must still include the poi_* keys with current values (so config readers are unchanged); add an assert that BUILDING_DEFS ∪ POI keys cover the maps. Simplest: include poi_* rows in BUILDING_DEFS with `is_poi=True, cls=None` so the views derive cleanly.**

**Per-caller `.get(key, default)` defaults vary and are load-bearing — DO NOT unify them:** cost default 100 (base.py:78), 0 (neutral/UI/economy:23), 999999 (economy:18); size default (1,1) (base/menu), (2,2) (ursina_prefabs:68), (3,2) (neutral farm). The derived views are drop-in `dict`s; the callers keep their own `.get(..., default)` calls unchanged.

**Hotkeys/placeable (currently 3 copies, all agree):** `{warrior_guild:1, marketplace:2, ranger_guild:3, rogue_guild:4, wizard_guild:5, blacksmith:6, inn:7, trading_post:8, temple:T, guardhouse:U}`; placeable order `[warrior_guild, ranger_guild, rogue_guild, wizard_guild, marketplace, blacksmith, inn, trading_post, temple, guardhouse]`. Note **display order ≠ hotkey order** — encode BOTH (`hotkey` field + a `placeable_order` index or an explicit ordered list).

**Guild→hero-class (sole authority `engine.py:1006` `class_by_guild`):** warrior_guild→warrior, ranger_guild→ranger, rogue_guild→rogue, wizard_guild→wizard, temple→cleric. → derive from `BuildingDef.hero_class`. NOTE `PLAYER_GUILD_TYPES` (4, no temple) ≠ engine `allowed` (5, with temple) — keep them as two distinct predicates.

**Path corrections:** factory is `game/building_factory.py:45` (not under entities/buildings/); catalog list is the instance attr `placeable_buildings` (lowercase). The "~17 zombie keys" = 8 types × stale rows across maps.

---

## 3. Scope — IN and OUT

**IN (WK70):**
- New `game/content/buildings.py`: `@dataclass(frozen=True, slots=True) BuildingDef` + `BUILDING_DEFS: dict[str, BuildingDef]` covering: all 30 enum types (incl. the 8 zombies, flagged), the 5 lairs (`is_lair`), and the 12 POIs (`is_poi`). Fields: `type, size, color, cost, max_occupants, cls, hotkey, placeable, placeable_order, hero_class, is_lair, is_poi, purge_candidate`.
- Derive in `config.py` (replacing the 4 hardcoded dicts): `BUILDING_COSTS` (exclude lairs), `BUILDING_SIZES` (incl. lairs+POIs), `BUILDING_COLORS` (incl. lairs+POIs), `BUILDING_MAX_OCCUPANTS` (exclude lairs) — **each byte-identical in keys+values to today's dict** (snapshot-guarded).
- Derive `BuildingFactory.BUILDING_REGISTRY` from `{k:d.cls for ... if d.cls and not d.is_poi and k not in (castle,house,farm)}`.
- Derive the catalog placeable list + `BUILDING_HOTKEYS` from `BUILDING_DEFS` in build_catalog_panel.py; have building_list_panel.py + the input_handler hotkey dispatch READ the same derived maps (kill the 2 duplicate copies + the if/elif chain — replace with a `{hotkey:type}` reverse-map lookup).
- Import-time coverage assert: `{bt.value for bt in BuildingType} <= set(BUILDING_DEFS)`.
- A snapshot-equality test pinning the derived views == the pre-refactor values.

**OUT (deferred):**
- **Deleting the 8 zombie types** (enum members + factory entries + their classes + constraints/tax-set memberships). → a separate guarded "zombie purge" sprint (grep for any live construction first).
- Folding `TAX_STASH_BUILDING_TYPES`/`NON_TAX_STASH_BUILDING_TYPES`/`BUILDING_CONSTRAINTS`/`BUILDING_PREREQUISITES` into BuildingDef (leave as-is; they reference zombies).
- Cluster 3/4/5 dedups (visual_specs, hero colors, audio) — later Round-C sprints.
- The guild→class move is OPTIONAL this sprint (do it only if clean; else leave engine.py:1006 and just note BuildingDef.hero_class mirrors it).

---

## 4. Definition of Done

- **A.** `python -m pytest` → all pass (baseline **633 passed / 4 skipped / 0 failed**).
- **B.** `python tools/determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** **Snapshot-equality test passes:** the derived `BUILDING_COSTS/SIZES/COLORS/MAX_OCCUPANTS` have byte-identical keys AND values to a captured snapshot of the pre-WK70 dicts (the test embeds the old values literally). The factory registry derives to the same 27 class mappings. The catalog/hotkey maps derive to the same values.
- **F.** `BUILDING_DEFS` is the only hand-authored building-data table; the 4 config dicts, the factory registry, and the catalog/hotkey lists are all DERIVED (no second hand-maintained copy remains; building_list_panel.py + input_handler hotkey dispatch read the derived maps).
- **G.** `python tools/validate_assets.py --report` → no NEW errors (prefab building_type coverage unchanged).
- **H.** Agents updated their logs; PM hub records the close.

---

## 5. Waves

```
W1 (Agent 05): create game/content/buildings.py (BuildingDef + BUILDING_DEFS) + derive the 4 config maps + coverage assert.  -> PM gate (snapshot test + digest + suite)
W2 (Agent 05): derive factory registry + catalog/hotkey/placeable; kill the 2 duplicate copies + the input_handler if/elif.  -> PM gate
W3 (Agent 11): snapshot-equality test (capture old values) + full DoD gate (suite, digest, determinism, qa_smoke, validate_assets).
   (Agent 03 consult: architecture/import-order if config.py circular-import risk appears — config is imported by 152 files.)
```

W1 and W2 are sequential (both touch config.py + the registry). W3 verifies.

---

## 6. Per-wave tasks

### W1 — BuildingDef + BUILDING_DEFS + derived config maps (Agent 05)
- Create `game/content/buildings.py` with the `BuildingDef` dataclass and `BUILDING_DEFS` populated from the §2 inventory — **copy the EXACT current values** for every key (costs/sizes/colors/occupants per the inventory; cls per the factory; hotkey/placeable per §2). Include zombies (flagged), lairs (`is_lair`), POIs (`is_poi`).
- In `config.py`, REPLACE the 4 hardcoded dicts with derived views:
  ```python
  from game.content.buildings import BUILDING_DEFS
  BUILDING_COSTS = {k: d.cost for k, d in BUILDING_DEFS.items() if not d.is_lair}
  BUILDING_SIZES = {k: d.size for k, d in BUILDING_DEFS.items()}            # incl. lairs + POIs
  BUILDING_COLORS = {k: d.color for k, d in BUILDING_DEFS.items()}          # incl. lairs + POIs
  BUILDING_MAX_OCCUPANTS = {k: d.max_occupants for k, d in BUILDING_DEFS.items() if not d.is_lair}
  ```
  Match the CURRENT membership exactly (W3's snapshot test is the guard — run it locally as you go).
- **Import-cycle caution:** `game/content/buildings.py` must import `cls` types lazily or carefully — the building classes import from `game/entities/buildings/*` which may import `config`. If a cycle appears, store `cls` as a lazy resolver (a string class-name + a `factory_class(key)` accessor) or import the classes inside a function. Coordinate with Agent 03 if needed. The `BuildingType` coverage assert can live in `config.py` after the import.
- Add `assert {bt.value for bt in BuildingType} <= set(BUILDING_DEFS)` at import.
- VERIFY: `python -m pytest tests/test_wk67_ai_boundary.py -q` (digest), `python -m pytest tests/test_building.py -q`, then full `pytest -q` (633 passed) + determinism_guard. Report the derived-vs-old diff (should be none).

### W2 — derive factory + catalog/hotkeys; kill the duplicate copies (Agent 05)
- `game/building_factory.py`: derive `BUILDING_REGISTRY = {k: d.cls for k,d in BUILDING_DEFS.items() if d.cls and not d.is_poi and k not in ("castle","house","farm")}` (must equal the current 27 mappings — verify).
- `game/ui/build_catalog_panel.py`: derive `placeable_buildings` (ordered by `placeable_order`) and `BUILDING_HOTKEYS` from `BUILDING_DEFS`.
- `game/ui/building_list_panel.py`: read the SAME derived maps (delete its duplicate `BUILDING_HOTKEYS` + `placeable_buildings`).
- `game/input_handler.py:298-320`: replace the hardcoded if/elif hotkey chain with a `{hotkey: type}` reverse-map derived from `BUILDING_DEFS` (note: the chain used lowercase `t`/`u`; the dicts use `T`/`U` — pick the working one, verify the build hotkeys still trigger the right building; if a test/observe covers this, run it).
- VERIFY: full `pytest -q`, digest, determinism_guard, qa_smoke. Report the derived factory/catalog/hotkey equality.

### W3 — snapshot-equality + DoD gate (Agent 11)
- Create `tests/test_wk70_building_registry.py`: embed a literal snapshot of the PRE-refactor `BUILDING_COSTS/SIZES/COLORS/MAX_OCCUPANTS` (exact keys+values from §2 / the current source) and assert the derived views equal them EXACTLY (keys set + every value). Assert the factory registry has the same 27 class mappings (by class name). Assert `BUILDING_HOTKEYS`/placeable derive to the known values. Assert the import-time coverage assert holds and that POI/lair membership in each view matches §2.
- Run the full DoD gate (A-G) and report.

---

## 7. Risk assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Derived view drifts from current values (membership or value) | Med | W3 snapshot-equality test embeds the literal old values; run it after W1 |
| Import cycle (game/content/buildings ↔ config ↔ entities) | **Med-High** | config is imported by 152 files; resolve `cls` lazily (string name + accessor) or import classes inside a function; Agent 03 consult |
| Lair/POI membership wrong in a view → a reader's `in`/iteration changes | Med | §2 specifies exact membership (lairs out of COSTS/OCCUPANTS, in SIZES/COLORS; POIs in all 4); snapshot test guards it |
| Hotkey case mismatch (t/u vs T/U) changes which key triggers a build | Low | Pick the currently-working mapping; verify via the hotkey reverse-map test |
| Digest drift (building costs/sizes affect the seeded scenario) | Low | Values are byte-identical → digest unchanged; verify after W1 |

---

## 8. Success criteria (one-liner)

WK70 succeeds when there is exactly ONE hand-authored building table (`BUILDING_DEFS`), every other building map is derived from it with byte-identical keys+values, the 3 duplicate hotkey/placeable copies are gone, and **everything plays identically** — proven by the snapshot-equality test, 633+ green tests, and the unchanged `b73961…` digest.

---

## 9. Follow-up backlog

- **Zombie purge sprint:** delete the 8 WK34 types (enum + factory + classes + constraints/tax sets + dead comment), grep-guarded for zero live construction.
- Fold `TAX_STASH`/`NON_TAX_STASH`/constraints/prereqs into BuildingDef flags.
- Cluster 3 (UnitVisualSpec adoption), Cluster 4 (`HERO_CLASS_COLORS`), Cluster 5 (audio contract).
- Round B-2 presentation splits (hud/ursina_renderer/engine/hero/input_handler); Move 9 (SystemRunner); Round D (AI router).

---

## 10. Kickoff appendix

**Roster:** 05 GameplaySystems (W1+W2, sequential — owns building content/registry), 11 QA (W3 snapshot-equality + DoD gate), 03 TechnicalDirector (on-call consult for import-order/cycle).
**Dispatch order:** 05 W1 → PM gate (snapshot test + digest + suite) → 05 W2 → PM gate → 11 W3 → PM final gate → commit+push.
**Universal reminders:** onboard via `.cursor/rules` for your #; read your PM-hub task + this plan; `claude-opus-4-8`; BEHAVIOR-PRESERVING — derived views byte-identical to current, digest `b73961…` unchanged; NO screenshots; update your own log; **DO NOT COMMIT**; no iterate after `status=done`.
