"""Payload commitments and erasure (DESIGN-15 D4, claims T2-T3).

An identified payload never enters the ledger body. What the
chain holds is a ``commitment`` record: the HMAC-SHA-256, under
the tenant's own key, of the payload prefixed with a per-record
random salt. The payload lives elsewhere, encrypted under its
own key; the salt is held with the payload, never written to the
chain. The ledger then proves a payload existed and has not
changed — and nothing more: without the tenant's key, the
commitment yields nothing about the payload, not even whether a
guessed payload is the committed one.

Erasure is the dual act: destroy the payload's key and its salt,
and append an ``erasure`` record referencing the commitment,
signed by the tenant's data-controller key. The payload becomes
unrecoverable from every ledger artifact while the commitment,
and the chain around it, remain verifiable.
"""

from __future__ import annotations

import hashlib
import hmac
import os

#: The record types this module's values travel in. The records
#: themselves are ordinary appends through either engine.
COMMITMENT_TYPE = "commitment"
ERASURE_TYPE = "erasure"

_MIN_SALT = 16


def new_salt() -> bytes:
    """A fresh per-record salt. Held with the payload, never
    written to the chain; destroyed with it at erasure."""
    return os.urandom(_MIN_SALT)


def commitment_for(key: bytes, salt: bytes, payload: bytes) -> str:
    """The commitment value for one payload: HMAC-SHA-256 under
    the tenant's key over salt || payload, as hex. ``key`` is the
    tenant's HMAC key, held with the payload store; it never
    enters the ledger."""
    if len(salt) < _MIN_SALT:
        raise ValueError(f"salt must be at least {_MIN_SALT} bytes")
    return hmac.new(key, salt + payload, hashlib.sha256).hexdigest()


def verify_commitment(key: bytes, salt: bytes, payload: bytes, commitment: str) -> bool:
    """Does this payload, under this key and salt, reproduce the
    committed value? The key holder's recomputation — the only
    direction that can succeed."""
    return hmac.compare_digest(commitment_for(key, salt, payload), commitment)
