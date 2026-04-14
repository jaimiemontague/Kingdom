import os
from pathlib import Path
from ursina import *

def test_rotation():
    app = Ursina(borderless=False)
    
    import gltf
    import panda3d.core as p3d
    
    p = Path("assets/models/Models/GLB format/workbench-anvil.glb").resolve()
    gs = gltf.GltfSettings()
    root = gltf.load_model(str(p), gltf_settings=gs)
    np = p3d.NodePath(root)
    
    ent = Entity(model=np, position=(0,0,0))
    # If we rotate it -90 on X, does Y become height?
    ent.rotation_x = -90
    
    # Check visual bounds
    tb = ent.model.getTightBounds()
    print(f"Original model tight bounds: {tb}")
    
    # Ursina uses Entity.bounds for the scaled/rotated AABB? No.
    # But if we rotate Entity, the visual appearance will stand up!
    print("Done")
    sys.exit(0)

if __name__ == "__main__":
    test_rotation()
