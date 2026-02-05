# Studio Gateway (Autonomous AI Studio Runtime)

This repo includes a **Studio Gateway**: a lightweight, always-on style control plane that can run the **AI Studio** workflow autonomously (Agent 01 orchestrates multi-round sprints, runs QA gates, and can integrate/ship when configured).

It is designed to mirror the operating model documented in:

- `.cursor/plans/ai_studio_infrastructure_progress.md`
- `.cursor/plans/studio-agent-cards_c3880ea5.plan.md`

## What you get (MVP)

- **Control plane state** stored on disk (JSON) and an **append-only event stream** (JSONL)\n- A deterministic **R0–R5** sprint loop (at least 5 rounds)\n- **QA gate execution** using your existing gate command(s) (default: `python tools/qa_smoke.py --quick`)\n- A minimal hook surface to attach automation at `sprint_start`, `round_start`, `round_done`, `gate_done`, `release_ready`\n+
## Storage / artifacts

Runtime state is stored under `.studio_gateway/` (gitignored):

- `.studio_gateway/state.json` — canonical state (sprints, rounds, gate results)\n- `.studio_gateway/events.jsonl` — event stream\n- `.studio_gateway/artifacts/<sprint_id>/...` — captured stdout/stderr for gates\n+
## CLI usage

From repo root:

```bash
# Initialize the state store\n+python -m studio_gateway init\n+\n+# View status\n+python -m studio_gateway status\n+\n+# Create a sprint\n+python -m studio_gateway sprint create wk8_demo --title \"Week 8 Demo\"\n+\n+# Run through R0..R5\n+python -m studio_gateway sprint run wk8_demo\n+\n+# View recent events\n+python -m studio_gateway events --tail 100\n+```\n+\n+## Operator notes / recovery\n+\n+- If a gate fails, check the recorded stdout/stderr in `.studio_gateway/artifacts/<sprint_id>/gates/<gate_id>/`.\n+- To “reset” local Studio Gateway state, you can delete `.studio_gateway/` (it’s generated).\n+- If you want to keep historical runs, archive `.studio_gateway/` somewhere else.\n+
