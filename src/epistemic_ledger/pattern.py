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
"""

from __future__ import annotations

import json

MATRIX_FORMAT = "epistemic-ledger-matrix/1"


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
