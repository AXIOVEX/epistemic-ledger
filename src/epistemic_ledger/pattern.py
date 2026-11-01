"""The winning-combination pattern surface (DESIGN-17).

The pattern, as this package implements its ledger half:
an epistemic ledger whose every material claim carries a
statement, source, date, status, confidence, falsifier,
and a does-not-establish line; corrections as append-only
reclassifications; and every downstream layer GENERATED
from the ledger by script — never hand-made.

This module holds the generators and (stage 5) the gate.
Everything here is a pure function of the ledger's records:
no wall clock, no project-specific content, so the future
shared component can extract this module unchanged.

Stage 3: the matrix. `build_matrix` folds the ledger's
event list into one canonical dict — a row per claim,
live and terminal, in assertion order — and the renderers
derive the JSON and Markdown forms from that one dict.

Stage 4: the map. `build_map` renders the layered surface
— headline, claim groups by status, decisions with their
basis, and per-claim evidence (the ids of the events that
touch each claim) — from the same fold.

Stage 5: the gate. `check_pattern` regenerates the matrix
and the map from the ledger's records and byte-compares
them against the artifacts under check; any divergence is
a downstream defect, reported by layer.
"""

from __future__ import annotations

import json
import os

MATRIX_FORMAT = "epistemic-ledger-matrix/1"


def events_from_log(ledger_dir):
    """The event list of the ledger at `ledger_dir`, read
    WITHOUT opening the store: no writer lock, no database,
    no repair — a pure read of events.jsonl with the same
    parse semantics as `Ledger._events`. The gate uses this
    so checking a ledger writes nothing (the harmonization
    corollary: a read-only gate must be write-free). A line
    that does not parse raises ValueError naming the line.
    """
    path = os.path.join(ledger_dir, "events.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
    except FileNotFoundError:
        return []
    events = []
    for i, line in enumerate(lines, start=1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {i}: {exc}") from exc
    return events


def build_matrix(events):
    """Fold an event list into the canonical claims matrix.

    `events` is the ledger's event list in log order (the
    dicts `Ledger._events()` yields). The fold mirrors the
    projection's semantics over the claim-bearing event
    types: assert creates a row, score_revision settles its
    confidence, supersede and claim_status_changed close it
    into its terminal status. Every asserted claim appears
    exactly once, in assertion order.
    """
    rows = {}
    order = []
    for event in events:
        etype = event.get("type")
        payload = event.get("payload") or {}
        if etype == "assert":
            claim_id = payload["claim_id"]
            rows[claim_id] = {
                "claim_id": claim_id,
                "statement": payload["statement"],
                "source": payload.get("source"),
                "date": event.get("t"),
                "status": "active",
                "confidence": float(payload["prior"]),
                "falsifier": payload.get("falsifier"),
                "does_not_establish": payload.get("does_not_establish"),
                "superseded_by": None,
            }
            order.append(claim_id)
        elif etype == "score_revision":
            row = rows.get(payload.get("claim_id"))
            if row is not None:
                row["confidence"] = float(payload["new_score"])
        elif etype == "supersede":
            row = rows.get(payload.get("old_claim_id"))
            if row is not None:
                row["status"] = "superseded"
                row["superseded_by"] = payload.get("new_claim_id")
        elif etype == "claim_status_changed":
            row = rows.get(payload.get("claim_id"))
            if row is not None:
                row["status"] = payload["status"]
    claims = [rows[claim_id] for claim_id in order]
    counts: dict[str, int] = {}
    for row in claims:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"format": MATRIX_FORMAT, "claims": claims, "counts": counts}


def matrix_from_ledger(ledger):
    """The canonical matrix for a live Ledger instance."""
    return build_matrix(ledger._events())


def matrix_json(matrix):
    """The canonical JSON rendering: sorted keys, exact
    floats (repr), one trailing newline. This is the byte
    form the verification gate compares."""
    return json.dumps(matrix, indent=2, sort_keys=True) + "\n"


def _cell(value):
    if value is None:
        return ""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def matrix_markdown(matrix):
    """The Markdown rendering of the same canonical dict:
    a headline count line and one table row per claim."""
    counts = matrix["counts"]
    headline = ", ".join(f"{k}: {counts[k]}" for k in sorted(counts))
    lines = [
        "# Claims matrix (generated — do not edit)",
        "",
        f"Claims: {len(matrix['claims'])} ({headline})",
        "",
        "| Claim | Statement | Source | Date | Status | Confidence "
        "| Falsifier | Does not establish | Superseded by |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in matrix["claims"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row["claim_id"]),
                    _cell(row["statement"]),
                    _cell(row["source"]),
                    _cell(row["date"]),
                    _cell(row["status"]),
                    repr(float(row["confidence"])),
                    _cell(row["falsifier"]),
                    _cell(row["does_not_establish"]),
                    _cell(row["superseded_by"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


MAP_FORMAT = "epistemic-ledger-map/1"

# Payload keys through which an event can reference a claim.
_CLAIM_REF_KEYS = ("claim_id", "old_claim_id", "new_claim_id", "supports_id")


def build_map(events):
    """Fold an event list into the layered map.

    Layers: the headline (event, claim, and decision totals
    plus the matrix's per-status counts); claim groups by
    status, in assertion order; decisions with their basis
    claim ids and their event id; and per-claim evidence —
    the ids of every event whose payload references the
    claim. Every element is a ledger id or a count folded
    from them: nothing appears that is not in the ledger.
    """
    matrix = build_matrix(events)
    touched: dict[str, list[str]] = {row["claim_id"]: [] for row in matrix["claims"]}
    decisions = []
    for event in events:
        payload = event.get("payload") or {}
        event_id = event.get("event_id")
        for key in _CLAIM_REF_KEYS:
            ref = payload.get(key)
            if ref in touched and event_id not in touched[ref]:
                touched[ref].append(event_id)
        if event.get("type") == "decision":
            decisions.append(
                {
                    "decision_id": payload["decision_id"],
                    "label": payload.get("label"),
                    "basis": list(payload.get("basis") or []),
                    "event_id": event_id,
                }
            )
    groups = []
    for status in sorted(matrix["counts"]):
        groups.append(
            {
                "status": status,
                "claim_ids": [
                    row["claim_id"]
                    for row in matrix["claims"]
                    if row["status"] == status
                ],
            }
        )
    return {
        "format": MAP_FORMAT,
        "headline": {
            "events": len(events),
            "claims": len(matrix["claims"]),
            "decisions": len(decisions),
            "counts": matrix["counts"],
        },
        "groups": groups,
        "decisions": decisions,
        "evidence": [
            {"claim_id": row["claim_id"], "events": touched[row["claim_id"]]}
            for row in matrix["claims"]
        ],
    }


def map_from_ledger(ledger):
    """The canonical map for a live Ledger instance."""
    return build_map(ledger._events())


def map_json(map_dict):
    """The canonical JSON rendering of the map — the byte
    form the verification gate compares."""
    return json.dumps(map_dict, indent=2, sort_keys=True) + "\n"


def map_markdown(map_dict):
    """The Markdown rendering: headline first, then the
    layers — groups, decisions with their basis, and
    per-claim evidence event ids."""
    head = map_dict["headline"]
    counts = head["counts"]
    headline = ", ".join(f"{k}: {counts[k]}" for k in sorted(counts))
    lines = [
        "# Ledger map (generated — do not edit)",
        "",
        f"Events: {head['events']} · Claims: {head['claims']} "
        f"({headline}) · Decisions: {head['decisions']}",
        "",
        "## Claims by status",
        "",
    ]
    for group in map_dict["groups"]:
        lines.append(f"- {group['status']}: " + ", ".join(group["claim_ids"]))
    lines += ["", "## Decisions", ""]
    if map_dict["decisions"]:
        for d in map_dict["decisions"]:
            lines.append(
                f"- {d['decision_id']} ({_cell(d['label'])}) — basis: "
                + ", ".join(d["basis"])
                + f" — event {d['event_id']}"
            )
    else:
        lines.append("- none")
    lines += ["", "## Evidence", ""]
    for entry in map_dict["evidence"]:
        lines.append(f"- {entry['claim_id']}: " + ", ".join(entry["events"]))
    return "\n".join(lines) + "\n"


def check_pattern(events, matrix_text, map_text):
    """The verification gate (DESIGN-17, P5).

    Regenerates the matrix and the map from the ledger's
    records and byte-compares them with the artifacts under
    check. Returns {"ok": bool, "problems": [str]} — a
    divergence is a defect in the downstream artifact,
    never in the ledger, and the problem names the layer.
    """
    problems = []
    if matrix_text != matrix_json(build_matrix(events)):
        problems.append("matrix diverges from the ledger (regenerate it)")
    if map_text != map_json(build_map(events)):
        problems.append("map diverges from the ledger (regenerate it)")
    return {"ok": not problems, "problems": problems}


def check_pattern_for_ledger(ledger, matrix_text, map_text):
    """The gate over a live Ledger instance's artifacts."""
    return check_pattern(ledger._events(), matrix_text, map_text)
