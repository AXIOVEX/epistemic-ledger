"""Payload commitments (DESIGN-15 D4, claims T2-T3, unit level).

The HMAC construction itself: the key holder's recomputation
verifies, and every single-factor change — key, salt, payload —
breaks it. The adversarial drills (dictionary attack over a
known payload space, post-erasure recovery from every artifact)
live in the battery.
"""

from __future__ import annotations

import pytest

from epistemic_ledger import commitments

KEY = bytes.fromhex("aa" * 32)
OTHER_KEY = bytes.fromhex("bb" * 32)
PAYLOAD = b"case-1: reading support, twice weekly"


def test_round_trip_verifies():
    salt = commitments.new_salt()
    value = commitments.commitment_for(KEY, salt, PAYLOAD)
    assert len(value) == 64
    assert commitments.verify_commitment(KEY, salt, PAYLOAD, value)


def test_every_factor_is_load_bearing():
    salt = commitments.new_salt()
    value = commitments.commitment_for(KEY, salt, PAYLOAD)
    assert not commitments.verify_commitment(OTHER_KEY, salt, PAYLOAD, value)
    assert not commitments.verify_commitment(KEY, salt, b"case-2", value)
    assert not commitments.verify_commitment(
        KEY, commitments.new_salt(), PAYLOAD, value
    )


def test_salt_is_per_record():
    one = commitments.commitment_for(KEY, commitments.new_salt(), PAYLOAD)
    two = commitments.commitment_for(KEY, commitments.new_salt(), PAYLOAD)
    assert one != two
    assert len(commitments.new_salt()) >= 16


def test_short_salt_refused():
    with pytest.raises(ValueError):
        commitments.commitment_for(KEY, b"short", PAYLOAD)
