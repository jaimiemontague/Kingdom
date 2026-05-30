"""WK86 Round B-3 seam tests — one-shot world generation moved into game/worldgen.py.

WK86 moved ``generate_terrain`` / ``generate_heightmap`` / ``flatten_building_footprints``
VERBATIM out of ``game/world.py`` (483 -> 278 LOC) into a new ``game/worldgen.py``.
Each moved function takes the ``World`` instance as ``world`` and mutates it in
place; ``World`` keeps three 1-line **delegating wrappers** (same names) so every
existing caller (``World.__init__``, ``setup_initial_state``, tools/tests) is
unchanged. The ``flatten_building_footprints`` wrapper takes ``buildings`` and
forwards ``(self, buildings)``.

Import-cycle safety is by construction: ``worldgen.py`` imports ``World`` only
under ``TYPE_CHECKING`` and lazy-imports ``TileType`` *inside* the functions;
``game.world`` imports ``worldgen`` only lazily inside the wrappers. So neither
module imports the other at module load time and there is no cycle in either
import order.

This is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-derive the *behavior*
of generation tile-by-tile — that is covered byte-identically by the full suite
and the WK67 AI-decision digest (``b73961…``; the seeded world the digest scenario
runs on is produced by exactly these functions, so any generation drift breaks it).
This file proves the *seam* plus a **belt-and-suspenders world-snapshot pin**:

1. ``game.worldgen`` exposes ``generate_terrain`` + ``generate_heightmap`` +
   ``flatten_building_footprints`` (all callable), in the new home.
2. ``World.generate_terrain`` / ``World.generate_heightmap`` /
   ``World.flatten_building_footprints`` are delegating wrappers — spy +
   monkeypatch the ``worldgen`` function, call the wrapper on a ``World``
   instance, and assert the worldgen function was invoked with that ``World``
   (and, for flatten, the forwarded ``buildings``). The lazy import inside each
   wrapper means the monkeypatch is what runs.
3a. AST guard: ``worldgen.py`` has NO module-top ``import game.world`` /
    ``from game.world import …`` (``World`` is TYPE_CHECKING-only; ``TileType``
    is lazy-imported inside the functions, which is runtime-only and excluded).
3b. No module-load cycle — in a FRESH subprocess, ``import game.worldgen`` then
    ``import game.world`` succeeds, AND the reverse order succeeds.
4. WORLD-SNAPSHOT PIN: with a fixed seed (``set_sim_seed(3)``) build a ``World``,
   and assert a stable sha256 of the resulting tile grid + the generated
   heightmap matches a recorded baseline. This pins the generated world
   byte-identical beyond the AI digest. Computed in a FRESH subprocess with a
   pinned ``SIM_SEED`` env: the heightmap's Perlin ``base`` reads
   ``config.SIM_SEED`` (read from the env at import; some suite modules set
   ``os.environ['SIM_SEED']='42'`` at import time — see the WK67 PM NOTE), so the
   pin must run in a clean process with ``SIM_SEED`` pinned or it would flap by
   pytest collection order. The tile grid uses the ``world_gen`` sub-RNG (seeded
   by ``set_sim_seed``) and is independent of ``config.SIM_SEED``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import game.worldgen as worldgen


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent

_WORLDGEN_REL_PATH = "game/worldgen.py"
_WORLD_TARGET = "game.world"

_MOVED_FUNCTIONS = ("generate_terrain", "generate_heightmap", "flatten_building_footprints")


# ---------------------------------------------------------------------------
# 1. worldgen exposes the three moved functions, callable, in the new home.
# ---------------------------------------------------------------------------

def test_worldgen_exposes_moved_generation_functions():
    assert worldgen.__name__ == "game.worldgen"
    for name in _MOVED_FUNCTIONS:
        fn = getattr(worldgen, name, None)
        assert fn is not None, f"game.worldgen.{name} missing"
        assert callable(fn), f"game.worldgen.{name} is not callable"


# ---------------------------------------------------------------------------
# 2. The World methods are delegating wrappers. Spy + monkeypatch the worldgen
#    function, call the wrapper on a World instance, and assert the worldgen
#    function ran and received that exact World (and forwarded args). Each wrapper
#    imports the worldgen function *lazily at call time*, so the monkeypatched
#    object is the one that runs — this is the load-bearing seam.
#
#    Note: World.__init__ auto-runs generate_terrain()/generate_heightmap(); we
#    build the instance via object.__new__ to isolate ONE wrapper call per spy.
# ---------------------------------------------------------------------------

def _bare_world():
    """A World instance WITHOUT running __init__ (no auto-generation)."""
    from game.world import World

    return object.__new__(World)


def test_generate_terrain_is_delegating_wrapper(monkeypatch):
    received = []

    def _spy(world):
        received.append(world)
        return None

    monkeypatch.setattr(worldgen, "generate_terrain", _spy)
    world = _bare_world()
    world.generate_terrain()
    assert received == [world], (
        "World.generate_terrain must delegate to game.worldgen.generate_terrain, "
        f"passing the World instance. invocations={received!r}"
    )


def test_generate_heightmap_is_delegating_wrapper(monkeypatch):
    received = []

    def _spy(world):
        received.append(world)
        return None

    monkeypatch.setattr(worldgen, "generate_heightmap", _spy)
    world = _bare_world()
    world.generate_heightmap()
    assert received == [world], (
        "World.generate_heightmap must delegate to game.worldgen.generate_heightmap, "
        f"passing the World instance. invocations={received!r}"
    )


def test_flatten_building_footprints_is_delegating_wrapper(monkeypatch):
    received = []

    def _spy(world, buildings):
        received.append((world, buildings))
        return None

    monkeypatch.setattr(worldgen, "flatten_building_footprints", _spy)
    world = _bare_world()
    sentinel_buildings = ["b1", "b2"]
    world.flatten_building_footprints(sentinel_buildings)
    assert len(received) == 1, (
        "World.flatten_building_footprints must delegate exactly once to "
        f"game.worldgen.flatten_building_footprints. invocations={received!r}"
    )
    got_world, got_buildings = received[0]
    assert got_world is world, "flatten wrapper did not forward the World instance"
    assert got_buildings is sentinel_buildings, (
        "flatten wrapper did not forward the `buildings` argument unchanged"
    )


# ---------------------------------------------------------------------------
# 3a. AST guard: worldgen.py has NO module-top import of game.world.
#
#     The wrappers import worldgen lazily, and worldgen references World only
#     under TYPE_CHECKING and lazy-imports TileType *inside* the functions. For
#     the seam to be cycle-free, worldgen.py must never import game.world at
#     module load time. This walks the module body's direct children plus the
#     bodies of any top-level non-TYPE_CHECKING ``if`` blocks; lazy imports inside
#     function bodies are runtime-only and intentionally excluded.
# ---------------------------------------------------------------------------

def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    Matches ``target`` as a dotted module (``import X`` / ``from X import …``) and
    as a bare leaf (so ``from game import world`` is caught too). TYPE_CHECKING
    blocks are skipped (those imports are never executed at runtime). Imports
    nested inside function/class bodies are NOT walked — those are lazy/runtime.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    leaf = target.rsplit(".", 1)[-1]
    parent = target.rsplit(".", 1)[0] if "." in target else ""

    def _scan(import_node):
        if isinstance(import_node, ast.Import):
            for alias in import_node.names:
                if alias.name == target or alias.name.startswith(target + "."):
                    found.append(ast.dump(import_node))
        elif isinstance(import_node, ast.ImportFrom):
            mod = import_node.module or ""
            # Direct `from game.world import ...`
            if mod == target or mod.startswith(target + "."):
                found.append(ast.dump(import_node))
            # `from game import world`
            elif parent and mod == parent:
                for alias in import_node.names:
                    if alias.name == leaf:
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


def test_worldgen_has_no_module_level_world_import():
    path = _REPO_ROOT / _WORLDGEN_REL_PATH
    assert path.exists(), f"{_WORLDGEN_REL_PATH} missing"
    offending = _module_level_imports_of(path, _WORLD_TARGET)
    assert not offending, (
        f"{_WORLDGEN_REL_PATH} imports {_WORLD_TARGET} at module load time — the "
        f"World wrappers already import worldgen lazily, so a top-level "
        f"worldgen->world import would form a cycle. World must be TYPE_CHECKING-"
        f"only and TileType lazy-imported inside the functions. Offending: {offending}"
    )


# ---------------------------------------------------------------------------
# 3b. No module-load cycle: a FRESH interpreter can import the two modules in
#     EITHER order without an ImportError (a top-level cycle would raise here).
#     Run in a subprocess so the import truly happens cold (neither module is in
#     this session's sys.modules). One subprocess per order.
# ---------------------------------------------------------------------------

def _fresh_import_order_ok(first: str, second: str) -> subprocess.CompletedProcess:
    code = (
        f"import {first}\n"
        f"import {second}\n"
        "print('WK86_IMPORT_OK')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=120,
    )


@pytest.mark.parametrize(
    "first, second",
    [
        ("game.worldgen", "game.world"),
        ("game.world", "game.worldgen"),
    ],
)
def test_no_module_load_cycle_fresh_import(first, second):
    proc = _fresh_import_order_ok(first, second)
    assert proc.returncode == 0, (
        f"fresh import order `import {first}; import {second}` failed (a module-load "
        f"cycle would raise here).\nreturncode={proc.returncode}\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )
    assert "WK86_IMPORT_OK" in proc.stdout, (
        f"fresh import of {first} then {second} did not complete cleanly.\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    )


# ===========================================================================
# 4. World-snapshot pin (belt-and-suspenders beyond the b73961… AI digest).
# ===========================================================================
#
# Golden hashes captured from current HEAD (post-extraction) with set_sim_seed(3)
# and SIM_SEED=1 pinned in the env. The tile grid is hashed row-by-row as ints;
# the heightmap row-by-row as 6-dp-rounded floats. These pin the generated world
# byte-identical: any reorder/change in the moved RNG calls, the WK53 heightmap
# passes, or the terrain_height writes shifts one of these and goes red.
#
# WHY A SUBPROCESS WITH A PINNED ENV: the heightmap's Perlin octaves use
# ``base = int(config.SIM_SEED)``; config.SIM_SEED is read from the env at import
# (config.py: ``SIM_SEED = int(os.getenv("SIM_SEED", "1"))``) and is NOT changed
# by set_sim_seed. Some suite modules (tests/perf_*stress*.py) set
# os.environ["SIM_SEED"]="42" at import time, which pytest collection inherits, so
# an in-process pin would flap by collection order (verified: SIM_SEED=42 changes
# the heightmap hash). Pinning SIM_SEED=1 in a fresh process makes the pin stable
# regardless of suite ordering — the SAME bulletproofing the WK67 keystone uses.
_SNAPSHOT_SEED = 3
_SNAPSHOT_SIM_SEED_ENV = "1"
_SNAPSHOT_TILES_HASH = "1418f9617bb7d8374cd53efae6f59597187c19256671f361c81003fd95ce5c9a"
_SNAPSHOT_HEIGHTMAP_HASH = "87f69ce3fbac1cdd8c23fbd6af5624a87934c0cfcf2ebf33e677a21f8f5c22ea"
_SNAPSHOT_DIMS = (250, 250)            # MAP_WIDTH x MAP_HEIGHT at capture time
_SNAPSHOT_GRID_DIMS = (501, 501)       # heightmap fence-post grid (2*N+1)
_SNAPSHOT_STDOUT_MARKER = "WK86_WORLD_SNAPSHOT="


def _compute_world_snapshot_in_subprocess() -> dict:
    """Build a seeded World in a FRESH interpreter and return its snapshot dict.

    Returns a dict with keys: tiles_hash, heightmap_hash, heightmap_present,
    width, height, grid_w, grid_h. SIM_SEED is pinned in the env so the
    heightmap's Perlin base is byte-stable regardless of pytest collection order.
    """
    import json

    code = (
        "import hashlib, json, config\n"
        "from game.sim.determinism import set_sim_seed\n"
        f"set_sim_seed({_SNAPSHOT_SEED})\n"
        "from game.world import World\n"
        "w = World()\n"
        "hg = hashlib.sha256()\n"
        "for row in w.tiles:\n"
        "    hg.update(repr(tuple(int(t) for t in row)).encode())\n"
        "present = w.heightmap is not None\n"
        "hm = hashlib.sha256()\n"
        "for row in (w.heightmap or []):\n"
        "    hm.update(repr(tuple(round(float(v), 6) for v in row)).encode())\n"
        "out = {\n"
        "    'tiles_hash': hg.hexdigest(),\n"
        "    'heightmap_hash': hm.hexdigest(),\n"
        "    'heightmap_present': present,\n"
        "    'width': int(w.width), 'height': int(w.height),\n"
        "    'grid_w': int(w.heightmap_grid_w), 'grid_h': int(w.heightmap_grid_h),\n"
        "    'sim_seed': int(config.SIM_SEED),\n"
        "}\n"
        f"print('{_SNAPSHOT_STDOUT_MARKER}' + json.dumps(out))\n"
    )
    import os

    env = dict(os.environ)
    env["SIM_SEED"] = _SNAPSHOT_SIM_SEED_ENV
    env["DETERMINISTIC_SIM"] = "1"
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        cwd=str(_REPO_ROOT),
    )
    for line in proc.stdout.splitlines():
        if line.startswith(_SNAPSHOT_STDOUT_MARKER):
            return json.loads(line[len(_SNAPSHOT_STDOUT_MARKER):])
    raise AssertionError(
        "subprocess did not print the world snapshot.\n"
        f"returncode={proc.returncode}\nstdout(tail)={proc.stdout[-2000:]}\n"
        f"stderr(tail)={proc.stderr[-2000:]}"
    )


def test_world_snapshot_is_byte_identical():
    """A fixed-seed World generates the byte-identical tile grid + heightmap.

    Belt-and-suspenders beyond the AI-decision digest: this pins the GENERATED
    WORLD itself (the artifact the extraction moved), so a behavior change in
    generate_terrain/generate_heightmap is caught even if it somehow did not move
    the 300-tick AI digest. Computed in a fresh subprocess with SIM_SEED pinned so
    it is stable regardless of pytest collection order.
    """
    snap = _compute_world_snapshot_in_subprocess()

    # config.SIM_SEED was actually pinned in the subprocess (guards the rationale).
    assert snap["sim_seed"] == int(_SNAPSHOT_SIM_SEED_ENV), (
        "subprocess did not see the pinned SIM_SEED — the heightmap baseline would "
        f"not be reproducible. got config.SIM_SEED={snap['sim_seed']}"
    )

    # Map dimensions match the capture (a MAP_WIDTH/HEIGHT change would legitimately
    # require recapturing, but should not pass silently against the old hash).
    assert (snap["width"], snap["height"]) == _SNAPSHOT_DIMS, (
        f"map dims changed {(snap['width'], snap['height'])} != {_SNAPSHOT_DIMS} — "
        "recapture the world-snapshot baseline if this map-size change is intended"
    )

    # Tile grid: independent of config.SIM_SEED (uses the world_gen sub-RNG seeded
    # by set_sim_seed). MUST be byte-identical.
    assert snap["tiles_hash"] == _SNAPSHOT_TILES_HASH, (
        "generated tile grid drifted from the recorded baseline — generate_terrain "
        "is no longer byte-identical (RNG call order / lake / forest / path / trim "
        f"changed). got={snap['tiles_hash']} baseline={_SNAPSHOT_TILES_HASH}"
    )

    # Heightmap: depends on config.SIM_SEED (pinned above) + the WK53 passes.
    if not snap["heightmap_present"]:
        pytest.skip(
            "heightmap is None (the `noise` package is unavailable in this env) — "
            "tile-grid pin still asserted; heightmap pin skipped"
        )
    assert (snap["grid_w"], snap["grid_h"]) == _SNAPSHOT_GRID_DIMS, (
        f"heightmap grid dims changed {(snap['grid_w'], snap['grid_h'])} != "
        f"{_SNAPSHOT_GRID_DIMS}"
    )
    assert snap["heightmap_hash"] == _SNAPSHOT_HEIGHTMAP_HASH, (
        "generated heightmap drifted from the recorded baseline — generate_heightmap "
        "is no longer byte-identical (Perlin octaves / flatness / castle flatten / "
        "zone elevation / water clamp changed). "
        f"got={snap['heightmap_hash']} baseline={_SNAPSHOT_HEIGHTMAP_HASH}"
    )


def test_world_snapshot_is_reproducible_across_builds():
    """Two fresh-process builds give the same world snapshot (internal determinism).

    Proves the generated-world scenario is itself deterministic in a clean process
    (the guardrail the byte-identical pin is diffed against), independent of any
    in-process global-state carry-over.
    """
    s1 = _compute_world_snapshot_in_subprocess()
    s2 = _compute_world_snapshot_in_subprocess()
    assert s1 == s2, (
        "world snapshot is not reproducible across two fresh same-seed builds — "
        f"generation is nondeterministic.\ns1={s1}\ns2={s2}"
    )
