# WK122 Round B — fix: clicking a guard / tax collector crashes (WK63 selection regression)

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Sprint key (PM hub):** `wk122_round_b_guard_taxcollector_selection_crash`
**Version target:** patch (crash/regression fix + restored info panels)
**Verification class:** MIXED — headless gates + PYGAME HUD captures are authoritative for the
panels (NOT the deferred ursina exception); the live in-world *click* that picks a guard in the
3D scene is an ursina interaction → **deferred to Jaimie's end-test** (exact command in §6).
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. The bug (Sovereign-reported, live play)

Clicking the **market while a hero was selected** crashed the game:

```
File "game/engine_facades/selection.py", line 107, in try_select_guard
    engine.selected_hero = best
File "game/engine.py", line 462, in selected_hero
    self.selection.select_hero(v.hero_id)
AttributeError: 'Guard' object has no attribute 'hero_id'
```

A **guard** standing near the market is hit-tested *before* the building in the click-priority
chain (`game/input/mouse.py:313`, guard before building), so the crash fires on the guard, not
the market.

**Sovereign directive on scope:** *"They used to have their own panel, so look for code with a
basic info panel and if you can't find it then go ahead and add it."*

---

## 1. Root cause (CONFIRMED — diagnosed via a 3-agent read-only investigation)

This is a **WK63 regression**. The WK63 boundary cleanup made `selected_hero` ID-based:

- `engine.py` `selected_hero` **setter** (~L457-462): `self.selection.select_hero(v.hero_id)`
- `engine.py` `selected_hero` **getter** (~L447-455): resolves the id only against `self.sim.heroes`

But **six call sites still force-fit a non-hero into the hero slot** — restoring pre-WK63 behavior
where `selected_hero` held a *live object*:

| Site | Entity |
|------|--------|
| `game/engine_facades/selection.py:86` (`try_select_tax_collector`) | TaxCollector |
| `game/engine_facades/selection.py:107` (`try_select_guard`) | Guard ← **the crash hit** |
| `game/engine_facades/selection.py:183` (`try_ursina_select_unit_at_screen`) | TaxCollector |
| `game/engine_facades/selection.py:188` (`try_ursina_select_unit_at_screen`) | Guard |
| `game/engine.py:462` setter | (both, for guard) |
| `game/engine.py:462` setter | (both, for tax_collector) |

`Guard` has `.entity_id` (no `hero_id`); `TaxCollector` has neither (it is the singleton
`self.sim.tax_collector`). So **any click that picks a guard or the tax collector crashes.**
`try_select_tax_collector` and both ursina-pick branches are **latent crashes** of the same bug.

## 1a. KEY finding — the panels were never removed

The guard / tax-collector info panels are **alive and intact** in `game/ui/hero_panel.py`:
`_render_guard()` (~L328-441) and `_render_tax_collector()` (~L248-326). `HeroPanel.render()`
(~L1096-1101) dispatches on `isinstance(hero, TaxCollector)` then `isinstance(hero, Guard)`
*before* `_render_standard_hero`. The snapshot already does `gs["selected_hero"] = self.selected_hero`
and builds `selected_hero_profile` with a `getattr(_sel, "hero_id", "")` default (safe → `None`
for non-heroes). **They have worked since WK49 (commit 0bfd6fb).** The ONLY thing WK63 broke is
the `selected_hero` property / `SelectionState` being unable to *hold and resolve* a Guard or
TaxCollector. → Sovereign's "they used to have a panel" is correct; the panels exist; **reconnect,
don't rebuild.**

---

## 2. The fix (Design B — minimal, locked)

**Restore the hero slot's ability to carry a Guard / TaxCollector, keeping WK63's no-stale-ref
semantics. NO new selection slots. NO new panel classes. Do NOT touch the existing hero_panel
panels.** (The competing "add `selected_guard`/`selected_unit` + new panel classes" design was
rejected — it would duplicate working code and orphan the real panels.)

1. **`game/presentation/selection_state.py`** — add `selected_hero_kind: Optional[str] = None`
   (`'hero' | 'guard' | 'tax_collector'`). `select_hero(hero_id, kind='hero')` sets id+kind
   (still clears enemy+peasant). `clear_hero()` resets kind. `on_entity_destroyed` resets kind
   when it clears the hero id. Keep `dataclass(slots=True)` valid.
2. **`game/engine.py` `selected_hero` property:**
   - **setter:** `None`→clear; `Guard`→`select_hero(v.entity_id, kind='guard')`;
     `TaxCollector`→`select_hero(None, kind='tax_collector')`; else hero→`select_hero(v.hero_id,'hero')`.
     Use isinstance with a cycle-safe (local) import, or duck-typing. Verify `import game.engine` still works.
   - **getter:** branch on kind — `'guard'`→live guard in `sim.guards` by `entity_id` & `is_alive`
     else clear+None; `'tax_collector'`→`sim.tax_collector` else clear+None; `'hero'`/None→
     **byte-identical** existing behavior. Resolves live each frame (no stale refs for any kind).
3. **Defensive (only if reachable):** `game/input/keyboard.py:~194` does `c.selected_hero.name`
   (guards/tax-collector have no `.name`). If reachable with a non-hero selected, make it
   `getattr(..., "name", "")`; else leave it.

**Out of scope (do NOT touch):** `mouse.py:141/158`, `actions.py:254` (they receive heroes); the
"set-one-clear-others" idiom; any sim behavior. No new files.

### Why downstream already tolerates a non-hero in the slot
- `engine.py:~943` profile builder uses `getattr(_sel,"hero_id","")` → `None` for non-heroes.
- `hero_panel.render()` isinstance-dispatches to the guard/tax panels *before* hero-only code.
- `hud_left_layout.py:410-411`, `hud_panel_buttons.py:124` all use `getattr(sel,"hero_id","")`.

---

## 3. Tests (regression)

`tests/test_guard_taxcollector_selection.py` (headless): select a guard and the tax collector via
the pygame path AND the ursina-pick assignment path → assert **no exception**, `engine.selected_hero`
returns the SAME object, `isinstance` correct. Stale-ref case: select a guard, kill/remove it →
`engine.selected_hero is None`, no crash. Normal hero selection still returns the hero.

## 4. Headless HUD captures (pygame HUD — authoritative here)

Two PNGs under `tmp/wk122_captures/` (throwaway, not committed): Guard selected → Guard panel
(header / state / HP); TaxCollector selected → Tax Collector panel (status / gold). Reviewed for
alignment+layering first, then content.

## 5. Gates (Definition of Done)

- `python tools/qa_smoke.py --quick` → exit 0 (incl. determinism guard)
- WK67 behavior digest → byte-identical (selection is presentation-owned; sim untouched)
- Targeted pytest: selection + hud + watch-card suites + the new regression test → green
- FPS Gate 5: `11-fps-performance-guardrails.mdc` read; per-frame `selected_hero` getter adds only
  a guard-list scan *when a guard is selected* — no known cost reintroduced
- Adversarial review verdict: hero selection byte-identical, stale-ref handled, all 6 sites safe,
  hero-only readers safe, no import cycle
- **No commit** without Sovereign go-ahead

## 6. Human end-test (Jaimie) — live ursina click (deferred exception)

```
python main.py
```

Then: select a hero → click a **guard** (the little patrol units near guardhouses/palace, or the
one near the market) → expect a **Guard** info panel on the left (no crash). Click the **tax
collector** (gold-colored NPC) → expect a **Tax Collector** panel. Click the **market** itself →
building panel. Report any crash or wrong/missing panel.
