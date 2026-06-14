# WK137 — Initial Goblin Wave + Goblin Warchief Boss

**Status:** AUTHORITATIVE plan for sprint `wk137_initial_goblin_wave`. Agents MUST read their ticket section end-to-end before touching code. Written by the PM session 2026-06-10 after direct code research; every file/line reference below was verified against the current tree.

**Sovereign decisions of record (Jaimie, 2026-06-10):**
1. Fixed 30 **sim-second** timer — the wave fires at 30 sim-seconds regardless of how many heroes the player has hired. Balance is tuned in a seeded harness (10/8/6 heroes). Sim-time = freezes on pause, ~60 wall-seconds at default NORMAL speed (0.5×).
2. Wave unit = **goblins**; boss = **"The Goblin Warchief"** — a goblin with 2× HP (60), 1.5× attack (15), ~33% larger sprite, its own name.
3. Renderer fix honors per-unit `size` for **ALL** bosses (Bandit Lord / Demon Overlord / Dragon finally render larger), not just the new one.
4. Balance targets on NORMAL difficulty: **10 heroes** win without much trouble; **8 heroes** win but 2–4 likely die; **6 heroes** are hard-matched to win.

---

## CENTRAL CONSTRAINT — WK67 digest stays byte-identical

`tests/test_wk67_ai_boundary.py` runs 300 ticks @ `engine.update(1/60)` = **exactly 5 sim-seconds** and asserts digest `b73961…`. The initial wave warns at **20 s** and spawns at **30 s** — both far outside the window — so this feature is digest-safe **by timing**, PROVIDED:
- **Zero RNG draws** before the spawn moment: no `get_rng(...)` calls or `self.rng.*` draws at construction or in the pre-trigger code path. The pre-trigger path may only do float comparisons against `elapsed_sec`.
- **Zero state mutation** in ticks 0–300: no writes to heroes, economy, `ctx.enemies`, or `EnemySpawner.wave_number` (the digest hashes `spawner.wave_number` — the wave-events system must never touch it; it doesn't today, keep it that way).
- New config constants and the new `ENEMY_STATS` entry are inert data — fine.

Every agent runs `python -m pytest tests/test_wk67_ai_boundary.py -q` before reporting done. If it goes red, your change is wrong — do NOT re-baseline the digest.

---

## Verified code facts (do not re-derive; trust these, but read the cited code)

- **Wave system:** `game/systems/wave_events.py` — `WaveEventSystem.update(ctx, dt)` accumulates `self.elapsed_sec += dt` (sim-time, already speed-scaled). Scheduled waves come from `_WAVE_TABLE` (line ~60), BUT the fire time is computed from the **table index**: `_current_event_def()` (line ~179) uses `minute = _wave_cfg.first_event_minute + self._next_table_index * _wave_cfg.interval_minutes` (2.0 min first, 1.75 min interval). **Therefore the initial wave must NOT be inserted into `_WAVE_TABLE`** — that would shift every later wave. It must be special-cased with its own flags.
- `_spawn_wave(event_def, ctx)` (line ~242): applies difficulty count multiplier `wave_event_count`, picks a `random_edge` via the named RNG stream `get_rng("wave_events")`, plans spawn positions with `_edge_position`, staggers construction via `self._pending_spawns` (WK128, `stagger_cap`), applies `difficulty.apply_to_enemy(enemy)` per enemy in `_drain_pending_spawns` (line ~228), then does `self._next_table_index += 1; self._warning_emitted = False` and emits `hud_message` "INCOMING: {name}!".
- Wave-clear (update, line ~152): when `_active_wave_def` set, no pending spawns, and all `_active_wave_enemies` dead → deposits `reward_gold` to `ctx.economy.player_gold`, emits `wave_cleared` + "Wave Cleared! +N Gold". Only ONE wave can be active at a time (`_active_wave_def is None` gate) — this invariant is kept.
- **HUD is already fully wired:** emitting `{"type": "wave_incoming", "name": ..., "seconds": ...}` produces the centered countdown banner (`game/ui/hud_toasts.py:on_wave_incoming`); `{"type": "hud_message", "text": ..., "color": ...}` produces the log line. **Zero new HUD code in this sprint.**
- **Enemy stats:** `game/entities/enemy.py` — frozen dataclass `EnemyStats` + dict `ENEMY_STATS` (line ~60). Goblin: `hp=GOBLIN_HP` (30), `attack_power=GOBLIN_ATTACK * 2` (= 10; `GOBLIN_ATTACK = 5` in config.py:239), `speed=GOBLIN_SPEED` (90.0), size 18. `name`/`is_boss` are only set on the instance when the stat block defines them (see `__init__` gating ~line 221). Thin subclasses like `class Goblin(Enemy)` at line ~515.
- **Config:** `config.py` — `WaveEventConfig` dataclass + `WAVE_EVENT = WaveEventConfig()` at lines ~60–70 (`first_event_minute=2.0`, `interval_minutes=1.75`, `warning_seconds=10.0`, `max_enemy_cap_overflow=1.5`). Hero: HP 60 / attack 10 / defense 5 / 1000 ms cooldown (lines 219–222). `MAX_ALIVE_ENEMIES = 80`.
- **Renderer gap:** both unit renderers draw every enemy at fixed `ENEMY_SCALE = 0.5 * _US`:
  - `game/graphics/instanced_unit_renderer.py` line ~787: `pack_outside(vx, vy, vz, ENEMY_SCALE, uv, ENEMY_SCALE)`; `wy = terrain_y + ENEMY_SCALE * 0.5` (line ~785). Sprite UV: `et_key = str(e.enemy_type or "goblin").lower()` → `EnemySpriteLibrary.clips_for(et_key, ...)` → `self._atlas_builder.lookup_uv("enemy", et_key, clip_name, frame_idx)`.
  - `game/graphics/ursina_unit_sync.py` line ~248: `s = ENEMY_SCALE`; label at line ~276 is built from `enemy_type` (`.replace("_"," ").title()`), ignoring the boss `.name`.
- **Atlas gap (pre-existing bug):** `game/graphics/unit_atlas.py` `_build()` (line ~90) packs ONLY `("goblin","wolf","skeleton","skeleton_archer","spider","bandit")`. Boss types (`bandit_lord` etc.) miss and `lookup_uv` returns the **fallback UV = the first packed frame** — existing bosses render with a wrong sprite today. WK137 fixes this (ticket T2).
- **Sprite library:** `game/graphics/enemy_sprites.py` `clips_for(enemy_type)` loads PNGs from `assets/sprites/enemies/<type>/<action>/*.png` if present, else generates procedural frames colored by `_type_color`. **Goblin PNG art EXISTS** (all 5 actions). Unknown types currently get a default-brown procedural blob.
- **DTO already carries what we need:** `game/sim/render_dto.py` `UnitDTO` has `size: int` (filled from `entity.size`, line ~190) and `name: str` (line ~196). **No DTO changes needed.**
- **Difficulty:** `game/systems/difficulty.py` — EASY/NORMAL/HARD; NORMAL = all 1.0×. **DEV_MODE defaults to EASY** (line ~67) — balance harness MUST force NORMAL explicitly.
- **Heroes at start:** zero heroes auto-spawn; player hires at 100g from the pre-built warrior_guild + ranger_guild (no temple at start → **only warriors and rangers can exist at 30 s**). Starting gold 2100. Permadeath (no auto-respawn).
- **Combat aggro is free:** `Enemy.find_target` (game/entities/enemy.py ~line 306) autonomously targets peasants/heroes/guards/buildings and strongly prefers buildings within `ENEMY_BUILDING_PRIORITY_RANGE_TILES = 10` of town; castle is always a fallback. A spawned wave marches on the town by itself.

## Balance math (pre-derived — use this, don't re-derive)

Hero: 60 hp, 10 atk, 5 def, 1.0 s swing → **10 DPS**; incoming damage is `max(1, dmg − 5)`.
Goblin: 30 hp (3 hero-hits), deals `max(1, 10−5) = 5` per 1.5 s → 3.33 DPS on its focused target. 12 hits (~18 s of focus) kill a hero.
Warchief: 60 hp (6 hero-hits), deals `max(1, 15−5) = 10` per 1.5 s → 6.67 DPS. 6 hits (~9 s of focus) kill a hero.
Starting composition: **10 goblins + 1 warchief** (360 total wave HP). Expected: 10 heroes (~100 DPS) clear in ~4–5 s with ~0–1 deaths from focus-fire; 8 heroes ~5–6 s, 1–3 deaths; 6 heroes ~8 s+, focus-fire cascades, 2–4+ deaths / possible loss. **The single tuning lever is the goblin count (sweep 8–14).** Warchief stats are FIXED by spec (2×/1.5× goblin) — never tune the boss to fix balance.

**Acceptance bands (NORMAL difficulty, seeded deterministic runs, heroes = alternating warrior/ranger):**
- H=10: wins ≥ 9/10 seeds AND mean hero deaths ≤ 1.5
- H=8: wins ≥ 7/10 AND mean deaths in [1.0, 4.5]
- H=6: wins ≤ 6/10 OR mean deaths ≥ 3.5

---

# Tickets

## T1 (Agent 05 — GameplaySystems): warchief stats + initial wave logic + config + sim tests

**File lane:** `config.py`, `game/entities/enemy.py`, `game/systems/wave_events.py`, `tests/test_wk137_initial_wave.py` ONLY. DO NOT edit graphics files, UI files, or `game/systems/spawner.py`. DO NOT COMMIT (PM commits).

### T1.a config.py — add next to `WaveEventConfig` (~line 60–70)

```python
@dataclass(frozen=True)
class InitialWaveConfig:
    """WK137: scripted first assault — fires once at trigger_sec, independent of the WK60 table.

    trigger_sec/goblin_count read env overrides so QA and the PM capture rig can
    re-time / re-size the wave without code edits (KINGDOM_INITIAL_WAVE_SEC=3 for captures).
    """
    enabled: bool = True
    trigger_sec: float = float(getenv("KINGDOM_INITIAL_WAVE_SEC", "30.0"))  # sim-seconds
    goblin_count: int = int(getenv("KINGDOM_INITIAL_WAVE_GOBLINS", "10"))   # WK137 tuning lever
    reward_gold: int = 60
    name: str = "Goblin Warband"

INITIAL_WAVE = InitialWaveConfig()
```
Match the module's existing import style for `getenv` (config.py already env-reads `SIM_TICK_HZ` — copy that pattern exactly). Name it "Goblin Warband", NOT "Goblin Raid" — that name is taken by the 2-minute table wave and the HUD must not confuse them.

### T1.b game/entities/enemy.py — new ENEMY_STATS entry + subclass

Add to `ENEMY_STATS` (after `"bandit"`, before `"bandit_lord"`):

```python
"goblin_warchief": EnemyStats(
    # WK137: initial-wave boss — same chassis as goblin, 2x HP / 1.5x attack per spec.
    # Goblin's effective attack is GOBLIN_ATTACK * 2 == 10, so 1.5x => GOBLIN_ATTACK * 3 == 15.
    hp=GOBLIN_HP * 2,            # 60
    attack_power=GOBLIN_ATTACK * 3,  # 15
    speed=GOBLIN_SPEED,          # 90.0
    xp_reward=50,
    gold_reward=40,
    color=(96, 48, 12),          # darker goblin brown — reads "elite" in 2D/procedural frames
    size=24,                     # 18 * 1.33 — renderer scales billboards by size/18 (WK137 T2)
    has_attackers=True,
    is_boss=True,
    name="The Goblin Warchief",
),
```

Add the subclass next to `Goblin` (~line 515), mirroring it exactly:

```python
class GoblinWarchief(Enemy):
    """WK137 initial-wave boss. Stats: ENEMY_STATS["goblin_warchief"]."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y, "goblin_warchief")
```

Do NOT touch `Enemy.__init__`, `find_target`, or any other type's stats.

### T1.c game/systems/wave_events.py — the initial wave

1. Imports: add `GoblinWarchief` to the existing `game.entities.enemy` import block; add `INITIAL_WAVE as _initial_cfg` to the `config` import block.
2. `__init__`: add two flags (NO RNG, no other state):
```python
# WK137: scripted initial assault (fires once, before the scheduled table).
self._initial_wave_done: bool = False
self._initial_warning_emitted: bool = False
```
3. `_spawn_wave`: add a keyword-only param and gate the table-advance lines (currently `self._next_table_index += 1` and `self._warning_emitted = False` near the end):
```python
def _spawn_wave(self, event_def: WaveEventDef, ctx: SystemContext, *, advance_table: bool = True) -> None:
    ...
    if advance_table:
        # Advance index for next wave
        self._next_table_index += 1
        self._warning_emitted = False
```
Everything else in `_spawn_wave` stays byte-identical (the existing call in `update` passes no kwarg → behavior unchanged).
4. New method, called from `update()` immediately after the `_drain_pending_spawns` block and BEFORE `event_def = self._current_event_def()`:
```python
def _update_initial_wave(self, ctx: SystemContext) -> None:
    """WK137: one-shot scripted wave at INITIAL_WAVE.trigger_sec (sim-seconds).

    Digest guard: before the warning moment this does float compares only —
    no RNG draws, no state writes (WK67 window is ticks 0-300 = 5 sim-sec;
    warning fires at trigger-10s=20s, spawn at 30s, both outside it).
    """
    if self._initial_wave_done or not _initial_cfg.enabled:
        return
    trigger = _initial_cfg.trigger_sec
    if (not self._initial_warning_emitted
            and self.elapsed_sec >= trigger - _wave_cfg.warning_seconds):
        self._initial_warning_emitted = True
        ctx.event_bus.emit({
            "type": "wave_incoming",
            "name": _initial_cfg.name,
            "seconds": _wave_cfg.warning_seconds,
        })
    if self.elapsed_sec >= trigger and self._active_wave_def is None:
        event_def = WaveEventDef(
            name=_initial_cfg.name,
            minute=trigger / 60.0,
            composition=[(Goblin, _initial_cfg.goblin_count), (GoblinWarchief, 1)],
            direction="random_edge",
            reward_gold=_initial_cfg.reward_gold,
        )
        self._spawn_wave(event_def, ctx, advance_table=False)
        self._initial_wave_done = True
        ctx.event_bus.emit({
            "type": "hud_message",
            "text": "The Goblin Warchief leads the assault!",
            "color": (255, 80, 80),
        })
```
Known/accepted interactions (do not "fix" these): difficulty count multiplier applies inside `_spawn_wave` — EASY gets ~6 goblins + 1 warchief, HARD gets 15 goblins + 2 warchiefs (`max(1, round(1*1.5)) == 2` — intended escalation). If the initial wave is somehow still alive at 2:00, the table wave waits for it (existing one-wave-at-a-time invariant).

### T1.d tests — `tests/test_wk137_initial_wave.py`

First `grep -r "WaveEventSystem" tests/` and mimic the existing wave-events test harness (stub `SystemContext` with an event-collecting bus, `enemies=[]`, economy stub) — copy its fixture style, do not invent a new one. Required cases:
1. **Warchief stats honor the spec:** `ENEMY_STATS["goblin_warchief"].hp == 2 * ENEMY_STATS["goblin"].hp`, `.attack_power == 15 == 1.5 * ENEMY_STATS["goblin"].attack_power` (goblin's is 10), `.speed == ENEMY_STATS["goblin"].speed`, `is_boss is True`, `name == "The Goblin Warchief"`, `size == 24`. Also construct `GoblinWarchief(0, 0)` and assert instance `hp/max_hp == 60`, `attack_power == 15`, `enemy_type == "goblin_warchief"`, `e.name` set, `e.is_boss is True`.
2. **Timing:** drive `WaveEventSystem.update` with `dt=0.05` and no difficulty (or NORMAL): assert NO `wave_incoming` event and NO enemies before `elapsed_sec < 20.0`; the `wave_incoming` named "Goblin Warband" arrives in the [20.0, 20.1] step; enemies appear in the [30.0, 30.1] step (remember WK128 stagger: tick a few extra times until `_pending_spawns` is empty before counting).
3. **Composition (NORMAL):** exactly `INITIAL_WAVE.goblin_count` enemies with `enemy_type == "goblin"` and exactly 1 with `enemy_type == "goblin_warchief"`.
4. **One-shot:** run on to 60 s — no second initial wave; `_initial_wave_done is True`.
5. **Table unshifted:** after the initial wave fires, assert `_next_table_index == 0` still, and running on to 120 s fires the "Goblin Raid" table wave (its `hud_message` "INCOMING: Goblin Raid!" appears) — proving the schedule didn't move.
6. **Kill-switch:** monkeypatch a disabled config (e.g. `wave_events_module._initial_cfg = InitialWaveConfig(enabled=False)` — module-attr patch, mirror how test_spawner.py monkeypatches `spawner_module.Goblin`) → nothing fires at 30 s.
7. **Difficulty counts:** with a real `DifficultySystem` forced to EASY and to HARD, assert goblin counts `max(1, round(10*0.6)) == 6` and `round(10*1.5) == 15`, warchief count 1 (EASY) and 2 (HARD).

**Verify before reporting done (run all, paste outputs in your log):**
```
python -m pytest tests/test_wk137_initial_wave.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q        # digest MUST stay green
python -m pytest tests/test_spawner.py tests/test_wk61_r10_wave_timing.py tests/test_wk61_r11_wolf_pack_spawn.py -q
python tools/qa_smoke.py --quick
```
Also run one engine-level smoke and paste its output: a throwaway script (do not commit it... actually save as nothing — just run inline with `python -c` or a temp file under tmp/) that builds `GameEngine(headless=True)` with `DETERMINISTIC_SIM=1 SIM_SEED=7`, ticks `engine.update(1/60)` 2,100 times (35 sim-sec), then asserts exactly one alive enemy has `enemy_type == "goblin_warchief"` and ≥1 goblins exist. This proves the wiring works end-to-end in the real engine, not just against stubs.

Write your worker log round (`sprint_id: "wk137_initial_goblin_wave"`, `round_id: "r1"`, `status`, `what_i_changed`, `commands_run`, `evidence`, `blockers`, `follow_ups`) per `.cursor/rules/05-agent-log-conventions.mdc`.

## T2 (Agent 03 — TechnicalDirector): renderer honors boss size + sprite/atlas coverage + name labels

**File lane:** `game/graphics/instanced_unit_renderer.py`, `game/graphics/ursina_unit_sync.py`, `game/graphics/enemy_sprites.py`, `game/graphics/unit_atlas.py`, `tests/test_wk137_boss_scale.py` ONLY. DO NOT edit `game/sim/render_dto.py` (the DTO already carries `size` and `name`), `config.py`, or `game/entities/*`. DO NOT COMMIT (PM commits).

### T2.a per-instance enemy billboard scale (both renderers)

Both modules already duplicate `ENEMY_SCALE` with a "recomputed here identically" convention — follow it: define the SAME helper in BOTH modules (do not cross-import renderer modules):

```python
# WK137: per-instance enemy billboard scale — `size` stat / 18 (the basic-enemy
# baseline), clamped so a bad stat can never explode an instance. 18->1.0x,
# warchief 24->1.33x, bandit_lord 28->1.56x, demon 32->1.78x, dragon 36->2.0x.
_ENEMY_BASE_SIZE = 18.0
_ENEMY_SCALE_MAX_MULT = 2.0

def enemy_billboard_scale(size: int) -> float:
    mult = max(1.0, min(_ENEMY_SCALE_MAX_MULT, float(size or 18) / _ENEMY_BASE_SIZE))
    return ENEMY_SCALE * mult
```

- `instanced_unit_renderer.py` enemy loop (~line 760–790): compute `e_scale = enemy_billboard_scale(e.size)` once per enemy; replace BOTH uses of `ENEMY_SCALE` in that loop — `wy = terrain_y + e_scale * 0.5` and `pack_outside(vx, vy, vz, e_scale, uv, e_scale)`. Leave `pack_hp_bar` untouched. PERF: this is the per-frame hot loop — one multiply/divide per enemy, no allocations, no dict lookups; do NOT add anything else to the loop.
- `ursina_unit_sync.py` enemy loop (~line 248): `s = enemy_billboard_scale(int(getattr(e, "size", 18) or 18))` replacing `s = ENEMY_SCALE`; the existing `sx_e = s * facing_e`, scale tuple, and `terrain_y + s * 0.5` then pick the new value up automatically. The `get_or_create_entity(scale=(s, s, 1), ...)` is creation-time only — verify `_sync_unit_atlas_billboard` receives the per-frame scale tuple `(sx_e, s, 1)` (it does today) so an enemy whose entity was created before this change still syncs to the right size.

### T2.b sprite asset alias + atlas coverage for boss types

`enemy_sprites.py`:
```python
# WK137: boss variants reuse their base type's PNG art when they have no folder
# of their own (assets/sprites/enemies/goblin_warchief/ does not exist; goblin does).
_ASSET_FOLDER_ALIASES = {"goblin_warchief": "goblin"}
```
- In `_try_load_asset_frames`, resolve the folder through the alias: `folder_type = _ASSET_FOLDER_ALIASES.get((enemy_type or "goblin").lower(), enemy_type or "goblin")`.
- In `_type_color`, add boss colors so procedural fallbacks aren't all default brown — match the `ENEMY_STATS` colors: `goblin_warchief` → `(96, 48, 12)`, `bandit_lord` → `(180, 100, 30)`, `demon_overlord` → `(200, 30, 30)`, `dragon` → `(220, 60, 20)`.

`unit_atlas.py` `_build()` (~line 90): extend the packed enemy tuple to
`("goblin", "wolf", "skeleton", "skeleton_archer", "spider", "bandit", "goblin_warchief", "bandit_lord", "demon_overlord", "dragon")`.
This FIXES a pre-existing bug: boss types were never packed, so `lookup_uv("enemy", "bandit_lord", ...)` silently returned the fallback UV (the first packed frame — a hero frame) and bosses rendered with the wrong sprite. After this change the warchief packs real goblin frames (via the T2.b alias) and the three legacy bosses pack their colored procedural frames. Capacity is not a concern (atlas is 2048², 64×64 32-px cells; current usage is well under a quarter).

### T2.c boss name labels

- `ursina_unit_sync.py` (~line 276): prefer the instance name —
  `enemy_label = str(getattr(e, "name", "") or "") or str(getattr(e, "enemy_type", "enemy") or "enemy").replace("_", " ").title()`
  ("The Goblin Warchief" / "The Bandit Lord" instead of "Goblin Warchief"/"Bandit Lord" title-casing of the type key).
- `instanced_unit_renderer.py`: find where `add_label_source("enemy", e, ...)` resolves display text (follow the call) and apply the same name-preference there if it title-cases `enemy_type`. If labels in the instanced path are resolved elsewhere (a label sync module), make the same one-line fix there and ADD that file to your lane — note it in your log.

### T2.d tests — `tests/test_wk137_boss_scale.py`

1. Scale math, both modules agree: for sizes `[12, 18, 24, 28, 32, 36, 48]` assert `instanced.enemy_billboard_scale(s) == unit_sync.enemy_billboard_scale(s)`; assert `enemy_billboard_scale(18) == ENEMY_SCALE` exactly; `enemy_billboard_scale(24) == ENEMY_SCALE * (24/18)`; `enemy_billboard_scale(48) == ENEMY_SCALE * 2.0` (clamp); `enemy_billboard_scale(12) == ENEMY_SCALE` (floor — never smaller than baseline); `enemy_billboard_scale(0)` and `enemy_billboard_scale(None)` return `ENEMY_SCALE` (defensive).
2. Sprite alias: `EnemySpriteLibrary.clips_for("goblin_warchief", size=32)` walk-clip frame count equals `clips_for("goblin", size=32)`'s (proves the PNG folder alias engaged, not the procedural fallback — goblin has real PNG art for all 5 actions).
3. Atlas coverage: first `grep -r "unit_atlas\|UnitAtlas" tests/` and mimic any existing atlas test's headless-pygame setup. Build the atlas and assert keys `("enemy", t, "idle", 0)` for t in the four boss types exist in the UV map (NOT the fallback region) — access the private map the same way existing tests do; if none exist, assert `lookup_uv("enemy", "goblin_warchief", "idle", 0) != lookup_uv("enemy", "definitely_missing_type", "idle", 0)`.

**Verify before reporting done (run all, paste outputs):**
```
python -m pytest tests/test_wk137_boss_scale.py -q
python -c "import game.graphics.instanced_unit_renderer, game.graphics.ursina_unit_sync, game.graphics.unit_atlas, game.graphics.enemy_sprites"   # import seam gate
python -m pytest tests/test_wk67_ai_boundary.py -q
python -m pytest tests/ -q -k "instanced or atlas or unit_sync or sprite"   # existing renderer/parity suites must stay green
python tools/qa_smoke.py --quick
```
SCREENSHOT NOTE: you are headless — per the WK-standing rule for `game/graphics/ursina_*` slices you ship with the import/seam/digest gates above and the PM performs live Ursina captures on the GPU box afterward (warchief vs goblin size, boss labels, Bandit Lord scale). Flag anything you could not visually confirm in `follow_ups`.

Write your worker log round (`sprint_id: "wk137_initial_goblin_wave"`, `round_id: "r1"`, full required fields).

## T3 (Agent 11 — QA, wave 2): balance harness + tuning verdict + full gates

**File lane:** `tools/wk137_balance_probe.py`, `tests/test_wk137_initial_wave_balance.py` ONLY. You do NOT edit config.py — if tuning is needed you REPORT the recommended `goblin_count` and the PM dispatches 05 in r2. DO NOT COMMIT (PM commits).

**Goal:** measure the initial wave against the Sovereign's targets on NORMAL difficulty and recommend the final `goblin_count`.

### Harness design (build `tools/wk137_balance_probe.py` first, the pytest reuses its core)

- Engine per run: copy the reset/seed pattern from `tests/test_wk67_ai_boundary.py::_build_digest_engine` (env `DETERMINISTIC_SIM=1`, `SIM_SEED=<seed>`, `set_sim_seed`, fresh `GameEngine(headless=True)`). Each (seed, hero_count, goblin_count) combination gets a FRESH engine — never reuse.
- **Force NORMAL difficulty explicitly** — DEV_MODE defaults the shared `DifficultySystem` to EASY (game/systems/difficulty.py ~line 67). Locate the difficulty system instance on the sim engine (`SimEngine.difficulty_system`) and set NORMAL before ticking. Assert it took effect; an EASY-run matrix is worthless.
- **Isolate the wave** (primary matrix): after engine setup, neutralize the other two spawn sources — set the trickle spawner's `initial_no_spawn_ms` to `10**9` (the attribute exists; `tests/test_spawner.py` sets it), and clear the lair list on the lair system (find the instance on the sim engine — `game/systems/lairs.py`; lairs are placed in `setup_initial_state`). Then assert the enemies list is EMPTY on the tick before the wave spawns — this assertion is your proof of isolation.
- Seed heroes: copy the approach of `tests/test_wk67_ai_boundary.py::_seed_digest_heroes` (constructs heroes near the castle and registers them). Hero mix = alternating warrior/ranger ONLY (the two starting guilds; clerics need a temple the player doesn't have at 30 s). Keep direct Python refs to the hero objects — permadeath culling REMOVES dead heroes from `engine` lists (WK123 C2), so counting survivors via the live list undercounts; count via your refs' `is_alive`/`hp`.
- Wave capture: tick `engine.update(1/60)` to 30 sim-sec (1800 ticks); the wave constructs over a few ticks (WK128 stagger) — locate the `WaveEventSystem` instance on the sim engine, wait until its `_pending_spawns` is empty, then snapshot `list(wave_sys._active_wave_enemies)` (it resets on clear, so snapshot immediately).
- Outcome: continue ticking up to +120 sim-sec (7200 ticks) past spawn. **win** = every snapshot enemy `is_alive == False` AND the castle still standing; record `hero_deaths` (your refs with `is_alive False`), `time_to_clear_sec`, survivors' mean hp.
- Matrix: seeds `[11, 23, 37, 41, 53, 67, 71, 83, 97, 101]` × H ∈ (10, 8, 6) at the shipped `goblin_count`. Then a tuning sweep at H=8: `KINGDOM_INITIAL_WAVE_GOBLINS` ∈ 8..14 × 5 seeds (env var must be set BEFORE config import in the subprocess — run each sweep cell as a subprocess like the digest test does, or set env and reimport carefully; subprocess is safer and the digest test shows the pattern).
- Probe output: a per-cell table (seed, H, count, win, deaths, t_clear) + summary per (H, count) + a one-line RECOMMENDATION: the count whose H=10/8/6 summary best fits the bands below.

### Acceptance bands (NORMAL, the shipped count) — these are the pytest asserts
- H=10: wins ≥ 9/10 AND mean deaths ≤ 1.5
- H=8: wins ≥ 7/10 AND mean deaths in [1.0, 4.5]
- H=6: wins ≤ 6/10 OR mean deaths ≥ 3.5

`tests/test_wk137_initial_wave_balance.py` runs a 3-seed subset (`[11, 23, 37]`) × H ∈ (10, 8, 6) with proportional bands (H=10: 3/3 wins, ≤1.5 mean deaths; H=8: ≥2/3 wins, deaths band; H=6: ≤2/3 wins OR ≥3.5 mean deaths) so the suite stays fast; check the repo's slow-test marker convention (`grep -r "slow" tests/conftest.py pytest.ini setup.cfg pyproject.toml`) and mark accordingly if one exists. The runs are deterministic per seed — same numbers every rerun, so the asserts will not flake.

### Realistic sanity pass (memory lesson: sanitized harnesses mask bugs)
One full-systems run (spawner + lairs LEFT ON), H=8, seed 11, to 180 sim-sec: assert no exception, the initial wave fired at 30 s, and a `wave_cleared` OR ongoing combat state is reached. Log the outcome — no balance asserts here.

**Verify before reporting done (run all, paste outputs + the full probe table):**
```
python tools/wk137_balance_probe.py            # full matrix + sweep + recommendation
python -m pytest tests/test_wk137_initial_wave_balance.py -q
python -m pytest tests/test_wk67_ai_boundary.py -q
python -m pytest tests/ -q                     # full suite
python tools/qa_smoke.py --quick
```
**Verdict format (end of your log):** `BALANCE: PASS at goblin_count=N` or `BALANCE: FAIL — recommend goblin_count=M (H=10: w/d, H=8: w/d, H=6: w/d at M)`. If FAIL, the PM dispatches 05 for a one-constant r2 retune and you re-run the matrix.

Write your worker log round (`sprint_id: "wk137_initial_goblin_wave"`, `round_id: "r1"`, full required fields).

---

## Send list

- Wave 1 (parallel, disjoint lanes): **05** (T1), **03** (T2)
- Wave 2: **11** (T3)
- r2 (conditional, only if 11 reports BALANCE: FAIL): 05 sets `goblin_count` to 11's recommendation; 11 re-runs the matrix.
- do_not_send: 02, 04, 06, 07, 08, 09, 10, 12, 13, 14, 15 (no UI code — HUD events already wired; no art assets — goblin PNGs reused; 10's perf concern is bounded to one multiply in the enemy loop and is covered by 03's constraint + PM capture).

## PM gates before close (PM session, not agents)

1. Live Ursina captures on the GPU box (`tools/run_ursina_capture_once.py`, `KINGDOM_INITIAL_WAVE_SEC=3` to fire the wave during capture; crop+upscale per memory): (a) warchief beside a goblin — visibly ~1.3× with "The Goblin Warchief" label; (b) the wave_incoming countdown banner; (c) a Bandit Lord — now larger AND no longer the wrong sprite; (d) legacy (non-instanced) path spot-check if an env toggle exists; (e) wave-cleared message. Broad coverage — every visual change path, not just the agent's scenario.
2. `python tools/qa_smoke.py --quick` PASS on the final tree; digest green.
3. Human gates: Sovereign playtest, commit/push (PM commits only when Jaimie says).

## Known/deferred (write into the close round)
- HP-bar dims stay the fixed per-kind spec — a 2× dragon gets a standard-size bar (polish later if Jaimie cares).
- Pause-menu difficulty multipliers give HARD two warchiefs (round(1.5)=2) — intended.
- The pygame 2D fallback renderer already honored `size` — untouched.
