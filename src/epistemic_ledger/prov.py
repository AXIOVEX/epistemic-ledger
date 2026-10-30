"""W3C PROV provenance export (DESIGN-15 D6, claim V1).

Renders chained-store records as a W3C PROV document
(PROV-JSON): one entity per record, one activity per append,
one agent per actor, generation and association relations for
every record, and derivation relations only where a record
declares them — a payload ``derived_from`` list of record seqs,
or a ``basis`` list on a record of type ``decision``. The
export invents no other links.

The export is a wrapper: a ``header`` carrying the record
count, the store's head hash, and (when the caller supplies
one) the signed tree head the export was made under — so anyone
holding that STH can check the export against the anchored
chain — beside the PROV ``document`` itself.

The export is a pure function of its inputs: identifiers derive
from sequence numbers, no wall clock is consulted, and callers
serializing with sorted keys get a byte-identical re-export of
an unchanged store (V1's determinism leg).
"""

from __future__ import annotations

import re

__all__ = ["export_prov", "export_store_prov"]

_FORMAT = "epistemic-ledger-prov/1"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _agent_id(actor: str, seen: dict[str, str]) -> str:
    """A valid, stable PROV identifier for an actor string.

    The exact actor string is preserved on the agent as an
    attribute; the identifier is its slug, disambiguated in
    first-seen order if two actors slugify alike.
    """
    if actor in seen:
        return seen[actor]
    base = "el:agent-" + _UNSAFE.sub("-", actor)
    candidate = base
    n = 2
    while candidate in seen.values():
        candidate = f"{base}-{n}"
        n += 1
    seen[actor] = candidate
    return candidate


def _declared_derivations(record: dict) -> list[int]:
    payload = record.get("payload") or {}
    if not isinstance(payload, dict):
        return []
    refs: list[int] = []
    derived = payload.get("derived_from")
    if isinstance(derived, list):
        refs.extend(x for x in derived if isinstance(x, int))
    if record.get("type") == "decision":
        basis = payload.get("basis")
        if isinstance(basis, list):
            refs.extend(x for x in basis if isinstance(x, int))
    return refs


def export_prov(records: list[dict], head_hash: str, sth: dict | None = None) -> dict:
    """The PROV export of a record slice (usually a whole store).

    ``records`` are chained-store record dicts as the bindings'
    record reader returns them; ``head_hash`` is the store's
    head hash the export is made under; ``sth`` is an optional
    signed tree head dict to carry in the header.
    """
    entities: dict[str, dict] = {}
    activities: dict[str, dict] = {}
    agents: dict[str, dict] = {}
    generated: dict[str, dict] = {}
    associated: dict[str, dict] = {}
    derived: dict[str, dict] = {}
    agent_ids: dict[str, str] = {}
    present = {rec["seq"] for rec in records}
    derivations = 0

    for rec in records:
        seq = rec["seq"]
        entity_id = f"el:record-{seq}"
        activity_id = f"el:append-{seq}"
        agent_id = _agent_id(rec["actor"], agent_ids)
        entities[entity_id] = {
            "el:recordType": rec["type"],
            "el:hash": rec["hash"],
            "el:prevHash": rec["prev_hash"],
        }
        activities[activity_id] = {
            "prov:startTime": rec["t"],
            "el:recordType": rec["type"],
        }
        agents.setdefault(agent_id, {"el:actorName": rec["actor"]})
        generated[f"_:wgb{seq}"] = {
            "prov:entity": entity_id,
            "prov:activity": activity_id,
        }
        associated[f"_:waw{seq}"] = {
            "prov:activity": activity_id,
            "prov:agent": agent_id,
        }
        for i, src in enumerate(_declared_derivations(rec)):
            if src not in present:
                continue
            derived[f"_:wdf{seq}-{i}"] = {
                "prov:generatedEntity": entity_id,
                "prov:usedEntity": f"el:record-{src}",
            }
            derivations += 1

    document = {
        "prefix": {
            "prov": "http://www.w3.org/ns/prov#",
            "el": "urn:epistemic-ledger:",
        },
        "entity": entities,
        "activity": activities,
        "agent": agents,
        "wasGeneratedBy": generated,
        "wasAssociatedWith": associated,
        "wasDerivedFrom": derived,
    }
    header = {
        "format": _FORMAT,
        "records": len(records),
        "head_hash": head_hash,
        "sth": sth,
        "derivations": derivations,
    }
    return {"header": header, "document": document}


def export_store_prov(store_dir: str, sth: dict | None = None) -> dict:
    """Export a whole chained store directory (bindings reader)."""
    import json

    from epistemic_ledger._core import read_records_json

    records = json.loads(read_records_json(store_dir))
    head = records[-1]["hash"] if records else "0" * 64
    return export_prov(records, head, sth)
