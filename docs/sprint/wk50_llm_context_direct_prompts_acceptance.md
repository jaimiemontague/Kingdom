# WK50 — LLM decision moments & direct prompts — Player-facing acceptance

**Sprint:** `wk50_llm_context_direct_prompts`  
**Owner:** Agent 02 (GameDirector / Product)  
**Plan:** `.cursor/plans/wk50_llm_context_direct_prompts_396eb5fa.plan.md`

This checklist defines **what the player must observe** after Phase **2A** (autonomous LLM decision moments) and Phase **2B** (direct prompt commands). Engineering owns validators, prompts, and routing; this doc is the **feel + observable behavior** contract.

---

## Product pillars for this sprint

1. **Rare, meaningful LLM** — Heroes are not “chatty brains.” Consultations happen at named decision moments, not every routine AI tick.
2. **Indirect control preserved** — Plain English can *suggest* outcomes; **deterministic game code** validates and executes movement or commerce. The Sovereign does not puppet raw coordinates or invent systems through dialogue.
3. **Person-like obedience** — For **supported, safe** requests the hero **usually complies** (movement/healing/rest/shopping/explore/status). For **unsafe, impossible, or out-of-scope** requests the hero **refuses or redirects in character**, without hallucinating attacks, quests, or new rules.

---

## Scope reminder

**In MVP**

- Phase 2A: Named decision moments (e.g. low-health combat, post-combat injured, rested-and-ready; shopping optional per plan) with bounded profile/tactical context.
- Phase 2B: Safe core intents only: `status_report`, `return_home`, `seek_healing`, `go_to_known_place`, `buy_potions`, `explore_direction`, `rest_until_healed`, `no_action_chat_only`.

**Explicitly out of MVP (must not ship as reliable player commands)**

- Attack lair / attack nearest enemy / bounty-by-chat / escort-follow-protect / emotional-driven behavior shifts / quests / relationships / LLM-authored rules or memories.

---

## Environment

- Manual verification with LLM disabled path where applicable: `--no-llm` or `--provider mock` per QA plan.
- When testing LLM-facing behavior, use **`python main.py --provider mock`** so scenarios stay reproducible (Agent 11 owns automated prompt/mock coverage).

---

## Phase 2A — Autonomous decision moments (player-observable)

### Feel gates

| # | Criterion | Pass |
|---|-----------|------|
| A-F1 | During an ordinary session (several minutes), the player **does not** perceive heroes pausing constantly for “thinking” or spamming advisory chatter tied to LLM. Moments feel **occasional**, tied to tension or recovery—not background noise. | Yes |
| A-F2 | When a consultation **does** occur, the hero’s subsequent behavior reads as a **meaningful fork** (fight vs flee vs potion; where to go after injury; what to do when rested)—not indistinguishable from default wandering. | Yes |
| A-F3 | If the LLM is unavailable or returns garbage, behavior **degrades gracefully**: fallback AI keeps the hero playable without crashes or illegal actions (no teleport-invented destinations). | Yes |

### Moment-aligned expectations (high level)

| # | Criterion | Pass |
|---|-----------|------|
| A-M1 | **Low-health combat**: Hero under threat may choose among outcomes consistent with survival tension (e.g. continue fighting, retreat, use potion when allowed)—player can tell *something* weighted happened, not random jitter every frame. | Yes |
| A-M2 | **Post-combat injured**: Injured heroes bias toward recovery-related behaviors (safety, supplies, exploration when appropriate)—readable “wounded hero making a plan.” | Yes |
| A-M3 | **Rested and ready**: After meaningful recovery in safety, heroes resume purposeful activity rather than idle loops—aligned with plan’s allowed actions for that moment. | Yes |

*(Shopping moment, if shipped: visible only when near relevant commerce with real purchase pressure—not perpetual shop chatter.)*

### Negative acceptance (must not happen)

| # | Criterion | Pass |
|---|-----------|------|
| A-N1 | No observable **LLM call spam** (many consultations per hero per minute without cooldown/equivalent gating). | Yes |
| A-N2 | Heroes do **not** narrate full dungeon-master prose every tick; autonomous output stays **action-oriented** after validation (player cares what they *do*, not a novel). | Yes |

---

## Phase 2B — Direct prompt commands (player-observable)

### Sovereign interaction feel

| # | Criterion | Pass |
|---|-----------|------|
| B-F1 | Chat still reads as **conversation with a subject**, not a cheat console: responses are **in character**, including obey/defy framing where applicable. | Yes |
| B-F2 | When the Sovereign asks something **supported and feasible**, the hero **usually** carries out the intent (movement/commerce/heal/rest/explore) after validation—not silent no-ops without explanation. | Yes |
| B-F3 | When the request is **unsupported** (e.g. “attack the lair”), the hero **does not** execute combat directives as if MVP supported them; reply clarifies limitation or defers **without inventing combat**. | Yes |
| B-F4 | When the request is **unsafe or impossible** (e.g. cross-map trek while critically wounded; unknown place name; broke at shop), the hero **refuses or redirects** with an understandable reason—still feels like a person, not a generic error string. | Yes |

### Command spot-checks (manual or scripted mock)

Use hero chat as described in the sprint plan (Agent 11 expands pytest/mock scenarios).

| Player says (examples) | Pass behavior |
|------------------------|----------------|
| “How are you?” / status-style prompt | **Spoken/status response** without mandatory movement (`status_report` path); no fake combat or quests. |
| “Go home” / return to safety | **Movement toward known home/safety** when resolvable and safe enough; otherwise **in-character refusal/redirect**. |
| “Heal up” / seek healing | **Potion use or movement toward healing/safety** consistent with supplies and HP policy—not suicidal cross-country hikes when critical. |
| “Buy potions” | **Shop path**: move toward known commerce when needed; **buy** when affordable and rules allow; otherwise explains **no gold / no shop / cannot**. |
| “Go to the inn” (or other **known** place) | **Move_to** only when place resolves from hero knowledge; **no invented landmarks**. |
| “Explore east” | **Deterministic bounded explore** in requested direction—not arbitrary coordinates from LLM prose. |
| “Attack the lair” / kill-focused orders | **No MVP combat execution** from chat; **refusal / deferral** in character without hallucinating success. |

### Negative acceptance (must not happen)

| # | Criterion | Pass |
|---|-----------|------|
| B-N1 | Chat never causes **instant teleport**, **spawn items**, **rewrite memory**, or **new game rules** from prose alone. | Yes |
| B-N2 | Unsupported intents map to **`no_action_chat_only`** or explicit refusal—not silent application of random `tool_action`. | Yes |
| B-N3 | LLM-chosen targets that fail validation do **not** apply as physics; player sees stable fallback (stay put, safer intent, or deterministic fallback behavior). | Yes |

---

## Cross-phase regression (Majesty feel)

| # | Criterion | Pass |
|---|-----------|------|
| R1 | Player still primarily steers via **economy, buildings, incentives**—heroes remain **agents**, not RTS units with chat micromanagement every tick. | Yes |
| R2 | `--provider mock` and `--no-llm` paths remain **stable** for extended smoke (see sprint QA gates). | Yes |

---

## Verification ownership

- **Automated:** Agent 11 — decision moment triggers, prompt content, mock conversation paths, invalid output handling (`pytest`, `qa_smoke`, assets when touched).
- **Product sign-off:** Agent 02 — this checklist is updated if scope shifts; disputes escalate to Agent 01.

---

## Revision

| Round | Agent | Notes |
|-------|-------|-------|
| `wk50_r1_design_guardrails` | 02 | Initial player-facing acceptance for Phase 2A + 2B MVP safe-core scope. |
