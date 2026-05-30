# WK79 Sprint Plan — Round C-3: audio_system.py → game/audio/ package

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; audio_system.py (513 LOC) split into a focused `game/audio/` package behind a thin AudioSystem facade; behavior byte-identical.
**Predecessors:** WK68-78. **Roadmap:** Round C (audio area: split the god-file + establish the contract as a single source).

## 0. TL;DR
`game/audio/audio_system.py` (513 LOC) mixes the audio-event contract, the SFX loader/cache, visibility gating, event dispatch, ambient playback, and mixer volume in one class. WK79 extracts the cohesive clusters into modules using the proven pure-move pattern (functions take the `AudioSystem` as `audio`; the methods become 1-line delegating wrappers so engine.py's call sites — `on_event`/`set_listener_view`/`set_*_volume`/`set_ambient`/etc. — are unchanged), and lifts the contract dicts into `contract.py`. **Audio is fully isolated** from sim/render/AI, so a structurally-sound split (imports OK + full suite + qa_smoke audio paths run without crash) is reliably correct. The WK67 digest is unaffected (audio doesn't touch the sim). PM writes no code.

## 1. Scope
**IN — create `game/audio/` modules and move into them:**
- `game/audio/contract.py`: `AUDIO_EVENT_MAP` (audio_system.py:23) + `SOUND_COOLDOWNS_MS` (55) — the single source of truth for the audio event→sfx contract. Re-import them into audio_system.py (`from game.audio.contract import AUDIO_EVENT_MAP, SOUND_COOLDOWNS_MS`) so any other reader is unaffected.
- `game/audio/mixer_volume.py`: the 6 volume methods (`set_master_volume`/`get_master_volume`/`set_music_volume`/`get_music_volume`/`set_sfx_volume`/`get_sfx_volume`) + `_apply_ambient_volume` if cleanly co-located, as functions taking `audio`.
- `game/audio/ambient.py`: `set_ambient`/`stop_ambient`/`start_interior_ambient`/`stop_interior_ambient`/`update_enemy_ambient`, as functions taking `audio`.
- `game/audio/sfx_cache.py`: `_load_sfx`/`_assets_dir`/`play_sfx`, as functions taking `audio` (`_assets_dir` is a @staticmethod — keep it a plain function).
- `AudioSystem` (stays in audio_system.py as the facade) KEEPS: `__init__`, `on_event`, `_emit_single_event`, `set_listener_view`, `_is_audible_world_event` (the event-dispatch core), and a 1-line delegating wrapper for every moved method (same names + signatures).

**OUT:** unifying the contract across enemy_sounds.py / events.py / EVENT_CONTRACT.md (cluster-5 cross-file dedup — a separate sprint); the listener-position / 3D-attenuation fix (audit audio finding — behavior change, defer); any behavior change. **Do NOT touch game/audio/enemy_sounds.py.**

## 2. Pattern (WK75-78, verbatim)
```python
# game/audio/mixer_volume.py
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game.audio.audio_system import AudioSystem

def set_master_volume(audio: "AudioSystem", volume_0_to_1: float) -> None:
    # EXACT body, self.->audio.
    ...
```
```python
# game/audio/audio_system.py
def set_master_volume(self, volume_0_to_1):
    from game.audio import mixer_volume
    return mixer_volume.set_master_volume(self, volume_0_to_1)
```
TYPE_CHECKING-only AudioSystem import; no cycle; copy each method's leaf imports (pygame, os, config volume defaults, etc.); preserve behavior exactly.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **739 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green (its scenarios emit audio events through on_event/play_sfx — exercises the moved code).
- **E.** `game/audio/{contract,mixer_volume,ambient,sfx_cache}.py` exist; `AUDIO_EVENT_MAP`/`SOUND_COOLDOWNS_MS` defined once in contract.py (re-imported by audio_system); the moved method names still on AudioSystem as delegating wrappers; audio_system.py smaller (~513 → ~280); no import cycle.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 14):** extract the package + wrappers + contract. Verify suite + qa_smoke + digest.
- **W2 (Agent 11):** seam test (modules exist + wrappers delegate + contract single-source) + full DoD.

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| A moved method references a name only imported at audio_system top → NameError | Med | copy each method's imports; full suite + qa_smoke (emits audio events) catch it |
| Import cycle (module ↔ audio_system) | Med | TYPE_CHECKING-only import (proven WK75-78) |
| A volume/ambient path breaks but no test plays sound | Low-Med | qa_smoke emits events through the dispatch; full suite imports; audio is isolated so a structural break fails to import/crashes on event |
| contract dicts not byte-identical after move | Low | move the dict literals verbatim; a quick equality check |

## 6. Success
The AudioSystem's loader/visibility/ambient/mixer/contract live in focused `game/audio/` modules behind a thin facade, audio behaves identically — proven by 739+ green tests, clean determinism guard, unchanged digest, and green qa_smoke (which runs audio event dispatch).

## 7. Kickoff
Roster: 14 SoundDirector (extraction W1), 11 (verify + DoD W2), 03 (consult on import structure). Order: 14 W1 → PM gate (suite + qa_smoke + digest) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; PURE MOVE, behavior-preserving, keep wrapper names, TYPE_CHECKING-only import; NO screenshots (audio); own log; DO NOT COMMIT.
Follow-ups: cross-file audio contract unification (enemy_sounds/events/doc); 3D listener-attenuation fix; the BIG presentation splits (hud/ursina_renderer/ursina_app); Move 9; world.py; config package; clusters 3/4; Round D AI; Round E audit; zombie purge.
