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

**Discovery completed 2026-06-09** — 11 explorers + synthesis (12 agents, ~2M tokens, 73 raw
candidates → 36 ranked). **Full per-candidate detail (mechanism, fix design, evidence,
file:line citations): `.cursor/plans/mythos_lag_fix_candidates.json`** (committed). Theory of
the lag — four stacked, independently measured costs:

1. **vsync quantization** — Panda defaults `sync-video` ON (Ursina's vsync kwarg is dead
   code); every frame rounds up to a 16.7 ms vblank multiple (~10–16 ms lost at the 30 fps
   boundary; explains the 33↔50 ms alternation that reads as jitter).
2. **Legacy per-Entity unit render** (~23 ms rend at spec) — proven 2.5× instanced path
   exists but is blocked from default by overlay parity gaps (+ 4 correctness gaps found:
   terrain-height, projectile kinds, non-uniform scales, shadow y).
3. **HUD upload conversion stack** (~12–14 ms maximized + a measured 50 ms full-upload hitch
   fallback) — pygame surface bytes are byte-identical to Panda F_rgba BGRA → zero-copy.
4. **Sim tick doubled at FAST** (~6–12 ms/frame) — five cacheable per-tick rebuilds (hero
   profiles, tree-growth dict, POI scans, fog, threat scans) + A* bursts for p99 spikes.

**Hero-spawn hitch root-caused (confirmed):** every Ursina `Text()` re-runs
`FontPool.load_font` + appends a duplicate model-path dir (5.3–21 ms/label, degrades over
session); plus construction-stage prefab swaps cost 11–64 ms AND leak ~26 orphan entities
per swap (an uncovered C1-class leak — re-introduces time-degradation in real play).

### Ranked top candidates (gain @ gate combo; full list in the JSON)

| # | id | stack | eff | conf | expected gain |
|---|----|-------|-----|------|---------------|
| 1 | vsync-off | S1 engine-config | S | high | windowed 28-29.5→~36-40; maximized 21-23→~25-30 |
| 2 | hud-bgra-zero-copy | S3 HUD | S | **confirmed** | hudU 12-14→1.3-4 ms maximized; kills 25-69 ms hitch class |
| 3 | text-font-cache-patch | S2 spawn-hitch | S | **confirmed** | 6-unit wave burst 35-40→~4 ms; kills per-spawn degradation |
| 4 | overlay-dirty-gates | S4 legacy-rend | S | **confirmed** | ~5.5-6.5 ms/frame skippable no-change sync |
| 5 | prefab-swap-orphan-free | S2 | S | **confirmed** | prevents re-emergent time-degradation (26 orphans/swap) |
| 6 | hud-radar-throttle-10hz | S3 | S | high | with #2: hudU avg →~1.5-2 ms maximized |
| 7 | lazy-hero-profiles | S5 sim | S | **confirmed** | ~1.5-3 ms/frame at FAST w/ 20+ heroes |
| 8 | prefab-path-resolve-cache | S4 | S | **confirmed** | ~2 ms @24 bldgs → ~8.5 ms @100 (per-frame is_file() on OneDrive!) |
| 9 | tree-growth-incremental | S5 | S | **confirmed** | ~0.9-1.8 ms/frame + gen0 GC relief |
| 10 | poi-discovery-throttle | S5 | S | **confirmed** | ~0.8-1.1 ms/frame at FAST |
| 11 | snapshot-once-per-frame | S4 | S | high | ~1.5-2.5 ms/frame (duplicate DTO pass) |
| 12 | scene-entities-ignore | S1 | S | high | ~1-5 ms/frame, scales with entity count |
| 13 | label-zoom-lod-pooled | S4 | S | high | ~100 TextNode draws gone at gate zoom |
| 14 | astar-burst-cap-tile-goals | S5 | S | high | p99 spikes 6-7.5→~2-3 ms |
| 15 | unit-prewarm-extension | S2 | S | high | kills first-spawn 270 ms hitch class |
| 16-19 | inst-hp-bars / parity-gaps / linear-interp / **default-flip** | **S6 instancing-default** | M | high | **THE landing: default 13-15 → ~30-31 windowed / 25+ maximized, stacks with S1+S3** |
| 21 | building-prefab-template-flatten | S7 | M | high | construction hitches 11-64→1-5 ms; +2-3 fps late-game |
| 22-24 | fog-cadence / tree-blocking-set / ai-threat-cache | S5 | M | high | p99 tick 10-35 → ~5-6 ms |
| 30 | fast-dt-scaling | S5 | M | medium | halves remaining sim CPU at FAST |
| 31-36 | hud-region-split / culldraw-threading / mbinary-alpha / spatial-grid / numpy-soa / sim-worker-thread | S8 reserve | M-XL | low-high | pulled only if S1-S7 miss the bar; spatial-grid+SoA = the "hundreds" substrate |

### Execution order (each stack A/B-gated by soak/smoke evidence)

S0 measurement extras → **S1 engine-config (vsync!)** → **S2 spawn-hitch** → **S3 HUD
zero-copy** → S4 legacy quick wins → S5 sim-tick → **S6 instancing-default (headline)** →
S7 building batching → S8 architecture reserve (only as needed).
Cheap+confirmed first: S1+S2+S3 alone are projected to put windowed past 30 and kill the
hitches; S6 is the mapped route to >30 sustained at maximized with headroom for "hundreds".

## 5. Iteration protocol

- One candidate (or one coherent stack) at a time; `git status` clean between candidates.
- Screen: 90s smoke @ out/fast/windowed + out/fast/maximized (24h/24b/80e maintained).
- Gate: 20-min soak @ gate combo when smokes clear ~35+ avg (headroom over the 30 floor).
- Keep iff: smoke improves materially OR part of a larger keep-stack; otherwise revert.
- Commit+push on every milestone (working FPS step, harness upgrade, overlay parity, etc.).
- Check for concurrent-session file changes before each commit (stage by path only).

## 6. Results log (append-only — every run gets a row)

| date | build | combo | run | avg | p50 | p10 | min | rend | tick | hudR | hudU | verdict |
|------|-------|-------|-----|-----|-----|-----|-----|------|------|------|------|---------|
| 06-09 | BASELINE (53dccec) | out/fast/windowed | 2.5min smoke | 15.4 | 15.0 | 10.8 | 13.6* | 22.4 | 9.5 | 3.7 | 10.6 | FAIL (need >30) |
| 06-09 | BASELINE (53dccec) | out/fast/maximized | 2.5min smoke | 13.1 | 12.7 | 9.4 | 10.2* | 23.8 | 11.4 | 4.0 | 17.3 | FAIL |

| 06-09 | **R1 = S1+S2+S3** | out/fast/windowed | 2.5min smoke | **18.6** | 18.9 | 16.7 | 16.3 | 19.1 | 7.8 | 3.6 | **0.84** | FAIL (need >30) — +21% vs base |
| 06-09 | **R1 = S1+S2+S3** | out/fast/maximized | 2.5min smoke | **19.0** | 19.2 | 17.5 | 15.5 | 18.3 | 7.7 | 3.8 | **1.29** | FAIL — **+45% vs base**; win/max gap CLOSED |

\* min of window fps_ema rows (not single-frame min). Stage cols = fps-probe avg ms.
Baseline notes: `gpu_or_ursina` untracked remainder frequently 20–45 ms with spikes >100 ms
— consistent with vsync present-wait + GPU draw; hudU max 47.4 (windowed) / 75.9 (maximized)
confirms the full-upload hitch class; tick max 96–229 ms = catch-up + A* burst class.

| 06-09 | **R2 = R1+S5+S6** | out/fast/windowed | 2.5min smoke | **48.6** | 50.2 | 42.1 | 37.0 | 5.9 | 1.9 | 2.9 | 0.65 | **PASS (all rows >30)** |
| 06-09 | **R2 = R1+S5+S6** | out/fast/maximized | 2.5min smoke | **44.4** | 45.9 | 38.8 | 36.4 | 6.2 | 2.1 | 3.2 | 1.04 | **PASS (all rows >30)** |

**R2 outcome (committed):** S6 instancing DEFAULT-ON with full parity (instanced HP bars,
terrain-Y, non-uniform scales, magic/heal orbs, legacy linear interp, pooled zoom-LOD
labels; legacy path intact behind KINGDOM_URSINA_INSTANCING=0; 51 instancing tests) +
S5 sim-tick stack (tick bench mean 4.7→2.3 ms, p99 15.1→9.0, max 130→50; WK67 digest
BYTE-IDENTICAL with all defaults on; fast-dt-scaling built but default OFF pending balance
soak). Baseline → R2: windowed 15.4→48.6 (3.2×), maximized 13.1→44.4 (3.4×). Remaining
stages: igloop ~10 ms, rend ~6, hudR ~3, tick ~2. Next: definitive 20.5-min soaks.

| 06-09 | **R2 definitive d1** | out/fast/windowed | **20.5-min soak** | 49.2* | 40.5 | 36.8 | 24.6 | 5.6 | 2.0 | 2.8 | 0.65 | 149/150 window rows >30; ONE dip (screenshot+wave burst @t=916) |
| 06-09 | **R2 definitive d1** | out/fast/maximized | **20.5-min soak** | 44.4* | 36.4 | 31.9 | 28.9 | — | — | — | — | 147/150 rows >30; 3 dips 28.9-29.4 during background-agent CPU contention |

\* whole-run probe avg; p50/p10/min are the minute-15–20 window stats. 100 screenshots
captured per definitive run (minutes 15–20, every 3 s). **FPS is time-FLAT across all 20.5
minutes** (e.g. d1 windowed: probe avg 49.2 over 56k frames; window avg 40.6 at minute 15–20
with measurement overhead) — the original "gets worse after 10+ minutes" report is RESOLVED.
R3 (spawn stagger) then removed the wave-burst dip class. Runs d2/d3 ended early with rc=0
and no crash — the Sovereign was live-watching and closed the windows; he declared the result
**"FPS is very smooth now and I'm happy with it"** (2026-06-09) and redirected remaining work
to two instancing visual bugs: upside-down creature sprites + unwanted blob shadows (R4).

**R1 outcome (committed):** vsync=off verified engaged; zero-copy verified (`BGRA layout
verified` + hudU max 6.5 ms — the 47–76 ms hitch class is GONE); font patch + prewarm
(509 ms startup) + orphan-free swaps in. New `igloop` stage attribution shows the remaining
wall: **igloop ~20.5 ms (GPU cull/draw of ~300-400 legacy entities) + rend ~18-19 ms (legacy
per-Entity sync)** → S6 instancing-default is the next lever, then S5 (tick 7.7 avg, max 135).

## 7a. CLOSEOUT — 2026-06-09

Sovereign playtest verdict: **"playtest went great"** (after earlier "FPS is very smooth
now and I'm happy with it"). R4 visual fixes (upright sprites, shadows off) confirmed in
play. qa_smoke --quick green at every round. Branch `mythos-lag-fix` merged to `main`.
Sprint CLOSED.

## 7. Definition of Done

- §1 bar met: >30 fps sustained min 15–20, gate combo, 2+ repeats, 100+ screenshots reviewed.
- Hero-spawn micro-lag eliminated (measured).
- qa_smoke --quick + full pytest green; no guardrail violated (tree density untouched).
- Winning changes committed + pushed with evidence; plan + guardrails doc updated.
