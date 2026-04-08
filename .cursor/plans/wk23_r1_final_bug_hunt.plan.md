# WK23 Round 1: Final Bug Hunt & Polish

This sprint targets four highly specific regressions and polish items. Below is the extensively researched plan for Agents 03 and 09 to execute without guesswork.

## User Review Required

> [!IMPORTANT]
> The plan handles the W/S inversion by directly swapping the addition/subtraction logic in `ursina_app.py`. Projectiles have been completely missing from Ursina (the renderer loop simply ignores the `gs["projectiles"]` array), so we'll add a rendering loop for them.

## Proposed Changes

---

### Bug 1: Projectiles & Fighting Animations Missing (Agent 09 - Art)

**Reasoning:**
Currently, `ursina_renderer.py`'s `update()` method loops over buildings, heroes, enemies, peasants, and guards. **It entirely ignores `gs.get("projectiles", [])`**, which is why arrows/magic are invisible in 3D.
Second, while heroes fetch their `anim_state`, it's possible Pygame's renderer is running first and wiping the `_render_anim_trigger` flag because both renderers manipulate the same simulation properties.

#### [MODIFY] `game/graphics/ursina_renderer.py`
- Add a new block for rendering projectiles at the end of `update()` (around Line 690, right before `heroes_alive = ...`). Iterate over `gs.get("projectiles", [])`, use `_get_or_create_entity`, and use `sprite_unlit_shader`.
```python
        # Projectiles — simple billboards
        for proj in gs.get("projectiles", []):
            s = 0.5
            ent, obj_id = self._get_or_create_entity(
                proj,
                model="quad",
                col=color.yellow,  # Fallback visible color
                scale=(s, s, 1),
                texture=None,
                billboard=True,
            )
            wx, wz = sim_px_to_world_xz(proj.x, proj.y)
            self._sync_billboard_entity(
                ent,
                tex=None,
                tint_col=color.yellow,
                scale_xyz=(s, s, 1),
                pos_xyz=(wx, s * 0.5, wz),
                shader=sprite_unlit_shader,
            )
            active_ids.add(obj_id)
```

---

### Bug 2: Peasant duplicate / "Dead" sprite staying forever (Agent 09 - Art)

**Reasoning:**
In `ursina_renderer.py` at line 636, the loop for peasants does not check `is_alive`. If the simulation keeps dead peasants in the array briefly to play a death animation or wait for cleanup, Ursina draws them forever as "idle".

#### [MODIFY] `game/graphics/ursina_renderer.py`
- Add `is_alive` checks to both the peasants and guards loops.
```python
        # Peasants — billboards
        for p in gs["peasants"]:
            if not getattr(p, "is_alive", True):
                continue
            # ... existing peasant code ...
            
        # Guards — billboards
        for g in gs["guards"]:
            if not getattr(g, "is_alive", True):
                continue
            # ... existing guard code ...
```

---

### Bug 3: Camera "W" and "S" keys inverted (Agent 03 - Architecture)

**Reasoning:**
In `ursina_app.py` around line 438, the pan handles `w` and `s`. Moving the camera "forward" (visually UP the screen) means increasing the Z coordinate. Currently, `hk["w"]` subtracts from `camera.z`, moving us South/Backwards. 

#### [MODIFY] `game/graphics/ursina_app.py`
- Swap the arithmetic for `w` and `s` exactly like this:
```python
            if hk["w"]:
                camera.z += pan_speed * dt
            if hk["s"]:
                camera.z -= pan_speed * dt
```

---

### Bug 4: Fog of War / Line of Sight Mismatch (Agent 03 - Architecture)

**Reasoning:**
The user reports: "hero can disappear into the fog of war in ursina and an invisible hero can be revealing the fog of war elsewhere". This indicates an offset. Both the Fog Quad and Terrain Quad must flawlessly match. If the terrain uses `(tw * ts) / SCALE` and `(th * ts) / SCALE`, then the Fog Quad must be perfectly aligned.

#### [MODIFY] `game/graphics/ursina_renderer.py`
- In `_ensure_fog_overlay()`, verify `wpx` and `hpx` exactly match the total world pixel sizes. Set `wx, wz` to literally match `_bake_terrain_floor()`.
- Ensure NO phantom offsets exist. In the `ent = Entity()` construction in `_ensure_fog_overlay`, make sure the calculation for `cx_px` and `cy_px` is correct, and verify if the buffer mapping (`row_unseen` loop) mirrors `ty` correctly.

## Verification Plan

### Manual Verification
- Press `W` and verify the view pans NORTH (up the screen).
- Hire a peasant, let goblins kill it, verify no duplicate sticky pixels remain.
- Send a hero into the black fog and ensure the illuminated circle accurately tracks their 3D billboard with no offsets.
- Place a bounty, let a ranger fire arrows. Verify projectiles exist.
