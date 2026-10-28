#!/usr/bin/env python3
"""Reference implementation of rust/CHAIN-FORMAT.md (chain format v1).

Produces the shared test vectors both engines must match. Pure
stdlib. Run: python3 tools/chainref.py  -> prints vectors as JSON.
"""

import hashlib
import json
import math
import struct
import sys

# ------------------------------------------------------------------
# ECMAScript Number::toString (RFC 8785 section 3.2.2) for floats.
# Python's repr() already yields the shortest round-trip decimal;
# this re-lays those digits out under the ECMAScript rules.
# ------------------------------------------------------------------


def _shortest_digits(x):
    """Return (digits, n) with x = 0.digits * 10**n, digits shortest."""
    r = repr(x)
    mant, _, exp = r.partition("e")
    e = int(exp) if exp else 0
    mant = mant.lstrip("-")
    if "." in mant:
        ip, fp = mant.split(".")
    else:
        ip, fp = mant, ""
    digits = (ip + fp).lstrip("0")
    # value = int(ip+fp) * 10**(e - len(fp)); strip trailing zeros
    point_exp = e - len(fp)
    trimmed = digits.rstrip("0")
    point_exp += len(digits) - len(trimmed)
    digits = trimmed
    n = point_exp + len(digits)  # value = 0.digits * 10**n
    return digits, n


def es_number(x):
    if isinstance(x, int):
        return str(x)
    if math.isnan(x) or math.isinf(x):
        raise ValueError("non-finite numbers are not valid in payloads")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    digits, n = _shortest_digits(abs(x))
    k = len(digits)
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + digits
    elif k == 1:
        out = digits + "e" + ("+" if n - 1 >= 0 else "-") + str(abs(n - 1))
    else:
        out = (
            digits[0]
            + "."
            + digits[1:]
            + "e"
            + ("+" if n - 1 >= 0 else "-")
            + str(abs(n - 1))
        )
    return sign + out


def canonical_json(value):
    """RFC 8785 canonical JSON for the payload value."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float)):
        return es_number(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return (
            "{"
            + ",".join(
                json.dumps(k, ensure_ascii=False, separators=(",", ":"))
                + ":"
                + canonical_json(v)
                for k, v in items
            )
            + "}"
        )
    raise TypeError(f"uncanonical type: {type(value)}")


# ------------------------------------------------------------------
# CRC32C (Castagnoli), table-driven, reflected polynomial 0x82F63B78.
# ------------------------------------------------------------------

_CRC_TABLE = []
for i in range(256):
    crc = i
    for _ in range(8):
        crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    _CRC_TABLE.append(crc)


def crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc = _CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


# ------------------------------------------------------------------
# The chain itself.
# ------------------------------------------------------------------

GENESIS_PREV = "0" * 64


def hash_input(seq, t, actor, etype, payload_canon, prev_hash):
    out = bytearray(b"ELCHAIN1")
    for field in (str(seq), t, actor, etype, payload_canon, prev_hash):
        b = field.encode("utf-8")
        out += struct.pack(">I", len(b))
        out += b
    return bytes(out)


def record_hash(seq, t, actor, etype, payload, prev_hash):
    canon = canonical_json(payload)
    digest = hashlib.sha256(hash_input(seq, t, actor, etype, canon, prev_hash))
    return digest.hexdigest()


def chain_line(seq, t, actor, etype, payload, prev_hash, sig=None):
    h = record_hash(seq, t, actor, etype, payload, prev_hash)
    obj = {
        "seq": seq,
        "t": t,
        "actor": actor,
        "type": etype,
        "payload": payload,
        "prev_hash": prev_hash,
        "hash": h,
    }
    if sig is not None:
        obj["sig"] = sig
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return f"{crc32c(line.encode('utf-8')):08x} {line}", h


def main():
    vectors = {}
    # Canonical-number vectors: RFC 8785's own examples and edge cases.
    numbers = [1.0, 0.000001, 1e-7, 1e30, 0.1, 1e16, 1e21,
               123456789.123456789, 5e-324, -0.0, 3.141592653589793]
    vectors["numbers"] = {repr(x): es_number(x) for x in numbers}
    # A three-record unsigned chain over representative payloads.
    records = [
        (1, "2026-10-27T00:00:00Z", "system", "assert",
         {"claim_id": "C-0001", "prior": 0.5, "statement": "genesis claim"}),
        (2, "2026-10-27T00:01:00Z", "wire-desk", "support",
         {"claim_id": "C-0002", "parent": "C-0001", "strength": 1}),
        (3, "2026-10-27T00:02:00Z", "wire-desk", "score_revision",
         {"claim_id": "C-0001", "new_score": 0.75}),
    ]
    prev = GENESIS_PREV
    lines = []
    for seq, t, actor, etype, payload in records:
        line, h = chain_line(seq, t, actor, etype, payload, prev)
        lines.append(line)
        prev = h
    vectors["chain_head"] = prev
    vectors["lines"] = lines
    json.dump(vectors, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
