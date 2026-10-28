"""LQL — the Ledger Query Language (DESIGN-13 section 5).

A small, read-only query language over a Ledger. The whole
grammar fits on one page (docs/lql.md). Anything outside the
grammar is a parse error naming the position — parsing completes
fully before anything executes, and LQL has no writes at all:
every construct compiles to a read call on the core API, and the
result is exactly that call's result (claim Q1).

    CLAIM <id>                        one claim, full record
    CLAIMS [WHERE <filter>]           live claims
    WHY <id>                          support ancestry
    IMPACT <id> [STRUCTURAL | PROPAGATED TO <number>]
    DEPENDS <id>                      dependency closure
    AS_OF <timestamp> <query>         CLAIMS/CLAIM/EVENTS/DECISIONS
                                      against the state at that time
    EVENTS [WHERE <filter>]           audit-trail reads over the log
    DECISIONS [WHERE <filter>]        decision nodes, with basis sets
    HEALTH                            the health report

Filters are comparisons over named fields combined with AND/OR
(AND binds tighter; no parentheses — the grammar budget is the
point). Fields per construct:

    CLAIMS:    status, writer, tier, score, kind, entrenchment,
               materiality, critical
    EVENTS:    type, actor, t
    DECISIONS: kind, actor, label
"""

from datetime import datetime

__all__ = ["LQLParseError", "execute", "parse"]


class LQLParseError(ValueError):
    """Malformed LQL. Carries the character position of the
    offending token; nothing was executed."""

    def __init__(self, message, position):
        super().__init__(f"{message} (position {position})")
        self.message = message
        self.position = position


class _Token:
    __slots__ = ("kind", "text", "pos")

    def __init__(self, kind, text, pos):
        self.kind = kind  # word | number | string | op | eof
        self.text = text
        self.pos = pos

    def __repr__(self):
        return f"<{self.kind} {self.text!r} @{self.pos}>"


_OPS = ("!=", "<=", ">=", "=", "<", ">")


def _tokenize(text):
    tokens = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "'":
            j = i + 1
            buf = []
            while True:
                if j >= n:
                    raise LQLParseError("unterminated string", i)
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(text[j])
                j += 1
            tokens.append(_Token("string", "".join(buf), i))
            i = j
            continue
        if ch in "=!<>":
            for op in _OPS:
                if text.startswith(op, i):
                    tokens.append(_Token("op", op, i))
                    i += len(op)
                    break
            else:
                raise LQLParseError(f"unexpected character {ch!r}", i)
            continue
        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in ".:+-"):
                j += 1
            raw = text[i:j]
            tokens.append(_Token("number", raw, i))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in "_-"):
                j += 1
            tokens.append(_Token("word", text[i:j], i))
            i = j
            continue
        raise LQLParseError(f"unexpected character {ch!r}", i)
    tokens.append(_Token("eof", "", n))
    return tokens


def _as_number(tok):
    """A number token reads as a float when it is one, else as a
    timestamp string (AS_OF operands start with digits too)."""
    try:
        return float(tok.text), True
    except ValueError:
        return tok.text, False


# Field types per construct: "str" fields compare as text,
# "num" fields numerically, "bool" against true/false words.
_FIELDS = {
    "claims": {
        "status": "str",
        "writer": "str",
        "tier": "str",
        "kind": "str",
        "score": "num",
        "entrenchment": "num",
        "materiality": "num",
        "critical": "bool",
    },
    "events": {"type": "str", "actor": "str", "t": "str"},
    "decisions": {"kind": "str", "actor": "str", "label": "str"},
}


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def next(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect_word(self, word):
        tok = self.peek()
        if tok.kind != "word" or tok.text.upper() != word:
            raise LQLParseError(f"expected {word}", tok.pos)
        return self.next()

    def at_word(self, word):
        tok = self.peek()
        return tok.kind == "word" and tok.text.upper() == word

    def expect_id(self, what):
        tok = self.next()
        if tok.kind not in ("word", "number") or not tok.text:
            raise LQLParseError(f"expected {what}", tok.pos)
        return tok

    def expect_end(self):
        tok = self.peek()
        if tok.kind != "eof":
            raise LQLParseError(f"unexpected trailing input {tok.text!r}", tok.pos)

    def parse_query(self):
        as_of = None
        if self.at_word("AS_OF"):
            self.next()
            ts_tok = self.next()
            if ts_tok.kind not in ("number", "string", "word"):
                raise LQLParseError("expected a timestamp after AS_OF", ts_tok.pos)
            as_of = ts_tok.text
            _validate_timestamp(as_of, ts_tok.pos)
            head = self.peek()
            if not (
                head.kind == "word"
                and head.text.upper() in ("CLAIM", "CLAIMS", "EVENTS", "DECISIONS")
            ):
                raise LQLParseError(
                    "AS_OF applies to CLAIM, CLAIMS, EVENTS, and DECISIONS",
                    head.pos,
                )
        tok = self.next()
        if tok.kind != "word":
            raise LQLParseError("expected a query keyword", tok.pos)
        kw = tok.text.upper()
        if kw == "CLAIM":
            id_tok = self.expect_id("a claim id after CLAIM")
            self.expect_end()
            return {"kind": "claim", "id": id_tok.text, "as_of": as_of}
        if kw == "CLAIMS":
            filt = self.parse_optional_filter("claims")
            self.expect_end()
            return {"kind": "claims", "filter": filt, "as_of": as_of}
        if kw == "WHY":
            id_tok = self.expect_id("a claim id after WHY")
            self.expect_end()
            return {"kind": "why", "id": id_tok.text}
        if kw == "DEPENDS":
            id_tok = self.expect_id("a claim id after DEPENDS")
            self.expect_end()
            return {"kind": "depends", "id": id_tok.text}
        if kw == "IMPACT":
            id_tok = self.expect_id("a claim id after IMPACT")
            mode, value = "structural", None
            if self.at_word("STRUCTURAL"):
                self.next()
            elif self.at_word("PROPAGATED"):
                self.next()
                self.expect_word("TO")
                v_tok = self.next()
                if v_tok.kind != "number":
                    raise LQLParseError(
                        "expected a number after PROPAGATED TO", v_tok.pos
                    )
                value, ok = _as_number(v_tok)
                if not ok:
                    raise LQLParseError(
                        "expected a number after PROPAGATED TO", v_tok.pos
                    )
                mode = "propagated"
            self.expect_end()
            return {"kind": "impact", "id": id_tok.text, "mode": mode, "value": value}
        if kw == "EVENTS":
            filt = self.parse_optional_filter("events")
            self.expect_end()
            return {"kind": "events", "filter": filt, "as_of": as_of}
        if kw == "DECISIONS":
            filt = self.parse_optional_filter("decisions")
            self.expect_end()
            return {"kind": "decisions", "filter": filt, "as_of": as_of}
        if kw == "HEALTH":
            self.expect_end()
            return {"kind": "health"}
        raise LQLParseError(f"unknown query keyword {tok.text!r}", tok.pos)

    def parse_optional_filter(self, scope):
        if not self.at_word("WHERE"):
            return None
        self.next()
        return self.parse_filter(scope)

    def parse_filter(self, scope):
        node = self.parse_and(scope)
        while self.at_word("OR"):
            self.next()
            node = ("or", node, self.parse_and(scope))
        return node

    def parse_and(self, scope):
        node = self.parse_comparison(scope)
        while self.at_word("AND"):
            self.next()
            node = ("and", node, self.parse_comparison(scope))
        return node

    def parse_comparison(self, scope):
        field_tok = self.next()
        if field_tok.kind != "word":
            raise LQLParseError("expected a field name", field_tok.pos)
        field = field_tok.text.lower()
        fields = _FIELDS[scope]
        if field not in fields:
            raise LQLParseError(
                f"unknown field {field_tok.text!r} for {scope}", field_tok.pos
            )
        op_tok = self.next()
        if op_tok.kind != "op":
            raise LQLParseError("expected a comparison operator", op_tok.pos)
        val_tok = self.next()
        ftype = fields[field]
        if ftype == "num":
            if val_tok.kind != "number":
                raise LQLParseError(
                    f"field {field} compares numerically; expected a number",
                    val_tok.pos,
                )
            value, ok = _as_number(val_tok)
            if not ok:
                raise LQLParseError(
                    f"field {field} compares numerically; expected a number",
                    val_tok.pos,
                )
        elif ftype == "bool":
            if val_tok.kind != "word" or val_tok.text.lower() not in ("true", "false"):
                raise LQLParseError(
                    f"field {field} compares against true or false", val_tok.pos
                )
            value = val_tok.text.lower() == "true"
        else:
            if val_tok.kind not in ("word", "string", "number"):
                raise LQLParseError("expected a value", val_tok.pos)
            value = val_tok.text
        return ("cmp", field, op_tok.text, value)


def _validate_timestamp(text, pos):
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        raise LQLParseError(f"invalid timestamp {text!r}", pos) from None


def parse(text):
    """Parse LQL text into a query plan. Raises LQLParseError with
    the offending position; a successful parse is the only way to
    reach execution."""
    if not isinstance(text, str) or not text.strip():
        raise LQLParseError("empty query", 0)
    return _Parser(_tokenize(text)).parse_query()


def _compare(actual, op, value):
    if actual is None:
        return op == "!=" and value is not None
    if op == "=":
        return actual == value
    if op == "!=":
        return actual != value
    if op == "<":
        return actual < value
    if op == "<=":
        return actual <= value
    if op == ">":
        return actual > value
    return actual >= value


def _matches(node, record):
    if node is None:
        return True
    tag = node[0]
    if tag == "and":
        return _matches(node[1], record) and _matches(node[2], record)
    if tag == "or":
        return _matches(node[1], record) or _matches(node[2], record)
    _, field, op, value = node
    return _compare(record.get(field), op, value)


def _filter_view(ledger, row_dict, tier_cache):
    """A claim dict plus its derived filter fields (kind, tier),
    used only for WHERE matching. Query results themselves are the
    core API dicts, unmodified — that is what makes Q1 an equality,
    not a resemblance. Writer tiers are memoized per query: a
    filtered scan over many claims must not become a lookup per
    row."""
    d = dict(row_dict)
    d["kind"] = d.get("score_kind")
    writer = d.get("writer")
    if writer:
        if writer not in tier_cache:
            tier_cache[writer] = ledger.get_writer(writer)
        d["tier"] = tier_cache[writer]
    else:
        d["tier"] = None
    return d


def execute(ledger, text):
    """Parse, then run the query against ``ledger``. The result is
    exactly the corresponding core API result (claim Q1):
    CLAIM -> get_claim, CLAIMS -> list_claims (filtered),
    WHY -> why, DEPENDS -> depends_on, IMPACT -> impact,
    EVENTS -> the event log (filtered), DECISIONS -> decisions
    (filtered), HEALTH -> health."""
    plan = parse(text)
    kind = plan["kind"]
    as_of = plan.get("as_of")
    if kind == "claim":
        if as_of is not None:
            for row in ledger.believed_at(as_of):
                if row["claim_id"] == plan["id"]:
                    return ledger._claim_dict(row)
            return None
        return ledger.get_claim(plan["id"])
    if kind == "claims":
        if as_of is not None:
            rows = [ledger._claim_dict(r) for r in ledger.believed_at(as_of)]
        else:
            rows = ledger.list_claims()
        tier_cache = {}
        return [
            r
            for r in rows
            if _matches(plan["filter"], _filter_view(ledger, r, tier_cache))
        ]
    if kind == "why":
        return ledger.why(plan["id"])
    if kind == "depends":
        return ledger.depends_on(plan["id"])
    if kind == "impact":
        if plan["mode"] == "propagated":
            return ledger.impact(
                plan["id"], mode="propagated", revised_score=plan["value"]
            )
        return ledger.impact(plan["id"])
    if kind == "events":
        events = ledger._events()
        if as_of is not None:
            events = [e for e in events if e["t"] <= as_of]
        return [e for e in events if _matches(plan["filter"], e)]
    if kind == "decisions":
        decisions = ledger.decisions()
        if as_of is not None:
            decisions = [d for d in decisions if d["t"] <= as_of]
        return [d for d in decisions if _matches(plan["filter"], d)]
    if kind == "health":
        return ledger.health()
    raise AssertionError(f"unhandled plan kind {kind}")  # unreachable
