# Mythos Lag Fix — Master Plan

**Author:** Agent 01 (Executive Producer / PM) — autonomous Sovereign-approved loop
**Status:** PLANNED → in execution
**Branch:** `mythos-lag-fix` (off `wk123-fps-degradation` HEAD `53dccec`; commit/push at every milestone — GitHub used as a save-state tool per Sovereign directive)
**Date opened:** 2026-06-09
**Models:** all subagents on Fable 5 (session top tier)

---

## 0. The directive (Sovereign report, 2026-06-09)

> "The FPS is not very smooth, and gets much worse once there is over 70 enemies on the map
> (let alone the hundreds of units we are aiming for) and the game has been running for 10+
> minutes, especially when it runs on the fastest speed. … Certain actions like spawning
> heroes cause micro lags too. … There's likely several factors and possibly large-scale
> architecture design choices that lead to the lag. Please be liberal and change the codebase
> however you see fit — it's just a prototype. If the game isn't smooth, there's no point in
> moving forward."

### What changed vs WK123 (read `.cursor/plans/wk123_fps_time_degradation.plan.md` first)

WK123 fixed the **time-degradation** (C1 overlay leak, C2 dead-hero accumulation) and revived
the **instanced unit renderer** (C7 `set_two_sided`), reaching ~31 fps windowed at the worst
combo — but found instancing **drops HP bars / name labels / gold labels** (C9: the instanced
branch returns before overlay sync), so it is NOT shippable as default, and concluded
"reliably >30 at maximized is not achievable **behavior-preservingly**."

**The new directive REMOVES the behavior-preserving constraint.** Architecture overhauls,
system redesigns, and visual-system rework are authorized. Two guardrails survive (memory +
rules): **never cut tree/grass/forest density** (Majesty feel), and don't undo the WK122-124
fix stack (dt-clamp, multi-band HUD upload, gc-freeze, pointer cache, prewarm, dirty-gates).
Everything else is on the table.

---

## 1. Acceptance bar (DEFINITIVE)

A run PASSES only when, **reliably across repeats**:

- **Scenario:** ≥20 heroes + ≥20 buildings + ≥75 enemies simultaneously (≈100+ units total),
  maintained for the whole run (top-up on death — measure load, not attrition).
- **Duration:** ≥20 minutes of real gameplay.
- **THE GATE:** FPS **> 30 sustained from minute 15 through minute 20** (a 5-minute window),
  at **fastest speed + zoomed out to the starting zoom** — the player's real conditions.
- **Evidence:** **100+ screenshots captured across minutes 15–20** (≈ every 3 s) + FPS CSV
  rows ≥ every 2 s in the window; window stats (avg/p50/p10/min) recorded in §6.
- **Matrix coverage** (capture FPS for each; gate = out×fast):
  - zoom out × fast, zoom out × normal, zoom normal × fast, zoom normal × normal
  - × windowed AND maximized (programmatic maximize confirmed working in WK123 harness).
- **Repeats:** the gate combo passes ≥2 independent 20-min runs before declaring victory.
- **Micro-lag:** hero spawn (and similar actions) no longer cause visible hitches —
  frame-time capture around forced spawn events shows no spike > ~80 ms attributable to spawn.
- **All tests pass:** `python tools/qa_smoke.py --quick` exit 0 + full `pytest` suite green.

## 2. Method

1. **Discovery workflow** (this session, dynamic multi-agent): ~12 parallel Fable 5 explorers
   sweep the entire codebase — render path, instancing/overlay parity, sim tick & AI,
   HUD/upload, spawn hitches, allocation/GC, Panda3D app config, prior-art docs, and
   clean-slate architecture options. Synthesis agent ranks candidates. → §4.
2. **Harness upgrade:** extend the WK123 soak harness to the 20-min / 100+-screenshot spec
   (subagent). Keep 90-second smokes as the cheap screen; 20-min soaks as the gate.
3. **Iterative loop** (hours): apply candidate → 90s smoke at the gate combo → if improved,
   stack; if not, `git checkout --` revert. Milestone = meaningful FPS step → commit + push.
   Periodically run the full 20-min gate. Never keep a change that didn't earn its place.
4. **Definitive validation:** full matrix, repeats, screenshot review (sample broadly per
   review-coverage memory), tests green, results logged, guardrails doc updated.

## 3. Known starting point (from WK123 measurements, same spec 24h/24b/80e)

| Path | out/fast/windowed | out/fast/maximized | Notes |
|---|---|---|---|
| Legacy per-Entity (DEFAULT today) | ~15 avg | ~13 avg | full visuals; rend ≈ 23 ms wall |
| Instanced units (opt-in) | **31.5 avg / p50 27.7** | **25.2 avg / p50 22.0** | but NO HP bars/names/gold (C9) |

So the shipped default is ~15 fps — **half the bar**. The instanced path + overlay parity +
maximized-path work is the known route; the discovery workflow hunts everything else
(sim-side fast-speed costs, hitch sources, hidden per-frame scaling) so we fix the whole
problem, not one axis.

## 4. Candidate fixes (filled by the discovery workflow — ranked)

*(populated after `mythos-lag-discovery` returns)*

## 5. Iteration protocol

- One candidate (or one coherent stack) at a time; `git status` clean between candidates.
- Screen: 90s smoke @ out/fast/windowed + out/fast/maximized (24h/24b/80e maintained).
- Gate: 20-min soak @ gate combo when smokes clear ~35+ avg (headroom over the 30 floor).
- Keep iff: smoke improves materially OR part of a larger keep-stack; otherwise revert.
- Commit+push on every milestone (working FPS step, harness upgrade, overlay parity, etc.).
- Check for concurrent-session file changes before each commit (stage by path only).

## 6. Results log (append-only — every run gets a row)

*(starts after harness upgrade)*

## 7. Definition of Done

- §1 bar met: >30 fps sustained min 15–20, gate combo, 2+ repeats, 100+ screenshots reviewed.
- Hero-spawn micro-lag eliminated (measured).
- qa_smoke --quick + full pytest green; no guardrail violated (tree density untouched).
- Winning changes committed + pushed with evidence; plan + guardrails doc updated.
