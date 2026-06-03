# WK105 Sprint Plan — Round B-22: extract ursina_app_debug_probe.py (env-gated debug/FPS-probe scaffolding) — second ursina god-file slice

**Author:** Agent 01 (PM) · **Date:** 2026-05-31 · **Goal:** all tests pass; the env-gated debug-layout + FPS-probe + auto-screenshot scaffolding extracted from `game/graphics/ursina_app.py` (1528 LOC) into a NEW `game/graphics/ursina_app_debug_probe.py`; normal play unaffected (the cluster is dead-by-default).
**Predecessors:** WK87–92 + WK104 (ursina owner-arg pure-move + headless seam-test pattern), WK93–103 (hud.py). **Roadmap:** Round B — ursina god-files. Second ursina slice; chosen + de-risked by the WK105 ursina grounding workflow (ranked safest: dead-by-default, zero external callers).

## 0. TL;DR
WK105 extracts the **debug/FPS-probe scaffolding** — a contiguous 8-method block (L985–1272) of ursina_app.py that is **dead-by-default** (every entry point is gated behind a `KINGDOM_URSINA_*` env flag or the auto-exit path) — into a NEW `game/graphics/ursina_app_debug_probe.py`, using the WK104 owner-arg pure-move. This is the **safest possible deferred-screenshot slice**: because the cluster never runs in normal play, a verbatim move cannot regress gameplay rendering. It has ZERO external callers, NO moved class (no back-import), NO module constant to mirror, and `UrsinaApp` has NO `__slots__` (so owner writes need no slot declaration). The only extra cost vs WK104: ursina_app.py has NO existing seam-test harness, so a fresh one is authored from the WK104 template. Per [[feedback_ursina_deferred_screenshots]], live before/after Ursina captures are DEFERRED to Jaimie's end test; the headless net (import smoke + seam test + suite + qa_smoke) + a meticulous PM verbatim-diff review is the in-agent safety net. PM writes no code.

## 1. Scope
**IN:** create `game/graphics/ursina_app_debug_probe.py`; move VERBATIM these 8 members out of `game/graphics/ursina_app.py` (owner class `UrsinaApp`, L57):

| Member | current lines | → in new module | Notes |
|---|---|---|---|
| `_add_wk30_debug_prefab_layout(self)` | 985–1062 | `_add_wk30_debug_prefab_layout(owner)` | env-gated `KINGDOM_URSINA_PREFAB_TEST_LAYOUT` (called __init__:187); touches only `owner.engine` + local imports |
| `_install_worker_scale_comparison_shot(self)` | 1064–1097 | `_install_worker_scale_comparison_shot(owner)` | env-gated `…WORKER_SCALE_SHOT` (called __init__:204, run():1333) |
| `_add_hero_fps_probe_layout(self, hero_count)` | 1099–1161 | `_add_hero_fps_probe_layout(owner, hero_count)` | env-gated `…HERO_FPS_PROBE_COUNT>0` (called __init__:192) |
| `_record_fps_probe_sample(self, dt)` | 1163–1170 | `_record_fps_probe_sample(owner, dt)` | FPS-probe trio; touches only `owner._fps_probe_*`; called run():1347 (no-op when disabled) |
| `_record_fps_probe_stage_ms(self, name, started_at)` | 1172–1175 | `_record_fps_probe_stage_ms(owner, name, started_at)` | called run():1328/1402/1415/1418 (no-op when disabled) |
| `_print_fps_probe_summary(self)` | 1177–1210 | `_print_fps_probe_summary(owner)` | reads `owner._fps_probe_*` + `owner.engine.heroes` |
| `_maybe_auto_screenshot_then_quit(self)` | 1212–1247 | `_maybe_auto_screenshot_then_quit(owner)` | reads `owner._auto_screenshot_path`; cross-calls the next two (see below); called run():1370 |
| `_save_window_screenshot_sync(base, out_path)` | 1249–1272 | `_save_window_screenshot_sync(base, out_path)` | **@staticmethod** — moves as a plain module function (NO owner arg); takes `(base, out_path)` |

**Owner-arg rule:** the 7 INSTANCE methods become module functions with `owner` first; rewrite every `self.`→`owner.` in their bodies (`owner.engine`, `owner._fps_probe_enabled/_elapsed/_warmup_sec/_samples/_stage_samples`, `owner._auto_screenshot_path`). The `@staticmethod` `_save_window_screenshot_sync` moves as a plain module function (no `owner`/`self`). **Intra-cluster calls** (both move together): inside the moved `_maybe_auto_screenshot_then_quit`, `self._print_fps_probe_summary()`→`_print_fps_probe_summary(owner)` and `self._save_window_screenshot_sync(base, out_path)`→`_save_window_screenshot_sync(base, out_path)` (DIRECT module-local calls, NOT `owner.*` — avoids a needless wrapper hop).

**Keep ALL heavy imports FUNCTION-LOCAL (copy verbatim inside the moved bodies, do NOT hoist):** `panda3d.core` (Filename/PNMImage) inside `_save_window_screenshot_sync`; `ursina.application` inside `_maybe_auto_screenshot_then_quit`; `game.entities.*` / `game.world.Visibility` / `Building` / `BuildingType` inside the 3 layout methods. Hoisting would pull ursina/panda at module load and break the headless import smoke / both-orders subprocess.

**Cross-calls staying on owner:** NONE (the grounding confirmed cross_calls_staying is empty). The staying internal call sites (`__init__` 187/192/204; `run()` 1328/1333/1347/1370/1402/1415/1418) reference `self.<name>` and reach the wrappers unchanged.

**STAYS on `UrsinaApp`** (DO NOT move): everything else — `__init__`, `run()`, the HUD/env staticmethods at L267–315 (`_read_int_env`, `_hud_quick_fingerprint`, `_hud_prefers_nearest_pixel_filter`, `_sync_hud_texture_filter_mode` — these are HOT-PATH, NOT debug scaffolding), etc. **OUT.**

## 2. Pattern (WK104, verbatim) — new module + wrappers
`game/graphics/ursina_app_debug_probe.py` header:
```python
"""Env-gated debug-layout + FPS-probe + auto-screenshot scaffolding, extracted from game.ui... game/graphics/ursina_app.py (WK105 slice).

All 8 members are dead-by-default (gated behind KINGDOM_URSINA_* env flags / the auto-exit path).
The 7 instance methods take owner=UrsinaApp first (self.->owner.); _save_window_screenshot_sync is a
plain module function (was a @staticmethod). UrsinaApp keeps 1-line delegating wrappers (exact names).
Acyclic: ursina_app.py imports this module one-way for the wrappers; this module imports UrsinaApp
ONLY under TYPE_CHECKING and keeps all heavy (ursina/panda3d/game.entities) imports function-local.
"""
from __future__ import annotations
import os
import time as pytime
from typing import TYPE_CHECKING
import config
if TYPE_CHECKING:
    from game.graphics.ursina_app import UrsinaApp
```
(Include `import time as pytime` ONLY if `_record_fps_probe_stage_ms` uses it at module scope — the grounding noted it uses `pytime.perf_counter`; match the original's reference. Trim `os`/`config`/`pytime` to exactly what the moved bodies reference at module scope; everything ursina/panda/entities stays function-local.)

### Wrappers on `UrsinaApp` (replace each moved method body; keep EXACT names/signatures):
```python
def _add_wk30_debug_prefab_layout(self) -> None:
    from game.graphics import ursina_app_debug_probe
    return ursina_app_debug_probe._add_wk30_debug_prefab_layout(self)
# ... analogous for _install_worker_scale_comparison_shot, _add_hero_fps_probe_layout(self, hero_count),
#     _record_fps_probe_sample(self, dt), _record_fps_probe_stage_ms(self, name, started_at),
#     _print_fps_probe_summary, _maybe_auto_screenshot_then_quit ...
@staticmethod
def _save_window_screenshot_sync(base, out_path: str) -> bool:
    from game.graphics import ursina_app_debug_probe
    return ursina_app_debug_probe._save_window_screenshot_sync(base, out_path)
```
(`_save_window_screenshot_sync` wrapper stays a `@staticmethod` — no owner arg — for exact class-attr parity, since run()/future callers may reference the class attr.) Add a top-level `from game.graphics import ursina_app_debug_probe` is NOT needed if the wrappers import lazily; keep the lazy `from game.graphics import ursina_app_debug_probe` inside each wrapper body (matches WK104). **Cycle proof:** the new module imports only os/time/config + (lazily, inside bodies) ursina/panda3d/game.entities, and imports `UrsinaApp` only under TYPE_CHECKING; ursina_app imports the new module one-way (lazily, in wrappers) → no runtime edge back → acyclic (confirmed by the both-orders subprocess test). Move VERBATIM.

## 3. Definition of Done
- **A.** `python -m pytest -q` all pass (baseline **1208 passed / 4 skipped / 0 failed** at WK104 close; +new seam test → expect ~1218+).
- **B.** `python tools/determinism_guard.py` clean (excludes game/graphics/**).
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` (pytest assertion).
- **D.** `python tools/qa_smoke.py --quick` green.
- **E.** headless import smoke: `SDL_VIDEODRIVER=dummy python -c "import game.graphics.ursina_app_debug_probe; import game.graphics.ursina_app; print('IMPORT_OK')"` + the reverse order both succeed.
- **F.** the 8 members live in `game/graphics/ursina_app_debug_probe.py`; `UrsinaApp` keeps the 8 wrapper names+signatures (incl. `_save_window_screenshot_sync` as `@staticmethod`); the staying call sites (__init__ 187/192/204; run() 1328/1333/1347/1370/1402/1415/1418) UNCHANGED; heavy imports kept function-local; file smaller (1528 → ~1247); **no import cycle** (both fresh orders); ZERO `self.` in the 7 moved INSTANCE functions (the staticmethod `_save_window_screenshot_sync` has neither self nor owner — correct).
- **G.** **DEFERRED (Jaimie):** the debug scaffolding only renders under env flags; if Jaimie wants visual confirmation, the relevant capture is `KINGDOM_URSINA_PREFAB_TEST_LAYOUT=1 … run_ursina_capture_once.py` — but since it's dead-by-default, the normal-play before/after captures (wk61_hold_g_tax_overlay) should be UNCHANGED. Flag as DEFERRED-NEEDS-DISPLAY; not run by headless agents.
- **H.** new seam test `tests/test_wk105_ursina_app_debug_probe.py`; PM verbatim-diff review; logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 09 ArtDirector):** create `ursina_app_debug_probe.py` (header + 8 members; 7 instance fns `self.`→`owner.`; `_save_window_screenshot_sync` as a plain module fn; heavy imports function-local; intra-cluster calls direct); add the 8 wrappers on `UrsinaApp` (incl. the `@staticmethod` one). Run: import smoke (both orders, SDL dummy), full suite, determinism_guard, WK67 digest (pytest), qa_smoke --quick. Verify ZERO `self.` in the 7 moved instance fns + no module-top runtime `ursina_app` import in the new module. DO NOT run live ursina screenshots (no display) — note deferred. Update own log. **DO NOT COMMIT.**
- **W2 (Agent 11 QA):** seam test `tests/test_wk105_ursina_app_debug_probe.py` — copy the 5 WK104 test classes from `tests/test_wk104_ursina_terrain_growth_sync.py`: (1) the 7 instance fns exist+callable+owner-first on the new module (parametrized inspect.signature first-param=='owner'); `_save_window_screenshot_sync` exists+callable but its signature test must NOT assert owner-first (it's `(base, out_path)`). (2) wrappers delegate — build a bare `fc = object.__new__(UrsinaApp)` (do NOT call __init__, it opens a window), monkeypatch-spy each module fn, call the wrapper, assert it forwards the bare instance as `owner` + remaining args; for the FPS trio, hand-set `_fps_probe_enabled/_elapsed/_warmup_sec/_samples/_stage_samples` to exercise real behavior; + AST check of each wrapper body. (3) AST guard: new module has NO module-top runtime `import game.graphics.ursina_app` (TYPE_CHECKING import of UrsinaApp allowed). (4) fresh-subprocess both import orders (SDL dummy) rc 0. (5) source assertion that ursina_app.py wrappers reference `ursina_app_debug_probe.<fn>`. Run full DoD A–F + H. Update own log. **DO NOT COMMIT.**
- **PM gate (me):** line-by-line VERBATIM-DIFF review (HEAD originals normalized self→owner vs the new module) — confirm faithful, zero residual self in the 7 instance fns, the staticmethod intact, heavy imports function-local, intra-cluster calls direct. Primary safety net (deferred screenshot).

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A `self.`→`owner.` missed → wrong attr at runtime under a debug flag | Low | dead-by-default (only runs under env flags, so no normal-play impact); PM verbatim-diff; grep zero-self; W2 FPS-trio behavior test |
| `_save_window_screenshot_sync` mishandled (it's a staticmethod, no owner) | Low | plan: moves as plain module fn; wrapper stays @staticmethod; W2 existence test skips owner-first for it |
| Heavy imports hoisted → headless import smoke / both-orders subprocess breaks | Low | plan: keep function-local verbatim; W1 import smoke + W2 subprocess test |
| Import cycle | Very Low | new module imports only os/time/config + TYPE_CHECKING UrsinaApp; lazy wrappers; both-orders subprocess |
| ursina_app has no existing seam harness | n/a | author fresh from the WK104 template (object.__new__(UrsinaApp)) |
| Render regression invisible headlessly | Low (accepted) | dead-by-default → no normal-play render path touched; per [[feedback_ursina_deferred_screenshots]] live captures DEFERRED to Jaimie |

## 6. Success
The debug/FPS-probe scaffolding lives in `game/graphics/ursina_app_debug_probe.py` behind 8 delegating wrappers — proven by 1208+ green tests (incl. a new WK104-style seam test), clean determinism guard, unchanged WK67 digest, a clean headless import smoke (both orders), a verified no-cycle, and a meticulous PM verbatim-diff review. Because the cluster is dead-by-default, normal-play rendering is provably untouched. `ursina_app.py` drops ~281 LOC (1528 → ~1247); second ursina god-file slice, first into ursina_app.py.

## 7. Kickoff
Roster: 09 ArtDirector (W1), 11 QA (W2), PM diff-gate. Order: W1 → PM verbatim-diff gate → W2 → commit+push (DEFERRED-screenshot flag). Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE VERBATIM owner-arg MOVE (7 instance fns `self.`→`owner.`; `_save_window_screenshot_sync` = plain module fn, wrapper stays @staticmethod); intra-cluster calls direct (not owner.*); keep heavy imports FUNCTION-LOCAL; TYPE_CHECKING-only UrsinaApp import; ZERO `self.` in the 7 instance fns; do NOT fold in the HUD/env staticmethods L267-315; live screenshots DEFERRED to Jaimie (dead-by-default → normal play unaffected); own log; DO NOT COMMIT.
Follow-ups (ursina, deferred-screenshot, in order): **WK106** FOG/A-WHOLE (9-method visibility+cull+instanced-fog cluster, ursina_terrain_fog_collab.py L351-656 → ursina_terrain_fog_visibility.py, ~330 LOC; one-way coupling w/ FOG/B confirmed; mirror TERRAIN_CHUNK_SIZE, back-import _InstancedTreeStub from growth_sync, re-import _set_static_prop_fog_tint from ursina_environment, RETARGET tests/test_terrain_perf.py L300 patch.object(tfc,'_set_static_prop_fog_tint') to the new module — it has REAL existing headless coverage there). Then **WK107** FOG/B (build_3d_terrain + ground-mesh + grass + batch helper, ~640 LOC — split further if needed). Then the ursina_app HUD/env cluster (hot-path, scope carefully). DEFER: handle_click redesign (hud.py:1058). De-slop: delete dead WATCH_MINIMAP_SIZE (hud.py:57). Non-render roadmap (fully headless-verifiable): config package split, ai/vocab.py + TaskRouter, world.py fog state-machine, the 21-file WK34 zombie-type purge, context_builder/direct_prompt_validator, Move 9 SystemRunner (RISKY).
