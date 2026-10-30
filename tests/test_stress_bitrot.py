"""T-PR sample of the bit-rot sweep (DESIGN-16, claim S2).

Sixty flips against a 200-record chained store: every interior
corruption must be detected, and tail corruptions must be detected or
repaired by the documented tail truncation — never silently accepted.
The exhaustive per-byte sweep runs at the nightly tier.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.stress.bitrot import run_sweep  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="bit-rot sweep semantics are POSIX (DESIGN-16 S2)"
)


def test_bitrot_sample_detects_everything():
    pytest.importorskip("epistemic_ledger._core")
    report = run_sweep(flips=60, records=200, seed=20261030)
    assert report["outcomes"]["missed"] == 0, report["missed"]
    assert report["outcomes"]["detected"] > 0
