# Dynamic Quests — Design Notes

**Status:** Concept / north-star (not a committed sprint spec)  
**Context:** Kingdom Sim — indirect control, hero autonomy, optional LLM dialogue, bounties and world systems as levers.

---

## What we mean by “dynamic quest”

A **dynamic quest** is a player-facing goal that **emerges from simulation state** during a run, rather than being picked from a fixed quest board at session start. The quest has:

- **A trigger** — something observable happened (combat outcome, building state, hero state, POI interaction, timer, economy threshold).
- **Stakes tied to the world** — a named hero, a place, a resource, or a failure condition that can worsen or resolve without a designer-authored script for every branch.
- **Resolution paths that heroes can pursue** — aligned with indirect control: the player sets incentives (bounties, gold, buildings, chat nudges); heroes decide tactics and timing.

Dynamic quests are **not** “more random events.” They are **consequences + readable hooks** so the player can answer: *Why does this goal exist now? Who cares? What happens if I ignore it?*

---

## Design pillars alignment

| Pillar | How dynamic quests should behave |
|--------|----------------------------------|
| **Indirect control** | The player does not order “go save X.” They influence: bounties, rewards, who gets gold, dialogue that frames priorities. Heroes choose to form a party, split, or ignore. |
| **Readable incentives** | The UI or narrative layer should surface *why* this quest exists (trapped warrior, tower curse, timer). Avoid opaque “quest ID 7 activated.” |
| **Emergence** | Outcomes come from systems (pathing, combat, AI policy, economy) interacting, not from a single cinematic script — while still allowing authored *templates* for quality. |

---

## Relationship to existing systems (today vs later)

**Today (conceptual hooks):**

- **Bounties** — closest analog: player-placed goals with rewards; heroes respond by policy + scoring.
- **Scenarios / pacing** — scripted nudges (e.g., early tips, auto-bounties) are *semi-dynamic* (time-based), not fully consequence-driven.
- **LLM / chat** — natural language layer for persuasion, information, and tone; must stay **non-authoritative** for sim-critical facts unless tightly grounded in state.

**Later (if pursued):**

- **POI types** with interaction contracts (e.g., “cursed structure,” “prison,” “lair”) that emit **world events** into a small quest ledger.
- **Quest templates** — data-driven patterns: trigger conditions + suggested bounty copy + failure escalations + cleanup rules.
- **Party / coordination** — heroes temporarily align targets; needs clear sim rules so it stays deterministic and testable.

---

## Example: Evil wizard’s tower (Gemini seed, expanded)

### Setup

- A **POI**: *Evil Wizard’s Tower* — dangerous region or building class on the map (fog-adjacent is fine for Majesty-like exploration tension).
- A **warrior** enters or assaults the tower (player bounty, curiosity, or AI “Journey” behavior). The tower’s **defense / spell effect** resolves: the warrior is not killed but **trapped** (new status: `imprisoned_at` + `tower_id`, or similar).

### Emergence

1. **Trigger:** Imprisonment event fires; a **dynamic quest record** is created: *“Free [Warrior] from the Wizard’s Tower.”*
2. **Player knowledge:** HUD or hero panel shows the warrior as *trapped* / unreachable; map may mark tower as special once known.
3. **Social layer:** The player opens chat with **another hero** (e.g., a wizard or rogue). Dialogue is grounded: *“[Warrior] never came back from the tower.”* The LLM must not invent facts; the client injects structured state (names, place, status).
4. **Hero decision:** The second hero’s AI evaluates rescue as attractive if bounty/reward/relationship/faction rules support it — or refuses if cowardly, busy, or underpaid.
5. **Party formation (optional stretch):** A second hero **coordinates** with a third (same tick cadence, not free-form multiplayer): shared target tile, shared bounty claim, or temporary “squad intent” so pathing and combat don’t fight each other.
6. **Resolution branches:**  
   - **Success:** Tower cleared or trap dispelled; warrior returns to normal AI.  
   - **Partial:** Another hero dies; warrior still trapped — quest persists, stakes rise.  
   - **Ignore:** Escalation (warrior’s health decay, tower spawns reinforcements) *only if* tuned to be fair and readable.

### Why this is a good *example*

- It ties **place + hero state + social persuasion** together.
- It showcases **emergent narrative** without requiring a linear campaign.
- It stresses **acceptance criteria** for any implementation: determinism, headless observability, and “no fake quests” (if the warrior is free, the quest must end).

---

## Taxonomy (building blocks)

| Kind | Description | Player lever |
|------|-------------|--------------|
| **Rescue** | Unit stuck, captured, or downed in a location | Bounty at location, gold to hire, chat appeal |
| **Revenge / retaliation** | Entity destroyed → survivors or faction pressure | Auto-bounty or optional ignore |
| **Race** | Another faction marching to claim a thing | Raise reward, build counter, intercept bounty |
| **Escort (soft)** | NPC or hero must survive a route — indirect only | Clear path with buildings/bounties, not click-to-move |
| **Timer pressure** | Siege, ritual, plague meter | Economic spend or hero assignment via incentives |

Each kind should map to **1–3 observable assertions** for QA (e.g., “quest active ⇒ imprisoned unit exists at POI”).

---

## Anti-patterns

- **Script soup:** Hundreds of bespoke branches maintained by hand instead of templates + sim rules.
- **LLM as game master:** Letting the model decide facts not in snapshot (who is trapped, where) — breaks trust and tests.
- **Forced micromanagement:** Any solution that requires direct orders contradicts core fantasy.
- **Silent failure:** Player never learns why a quest appeared or disappeared.

---

## Open questions (for PM / Game Director / Tech)

1. **Authoring:** Who creates POI behaviors — content scenarios only, or new building/lair types?
2. **Quest object:** In-memory event bus vs explicit `Quest` entity in sim — serialization for saves / future MP?
3. **Chat contract:** Structured “quest hints” injected into prompts vs purely freeform player text?
4. **Failure:** Is ignoring a dynamic quest always OK, or do some escalate by design?
5. **UI:** Minimal viable surface — bounty panel only first, or dedicated “Rumors / Situations” strip?

---

## Suggested next step (when this becomes a sprint)

- One **vertical slice**: single POI type + one trap status + bounty auto-suggestion + one headless scenario proving “imprison → rescue completes.”
- **No** full party AI until rescue path is fun with **two heroes** only.

---

## Revision log

| Date | Note |
|------|------|
| 2026-05-12 | Initial write-up: definition, pillars, wizard tower example, taxonomy, risks, open questions. |
