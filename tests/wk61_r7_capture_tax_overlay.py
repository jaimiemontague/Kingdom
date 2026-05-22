"""
WK61 R7 — Ursina hold-G tax gold overlay capture for QA verification.

Writes a short-lived runner under repo root so Ursina asset_folder resolves
correctly, applies the capture patch, subprocesses main.py, and saves one PNG.

Usage (repo root)::

    python tests/wk61_r7_capture_tax_overlay.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / ".wk61_r7_capture_runner.py"


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.ursina_screenshot import next_auto_screenshot_path_for

    out_path = next_auto_screenshot_path_for(
        subdir="wk61_r7_tax_overlay",
        stem="hold_g_multi_building",
    )
    env = os.environ.copy()
    env["KINGDOM_URSINA_AUTO_EXIT_SEC"] = "12"
    env["KINGDOM_URSINA_AUTO_SCREENSHOT_PATH"] = out_path
    env["KINGDOM_URSINA_PREFAB_TEST_LAYOUT"] = "1"
    env["KINGDOM_URSINA_REVEAL_ON_START"] = "1"
    env["KINGDOM_URSINA_EDITORCAMERA"] = "0"
    env["KINGDOM_URSINA_CAM_FOCUS_SPAN"] = "32"

    runner_src = textwrap.dedent(
        f"""
        import importlib.util
        import runpy
        import sys
        from pathlib import Path

        ROOT = Path(__file__).resolve().parent
        sys.path.insert(0, str(ROOT))
        patch_path = ROOT / "tests" / "wk61_r7_capture_patch.py"
        spec = importlib.util.spec_from_file_location("wk61_r7_capture_patch", patch_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        sys.argv = [str(ROOT / "main.py"), "--renderer", "ursina", "--no-llm"]
        import main as kingdom_main

        kingdom_main.main()
        """
    ).strip()
    RUNNER.write_text(runner_src, encoding="utf-8")

    print(f"[wk61-r7-capture] Will write: {out_path}", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(RUNNER)],
            cwd=str(ROOT),
            env=env,
        )
    finally:
        RUNNER.unlink(missing_ok=True)

    if result.returncode == 0 and Path(out_path).is_file():
        print(f"[wk61-r7-capture] Saved: {out_path}", flush=True)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
