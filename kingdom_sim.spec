# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Kingdom Sim.

Build command:
    pyinstaller kingdom_sim.spec

Output: dist/KingdomSim/KingdomSim.exe  (--onedir mode)
"""

import os
import site
import glob

block_cipher = None

# ── Locate panda3d and ursina packages for bundling ──────────────
def _find_package(name):
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        candidate = os.path.join(sp, name)
        if os.path.isdir(candidate):
            return candidate
    mod = __import__(name)
    return os.path.dirname(mod.__file__)

_p3d_dir = _find_package('panda3d')
_ursina_dir = _find_package('ursina')

# ── Panda3D display/audio DLLs (dynamically loaded, not traced) ───
_p3d_dlls = []
for dll_name in [
    'libpandagl.dll', 'libpandadx9.dll', 'libp3tinydisplay.dll',
    'libp3windisplay.dll', 'libp3openal_audio.dll', 'libp3fmod_audio.dll',
    'libpandafx.dll', 'libpandaskel.dll', 'libp3ffmpeg.dll',
    'libp3ptloader.dll', 'libp3assimp.dll', 'libp3vision.dll',
    'libpandaai.dll', 'libpandaode.dll',
    'fmodex64.dll', 'cgD3D9.dll', 'cgGL.dll',
    'avcodec-55.dll', 'avformat-55.dll', 'avutil-52.dll',
    'swresample-0.dll', 'swscale-2.dll',
    'd3dx9_43.dll',
]:
    src = os.path.join(_p3d_dir, dll_name)
    if os.path.exists(src):
        _p3d_dlls.append((src, 'panda3d'))

# ── Asset data bundles ──────────────────────────────────────────────
# Each tuple: (source_glob_or_dir, dest_dir_in_bundle)
datas = [
    ('assets/audio',                  'assets/audio'),
    ('assets/sprites',                'assets/sprites'),
    ('assets/models',                 'assets/models'),
    ('models_compressed',             'models_compressed'),
    ('assets/prefabs',                'assets/prefabs'),
    ('assets/textures',               'assets/textures'),
    ('assets/maps',                   'assets/maps'),
    ('assets/ui',                     'assets/ui'),
    ('config.py',                     '.'),
    ('.env.example',                  '.'),
    ('assets/ATTRIBUTION.md',        'assets'),
    # Panda3D config files (display pipeline, model-cache, etc.)
    (os.path.join(_p3d_dir, 'etc'),   'panda3d/etc'),
    # Panda3D built-in models (fallback quad, etc.)
    (os.path.join(_p3d_dir, 'models'), 'panda3d/models'),
    # Ursina built-in resources (fonts, models, textures, shaders)
    (os.path.join(_ursina_dir, 'fonts'),             'ursina/fonts'),
    (os.path.join(_ursina_dir, 'models'),             'ursina/models'),
    (os.path.join(_ursina_dir, 'models_compressed'),  'ursina/models_compressed'),
    (os.path.join(_ursina_dir, 'textures'),           'ursina/textures'),
    (os.path.join(_ursina_dir, 'shaders'),            'ursina/shaders'),
]

# ── Hidden imports ──────────────────────────────────────────────────
# PyInstaller's static analysis misses these dynamic / lazy imports.
hiddenimports = [
    # Panda3D C extensions
    'panda3d.core',
    'panda3d.direct',
    'panda3d.egg',
    'panda3d.physics',
    'direct.showbase',
    'direct.showbase.ShowBase',
    'direct.task',
    'direct.task.Task',

    # Ursina internals (lazy-imported throughout game/graphics/)
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

    # Pygame
    'pygame',
    'pygame.mixer',
    'pygame.font',
    'pygame.image',
    'pygame.transform',
    'pygame.draw',
    'pygame.surface',
    'pygame.event',

    # LLM providers (included per decision)
    'anthropic',
    'openai',
    'google.generativeai',
    'httpx',

    # Pillow
    'PIL',
    'PIL.Image',

    # dotenv
    'dotenv',
]

# ── Modules to exclude (dev-only) ──────────────────────────────────
excludes = [
    'tkinter',
    'matplotlib',
    'scipy',
    'numpy.testing',
    'pytest',
    'IPython',
    'notebook',
]

# ── Analysis ────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_p3d_dlls,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── PYZ (compressed Python bytecode archive) ───────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── EXE ─────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KingdomSim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,                       # Sprint 3 switches to False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=None,                          # Sprint 2 adds .ico
)

# ── COLLECT (onedir output) ────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KingdomSim',
)
