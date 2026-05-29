"""WK65 Round 0 (Wave 0) — tooling-correctness pins.

Sprint: wk65_round0_deslop_foundation
Round:  wk65_w0_tooling_baseline
Owner:  Agent 12 (ToolsDevEx_Lead)

Purpose
-------
Pin the Wave-0 fixes to the QA tools that gate every other agent's verification:

``tools/determinism_guard.py``
  (a) ``--paths`` pointed outside ``PROJECT_ROOT`` must not crash
      (``Path.relative_to`` raised ``ValueError``); reporting now falls back to
      the raw path string via ``_display_path``.
  (b) Parse errors are reported separately and do NOT produce the FAIL/exit-1 of
      a real determinism violation (real violations still exit 1).
  (c) The AST matcher is alias-aware: ``import time as t``,
      ``from random import random``, etc. are normalized before matching, while
      ``rng.random()`` on a passed-in object is still NOT flagged.

``tools/observe_sync.py``
  The dual-clock bug is covered indirectly by ``qa_smoke`` /
  ``observe_sync --qa`` gates; here we assert the single-clock source is wired in
  (the module reads ``game.sim.timebase.now_ms`` and no longer computes the
  multiplier-blind ``int((t * 1000) / 60)`` clock).

These call the REAL ``determinism_guard`` API: ``scan_file(Path) -> list[dict]``
and ``main()`` (argv-driven, returns an exit code).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import tools.determinism_guard as dg

PROJECT_ROOT_FOR_TOOLS = Path(__file__).resolve().parents[1] / "tools"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _write(tmp_path: Path, name: str, src: str) -> Path:
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return p


def _kinds(findings: list[dict]) -> list[str]:
    return [f["kind"] for f in findings]


# --------------------------------------------------------------------------- #
# (c) alias-aware matching — POSITIVE cases (must be flagged)
# --------------------------------------------------------------------------- #
def test_plain_random_random_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "a.py", "import random\n\nx = random.random()\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["global_rng"], findings


def test_aliased_random_module_is_flagged(tmp_path: Path) -> None:
    # `import random as r; r.random()` — the alias root must be normalized.
    f = _write(tmp_path, "b.py", "import random as r\n\nx = r.random()\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["global_rng"], findings


def test_from_random_import_random_is_flagged(tmp_path: Path) -> None:
    # `from random import random; random()` — bare call bound from the module.
    f = _write(tmp_path, "c.py", "from random import random\n\nx = random()\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["global_rng"], findings


def test_from_random_import_alias_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "c2.py", "from random import randint as ri\n\nx = ri(0, 9)\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["global_rng"], findings


def test_time_time_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "d.py", "import time\n\nt = time.time()\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["wall_clock_time"], findings


def test_aliased_time_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "e.py", "import time as t\n\nnow = t.time()\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["wall_clock_time"], findings


def test_from_time_import_time_alias_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path, "e2.py", "from time import time as now\n\nv = now()\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["wall_clock_time"], findings


def test_aliased_datetime_now_is_flagged(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "f.py",
        "import datetime as dt\n\nx = dt.datetime.now()\n",
    )
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["wall_clock_time"], findings


def test_from_datetime_import_datetime_is_flagged(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "f2.py",
        "from datetime import datetime\n\nx = datetime.now()\n",
    )
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["wall_clock_time"], findings


# --------------------------------------------------------------------------- #
# (c) alias-aware matching — NEGATIVE cases (must NOT be flagged)
# --------------------------------------------------------------------------- #
def test_passed_in_rng_object_is_not_flagged(tmp_path: Path) -> None:
    # `rng.random()` where `rng` is a passed-in object (seeded RNG) — the whole
    # point of the seeded-RNG pattern; must stay clean.
    f = _write(
        tmp_path,
        "g.py",
        "def step(rng):\n    return rng.random()\n",
    )
    findings = dg.scan_file(f)
    assert findings == [], findings


def test_unrelated_alias_named_random_attr_is_not_flagged(tmp_path: Path) -> None:
    # A method named `random` on an unrelated object must not be flagged.
    f = _write(
        tmp_path,
        "h.py",
        "class Thing:\n    def random(self):\n        return 4\n\nThing().random()\n",
    )
    findings = dg.scan_file(f)
    assert findings == [], findings


def test_unrelated_module_alias_is_not_flagged(tmp_path: Path) -> None:
    # Aliasing an unrelated module must not seed false positives.
    f = _write(
        tmp_path,
        "i.py",
        "import os as t\n\nx = t.getcwd()\n",
    )
    findings = dg.scan_file(f)
    assert findings == [], findings


# --------------------------------------------------------------------------- #
# (b) parse error is separated from real violations
# --------------------------------------------------------------------------- #
def test_parse_error_is_reported_as_parse_error_not_violation(tmp_path: Path) -> None:
    f = _write(tmp_path, "broken.py", "def oops(:\n    pass\n")
    findings = dg.scan_file(f)
    assert _kinds(findings) == ["parse_error"], findings


def test_parse_error_alone_does_not_fail_main(tmp_path: Path, capsys, monkeypatch) -> None:
    # A directory whose only problem is an unparseable file must NOT exit 1.
    _write(tmp_path, "broken.py", "def oops(:\n    pass\n")
    monkeypatch.setattr(sys, "argv", ["determinism_guard.py", "--paths", str(tmp_path)])
    rc = dg.main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "PASS" in out
    assert "parse_error" in out  # surfaced under its own header, not as a violation


def test_real_violation_still_exits_one(tmp_path: Path, capsys, monkeypatch) -> None:
    _write(tmp_path, "bad.py", "import time\n\nt = time.time()\n")
    monkeypatch.setattr(sys, "argv", ["determinism_guard.py", "--paths", str(tmp_path)])
    rc = dg.main()
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "FAIL" in out


def test_parse_error_plus_violation_exits_one_but_reports_both(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    _write(tmp_path, "broken.py", "def oops(:\n    pass\n")
    _write(tmp_path, "bad.py", "import time\n\nt = time.time()\n")
    monkeypatch.setattr(sys, "argv", ["determinism_guard.py", "--paths", str(tmp_path)])
    rc = dg.main()
    out = capsys.readouterr().out
    assert rc == 1, out  # the real violation drives exit-1
    assert "FAIL" in out
    assert "parse_error" in out  # the parse error is still surfaced, separately


# --------------------------------------------------------------------------- #
# (a) --paths outside the repo must not raise
# --------------------------------------------------------------------------- #
def test_display_path_outside_repo_does_not_raise(tmp_path: Path) -> None:
    # tmp_path is outside PROJECT_ROOT; the old `relative_to(PROJECT_ROOT)` raised.
    outside = tmp_path / "somewhere.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    assert dg._display_path(outside) == str(outside)


def test_paths_outside_repo_clean_file_does_not_raise(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    # A benign file outside the repo: must scan cleanly and not crash.
    f = _write(tmp_path, "clean.py", "def add(a, b):\n    return a + b\n")
    monkeypatch.setattr(sys, "argv", ["determinism_guard.py", "--paths", str(f)])
    rc = dg.main()  # must not raise ValueError
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "PASS" in out


def test_paths_outside_repo_violation_reports_absolute_path(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    # A violation in an out-of-repo file must be reported (with a usable path)
    # and exit 1 — not crash.
    f = _write(tmp_path, "ext_violation.py", "import random\n\nx = random.random()\n")
    monkeypatch.setattr(sys, "argv", ["determinism_guard.py", "--paths", str(f)])
    rc = dg.main()
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "global_rng" in out
    assert str(f) in out  # absolute fallback path is present


# --------------------------------------------------------------------------- #
# --json output splits violations from parse errors
# --------------------------------------------------------------------------- #
def test_json_output_splits_violations_and_parse_errors(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    _write(tmp_path, "broken.py", "def oops(:\n    pass\n")
    _write(tmp_path, "bad.py", "import time\n\nt = time.time()\n")
    monkeypatch.setattr(
        sys, "argv", ["determinism_guard.py", "--json", "--paths", str(tmp_path)]
    )
    rc = dg.main()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 1
    assert "violations" in payload and "parse_errors" in payload
    assert len(payload["violations"]) == 1
    assert payload["violations"][0]["kind"] == "wall_clock_time"
    assert len(payload["parse_errors"]) == 1
    assert payload["parse_errors"][0]["kind"] == "parse_error"


# --------------------------------------------------------------------------- #
# observe_sync single-clock wiring (dual-clock fix)
# --------------------------------------------------------------------------- #
def test_observe_sync_reads_authoritative_clock_not_dual_clock() -> None:
    """The multiplier-blind `int((t * 1000) / 60)` clock is gone, replaced by a
    read of the single authoritative `game.sim.timebase.now_ms`."""
    src = (PROJECT_ROOT_FOR_TOOLS / "observe_sync.py").read_text(encoding="utf-8")
    # Strip comment bodies before checking: a comment may legitimately mention the
    # old formula while explaining the fix; what matters is the live assignment.
    code_lines = [ln.split("#", 1)[0] for ln in src.splitlines()]
    code = "\n".join(code_lines)
    assert "int((t * 1000) / 60)" not in code, "dual-clock assignment still present in code"
    assert "now_ms_val = int(now_ms())" in code
    # `now_ms` is imported from the single-owner timebase module.
    assert "from game.sim.timebase import" in src and "now_ms" in src
