"""Standalone verification of signed tree heads and proofs
(DESIGN-15 stage 1, claims A1-A3).

This module is the third-party verifier: it checks signed tree
heads (STHs), record inclusion proofs, and checkpoint consistency
proofs using only JSON artifacts and the checkpoint key's public
key — no store access, no Rust extension, nothing beyond the
standard library and the package's vendored Ed25519. Anything
Arcturus (or an auditor) pins or receives can be checked here.

Formats are the Rust core's (`epistemic_ledger_core::sth`): the
STH signature is Ed25519 over SHA-256 of the domain separator
``ELSTH1`` followed by the canonical JSON of the unsigned head;
for the flat head object, canonical JSON is sorted-key compact
JSON. Inclusion is the RFC 9162 audit path within one checkpoint
segment; consistency is checkpoint chain linkage (each checkpoint
carries its predecessor's root in ``prev_root``).
"""

from __future__ import annotations

import hashlib
import json

from . import ed25519

_DOMAIN = b"ELSTH1"


def _canonical(obj: dict) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _sth_digest(sth: dict) -> bytes:
    unsigned = {
        "checkpoint_seq": sth["checkpoint_seq"],
        "key_id": sth["key_id"],
        "root": sth["root"],
        "timestamp": sth["timestamp"],
        "tree_size": sth["tree_size"],
    }
    return hashlib.sha256(_DOMAIN + _canonical(unsigned)).digest()


def verify_sth(sth: dict, pubkey_hex: str) -> bool:
    """True iff the STH's signature verifies under the checkpoint
    key. Checks the signature only; pair with the fork test and
    consistency verification for the full pinning discipline."""
    try:
        pubkey = bytes.fromhex(pubkey_hex)
        sig = bytes.fromhex(sth["signature"])
        digest = _sth_digest(sth)
    except (KeyError, ValueError):
        return False
    return ed25519.verify(pubkey, digest, sig)


def is_fork(a: dict, b: dict) -> bool:
    """Equivocation test (A3): two heads for the same checkpoint
    (same sequence and tree size) with different roots. Verify both
    signatures first — a fork between two *validly signed* heads is
    proof the operator equivocated."""
    return (
        a.get("checkpoint_seq") == b.get("checkpoint_seq")
        and a.get("tree_size") == b.get("tree_size")
        and a.get("root") != b.get("root")
    )


def _leaf_hash(leaf: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + leaf).digest()


def _node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(total: int) -> int:
    k = 1
    while k * 2 < total:
        k *= 2
    return k


def _fold(acc: bytes, index: int, total: int, proof: list[bytes]) -> bytes | None:
    if total == 1:
        return acc if not proof else None
    if not proof:
        return None
    sibling, rest = proof[-1], proof[:-1]
    k = _split(total)
    if index < k:
        left = _fold(acc, index, k, rest)
        return None if left is None else _node_hash(left, sibling)
    right = _fold(acc, index - k, total - k, rest)
    return None if right is None else _node_hash(sibling, right)


def verify_inclusion(
    leaf_hash_hex: str,
    index: int,
    segment_len: int,
    proof_hex: list[str],
    root_hex: str,
) -> bool:
    """True iff the record hash at ``index`` is included in the
    segment whose Merkle root is ``root_hex`` (A2)."""
    try:
        leaf = bytes.fromhex(leaf_hash_hex)
        root = bytes.fromhex(root_hex)
        proof = [bytes.fromhex(h) for h in proof_hex]
    except ValueError:
        return False
    if segment_len == 0 or index >= segment_len or len(leaf) != 32 or len(root) != 32:
        return False
    return _fold(_leaf_hash(leaf), index, segment_len, proof) == root


def verify_consistency(from_sth: dict, to_sth: dict, proof: dict) -> bool:
    """True iff ``to_sth`` extends ``from_sth`` (A1): the proof's
    checkpoints link the two heads' roots into one unbroken,
    contiguous chain. Verify both heads' signatures separately."""
    links = proof.get("checkpoints", [])
    a_seq, b_seq = from_sth["checkpoint_seq"], to_sth["checkpoint_seq"]
    if a_seq > b_seq:
        return False
    if a_seq == b_seq:
        return (
            not links
            and from_sth["tree_size"] == to_sth["tree_size"]
            and from_sth["root"] == to_sth["root"]
        )
    if len(links) != b_seq - a_seq:
        return False
    prev_root = from_sth["root"]
    next_first = from_sth["tree_size"] + 1
    for link in links:
        if (
            link["prev_root"] != prev_root
            or link["first_seq"] != next_first
            or link["last_seq"] < link["first_seq"]
        ):
            return False
        prev_root = link["root"]
        next_first = link["last_seq"] + 1
    return prev_root == to_sth["root"] and next_first == to_sth["tree_size"] + 1


def verify_anchored_record(
    record_hash_hex: str,
    inclusion: dict,
    sth: dict,
    pubkey_hex: str,
) -> bool:
    """The full A2 check in one call: the STH is validly signed,
    the inclusion proof belongs to the STH's checkpoint (same root,
    sequence coverage), and the record is included under that root.
    ``inclusion`` is the object the bindings' inclusion proof call
    returns."""
    if not verify_sth(sth, pubkey_hex):
        return False
    if (
        inclusion.get("root") != sth["root"]
        or inclusion.get("checkpoint_seq") != sth["checkpoint_seq"]
    ):
        return False
    if not (
        inclusion["segment_first_seq"]
        <= inclusion["seq"]
        <= inclusion["segment_last_seq"]
    ):
        return False
    return verify_inclusion(
        record_hash_hex,
        inclusion["index"],
        inclusion["segment_len"],
        inclusion["proof"],
        inclusion["root"],
    )


def key_effective_at(report: dict, key_id: str, seq: int) -> bool:
    """Was ``key_id`` inside an enrollment window at ``seq``?

    ``report`` is the governance report the bindings return (the
    partition's enrollment windows and violations, folded from its
    own chain). A checkpoint-key holder checks a signed tree head
    this way: the head's key must have been effective at the
    head's tree size. The report's violations are the caller's to
    inspect — a window read from a report that carries violations
    describes a store that does not govern cleanly.
    """
    for window in report.get("windows", []):
        if window.get("key_id") != key_id:
            continue
        revoked = window.get("revoked_seq")
        if window["enrolled_seq"] < seq and (revoked is None or seq < revoked):
            return True
    return False
