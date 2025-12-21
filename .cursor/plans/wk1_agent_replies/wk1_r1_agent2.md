# WK1 R1 — Agent 2 (GameDirector_ProductOwner) Response

## Status
Acting as **Agent 2) GameDirector_ProductOwner** for the WK1 “broad sweep” sprint: deliver the **1-page acceptance checklist** that captures “Majesty feel” improvements (clarity + incentives + pacing) with low bug risk.

## Deliverables
- **1-page sprint acceptance checklist**: `docs/sprint/wk1_acceptance_checklist.md`
- **Plan wired to checklist** (single source of truth for QA): `.cursor/plans/wk1-broad-sweep-midweek-endweek_3ca65814.plan.md`

## Questions (only blockers)
- **Build A vs Build B intent**: Do you want **FS-3 (early pacing guardrail)** strictly **Build B only**, or can a minimal “HUD prompt only” version land in Build A if it’s safe?
- **Intent labels**: Should we lock the exact intent taxonomy to the plan’s list (`idle`, `pursuing_bounty`, `shopping`, etc.), or allow a smaller subset for this week?

## Next actions
- Use `docs/sprint/wk1_acceptance_checklist.md` as the QA signoff for Build A and Build B.
- If you confirm the two questions above, I’ll update the checklist wording to match the exact build split and intent taxonomy (no code changes required).

## Handoff checklist
- **Files changed**
  - `docs/sprint/wk1_acceptance_checklist.md`
  - `.cursor/plans/wk1-broad-sweep-midweek-endweek_3ca65814.plan.md`
- **How to test**
  - Open the sprint plan and click the checklist link.
  - Ensure the checklist matches the sprint’s P0/P1 gates and is usable for a 10-minute manual pass.
- **Gotchas / future cleanup**
  - None (docs-only).
- **Follow-up tasks (other agents)**
  - Agent 3/6/8 can implement against the checklist gates (intent + last decision + bounty responders/attractiveness + early pacing prompt).


