## Event Table (Draft) — Content Hooks for Replayability

This document proposes **event content** (raids, festivals, disasters) that can be layered on top of current systems.

Design goals:

- **Telegraph → response → consequence** (readable and fair)
- **Small footprint**: events should mostly change *existing knobs* temporarily
- **Deterministic-friendly**: schedule by sim time/ticks

---

## Suggested “Event” structure (content-only)

```json
{
  "id": "festival_small",
  "name": "Harvest Festival",
  "category": "festival",
  "weight": 5,
  "min_time_seconds": 90,
  "max_time_seconds": 600,
  "cooldown_seconds": 180,
  "telegraph_seconds": 8,
  "effects": [
    { "type": "tax_bonus_pct", "value": 10, "duration_seconds": 45 }
  ]
}
```

---

## P0 event set (safe + simple)

### Festivals (economy spikes; positive pressure relief)

- **Harvest Festival**
  - **Telegraph**: HUD message “Festival begins soon…”
  - **Effect**: `tax_bonus_pct +10%` for 45s (or “bonus gold on kills +X%”)
  - **Counterplay**: hire/build during window

- **Market Boom**
  - **Effect**: discount marketplace items 15% for 60s
  - **Counterplay**: encourage potion/gear stocking

### Raids (localized spike; teaches defense + bounty usage)

- **Bandit Raid**
  - **Spawn**: small enemy group at map edge (reuses spawn system)
  - **Target**: nearest neutral building cluster (houses/food stands)
  - **Reward**: place an auto `hunt_enemy_type` bounty for “goblin/bandit” (or targeted defend bounty)

### Disasters (soft constraints; push strategic variety)

- **Drought**
  - **Effect**: reduce neutral building tax generation for 90s
  - **Counterplay**: diversify economy / clear lairs for stash payouts

- **Fog Night**
  - **Effect**: reduce vision radius / increase fog opacity for 60s (future)
  - **Counterplay**: keep heroes near castle; use guardhouse/ballista

---

## P1 event set (requires a bit more plumbing)

- **Plague**
  - **Effect**: heroes heal slower; inn becomes higher priority / more valuable
  - **Needs**: a generalized “status modifier” system or per-hero regen logic

- **Religious Holiday**
  - **Effect**: temple buildings generate periodic small buffs or gold
  - **Needs**: temple-specific logic + buff framework usage

---

## Determinism / MP-readiness checklist

- Events scheduled off **sim time** (accumulated `dt`) not wall clock.
- All randomness derived from a single seeded RNG stream.
- Event outcomes depend only on sim state + scheduled time, not on UI input timing.



