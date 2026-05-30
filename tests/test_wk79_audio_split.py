"""WK79 Round C-3 seam tests — AudioSystem split into the ``game/audio/`` package.

WK79 moved the cohesive clusters out of the 513-LOC ``game/audio/audio_system.py``
god-file into focused modules, using the WK69/WK75-78 pure-move pattern (functions
take the live ``AudioSystem`` as ``audio``; ``self.`` -> ``audio.``):

* ``game/audio/contract.py``    — ``AUDIO_EVENT_MAP`` + ``SOUND_COOLDOWNS_MS``
* ``game/audio/sfx_cache.py``   — ``_assets_dir`` / ``_load_sfx`` / ``play_sfx``
* ``game/audio/mixer_volume.py``— the 6 volume getters/setters + ``_apply_ambient_volume``
* ``game/audio/ambient.py``     — ``set_ambient`` / ``stop_ambient`` /
                                  ``start_interior_ambient`` / ``stop_interior_ambient`` /
                                  ``update_enemy_ambient`` (+ ``_INTERIOR_AMBIENT_MAP``)

``AudioSystem`` keeps the event-dispatch core (``__init__`` / ``on_event`` /
``_emit_single_event`` / ``set_listener_view`` / ``_is_audible_world_event``) and a
1-line delegating wrapper of the same name+signature for every moved method, so
engine.py's call sites are unchanged.

This is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-test audio behavior
(that is covered byte-identically by the full suite + qa_smoke audio-event dispatch).
It proves the *seam*:

1. all four new package modules import;
2. the contract dicts are single-source — defined non-empty in ``contract.py`` and
   re-imported into ``audio_system`` by *identity* (the very same objects);
3. each moved method on ``AudioSystem`` DELEGATES to its module function, passing the
   live ``AudioSystem`` as the first positional arg and forwarding args + return;
4. an AST/import guard: the new modules (sfx_cache / mixer_volume / ambient) do NOT
   import ``game.audio.audio_system`` at module load time (TYPE_CHECKING-only) — i.e.
   no module-level import cycle.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

# Headless SDL/audio — AudioSystem + the audio package pull in pygame transitively.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.audio import (  # noqa: E402  (after SDL env)
    ambient,
    audio_system as audio_system_mod,
    contract,
    mixer_volume,
    sfx_cache,
)
from game.audio.audio_system import AudioSystem  # noqa: E402


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_audio() -> AudioSystem:
    """Build a real AudioSystem with audio disabled.

    ``enabled=False`` short-circuits ``__init__`` before any mixer init / SFX load,
    so no real audio device is needed. The delegation tests monkeypatch the module
    function, so the wrapper-target's body (which would touch pygame) never runs.
    """
    return AudioSystem(enabled=False)


# ---------------------------------------------------------------------------
# 1. All four new package modules import.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, expected_name",
    [
        (contract, "game.audio.contract"),
        (sfx_cache, "game.audio.sfx_cache"),
        (mixer_volume, "game.audio.mixer_volume"),
        (ambient, "game.audio.ambient"),
    ],
)
def test_package_modules_import(module, expected_name):
    assert module is not None, f"{expected_name} failed to import"
    assert module.__name__ == expected_name


# ---------------------------------------------------------------------------
# 2. Contract is single-source: non-empty dicts in contract.py, re-imported
#    into audio_system by IDENTITY (the very same objects).
# ---------------------------------------------------------------------------

def test_contract_dicts_non_empty():
    assert isinstance(contract.AUDIO_EVENT_MAP, dict)
    assert isinstance(contract.SOUND_COOLDOWNS_MS, dict)
    assert contract.AUDIO_EVENT_MAP, "AUDIO_EVENT_MAP is empty"
    assert contract.SOUND_COOLDOWNS_MS, "SOUND_COOLDOWNS_MS is empty"


def test_audio_system_reimports_contract_by_identity():
    # audio_system re-imports the canonical objects; not a copy.
    assert audio_system_mod.AUDIO_EVENT_MAP is contract.AUDIO_EVENT_MAP, (
        "audio_system.AUDIO_EVENT_MAP must be contract.AUDIO_EVENT_MAP (single source)"
    )
    assert audio_system_mod.SOUND_COOLDOWNS_MS is contract.SOUND_COOLDOWNS_MS, (
        "audio_system.SOUND_COOLDOWNS_MS must be contract.SOUND_COOLDOWNS_MS (single source)"
    )


# ---------------------------------------------------------------------------
# 3. Each moved method on AudioSystem delegates to its module function,
#    forwarding (audio, *args) and returning the module function's result.
#
# Representative coverage across all four moved-method modules:
#   mixer_volume: set_master_volume, get_master_volume, _apply_ambient_volume
#   sfx_cache:    play_sfx, _load_sfx
#   ambient:      set_ambient, update_enemy_ambient
#
# ``call_args`` is what the wrapper is invoked with; ``expected_forwarded`` is the
# positional tail the module fn should receive after the AudioSystem. They differ
# for set_ambient/play_sfx, whose wrappers normalise optional params to their
# defaults and forward them positionally (e.g. play_sfx -> (sound_key, 1.0)).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, fn_name, wrapper_name, call_args, expected_forwarded",
    [
        (mixer_volume, "set_master_volume", "set_master_volume", (0.5,), (0.5,)),
        (mixer_volume, "get_master_volume", "get_master_volume", (), ()),
        (mixer_volume, "_apply_ambient_volume", "_apply_ambient_volume", (), ()),
        # play_sfx wrapper forwards the volume default (1.0) positionally.
        (sfx_cache, "play_sfx", "play_sfx", ("ui_click",), ("ui_click", 1.0)),
        (sfx_cache, "_load_sfx", "_load_sfx", (), ()),
        # set_ambient wrapper forwards (track_name, volume default 0.4) positionally.
        (ambient, "set_ambient", "set_ambient", ("ambient_loop",), ("ambient_loop", 0.4)),
        (ambient, "update_enemy_ambient", "update_enemy_ambient", ([],), ([],)),
    ],
)
def test_wrapper_delegates_to_module_function(
    monkeypatch, module, fn_name, wrapper_name, call_args, expected_forwarded
):
    audio = _make_audio()
    calls = []
    sentinel = object()

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(module, fn_name, spy)

    wrapper = getattr(audio, wrapper_name)
    result = wrapper(*call_args)

    # Wrapper returned exactly what the module function returned.
    assert result is sentinel, f"{wrapper_name} did not forward the return value"

    # Module function fired exactly once.
    assert len(calls) == 1, f"{module.__name__}.{fn_name} fired {len(calls)} times (want 1)"

    args, kwargs = calls[0]
    # First positional arg is the live AudioSystem instance.
    assert args[0] is audio, f"{wrapper_name} did not pass the AudioSystem as first arg"
    # Remaining args forwarded as expected (including wrapper-supplied defaults).
    assert args[1:] == expected_forwarded, (
        f"{wrapper_name} forwarded {args[1:]!r}, expected {expected_forwarded!r}"
    )
    assert kwargs == {}, f"{wrapper_name} forwarded unexpected kwargs {kwargs!r}"


# ---------------------------------------------------------------------------
# 4. AST/import guard: the moved-method modules do NOT import
#    game.audio.audio_system at module load time (TYPE_CHECKING-only / no cycle).
# ---------------------------------------------------------------------------

_AUDIO_SYSTEM_TARGET = "game.audio.audio_system"


def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    Walks only the module body's direct children (and the bodies of any top-level
    ``if`` blocks whose test is NOT ``TYPE_CHECKING``). Imports nested inside function
    or class bodies are *runtime-lazy* and cannot create an import cycle, so they are
    intentionally excluded.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []

    def _scan(import_node):
        if isinstance(import_node, ast.Import):
            for alias in import_node.names:
                if alias.name == target or alias.name.startswith(target + "."):
                    found.append(ast.dump(import_node))
        elif isinstance(import_node, ast.ImportFrom):
            mod = import_node.module or ""
            if mod == target or mod.startswith(target + "."):
                found.append(ast.dump(import_node))

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _scan(node)
        elif isinstance(node, ast.If):
            test = node.test
            is_type_checking = isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
            if is_type_checking:
                continue  # TYPE_CHECKING-only imports are allowed (never executed)
            for sub in node.body + node.orelse:
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    _scan(sub)

    return found


@pytest.mark.parametrize(
    "rel_path",
    [
        "game/audio/sfx_cache.py",
        "game/audio/mixer_volume.py",
        "game/audio/ambient.py",
    ],
)
def test_no_module_level_audio_system_import(rel_path):
    path = _REPO_ROOT / rel_path
    assert path.exists(), f"{rel_path} missing"
    offending = _module_level_imports_of(path, _AUDIO_SYSTEM_TARGET)
    assert not offending, (
        f"{rel_path} imports {_AUDIO_SYSTEM_TARGET} at module load time (import-cycle "
        f"risk); the AudioSystem import must be TYPE_CHECKING-only. Offending: {offending}"
    )


@pytest.mark.parametrize(
    "rel_path",
    [
        "game/audio/sfx_cache.py",
        "game/audio/mixer_volume.py",
        "game/audio/ambient.py",
    ],
)
def test_type_checking_import_present(rel_path):
    """Sanity: the AudioSystem import IS present, but only under TYPE_CHECKING."""
    path = _REPO_ROOT / rel_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tc_imports = []
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                for sub in node.body:
                    if (
                        isinstance(sub, ast.ImportFrom)
                        and sub.module == _AUDIO_SYSTEM_TARGET
                    ):
                        tc_imports.append([a.name for a in sub.names])
    assert ["AudioSystem"] in tc_imports, (
        f"{rel_path} should TYPE_CHECKING-import AudioSystem"
    )
