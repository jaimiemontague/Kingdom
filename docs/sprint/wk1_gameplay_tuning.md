## WK1 Gameplay Tuning (Agent 5: GameplaySystemsDesigner)

### Goals (this week)
- **Bounties feel like a real lever** (clear cost tiers; lair bounties actually cause lair clearing).
- **Early game feels alive but not lethal** (lairs pressure you, but you can stabilize).
- **Lair bounties make sense vs stash payout** (clearing a lair is a satisfying “chapter beat”).

---

## Bounty reward bands (early game)

These are **player-paid** rewards (cost == reward). Suggested defaults:

| Tier | How to place | Reward (gold) | When to use |
|---|---:|---:|---|
| Low | `B` | **25** | scouting / nudging a nearby hero |
| Medium | `Shift+B` | **60** | redirecting a hero away from distractions |
| High | `Ctrl+B` | **150** | “drop everything” / risky objectives |

### Lair bounty
- **Default lair bounty**: **90** (`LAIR_BOUNTY_COST`)
- **Expected total hero payout on clear**: bounty (90) + lair stash (typically 75–200+)  
  This keeps lairs desirable without making bounties mandatory.

---

## Lair stash + pressure sanity

### Stash growth
- `LAIR_STASH_GROWTH_PER_SPAWN`: **8** (was 6)
- Baseline initial stashes increased so clearing feels rewarding even if you clear “early”.

### Spawn pressure
- Slightly slower lair spawn intervals (still active, less “instant cap to 20 enemies”).

---

## Economy baseline

- `STARTING_GOLD`: **1500** (was 10000)  
  Enough for early building choices, but now gold decisions (guild vs market vs defense vs bounties) actually matter.

---

## Notes / follow-ups (later, not required for wk1)
- Consider a simple UI affordance for bounties (small selector / wheel) once Build B is stable.
- Consider scaling lair bounty cost with lair `threat_level` once we have threat surfaced in UI.



