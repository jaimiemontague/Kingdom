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

**WK32 / WK32-BUG-005:** ``pack_color_multiplier_for_rel`` + ``apply_kenney_pack_color_tint_to_entity`` —
non-Retro Kenney packs use multiplier **0.75** (~25% darker vs Retro **1.00**); promoted
``environment/`` meshes use the Nature Kit tint (also **0.75**). **Extent** for ``environment/``
stays **1.0** in ``pack_extent_multiplier_for_rel``. See plan workstream E + PM revision 2026-04-18.

WK67 Round A-2 (L9): the per-pack scale + tint policy moved verbatim into
``game.graphics.kenney_material`` (sever the ``game/graphics -> tools`` runtime
import). This module is now a thin **re-export** so every existing tools consumer
(``model_viewer_kenney``, ``model_assembler_kenney``, ``wall_flush_pair_kenney``,
``wk31_flush_screenshot_batch``, …) keeps importing these symbols from
``tools.kenney_pack_scale`` unchanged. ``tools`` -> ``game`` is the allowed
(non-circular) import direction.
"""
from __future__ import annotations

from game.graphics.kenney_material import (  # noqa: F401
    RETRO_REFERENCE_MAX_EXTENT,
    _ENV_TREE_COLOR_MULTIPLIER_DEFAULT,
    _MERGED_COLLISION_PACK,
    _MERGED_GLB_DEFAULT_MULTIPLIER,
    _MERGED_SURVIVAL_ONLY_BASENAMES,
    _PACK_COLOR_MULTIPLIER_BY_FOLDER,
    _PACK_EXTENT_MULTIPLIER_BY_FOLDER,
    _RETRO_RAW_GLB,
    _SURVIVAL_RAW_GLB,
    _load_merged_survival_only_basenames,
    _norm_rel,
    apply_kenney_pack_color_tint_to_entity,
    infer_kenney_pack_folder_id,
    pack_color_multiplier_for_rel,
    pack_extent_multiplier_for_rel,
    pack_max_extent_for_rel,
)
