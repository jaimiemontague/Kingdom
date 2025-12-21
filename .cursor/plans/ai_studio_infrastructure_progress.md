### AI Studio / Agents Infrastructure — Progress Log (Kingdom Sim)

**Document purpose**: This is a detailed, “printable” record of what we’ve built so far to operationalize the **AI Studio** (13 department-lead agents) inside Cursor for Kingdom Sim, including planning structure, multi-agent coordination, logging formats, and PM synthesis patterns.

**Audience**: Jaimie (solo dev + studio operator), and future “you” returning after time away.

**Scope**: Infrastructure and process only (not gameplay feature implementation). This is the *how we coordinate the agents* layer.

---

### 1) Starting point (what existed at the beginning)

- **Agent card set**: A single document listing 13 directors and shared rules:
  - `.cursor/plans/studio-agent-cards_c3880ea5.plan.md`
  - Contains:
    - Department lead definitions (ExecutiveProducer_PM, GameDirector_ProductOwner, TechnicalDirector_Architecture, etc.)
    - Shared engagement rules: modular work, small increments, async coordination, multiplayer guardrails.
    - Required response format per agent (Status/Deliverables/Questions/Next actions).

- **Project QA scaffolding already present** (important because it becomes the “release gate” for lightweight builds):
  - `QA_TEST_PLAN.md`
  - `RELEASE_QA_CHECKLIST.md`
  - `tools/qa_smoke.py`
  - `tools/observe_sync.py`

- **Existing “Next Slice” spec doc (key anchor)**:
  - `docs/feature_specs/next_slice_specs.md`
  - Defines:
    - FS-1: Hero intent + last decision inspect (“why did they do that?”)
    - FS-2: Bounty clarity (responders + attractiveness)
    - FS-3: Early pacing guardrail (reduce dead air)

---

### 2) Studio operating decisions (high-level)

We aligned on:

- **Priority**: build features that work with minimal bugs (stability-first).
- **Build cadence**: **lighter, more frequent builds**.
- **Dates**: deferred; we operate on “ship when stable” with a weekly/biweekly rhythm.

These decisions shape the infrastructure: the whole system is designed to make it easy to ship small increments while keeping a stable baseline.

---

### 3) 1-week sprint planning (Week 1: broad sweep)

We created a 1-week sprint plan oriented around strengthening Majesty-like feel without ballooning risk:

- **Plan file**:
  - `.cursor/plans/wk1-broad-sweep-midweek-endweek_3ca65814.plan.md`

Core attributes of the plan:

- **Two-build cadence**:
  - **Build A (Midweek)**: clarity + incentive legibility + instrumentation (low risk)
  - **Build B (Endweek)**: early pacing guardrail + balance polish + perf/stability pass
- **Definition of Done (DoD)** emphasized:
  - Must pass headless smoke: `python tools/qa_smoke.py --quick`
  - Must be playable in `--no-llm` and `--provider mock`
  - Determinism guardrails: prefer sim-time/tick; avoid wall-clock for sim-relevant logic

The sprint plan also included:

- **Workstreams mapped to the 13 agents**
- **Integration order** to reduce merge conflicts
- **Release notes templates** references

---

### 4) The “13 agent replies problem” (what failed and why)

#### The initial attempt
We tried collecting replies by having agents update a shared log file (JSONL).

- Attempted shared log:
  - `.cursor/plans/wk1_agent_responses_log.jsonl`

#### Why it failed
Multiple agents editing the same file at the same time caused:

- Overwrites / lost edits
- Merge conflicts
- Confusion about “who owns which line”

Even with instructions like “only edit your line,” concurrency still led to collisions in practice.

**Lesson**: For 13 parallel agents, do not use one shared file as the primary write target.

---

### 5) Solution: per-agent files (no conflicts) + structured schema

We switched to **13 agent-owned files** (one per director), placed under:

- `.cursor/plans/agent_logs/`

#### Created files (one per agent)
- `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`
- `.cursor/plans/agent_logs/agent_02_GameDirector_ProductOwner.json`
- `.cursor/plans/agent_logs/agent_03_TechnicalDirector_Architecture.json`
- `.cursor/plans/agent_logs/agent_04_NetworkingDeterminism_Lead.json`
- `.cursor/plans/agent_logs/agent_05_GameplaySystemsDesigner.json`
- `.cursor/plans/agent_logs/agent_06_AIBehaviorDirector_LLM.json`
- `.cursor/plans/agent_logs/agent_07_ContentScenarioDirector.json`
- `.cursor/plans/agent_logs/agent_08_UX_UI_Director.json`
- `.cursor/plans/agent_logs/agent_09_ArtDirector_Pixel_Animation_VFX.json`
- `.cursor/plans/agent_logs/agent_10_PerformanceStability_Lead.json`
- `.cursor/plans/agent_logs/agent_11_QA_TestEngineering_Lead.json`
- `.cursor/plans/agent_logs/agent_12_ToolsDevEx_Lead.json`
- `.cursor/plans/agent_logs/agent_13_SteamRelease_Ops_Marketing.json`

#### Design goals for the new schema
- **No collisions**: each agent edits only their own file.
- **Searchable history**: nest rounds under sprints.
- **Structured output**: agents don’t just paste raw text; they break responses into:
  - summary bullets
  - proposed changes
  - acceptance criteria
  - risks
  - dependencies
  - questions back to PM
  - recommended next actions
  - agent_fields (role-specific extras)

---

### 6) Schema v2.0 (nested sprints → rounds)

All agent log files were upgraded to:

- `schema_version: "2.0"`
- A top-level object:
  - `sprints: { "<sprint_id>": { sprint_meta, rounds } }`

Each sprint entry contains:

- `sprint_meta`: references (e.g., the sprint plan path)
- `rounds`: a map of round IDs to structured prompt/response objects

This solves the second core issue:

- **“Where do I put Round 2 or Week 2?”** → nested under a new round or new sprint ID.

---

### 7) Reply entry template (standardized structured response)

We created a reusable template file:

- `.cursor/plans/agent_logs/REPLY_ENTRY_TEMPLATE.json`

This file contains the canonical JSON object shape to paste under:

- `sprints["<sprint_id>"].rounds["<round_id>"]`

It ensures every agent reply includes the “good” structure we wanted:

- `prompt_text`
- `response.raw` (full response)
- the structured arrays (summary/proposals/criteria/risks/etc.)
- `response.agent_fields` for role-specific data

This template reduces agent variability and makes PM synthesis faster.

---

### 8) “Forget prior instructions” universal prompt (operational reset)

Because agents may have had mixed instructions over time (shared-file JSONL vs per-agent JSON),
we created a universal directive to reset their behavior:

- “Forget prior logging instructions.”
- “Write to your own file under `.cursor/plans/agent_logs/`.”
- “Model your response after `REPLY_ENTRY_TEMPLATE.json`.”

This is important operationally: without it, agents can keep following stale patterns.

---

### 9) PM synthesis centralization (single source of truth for decisions)

After agents submitted their logs, we created a **PM synthesis & response hub** inside:

- `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`

#### What we changed in Agent 01’s file
We extended Agent 01’s log to include a sprint+round entry that:

- Responds to all 13 agents in one place
- Records PM decisions (so the studio doesn’t thrash)
- Captures integration order

Specifically, we added under:

- `sprints["wk1-broad-sweep-midweek-endweek"].rounds["wk1_r1"]`

The PM round entry includes:

- `pm_decisions`:
  - Build A vs Build B split
  - locked intent taxonomy
  - determinism gate requirements
  - UI defaults (help overlay default off)
  - attractiveness policy (global tier for Build A)
- `pm_responses_by_agent`:
  - A key per agent ID: “acknowledged + asks”
- `pm_integration_order`:
  - the order we want changes to land to minimize breakage
- `pm_open_questions_resolved`:
  - a list of questions explicitly closed so they don’t reopen repeatedly

#### Why this is useful
Agents no longer need to hunt through 13 files or ambiguous chat history:

- They can read a single PM decision source and proceed with confidence.

---

### 10) Operational workflow (how to run future rounds)

This is the “repeatable” workflow for sprints going forward.

#### Step A: PM creates sprint + round
1. Create or update the sprint plan under `.cursor/plans/`.
2. Decide:
   - `sprint_id` (example: `wk2-coreloop-polish`)
   - `round_id` (example: `wk2_r1`)
3. Put prompts into the sprint plan (or a separate prompt doc).

#### Step B: Agents respond in their own files
Each agent:
1. Opens their file in `.cursor/plans/agent_logs/`.
2. Creates/updates:
   - `sprints[sprint_id].rounds[round_id]`
3. Pastes the template object, fills it out, and saves.

#### Step C: PM synthesizes
PM reads all agents’ round entries, then updates:

- `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json`

The PM round response should include:

- Decisions (close open questions)
- Follow-up asks per agent
- Integration order
- Release gates

#### Step D: PM broadcasts a single “read PM response” prompt
PM sends a single instruction to all agents:

- “Read PM decisions here, then update your agent log with ACK + blockers.”

This keeps coordination tight and avoids repeating guidance 13 times.

---

### 11) Key conventions established

#### IDs
- **Agents**: `01`..`13`
- **Sprints**: descriptive string, stable (example: `wk1-broad-sweep-midweek-endweek`)
- **Rounds**: `wkN_rM` (or similar)

#### Location
- Plans live in `.cursor/plans/`
- Agent logs live in `.cursor/plans/agent_logs/`

#### Ownership
- Each agent edits only their own file.
- PM decisions live in Agent 01’s file as the broadcast hub.

---

### 12) Common pitfalls (and how we avoided them)

- **Shared-file overwrites**: solved by per-agent files.
- **Free-form responses**: solved by a common reply template.
- **Reopened decisions**: solved by `pm_open_questions_resolved`.
- **Determinism drift**:
  - decisions include “no wall-clock in sim logic”
  - QA smoke and determinism guard are treated as release gates

---

### 13) Suggested next infrastructure improvements (optional)

These are not required, but will make future sprints smoother.

- **Add an index file** (PM-owned only):
  - `.cursor/plans/agent_logs/index.json`
  - Records which sprint/round is “current,” plus links to plan files and key decisions.

- **Add a tiny synthesis tool** (ToolsDevEx agent):
  - A script that reads all 13 JSON files and prints:
    - per-agent blockers
    - aggregated risks
    - dependency graph
  - This is optional; manual PM synthesis is fine for now.

- **Standardize timestamps**:
  - Choose ISO8601 local (with offset) everywhere.

---

### 14) Quick reference (file list)

**Core docs**
- `.cursor/plans/studio-agent-cards_c3880ea5.plan.md`
- `.cursor/plans/wk1-broad-sweep-midweek-endweek_3ca65814.plan.md`
- `.cursor/plans/ai_studio_infrastructure_progress.md` (this file)

**Agent logs**
- `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json` (PM hub)
- `.cursor/plans/agent_logs/agent_02_...json` through `agent_13_...json`

**Template**
- `.cursor/plans/agent_logs/REPLY_ENTRY_TEMPLATE.json`

**Legacy / deprecated**
- `.cursor/plans/wk1_agent_responses_log.jsonl` (shared-file approach; kept for history but not recommended)

---

### 15) Current status snapshot (as of this document)

- Agent infrastructure is now stable:
  - 13 agent files, no collisions
  - structured replies nested by sprint/round
  - PM decisions centralized and broadcast through Agent 01 file
- Agents are currently working on a broadcast prompt to acknowledge PM decisions and proceed with follow-ups.


