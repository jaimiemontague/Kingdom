# WK49 — Hero Profile MVP — Player-facing acceptance

**Sprint:** `wk49_hero_profile_foundation`  
**Owner:** Agent 02 (GameDirector / Product)  
**Plan:** `.cursor/plans/wk49_hero_profile_foundation_274e344b.plan.md`  
**Roadmap:** `.cursor/plans/wk49_hero_profile_roadmap_6f3a1b2c.plan.md`

This checklist defines **what the player must see and verify** when they select a hero after the WK49 implementation waves. Engineering uses `HeroProfileSnapshot` / `selected_hero_profile`; this doc is the **player-observable** contract.

---

## Scope reminder (product)

**In scope for WK49 MVP**

- Richer hero profile driven by the same read model UI and future LLM adapters will share.
- Stable per-hero identity (`hero_id`) so duplicate names do not confuse the panel.
- Bounded, deterministic **recent memory** and **known places** surfaced in UI when data exists.

**Out of scope (explicit non-goals for signoff)**

- Full LLM behavior or prompt changes.
- Emotional simulation driving decisions; skills/spells; full quest framework.
- Save/load of profile history beyond what the live session holds.
- Migrating every gameplay system from `hero.name` to `hero_id` (only profile correctness where required).

---

## Environment

- Primary resolution: **1920×1080** (window or borderless per project defaults).
- Manual smoke: `python main.py --no-llm` from repo root.
- Automated UI evidence: screenshot scenario and path per sprint plan (Agent 11).

---

## 10-minute manual pass (player)

Use `--no-llm`. Start a run, let heroes move, then:

1. **Select several heroes** (including two with the **same displayed name** if the scenario produces them).
2. Watch the **left hero profile panel** for each selection.
3. Let at least one hero **explore near buildings** so discovery/memory can populate.
4. Re-select the same hero after time passes and confirm **memory / known places** update or show an explicit empty state (no silent failure).

---

## Acceptance criteria (pass / fail)

### Stability and selection

| # | Criterion | Pass |
|---|-----------|------|
| S1 | Clicking/selecting a hero **never crashes** the game during normal profile display. | Yes |
| S2 | Switching quickly between heroes **does not** crash or show stale data from the prior hero (wrong identity block). | Yes |
| S3 | If two heroes share a **name**, the panel still reflects the **actually selected** hero (distinct stats/identity line); no obvious “mixed” sheet. | Yes |

### Identity and progression

| # | Criterion | Pass |
|---|-----------|------|
| I1 | **Name** and **class** (hero type) are visible in the profile header area. | Yes |
| I2 | **Level** is shown as an integer the player can read at a glance. | Yes |
| I3 | **XP** is visible as current vs next-level (or equivalent: current, target, and a **percent or bar**). Player can tell how far to the next level. | Yes |

### Vitals

| # | Criterion | Pass |
|---|-----------|------|
| V1 | **HP** is shown (current / max or bar + numbers). | Yes |
| V2 | **Attack** and **defense** (ATK / DEF) are shown as readable integers (or clearly labeled values). | Yes |
| V3 | **Speed** is shown if present on the snapshot; if omitted for space, UI documents “deferred” in Agent 08 notes—not a silent gap without team agreement. | Per implementation |

### Economy and gear

| # | Criterion | Pass |
|---|-----------|------|
| E1 | **Gold** (spendable) is visible. | Yes |
| E2 | **Taxed gold** (or equivalent “owed / withheld” label) is visible if the sim tracks it. | Yes |
| E3 | **Potions**: current and cap (or “N / M”) are visible. | Yes |
| E4 | **Weapon**: name (or “None”) and offensive contribution if the contract exposes it (e.g. weapon attack). | Yes |
| E5 | **Armor**: name (or “None”) and defensive contribution if exposed (e.g. armor defense). | Yes |

### Personality and “who they are”

| # | Criterion | Pass |
|---|-----------|------|
| P1 | **Personality** string (from profile identity/persona) is visible—not only class. | Yes |
| P2 | **Narrative seed** fields (`emotional_state`, `life_stage`, `personal_goal`, `origin_hint` per plan) may show as **short labels** or a single compact line; full prose is **not** required this sprint. | Optional / compact |

### Situation: location, intent, target

| # | Criterion | Pass |
|---|-----------|------|
| L1 | **Current location** reads naturally (e.g. `Inside: <Building Type>` vs `Outdoors` per plan). | Yes |
| L2 | **Current intent** is visible (what they are trying to do in player language). | Yes |
| L3 | **Current state** (state machine label) is visible if space allows; if cut for width, **intent + location** must remain. | Prefer both |
| L4 | **Current target** is a **short** string (building/enemy/bounty-style label), not a debug dump. | Yes |
| L5 | **Last decision** (structured summary / reason / age) appears if provided by sim; if missing, UI shows nothing or an unobtrusive placeholder—**no** crash. | Yes |

### Career stats

| # | Criterion | Pass |
|---|-----------|------|
| C1 | A **career** section shows counters that match the sprint plan intent, e.g. tiles revealed, places discovered, enemies defeated, bounties claimed, gold earned, purchases made—or a clearly labeled subset if space forces a phase-1 cut (document cut in Agent 08 report). | Yes (subset OK if documented) |

### Known places

| # | Criterion | Pass |
|---|-----------|------|
| K1 | **Known places** appear as a **bounded** list (count + lines or compact list): stable id-backed entries, not raw objects. | Yes |
| K2 | When **no** places are known, UI shows an **explicit empty state** (e.g. “No places yet”) rather than a blank hole. | Yes |
| K3 | After exploration, **at least one** known place can appear in a normal run (per sprint: discovery hook). | Yes |

### Recent memory

| # | Criterion | Pass |
|---|-----------|------|
| M1 | **Recent memory** shows the **latest** entries (newest first or chronological with clear order—team picks one and stays consistent). | Yes |
| M2 | Each line is **short** (truncation OK); no wall of text in the narrow left column (~224px). | Yes |
| M3 | When memory is empty, UI shows **empty state**, not crash. | Yes |
| M4 | In a normal run, **at least one deterministic memory event** can appear (e.g. discovering / seeing a known place), per sprint plan. | Yes |

### Readability and regression

| # | Criterion | Pass |
|---|-----------|------|
| R1 | At **1920×1080**, profile text is **readable**: no clipped critical numbers, no overlapping sections in screenshot spot-check (Agent 11). | Yes |
| R2 | **Previous baseline info** (pre-WK49: name, key stats, chat affordances) **still works**; WK49 is additive, not a regression of the old panel. | Yes |
| R3 | **Hero Focus / right panel**: Chat behavior **preserved** this sprint unless broken; optional richer profile in top half is **nice-to-have**, not a release blocker if PM accepts “left panel first” per plan. | Per plan |

### LLM / AI behavior

| # | Criterion | Pass |
|---|-----------|------|
| A1 | **No** change to LLM provider behavior is required for WK49 signoff; `--no-llm` path is sufficient for this checklist. | Yes |

---

## Product cuts and objections (locked guidance)

- **Width:** Left column stays tight; long strings must **truncate with ellipsis** or stack. Prefer **2 memory lines** + “more in focus panel later” over unreadable clutter.
- **Speed / marginal stats:** May defer if ATK/DEF/HP/gold/intent fill the bar; document any deferral.
- **Right panel:** Ship **left panel MVP** first if layout risk is high; right panel expansion is secondary per execution plan.
- **Emotional / story depth:** Display **labels only**; no derived “mood engine” affecting gameplay this sprint.

---

## Definition of Done (cross-reference)

Sprint **DoD** from plan: profile contract exists, `hero_id` non-empty, `selected_hero_profile` in `get_game_state()`, UI renders without overlap in screenshot verification, memory/places bounded and deterministic, `qa_smoke --quick` passes, assets validator clean—plus this document for **player-facing** signoff.

---

## Sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| Product (Agent 02) | — | 2026-04-30 | Checklist authored |
| QA (Agent 11) | — | — | Pending implementation |
| PM / Human smoke | Jaimie | — | Pending `python main.py --no-llm` |
