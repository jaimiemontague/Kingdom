# Kingdom Sim — Agent Identity & Ownership Contract

This file exists to keep our multi-agent “AI studio” **predictable**.

If an agent is unsure whether a change is “in their lane”, the default is:
**STOP → write a ticket/prompt → hand off to the owning agent.**

---

## Non‑negotiables (apply to everyone)

- **No silent scope expansion**: implement only what’s in the sprint plan / assigned prompt.
- **Gates before claiming done**: if you changed code, run `python tools/qa_smoke.py --quick` (and `python tools/validate_assets.py --report` if assets/manifests changed).
- **UI / visible graphics — screenshot loop**: if the player can see the change, use `python tools/capture_screenshots.py` (or an agreed scenario) to produce PNGs, **inspect** them, and **iterate** (fix → re-capture) until the images show the expected result. See `.cursor/rules/06-workflow-sop.mdc` Phase 4b. Do not mark work complete if the latest capture still looks wrong.
- **Determinism boundary is sacred**: do not introduce wall‑clock time / global RNG inside sim code.
- **PowerShell commands**: all human-facing commands must be Windows PowerShell compatible.
- **Orchestrator receipt + log contract is mandatory**: SDK-launched agents must onboard first, write a valid JSON log entry at `sprints[SPRINT_ID].rounds[ROUND_ID]` in their own agent log, validate it with `python -m json.tool .cursor/plans/agent_logs/agent_NN_YourRole.json`, then run the exact `npx tsx tools\ai_studio_orchestrator\src\cli.ts complete ...` receipt command from their prompt before claiming done. Required log fields: `sprint_id`, `round_id`, `status`, `what_i_changed`, `commands_run`, `evidence`, `blockers`, and `follow_ups` or `recommended_next_actions`.

---

## Agent 01 (PM) — hard boundary

Agent 01 is the **Executive Producer / PM**.

### What Agent 01 MAY edit
- `.cursor/plans/**`
- `.cursor/rules/**`
- `AGENTS.md` (this file)

### What Agent 01 MUST NOT edit
- **Anything in**: `game/**`, `ai/**`, `tools/**`, `assets/**`, `tests/**`, `config.py`, `main.py`, `requirements.txt`

### If Agent 01 finds a bug / needed change
Agent 01 must do **only**:
1. Write a structured ticket (title, repro, expected/actual, acceptance).
2. Write a **handoff prompt** to the owning agent (template below).
3. Provide a **send list + order** (with intelligence recommendations).

If you see Agent 01 proposing code edits, that is a process bug—stop and re-route.

---

## Ownership map (who edits what)

This is the single source of truth for “who touches which directories”.

| Area | Primary owner | Notes |
|---|---|---|
| `game/sim/`, `game/sim_engine.py`, `game/engine.py`, `game/game_commands.py` | **Agent 03** | Architecture, engine contracts, renderer wiring |
| `game/entities/**`, `game/systems/**`, balance & tuning | **Agent 05** | Simulation logic + gameplay systems |
| `ai/**` | **Agent 06** | AI behaviors + LLM providers/prompting |
| `game/ui/**` | **Agent 08** | HUD/panels/menus |
| `game/graphics/**` (2D/3D renderers, sprites, VFX) | **Agent 09** | Visual pipeline; Agent 03 consult for engine contracts |
| `game/audio/**` | **Agent 14** | Audio system + licensing |
| `tools/**`, `tools/assets_manifest.json`, validators, capture tools | **Agent 12** | DevEx + tooling + asset validation |
| `assets/prefabs/**`, 3D kitbashing workflows | **Agent 15** | Prefab JSON authoring via assembler; attribution updates as needed |
| QA gates & scenarios | **Agent 11** | `tools/qa_smoke.py`, `tools/observe_sync.py`, QA assertions |
| Performance consult | **Agent 10** | Benchmarking + perf overlay guidance |
| Steam ops / patch notes | **Agent 13** | CHANGELOG-derived player-facing comms |

If a change crosses domains, the implementer must:
- keep it **minimal**, and
- flag it to the primary owner for review in the report-out.

---

## Standard handoff prompt template (PM → implementer)

Use this exact structure in Agent 01 prompts.

```text
Task: <1 sentence outcome, player-facing if possible>

Scope:
- In scope: <bullets>
- Out of scope: <bullets>

Files you MAY edit:
- <paths>

Files you MUST NOT edit:
- <paths>

Acceptance:
- <observable pass/fail bullets>

Commands (from repo root, PowerShell):
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report  # only if assets/manifests changed

Report back with:
- Files touched
- Commands run + exit codes
- Agent log path + sprint/round entry written
- Any follow-ups / risks
```

---

## Escalation / coordination rules

- If you need another agent’s change first: mark yourself **blocked** and state exactly what you’re waiting on.
- If you discover extra work: file it as a **new ticket**; do not “just do it” unless you are the owner and it is required to keep gates green.


---

## Cursor Cloud specific instructions

### Environment

- **Python 3.13** is installed via deadsnakes PPA; the venv lives at `/workspace/.venv`.
- Activate with: `source /workspace/.venv/bin/activate`
- **Ursina** (Panda3D-based 3D engine) is installed but **not** in `requirements.txt`. The update script installs it separately.
- **No audio hardware** — ALSA/PulseAudio warnings are expected and harmless. The game falls back to `NullAudioManager`.

### Display

- A virtual framebuffer (`Xvfb :99`) must be running for any pygame or Ursina rendering.
- Start it: `Xvfb :99 -screen 0 1920x1080x24 &`
- Set: `export DISPLAY=:99`
- The headless QA tools (`observe_sync.py`, `qa_smoke.py`) use `SDL_VIDEODRIVER=dummy` internally so they work even without Xvfb, but interactive/capture runs and `capture_screenshots.py` need the display.

### Running the game

- **2D pygame** (used for screenshots/captures/headless testing): `python main.py --renderer pygame --no-llm`
- **3D Ursina** (default renderer): `python main.py --no-llm`
- Both work on DISPLAY=:99. Use `--no-llm` or `--provider mock` to avoid needing API keys.

### Key commands (from repo root)

| Task | Command |
|------|---------|
| QA smoke (mandatory gate) | `python tools/qa_smoke.py --quick` |
| Determinism guard | `python tools/determinism_guard.py` |
| Asset validation | `python tools/validate_assets.py --report` |
| Unit tests | `python -m pytest tests/ -q` |
| Capture screenshots | `python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/verify --size 1920x1080 --ticks 120` |
| Headless observer | `python tools/observe_sync.py --seconds 10 --heroes 5 --seed 3 --log-every 120 --realtime --bounty` |

### Gotchas

- An archived test file at `tools/archive/root_wk40_stage5/test_llm.py` requires `OPENAI_API_KEY` at import time. Run `pytest tests/` (not `pytest` from root) to avoid collection errors.
- The game window is 1920x1080 borderless by default. Ensure Xvfb screen is at least that size.
- LLM API keys are **optional** — the game is fully functional with `--no-llm` or `--provider mock`.
