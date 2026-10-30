"""T-PR sample of the kill-point sweep (DESIGN-16, claim S1).

Three kills per engine at small scale — the full sweeps (500 kills)
run at the nightly tier. Both engines must come back ``clean``:
opens, verifies, and holds exactly a prefix of the attempted appends
including every acknowledged one. For the Rust store that is its
specified torn-tail repair (DESIGN-13); for the Python engine it is
crash recovery at open (DESIGN-16 S1c: torn tail truncated, drifted
projection rebuilt from the log, anything else a loud refusal — and
a refusal classifies as ``loud_recoverable`` or ``error`` here,
never ``clean``).

Windows is skipped: its kill and lock semantics differ by design
(DESIGN-12), and the sweep's claims are stated for POSIX.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.stress.killpoint import run_trial  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="kill-point semantics are POSIX (DESIGN-16 S1)"
)

TRIALS = 3
COUNT = 3_000


def test_killpoint_rust_trials_are_clean():
    pytest.importorskip("epistemic_ledger._core")
    rng = random.Random(20261030)
    for _ in range(TRIALS):
        result = run_trial("rust", rng, COUNT)
        assert result["outcome"] == "clean", result


def test_killpoint_python_trials_are_clean():
    rng = random.Random(20261030)
    for _ in range(TRIALS):
        result = run_trial("python", rng, COUNT)
        assert result["outcome"] == "clean", result
