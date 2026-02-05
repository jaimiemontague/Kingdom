# Studio Gateway (Autonomous AI Studio Runtime)

This repo includes a **Studio Gateway**: a lightweight, always-on style control plane that can run the **AI Studio** workflow autonomously (Agent 01 orchestrates multi-round sprints, runs QA gates, and can integrate/ship when configured).

It is designed to mirror the operating model documented in:

- `.cursor/plans/ai_studio_infrastructure_progress.md`
- `.cursor/plans/studio-agent-cards_c3880ea5.plan.md`

## What you get (MVP)

- **Control plane state** stored on disk (JSON) and an **append-only event stream** (JSONL)
- A deterministic **R0–R5** sprint loop (at least 5 rounds)
- **QA gate execution** using your existing gate command(s) (default: `python tools/qa_smoke.py --quick`)
- A minimal hook surface to attach automation at `sprint_start`, `round_start`, `round_done`, `gate_done`, `release_ready`

## Web UI (recommended)

Start the local server, then open the dashboard in your browser.

```bash
python -m studio_gateway init
python -m studio_gateway serve --host 127.0.0.1 --port 18790
```

Then open `http://127.0.0.1:18790/`.

### Providing sprint instructions (the “Brief”)

In the Web UI:

- Pick a sprint in the dropdown
- Fill out **Sprint brief / instructions**
- (Optional) select **Active agents** and sprint overrides
- Click **Save sprint instructions**

Those values are saved into the sprint record under `meta` and are included in Agent 01’s Round 1 prompts.

## Storage / artifacts

Runtime state is stored under `.studio_gateway/` (gitignored):

- `.studio_gateway/state.json` — canonical state (sprints, rounds, gate results)
- `.studio_gateway/events.jsonl` — event stream
- `.studio_gateway/artifacts/<sprint_id>/...` — captured stdout/stderr for gates

The Web UI uses an auth token stored in `.studio_gateway/config.json` (gitignored). In the UI, paste it into the **Token** field.

To view your token quickly:

```bash
python -c "import json; print(json.load(open('.studio_gateway/config.json','r'))['auth_token'])"
```

## CLI usage

From repo root:

```bash
# Initialize the state store
python -m studio_gateway init

# View status
python -m studio_gateway status

# Create a sprint
python -m studio_gateway sprint create wk8_demo --title "Week 8 Demo"

# Run through R0..R5
python -m studio_gateway sprint run wk8_demo

# View recent events
python -m studio_gateway events --tail 100
```

## Operator notes / recovery

- If a gate fails, check the recorded stdout/stderr in `.studio_gateway/artifacts/<sprint_id>/gates/<gate_id>/`.
- To “reset” local Studio Gateway state, you can delete `.studio_gateway/` (it’s generated).
- If you want to keep historical runs, archive `.studio_gateway/` somewhere else.

### UI glossary

- **Sprints dropdown**: your saved sprint records.
- **Events**: the Studio Gateway event log (round start/end, gates, errors).
- **Tail**: how many recent events to fetch.
- **Poll**: fetch events now (use Auto-poll to refresh every ~2s).
