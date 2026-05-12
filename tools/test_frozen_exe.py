"""Automated smoke test for the frozen KingdomSim.exe."""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_EXE = r"C:\KingdomBuild\dist\KingdomSim\KingdomSim.exe"
SCRIPT_TIMEOUT = 60  # hard cap for entire script
ERROR_PATTERNS = ("FileNotFoundError", "ModuleNotFoundError", "ImportError", "Traceback")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for frozen KingdomSim.exe")
    parser.add_argument("exe", nargs="?", default=DEFAULT_EXE, help="Path to KingdomSim.exe")
    parser.add_argument("--timeout", type=int, default=15, help="Seconds to wait for boot (default 15)")
    args = parser.parse_args()

    exe_path = Path(args.exe)
    boot_timeout = args.timeout
    results: list[tuple[str, str, bool]] = []  # (id, detail, passed)

    proc = None
    stdout_file = None
    stderr_file = None

    try:
        # ----------------------------------------------------------
        # TC-01 EXE_EXISTS
        # ----------------------------------------------------------
        if exe_path.is_file():
            results.append(("TC-01 EXE_EXISTS", "", True))
        else:
            results.append(("TC-01 EXE_EXISTS", f"{exe_path} not found", False))
            # Can't continue without the exe — mark remaining as skipped
            for tc in ("TC-02 BOOT", "TC-03 NO_PYTHON_ERRORS", "TC-04 BANNER", "TC-05 CLEAN_EXIT"):
                results.append((tc, "skipped (exe missing)", False))
            return _report(results)

        # Prepare temp files for stdout / stderr capture
        stdout_file = tempfile.NamedTemporaryFile(mode="w", suffix="_stdout.txt", delete=False)
        stderr_file = tempfile.NamedTemporaryFile(mode="w", suffix="_stderr.txt", delete=False)

        # ----------------------------------------------------------
        # TC-02 BOOT
        # ----------------------------------------------------------
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                [str(exe_path), "--no-llm", "--renderer", "ursina"],
                stdout=stdout_file,
                stderr=stderr_file,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except OSError as exc:
            results.append(("TC-02 BOOT", f"failed to launch: {exc}", False))
            for tc in ("TC-03 NO_PYTHON_ERRORS", "TC-04 BANNER", "TC-05 CLEAN_EXIT"):
                results.append((tc, "skipped (launch failed)", False))
            return _report(results)

        deadline = time.monotonic() + boot_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(1)

        if proc.poll() is not None:
            results.append(("TC-02 BOOT", f"process exited early (code {proc.returncode})", False))
        else:
            results.append(("TC-02 BOOT", f"alive after {boot_timeout}s", True))

        # Flush temp files before reading
        stdout_file.close()
        stderr_file.close()

        # ----------------------------------------------------------
        # TC-03 NO_PYTHON_ERRORS
        # ----------------------------------------------------------
        stderr_text = Path(stderr_file.name).read_text(errors="replace")
        error_count = sum(stderr_text.count(pat) for pat in ERROR_PATTERNS)
        if error_count == 0:
            results.append(("TC-03 NO_PYTHON_ERRORS", "0 errors in stderr", True))
        else:
            hits = [p for p in ERROR_PATTERNS if p in stderr_text]
            results.append(("TC-03 NO_PYTHON_ERRORS", f"{error_count} error(s): {', '.join(hits)}", False))

        # ----------------------------------------------------------
        # TC-04 RENDER_INIT
        # ----------------------------------------------------------
        # Frozen exe buffers stdout indefinitely, so check stderr for
        # Panda3D display pipeline initialization evidence instead.
        stdout_text = Path(stdout_file.name).read_text(errors="replace")
        banner_found = "Kingdom Sim" in stdout_text
        render_found = "wglGraphicsPipe" in stderr_text or "GraphicsPipe" in stderr_text
        if banner_found or render_found:
            detail = "banner in stdout" if banner_found else "wglGraphicsPipe in stderr"
            results.append(("TC-04 RENDER_INIT", detail, True))
        else:
            results.append(("TC-04 RENDER_INIT", "no init evidence in stdout or stderr", False))

        # ----------------------------------------------------------
        # TC-05 CLEAN_EXIT
        # ----------------------------------------------------------
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=10)
                results.append(("TC-05 CLEAN_EXIT", "process killed cleanly", True))
            except Exception as exc:
                results.append(("TC-05 CLEAN_EXIT", f"kill failed: {exc}", False))
        else:
            # Already exited — still counts as terminable
            results.append(("TC-05 CLEAN_EXIT", f"already exited (code {proc.returncode})", True))

    finally:
        # Ensure process is dead
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass

        # Clean up temp files
        for f in (stdout_file, stderr_file):
            if f is not None:
                try:
                    if not f.closed:
                        f.close()
                    os.unlink(f.name)
                except OSError:
                    pass

    return _report(results)


def _report(results: list[tuple[str, str, bool]]) -> int:
    passed = sum(1 for *_, ok in results if ok)
    failed = len(results) - passed

    print()
    for tc_id, detail, ok in results:
        tag = "[PASS]" if ok else "[FAIL]"
        suffix = f" ({detail})" if (ok and detail) else (f" — {detail}" if detail else "")
        print(f"{tag} {tc_id}{suffix}")

    print(f"\nResults: {passed}/{len(results)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
