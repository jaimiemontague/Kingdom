---
name: Unit Instancing HD-2D Visual Polish
overview: "Sprint 2 of the Unit Instancing Master Plan (wk48). Reinvests reclaimed CPU/GPU performance into premium visual polish. Delivers sub-pixel movement interpolation (exponential smoothing), performant blob shadows via shared instance buffers, projectile instancing, and removes the feature gate to make instancing the default pipeline."
todos:
  - id: sprint2-wave1
    content: "Sprint 2 Wave 1: Agent 03 implements visual position caching & exponential smoothing (lerping) + inside-building layer separation."
    status: pending
  - id: sprint2-wave2
    content: "Sprint 2 Wave 2: Agent 09 implements Blob Shadows (second GeomNode + custom shader) & Projectile instancing."
    status: pending
  - id: sprint2-wave3
    content: "Sprint 2 Wave 3: Agent 11 removes feature gate, deprecates legacy paths, and runs QA gates."
    status: pending
isProject: false
---

# Master Plan: HD-2D Visual Polish (Instancing Phase 2)

## Problem Statement

With the core instancing pipeline (WK47) complete, the game handles massive unit counts performantly. However, the units move rigidly (snapping to grid/sim ticks), lack grounding in the 3D environment, and projectiles still use the slow legacy rendering path. 

**Target**: A premium, buttery-smooth visual experience ("HD-2D" feel) without sacrificing the performance gains from Sprint 1.

---

## Wave 1: Sub-Pixel Smoothing & Compositing

### Agent 03 (Architecture)
**Task**: Implement render-only movement smoothing (exponential trailing) and fix "inside building" draw order.

#### 1. Movement Smoothing (Exponential Trailing)
**Context**: The simulation updates synchronously with the frame rate (`dt`), but without a fixed-step accumulator. True deterministic interpolation isn't possible. Instead, we use a **render-only visual position cache**.
**Instructions**:
1. In `InstancedUnitRenderer`, add a dictionary to track visual positions: `self._visual_pos_by_id: dict[int, tuple[float, float, float]] = {}`
2. During `update()`, for each unit, calculate the world position (`target_wx, target_wy, target_wz`).
3. Fetch the previous visual position from `_visual_pos_by_id`. If it doesn't exist, use the target position immediately.
4. If it does exist, calculate the distance. If the distance is very large (e.g., > 1.5 world units), **snap** to the target immediately (handles teleports / entering buildings).
5. If the distance is small, use exponential smoothing: `visual_pos += (target_pos - visual_pos) * (1.0 - math.exp(-SMOOTHING_SPEED * dt))`. A good `SMOOTHING_SPEED` is around `15.0`.
6. Pack the `visual_pos` into the instance buffer instead of the raw `target_pos`.
7. Update `_visual_pos_by_id` with the new `visual_pos`.
8. Clean up dead units from `_visual_pos_by_id` at the end of `update()`.

**Code Example (`instanced_unit_renderer.py`)**:
```python
# Helper for exponential smoothing
import math
from ursina import time

def _smooth_position(self, obj_id: int, target_pos: tuple[float, float, float]) -> tuple[float, float, float]:
    tx, ty, tz = target_pos
    if obj_id not in self._visual_pos_by_id:
        self._visual_pos_by_id[obj_id] = target_pos
        return target_pos
        
    vx, vy, vz = self._visual_pos_by_id[obj_id]
    
    # Snap if distance is too large (teleport)
    dist_sq = (tx - vx)**2 + (ty - vy)**2 + (tz - vz)**2
    if dist_sq > 2.25:  # 1.5^2
        self._visual_pos_by_id[obj_id] = target_pos
        return target_pos
        
    # Exponential smoothing
    dt = time.dt
    lerp_factor = 1.0 - math.exp(-15.0 * dt)
    new_x = vx + (tx - vx) * lerp_factor
    new_y = vy + (ty - vy) * lerp_factor
    new_z = vz + (tz - vz) * lerp_factor
    
    new_pos = (new_x, new_y, new_z)
    self._visual_pos_by_id[obj_id] = new_pos
    return new_pos
```

#### 2. Inside-Building Compositing (Two Passes)
**Context**: Heroes inside buildings need to render on top of the 3D building footprint.
**Instructions**:
1. We need TWO GeomNodes. Rename `self._geom_node_path` to `self._geom_node_outside`.
2. Create `self._geom_node_inside` identically, but set:
   - `self._geom_node_inside.set_depth_test(False)`
   - `self._geom_node_inside.set_bin("fixed", 100)` (Draw late, over everything)
3. Both GeomNodes must share the exact same `self._instance_buffer`.
4. In `update()`, pack `outside_units` first, recording `count_outside`. Then pack `inside_units`, recording `count_inside`.
5. Set the instance counts: 
   - `_geom_node_outside.set_instance_count(count_outside)`
   - `_geom_node_inside.set_instance_count(count_inside)`
6. **CRITICAL**: For `_geom_node_inside`, we must tell Panda3D to start rendering instances from an offset (skip the outside units). Use `geom.set_instance_count(count_inside)` but we also need an offset. Wait, `Geom.set_instance_count` doesn't take an offset. 
7. **Alternative**: If offsets are hard, just use two separate buffer textures. Since inside units are rare, a small secondary buffer (`_instance_buffer_inside`) is perfectly fine and much easier.

**Verification**:
- Command a unit to walk. It should glide buttery-smooth between tiles.
- Command a hero to enter a building. They should render on top of the building roof/structure.

---

## Wave 2: Environmental Grounding & Projectiles

### Agent 09 (Visual Pipeline)
**Task**: Implement performant Blob Shadows and Projectile Instancing.

#### 1. Blob Shadows (Shared Instance Data)
**Context**: Drawing individual shadow entities ruins performance. We can draw shadows for free by creating a second GeomNode that reads the *same* `_instance_buffer`.
**Instructions**:
1. In `InstancedUnitRenderer._ensure_initialized()`, create `self._shadow_geom_node` (a quad lying flat on the X/Z floor).
2. Bind `self._instance_buffer` to it.
3. Write `game/graphics/shadow_instanced_shader.py` (GLSL).
   - **Vertex Shader**: Reads position from `instanceData`. Ignores the UV region data. Sets Y to `0.01` (just above terrain). Scales the shadow slightly wider than the unit.
   - **Fragment Shader**: Draws a procedural radial gradient fading to `alpha=0.0`.
4. Render Queue: `self._shadow_geom_node.set_bin("transparent", 0)` (Before the units).
5. **Caveat**: Shadows should ONLY cover grounded units. Skip projectiles and inside-building units. If inside-units use a separate buffer (from Wave 1), simply don't bind a shadow node to that buffer.

**Code Example (`shadow_instanced_shader.py`)**:
```python
from ursina.shader import Shader
shadow_instanced_shader = Shader(
    name="shadow_instanced_shader", language=Shader.GLSL,
    vertex="""#version 330
    uniform mat4 p3d_ModelViewProjectionMatrix;
    in vec4 p3d_Vertex;
    in vec2 p3d_MultiTexCoord0;
    out vec2 uvs;
    uniform samplerBuffer instanceData;
    
    void main() {
        int base = gl_InstanceID * 2;
        vec4 posScale = texelFetch(instanceData, base);
        vec3 instancePos = posScale.xyz;
        float scale = posScale.w;
        
        // Flat on the floor, slightly wider than tall
        vec3 worldPos = vec3(
            instancePos.x + p3d_Vertex.x * scale * 1.2,
            0.01, // Hover just above terrain
            instancePos.z + p3d_Vertex.y * scale * 0.8
        );
        gl_Position = p3d_ModelViewProjectionMatrix * vec4(worldPos, 1.0);
        uvs = p3d_MultiTexCoord0;
    }
    """,
    fragment="""#version 330
    in vec2 uvs;
    out vec4 fragColor;
    void main() {
        // Radial gradient from center (0.5, 0.5)
        float dist = distance(uvs, vec2(0.5, 0.5));
        float alpha = smoothstep(0.5, 0.1, dist) * 0.6; // Max 60% opacity
        if (alpha < 0.01) discard;
        fragColor = vec4(0.0, 0.0, 0.0, alpha);
    }
    """
)
```

#### 2. Projectile Instancing
**Instructions**:
1. In `unit_atlas.py`, pack the projectile surface from `game.graphics.vfx.get_projectile_billboard_surface()` into the atlas under key `("vfx", "projectile", "arrow", 0)`.
2. In `instanced_unit_renderer.py` `update()`, add a loop for `snapshot.vfx_projectiles`.
3. Note: Projectiles shouldn't cast blob shadows. If you are sharing the `_instance_buffer` with the shadow node, you might need a secondary buffer for projectiles, or pass a flag in the `scale` w-component (e.g., negative scale means no shadow) and `discard` in the shadow vertex shader.

**Verification**:
- Use `python tools/take_screenshot.py` to capture a group of units. Verify soft oval shadows exist under them.
- Ensure arrows render properly and do not cast blob shadows.

---

## Wave 3: Feature Gate Removal & QA

### Agent 11 (QA)
**Task**: Finalize the pipeline.
1. In `ursina_renderer.py`, remove the `KINGDOM_URSINA_INSTANCING` environment variable check. Make `InstancedUnitRenderer` the absolute default path.
2. Delete legacy `_sync_snapshot_heroes`, `_sync_snapshot_enemies`, etc., from `UrsinaRenderer` to clean up technical debt.
3. Remove `_sync_snapshot_projectiles` from `UrsinaRenderer`.
4. Run `python tools/qa_smoke.py --quick`.
5. Run `python tools/perf_stress_test.py --units 500 --frames 300` to log final performance metrics for the patch notes.
