---
name: kenney-gltf-ursina-integration-guide
overview: Lessons from the Kenney GLB viewer for integrating glTF into Kingdom (Ursina / Panda3D).
todos: []
isProject: false
---

# Kenney glTF / Ursina Integration Guide

Reference document for **Agent 03 (Tech)**, **Agent 09 (Art)**, and anyone wiring **Kenney `.glb` / `.gltf`** into the game or tools. It summarizes what we learned building and iterating **`tools/model_viewer_kenney.py`** (standalone Ursina browser over `assets/models`).

**Canonical tool:** `python tools/model_viewer_kenney.py` (from repo root).

---

## 1. Why this matters in-game

The same pitfalls appear in **any** Ursina `Entity(model=…)` path that uses the **default entity shader** (see §3). The game's **`ursina_renderer.py`** will hit the same issues unless materials and color are handled per-geom using the two-path strategy documented in §5.

**Critical takeaway:** Kenney asset packs contain a **mix** of textured and untextured models. A single rendering strategy (unlit-only or lit-only) will always break one category. You must **classify each geom** and route it to the correct shader path. This is the single most important lesson from the viewer work.

---

## 2. Loader and formats

| Topic | Discovery |
|--------|-----------|
| **Loader** | Use Panda's **`gltf`** package: `gltf.load_model(path, gltf_settings=GltfSettings())` → `NodePath`. Same pipeline as intended for production loads. |
| **Formats in repo** | Kenney ships **duplicate exports** (`.obj`, `.fbx`, `.dae`, `.glb`, `.gltf`). The viewer **only scans `.glb` and `.gltf`** to avoid duplicate grids and missing-texture OBJ/MTL confusion. For game integration, pick **one** canonical format per asset (usually **`.glb`**). |
| **Self-contained vs split** | **`.glb`** embeds buffers/textures. **`.gltf`** may reference external images; paths are relative to the file — wrong CWD breaks textures. Prefer **`.glb`** for fewer path bugs. |

---

## 3. Ursina `Entity` default shader vs glTF materials

| Topic | Discovery |
|--------|-----------|
| **Default behavior** | New `Entity(...)` sets **`unlit_with_fog_shader`** (unless overridden). Fragment is effectively **`texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color`**. |
| **Material `base_color` ignored** | That unlit path **does not** read Panda **`Material.base_color`** or glTF **`baseColorFactor`**. Untextured PBR materials (factor-only) render **flat white** if you do nothing else. |
| **Scene lights ignored** | The default unlit shader ignores **all** scene lights (`AmbientLight`, `DirectionalLight`, etc.) completely. Even a perfect lighting rig has **zero effect** on entities using this shader. Lights only matter for entities using a lit shader path. |
| **`setShaderAuto()` — confirmed failure** | Calling **`setShaderAuto()`** on entities or GeomNodes causes **completely black/invisible** models. This was tested multiple times across v0.2 and v0.3 with different lighting rigs (including a 7-directional wrap setup). Panda3D's auto-generated PBR shader expects lighting inputs (IBL, environment probes) that simple Ursina `AmbientLight`/`DirectionalLight` nodes do not provide. **Do not use `setShaderAuto()` for Kenney assets in this project.** |
| **`clearShader()` + `setShaderAuto()` on model** | Same failure mode as above. **Not recommended.** |

**Implication for the game:** You cannot use a single shader for all Kenney assets. Use the **two-path strategy** in §5: unlit for textured geoms, custom lit for factor-only geoms.

---

## 4. Three ways Kenney assets encode "color"

Real examples from inspecting files in-repo:

| Style | Example pack | What the glTF contains | Visual behavior |
|--------|---------|-------------------------|---------------------|
| **Textured** | Retro Fantasy Kit, Survival Kit (`Models/GLB format/`) | **`baseColorTexture`** + UVs; no `COLOR_0` | Textures carry all visual detail. Unlit shader works fine — the texture provides shading baked into the art. |
| **Solid materials (no textures)** | Nature Kit (`Models/GLTF format/`) | **`images: 0`, `textures: 0`**; **`baseColorFactor`** per material only; **`COLOR_0` absent** | Colors are correct but geometry has **zero visual depth** under unlit. Needs a **lit shader** to produce 3D shading via normals. |
| **Vertex-painted** | Some kits | **`COLOR_0`** + often white **`baseColorFactor`** | Needs **`ColorAttrib.make_vertex()`** so `p3d_Color` in the shader comes from the mesh, not flat white. |

**Rule:** Inspect the asset (quick JSON chunk in `.glb` or Blender) before guessing: **texture vs factor vs vertex** drives the shader path.

**Critical distinction (learned the hard way):** Factor-only models are not "broken" or "missing textures." They are intentionally designed with solid-color materials. Their official Kenney previews show them with **lit shading** — the 3D depth comes from lighting interaction with surface normals, not from texture detail. Treating them as "unlit but with the right flat color" produces visually correct colors but looks like placeholder art.

---

## 5. The two-path shading strategy (v0.3 — confirmed working)

After loading with `gltf.load_model` and creating an `Entity(...)`, call **`_apply_gltf_color_and_shading(ent.model)`** which walks **`GeomNode`s** and classifies **per-geom**:

### Path A: Textured geoms (unlit — keep default Ursina shader)

- Detected by: `TextureAttrib` has at least one stage with a non-null texture.
- Action: Leave render state as-is (Ursina's default unlit shader displays the texture correctly).
- If vertex colors also present: set `ColorAttrib.make_vertex()` so vertex paint modulates the texture.

### Path B: Factor-only geoms (custom lit shader)

- Detected by: No texture stages with real textures AND no `COLOR_0` vertex attribute.
- Action:
  1. Extract `baseColorFactor` from the `Material` via `mat.get_base_color()` (fallback to `mat.get_diffuse()`, then white).
  2. Inject it into the render state via `ColorAttrib.make_flat(base_color)`.
  3. Set a **custom lightweight GLSL shader** on the `GeomNode` NodePath that reads `p3d_Color` and applies Lambert N·L lighting with hardcoded key + fill directions.

### Path C: Vertex-colored geoms (unlit)

- Detected by: No texture AND `COLOR_0` present in vertex data format.
- Action: `ColorAttrib.make_vertex()` — same as v0.2.

### The custom lit shader (factor_lit_shader)

This shader is the key innovation of v0.3. It avoids both the flat-unlit problem AND the `setShaderAuto()` black-silhouette regression by using a self-contained GLSL program:

```glsl
// Vertex shader
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat3 p3d_NormalMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec3 vNormal;
out vec4 vColor;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vNormal = normalize(p3d_NormalMatrix * p3d_Normal);
    vColor = p3d_Color;
}

// Fragment shader
#version 150
in vec3 vNormal;
in vec4 vColor;
out vec4 fragColor;
void main() {
    vec3 N = normalize(vNormal);
    vec3 keyDir  = normalize(vec3( 0.4,  0.7, -0.5));
    vec3 fillDir = normalize(vec3(-0.3,  0.4,  0.6));
    float key  = max(dot(N, keyDir),  0.0);
    float fill = max(dot(N, fillDir), 0.0);
    float shade = 0.38 + 0.48 * key + 0.18 * fill;
    fragColor = vec4(vColor.rgb * shade, vColor.a);
}
```

**Why this works when `setShaderAuto()` does not:**
- Does not depend on Panda3D's auto-shader infrastructure or PBR material pipeline.
- Does not read `p3d_LightSource` uniforms (which Ursina's simple lights may not populate correctly for PBR).
- Light directions are hardcoded in view space — consistent regardless of scene light setup.
- `p3d_Color` is reliably populated by `ColorAttrib.make_flat()` in the render state.
- Key + fill + ambient floor produces wrap-style shading that looks good from any camera angle.

**Game port:** When using this in `ursina_renderer.py`, create the shader once at init and reuse. The light directions can be adjusted or made into uniforms if the game needs dynamic lighting on factor-only models.

---

## 6. Lighting

### Scene lights (AmbientLight / DirectionalLight)

Scene lights in Ursina only affect entities using a shader that reads `p3d_LightSource` uniforms. Under the default `unlit_with_fog_shader`, they are **completely ignored**. Under `setShaderAuto()`, they cause **black renders** because Panda3D's generated PBR shader expects richer light data than Ursina provides.

**Practical impact:** The `_setup_scene_lighting()` function in the viewer sets up ambient + directional lights. These exist in the scene but have **no effect on any model rendering** in the current two-path strategy. The factor-only lit shader uses hardcoded light directions instead. The scene lights are retained for potential future use if a proper PBR path is implemented.

### Hardcoded lighting in the factor-only shader

The custom shader uses two hardcoded directions in view space:
- **Key light:** `(0.4, 0.7, -0.5)` — upper-right-front
- **Fill light:** `(-0.3, 0.4, 0.6)` — upper-left-back at 37% intensity
- **Ambient floor:** `0.38` — ensures no face is darker than 38% of its base color

This produces a shading range of roughly 0.38 (deep shadow) to ~1.0 (full light), giving clearly visible 3D depth while keeping shadow areas readable.

---

## 7. Orientation and scale (viewer false starts)

| Topic | Discovery |
|--------|-----------|
| **Ad-hoc axis fix** | Applying **`-90°` on X** to "fix Z-up vs Y-up" **laid models on their side** in our setup and made **thin** props nearly invisible from above. **Do not** apply a global rotation without verifying bounds and one known-good asset. |
| **Scale** | Uniform scale from **tight bounds** to a max extent is fine; avoid **random Y translation** based on bounds unless you confirm the asset's ground plane in a DCC tool. |

### 7.1 Pack scale vs pack color (WK31 / WK32 — single source: `tools/kenney_pack_scale.py`)

| Policy | Role |
|--------|------|
| **`pack_extent_multiplier_for_rel(rel)`** | Uniform fit / prefab piece scale vs **Retro Fantasy Kit = 1.0** (grid feel). Used by `model_viewer_kenney`, `model_assembler_kenney`, `ursina_renderer._load_prefab_instance`, and wall-flush tools. |
| **`pack_color_multiplier_for_rel(rel)`** | Albedo **tint** vs Retro = **1.0** (unchanged). Non-Retro packs use **0.75** (~25% darker): Survival, Nature, Fantasy Town, Graveyard, Blocky. **Retro** merged `Models/GLB format/` defaults and **cursor-pixel** stay **1.0**. **`environment/`** promoted meshes use the **Nature Kit** value (**0.75**) so grass / tree / rock in terrain match Nature-tinted kit pieces (WK32-BUG-005 retune 2026-04-18). |
| **`apply_kenney_pack_color_tint_to_entity(entity, rel)`** | After `_apply_gltf_color_and_shading`, sets `Entity.color` to `(m,m,m)` from `pack_color_multiplier_for_rel` so textured + factor-only paths both modulate consistently. |

Routing for **color** mirrors **extent** (same raw-folder names, merged `Models/GLB format` Survival vs Retro disambiguation, `Models/GLTF format` → Nature, suffix rules for Fantasy Town / Graveyard / Blocky). Paths may be passed either as `Models/...` / `environment/...` **or** with an `assets/models/` prefix (scatter entities use full `assets/models/environment/...` strings — the helper strips the prefix before classification). See WK32 workstream E in `wk32_camera_construction_nature_polish.plan.md`.

---

## 8. Debugging materials (`--debug-materials` flag)

The viewer supports `--debug-materials` which prints per-geom classification and aggregate counts:

```
python tools/model_viewer_kenney.py --debug-materials --max-total 300
```

Output shows for each geom: `branch=textured|textured_vertex|vertex|flat`, whether textures were found, and the texture stage name. Aggregate summary at the end shows totals.

**Critical testing lesson:** When using `--max-total` for sampling, be aware that models are loaded in **alphabetical path order**. With this repo's folder structure:
1. `environment/` (4 textured models)
2. `Models/GLB format/` (~200 textured models — Retro Fantasy / Survival Kit)
3. `Models/GLTF format/` (~329 factor-only models — Nature Kit)
4. `Models/Kenny raw downloads/` (~532 mixed models)

So `--max-total 200` will **only test textured models** and show `flat=0`, giving a false sense of correctness. To test the factor-only path, use `--max-total 250` or higher to reach the Nature Kit models. Always check that the aggregate output includes `flat > 0` before concluding the factor-only path is working.

---

## 9. Checklist before shipping a Kenney glTF in-game

- [ ] Confirmed **one** export format (prefer **`.glb`**) and **no** duplicate `.obj` variant required at runtime.
- [ ] Verified **color encoding** for the specific model: texture / `baseColorFactor` only / `COLOR_0` / combination.
- [ ] Implemented the **two-path strategy** (§5): unlit for textured, custom lit for factor-only.
- [ ] Factor-only models show **3D shading** (visible light/shadow variation on angled faces), not flat color blocks.
- [ ] Textured models are **not affected** by the factor-only shader path.
- [ ] **Did NOT use `setShaderAuto()`** — it produces black/invisible renders with Ursina's light setup.
- [ ] Debug-verified with `--debug-materials` using a `--max-total` large enough to include both textured AND factor-only models.
- [ ] Visual check by a **human** — automated diagnostics cannot confirm shading quality.
- [ ] **QA:** `python tools/qa_smoke.py --quick` after renderer changes.

---

## 10. Dead ends and pitfalls (post-mortem)

This section documents approaches that were tried, seemed correct based on code analysis, but failed upon visual review. Future agents should read this before proposing material/shader changes.

### Pitfall 1: Assuming flat colors meant misclassified textures (v0.2 bug hunt)

**What happened:** Factor-only Nature Kit models appeared as flat teal/orange blocks. The hypothesis was that the texture stage detection (`"Base Color"` exact string match) was too strict and missing textures bound under variant names.

**Why it seemed right:** The code had an exact string comparison `st.get_name() == "Base Color"` which could plausibly miss aliases. Broadening the detection to include case-insensitive aliases and fallback heuristics seemed like a sound fix.

**Why it was wrong:** The Nature Kit models have **zero textures** — no texture stages at all. The string matching code was never even reached for these models. The diagnostic data proved this (`flat=0` across all tested models) but the test sample was biased (see Pitfall 2).

**Lesson:** Before fixing a detection/classification path, verify that the path is actually being reached by the problematic assets. A classification fix for code that never runs on the affected models has zero impact.

### Pitfall 2: Biased test sampling via `--max-total`

**What happened:** All diagnostic runs used `--max-total 30` and `--max-total 200`. Due to alphabetical sort order, these samples contained exclusively textured models (Retro Fantasy/Survival Kit from `Models/GLB format/`). The Nature Kit models (from `Models/GLTF format/`) start at approximately index 204. The aggregate output showed `flat=0, textured=62` and `flat=0, textured=414` — which was interpreted as "no misclassification" rather than "we never tested the affected models."

**Why it seemed right:** The aggregate counts showed clean classification with zero errors, which appeared to validate the fix.

**Why it was wrong:** A test that never exercises the broken code path proves nothing. The `flat=0` should have been a red flag — if the visual problem is flat-colored models, and the diagnostics show zero flat-classified models, the sample is wrong.

**Lesson:** Always verify that your test sample includes representatives of the failing case. Check that the aggregate output shows the expected branch distribution before concluding.

### Pitfall 3: `setShaderAuto()` as the lit-shader solution (v0.3 first attempt)

**What happened:** After correctly identifying that factor-only models need a lit shader (not just correct color injection), `setShaderAuto()` was applied per-GeomNode. The viewer launched without errors, but all Nature Kit models rendered as **completely black/invisible**.

**Why it seemed right:** `setShaderAuto()` is Panda3D's standard way to enable auto-generated lighting shaders. The scene had a proper lighting rig (ambient + 7 directionals). The integration guide warned about this but attributed the failure to "inadequate lighting" — which had since been improved.

**Why it was wrong:** Panda3D's auto-shader generates a PBR-style shader for glTF materials. This shader expects lighting inputs (IBL environment maps, PBR-compatible light uniforms) that Ursina's simple `AmbientLight`/`DirectionalLight` wrappers do not provide correctly. The lighting rig quality is irrelevant — the **interface** between shader and lights is incompatible. No amount of ambient/directional tuning fixes a PBR shader that expects IBL probes.

**Lesson:** `setShaderAuto()` is not a reliable path for Ursina + glTF PBR materials. Use a custom GLSL shader with known inputs instead. The correct abstraction boundary is: if you control the shader source, you control what it needs.

### Pitfall 4: Treating "correct color" as "correct rendering"

**What happened:** The v0.2 fix successfully made flat-colored models show their correct `baseColorFactor` colors (teal, orange, brown, etc.) instead of white. This was declared working.

**Why it seemed right:** The colors matched Kenney's palette. The code was reading material properties correctly and injecting them into the render state.

**Why it was wrong:** Correct colors with zero shading looks like placeholder art. The official Kenney previews show these models with clear light/shadow variation from surface normals interacting with lighting. "Correct color" ≠ "correct rendering." The models need both correct color AND 3D shading to look right.

**Lesson:** Always compare against the asset author's official preview, not just against "white" or "black." The bar is not "colors are present" — it's "looks like the official preview."

---

## 11. Related docs

| Doc | Role |
|-----|------|
| [kenney_assets_models_mapping.plan.md](./kenney_assets_models_mapping.plan.md) | Folder map, packs, merged OBJ paths. |
| [master_plan_3d_graphics_v1_5.md](./master_plan_3d_graphics_v1_5.md) | v1.5 3D roadmap (renderer, phases). |
| `tools/model_viewer_kenney.py` | Runnable reference: scan, layout, two-path shading, `_apply_gltf_color_and_shading`. |

---

## 12. Revision history

- **v0.1** (viewer): Kenney-only `.glb`/`.gltf` scan, EditorCamera, duplicate-format filter.
- **v0.2** (viewer): Unlit-compatible `baseColorFactor` / vertex color via per-geom `ColorAttrib`; avoided `clearShader` + `setShaderAuto` regression (black / missing draws). Factor-only models showed correct colors but zero shading (flat appearance).
- **v0.3** (viewer): Two-path shading strategy. Textured geoms stay on unlit default. Factor-only geoms get a custom GLSL lit shader (`factor_lit_shader`) with hardcoded key+fill Lambert lighting via `p3d_Color` + `p3d_Normal`. Confirmed `setShaderAuto()` still produces black renders — replaced with custom shader. Added `--debug-materials` flag. Fixed `README.md` command reference. Documented sampling bias pitfall.

*This guide should be updated when the in-game renderer's shading path changes (e.g. full PBR in v1.5 Phase 4).*
