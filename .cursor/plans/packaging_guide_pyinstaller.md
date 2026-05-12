# Kingdom Sim -- PyInstaller Packaging Guide

> **Audience:** A new AI agent or human developer who has never seen the Kingdom Sim codebase.
> **Purpose:** A complete, self-contained reference that explains how the game is frozen into a standalone Windows `.exe`, what problems were encountered and solved during the WK25 Packaging Spike (May 2026), and how to reproduce, modify, or troubleshoot the build.
> **Last updated:** 2026-05-12

---

## Table of Contents

1. [What Is Kingdom Sim?](#1-what-is-kingdom-sim)
2. [Technology Stack](#2-technology-stack)
3. [Why PyInstaller?](#3-why-pyinstaller)
4. [Architecture Decisions](#4-architecture-decisions)
5. [Build Environment Setup](#5-build-environment-setup)
6. [The Five Critical Problems We Solved](#6-the-five-critical-problems-we-solved)
   - [Problem 1: Path Resolution (THE #1 BLOCKER)](#problem-1-path-resolution-the-1-blocker)
   - [Problem 2: Panda3D Display DLLs Not Bundled](#problem-2-panda3d-display-dlls-not-bundled)
   - [Problem 3: Ursina Built-in Resources Not Bundled](#problem-3-ursina-built-in-resources-not-bundled)
   - [Problem 4: Panda3D Model Search Path](#problem-4-panda3d-model-search-path)
   - [Problem 5: Asset Directory Structure Mismatch](#problem-5-asset-directory-structure-mismatch)
7. [Hidden Imports](#7-hidden-imports)
8. [What Gets Bundled (and What Does Not)](#8-what-gets-bundled-and-what-does-not)
9. [The Build Pipeline](#9-the-build-pipeline)
10. [Smoke Tests](#10-smoke-tests)
11. [Known Safe Warnings](#11-known-safe-warnings)
12. [Known Issues](#12-known-issues)
13. [Key Files Reference](#13-key-files-reference)
14. [When to Update the Spec](#14-when-to-update-the-spec)
15. [Step-by-Step From Scratch](#15-step-by-step-from-scratch-if-the-venv-is-lost)
16. [Rules for Future Developers and Agents](#16-rules-for-future-developers-and-agents)

---

## 1. What Is Kingdom Sim?

Kingdom Sim is a ~200,000+ line Python game inspired by the classic game Majesty. It simulates a fantasy kingdom where heroes are AI-driven (via LLM or a mock fallback) and the player manages buildings, economy, and kingdom defense.

The game runs from `main.py` at the repository root. It accepts two important command-line arguments:

| Flag | Effect |
|------|--------|
| `--renderer ursina` | (Default) Launches the full 3D renderer powered by Ursina/Panda3D |
| `--renderer pygame` | Launches the legacy 2D renderer powered by Pygame |
| `--no-llm` | Disables all LLM API calls and uses `BasicAI` for hero behavior instead |

---

## 2. Technology Stack

Understanding the technology stack is critical to understanding the packaging challenges. Kingdom Sim is not a straightforward Python application -- it depends on multiple rendering engines, native DLLs, and external AI APIs.

| Technology | Role | Packaging Implications |
|---|---|---|
| **Ursina** (built on Panda3D) | Primary 3D renderer | Ships fonts, models, textures, shaders as non-Python resources. PyInstaller does NOT bundle these automatically. |
| **Panda3D** | Underlying C++ 3D engine | Dynamically loads display DLLs at runtime via a plugin system. PyInstaller's static analysis never sees these imports. Also requires `Config.prc` files from `panda3d/etc/`. |
| **Pygame** | Hidden SDL backend for UI compositing, font rendering, and audio | Less problematic for packaging, but several submodules (mixer, font, image, transform, draw, surface, event) are dynamically imported and must be listed as hidden imports. |
| **LLM Providers** | OpenAI, Anthropic Claude, Google Gemini, xAI Grok for AI hero behavior | The `anthropic`, `openai`, `google.generativeai`, and `httpx` packages must be bundled. A mock fallback exists for offline use. |
| **Pillow (PIL)** | Image manipulation | `PIL` and `PIL.Image` are lazy imports and need to be listed as hidden imports. |
| **Python 3.11** | Target runtime | Panda3D has compatibility issues with Python 3.12+. The dev machine runs 3.13.2, so a separate 3.11 venv is required for building. |

---

## 3. Why PyInstaller?

Three packaging tools were evaluated during the WK25 Packaging Spike. PyInstaller was chosen for specific, practical reasons:

### PyInstaller (chosen)
- Panda3D ships its own PyInstaller hooks and has proven community support for game distribution.
- Large ecosystem of solved problems and StackOverflow answers for game packaging.
- `.spec` file gives fine-grained control over which files, DLLs, and data directories are included.

### Nuitka (rejected)
- Nuitka compiles Python to C, which fundamentally breaks Panda3D's DLL loading mechanism. The Panda3D display plugin system expects to find and load DLLs by name at runtime, and Nuitka's compilation model is incompatible with this.

### cx_Freeze (rejected)
- cx_Freeze has stale community support for game distribution. There are very few recent examples of Panda3D or Ursina games being packaged with cx_Freeze, which would mean solving all the same DLL/resource problems from scratch without community guidance.

---

## 4. Architecture Decisions

### `--onedir` Mode (Not `--onefile`)

PyInstaller offers two output modes:

| Mode | How it works | Trade-off |
|------|-------------|-----------|
| `--onefile` | Packs everything into a single `.exe`. On every launch, it extracts the full contents to a temporary directory, then runs from there. | 5-15 second cold start with Kingdom Sim's asset footprint. Unacceptable for a game. |
| `--onedir` | Creates a directory with the `.exe` and all dependencies as real files alongside it. | Near-instant launch. Larger footprint on disk, but assets stay on the real filesystem. |

**We use `--onedir`.** The final output is a directory at `C:\KingdomBuild\dist\KingdomSim\` containing `KingdomSim.exe` and all supporting files.

### Build Location: `C:\KingdomBuild\` (NOT Inside the Repo)

This is a critical decision. The repository lives inside OneDrive:

```
C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom
```

PyInstaller generates **thousands** of temporary files in its `build/` and `dist/` directories during compilation. If these directories are inside the repo (which is inside OneDrive), OneDrive tries to sync all of them. This causes:

- Build corruption (files locked by OneDrive sync while PyInstaller is writing them)
- Builds slowing to a crawl (OneDrive upload bandwidth consumed by temp files)
- OneDrive quota consumption by throwaway build artifacts

**Solution:** All build outputs go to `C:\KingdomBuild\`, which is outside OneDrive entirely:

```
C:\KingdomBuild\
    venv\              -- Dedicated Python 3.11 virtual environment
    build\             -- PyInstaller work directory (intermediate files)
    dist\KingdomSim\   -- Final distributable output
```

### Python Version: 3.11.9

| Python Version | Status |
|---|---|
| 3.13.2 | Installed as the dev machine's default. **NOT used for building.** |
| 3.11.9 | Used for the build venv. This is the safest target for Panda3D. |
| 3.10 | Available on the machine but not used. |
| 3.12+ | **Known incompatible with Panda3D.** Do not use. |

Panda3D has known issues with Python 3.12 and later. The 3.11 line is the newest confirmed-compatible version. The build venv is specifically pinned to 3.11.

---

## 5. Build Environment Setup

The build environment is separate from the development environment. Here is the complete layout:

```
C:\KingdomBuild\
    venv\
        Scripts\
            python.exe      -- Python 3.11.9 interpreter
            pyinstaller.exe -- PyInstaller CLI
            pip.exe
        Lib\
            site-packages\  -- All dependencies installed from requirements.txt
    build\                  -- PyInstaller intermediate output (can be deleted)
    dist\
        KingdomSim\
            KingdomSim.exe  -- The frozen executable
            _internal\      -- All bundled Python modules, DLLs, and assets
```

The venv was created with:
```powershell
py -3.11 -m venv C:\KingdomBuild\venv
```

Dependencies were installed with:
```powershell
C:\KingdomBuild\venv\Scripts\python.exe -m pip install --upgrade pip
C:\KingdomBuild\venv\Scripts\python.exe -m pip install -r requirements.txt
```

The `requirements.txt` at the repo root includes all runtime dependencies (ursina, panda3d, pygame, anthropic, openai, google-generativeai, httpx, pillow, python-dotenv) as well as pyinstaller itself.

---

## 6. The Five Critical Problems We Solved

The WK25 Packaging Spike encountered five major blockers, in the order they were discovered. Each one prevented the game from running at all in frozen form. Understanding these problems is essential because **any of them can recur** if future code changes violate the assumptions.

---

### Problem 1: Path Resolution (THE #1 BLOCKER)

**Severity:** Total failure. Every single asset load crashes with `FileNotFoundError`.

#### What Broke

The codebase had **40+ call sites** that computed the project root directory using patterns like this:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]
```

When running from source (`python main.py`), `__file__` resolves to something like:

```
C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\hero_sprites.py
```

And `.parents[2]` correctly climbs to:

```
C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\
```

But inside a PyInstaller `--onedir` bundle, `__file__` resolves into the `_internal/` subfolder:

```
C:\KingdomBuild\dist\KingdomSim\_internal\game\graphics\hero_sprites.py
```

And `.parents[2]` climbs to:

```
C:\KingdomBuild\dist\KingdomSim\_internal\
```

This is the **wrong directory**. The assets are at `_internal/assets/`, not `_internal/../assets/`. Every single `Path(__file__).resolve().parents[N]` call resolves to the wrong place. Every asset load fails.

#### The Fix

Created `game/paths.py` -- a single centralized path resolution module:

```python
import os, sys
from pathlib import Path

def get_project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]

PROJECT_ROOT = get_project_root()
ASSETS_DIR = PROJECT_ROOT / "assets"
```

The key insight: PyInstaller sets `sys.frozen = True` and `sys._MEIPASS` to the `_internal/` directory path when running from a frozen bundle. By checking `sys.frozen`, we can branch between development mode and frozen mode.

Then **all 7 runtime files** in `game/` that computed their own root were migrated to import from `game.paths`:

| File | Old Pattern | New Pattern |
|------|-------------|-------------|
| `game/graphics/building_sprites.py` | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT, ASSETS_DIR` |
| `game/graphics/hero_sprites.py` | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT, ASSETS_DIR` |
| `game/graphics/enemy_sprites.py` | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT, ASSETS_DIR` |
| `game/graphics/worker_sprites.py` | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT, ASSETS_DIR` |
| `game/graphics/prefab_texture_overrides.py` | Local `PROJECT_ROOT = Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT, ASSETS_DIR` |
| `game/graphics/ursina_environment.py` | `Path(__file__).resolve().parents[2]` | `from game.paths import PROJECT_ROOT, ASSETS_DIR` |
| `game/audio/audio_system.py` | `Path(__file__).resolve().parents[2] / "assets" / "audio"` | `from game.paths import ASSETS_DIR` |

**Files NOT changed:** Files in `tools/` and `studio_gateway/` also use the `Path(__file__).parents[N]` pattern, but these are **dev-only** and are excluded from the bundle entirely. They were intentionally left alone.

#### How to Verify the Fix Still Holds

Run this command from the repo root:

```powershell
grep -r "parents\[" game/
```

The **only** result should be `game/paths.py:10`. If any other file in `game/` contains `parents[`, it means someone introduced a new path computation that bypasses `game.paths`, and the frozen build **will** break.

#### Rule for Future Development

**If a future agent or developer adds a new file that loads assets, they MUST import from `game.paths`.** They must never compute their own root via `Path(__file__).parents[N]`. If they do, the development build will work fine (because `__file__` resolves correctly from source), but the frozen build will crash with `FileNotFoundError`.

---

### Problem 2: Panda3D Display DLLs Not Bundled

**Severity:** Total failure. No window opens. Crash with "No graphics pipe is available!"

#### What Broke

The first build attempt that survived path resolution crashed immediately with:

```
:display: loading display module: libpandagl.dll
:display(warning): Unable to load libpandagl.dll: Path not found
:display: loading display module: libpandadx9.dll
:display(warning): Unable to load libpandadx9.dll: Path not found
:display: loading display module: libp3tinydisplay.dll
:display(warning): Unable to load libp3tinydisplay.dll: Path not found
...
Exception: No graphics pipe is available!
```

#### Why PyInstaller Missed Them

Panda3D has a **plugin system** for display modules. At runtime, it reads its `Config.prc` file to determine which display modules to try loading, then calls the OS-level `LoadLibrary()` (on Windows) to load the DLL by name. This is completely invisible to PyInstaller's static analysis, which traces Python `import` statements. Since no Python code ever says `import libpandagl`, PyInstaller has no idea these DLLs exist or are needed.

#### The Fix

In `kingdom_sim.spec`, we added explicit binary declarations that locate the DLLs from the installed `panda3d` package directory and bundle them:

```python
_p3d_dir = _find_package('panda3d')
_p3d_dlls = []
for dll_name in [
    'libpandagl.dll', 'libpandadx9.dll', 'libp3tinydisplay.dll',
    'libp3windisplay.dll', 'libp3openal_audio.dll', 'libp3fmod_audio.dll',
    # ... plus ~15 more DLLs
]:
    src = os.path.join(_p3d_dir, dll_name)
    if os.path.exists(src):
        _p3d_dlls.append((src, 'panda3d'))
```

These DLLs get placed into `_internal/panda3d/` in the output directory, which is where Panda3D's plugin loader expects to find them.

#### Also Required: panda3d/etc/ Config Files

Even with the DLLs present, Panda3D still could not initialize its display pipeline without `Config.prc` and `Confauto.prc` from the `panda3d/etc/` directory. These configuration files tell Panda3D which display modules to try and in what order. Without them, Panda3D does not know where to look for its own DLLs even if they are sitting right next to the executable.

These were added as a `datas` entry in the spec:

```python
(os.path.join(_p3d_dir, '..', 'panda3d', 'etc'), 'panda3d/etc'),
```

---

### Problem 3: Ursina Built-in Resources Not Bundled

**Severity:** Total failure. Window opens but crashes trying to render anything.

#### What Broke

After fixing the Panda3D DLLs, the display pipeline initialized successfully (a window appeared!), but the game immediately crashed with:

```
:pnmtext(error): Unable to find font file OpenSans-Regular.ttf
OSError: Could not load font file: OpenSans-Regular.ttf
```

Additional warnings appeared:

```
missing model: 'quad'
missing model: 'cube'
```

#### Why This Happened

Ursina ships its own built-in resources -- fonts (OpenSans-Regular.ttf, VeraMono.ttf), primitive models (quad, cube, sphere, etc.), textures, and shaders -- inside subdirectories of the `ursina` Python package directory. PyInstaller bundles the Python `.py` files from the package, but it does **not** automatically bundle non-Python resource subdirectories.

The missing resources include:

| Directory | Contents | Why It Matters |
|-----------|----------|---------------|
| `ursina/fonts/` | OpenSans-Regular.ttf, VeraMono.ttf | Default fonts used by `ursina.Text` and all on-screen text |
| `ursina/models/` | quad.obj, cube.obj, sphere.obj, etc. | Primitive geometry used by nearly every `Entity` |
| `ursina/models_compressed/` | Pre-compiled .bam versions of the above | Faster loading alternatives to .obj |
| `ursina/textures/` | Default textures | Fallback textures for entities without custom textures |
| `ursina/shaders/` | GLSL shader files | Lit, unlit, and shadow shaders |

#### The Fix

Added all of Ursina's resource directories to the spec's `datas` list:

```python
_ursina_dir = _find_package('ursina')
# In datas list:
(os.path.join(_ursina_dir, 'fonts'),             'ursina/fonts'),
(os.path.join(_ursina_dir, 'models'),             'ursina/models'),
(os.path.join(_ursina_dir, 'models_compressed'),  'ursina/models_compressed'),
(os.path.join(_ursina_dir, 'textures'),           'ursina/textures'),
(os.path.join(_ursina_dir, 'shaders'),            'ursina/shaders'),
```

These directories are copied into `_internal/ursina/` in the output, preserving the relative path structure that Ursina expects.

---

### Problem 4: Panda3D Model Search Path

**Severity:** Partial failure. Window opens, UI renders, but 3D models (buildings, heroes, environment) are invisible or cause errors.

#### What Broke

Even with all assets correctly bundled into the frozen build, Panda3D could not find `.glb` model files. Panda3D maintains its own model search path (separate from Python's `sys.path`), and it did not include the bundled asset directories.

When code requested a model like `"assets/models/buildings/blacksmith.glb"`, Panda3D searched its default model path (which in a frozen bundle does not include the `_internal/assets/` directory) and failed silently or threw an error.

#### The Fix

In `game/graphics/ursina_app.py`, immediately after the Ursina application is created, we added explicit model path configuration:

```python
from game.paths import ASSETS_DIR
from panda3d.core import getModelPath

getModelPath().appendDirectory(str(ASSETS_DIR.resolve()))
getModelPath().appendDirectory(str((ASSETS_DIR / "models").resolve()))
```

**Timing is critical:** These lines MUST come:
- **AFTER** `self.app = Ursina(...)` -- because the Panda3D `getModelPath()` is not available until the ShowBase (Ursina's parent class) is initialized.
- **BEFORE** any `Entity` creation or model loading -- because models are loaded on `Entity` construction.

If these lines are placed in the wrong location, either `getModelPath()` will fail (too early) or models will already have failed to load (too late).

---

### Problem 5: Asset Directory Structure Mismatch

**Severity:** Build succeeds but assets are missing at runtime.

#### What Broke

The initial `.spec` file referenced `assets/models/nature-kit` as one of the data directories to bundle. This directory **did not exist**. The actual model directory structure was:

```
assets/models/
    buildings/
    environment/
    heroes/
    ... (other subdirectories)
```

There was no `nature-kit` subdirectory. The spec was written based on an assumption about the directory structure that turned out to be wrong.

#### The Fix

Changed the spec to bundle the **entire** `assets/models/` directory instead of cherry-picking subdirectories:

```python
('assets/models', 'assets/models'),
```

This ensures that all models, regardless of subdirectory organization, are included.

#### Lesson for Future Agents

**ALWAYS verify that directory paths exist before adding them to the spec.** Use `Get-ChildItem` or `ls` to check. A nonexistent source directory in a `datas` entry will silently produce an empty destination, and the build will succeed but the runtime will fail.

---

## 7. Hidden Imports

PyInstaller's static analysis traces Python `import` statements to determine which modules to bundle. However, many modules in the Kingdom Sim dependency tree use **lazy imports** (importing inside function bodies) or **dynamic imports** (`importlib.import_module()`, `__import__()`, or framework-level plugin loading). These are invisible to static analysis and must be explicitly listed.

The `kingdom_sim.spec` file contains a `hiddenimports` list. Here is the full categorized list and why each category is needed:

### Panda3D (C Extensions)

These are native C++ extension modules that Panda3D loads dynamically:

```python
'panda3d.core',
'panda3d.direct',
'panda3d.egg',
'panda3d.physics',
'direct.showbase',
'direct.showbase.ShowBase',
'direct.task',
'direct.task.Task',
```

### Ursina (Lazy Imports Throughout game/graphics/)

Ursina uses extensive lazy importing. Many of these modules are imported inside function bodies or loaded on first use:

```python
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
'ursina.text',
'ursina.texture',
'ursina.vec2',
'ursina.vec3',
'ursina.window',
```

### Pygame

Pygame submodules that are imported dynamically:

```python
'pygame',
'pygame.mixer',
'pygame.font',
'pygame.image',
'pygame.transform',
'pygame.draw',
'pygame.surface',
'pygame.event',
```

### LLM Providers

```python
'anthropic',
'openai',
'google.generativeai',
'httpx',
```

### Other

```python
'PIL',
'PIL.Image',
'dotenv',
```

### How to Know When to Add a New Hidden Import

If a future code change adds an import that happens **inside a function body**, **inside a try/except**, or via any dynamic mechanism, and that import pulls in a module not already listed, the frozen build will crash with:

```
ModuleNotFoundError: No module named 'some_module'
```

The fix is always the same: add the module name to the `hiddenimports` list in `kingdom_sim.spec`.

**Common patterns that require hidden imports:**

```python
# Pattern 1: Import inside a function (very common in Ursina code)
def create_entity():
    from ursina import Mesh  # PyInstaller won't see this

# Pattern 2: Import inside try/except
try:
    import some_optional_module
except ImportError:
    some_optional_module = None

# Pattern 3: Framework-level dynamic loading
# Panda3D and Ursina do this extensively internally
```

---

## 8. What Gets Bundled (and What Does Not)

### Bundled (in the spec's `datas` and `binaries`)

These are explicitly listed in `kingdom_sim.spec` and end up inside `_internal/` in the output:

| Source Path | Destination in Bundle | Contents |
|-------------|----------------------|----------|
| `assets/audio/` | `assets/audio/` | .ogg and .wav sound effects |
| `assets/sprites/` | `assets/sprites/` | .png sprite sheets |
| `assets/models/` | `assets/models/` | ALL model formats (.glb, .obj, .fbx, etc.) |
| `assets/prefabs/` | `assets/prefabs/` | .json building kitbash definitions |
| `assets/textures/` | `assets/textures/` | .png texture overrides |
| `assets/maps/` | `assets/maps/` | .json map layouts |
| `assets/ui/` | `assets/ui/` | UI assets |
| `models_compressed/` | `models_compressed/` | Pre-compiled .bam model cache |
| `config.py` | `config.py` | Gameplay configuration dataclasses |
| `.env.example` | `.env.example` | API key template (NOT real keys!) |
| `assets/ATTRIBUTION.md` | `assets/ATTRIBUTION.md` | CC0 license credits |
| `panda3d/etc/` | `panda3d/etc/` | Config.prc, Confauto.prc |
| `panda3d/models/` | `panda3d/models/` | Built-in Panda3D models |
| `ursina/fonts/` | `ursina/fonts/` | OpenSans-Regular.ttf, VeraMono.ttf |
| `ursina/models/` | `ursina/models/` | Primitive geometry (.obj files) |
| `ursina/models_compressed/` | `ursina/models_compressed/` | Pre-compiled .bam primitives |
| `ursina/textures/` | `ursina/textures/` | Default textures |
| `ursina/shaders/` | `ursina/shaders/` | GLSL shader files |
| ~20 Panda3D DLLs | `panda3d/` | Display modules, audio, codecs |

### NOT Bundled (dev-only, intentionally excluded)

| Directory | Why It Is Excluded |
|-----------|-------------------|
| `tools/` | Build scripts, profilers, dev utilities. Not needed at runtime. |
| `studio_gateway/` | AI agent orchestration system. Dev infrastructure only. |
| `tests/` | pytest suite. Not needed in distribution. |
| `.cursor/` | Plans, agent logs, IDE configuration. |
| `.claude/` | Worktrees, memory. AI assistant configuration. |
| `.env` | **Real API keys. NEVER ship this.** |
| `docs/` | Screenshots, documentation. Not needed at runtime. |

### Security Note

The `.env` file contains real LLM API keys and must **never** be included in the bundle. The spec includes `.env.example` (the template with placeholder values) instead. If you see `.env` (without `.example`) in the `datas` list, that is a security issue and must be removed immediately.

---

## 9. The Build Pipeline

### One-Command Build

```powershell
python tools/build_executable.py --clean --test
```

This single command handles the entire build-test cycle.

### What the Build Script Does (Step by Step)

1. **Validates prerequisites:**
   - Checks that `C:\KingdomBuild\venv` exists
   - Checks that PyInstaller is installed in the venv
   - Checks that `kingdom_sim.spec` exists in the repo root

2. **Cleans previous build artifacts** (if `--clean` is passed):
   - Deletes `C:\KingdomBuild\build\` (intermediate files)
   - Deletes `C:\KingdomBuild\dist\` (previous output)

3. **Invokes PyInstaller:**
   ```powershell
   C:\KingdomBuild\venv\Scripts\python.exe -m PyInstaller kingdom_sim.spec --distpath C:\KingdomBuild\dist --workpath C:\KingdomBuild\build --noconfirm
   ```
   Key flags:
   - `--distpath C:\KingdomBuild\dist` -- output goes outside OneDrive
   - `--workpath C:\KingdomBuild\build` -- intermediate files go outside OneDrive
   - `--noconfirm` -- overwrite existing output without prompting

4. **Verifies the output:**
   - Checks that `KingdomSim.exe` exists at the expected path
   - Prints the total file count and directory size

5. **Runs the smoke test** (if `--test` is passed):
   - Launches `KingdomSim.exe`
   - Waits 15 seconds
   - Checks for crashes, Python errors, and display initialization
   - Reports pass/fail for each test case

### Build Performance

| Metric | Value |
|--------|-------|
| Build time (from clean) | ~72 seconds |
| Output size | 449 MB |
| Output file count | 14,082 files |

---

## 10. Smoke Tests

The automated smoke test suite lives at `tools/test_frozen_exe.py`. It runs 5 test cases against the built executable:

| ID | Name | What It Checks |
|----|------|---------------|
| TC-01 | EXE_EXISTS | The `KingdomSim.exe` file exists on disk at the expected path. |
| TC-02 | BOOT | The process is still alive after 15 seconds (it did not crash immediately). |
| TC-03 | NO_PYTHON_ERRORS | Zero occurrences of `FileNotFoundError`, `ModuleNotFoundError`, `ImportError`, or `Traceback` in stderr output. |
| TC-04 | RENDER_INIT | The string `wglGraphicsPipe` is detected in stderr, proving the Panda3D display pipeline initialized successfully. |
| TC-05 | CLEAN_EXIT | The process can be terminated cleanly (responds to termination signal). |

### Why TC-04 Uses stderr Instead of stdout

The frozen `.exe` buffers stdout indefinitely. This is Python's default behavior when stdout is not connected to a terminal (a TTY). Since the smoke test captures output via subprocess pipes (not a terminal), stdout never flushes. The boot banner "Kingdom Sim" never appears in captured stdout.

However, Panda3D writes its display initialization messages to stderr (via its C++ logging system), which is NOT subject to Python's stdout buffering. The smoke test checks stderr for `wglGraphicsPipe` as evidence that the display pipeline initialized.

---

## 11. Known Safe Warnings

During the build process and at runtime, you will see various warnings. The following are **safe to ignore** -- they do not indicate problems:

| # | Warning Message | Why It Is Safe |
|---|----------------|---------------|
| 1 | `Invalid integer value for ConfigVariable win-size: 1080.0` | Panda3D is parsing a float as an integer. The window opens fine regardless. |
| 2 | `Unable to open .../models_compressed/...bam` | BAM cache miss. The engine falls back to loading the original .glb model. Non-fatal, just slightly slower for that particular model load. |
| 3 | `Could not find icon filename textures/ursina.ico` | Cosmetic only. The default Windows icon is used instead. |
| 4 | `google.generativeai deprecation` | Google renamed their SDK. This is a build-time warning only and does not affect functionality. |
| 5 | `Hidden import "pycparser.lextab" not found!` | Optional parser tables for the `pycparser` package. Not needed at runtime. |
| 6 | `Hidden import "tzdata" not found!` | Timezone data. Not needed for a game that does not display real-world times. |

---

## 12. Known Issues

### Hero Rendering Performance in Frozen Build

**Symptom:** When heroes are spawned in the frozen build, the game exhibits frame skipping and heroes appear to teleport between positions rather than moving smoothly.

**Root cause:** This is a **pre-existing performance issue** in the instanced unit renderer (`game/graphics/instanced_unit_renderer.py`). It is NOT a packaging defect. The frozen build amplifies it slightly due to marginally slower module access in the PyInstaller bundle compared to running from source.

**Status:** Needs a dedicated performance profiling sprint (Agent 10 - Perf). Not a packaging blocker.

### Stdout Buffering

**Symptom:** The frozen `.exe` buffers stdout indefinitely. The "Kingdom Sim" boot banner and any `print()` output never flushes when stdout is redirected to a file or pipe.

**Root cause:** Python's default behavior when stdout is not connected to a terminal. This is standard Python behavior, not a PyInstaller issue.

**Workaround:** The smoke test (`test_frozen_exe.py`) checks stderr for `wglGraphicsPipe` initialization evidence instead of relying on stdout.

**Potential fix (not yet implemented):** Add `-u` (unbuffered) to the Python interpreter flags in the spec, or set `PYTHONUNBUFFERED=1` as an environment variable in the entry point. This was not done during the WK25 spike because it was not a functional blocker.

---

## 13. Key Files Reference

| File | Location (relative to repo root) | Purpose |
|------|----------------------------------|---------|
| `kingdom_sim.spec` | Root | PyInstaller build specification. Defines the entry point, all asset bundles, all hidden imports, and all Panda3D DLL binaries. This is THE most important file for packaging. |
| `game/paths.py` | `game/` | Centralized path resolution module. Contains the `sys._MEIPASS` / `sys.frozen` check. All runtime code must import paths from here. |
| `version_info.txt` | Root | Windows `.exe` metadata: version 1.5.5.0, company name "Kingdom Sim Studio". This information appears in the Properties dialog when right-clicking the .exe. |
| `tools/build_executable.py` | `tools/` | The one-command build pipeline script. Validates prerequisites, invokes PyInstaller, verifies output, and optionally runs smoke tests. |
| `tools/test_frozen_exe.py` | `tools/` | Automated 5-case smoke test suite. Launches the built .exe and checks for crashes, errors, and successful display initialization. |
| `requirements.txt` | Root | All Python dependencies including ursina, panda3d, pygame, pyinstaller, and LLM provider packages. |
| `.cursor/plans/wk25_packaging_spike.plan.md` | `.cursor/plans/` | The full master plan for the WK25 Packaging Spike, with all agent audits and round-by-round documentation. |

---

## 14. When to Update the Spec

The `kingdom_sim.spec` file needs to be updated when any of the following occur:

### New Asset Directories

If a new directory is added under `assets/` (e.g., `assets/cinematics/`), it must be added to the `datas` list in the spec:

```python
('assets/cinematics', 'assets/cinematics'),
```

Without this, the directory will exist in the source tree but be absent from the frozen build.

### New Python Packages with Lazy/Dynamic Imports

If a new dependency is added to the project and it uses lazy or dynamic imports, its modules must be added to `hiddenimports`. Common signs:
- The package works fine in development but crashes with `ModuleNotFoundError` in the frozen build.
- The package uses plugin architectures or `importlib.import_module()`.

### New Custom Shaders

If new Ursina shaders are added, the corresponding `ursina.shaders.*` submodules may need to be added to `hiddenimports`. Ursina loads shader modules lazily.

### Entry Point Changes

If `main.py` is renamed, moved, or restructured, the `Analysis` block in the spec must be updated to point to the new entry point:

```python
a = Analysis(
    ['main.py'],  # <-- This must match the actual entry point
    ...
)
```

### Panda3D or Ursina Upgrades

If the Panda3D or Ursina packages are upgraded to new versions:
- **Panda3D DLL names may change.** The list of DLLs in the spec's `binaries` section may need updating.
- **Ursina resource directory structure may change.** The `datas` entries for `ursina/fonts/`, `ursina/models/`, etc., may need updating.
- **New hidden imports may be required** if the upgraded package introduces new lazy-loading behavior.

Always test the frozen build after upgrading either of these packages.

---

## 15. Step-by-Step From Scratch (If the Venv is Lost)

If the build environment at `C:\KingdomBuild\` is deleted, corrupted, or a new machine needs to be set up, follow these steps exactly:

### Step 1: Install Python 3.11

```powershell
winget install Python.Python.3.11
```

Verify installation:

```powershell
py -3.11 --version
# Expected output: Python 3.11.9 (or any 3.11.x)
```

### Step 2: Create the Build Directory and Virtual Environment

```powershell
mkdir C:\KingdomBuild
py -3.11 -m venv C:\KingdomBuild\venv
```

Verify the venv:

```powershell
C:\KingdomBuild\venv\Scripts\python.exe --version
# Expected output: Python 3.11.x
```

### Step 3: Install All Dependencies

```powershell
C:\KingdomBuild\venv\Scripts\python.exe -m pip install --upgrade pip
C:\KingdomBuild\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify PyInstaller is available:

```powershell
C:\KingdomBuild\venv\Scripts\python.exe -m PyInstaller --version
```

### Step 4: Run the Build

```powershell
python tools/build_executable.py --clean --test
```

### Step 5: Verify the Output

After a successful build:

```powershell
# Check that the exe exists
Test-Path C:\KingdomBuild\dist\KingdomSim\KingdomSim.exe

# Check the output size
(Get-ChildItem C:\KingdomBuild\dist\KingdomSim -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
# Expected: ~449 MB

# Count the files
(Get-ChildItem C:\KingdomBuild\dist\KingdomSim -Recurse -File).Count
# Expected: ~14,082
```

### Step 6: Manual Smoke Test (Optional)

If you want to test manually instead of using `--test`:

```powershell
# Launch the exe
Start-Process C:\KingdomBuild\dist\KingdomSim\KingdomSim.exe

# Wait for a window to appear
# If a 3D window opens with the game world visible, the build is working
# Close the window when done
```

---

## 16. Rules for Future Developers and Agents

This section codifies the lessons learned during the WK25 Packaging Spike into rules that must be followed to prevent regressions.

### Rule 1: Never Compute Your Own Project Root

**Wrong:**
```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]
```

**Right:**
```python
from game.paths import PROJECT_ROOT, ASSETS_DIR
```

If you add a new file under `game/` that needs to load assets, import from `game.paths`. The `parents[N]` pattern resolves to the wrong directory in frozen builds.

### Rule 2: Always Add New Asset Directories to the Spec

If you create a new directory under `assets/` (e.g., `assets/particles/`), you must add a corresponding `datas` entry to `kingdom_sim.spec`. The build script does not auto-discover new directories.

### Rule 3: Always Add New Dynamic Imports to hiddenimports

If you add a new `import` statement inside a function body, inside a `try/except`, or via `importlib`, and the imported module is not already in the `hiddenimports` list, add it. Test by running the frozen build -- if you see `ModuleNotFoundError`, the missing module needs to be added.

### Rule 4: Verify Directory Paths Before Adding to Spec

Before adding a path to `datas` or `binaries` in the spec, confirm the directory or file actually exists. Use `Get-ChildItem` or `ls`. A nonexistent source path will silently result in a missing asset at runtime.

### Rule 5: Test the Frozen Build After Any Structural Change

"Structural change" means:
- Adding, renaming, or moving files in `game/`
- Adding new Python dependencies
- Adding new asset directories
- Upgrading Panda3D or Ursina
- Modifying `main.py`

Run `python tools/build_executable.py --clean --test` after any structural change.

### Rule 6: Build Outside OneDrive

Never change the build output paths to point inside the OneDrive-synced repo directory. The build generates thousands of temporary files that will cripple OneDrive sync and corrupt the build.

### Rule 7: Use Python 3.11 for Building

Do not attempt to build with Python 3.12 or later. Panda3D has known compatibility issues with 3.12+. The build venv must be created with `py -3.11`.
