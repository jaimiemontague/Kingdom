# AI Studio Orchestrator

TypeScript CLI for routing Kingdom Sim AI Studio sprints through the Cursor SDK.
It reads the PM hub, launches the selected agents, records a run ledger, and
stops at human gates.

## Setup

From this folder:

```powershell
npm install
$env:CURSOR_API_KEY = "crsr_..."
```

All orchestrated agents use Composer 2. The CLI rejects model overrides unless a
future human-approved exception path is added.

Every launched agent is instructed to onboard first, write a valid JSON log entry,
and then run a tokenized `complete` command. The completion receipt triggers the
orchestrator to launch a Composer 2 log-reader/verifier agent. The required log
entry is:

```text
.cursor/plans/agent_logs/agent_NN_YourRole.json
→ sprints[SPRINT_ID].rounds[ROUND_ID]
```

If verification returns `needs_log_repair`, have that same agent repair its own
log. Do not manually patch another agent's log except as a deliberate human
recovery action.

## Commands

Dry-run a sprint round without launching SDK agents:

```powershell
npm run studio -- validate --sprint wk46-stage3-lumberjack-builders --round wk46_r0_kickoff
npm run studio -- run --sprint wk46-stage3-lumberjack-builders --round wk46_r0_kickoff --dry-run
```

Launch a specific agent locally:

```powershell
npm run studio -- run --sprint wk46-stage3-lumberjack-builders --round wk46_r0_kickoff --agents 11 --mode assist
```

Show the latest ledger and write a dashboard:

```powershell
npm run studio -- status --write-dashboard
```

### Multiple rounds in one go (chain)

The CLI accepts one `--round` per `run`. To run several rounds back-to-back (e.g. WK47 R2b then R3), from repo root:

```powershell
$env:CURSOR_API_KEY = "crsr_..."
.\tools\ai_studio_orchestrator\run_remaining_rounds.ps1
```

Defaults: sprint `wk47_unit_instancing_core`, rounds `wk47_r2b_sync_integration` then `wk47_r3_validation`. Override: `-Sprint <id> -Rounds @('round_a','round_b')`.

Prompt Agent 01 to synthesize a completed wave:

```powershell
npm run studio -- synthesize --ledger runs/<ledger>.json --mode assist
```

Workers receive a command shaped like:

```powershell
npx tsx "tools\ai_studio_orchestrator\src\cli.ts" complete --cwd "<repo>" --sprint "<sprint>" --round "<round>" --agent "09" --token "<token>" --status done --summary "..."
```

## Human Gates

The orchestrator stops before manual playtests, visual approvals, version bumps,
git commits, git pushes, failed QA gates, and non-Composer model resolution.

## Receipt And Log Verification

After a completion receipt, the verifier checks:

- receipt token, sprint, round, and agent match the active wave
- agent log file exists
- JSON parses
- `sprints[SPRINT_ID].rounds[ROUND_ID]` exists
- round object contains `sprint_id`, `round_id`, `status`, `what_i_changed`,
  `commands_run` or `how_to_test`, `evidence`, `blockers`, and `follow_ups` or
  `recommended_next_actions`

The ledger prints the exact reason when verification returns `needs_log_repair`,
`needs_pm`, or `failed`.
