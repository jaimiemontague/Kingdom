"""
Kenney pack scale policy (WK31) — **single source of truth** for Tools + runtime.

**Calibration:** *Retro Fantasy Kit* (raw tree folder ``kenney_retro-fantasy-kit`` and
merged ``Models/GLB format`` pieces without a newer pack suffix) is the **1.0**
reference: a model uniformly fit to ``RETRO_REFERENCE_MAX_EXTENT`` world units matches
the grid “one cell ≈ one unit” feel used when kitbashing military / house prefabs.

Other Kenney packs ship GLBs at different native scales. We apply a **per-pack
uniform multiplier** on:

- ``model_viewer_kenney`` — ``_fit_uniform_and_ground(..., max_extent=...)``
- ``model_assembler_kenney`` — piece entity scale (authored JSON scale is *logical*;
  multiplier applied at display time only)
- ``game/graphics/ursina_renderer._load_prefab_instance`` — same multiplier on each
  piece’s ``scale`` tuple

**Tuning:** Starting multipliers are conservative; Agent 15’s wall/fence flush pass
may justify raising/lowering factors or adding filename-specific overrides later.
Encode new empirical defaults here (or in a small data file imported here) so
viewer / assembler / game stay aligned.

**WK31 Agent 15 (flush evidence):** Side-by-side Ursina pairs with bounds-based
spacing (``tools/wall_flush_pair_kenney.py`` + ``docs/screenshots/wk31_flush/``)
confirmed **no change** to Fantasy Town / Graveyard / Nature / Survival
folder multipliers (1.10 / 1.10 / 1.20 / 1.14). Merged ``Models/GLB format``
Survival disambiguation (raw-tree diff + §3.3 collisions) was added so Survival
pieces in prefabs get the Survival multiplier without raw paths.

See: ``.cursor/plans/wk31_kingdom_perf_and_economy.plan.md`` Part A.2.1,
``.cursor/plans/kenney_assets_models_mapping.plan.md``.
"""
from __future__ import annotations

from pathlib import Path

# Grid fit reference: uniform-fit target (max axis length after fit) for Retro.
RETRO_REFERENCE_MAX_EXTENT = 5.0

# Per top-level Kenney raw-download folder id (under
# ``Models/Kenny raw downloads (for exact paths)/``). Values are multipliers on
# ``RETRO_REFERENCE_MAX_EXTENT`` for the viewer’s uniform fit, and uniform scale on
# prefab pieces at runtime (relative to Retro).
_PACK_EXTENT_MULTIPLIER_BY_FOLDER: dict[str, float] = {
    "kenney_retro-fantasy-kit": 1.0,
    "kenney_survival-kit": 1.14,
    "kenney_nature-kit": 1.20,
    "kenney_fantasy-town-kit_2.0": 1.10,
    "kenney_graveyard-kit_5.0": 1.10,
    "kenney_blocky-characters_20": 1.0,
    "kenney_cursor-pixel-pack": 1.0,
}

# Merged ``Models/GLB format`` mixes Retro + Survival (+ suffixed FT/GY); unsuffixed
# names default to Retro (1.0) except as resolved below (WK31 Agent 15 + mapping §3.3).
_MERGED_GLB_DEFAULT_MULTIPLIER = 1.0

# Basenames that appear **only** in ``kenney_survival-kit`` (not in Retro raw GLB list).
# Computed at import from ``assets/models/.../Kenny raw downloads`` when present.
_SURVIVAL_RAW_GLB: Path | None = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "models"
    / "Models"
    / "Kenny raw downloads (for exact paths)"
    / "kenney_survival-kit"
    / "Models"
    / "GLB format"
)
_RETRO_RAW_GLB: Path | None = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "models"
    / "Models"
    / "Kenny raw downloads (for exact paths)"
    / "kenney_retro-fantasy-kit"
    / "Models"
    / "GLB format"
)


def _load_merged_survival_only_basenames() -> frozenset[str]:
    """Filenames in Survival but not Retro — merged ``Models/GLB format`` uses Survival bytes."""
    try:
        if _SURVIVAL_RAW_GLB is None or _RETRO_RAW_GLB is None:
            return frozenset()
        if not _SURVIVAL_RAW_GLB.is_dir() or not _RETRO_RAW_GLB.is_dir():
            return frozenset()
        sset = {p.name.lower() for p in _SURVIVAL_RAW_GLB.glob("*.glb")}
        rset = {p.name.lower() for p in _RETRO_RAW_GLB.glob("*.glb")}
        return frozenset(sset - rset)
    except OSError:
        return frozenset()


_MERGED_SURVIVAL_ONLY_BASENAMES = _load_merged_survival_only_basenames()

# Retro–Survival filename collisions: which pack’s copy lives in merged ``Models/GLB format``.
# See ``kenney_assets_models_mapping.plan.md`` §3.3.
_MERGED_COLLISION_PACK: dict[str, str] = {
    "fence.glb": "retro",
    "floor.glb": "survival",
    "structure.glb": "survival",
}


def _norm_rel(rel: str) -> str:
    return str(rel).replace("\\", "/").lstrip("/")


def infer_kenney_pack_folder_id(rel: str) -> str | None:
    """Best-effort pack id string for logs / attribution hints (not always unique)."""
    r = _norm_rel(rel)
    parts = tuple(Path(r).parts)
    raw_mark = "Kenny raw downloads (for exact paths)"
    if raw_mark in parts:
        i = parts.index(raw_mark)
        if i + 1 < len(parts):
            return parts[i + 1]
    name = Path(r).name.lower()
    if name.endswith("-fantasy-town.glb") or name.endswith("-fantasy-town.gltf"):
        return "kenney_fantasy-town-kit_2.0"
    if name.endswith("-graveyard.glb") or name.endswith("-graveyard.gltf"):
        return "kenney_graveyard-kit_5.0"
    stem = Path(name).stem
    if stem.startswith("character-") and len(stem) == len("character-x"):
        return "kenney_blocky-characters_20"
    if r.startswith("environment/"):
        return None
    if r.startswith("Models/GLB format/"):
        return "__merged_glb__"
    if r.startswith("Models/GLTF format/"):
        return "kenney_nature-kit"
    return None


def pack_extent_multiplier_for_rel(rel: str) -> float:
    """Uniform extent/scale multiplier vs Retro (1.0 = Retro Fantasy calibration)."""
    r = _norm_rel(rel)
    if not r:
        return 1.0
    if r.startswith("environment/"):
        return 1.0

    parts = tuple(Path(r).parts)
    raw_mark = "Kenny raw downloads (for exact paths)"
    if raw_mark in parts:
        i = parts.index(raw_mark)
        if i + 1 < len(parts):
            folder = parts[i + 1]
            return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER.get(folder, 1.0))

    name = Path(r).name
    nl = name.lower()
    if nl.endswith("-fantasy-town.glb") or nl.endswith("-fantasy-town.gltf"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_fantasy-town-kit_2.0"])
    if nl.endswith("-graveyard.glb") or nl.endswith("-graveyard.gltf"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_graveyard-kit_5.0"])

    stem_l = Path(nl).stem
    if stem_l.startswith("character-") and len(stem_l) == len("character-x"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_blocky-characters_20"])

    if r.startswith("Models/GLB format/"):
        bn = Path(r).name.lower()
        if bn in _MERGED_COLLISION_PACK:
            side = _MERGED_COLLISION_PACK[bn]
            if side == "survival":
                return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_survival-kit"])
            return float(_MERGED_GLB_DEFAULT_MULTIPLIER)
        if bn in _MERGED_SURVIVAL_ONLY_BASENAMES:
            return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_survival-kit"])
        return float(_MERGED_GLB_DEFAULT_MULTIPLIER)
    if r.startswith("Models/GLTF format/"):
        return float(_PACK_EXTENT_MULTIPLIER_BY_FOLDER["kenney_nature-kit"])

    return 1.0


def pack_max_extent_for_rel(rel: str, *, base_max_extent: float = RETRO_REFERENCE_MAX_EXTENT) -> float:
    """Max axis length after uniform fit (viewer / wall-flush tools)."""
    return float(base_max_extent) * pack_extent_multiplier_for_rel(rel)
