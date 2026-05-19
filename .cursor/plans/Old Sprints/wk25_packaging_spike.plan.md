---
name: wk25-packaging-spike
overview: Master plan to package Kingdom Sim (Ursina/Pygame hybrid, 200k+ LOC) into a standalone Windows .exe for Steam Early Access distribution. Covers path resolution, asset bundling, hidden imports, build pipeline, QA strategy, and depot structure.
todos:
  - Sprint 1 — Foundation (path abstraction, dependency manifest, .spec scaffold)
  - Sprint 2 — Asset pipeline & build automation (strip unused formats, bundle, CI script)
  - Sprint 3 — Steam-ready polish (save-game relocation, console suppression, depot, smoke test on clean VM)
isProject: true
---

# WK25 Packaging Spike — Master Plan

## Executive Summary

Kingdom Sim has never been packaged into a standalone executable. The game currently runs from source via `python main.py`, depends on a hybrid Ursina (Panda3D) + Pygame stack with LLM API integrations, and references ~36,000 asset files through `Path(__file__).resolve().parents[N]` calls that will break inside a frozen bundle. This spike eliminates the technical debt by producing a working `.exe` that boots, renders 3D, plays audio, and talks to LLM APIs on a Windows machine **with no Python installed**.

**Goal:** A repeatable, CI-ready build pipeline that outputs a distributable `KingdomSim/` folder suitable for Steam depot upload.

**Recommended tool:** PyInstaller (see Agent 12 rationale in Section 2).

---

## 1. Subagent Audit Reports

### Agent 03 — Technical Director (Architecture)

**Critical blockers identified: 3**

1. **`Path(__file__).resolve().parents[N]` is the #1 distribution killer.** There are **40+ call sites** across `game/` and `tools/` that derive `PROJECT_ROOT` this way. Inside a PyInstaller `--onedir` bundle, `__file__` resolves into the `_internal/` subfolder, and `.parents[2]` climbs into the wrong directory. Every one of these must be replaced with a centralized `get_project_root()` that checks `sys._MEIPASS` first.

   Files requiring patching (game/ runtime — tools/ are dev-only and excluded from the bundle):
   | File | Current pattern |
   |------|----------------|
   | `game/graphics/building_sprites.py:35` | `Path(__file__).resolve().parents[2]` |
   | `game/graphics/hero_sprites.py:38` | `Path(__file__).resolve().parents[2]` |
   | `game/graphics/enemy_sprites.py:32` | `Path(__file__).resolve().parents[2]` |
   | `game/graphics/worker_sprites.py:36` | `Path(__file__).resolve().parents[2]` |
   | `game/graphics/prefab_texture_overrides.py:15` | `Path(__file__).resolve().parents[2]` → `PROJECT_ROOT` |
   | `game/graphics/ursina_environment.py:12` | `Path(__file__).resolve().parents[2]` → `PROJECT_ROOT` |
   | `game/audio/audio_system.py:149` | `Path(__file__).resolve().parents[2] / "assets" / "audio"` |
   | `studio_gateway/cli.py:20` | `Path(__file__).resolve().parents[1]` |

2. **Hidden imports — Ursina + Panda3D.** Ursina dynamically imports shaders, mesh types, and Panda3D C extensions at runtime. PyInstaller's static analysis misses:
   - `panda3d.core` (C extension: `Geom`, `GeomNode`, `GeomTriangles`, `GeomVertexData`, `GeomVertexFormat`, `GeomVertexWriter`, `NodePath`, `Texture`, `TransparencyAttrib`, `CollisionRay`, `Point3`, `Vec3`, `LVecBase4f`, `Filename`, `PNMImage`, `getModelPath`)
   - `ursina.shaders` (dynamic shader registry)
   - `ursina.lights` (`AmbientLight`, `DirectionalLight`)
   - `ursina.shader.Shader` (custom shader compilation)
   - `ursina.vec2`, `ursina.color`
   - `ursina.application` (referenced at runtime in `ursina_app.py:533`)

3. **Panda3D model path configuration.** Ursina defaults `application.asset_folder` to `dirname(sys.argv[0])`. In a frozen bundle, `sys.argv[0]` points to the `.exe`, not the internal data folder. The Panda3D `getModelPath()` must be explicitly set to the bundled `assets/` location at startup, before any Entity loads a `.glb`.

**Recommendation:** Create a single `game/paths.py` module:
```python
import sys
from pathlib import Path

def get_project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]

PROJECT_ROOT = get_project_root()
ASSETS_DIR = PROJECT_ROOT / "assets"
```
All 40+ call sites import from `game.paths` instead of computing their own root.

---

### Agent 12 — Tools/DevEx (Build Framework)

**Recommendation: PyInstaller (`--onedir` mode)**

| Criterion | PyInstaller | Nuitka | cx_Freeze |
|-----------|------------|--------|-----------|
| Panda3D/Ursina support | Proven (Panda3D ships PyInstaller hooks) | Experimental; C-extension compilation breaks panda3d DLLs | Minimal community support |
| Build speed | ~2–5 min | 20–60 min (full C compilation) | ~5 min |
| Output size control | `--exclude-module`, tree-shaking | Better binary size but longer iteration | Moderate |
| Community/docs | Excellent for game distribution | Growing but game-specific gaps | Stale |
| `--onefile` vs `--onedir` | `--onedir` recommended (avoids temp extraction lag) | N/A (always directory) | Directory only |
| Windows code-signing | Supported | Supported | Supported |

**Why not `--onefile`:** Ursina/Panda3D loads assets by filesystem path. `--onefile` extracts to a temp dir on every launch (5–15s cold start with our 11GB+ asset footprint). `--onedir` keeps assets on disk permanently — instant boot.

**Build script specification (`tools/build_executable.py`):**
```
Usage: python tools/build_executable.py [--clean] [--strip-unused-formats] [--skip-tests]

Steps:
  1. Validate requirements (PyInstaller installed, Python version, venv active)
  2. Generate/update kingdom_sim.spec from template
  3. Run asset pipeline (strip .fbx/.obj/.dae/.stl/.aseprite if --strip-unused-formats)
  4. Invoke PyInstaller with the .spec
  5. Copy .env.example → dist/KingdomSim/.env (strip API keys)
  6. Run post-build smoke test (tools/test_frozen_exe.py)
  7. Print artifact manifest (size, file count, sha256 of .exe)
```

**`.spec` file skeleton (`kingdom_sim.spec`):**
```python
# kingdom_sim.spec — PyInstaller build specification
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/audio', 'assets/audio'),
        ('assets/sprites', 'assets/sprites'),
        ('assets/models/environment', 'assets/models/environment'),
        ('assets/models/nature-kit', 'assets/models/nature-kit'),
        ('assets/prefabs', 'assets/prefabs'),
        ('assets/textures', 'assets/textures'),
        ('assets/maps', 'assets/maps'),
        ('assets/ui', 'assets/ui'),
        ('config.py', '.'),
        ('.env.example', '.'),
    ],
    hiddenimports=[
        # Panda3D core (C extensions, not traced by static analysis)
        'panda3d.core',
        'panda3d.direct',
        'panda3d.egg',
        'panda3d.physics',
        'direct.showbase',
        'direct.showbase.ShowBase',
        'direct.task',
        'direct.task.Task',
        # Ursina internals
        'ursina',
        'ursina.application',
        'ursina.camera',
        'ursina.color',
        'ursina.entity',
        'ursina.lights',
        'ursina.mesh',
        'ursina.mouse',
        'ursina.scene',
        'ursina.shader',
        'ursina.shaders',
        'ursina.shaders.lit_with_shadows_shader',
        'ursina.shaders.unlit_shader',
        'ursina.texture',
        'ursina.vec2',
        'ursina.vec3',
        'ursina.window',
        'ursina.text',
        # Pygame (SDL backend)
        'pygame',
        'pygame.mixer',
        'pygame.font',
        'pygame.image',
        # LLM providers
        'anthropic',
        'openai',
        'google.generativeai',
        'httpx',
        # PIL / Pillow
        'PIL',
        'PIL.Image',
        # dotenv
        'dotenv',
    ],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy.testing',
        'pytest',
        'IPython',
        'notebook',
        'tools',           # dev-only tooling
        'studio_gateway',  # agent orchestration, not shipped
        'tests',           # test suite
    ],
    ...
)
```

---

### Agent 11 — QA/Test Engineering

**Problem:** `qa_smoke.py` imports and runs the source tree directly. It cannot test a frozen `.exe` because the module structure doesn't exist inside the bundle.

**Strategy: Two-tier testing**

| Tier | What | How | When |
|------|------|-----|------|
| **Tier 1 — Source smoke** | Existing `qa_smoke.py` | `python tools/qa_smoke.py --quick` | Pre-build gate |
| **Tier 2 — Frozen smoke** | New `test_frozen_exe.py` | Launches `.exe` as subprocess, asserts boot + render + audio | Post-build gate |

**`tools/test_frozen_exe.py` specification:**
```
Tests (all automated, no human interaction):
  1. BOOT: Launch dist/KingdomSim/KingdomSim.exe --renderer ursina --no-llm
     - Assert: process starts, no crash within 10s
     - Assert: stdout contains "Kingdom Sim" banner
  2. WINDOW: After 5s, capture window screenshot via Windows API
     - Assert: screenshot is not all-black (Ursina rendered something)
  3. AUDIO: Assert pygame.mixer initialized (check stdout/log for "mixer init")
  4. ASSET LOAD: Assert no "FileNotFoundError" or "Could not find" in stderr
  5. CLEAN EXIT: Send WM_CLOSE, assert exit code 0 within 5s
  6. SAVE PATH: Assert %APPDATA%/KingdomSim/ directory was created (Sprint 3)

Timeout: 60s total. Exit with code 0 = pass, 1 = fail with diagnostics.
```

**Clean-machine testing:** Final validation must occur on a Windows 10/11 VM or fresh user account with:
- No Python installed
- No `PYTHONPATH` set
- No `.env` in the system (game must handle missing API keys gracefully)

---

### Agent 09 — Art Director & Agent 14 — Audio Director

**Asset bundling requirements:**

The `assets/` tree contains **36,446 files across ~11GB** in the source repo. Most of this is duplicate 3D model formats. The game runtime only uses:

| Asset type | Format used at runtime | Ship? | Source formats to EXCLUDE |
|-----------|----------------------|-------|--------------------------|
| 3D models | `.glb` only | Yes | `.obj`, `.mtl`, `.fbx`, `.dae`, `.stl` (5,887 files, ~60% of model dir) |
| Sprites | `.png` | Yes | `.aseprite` source files (20 files) |
| Audio SFX | `.ogg`, `.wav` | Yes | None (only 14 audio files total) |
| Prefabs | `.json` | Yes | None |
| Textures | `.png` | Yes | None |
| Maps | `.json` | Yes | None |
| Attribution | `.txt`, `.md`, `.url` | Include `ATTRIBUTION.md` only | Individual `.url` link files |

**Estimated distributable asset footprint after stripping:**
- Current: ~11 GB
- After removing unused formats: ~3–4 GB
- After optional PNG compression (pngquant): ~2.5–3 GB

**Audio-specific requirements (Agent 14):**
- All 14 audio files in `assets/audio/` must be bundled at `assets/audio/sfx/` relative to the `.exe`
- `audio_system.py:149` derives the audio path from `__file__` — must use `game.paths.ASSETS_DIR / "audio"` instead
- Pygame mixer initialization (`pygame.mixer.init()`) must handle missing audio hardware gracefully (already does — `audio_system.py` wraps in try/except)
- No streaming audio (all files < 1MB) — no special I/O considerations

**Art-specific requirements (Agent 09):**
- Sprite libraries (`building_sprites.py`, `hero_sprites.py`, `enemy_sprites.py`, `worker_sprites.py`) all derive paths from `__file__` — must migrate to `game.paths`
- Ursina loads `.glb` models via Panda3D's `getModelPath()` — the bundled `assets/models/` must be appended to this search path at startup
- PNG sprites composited onto Ursina UI via `PIL.Image` → `ursina.Texture` — this pipeline is path-sensitive

---

### Agent 13 — Steam/Ops

**Build artifact requirements for Steam:**

1. **Console suppression:** PyInstaller `--noconsole` flag (or `console=False` in `.spec`). The game must not open a CMD window on launch.

2. **Depot structure:**
   ```
   depot_build/
   └── KingdomSim/
       ├── KingdomSim.exe          # Main executable
       ├── _internal/              # PyInstaller internals (Python DLLs, .pyc)
       ├── assets/                 # Game content (external, not inside _internal)
       │   ├── audio/
       │   ├── models/
       │   ├── sprites/
       │   ├── prefabs/
       │   ├── textures/
       │   ├── maps/
       │   └── ui/
       ├── .env.example            # Template (no real API keys!)
       ├── ATTRIBUTION.md          # CC0 license credits (Kenney, etc.)
       ├── steam_appid.txt         # Steam App ID (for Steamworks SDK, added later)
       └── saves/                  # Empty dir; created on first run
   ```

3. **Save-game data location:** Currently no save system exists. When implemented, saves **must** go to `%APPDATA%/KingdomSim/saves/`, not the install directory (Steam install dirs may be read-only, and Cloud Save requires a known path).

   Preparation now:
   ```python
   # game/paths.py addition
   def get_save_dir() -> Path:
       if sys.platform == 'win32':
           base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
       else:
           base = Path.home() / '.local' / 'share'
       save_dir = base / 'KingdomSim' / 'saves'
       save_dir.mkdir(parents=True, exist_ok=True)
       return save_dir
   ```

4. **`.env` / API key handling:** The `.env` file must NOT be bundled with real keys. Ship `.env.example`. The game must boot and play without any LLM keys (it already falls back to `BasicAI` via `--no-llm` / exception handler in `main.py:73`). For Steam, the default should be `--no-llm` unless the user provides their own keys.

5. **Version metadata:** The `.exe` needs a Windows version resource (right-click → Properties → Details):
   ```
   FileDescription: Kingdom Sim
   FileVersion: 1.5.5
   ProductName: Kingdom Sim
   CompanyName: Kingdom Sim Studio
   LegalCopyright: (C) 2025-2026
   ```
   Set via PyInstaller `--version-file` option pointing to a `version_info.txt`.

6. **Windows Defender / SmartScreen:** Unsigned `.exe` files from PyInstaller trigger SmartScreen warnings. For Steam distribution this is mitigated by Steam's own launcher, but for direct downloads, code-signing with an EV certificate is eventually required. **Not a Sprint 1 blocker** — Steam handles this.

---

### Agent 04 — Determinism Lead & Agent 10 — Performance Lead

**Runtime behavior differences in a frozen bundle:**

1. **Asset I/O from `--onedir` is identical to source.** Files sit on the real filesystem, not in a compressed archive. No I/O regression expected. (This would be different with `--onefile`, which extracts to a temp dir — another reason to avoid it.)

2. **Panda3D BAM cache.** Panda3D automatically converts `.glb` → `.bam` (binary) on first load and caches them. In source mode, the cache goes to `~/.panda3d/cache/`. In a frozen bundle, the same behavior applies — **no change.** However, first-run on a clean machine will be slower as the BAM cache builds. The existing `tools/prewarm_panda_bam_cache.py` script should be adapted to run as a post-install step or first-launch warmup.

3. **Determinism risk: NONE identified.** The simulation runs on `sim_engine.py` with seeded RNG. Packaging does not affect:
   - Tick rate (driven by `time.perf_counter`, not filesystem)
   - RNG seeding (read from `config.py` / `.env`)
   - Entity ordering (Python dicts are insertion-ordered since 3.7; frozen Python is still CPython)

4. **Performance risk: startup time.** Importing Panda3D + Ursina + Pygame from a frozen bundle may add 1–3s to cold start vs. source. This is acceptable for a game. Mitigation: splash screen during init.

5. **`importlib` / dynamic imports.** Several files use `from ursina import ...` inside function bodies (lazy imports). PyInstaller's `--hidden-import` flags handle this as long as we declare them. The `.spec` file above covers all identified cases.

---

### Agents 02, 05, 06, 07, 08 — Gameplay, AI, Scenarios, UI

**Confirmation: all dynamic assets and configs must be included in the manifest.**

| Agent | System | Dynamic files at runtime | Bundling action |
|-------|--------|------------------------|-----------------|
| 02 (Game Director) | Design pillars / feature flags | `config.py` (frozen dataclasses) | Bundle `config.py` at root |
| 05 (Gameplay) | Economy/combat tuning | `config.py` dataclasses (`EconomyConfig`, `HeroConfig`, `EnemyConfig`, `LairConfig`) | Same — all in `config.py` |
| 06 (AI/LLM) | Prompt templates, provider configs | `ai/providers/*.py`, `.env` for API keys | Bundle `ai/` package; ship `.env.example` |
| 07 (Content/Scenarios) | Event tables, scenario goals | Hardcoded in `game/systems/` currently; `assets/maps/*.json` for map data | Bundle `assets/maps/` |
| 08 (UX/UI) | HUD layouts, panel configs | Hardcoded in `game/ui/` Python modules; sprite paths in `assets/sprites/` and `assets/ui/` | Bundle `game/ui/` package + `assets/sprites/` + `assets/ui/` |

**Agent 15 — Model Assembler (Kitbash):**
- Prefab JSONs in `assets/prefabs/buildings/*.json` are loaded at runtime by `ursina_prefabs.py`
- These reference `.glb` model paths relative to `assets/models/` — paths must resolve correctly in the bundle
- All prefab JSONs must be included in the `.spec` `datas` list

**No blockers from these agents.** Their systems are either pure Python (bundled automatically) or reference assets already covered by the Art/Audio manifest.

---

## 2. Execution Sprints

### Sprint 1 — Foundation (Week 25, Days 1–3)

**Goal:** All path references are bundle-safe; first successful `pyinstaller` invocation produces a `.exe` that boots (may still have missing assets or import errors).

| # | Task | Owner | Files | Acceptance |
|---|------|-------|-------|------------|
| 1.1 | Create `game/paths.py` with `get_project_root()`, `ASSETS_DIR`, `get_save_dir()` | Agent 03 | `game/paths.py` (new) | Module importable; returns correct root in source and frozen modes |
| 1.2 | Migrate all `Path(__file__).parents[N]` in `game/` to `game.paths.PROJECT_ROOT` | Agent 03 | `building_sprites.py`, `hero_sprites.py`, `enemy_sprites.py`, `worker_sprites.py`, `prefab_texture_overrides.py`, `ursina_environment.py`, `audio_system.py` | `grep -r "parents\[" game/` returns 0 hits |
| 1.3 | Add Panda3D model-path setup to `ursina_app.py` init | Agent 03 | `game/graphics/ursina_app.py` | `getModelPath()` includes `ASSETS_DIR` before any Entity is created |
| 1.4 | Add `ursina` and `panda3d` to `requirements.txt` | Agent 12 | `requirements.txt` | `pip install -r requirements.txt` in fresh venv succeeds |
| 1.5 | Create `kingdom_sim.spec` scaffold | Agent 12 | `kingdom_sim.spec` (new) | `pyinstaller kingdom_sim.spec` completes without error |
| 1.6 | Create `version_info.txt` for Windows .exe metadata | Agent 13 | `version_info.txt` (new) | Right-click `.exe` → Properties shows correct version |
| 1.7 | Verify source smoke tests still pass after path migration | Agent 11 | — | `python tools/qa_smoke.py --quick` exits 0 |

**Sprint 1 Definition of Done:**
- `pyinstaller kingdom_sim.spec` completes
- `dist/KingdomSim/KingdomSim.exe` exists
- The `.exe` starts (may crash after boot banner — that's fine for Sprint 1)
- Source-mode game still runs: `python main.py --renderer ursina --no-llm`

---

### Sprint 2 — Asset Pipeline & Build Automation (Week 25, Days 4–6)

**Goal:** The `.exe` boots, renders the 3D world, plays audio, and handles missing LLM keys gracefully. The build is automated via a single command.

| # | Task | Owner | Files | Acceptance |
|---|------|-------|-------|------------|
| 2.1 | Build `tools/build_executable.py` pipeline script | Agent 12 | `tools/build_executable.py` (new) | `python tools/build_executable.py` produces working `.exe` |
| 2.2 | Build `tools/strip_unused_assets.py` — removes `.fbx/.obj/.mtl/.dae/.stl/.aseprite` from a staging copy | Agent 12 | `tools/strip_unused_assets.py` (new) | Staging dir contains only `.glb`, `.png`, `.ogg`, `.wav`, `.json`, `.md` |
| 2.3 | Iterate on `kingdom_sim.spec` hidden imports until `.exe` renders 3D | Agent 03 + 12 | `kingdom_sim.spec` | `.exe` shows terrain + buildings (not black screen) |
| 2.4 | Fix any Panda3D BAM cache path issues in frozen mode | Agent 03 | `game/graphics/ursina_app.py` | No "cannot write to cache" errors in stderr |
| 2.5 | Verify audio plays from bundled assets | Agent 14 | — | UI click / building place sound audible from `.exe` |
| 2.6 | Verify LLM graceful degradation | Agent 06 | — | `.exe` launched without `.env` falls back to `BasicAI`, no crash |
| 2.7 | Create `tools/test_frozen_exe.py` (Tier 2 frozen smoke test) | Agent 11 | `tools/test_frozen_exe.py` (new) | Script exits 0 when run against a working build |

**Sprint 2 Definition of Done:**
- `python tools/build_executable.py` runs end-to-end with no manual steps
- The `.exe` renders the Ursina 3D viewport (terrain, buildings, units visible)
- Audio SFX plays on user actions
- No `FileNotFoundError` in stderr
- `tools/test_frozen_exe.py` exits 0

---

### Sprint 3 — Steam-Ready Polish (Week 26, Days 1–3)

**Goal:** The build is release-candidate quality. Console hidden, depot structured, tested on a clean machine, and save-path ready.

| # | Task | Owner | Files | Acceptance |
|---|------|-------|-------|------------|
| 3.1 | Set `console=False` in `.spec` (suppress CMD window) | Agent 12 | `kingdom_sim.spec` | Double-clicking `.exe` opens game window only, no console |
| 3.2 | Add `--version-file version_info.txt` to `.spec` | Agent 13 | `kingdom_sim.spec`, `version_info.txt` | `.exe` Properties → Details shows "Kingdom Sim v1.5.5" |
| 3.3 | Implement `get_save_dir()` and wire into future save system | Agent 03 | `game/paths.py` | `%APPDATA%/KingdomSim/` dir created on first run |
| 3.4 | Create `tools/package_depot.py` — copies build into Steam depot layout | Agent 13 | `tools/package_depot.py` (new) | `depot_build/` matches the structure in Agent 13's audit |
| 3.5 | Add splash screen / loading indicator during Ursina init | Agent 08 | `game/graphics/ursina_app.py` | Users see "Loading..." rather than a frozen window for 2–5s |
| 3.6 | Clean-machine validation on Windows 10 VM | Agent 11 | — | `.exe` boots, renders, plays audio on a machine with no Python |
| 3.7 | Add `.exe` build step to CI (GitHub Actions) | Agent 12 | `.github/workflows/build.yml` (new) | Push to `main` triggers build; artifact uploaded |
| 3.8 | Final asset audit — verify ATTRIBUTION.md covers all shipped assets | Agent 09 | `assets/ATTRIBUTION.md` | Every Kenney pack referenced by shipped `.glb` files is listed |

**Sprint 3 Definition of Done:**
- No console window on launch
- `.exe` runs on a Windows 10 VM with no Python
- Save directory created at `%APPDATA%/KingdomSim/`
- `depot_build/` directory passes `steamcmd` `depot_build` dry-run
- CI produces build artifact on every push to `main`

---

## 3. Definition of Done — Full Spike

The packaging spike is **complete** when ALL of the following are true:

| # | Condition | Verified by |
|---|-----------|-------------|
| **DoD-1** | The game boots from `KingdomSim.exe` on a Windows 10/11 machine with **no Python installed** | Agent 11 (clean VM test) |
| **DoD-2** | The Ursina 3D viewport renders terrain, buildings, units, and fog-of-war | Agent 11 (screenshot comparison) |
| **DoD-3** | Audio SFX plays (building placement, UI clicks) | Agent 11 / Agent 14 (manual verification) |
| **DoD-4** | The game falls back to `BasicAI` when no `.env` / API keys are present — no crash, no error dialog | Agent 06 (automated test) |
| **DoD-5** | No `FileNotFoundError`, `ModuleNotFoundError`, or `ImportError` appears in stderr during a 60-second play session | Agent 11 (`test_frozen_exe.py`) |
| **DoD-6** | The `.exe` does not open a CMD console window | Agent 13 (visual check) |
| **DoD-7** | The distributable folder is < 5 GB after asset stripping | Agent 09 (size audit) |
| **DoD-8** | `python tools/build_executable.py` produces the build with zero manual steps | Agent 12 (CI run) |
| **DoD-9** | `python tools/qa_smoke.py --quick` still passes (source mode not broken) | Agent 11 (CI gate) |
| **DoD-10** | The build produces a `depot_build/` folder matching Steam depot layout requirements | Agent 13 (structure validation) |

---

## 4. Recommended Testing Tools

### 4.1 `tools/test_frozen_exe.py` — Frozen Build Smoke Tester

**Purpose:** Automated post-build verification that the `.exe` works without human interaction.

**Specification:**
```
Language: Python 3.10+ (runs on dev machine, NOT inside the bundle)
Dependencies: subprocess, time, ctypes (Windows API for window detection), Pillow (screenshot)

Subcommands:
  test_frozen_exe.py run          # Full test suite (default)
  test_frozen_exe.py boot-only    # Just check it starts
  test_frozen_exe.py assets-only  # Just check for FileNotFound errors

Test cases:
  TC-01 BOOT       Launch .exe, wait 10s, assert process alive
  TC-02 NO_CRASH   Assert stderr has no tracebacks after 15s
  TC-03 RENDER     Capture window screenshot, assert not all-black and not all-white
  TC-04 AUDIO_INIT Assert "mixer" init message in stdout (non-blocking)
  TC-05 NO_MISSING Assert 0 occurrences of "FileNotFoundError" or "not found" in stderr
  TC-06 CLEAN_EXIT Send WM_CLOSE via ctypes, assert exit code 0 within 5s
  TC-07 APPDATA    Assert %APPDATA%/KingdomSim/ exists after run (Sprint 3)

Output: JSON report + exit code (0 = all pass, 1 = any fail)
Timeout: 90s total safeguard
```

### 4.2 `tools/build_executable.py` — One-Command Build Pipeline

**Purpose:** Repeatable, CI-ready build from source to distributable.

**Specification:**
```
Language: Python 3.10+
Dependencies: PyInstaller, shutil, hashlib

Flags:
  --clean                  # Delete dist/ and build/ before starting
  --strip-unused-formats   # Run strip_unused_assets.py on staging copy
  --skip-tests             # Skip post-build test_frozen_exe.py
  --output-dir PATH        # Override dist/ location (default: dist/KingdomSim/)

Pipeline stages:
  1. VALIDATE   Check Python version, PyInstaller installed, venv active
  2. STAGE      Copy assets/ to build staging (apply --strip-unused-formats if set)
  3. BUILD      Invoke PyInstaller with kingdom_sim.spec
  4. MANIFEST   Copy .env.example, ATTRIBUTION.md, create empty saves/ dir
  5. VERIFY     Run test_frozen_exe.py (unless --skip-tests)
  6. REPORT     Print: exe path, total size, file count, sha256 hash

Exit codes: 0 = success, 1 = build failed, 2 = tests failed
```

### 4.3 `tools/strip_unused_assets.py` — Asset Slimmer

**Purpose:** Remove non-runtime asset formats from a staging copy to reduce distributable size.

**Specification:**
```
Language: Python 3.10+

Input:  Source assets/ directory path
Output: Cleaned staging directory (copy, never modifies source)

Rules:
  REMOVE: *.obj, *.mtl, *.fbx, *.dae, *.stl, *.aseprite, *.url
  KEEP:   *.glb, *.png, *.jpg, *.ogg, *.wav, *.json, *.md, *.txt (ATTRIBUTION only)

Report: files removed count, bytes saved, final directory size
```

### 4.4 `tools/package_depot.py` — Steam Depot Packager

**Purpose:** Arrange the PyInstaller output into Steam's expected depot structure.

**Specification:**
```
Language: Python 3.10+

Input:  dist/KingdomSim/ (PyInstaller output)
Output: depot_build/KingdomSim/ (Steam-ready layout)

Steps:
  1. Create depot_build/ structure
  2. Copy .exe and _internal/ from dist/
  3. Copy assets/ (already stripped) alongside .exe (NOT inside _internal/)
  4. Create steam_appid.txt placeholder
  5. Copy ATTRIBUTION.md
  6. Create empty saves/ directory
  7. Validate: assert .exe exists, assets/ has expected subdirs, no .env with real keys
```

---

## 5. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Ursina/Panda3D hidden import chase takes > 2 days | Medium | High — blocks all testing | Start with Panda3D's own PyInstaller hook (`PyInstaller.hooks.panda3d`); iterate on `.spec` with `--debug imports` flag |
| R2 | Asset directory > 5 GB even after stripping | Medium | Medium — slow downloads, large depot | Investigate texture atlasing, model LOD, and selective pack inclusion |
| R3 | Panda3D shader compilation fails in frozen mode | Low | High — black screen | Panda3D compiles shaders at runtime from source strings; should work. Test custom shaders (instanced_unit_shader, sprite_unlit_shader) specifically |
| R4 | Windows Defender flags unsigned .exe | High | Low for Steam (Steam launcher bypasses) | Accept for now; plan EV code-signing certificate for direct distribution later |
| R5 | First-run BAM cache build causes 30s+ stall | Medium | Medium — bad first impression | Add loading screen; consider pre-built BAM cache in depot |
| R6 | OneDrive sync conflicts during build (repo is in OneDrive) | Medium | Medium — corrupted build artifacts | Build in a local temp directory outside OneDrive, or add `dist/` and `build/` to OneDrive exclusion list |

---

## 6. Open Questions for Human Decision

1. **Steam App ID:** Has one been created yet? Needed for `steam_appid.txt` and Steamworks SDK integration. (Not a Sprint 1 blocker.)

2. **LLM in shipped build:** Should the `.exe` ship with LLM provider code at all, or should it be stripped to reduce surface area and dependency size? LLM libraries (openai, anthropic, google-generativeai) add ~50MB to the bundle.

3. **Target Python version for freeze:** Currently no `python_requires` specified. Recommend pinning to **Python 3.11** (best PyInstaller + Panda3D compatibility as of 2026-Q2). Python 3.12+ has known Panda3D packaging issues.

4. **CI runner:** GitHub Actions Windows runner for automated builds? Or local-only for now?

5. **Asset CDN vs. bundled:** For Steam, all assets ship in the depot. But if we ever want a launcher/demo, should we plan for a separate asset download step? (Recommend: no, keep it simple — bundle everything.)

---

## Appendix A: Full Hidden Import Inventory

Derived from static analysis of all `import` / `from ... import` statements in `game/`, `ai/`, and `main.py`:

```
# === Panda3D (C extensions) ===
panda3d.core
panda3d.direct
direct.showbase
direct.showbase.ShowBase
direct.task
direct.task.Task
direct.gui
direct.gui.OnscreenText

# === Ursina ===
ursina
ursina.application
ursina.camera
ursina.color
ursina.entity
ursina.lights
ursina.mesh
ursina.mouse
ursina.scene
ursina.shader
ursina.shaders
ursina.shaders.lit_with_shadows_shader
ursina.shaders.unlit_shader
ursina.text
ursina.texture
ursina.vec2
ursina.vec3
ursina.window

# === Pygame ===
pygame
pygame.font
pygame.image
pygame.mixer
pygame.transform
pygame.draw
pygame.surface
pygame.event

# === LLM Providers ===
anthropic
openai
google.generativeai
httpx
httpx._transports
httpx._transports.default

# === Standard Library (sometimes missed) ===
zlib
json
dataclasses
threading
queue
collections
```

## Appendix B: Files Requiring Path Migration (Complete List)

All files in `game/` that currently compute their own root via `Path(__file__).resolve().parents[N]`:

| File | Line | Current | Target |
|------|------|---------|--------|
| `game/graphics/building_sprites.py` | 35 | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT` |
| `game/graphics/hero_sprites.py` | 38 | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT` |
| `game/graphics/enemy_sprites.py` | 32 | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT` |
| `game/graphics/worker_sprites.py` | 36 | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT` |
| `game/graphics/prefab_texture_overrides.py` | 15 | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT` |
| `game/graphics/ursina_environment.py` | 12 | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT` |
| `game/audio/audio_system.py` | 149 | `Path(__file__).resolve().parents[2] / "assets" / "audio"` | `from game.paths import ASSETS_DIR; ASSETS_DIR / "audio"` |

Files in `tools/` and `studio_gateway/` also use this pattern but are **excluded from the bundle** (dev-only). No changes needed for those.

---

*Plan authored by Agent 01 (Executive Producer/PM) with simulated input from all 14 department leads.*
*Date: 2026-05-12*
*Target: Steam Early Access packaging readiness*

---

## 7. Packaging Guide — How to Build KingdomSim.exe

This section documents how to repeat the packaging process at future milestones.

### Prerequisites

- **Python 3.11** installed (`winget install Python.Python.3.11`)
- **Build venv** at `C:\KingdomBuild\venv` (created once, reused):
  ```
  py -3.11 -m venv C:\KingdomBuild\venv
  C:\KingdomBuild\venv\Scripts\python.exe -m pip install -r requirements.txt
  ```
- The build outputs to `C:\KingdomBuild\dist\` (outside OneDrive to avoid sync conflicts)

### One-Command Build

```
python tools/build_executable.py --clean --test
```

This will:
1. Clean previous build artifacts
2. Run PyInstaller with `kingdom_sim.spec`
3. Produce `C:\KingdomBuild\dist\KingdomSim\KingdomSim.exe`
4. Run the automated smoke test

### Manual Build (if the script has issues)

```
C:\KingdomBuild\venv\Scripts\python.exe -m PyInstaller kingdom_sim.spec --distpath C:\KingdomBuild\dist --workpath C:\KingdomBuild\build --noconfirm
```

### Testing the Build

```
python tools/test_frozen_exe.py
```

Or test a specific exe:
```
python tools/test_frozen_exe.py C:\KingdomBuild\dist\KingdomSim\KingdomSim.exe
```

### Known Warnings (Safe to Ignore)

| Warning | Cause | Impact |
|---------|-------|--------|
| `Invalid integer value for ConfigVariable win-size` | Panda3D config parsing float as int | None — window opens correctly |
| `Unable to open .../models_compressed/...bam` | BAM cache miss for pre-compiled models | None — falls back to .glb files |
| `Could not find icon filename textures/ursina.ico` | Ursina window icon not bundled | Cosmetic — default Windows icon used |
| `google.generativeai` deprecation warning | Google renamed their SDK | None at build time — update to `google.genai` when convenient |

### Key Files

| File | Purpose |
|------|---------|
| `kingdom_sim.spec` | PyInstaller build specification (entry point, assets, hidden imports, Panda3D DLLs) |
| `game/paths.py` | Centralized path resolution with `sys._MEIPASS` support for frozen builds |
| `version_info.txt` | Windows .exe metadata (version, company, copyright) |
| `tools/build_executable.py` | One-command build pipeline |
| `tools/test_frozen_exe.py` | Automated smoke test for the frozen .exe |
| `requirements.txt` | All dependencies including ursina, panda3d, pyinstaller |

### When to Rebuild

Rebuild after any milestone that changes:
- Dependencies (new imports, new packages in requirements.txt)
- Asset directory structure (new folders under `assets/`)
- Entry point or startup sequence (`main.py`, `ursina_app.py`)
- Custom shaders (may need new hidden imports)

The `kingdom_sim.spec` may need updating if new asset directories or hidden imports are added.

### Artifact Size Reference

As of WK25 (v1.5.5): **449 MB**, 14,082 files. Asset stripping (removing .fbx/.obj/.dae/.stl duplicates) is available if size becomes a concern but was not needed at this scale.
