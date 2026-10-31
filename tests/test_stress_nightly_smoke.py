"""T-PR smoke tests for the nightly-tier runners (DESIGN-16 S3).

Each runner is exercised at tiny bounds and must produce its
report with the stability verdicts green; the full bounds (the
2-hour soak, the exhaustive bit-rot program, the 1M-record scale
run) execute only in the nightly workflow. The rate and scale
numbers themselves are the nightly's claims, not the smoke's —
what is pinned here is that the runners work and their reports
are shaped as the nightly's report job expects.

The chained-store cases skip when the compiled core is absent
(the plain Test jobs do not build it).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.stress.readers import run_readers  # noqa: E402
from tools.stress.scale import run_scale  # noqa: E402
from tools.stress.soak import run_append_soak, run_soak  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="stress workers are POSIX (DESIGN-16)"
)


def test_soak_smoke_is_stable():
    report = run_soak(5.0, seed=7)
    assert report["errors"] == []
    assert report["final_verify_ok"]
    assert report["retention_ok"]


def test_append_soak_smoke_verifies():
    pytest.importorskip("epistemic_ledger._core")
    report = run_append_soak(5.0)
    assert report["append_verify_ok"]
    assert report["appends"] > 0
    # The leg gates on endurance + integrity; the rate is
    # reported, not gated (the bench gates the budget).
    assert report["passed"] == report["append_verify_ok"]
    assert report["append_rps"] > 0


def test_readers_sqlite_smoke_is_clean():
    report = run_readers("sqlite", 4.0, 2)
    assert report["passed"], report
    assert report["queries"] > 0


def test_readers_rust_smoke_is_clean():
    pytest.importorskip("epistemic_ledger._core")
    report = run_readers("rust", 4.0, 2)
    assert report["passed"], report
    assert report["queries"] > 0


def test_scale_smoke_reports_the_point():
    pytest.importorskip("epistemic_ledger._core")
    report = run_scale(2_000)
    assert report["records"] == 2_000
    assert report["open_pass"] and report["verify_pass"]
    # Below 10k records the impact leg is not measured.
    assert report["impact_ms"] is None
