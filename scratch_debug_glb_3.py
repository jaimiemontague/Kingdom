import os
from pathlib import Path

def test_origins():
    # If the origin is naturally at the bottom, then we don't need to offset ent.y!
    import gltf
    from panda3d.core import NodePath
    
    ps = ["assets/models/Models/GLB format/tree.glb",
          "assets/models/Models/GLB format/barrel.glb", 
          "assets/models/Models/GLB format/fence.glb"]
          
    for p_str in ps:
        p = Path(p_str)
        gs = gltf.GltfSettings()
        root = gltf.load_model(str(p), gltf_settings=gs)
        np = NodePath(root)
        bounds = np.getTightBounds()
        print(f"{p.name}: bounds = {bounds}")

if __name__ == "__main__":
    test_origins()
