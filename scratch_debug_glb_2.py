import os
from pathlib import Path
import gltf
from panda3d.core import NodePath

def test_load(rel_path):
    p = Path(rel_path).resolve()
    print(f"Loading {p}")
    if not p.exists():
        print("  - File does not exist!")
        return

    try:
        gs = gltf.GltfSettings()
        gs.no_srgb = False
        model_root = gltf.load_model(str(p), gltf_settings=gs)
        if model_root is None:
            print("  - model_root is None")
        else:
            np = NodePath(model_root)
            print(f"  - Loaded. Transform: {np.getTransform()}")
            print(f"  - Bounds: {np.getTightBounds()}")
    except Exception as e:
        print(f"  - Exception: {e}")

if __name__ == "__main__":
    test_load("assets/models/Models/GLB format/tree.glb")
