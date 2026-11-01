"""DESIGN-17 stage 6: the repo's own conformance gate.

The committed program ledger (docs/pattern/program-ledger)
and its committed generated layers must satisfy the gate
in the test suite as well as in CI's dedicated job: the
matrix and map on disk are byte-exactly the ones the
ledger generates, and the ledger itself is well-formed.
"""

import os

from epistemic_ledger.pattern import (
    check_pattern,
    events_from_log,
    validate_ledger,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATTERN_DIR = os.path.join(_HERE, "..", "docs", "pattern")
_LEDGER_DIR = os.path.join(_PATTERN_DIR, "program-ledger")


def _read(name):
    with open(os.path.join(_PATTERN_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_committed_artifacts_pass_the_gate():
    events = events_from_log(_LEDGER_DIR)
    result = check_pattern(events, _read("matrix.json"), _read("map.json"))
    assert result == {"ok": True, "problems": []}
    # Amendment 3: the committed ledger validates against
    # the pinned schema, with full source/falsifier
    # coverage (the program entered its claims fielded).
    report = validate_ledger(events)
    assert report["ok"] is True
    cov = report["coverage"]
    assert cov["with_source"] == cov["claims"]
    assert cov["with_falsifier"] == cov["claims"]
    # The ledger is the program's own record: it must be
    # non-trivial and carry the design series.
    assert len(events) >= 40
    sources = " ".join((e.get("payload") or {}).get("source") or "" for e in events)
    for series in ("DESIGN-13", "DESIGN-15", "DESIGN-16", "DESIGN-17"):
        assert series in sources
