"""T-PR sample of the kill-point sweep (DESIGN-16, claim S1).

Three kills per engine at small scale — the full sweeps (500 kills)
run at the nightly tier. Expectations are per engine and honest:

- Rust chained store: every trial must be ``clean`` — torn-tail repair
  at open is its specified behavior (DESIGN-13).
- Python engine: no trial may ever be ``silent_wrong``. ``clean`` and
  ``loud_recoverable`` are both acceptable at this tier; the strict
  clean-only property for the Python engine is tracked in DESIGN-16
  as the S1c follow-up (crash recovery at open).

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


def test_killpoint_python_never_silently_wrong():
    rng = random.Random(20261030)
    for _ in range(TRIALS):
        result = run_trial("python", rng, COUNT)
        assert result["outcome"] in ("clean", "loud_recoverable"), result
