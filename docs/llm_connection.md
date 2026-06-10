# LLM Connection Guide (WK134)

How to hook a real LLM up to Kingdom Sim's heroes, what they will and won't
obey, and how to smoke-test the whole pipe in two minutes.

## 1. Picking a provider

The provider is chosen by `.env` (loaded by `config.py`) or the command line:

```
# .env
LLM_PROVIDER=claude        # openai | claude | gemini | grok | mock
```

```powershell
# Command line override (wins over .env)
python main.py --provider claude
python main.py --provider mock     # no API key needed
python main.py --no-llm            # deterministic heuristic AI only
```

### API keys and models (env vars, all read from `.env`)

| Provider | Key env var | Model env var | Default model |
|---|---|---|---|
| openai | `OPENAI_API_KEY` | `OPENAI_MODEL` | `gpt-4o-mini` |
| claude | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` (new, WK134) | `claude-sonnet-4-6` |
| gemini | `GEMINI_API_KEY` | — | provider default |
| grok | `GROK_API_KEY` | — | provider default |
| mock | none | — | rule-based, deterministic |

`ANTHROPIC_MODEL` examples: `claude-haiku-4-5` (cheapest), `claude-sonnet-4-6`
(default — best speed/cost for short per-hero decisions), `claude-opus-4-8`
(smartest). Use the bare alias strings, no date suffixes.

### Loud fallback (WK134)

If the requested provider can't be used (bad name, missing API key, missing
package, init error), the game **falls back to the mock provider loudly**:

- one `WARNING: LLM provider '<name>' unavailable ... falling back to MOCK`
  line on the console at startup, and
- one orange HUD toast in-game ("LLM provider 'claude' unavailable — using
  mock AI"), and
- `LLMBrain.provider_fallback` / `provider_fallback_reason` flags readable by
  UI/debug tools.

If you expected real-LLM behavior and see that toast, check your `.env` key.

## 2. What heroes WILL obey in chat

Select a hero, open the chat panel, and type plain English. The hero's LLM
reply is validated before anything physical happens; these commands execute:

- **Go somewhere they know**: "go to the inn / castle / market / blacksmith",
  "go home". Heroes only know places they've discovered (their memory), so a
  fresh hero may honestly refuse "go to the blacksmith".
- **Explore a compass direction**: "explore north/south/east/west" (also
  NE/NW/SE/SW). They scout ~10 tiles that way.
- **Buy potions**: "buy potions" — buys immediately if at the market with
  coin, otherwise marches to a known market first. Refuses with no market
  known or no gold.
- **Heal**: "I need healing" — drinks a potion if carrying one and hurt,
  otherwise retreats toward home/castle/inn.
- **Rest**: "rest until healed".
- **Leave the building**: "leave the building".
- **Status**: "how are you?" — talk only, no action.

## 3. What heroes will NOT obey

- **Combat orders by chat**: "attack the lair", "fight that ogre" → polite
  Defy (`mvp_combat_deferred`). Use the bounty system (the Majesty lever) to
  direct violence.
- **Unknown places / invented targets**: validated against the hero's known
  places; unknown → in-character refusal, no movement.
- **Raw coordinates**: any coordinate-like fields from the LLM are stripped;
  destinations resolve only through known places and compass headings.
- **Accepting bounties by chat**: `accept_bounty` is an autonomous-only
  decision (see below) — the Sovereign nudges with bounty gold, not orders.

Every refusal still produces a spoken in-character reply in the chat panel
(`Defy` + a refusal reason), so silence = bug, refusal = working as designed.

## 4. Autonomous decisions (no chat needed)

Heroes consult the LLM at five "decision moments" (low-health combat,
post-combat injured, rested-and-ready, shopping opportunity, idle-seeking-
activity) plus the quest-offer moment. Notable behaviors:

- **accept_bounty** (wired for real in WK134): an idle hero offered
  `accept_bounty` commits to the best/nearest valid bounty via the same
  pursuit path the heuristic AI uses; if no valid bounty exists it degrades
  to exploring (logged, no crash).
- **Quest offers** (WK126/133): idle heroes *occasionally* walk to an open
  quest-giver. At the NPC the LLM decides accept/decline (the prompt carries
  quest type, target, reward, distance). Decline puts that giver on a
  **15-sim-minute per-hero cooldown**; accept points the hero at the
  objective. With `--no-llm` the verdict is a deterministic accept. The mock
  provider accepts quests rewarding >= 50g and declines stingier offers.
- Prompts include the hero's full inventory (weapon/armor/accessory/backpack),
  nearby POIs ("Forgotten Shrine (shrine, tier 2), 12 tiles NE"), known
  places, and recent memory.

## 5. Known limits

- **Timeouts**: decision calls get `LLM_TIMEOUT` = 5s, chat gets
  `CONVERSATION_TIMEOUT` = 8s. A slow/failed call falls back to a safe
  deterministic decision (`source="fallback"`); chat falls back to an
  in-character "I'm at a loss for words" line. A hung provider can never
  wedge a hero: a pending request is abandoned after ~20 sim-seconds
  (WK134 watchdog) and the hero resumes consulting normally.
- **Mock mode** is rule-based and deterministic — great for testing plumbing,
  not for personality. It only understands the phrasings listed above.
- One decision request per hero at a time; decisions are rate-limited by
  per-moment cooldowns (4–15s), so chat replies can lag a second or two.
- LLM output is advisory: everything is validated against allowlists before
  touching the sim, so a hallucinating model degrades to safe behavior.

## 6. Two-minute smoke procedure

1. `python main.py --provider mock` (no key needed; use `--renderer pygame`
   if the 3D viewer isn't set up).
2. Wait for a hero to spawn, click them to select, open chat.
3. Type `go explore north` → the hero should answer in character and start
   walking north (watch the minimap/intent label: `moving_to_destination`).
4. Type `how are you?` → status reply, no movement.
5. Type `attack the lair` → polite refusal (Defy), no movement.
6. Swap to a real provider (`.env`: `LLM_PROVIDER=claude` +
   `ANTHROPIC_API_KEY=...`), relaunch, repeat 3–5. If you see the orange
   "using mock AI" toast, the key/package isn't right.

Headless equivalents:

```powershell
python tools/qa_smoke.py --quick
python -m pytest tests/test_wk134_llm_e2e.py -q
```
