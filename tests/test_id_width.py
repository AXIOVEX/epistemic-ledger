"""Identifier width (release-tier soak find, 2026-10-31).

Event, claim, and decision ids come from one helper that
truncated a UUID to 8 hex characters — 32 bits of entropy,
a birthday collision inside ~100k events, which the first
completed 4-hour soak duly produced (verify_store reported
duplicate event ids and every later verification failed).
Ids are opaque strings everywhere; the fix is the full
128-bit UUID hex.
"""

from epistemic_ledger.ledger import _new_id


def test_ids_carry_the_full_uuid_width():
    for prefix in ("E", "C", "D"):
        value = _new_id(prefix)
        assert value.startswith(prefix)
        assert len(value) == 1 + 32
        int(value[1:], 16)  # hex


def test_ids_do_not_collide_at_soak_scale():
    draws = {_new_id("E") for _ in range(200_000)}
    assert len(draws) == 200_000
