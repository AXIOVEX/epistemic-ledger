"""DESIGN-17 stage 5: the verification gate (P5).

The gate regenerates the matrix and the map from the
ledger's records and fails on any divergence: a one-byte
change to either artifact, a missing claim row, a stale
artifact after the ledger moved, and (through the CLI) a
missing or hand-edited file.
"""

import json
import os

from epistemic_ledger.cli import main as cli_main
from epistemic_ledger.ledger import Ledger
from epistemic_ledger.pattern import (
    build_map,
    build_matrix,
    check_pattern,
    map_json,
    matrix_json,
)

T1 = "2026-06-01T00:00:00+00:00"


def _store(tmp_path):
    path = str(tmp_path / "store")
    led = Ledger(path)
    a = led.assert_claim("claim a", 0.8, source="s", t=T1)
    led.assert_claim("claim b", 0.6, t=T1)
    led.record_decision("decide", [a], t=T1)
    events = led._events()
    led.close()
    return path, events


def test_gate_passes_on_regenerated_artifacts(tmp_path):
    _, events = _store(tmp_path)
    result = check_pattern(
        events, matrix_json(build_matrix(events)), map_json(build_map(events))
    )
    assert result == {"ok": True, "problems": []}


def test_gate_fails_on_one_byte_change(tmp_path):
    _, events = _store(tmp_path)
    good_matrix = matrix_json(build_matrix(events))
    tampered = good_matrix.replace("claim a", "claim A", 1)
    assert tampered != good_matrix
    result = check_pattern(events, tampered, map_json(build_map(events)))
    assert result["ok"] is False
    assert any("matrix" in p for p in result["problems"])
    good_map = map_json(build_map(events))
    tampered_map = good_map.replace('"events": 4', '"events": 5', 1)
    assert tampered_map != good_map
    result = check_pattern(events, good_matrix, tampered_map)
    assert result["ok"] is False
    assert any("map" in p for p in result["problems"])


def test_gate_fails_on_missing_row_and_stale_artifacts(tmp_path):
    path, events = _store(tmp_path)
    matrix = build_matrix(events)
    matrix["claims"] = matrix["claims"][:-1]  # a dropped row
    result = check_pattern(events, matrix_json(matrix), map_json(build_map(events)))
    assert result["ok"] is False
    # Stale: the ledger moves, the artifacts do not.
    stale_matrix = matrix_json(build_matrix(events))
    stale_map = map_json(build_map(events))
    led = Ledger(path)
    led.assert_claim("claim c", 0.5, t=T1)
    fresh_events = led._events()
    led.close()
    result = check_pattern(fresh_events, stale_matrix, stale_map)
    assert result["ok"] is False
    assert len(result["problems"]) == 2


def test_cli_export_then_check_then_tamper(tmp_path):
    path, _ = _store(tmp_path)
    out = str(tmp_path / "pattern")
    assert cli_main(["pattern-export", path, out]) == 0
    for name in ("matrix.json", "matrix.md", "map.json", "map.md"):
        assert os.path.exists(os.path.join(out, name))
    assert cli_main(["pattern-check", path, out]) == 0
    # A hand-edit to the Markdown surface is drift too.
    md_path = os.path.join(out, "map.md")
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text.replace("Claims: 2", "Claims: 3", 1))
    assert cli_main(["pattern-check", path, out]) == 1
    # And a missing artifact is a failing gate, not a pass.
    os.remove(os.path.join(out, "matrix.json"))
    assert cli_main(["pattern-check", path, out]) == 1
    # The exported JSON parses and carries the format tags.
    with open(os.path.join(out, "map.json"), encoding="utf-8") as f:
        assert json.load(f)["format"] == "epistemic-ledger-map/1"
