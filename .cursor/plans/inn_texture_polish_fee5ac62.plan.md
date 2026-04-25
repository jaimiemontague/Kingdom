---
name: inn texture polish
overview: Create a texture-focused polish pass for the Inn so its Fantasy Town brown, grey, and teal materials read closer to the Retro Fantasy stone buildings in-game, with screenshots as a hard acceptance gate.
todos:
  - id: inspect-materials
    content: Inspect Inn Fantasy Town pieces in model viewer/debug materials and confirm whether whole-piece texture overrides are viable.
    status: completed
  - id: capture-baseline
    content: Capture baseline Inn/base overview/building catalog screenshots under docs/screenshots/wk32_inn_texture/.
    status: completed
  - id: add-tool-capture
    content: Add any missing screenshot/capture tooling for the model viewer and model assembler so Agent 09 can inspect rendered texture results directly.
    status: completed
  - id: author-textures
    content: Create or acquire wood, stone, and roof texture PNGs from license-safe sources, using online reference and attribution proof.
    status: completed
  - id: wire-overrides
    content: Add optional prefab texture overrides to schema, renderer, assembler, and inn_v2 metadata with cached nearest-neighbor texture loading.
    status: completed
  - id: iterate-screenshots
    content: Run game and tool screenshots after each pass; revise until the Inn visually matches nearby Retro-style buildings.
    status: completed
  - id: verify-log
    content: Run qa_smoke and validate_assets, then update Agent 09 log with evidence and screenshot paths.
    status: completed
isProject: false
---

# Inn Texture Polish Plan

## Goal
Bring `assets/prefabs/buildings/inn_v2.json` visually closer to the Retro Fantasy buildings in the screenshot by replacing the flat-looking Fantasy Town material reads with low-poly/pixel-textured surfaces:

- Brown wall/trim surfaces -> warm wood plank texture.
- Grey wall/foundation surfaces -> blocky stone texture.
- Teal roof surfaces -> darker roof tile/shingle texture.

The current Inn prefab is mostly Fantasy Town pieces in [`assets/prefabs/buildings/inn_v2.json`](assets/prefabs/buildings/inn_v2.json), while nearby buildings like [`assets/prefabs/buildings/warrior_guild_v1.json`](assets/prefabs/buildings/warrior_guild_v1.json) and [`assets/prefabs/buildings/castle_v1.json`](assets/prefabs/buildings/castle_v1.json) use Retro Fantasy pieces with more baked texture detail.

## Reference, Texture Sources, And Art Direction
Use online references and source textures from permissive sources. Kenney remains the preferred style reference because the surrounding buildings already use Kenney assets, but the work is not limited to Kenney packs if another source is a better fit.

- Kenney Retro Fantasy Kit: https://kenney.nl/assets/retro-fantasy-kit
- Kenney Retro Textures Fantasy: https://kenney.nl/assets/retro-textures-fantasy
- Other allowed sources: CC0/public-domain texture libraries, permissive commercial-use packs, or generated in-repo textures created from scratch using references.

If texture source files are downloaded, keep license/source proof under `.cursor/human_provided/` and update [`assets/ATTRIBUTION.md`](assets/ATTRIBUTION.md). Do not use unclear, AI-scraped, editorial-only, or non-commercial texture sources. If textures are generated in-repo from scratch using references, record them as Kingdom Sim CC0 generated assets and keep a short note describing the reference set.

Texture style constraints:

- Low-res, tileable, nearest-neighbor friendly, likely `64x64` or `128x128` PNGs.
- No photorealism; use chunky shapes, limited ramps, and baked top-left lighting.
- Match the screenshot’s Retro stone value range: muted, readable, not saturated teal.
- Avoid noisy high-frequency grain that shimmers at the default camera distance.

## Implementation Approach
Add a small prefab texture override path rather than replacing the whole Inn model or mutating raw Kenney GLBs.

- Add curated textures under a new folder such as [`assets/textures/buildings/inn/`](assets/textures/buildings/inn/):
  - `inn_wood_planks.png`
  - `inn_stone_blocks.png`
  - `inn_roof_shingles.png`
- Extend [`assets/prefabs/schema.md`](assets/prefabs/schema.md) with an optional per-piece texture override field, for example `texture_override` relative to `assets/`.
- Update [`assets/prefabs/buildings/inn_v2.json`](assets/prefabs/buildings/inn_v2.json) to assign overrides by piece type:
  - `wall-wood-*fantasy-town.glb` -> wood planks.
  - `wall-*fantasy-town.glb` / curb or foundation pieces -> stone blocks where appropriate.
  - `roof-*fantasy-town.glb` -> roof shingles.
- Update [`game/graphics/ursina_renderer.py`](game/graphics/ursina_renderer.py) in `_load_prefab_instance` to load texture overrides once, cache them by path, set nearest-neighbor filtering, and apply them after `_apply_gltf_color_and_shading`.
- Mirror the same override display in [`tools/model_assembler_kenney.py`](tools/model_assembler_kenney.py) so `--open inn_v2` shows the same result as the game.
- If whole-piece overrides damage windows/doors or UVs, fallback plan is to create Inn-specific duplicate model assets with edited embedded/external textures, then point only the Inn prefab at those derived assets.

## Tooling Scope
Create or extend any local tools needed to make the visual review loop reliable. This is explicitly in scope for this plan.

- Add a model-viewer capture path if [`tools/model_viewer_kenney.py`](tools/model_viewer_kenney.py) cannot currently save a focused screenshot of the relevant Inn pieces with the applied texture override.
- Add a model-assembler capture path if [`tools/model_assembler_kenney.py`](tools/model_assembler_kenney.py) cannot currently open `inn_v2`, frame it, save a screenshot, and exit automatically.
- Prefer a shared helper or CLI pattern consistent with [`tools/run_ursina_capture_once.py`](tools/run_ursina_capture_once.py), `KINGDOM_SCREENSHOT_SUBDIR`, `KINGDOM_SCREENSHOT_STEM`, and the synchronous screenshot path in [`game/graphics/ursina_app.py`](game/graphics/ursina_app.py).
- Save tool screenshots under `docs/screenshots/wk32_inn_texture/tool_viewer/` and `docs/screenshots/wk32_inn_texture/tool_assembler/`.
- Use the tool screenshots as first-pass evidence before launching the full game view; the final acceptance still requires in-game screenshots beside other buildings.

## Screenshot And Review Loop
Do not call the work done until the screenshots look cohesive next to the Retro buildings.

Capture baseline first:

```powershell
python tools/model_viewer_kenney.py --debug-materials
python tools/model_assembler_kenney.py --open inn_v2
python tools/run_ursina_capture_once.py --seconds 8 --subdir wk32_inn_texture --stem before_inn --no-llm
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk32_inn_texture/before_base_overview --size 1920x1080 --ticks 120
python tools/capture_screenshots.py --scenario building_catalog --seed 3 --out docs/screenshots/wk32_inn_texture/before_building_catalog --size 1920x1080 --ticks 120
```

After each texture iteration:

```powershell
python tools/model_assembler_kenney.py --open inn_v2
python tools/model_viewer_kenney.py --debug-materials
python tools/run_ursina_capture_once.py --seconds 8 --subdir wk32_inn_texture --stem after_inn_iterN --no-llm
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk32_inn_texture/after_base_overview_iterN --size 1920x1080 --ticks 120
python tools/capture_screenshots.py --scenario building_catalog --seed 3 --out docs/screenshots/wk32_inn_texture/after_building_catalog_iterN --size 1920x1080 --ticks 120
```

If the viewer/assembler commands are still manual-only, first add explicit capture commands such as:

```powershell
python tools/model_viewer_kenney.py --focus inn --screenshot-subdir wk32_inn_texture/tool_viewer --screenshot-stem inn_materials --auto-exit-sec 5
python tools/model_assembler_kenney.py --open inn_v2 --screenshot-subdir wk32_inn_texture/tool_assembler --screenshot-stem inn_v2 --auto-exit-sec 5
```

The exact flags can differ if they better match the existing tool architecture, but the result must be an automated screenshot path that Agent 09 can inspect without relying only on a live window.

Review each iteration against this checklist:

- Wood reads as wood at default zoom, not flat brown paint.
- Stone reads as masonry and belongs beside the castle/guild stone style.
- Roof no longer reads as a flat teal block; it has shingle/tile structure and a muted value.
- Inn remains distinct as an Inn, not visually confused with guild/castle buildings.
- No texture crawling, UV stretching, black materials, or over-dark pack tint artifacts.

## Gates
Run the normal project gates after the final visual pass:

```powershell
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Final log should include the chosen reference/source, texture file paths, before/after screenshot paths, gate results, and a short Agent 09 art signoff explaining why the Inn now matches the Retro-style building family.