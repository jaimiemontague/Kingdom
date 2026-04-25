---
name: prefab-texture-override-standard
overview: Standard procedure for replacing weak Kenney pack material reads with curated in-repo textures, without mutating original Kenney GLBs.
todos: []
isProject: false
---

# Prefab Texture Override Standard

Use this when a Kenney model is technically loading correctly, but the source material is not good enough for Kingdom Sim's camera or current art family.

This standard was proven on `assets/prefabs/buildings/inn_v2.json`, where the Fantasy Town Kit Inn pieces had flat brown, grey, and teal reads that did not match nearby Retro Fantasy stone buildings. The successful path was **not** to edit Kenney GLBs. It was to add curated texture PNGs under `assets/textures/`, assign them per prefab piece with `texture_override`, and display them through the shared override shader in runtime and tools.

## When To Use This

Use texture overrides when all of these are true:

- The model loads, scales, and shades correctly.
- The source pack's material is visually weaker than surrounding buildings.
- The mismatch is surface read, not silhouette, scale, pivot, or mesh structure.
- You can improve the asset with a small set of reusable low-res textures.
- You need the improvement scoped to one prefab or one building family.

Do not use texture overrides when:

- The mesh silhouette is wrong.
- The prefab is made from the wrong pieces.
- Windows, doors, trim, or props need separate material channels but the source mesh does not expose them cleanly.
- A replacement Retro Fantasy piece would solve the issue more cleanly.
- The desired result requires photorealism or PBR.

## Decision Tree

1. Inspect the source pieces.
   - Run `python tools/model_viewer_kenney.py --focus-prefab <prefab_id> --debug-materials --auto-exit-sec 3 --screenshot-subdir <subdir> --screenshot-stem <stem>`.
   - Confirm whether pieces are textured, factor-only, or vertex-colored.
   - Confirm whether the issue is flat color, weak atlas texture, over-bright pack tint, or actual missing texture.

2. Try a whole-piece texture override only if the piece can tolerate it.
   - Good candidates: plain wall, roof, curb, floor, rock, ground, simple trim.
   - Risky candidates: doors, windows, banners, shop stalls, signs, pieces with decorative atlas regions.
   - If a whole-piece override damages a detailed piece, remove the override from that piece and preserve its source material.

3. If original Kenney atlas colors appear on top of the override, fix the override application, not the texture.
   - The proven fix is recursive render-state cleanup in `game/graphics/prefab_texture_overrides.py`.
   - Clear old texture state on the model and child NodePaths before binding the override texture.
   - Apply the override shader and shader input recursively.

4. If the original UVs are atlas-swatch UVs, do not rely on the source UVs for detail.
   - Fantasy Town Kit pieces often sample tiny atlas regions.
   - A normal replacement texture bound to the original UVs can still look flat or show old atlas fragments.
   - The proven fix is object-space texture mapping in the override shader.

5. Capture screenshots and iterate.
   - Tool view first: assembler/model viewer.
   - Then in-game row against nearby style references.
   - Do not call the pass done until screenshots prove the asset sits with the target family.

## Files Involved

Texture assets:

- `assets/textures/buildings/<prefab_or_family>/<name>.png`
- `assets/textures/buildings/<prefab_or_family>/README.md`
- `assets/ATTRIBUTION.md`

Prefab metadata:

- `assets/prefabs/buildings/<prefab_id>.json`
- `assets/prefabs/schema.md`

Runtime/tool display:

- `game/graphics/prefab_texture_overrides.py`
- `game/graphics/ursina_renderer.py`
- `tools/model_assembler_kenney.py`
- `tools/model_viewer_kenney.py`
- `tools/ursina_capture.py`

Validation:

- `tools/validate_assets.py`
- `python tools/qa_smoke.py --quick`
- `python tools/validate_assets.py --report`

## Texture Authoring Rules

Keep textures low-res and stylized:

- Prefer `64x64` or `128x128` PNG.
- Use nearest-neighbor-friendly shapes.
- Avoid photoreal grain.
- Bake simple top-left highlights and lower-right shadows into the pixels.
- Keep color ramps narrow and muted.
- Ensure the texture still reads at the actual strategy camera distance.

For Kingdom Sim's current visual language:

- Wood should read as broad plank structure, not noisy bark.
- Stone should read as chunky Retro Fantasy masonry: warm tan-grey blocks, uneven shapes, dark mortar, and small chips.
- Roof should read as muted teal/blue-grey shingles or tiles, not a flat saturated slab.

## License And Attribution

Preferred source is generated in-repo CC0 texture art, using references only for style direction.

If generated in-repo:

- Add or update a generator script, such as `tools/generate_inn_texture_overrides.py`.
- Add a README beside the generated textures.
- Add an `assets/ATTRIBUTION.md` entry such as `kingdomsim_generated_building_textures`.
- State that no third-party pixels were copied.

If downloaded:

- Use only CC0/public-domain or permissive commercial-use textures.
- Store license/source proof under `.cursor/human_provided/` if needed.
- Update `assets/ATTRIBUTION.md`.
- Do not use unclear, editorial-only, non-commercial, AI-scraped, or attribution-ambiguous sources.

## Prefab JSON Pattern

Add `texture_override` only to pieces that need it.

```json
{
  "model": "Models/GLB format/roof-right-fantasy-town.glb",
  "pos": [1.5, 2.05, 1.25],
  "rot": [0.0, 90.0, 0.0],
  "scale": [1.0, 1.0, 1.0],
  "texture_override": "textures/buildings/inn/inn_roof_shingles.png"
}
```

Rules:

- Path is relative to `assets/`.
- Use POSIX slashes.
- Keep attribution updated if textures are generated or acquired.
- Do not add overrides to pieces where it destroys necessary details unless you have a separate detail-preserving strategy.
- For the Inn, final successful assignments were:
  - `roof-*fantasy-town.glb` -> `textures/buildings/inn/inn_roof_shingles.png`
  - `wall-wood-*fantasy-town.glb` -> `textures/buildings/inn/inn_wood_planks.png`
  - `wall-*fantasy-town.glb` and `road-curb-fantasy-town.glb` -> `textures/buildings/inn/inn_stone_blocks.png`

## Runtime Implementation Rules

Use `game/graphics/prefab_texture_overrides.py` as the single source of truth.

Required behavior:

- Resolve override paths under `assets/` only.
- Cache textures by absolute path.
- Load with PIL and create Ursina `Texture(..., filtering=None)`.
- Bind the texture after normal glTF color/shading setup.
- Do not apply source pack albedo darkening on top of override textures.
- Clear old texture state on the model and child NodePaths.
- Apply the override shader and `tex` shader input recursively.

Why recursive cleanup matters:

- GLB scene graphs can carry texture state below the root model.
- Setting `entity.texture` alone may not clear child `TextureAttrib`s.
- If child nodes keep the original Fantasy Town atlas, the old colored strips can appear on top of the new texture.
- The Inn refinement pass fixed this by clearing and rebinding texture state on the model plus all child NodePaths.

## Object-Space Texture Mapping

Use object-space mapping when source UVs are not useful.

Why:

- Kenney atlas-based pieces often use tiny UV islands into `colormap-*.png`.
- Binding a new detailed texture through those UVs can sample only one small region or smear unexpectedly.
- Object-space mapping ignores those atlas UVs and projects texture detail from model/world position.

The proven shader strategy:

- Vertex shader outputs world position and world normal.
- Fragment shader chooses planar UVs based on dominant normal axis.
- Horizontal faces use `worldPos.xz`.
- X-facing vertical faces use `worldPos.zy`.
- Z-facing vertical faces use `worldPos.xy`.
- UVs are tiled with `fract(uv)`.
- A small Lambert-style shade term keeps surfaces from becoming flat.

Do not use `setShaderAuto()`. It has already failed with black/invisible renders in this Ursina/Panda setup.

## Tooling Requirements

Every texture override path must be visible in both runtime and tools.

Required tool support:

- `tools/model_assembler_kenney.py` must show the same `texture_override` result as the game.
- `tools/model_viewer_kenney.py --focus-prefab <prefab_id>` must load the prefab's unique pieces and apply texture overrides for piece inspection.
- Both tools should support:
  - `--screenshot-subdir`
  - `--screenshot-stem`
  - `--auto-exit-sec`

Example commands:

```powershell
python tools/model_viewer_kenney.py --focus-prefab inn_v2 --debug-materials --auto-exit-sec 3 --screenshot-subdir wk32_inn_texture/tool_viewer --screenshot-stem after_inn_pieces
python tools/model_assembler_kenney.py --open inn_v2 --auto-exit-sec 3 --screenshot-subdir wk32_inn_texture/tool_assembler --screenshot-stem after_inn_v2
```

## In-Game Screenshot Requirements

Use the prefab test layout when comparing building families.

```powershell
$env:KINGDOM_URSINA_PREFAB_TEST_LAYOUT='1'
$env:KINGDOM_URSINA_EDITORCAMERA='0'
python tools/run_ursina_capture_once.py --seconds 8 --subdir wk32_inn_texture --stem after_inn_prefab_oblique --no-llm
$env:KINGDOM_URSINA_PREFAB_TEST_LAYOUT=''
$env:KINGDOM_URSINA_EDITORCAMERA=''
```

Also keep deterministic 2D/tool captures where useful:

```powershell
python tools/capture_screenshots.py --scenario base_overview --seed 3 --out docs/screenshots/wk32_inn_texture/after_base_overview --size 1920x1080 --ticks 120
python tools/capture_screenshots.py --scenario building_catalog --seed 3 --out docs/screenshots/wk32_inn_texture/after_building_catalog --size 1920x1080 --ticks 120
```

## Visual Acceptance Checklist

Before signing off:

- Wood reads as wood at default zoom.
- Stone reads like the target family, not generic brick or concrete.
- Roof has muted shingle/tile detail and no saturated teal slab.
- Doors and windows still read clearly.
- Original atlas colors are not visibly bleeding through.
- No black/invisible materials.
- No giant flat panels blocking the model.
- No texture crawling or shimmer at default camera distance.
- The building still reads as its gameplay type.
- The building sits with nearby Retro Fantasy / current terrain assets.

## Known Bad Attempts

Do not repeat these without a good reason:

- Editing source Kenney GLBs in place.
- Adding opaque quad panels in front of the model to "paint" texture detail. This can block the camera or create grey panels if the primitive path fails.
- Applying overrides to every piece blindly. Detailed door/window pieces can lose important read.
- Assuming `entity.texture = tex` is enough. It may leave child node texture state intact.
- Using `setShaderAuto()` for glTF/PBR material recovery.
- Calling the work done after a tool screenshot only. Final acceptance needs an in-game screenshot beside target-style buildings.

## Inn v2 Reference Implementation

The Inn pass is the reference implementation for this standard.

Key files:

- `assets/prefabs/buildings/inn_v2.json`
- `assets/textures/buildings/inn/inn_wood_planks.png`
- `assets/textures/buildings/inn/inn_stone_blocks.png`
- `assets/textures/buildings/inn/inn_roof_shingles.png`
- `tools/generate_inn_texture_overrides.py`
- `game/graphics/prefab_texture_overrides.py`
- `tools/model_assembler_kenney.py`
- `tools/model_viewer_kenney.py`

Final evidence from the successful pass:

- `docs/screenshots/wk32_inn_texture/tool_assembler/after_inn_v2_refine1_20260425_041105_734.png`
- `docs/screenshots/wk32_inn_texture/after_inn_refine_oblique1_20260425_041110_040.png`

Verification:

```powershell
python tools/qa_smoke.py --quick
python tools/validate_assets.py --report
```

Expected result:

- `qa_smoke` PASS.
- `validate_assets` PASS with `errors=0`.
- Existing missing-model warnings may remain until the broader 3D asset roster is filled.
