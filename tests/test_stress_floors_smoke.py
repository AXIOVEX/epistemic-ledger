"""T-PR smoke tests for the resource floors (DESIGN-16 S5).

The memory leg runs at small scale in the ordinary suite. The
disk leg needs a loopback mount (passwordless sudo); where that
is unavailable it must report ``not_run`` with a reason — the
shape is pinned here, the genuine ENOSPC run happens in the
release tier. The chained-store cases skip when the compiled
core is absent (the plain Test jobs do not build it).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.stress.floors import run_disk_floor, run_memory_floor  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="resource floors are POSIX (DESIGN-16 S5)"
)


def test_memory_floor_smoke_passes():
    pytest.importorskip("epistemic_ledger._core")
    leg = run_memory_floor(records=2_000, ceiling_mb=256)
    assert leg["status"] == "pass", leg
    assert leg["verified"] == 2_000


def test_disk_floor_reports_its_shape():
    pytest.importorskip("epistemic_ledger._core")
    leg = run_disk_floor(image_mb=96)
    assert leg["status"] in {"pass", "not_run"}
    if leg["status"] == "not_run":
        assert leg["detail"]
    else:
        assert leg["loud_failure"]
        assert leg["verified_after"] == leg["successful_appends"]
