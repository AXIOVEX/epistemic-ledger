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

import hashlib
import json
import os

MATRIX_FORMAT = "epistemic-ledger-matrix/1"

# Amendment 3 to the canonical pattern (ratified
# 2026-11-01): the ledger's schema is declared, versioned,
# and pinned; a validator enforces it at intake and in
# CI; coverage of the pattern-required fields is
# published on every run. The declaration lives in
# docs/pattern/SCHEMA.md; the rules it states are the
# ones enforced here.
SCHEMA_VERSION = "epistemic-ledger-claims/1"

#: The pattern-required claim fields (DESIGN-17 D1: all
#: nullable; absence is counted, never filled in).
PATTERN_FIELDS = ("source", "falsifier", "does_not_establish")


def proposition_fingerprint(statement):
    """The proposition fingerprint of a statement: SHA-256
    over its canonical form (line endings normalized,
    whitespace runs collapsed, ends stripped — the
    canonicalize-before-you-hash discipline). Computed
    fresh by the validator on every run; this package
    stores no fingerprint, so there is no stored value
    to trust.
    """
    canonical = " ".join(statement.replace("\r\n", "\n").split())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_ledger(events):
    """Validate a ledger's claim records against the
    pinned schema (SCHEMA_VERSION). Returns
    {"ok", "problems", "coverage", "schema"}.

    Every assert event is checked: statement present and
    a non-empty string; prior a number in [0, 1]; each
    pattern field a string or null (a missing key is a
    legacy null and is counted, not refused — DESIGN-17
    D1). A violation is a named problem; validation
    writes nothing.

    Coverage is published on every run: claim count,
    per-field non-null counts, and the fingerprint
    census (distinct propositions vs total, so duplicate
    propositions are a standing number). Note the one
    deliberate divergence from Glossa's D-B discipline,
    surfaced to the owner with this adoption: duplicate
    propositions are COUNTED, not refused at intake —
    in this package each assertion is a distinct
    evidence node, and independent assertions of one
    proposition are how corroboration is represented.
    """
    problems = []
    claims = 0
    coverage = {f"with_{f}": 0 for f in PATTERN_FIELDS}
    fingerprints = set()
    for i, event in enumerate(events):
        if event.get("type") != "assert":
            continue
        claims += 1
        p = event.get("payload") or {}
        cid = p.get("claim_id", "?")
        where = f"event {i + 1} (claim {cid})"
        statement = p.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            problems.append(f"{where}: statement missing or not a string")
        else:
            fingerprints.add(proposition_fingerprint(statement))
        prior = p.get("prior")
        if (
            not isinstance(prior, (int, float))
            or isinstance(prior, bool)
            or not 0.0 <= float(prior) <= 1.0
        ):
            problems.append(f"{where}: prior missing or not a number in [0, 1]")
        for f in PATTERN_FIELDS:
            v = p.get(f)
            if v is not None and not isinstance(v, str):
                problems.append(f"{where}: {f} is not a string or null")
            if v is not None:
                coverage[f"with_{f}"] += 1
    return {
        "ok": not problems,
        "problems": problems,
        "coverage": {
            "claims": claims,
            **coverage,
            "distinct_propositions": len(fingerprints),
            "duplicate_propositions": claims - len(fingerprints),
        },
        "schema": SCHEMA_VERSION,
    }


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
