# Quest Archetypes — Design Spec (Content Only)

This document defines **2–3 quest archetypes** that the Remote Exploration / Quest panel system should support. It is a **design specification only** — no implementation. The architecture (QUEST ViewMode, QuestViewPanel placeholder, quest events) is implemented in wk14; this doc describes the content shapes for future implementation.

**Design constraints:** Indirect control (player sets incentives; hero undertakes the quest). Readable narrative beats (travelogue text in the quest panel). Determinism-friendly (sim-time duration, seeded narrative variants). Rewards and failure conditions must map to existing or planned systems (economy, lairs, bounties).

---

## 1. Dungeon Crawl

**Summary:** A hero enters a monster lair, experiences travelogue-style progress through narrative beats, and returns with loot (lair stash + optional flavor rewards).

### Trigger

- Hero accepts or is assigned an **attack_lair** (or equivalent “clear this lair”) objective.
- Optional: player has placed a lair bounty and the hero is the designated responder; entering the lair transitions from “on map” to “quest mode” when the hero crosses the lair entrance.

### Duration

- **Sim-time bound** (e.g. 30–90 seconds of sim time), or **beat-driven**: 3–5 narrative beats, each advancing after a fixed sim interval or on “stage complete” (e.g. lair cleared = final beat).
- No wall-clock; all timing from sim tick / `timebase.now_ms()`.

### Narrative beats (3–5)

1. **Descent** — “{Hero} ventures into the depths of the {lair_type}…”
2. **Encounter** — “The air grows cold. Something stirs in the dark.”
3. **Combat** — “{Hero} fights the lair’s defenders.” (Can be abstract or tied to lair clear event.)
4. **Loot** — “Among the remains, {Hero} finds gold and trinkets.”
5. **Return** — “{Hero} emerges victorious, stash in hand.”

Beats are **text-only** in the QuestViewPanel travelogue area. No new sim systems required for “story”; lair clear and stash payout already exist.

### Reward types

- **Lair stash** — already paid on `lair_cleared` via economy.
- **Optional:** Small bonus gold or flavor “renown” for completing the crawl (tunable; can be zero for first implementation).

### Failure conditions

- **Hero dies** before lair clear → quest fails; emit `QUEST_FAILED` or equivalent; no stash payout.
- **Player recalls hero** → quest abandoned; hero returns with no reward (optional: partial reward if lair was cleared before recall).
- **Timeout** (if duration is sim-time bound) → hero returns without clearing; no stash.

---

## 2. Diplomatic Mission

**Summary:** A hero travels to a “distant settlement” (off-map or abstract location). The player sees text-based encounter beats in the quest panel. Success yields a reputation-style or economic reward.

### Trigger

- **New content hook:** e.g. “Diplomatic bounty” or “Envoy” building/order that assigns a hero to travel to a settlement.
- Alternative: hero chooses “journey” to a procedural “settlement” node when no local bounties are attractive (extends existing journey behavior).

### Duration

- **Sim-time bound** (e.g. 45–120 seconds). Hero is “away”; no on-map movement during quest.
- Beats advance on fixed sim intervals (e.g. every 15–20 seconds) or on scripted transitions.

### Narrative beats (3–5)

1. **Departure** — “{Hero} sets out for the border settlement.”
2. **Arrival** — “{Hero} reaches the outpost. The locals eye the kingdom’s colors.”
3. **Negotiation** — “{Hero} speaks with the elder. Tensions ease.”
4. **Outcome** — “The settlement agrees to trade. Word of the kingdom’s reach spreads.”
5. **Return** — “{Hero} returns with news and a token of goodwill.”

Text can be **seeded** (e.g. from hero name + sim seed) so the same run produces the same flavor; optional pool of variants for replayability.

### Reward types

- **Reputation** — abstract stat or counter (e.g. “Settlement goodwill +1”) for future content (raids, trade events).
- **Gold** — one-time payment from “the settlement” (economy credit).
- **Flavor only** — no mechanical reward in v1; just travelogue and “mission complete.”

### Failure conditions

- **Timeout** — hero returns with “No agreement reached”; no reward.
- **Recall** — player recalls hero; mission abandoned; no reward.
- **Hero death** (if applicable in this mode) — mission failed; no reward.

---

## 3. Bounty Hunt (Remote)

**Summary:** A hero pursues a high-value target “beyond the map edge” (abstract remote zone). Travelogue describes the hunt; success pays gold (bounty reward).

### Trigger

- **Bounty type** “hunt_remote” or a special **slay_enemy** / **hunt_enemy_type** that is marked “remote” (target is off-map or in an abstract “hunt zone”).
- Hero accepts the bounty and transitions to quest mode instead of pathing to an on-map entity.

### Duration

- **Sim-time bound** (e.g. 40–90 seconds). Hero is “away” until success, failure, or recall.

### Narrative beats (3–5)

1. **Pursuit** — “{Hero} follows the trail beyond the border.”
2. **Sighting** — “The quarry is cornered near the old ruins.”
3. **Showdown** — “{Hero} closes in. Steel meets steel.”
4. **Victory** — “The target falls. {Hero} claims the bounty.”
5. **Return** — “{Hero} returns with proof and collects the reward.”

Beats can be **purely time-based** (no sim combat during quest) or **event-based** (e.g. one “combat” tick that resolves success/fail by RNG or fixed outcome for first implementation).

### Reward types

- **Bounty gold** — same as existing bounty claim: `BountySystem` pays the hero (or economy) on success.
- **No stash** — this is a person/target hunt, not a lair; reward is the bounty only.

### Failure conditions

- **Target escapes / hunt fails** — e.g. seeded outcome or timeout; hero returns, bounty unclaimed (or expired).
- **Hero dies** (if remote combat is simulated) — bounty unclaimed; hero returns “defeated” or is removed per normal death rules.
- **Recall** — player recalls hero; bounty abandoned; no reward.

---

## Data contract (for implementers)

When implementing, each archetype can be described by a minimal **quest spec** shape so the panel and events stay consistent:

| Field           | Description |
|----------------|-------------|
| `archetype`    | `"dungeon_crawl"` \| `"diplomatic_mission"` \| `"bounty_hunt_remote"` |
| `hero_id`      | Hero undertaking the quest |
| `trigger_ref`  | Optional: lair_id, bounty_id, or settlement_id |
| `duration_ms`  | Sim-time duration (or null if beat-driven) |
| `beats`        | Ordered list of travelogue strings or beat keys |
| `reward_type`  | `"lair_stash"` \| `"gold"` \| `"reputation"` \| `"bounty"` |
| `failure_conditions` | List: `"death"`, `"recall"`, `"timeout"`, `"target_escape"` |

Events already defined in the architecture: `quest_started`, `quest_completed`, `quest_hero_returned`. Optional: `quest_failed` for failure conditions above.

---

## Alignment with existing systems

- **Lairs:** Dungeon Crawl uses existing lair clear + stash; no new lair types required.
- **Bounties:** Bounty Hunt (Remote) uses existing bounty reward flow; trigger may require a new bounty type or flag.
- **Economy:** All gold rewards go through existing economy; reputation is optional/future.
- **Determinism:** All duration and beat timing must use sim-time and seeded RNG for narrative variants.
