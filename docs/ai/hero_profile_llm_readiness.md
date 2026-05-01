# Hero Profile — LLM readiness (WK49 review)

**Scope:** Read-model only. No LLM behavior changes this sprint.  
**Sources reviewed:** `game/sim/hero_profile.py`, `game/systems/hero_memory.py`, `ai/context_builder.py`, execution plan Agent 06, roadmap Phase 2.

## 1. Is `HeroProfileSnapshot.to_dict()` enough structure for future prompts?

**Yes, as a stable “character sheet + situation” core.** Nested dataclasses flatten with `dataclasses.asdict()` into JSON-friendly primitives (strings, ints, floats, bools, lists, dicts). There are no live `Hero` / building / world references in the snapshot.

**What it gives the LLM well today**

- **Identity:** `hero_id`, name, class, personality, level.
- **Progression / vitals / inventory:** XP bar fields, HP/ATK/DEF/speed, gold, taxed gold, potions cap, weapon/armor names and stats.
- **Career:** aggregate counters (tiles revealed, places discovered, defeats, bounties, gold earned, purchases).
- **Situation:** `current_state`, `current_intent`, compact `current_location`, `current_target`, optional `last_decision` dict (matches existing decision logging).

**What it does *not* replace**

- **Tactical/world slice** still lives in `ContextBuilder` today: nearby enemies/allies (with distances), summarized bounties, shop_items, situation flags, building occupancy, `player_is_present`. A future adapter should **merge** a trimmed `profile_to_llm_context(...)` with a **bounded** tactical dict rather than dumping the full profile `to_dict()`.

## 2. Known places and recent memory — safe for LLM?

**Yes.** `known_places` is a tuple of `KnownPlaceSnapshot` (ids, types, labels, tile/world_pos, visit metadata). `recent_memory` is a tuple of `HeroMemoryEntry` (event_type, summary, subjects, tags, importance, sim_time_ms). No object handles.

Simulation caps (single source in `game/systems/hero_memory.py`):

- **`PROFILE_MEMORY_MAX_ENTRIES = 30`**
- **`KNOWN_PLACES_MAX_ENTRIES = 100`**

Snapshot build sorts deterministically (`sort_known_places`, `sort_memory_entries`), so prompt-friendly slices are order-stable.

## 3. Recommended limits *into* the LLM prompt (token control)

Storage caps are **upper bounds**; prompts should use **smaller** working sets unless doing a rare “deep recap” mode.

| Slice | Recommended default for **decision** prompts | Notes |
|-------|---------------------------------------------|--------|
| `known_places` | **6–10** entries | Prefer places **near current tile or current target** once distance metadata exists; else most recent by `last_seen_ms` / `visits`. |
| `recent_memory` | **8–12** entries | Roadmap aligns with ~8–12; include any `importance >= 2` first, then chronological tail. |
| Full `career` | **Keep** (small) | Numeric counters are cheap. |
| `narrative` | **Keep** once non-default | Today builder often uses defaults; see §5. |
| Entire `to_dict()` | **Avoid** for routine calls | Full known_places (up to 100) + rich last_decision can bloat context. |

Suggested Phase-2 helper shape (from sprint plan, refined):

```python
def profile_to_llm_context(profile, *, known_place_limit=8, memory_limit=12) -> dict:
    ...
```

Add optional `mode="decision" | "conversation"` later: conversation may allow slightly more memory, still capped.

## 4. Summarize vs verbatim

- **Verbatim (short):** `identity`, `current_intent`, `current_target`, `last_decision` reason/action, last few `summary` lines on memory entries, `known_places` `display_name` + `place_type`.
- **Summarize or filter:** long memory tails, large place lists, repeated discover events, low-importance noise.
- **Derive in adapter, do not store in sim hot paths:** emotional tone sentences, “story so far” paragraphs, relationship prose.

## 5. Missing or weak fields before a dedicated LLM update

| Gap | Risk | Suggested follow-up (not WK49 behavior) |
|-----|------|----------------------------------------|
| **`narrative`** always default in `build_hero_profile_snapshot` | LLM sees placeholder inner-life fields only | Persist seed fields on `Hero` when PM scopes it; builder reads stable per-hero narrative seeds. |
| **Location vocabulary** differs: profile `format_location_compact` (`In:blacksmith` / `Out`) vs `ContextBuilder` prose (`outdoors`, building occupiers) | Minor confusion in merged prompts | Unify labels in adapter layer (“display string” vs “semantic tag”). |
| **No `hero_id` in older ContextBuilder paths** | Mostly fixed if `hero_id` always set; adapter should prefer profile identity | Ensure `ContextBuilder.build_hero_context` uses profile identity when available. |
| **No distances in profile** (hero→target, hero→nearest inn, etc.) | LLM must rely on tactical dict | Keep distances in tactical slice; optionally add **derived** `distance_to_target_tiles` on snapshot later if cheap. |
| **World facts** (active bounty assignment, party orders) | Not in profile by design | Continue merging `bounty_options` / flags from `game_state`; document the split: **profile = who + history**, **context = local situation**. |
| **Skills / spells / quests** | Out of WK49 scope | Reserve roadmap fields; LLM must not invent mechanics until sim exposes them. |

## 6. Conclusion

The WK49 profile contract is **ready to back a Phase-2 LLM context adapter**: structured, bounded storage, deterministic ordering, no raw object leakage. Next engineering step is **not** to grow the prompt from raw `Hero`; it is to implement **`profile_to_llm_context` + merge with existing `ContextBuilder` tactical data**, with explicit numeric limits and optional importance-first memory selection.
