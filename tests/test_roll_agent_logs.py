"""Sprint-ordering matrix for tools/roll_agent_logs.py.

Owner: Agent 12 (ToolsDevEx_Lead)

Background — the real incident (2026-05-29)
-------------------------------------------
``_ordered_sprint_keys`` orders a rolling log's sprints chronologically so that
"keep last N" keeps the NEWEST sprints. The original implementation sorted undated
sprints (no ``sprint_meta.created_utc``) as epoch (1970), i.e. OLDEST. In a log
that MIXES dated + undated sprints, recent appended-undated sprints then sorted as
1970 and were wrongly archived.

Concretely, agent_01 had dated wk58..wk63 followed by undated wk64/wk65/wk66; the
epoch rule archived the recent wk64+wk65 and kept the ancient wk58+wk59.

The fix: undated sprints inherit the timestamp of their most-recent DATED
predecessor (walking the dict in insertion order). Trailing undated sprints thus
stay newest; leading undated sprints (no dated predecessor) inherit epoch and sort
oldest. All-undated logs (worker logs) keep insertion order via an early return.

Robustness note: undated sprints inherit the RUNNING MAX of the dated timestamps
seen so far (walking insertion order), NOT merely the immediate dated predecessor.
So a trailing undated sprint stays "newest" even if the DATED sprints were
themselves appended out of chronological order (e.g. {datedMar(idx0),
datedJan(idx1), undated(idx2)} -> the undated inherits Mar and sorts LAST). This
matches the tool docstring's "most recent dated seen so far" and is covered by
test_out_of_order_dated_then_trailing_undated_stays_newest.

These tests call the REAL tool API:
``from tools.roll_agent_logs import _ordered_sprint_keys, _roll_one`` (and the
module's ``LOG_DIR`` / ``ARCHIVE_DIR`` globals for the end-to-end case).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Mirror tests/test_wk65_tooling.py: import the tool package directly. Tests run
# from the repo root, but make the import robust if a runner changes cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import tools.roll_agent_logs as ral
from tools.roll_agent_logs import _ordered_sprint_keys, _roll_one


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _dated(created_utc: str) -> dict:
    """A sprint block WITH a created_utc timestamp."""
    return {"sprint_meta": {"created_utc": created_utc}, "rounds": {}}


def _undated() -> dict:
    """A sprint block WITHOUT a created_utc timestamp."""
    return {"rounds": {}}


# --------------------------------------------------------------------------- #
# (a) ALL-DATED, inserted out of chronological order -> result is chronological
# --------------------------------------------------------------------------- #
def test_all_dated_out_of_order_sorts_chronologically() -> None:
    sprints = {
        "wkC": _dated("2026-03-01T00:00:00Z"),  # newest, inserted first
        "wkA": _dated("2026-01-01T00:00:00Z"),  # oldest, inserted second
        "wkB": _dated("2026-02-01T00:00:00Z"),  # middle, inserted last
    }
    assert _ordered_sprint_keys(sprints) == ["wkA", "wkB", "wkC"]


# --------------------------------------------------------------------------- #
# (b) ALL-UNDATED -> result == insertion order exactly (worker-log path)
# --------------------------------------------------------------------------- #
def test_all_undated_preserves_insertion_order() -> None:
    sprints = {
        "first": _undated(),
        "second": _undated(),
        "third": _undated(),
        "fourth": _undated(),
    }
    keys = list(sprints.keys())
    assert _ordered_sprint_keys(sprints) == keys


# --------------------------------------------------------------------------- #
# (c) THE BUG CASE: dated wk58..wk63 + trailing undated wk64/65/66
#     keep=7 must archive exactly [wk58, wk59] and keep [wk60..wk66].
#     This FAILS against the old epoch-oldest logic (which archived wk64/wk65).
# --------------------------------------------------------------------------- #
def _bug_case_sprints() -> dict:
    return {
        "wk58": _dated("2026-04-01T00:00:00Z"),
        "wk59": _dated("2026-04-08T00:00:00Z"),
        "wk60": _dated("2026-04-15T00:00:00Z"),
        "wk61": _dated("2026-04-22T00:00:00Z"),
        "wk62": _dated("2026-04-29T00:00:00Z"),
        "wk63": _dated("2026-05-06T00:00:00Z"),
        "wk64": _undated(),
        "wk65": _undated(),
        "wk66": _undated(),
    }


def test_bug_case_trailing_undated_sort_last() -> None:
    ordered = _ordered_sprint_keys(_bug_case_sprints())
    assert ordered == [
        "wk58",
        "wk59",
        "wk60",
        "wk61",
        "wk62",
        "wk63",
        "wk64",
        "wk65",
        "wk66",
    ]


def test_bug_case_keep7_archives_only_two_oldest() -> None:
    sprints = _bug_case_sprints()
    ordered = _ordered_sprint_keys(sprints)
    keep = 7
    to_archive = ordered[: len(ordered) - keep]
    to_keep = ordered[len(ordered) - keep :]
    # Recent undated wk64/65/66 must be KEPT, ancient wk58/wk59 ARCHIVED.
    assert to_archive == ["wk58", "wk59"]
    assert to_keep == ["wk60", "wk61", "wk62", "wk63", "wk64", "wk65", "wk66"]


# --------------------------------------------------------------------------- #
# (d) INTERSPERSED: [datedA, undated, datedB] (datedA < datedB)
#     -> undated sorts BETWEEN them.
# --------------------------------------------------------------------------- #
def test_interspersed_undated_sorts_between_dated_neighbors() -> None:
    sprints = {
        "datedA": _dated("2026-01-01T00:00:00Z"),
        "undated": _undated(),
        "datedB": _dated("2026-02-01T00:00:00Z"),
    }
    # undated inherits datedA's time, then secondary insertion index keeps it
    # after datedA but before the later datedB.
    assert _ordered_sprint_keys(sprints) == ["datedA", "undated", "datedB"]


# --------------------------------------------------------------------------- #
# (e) LEADING-UNDATED: [undated, datedA, datedB]
#     -> leading undated inherits epoch and sorts OLDEST (archived first).
# --------------------------------------------------------------------------- #
def test_leading_undated_sorts_oldest() -> None:
    sprints = {
        "undated": _undated(),
        "datedA": _dated("2026-01-01T00:00:00Z"),
        "datedB": _dated("2026-02-01T00:00:00Z"),
    }
    assert _ordered_sprint_keys(sprints) == ["undated", "datedA", "datedB"]


def test_leading_undated_is_archived_first_with_keep2() -> None:
    sprints = {
        "undated": _undated(),
        "datedA": _dated("2026-01-01T00:00:00Z"),
        "datedB": _dated("2026-02-01T00:00:00Z"),
    }
    ordered = _ordered_sprint_keys(sprints)
    keep = 2
    to_archive = ordered[: len(ordered) - keep]
    assert to_archive == ["undated"]


# --------------------------------------------------------------------------- #
# (f) OUT-OF-ORDER DATED + trailing undated: running-max keeps the undated newest.
#     FAILS under immediate-predecessor inheritance (undated would sort middle).
# --------------------------------------------------------------------------- #
def test_out_of_order_dated_then_trailing_undated_stays_newest() -> None:
    sprints = {
        "late": _dated("2026-03-01T00:00:00Z"),   # newest, inserted first
        "early": _dated("2026-01-01T00:00:00Z"),  # oldest, inserted second
        "undated": _undated(),                     # inserted last -> must stay newest
    }
    # Dated sort chronologically (early, late). The undated inherits the running-max
    # (late's Mar timestamp); its insertion index keeps it after 'late' -> sorts last.
    assert _ordered_sprint_keys(sprints) == ["early", "late", "undated"]


# --------------------------------------------------------------------------- #
# edge: empty
# --------------------------------------------------------------------------- #
def test_empty_sprints_returns_empty() -> None:
    assert _ordered_sprint_keys({}) == []


# --------------------------------------------------------------------------- #
# end-to-end: _roll_one over a temp LOG_DIR/ARCHIVE_DIR with the bug-case log.
# --------------------------------------------------------------------------- #
def test_roll_one_end_to_end_archives_two_oldest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "agent_logs"
    archive_dir = log_dir / "archive"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Point the module's globals at the temp dirs (restored automatically by
    # monkeypatch at test teardown).
    monkeypatch.setattr(ral, "LOG_DIR", log_dir)
    monkeypatch.setattr(ral, "ARCHIVE_DIR", archive_dir)

    log_obj = {
        "schema_version": "2.0",
        "agent": {"id": "agent_99", "name": "Test"},
        "sprints": _bug_case_sprints(),
    }
    rolling_path = log_dir / "agent_99_Test.json"
    rolling_path.write_text(
        json.dumps(log_obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # dry_run=True: must compute the archive set without touching disk.
    result = _roll_one(rolling_path, keep=7, dry_run=True, ensure_archive=False)

    assert result["status"] == "would_roll", result
    assert result["sprints_archived"] == ["wk58", "wk59"]
    assert result["sprints_kept"] == 7
    assert result["sprints_total"] == 9
    # dry-run must not have created the archive.
    assert not (archive_dir / "agent_99_Test.archive.json").exists()


def test_roll_one_end_to_end_real_write_moves_two_oldest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_dir = tmp_path / "agent_logs"
    archive_dir = log_dir / "archive"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ral, "LOG_DIR", log_dir)
    monkeypatch.setattr(ral, "ARCHIVE_DIR", archive_dir)

    log_obj = {
        "schema_version": "2.0",
        "agent": {"id": "agent_99", "name": "Test"},
        "sprints": _bug_case_sprints(),
    }
    rolling_path = log_dir / "agent_99_Test.json"
    rolling_path.write_text(
        json.dumps(log_obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = _roll_one(rolling_path, keep=7, dry_run=False, ensure_archive=False)
    assert result["status"] == "rolled", result
    assert result["sprints_archived"] == ["wk58", "wk59"]

    # Rolling log now keeps wk60..wk66; archive holds exactly wk58 + wk59.
    rolling_after = json.loads(rolling_path.read_text(encoding="utf-8"))
    assert list(rolling_after["sprints"].keys()) == [
        "wk60",
        "wk61",
        "wk62",
        "wk63",
        "wk64",
        "wk65",
        "wk66",
    ]
    archive_after = json.loads(
        (archive_dir / "agent_99_Test.archive.json").read_text(encoding="utf-8")
    )
    assert list(archive_after["sprints"].keys()) == ["wk58", "wk59"]
