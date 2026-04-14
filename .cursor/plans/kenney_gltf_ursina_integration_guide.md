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

The same pitfalls appear in **any** Ursina `Entity(model=…)` path that uses the **default entity shader** (see §3). The game’s **`ursina_renderer.py`** will hit the same issues unless materials and color are folded in explicitly or the renderer uses a shader that reads glTF PBR material properties.

---

## 2. Loader and formats

| Topic | Discovery |
|--------|-----------|
| **Loader** | Use Panda’s **`gltf`** package: `gltf.load_model(path, gltf_settings=GltfSettings())` → `NodePath`. Same pipeline as intended for production loads. |
| **Formats in repo** | Kenney ships **duplicate exports** (`.obj`, `.fbx`, `.dae`, `.glb`, `.gltf`). The viewer **only scans `.glb` and `.gltf`** to avoid duplicate grids and missing-texture OBJ/MTL confusion. For game integration, pick **one** canonical format per asset (usually **`.glb`**). |
| **Self-contained vs split** | **`.glb`** embeds buffers/textures. **`.gltf`** may reference external images; paths are relative to the file — wrong CWD breaks textures. Prefer **`.glb`** for fewer path bugs. |

---

## 3. Ursina `Entity` default shader vs glTF materials

| Topic | Discovery |
|--------|-----------|
| **Default behavior** | New `Entity(...)` sets **`unlit_with_fog_shader`** (unless overridden). Fragment is effectively **`texture(p3d_Texture0, uvs) * p3d_ColorScale * vertex_color`**. |
| **Material `base_color` ignored** | That unlit path **does not** read Panda **`Material.base_color`** or glTF **`baseColorFactor`**. Untextured PBR materials (factor-only) can look **flat white** if you do nothing else. |
| **`setShaderAuto()` on the entity** | Calling **`setShaderAuto()`** on the entity (or clearing shaders without a controlled light rig) switched meshes to a **lit/PBR-style** path that **did not** match the scene’s Ursina lights in the viewer → **black silhouettes**, apparent **missing** models, and regressions. **Do not** treat “just add `setShaderAuto`” as a universal fix for game scenes without validating lights + shader compatibility. |
| **`clearShader()` + `setShaderAuto()` on model** | Same category: broke visibility and lighting in the standalone viewer. **Not recommended** as a drop-in for the game unless the full render/light setup matches Panda’s generated shader expectations. |

**Implication for the game:** If you keep **unlit** for performance/style, you must **explicitly** supply albedo via **texture stage 0**, **vertex color**, and/or **`ColorAttrib`** (see §5). If you move to **full PBR**, you must **light** the scene consistently with that path (see master plan Phase 4).

---

## 4. Three ways Kenney assets encode “color”

Real examples from inspecting files in-repo:

| Style | Example | What the glTF contains | Unlit default path |
|--------|---------|-------------------------|---------------------|
| **Textured** | `wall.glb` (Retro Fantasy) | **`baseColorTexture`** + UVs; no `COLOR_0` | Textures show if stage 0 is correct; **no** `baseColorFactor` needed in shader if texture carries the look. |
| **Solid materials (no textures)** | `cliff_block_rock.glb` (Nature Kit) | **`images: 0`, `textures: 0`**; **`baseColorFactor`** per material only; **`COLOR_0` absent** | Unlit ignores factors → **white** unless you **inject** color (§5). |
| **Vertex-painted** | Some kits | **`COLOR_0`** + often white **`baseColorFactor`** | Needs **`ColorAttrib` vertex mode** so `p3d_Color` in the shader comes from the mesh, not flat white. |

**Rule:** Inspect the asset (quick JSON chunk in `.glb` or Blender) before guessing: **texture vs factor vs vertex** drives the fix.

---

## 5. Practical fix pattern used in `model_viewer_kenney.py` (unlit-friendly)

For **standalone viewer** we **did not** rely on PBR auto-shading. Instead, after **`gltf.load_model`** and **`Entity(...)`**, we run **`_apply_unlit_gltf_color_attribs(model_root)`**, which walks **`GeomNode`s** and **per-geom** `RenderState`:

1. If the geom’s state has a **`Base Color` texture stage** with a **real texture** → keep texturing; if the mesh has a **color column**, set **`ColorAttrib.make_vertex()`** for vertex paint.
2. If there is **no** base-color texture → if the mesh has **vertex colors**, use **vertex** mode; else **`ColorAttrib.make_flat(material base / diffuse)`** from the loaded **`Material`** so unlit multiplies the correct RGBA.

**Game port:** Reuse this logic (or an equivalent shader that multiplies **baseColorFactor** and **COLOR_0** per glTF) when spawning environment props with **unlit** rendering. Centralize it in one helper used by **`ursina_renderer`** (or shared `game/graphics/` utility) rather than copy-pasting per prefab.

---

## 6. Lighting (viewer lessons; applicable to lit paths)

| Topic | Discovery |
|--------|-----------|
| **Single strong directional** | Reads as “lit from one side”; orbiting the camera leaves **large black** regions (Lambert falloff), mistaken for “broken” assets. |
| **Wrap-style rig** | **High ambient** + **several weak directionals** from different directions reduced “one stripe lit, rest black” for **unlit** + readable preview. |
| **Not a substitute for PBR lights** | If you switch the mesh to **shader-auto / PBR**, scene lights must match that pipeline (see §3). |

---

## 7. Orientation and scale (viewer false starts)

| Topic | Discovery |
|--------|-----------|
| **Ad-hoc axis fix** | Applying **`-90°` on X** to “fix Z-up vs Y-up” **laid models on their side** in our setup and made **thin** props nearly invisible from above. **Do not** apply a global rotation without verifying bounds and one known-good asset. |
| **Scale** | Uniform scale from **tight bounds** to a max extent is fine; avoid **random Y translation** based on bounds unless you confirm the asset’s ground plane in a DCC tool. |

---

## 8. Checklist before shipping a Kenney glTF in-game

- [ ] Confirmed **one** export format (prefer **`.glb`**) and **no** duplicate `.obj` variant required at runtime.
- [ ] Verified **color encoding**: texture / `baseColorFactor` only / `COLOR_0` / combination.
- [ ] If using **default unlit** entity shader: applied **§5-style** color handling OR custom shader that respects glTF factors.
- [ ] If using **PBR / `setShaderAuto`**: validated **scene lights** and **no** black-silhouette regression on target hardware.
- [ ] **QA:** `python tools/qa_smoke.py --quick` after renderer changes; spot-check with **`python tools/model_viewer_kenney.py`** for raw asset appearance.

---

## 9. Related docs

| Doc | Role |
|-----|------|
| [kenney_assets_models_mapping.plan.md](./kenney_assets_models_mapping.plan.md) | Folder map, packs, merged OBJ paths. |
| [master_plan_3d_graphics_v1_5.md](./master_plan_3d_graphics_v1_5.md) | v1.5 3D roadmap (renderer, phases). |
| `tools/model_viewer_kenney.py` | Runnable reference: scan, layout, lighting rig, `_apply_unlit_gltf_color_attribs`. |

---

## 10. Revision history (high level)

- **v0.1** (viewer): Kenney-only `.glb`/`.gltf` scan, EditorCamera, duplicate-format filter.
- **v0.2** (viewer): Unlit-compatible **`baseColorFactor`** / vertex color via per-geom **`ColorAttrib`**; avoided **`clearShader` + `setShaderAuto`** regression (black / missing draws).

*This guide should be updated when the in-game renderer’s shading path changes (e.g. full PBR in v1.5 Phase 4).*
