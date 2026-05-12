# Future Sub-Divisions with Department Head Subagents

## Purpose

This document describes a **future operating mode** for the Kingdom Sim AI Studio when sprints become **too large for a single pass** per department lead. The goal is to keep the PM’s sprint plan as the single source of truth while allowing each **involved agent (department head)** to break their slice into **sub-divisions** executed by **sub-agents** (separate Cursor sessions or orchestrator tasks), without losing ownership boundaries, gates, or traceability.

This is **not** required for normal sprints. Use it when scope, file touch count, or cross-system risk clearly exceeds what one session per agent can reliably finish.

---

## Preconditions (before any sub-division work)

1. **PM sprint plan exists** — The Executive Producer has published the sprint under `.cursor/plans/agent_logs/agent_01_ExecutiveProducer_PM.json` (or a linked sprint plan in `.cursor/plans/`) with:
   - clear goals, out-of-scope items, and integration order;
   - `pm_agent_prompts` / `pm_next_actions_by_agent` per participating agent;
   - bug tickets and feature specs the implementers must obey.

2. **Ownership is explicit** — `AGENTS.md` and role rules already define who may edit which paths. Sub-agents inherit the **same lane** as their department head; they do not get new ownership.

3. **Gates are non-negotiable** — Any sub-division that changes code must still end with `python tools/qa_smoke.py --quick` (and asset validation when applicable). Partial work that fails the gate does not merge forward.

---

## Workflow overview

```text
PM: sprint plan + assignments
        │
        ▼
Department head (Agent NN): reads PM hub + own log
        │
        ├── Derives "implementation plan" for THIS agent only
        │     (scope, tasks, order, files, risks, handoffs)
        │
        └── If sprint slice is large enough:
                  │
                  ├── Sub-division A → Sub-agent session / orchestrator child
                  ├── Sub-division B → …
                  └── Sub-division C → …
        │
        ▼
Department head: integrates results, resolves conflicts, updates own agent log
        │
        ▼
PM / QA: sprint review, human gates as usual
```

---

## What the department head produces

After the PM plan is fixed, each **involved** department lead should produce a short **implementation plan** (can live in their agent log under the sprint round, or in a sibling doc under `Sub-Division Plans/` if the write-up is long). The plan should include:

| Section | Why it matters |
|--------|----------------|
| **Scope restatement** | Prevents “helpful” scope creep; ties work to `pm_agent_prompts[NN]` only. |
| **Task breakdown** | Ordered or DAG-shaped list of concrete outcomes (not vague “polish UI”). |
| **File map** | Which paths this agent owns vs **must not** touch; where coordination is needed. |
| **Sub-division boundaries** | Each sub-division should be merge-sized: one coherent theme, minimal cross-file thrash. |
| **Interfaces & contracts** | If sub-agents touch shared types/events/snapshots, the head defines the contract first. |
| **Verification** | Per sub-division: commands + what “done” looks like (including screenshot loop for visible work). |
| **Handoff prompts** | If another department must do a follow-up, paste-ready text for PM to route. |

---

## Sub-agent model (logical shape)

**Sub-agents** are not new roles in `AGENTS.md`. They are **extra Cursor chats (or orchestrator child runs)** that:

- receive a **self-contained prompt** written by the department head (or PM, if the head delegates prompt authorship);
- work **only** inside the owning agent’s directories unless a one-line cross-domain change was pre-approved;
- report back with: files touched, commands + exit codes, evidence paths, blockers;
- **do not** replace the department head’s responsibility to integrate, resolve conflicts, and write the canonical log entry for the sprint round.

### When to spin up sub-agents

Reasonable triggers:

- Parallel tracks (e.g. Art: terrain pass + unit outlines) that touch different files and share only standards docs.
- Large mechanical work (asset manifest, scenario tables) separate from fragile logic.
- Investigation vs implementation split: one sub-agent researches repro, another implements the fix after the head approves the approach.

### When not to split

- Tight coupling across `game/engine.py`, `sim_engine.py`, and multiple systems — keep as one head-led thread or serialize sub-tasks strictly.
- Ambiguous product intent — Game Director / PM clarification first, then possibly split.

---

## Coordination and conflict avoidance

1. **One writer per file per wave** — If two sub-divisions need the same file, the head sequences them or merges tasks into one sub-agent.

2. **Trunk integration cadence** — Sub-agents should target small, reviewable chunks; the head rebases/merges frequently to reduce painful integration at the end of the sprint.

3. **Cross-domain changes** — Follow `AGENTS.md`: minimal patch + explicit note to the primary owner; prefer a ticket and handoff if the change is not urgent.

4. **Orchestrator vs manual** — If `tools/ai_studio_orchestrator` is used, each child run still follows `.cursor/rules/10-orchestrator-logging-contract.mdc` (receipt + log path). Department heads should align sub-agent logs so PM review does not miss evidence.

---

## Quality and evidence

- **Department head** remains accountable for gate green and for **Phase 4b** (screenshot proof for player-visible work), either by doing captures themselves or by requiring each visual sub-division to attach capture paths before merge.
- **PM** remains accountable for sprint-level Definition of Done and send lists; sub-divisions do not add new agents to `pm_send_list_minimal` without PM awareness (optional future convention: `pm_subwaves` in hub — only if the studio adopts it).

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Context drift (sub-agent forgets sprint constraints) | Prompt must link PM hub path + sprint/round id; restate out-of-scope bullets. |
| Duplicate or conflicting implementation | Head owns file map and order; one merge integrator. |
| Silent bypass of determinism / QA culture | Same gates; determinism guard inside `qa_smoke --quick`. |
| Log noise / missing audit trail | Head consolidates in their `agent_NN_*.json` round entry; sub-agents note “child of round X” if logs are split. |

---

## Adoption criteria (suggested)

Use this **Sub-Division** pattern when **any** of:

- more than ~3 distinct technical themes in one agent’s assignment;
- estimated **>5 primary owned files** with non-trivial logic changes;
- high regression risk (combat, AI, engine contracts) **and** parallel polish work — split polish, serialize core.

Otherwise, a single department-head session is simpler and less overhead.

---

## Summary

For **very large sprints**, the PM plan stays authoritative. Each **involved department head** produces an **implementation plan** for their slice and, when justified, **fans out sub-agents** along clear boundaries, integrates the results, and carries the **gates and agent log evidence**. This folder holds studio-level guidance for that mode; per-sprint detail should still anchor in the PM hub and the owning agent’s log.
