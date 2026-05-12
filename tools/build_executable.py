"""
Build pipeline for packaging Kingdom Sim into a standalone .exe via PyInstaller.

Usage:
    python tools/build_executable.py              # full build
    python tools/build_executable.py --clean      # wipe artifacts, then build
    python tools/build_executable.py --test       # build + run smoke test
    python tools/build_executable.py --skip-build --test  # test existing build

Runnable from any Python interpreter; the actual PyInstaller step uses
the dedicated build venv.
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BUILD_VENV = Path(r"C:\KingdomBuild\venv")
BUILD_DIR = Path(r"C:\KingdomBuild\build")
DIST_DIR = Path(r"C:\KingdomBuild\dist")
EXE_NAME = "KingdomSim"

VENV_PYTHON = BUILD_VENV / "Scripts" / "python.exe"
EXE_PATH = DIST_DIR / EXE_NAME / f"{EXE_NAME}.exe"
REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO_ROOT / "kingdom_sim.spec"
TEST_SCRIPT = REPO_ROOT / "tools" / "test_frozen_exe.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fail(msg: str) -> None:
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def heading(text: str) -> None:
    print(f"\n{'='*60}\n  {text}\n{'='*60}")


def folder_stats(folder: Path) -> tuple[int, float]:
    """Return (file_count, total_size_mb) for a directory tree."""
    files = list(folder.rglob("*"))
    files = [f for f in files if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    return len(files), total / (1024 * 1024)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def validate_prerequisites() -> None:
    heading("Validating prerequisites")

    if not VENV_PYTHON.exists():
        fail(
            f"Build venv not found at {BUILD_VENV}\n"
            "Create it with:\n"
            "  py -3.11 -m venv C:\\KingdomBuild\\venv\n"
            "  C:\\KingdomBuild\\venv\\Scripts\\pip install -r requirements.txt"
        )
    print(f"  venv Python : {VENV_PYTHON}")

    # Check PyInstaller is importable inside the venv
    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "PyInstaller", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(
            "PyInstaller is not installed in the build venv.\n"
            "Install it with:\n"
            f"  {BUILD_VENV / 'Scripts' / 'pip'} install pyinstaller"
        )
    print(f"  PyInstaller : v{result.stdout.strip()}")

    if not SPEC_FILE.exists():
        fail(f"Spec file not found: {SPEC_FILE}")
    print(f"  Spec file   : {SPEC_FILE}")


def clean() -> None:
    heading("Cleaning previous build artifacts")
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            print(f"  Deleting {d} ...")
            shutil.rmtree(d)
        else:
            print(f"  {d} — already clean")


def build() -> None:
    heading("Running PyInstaller")
    cmd = [
        str(VENV_PYTHON),
        "-m", "PyInstaller",
        str(SPEC_FILE),
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--noconfirm",
    ]
    print(f"  Command: {' '.join(cmd)}\n")

    t0 = time.perf_counter()
    result = subprocess.run(cmd)
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        fail(f"PyInstaller exited with code {result.returncode}")

    print(f"\n  PyInstaller finished in {elapsed:.1f}s")


def verify() -> None:
    heading("Verifying build output")

    if not EXE_PATH.exists():
        fail(f"Expected exe not found: {EXE_PATH}")

    dist_folder = DIST_DIR / EXE_NAME
    count, size_mb = folder_stats(dist_folder)

    print(f"  Exe path   : {EXE_PATH}")
    print(f"  Folder     : {dist_folder}")
    print(f"  Files      : {count}")
    print(f"  Total size : {size_mb:.1f} MB")


def run_test() -> None:
    heading("Running smoke test")

    if not TEST_SCRIPT.exists():
        fail(
            f"Test script not found: {TEST_SCRIPT}\n"
            "Create tools/test_frozen_exe.py first."
        )

    if not EXE_PATH.exists():
        fail(f"Exe not found for testing: {EXE_PATH}")

    cmd = [sys.executable, str(TEST_SCRIPT), str(EXE_PATH)]
    print(f"  Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        fail(f"Smoke test failed (exit code {result.returncode})")

    print("\n  Smoke test passed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Kingdom Sim into a standalone .exe"
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Delete build/dist folders before building",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run smoke test after build",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="Skip the PyInstaller step (use existing build)",
    )
    args = parser.parse_args()

    print(f"Kingdom Sim — Build Pipeline")
    print(f"Repo root: {REPO_ROOT}")

    if not args.skip_build:
        validate_prerequisites()

        if args.clean:
            clean()

        build()
        verify()
    else:
        print("\n  --skip-build: skipping PyInstaller step")
        if EXE_PATH.exists():
            dist_folder = DIST_DIR / EXE_NAME
            count, size_mb = folder_stats(dist_folder)
            print(f"  Existing exe : {EXE_PATH}")
            print(f"  Files        : {count}")
            print(f"  Total size   : {size_mb:.1f} MB")
        else:
            print(f"  Warning: exe not found at {EXE_PATH}")

    if args.test:
        run_test()

    heading("Done")


if __name__ == "__main__":
    main()
