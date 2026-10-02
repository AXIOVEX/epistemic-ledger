"""Ed25519 signatures — the RFC 8032 reference algorithm, vendored.

Pure Python on stdlib hashlib; the prototype stays zero-dependency.
Used for signed governance verdicts (Design Memo 10): writers hold
their own 32-byte seeds and sign externally; the ledger stores only
public keys and verifies. Validated against the RFC 8032 section
7.1 test vectors in prototype/tests/test_ledger.py.

Not constant-time — fine for verdict-rate signing/verification in a
research prototype; not a general-purpose crypto library.
"""

import hashlib

_b = 256
_q = 2 ** 255 - 19
_l = 2 ** 252 + 27742317777372353535851937790883648493


def _H(m):
    return hashlib.sha512(m).digest()


def _expmod(b, e, m):
    return pow(b, e, m)


def _inv(x):
    return pow(x, _q - 2, _q)


_d = (-121665 * _inv(121666)) % _q
_I = _expmod(2, (_q - 1) // 4, _q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = _expmod(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x


_By = (4 * _inv(5)) % _q
_Bx = _xrecover(_By)
_B = [_Bx % _q, _By % _q]


def _edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    den = _inv(1 + _d * x1 * x2 * y1 * y2)
    x3 = (x1 * y2 + x2 * y1) * den
    den2 = _inv(1 - _d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * den2
    return [x3 % _q, y3 % _q]


def _scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _encodeint(y):
    return y.to_bytes(32, "little")


def _encodepoint(P):
    x, y = P
    bits = [(y >> i) & 1 for i in range(_b - 1)]
    enc = bytearray(_encodeint(y))
    if x & 1:
        enc[31] |= 0x80
    return bytes(enc)


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _decodeint(s):
    return int.from_bytes(s, "little")


def _decodepoint(s):
    y = sum(2 ** i * _bit(s, i) for i in range(0, _b - 1))
    x = _xrecover(y)
    if x & 1 != _bit(s, _b - 1):
        x = _q - x
    return [x, y]


def _Hint(m):
    h = _H(m)
    return sum(2 ** i * _bit(h, i) for i in range(2 * _b))


def _publickey_from_h(h):
    a = 2 ** (_b - 2) + sum(2 ** i * _bit(h, i) for i in range(3, _b - 2))
    return a


def publickey(seed):
    """32-byte seed -> 32-byte public key."""
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = _H(seed)
    a = _publickey_from_h(h)
    return _encodepoint(_scalarmult(_B, a))


def sign(seed, msg):
    """32-byte seed + message bytes -> 64-byte signature."""
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = _H(seed)
    a = _publickey_from_h(h)
    pk = _encodepoint(_scalarmult(_B, a))
    r = _Hint(h[_b // 8:_b // 4] + msg)
    R = _scalarmult(_B, r)
    S = (r + _Hint(_encodepoint(R) + pk + msg) * a) % _l
    return _encodepoint(R) + _encodeint(S)


def verify(pk, msg, sig):
    """True iff sig is a valid signature of msg under pk (32 bytes)."""
    if len(pk) != 32 or len(sig) != 64:
        return False
    try:
        R = _decodepoint(sig[:32])
        A = _decodepoint(pk)
    except Exception:
        return False
    S = _decodeint(sig[32:])
    if S >= _l:
        return False
    h = _Hint(sig[:32] + pk + msg) % _l
    return _scalarmult(_B, S) == _edwards(R, _scalarmult(A, h))
