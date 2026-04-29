# AI Studio Automation Contract

This contract defines the machine-readable layer used by the Cursor SDK sprint
orchestrator. It preserves the current PM hub workflow: Agent 01 plans and
decides, worker agents write only their own logs, and Jaimie is prompted only
for explicit human gates.

## Source Of Truth

- PM hub: `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`
- Agent logs: `.cursor/plans/agent_logs/agent_NN_*.json`
- Role boundaries: `AGENTS.md` and `.cursor/rules/`
- Orchestrator: `tools/ai_studio_orchestrator/`

The PM hub remains authoritative. The orchestrator may read it, launch agents
from it, and write generated ledgers/dashboard files, but Agent 01 remains the
only owner of PM decisions.

## Agent 01 Lifecycle Modes

The orchestrator is designed to support Jaimie's existing Agent 01 workflow:

1. **Plan sprint** — Agent 01 clarifies features, pushes back on scope, writes a robust sprint plan, and reasons through implementation details for less-capable downstream agents.
2. **Kick off sprint** — Agent 01 updates the PM hub with per-agent prompts, send order, automation DAG, human gates, and a universal prompt.
3. **Review / continue / close sprint** — Agent 01 reads worker logs and ledgers, decides whether to continue, create a follow-up round, stop for human playtest, or close the sprint.

Automation should not bypass these modes. It should remove manual copy/paste and status polling while keeping Agent 01 as the source of PM decisions.

## Round Automation Block

Each sprint round may include an optional `automation` object:

```json
{
  "automation": {
    "mode": "manual | assist | auto_until_human_gate",
    "runnable_agents": ["03", "05", "11"],
    "dependencies": [
      { "id": "wave1", "agents": ["03", "05"], "parallel": true },
      { "id": "qa", "after": ["wave1"], "agents": ["11"] }
    ],
    "human_gates": ["manual_playtest", "visual_approval", "version_bump", "commit", "push"],
    "success_signals": {
      "required_log_entries": true,
      "required_exit_codes": [0],
      "required_gates": ["python tools/qa_smoke.py --quick"]
    },
    "failure_policy": {
      "retry_limit": 0,
      "on_failure": "stop_for_pm"
    },
    "model_policy": {
      "required_model": "composer-2",
      "allow_overrides": false
    }
  }
}
```

If `automation` is absent, the orchestrator derives a v1 DAG from
`pm_send_list_minimal` using these fields in order:

1. `waves`
2. `batch_1_parallel` then `then_in_order`
3. `then_in_order`
4. keys in `pm_agent_prompts`

## Model Policy

All automated agents and subagents must use Composer 2 unless Jaimie explicitly
approves a one-run exception in the PM hub.

- SDK agents are created with `model: { id: "composer-2" }`.
- Per-run model overrides are rejected unless `automation.model_policy` allows
  them and includes human approval.
- Inline SDK subagents must inherit from a Composer 2 parent or explicitly use
  Composer 2.
- File-based subagents created for automation must use `model: inherit` and
  must not request higher-cost model changes.
- The run ledger records the resolved model for each run.

The PM's `high`, `medium`, and `low` intelligence tags remain required, but in
automated mode they affect risk handling and review strictness, not model cost.

## Human Gates

The orchestrator must stop before:

- manual gameplay/playtest requests
- visual approval of art, models, screenshots, or animation
- version bump or changelog publication
- git commit or push
- any failed QA gate
- any non-Composer model resolution without approval

When stopped, the orchestrator prints exact PowerShell commands for Jaimie if a
manual test is required.

## Worker Completion

A worker wave is complete only when:

- every required SDK run finishes with status `finished`
- each required worker writes a token-checked completion receipt
- the Composer 2 log-reader/verifier writes a verification receipt with status
  `verified`
- required gates mentioned in the prompt are reported by the worker or are run
  later by Agent 11

The orchestrator treats worker final text as advisory. Completion receipts drive
handoff. Agent logs and gate evidence remain the durable audit record.

## Completion Receipts

Every worker prompt includes an exact command:

```powershell
npx tsx tools\ai_studio_orchestrator\src\cli.ts complete --token <RUN_TOKEN> ...
```

The worker must run it after updating its own log and before final response.

The orchestrator rejects receipts with the wrong token, sprint, round, or agent.
Old receipts cannot advance a new wave.

## Verifier Receipts

After a completion receipt appears, the orchestrator launches a Composer 2
log-reader/verifier agent. The verifier reads the receipt and claimed log, then
writes a verification receipt:

- `verified` — proceed to the next wave
- `needs_log_repair` — route a focused repair task to the same worker or stop for PM
- `needs_pm` — worker is blocked; ask Agent 01
- `failed` — gate/work failed; ask Agent 01

## PM Feedback Loop

After each wave, the orchestrator may launch Agent 01 with a synthesis prompt:

1. Read completed agent logs for the sprint/round.
2. Update the PM hub with decisions, blockers, bug tickets, and next waves.
3. Decide whether to continue, retry, escalate, or pause for Jaimie.

Workers do not directly edit Agent 01's PM hub unless their role explicitly is
Agent 01. Cross-agent requests must be recorded as `questions_back_to_pm`,
`dependencies`, `blockers`, or `recommended_next_actions` in the worker log.

When the orchestrator prompts Agent 01 after a worker wave, the prompt should include:

- the sprint and round ids
- the ledger path
- completed agents
- failed log validations or gate failures
- human feedback, if any
- an instruction to create a follow-up round instead of implementing code directly

Agent 01 must not mark a sprint complete until automated gates and required human gates are satisfied.

## Ledger And Dashboard

Generated run state belongs under:

- `tools/ai_studio_orchestrator/runs/*.json`
- `tools/ai_studio_orchestrator/runs/dashboard.md`

These files are generated and are ignored by git. The ledger records sprint,
round, runtime, model, agent IDs, run IDs, status, duration, and stop reasons.
