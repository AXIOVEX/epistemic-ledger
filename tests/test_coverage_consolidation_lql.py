"""Coverage tests for consolidation.py and lql.py.

Consolidation: the live network clients (OpenRouterClient,
LocalClient) are exercised only through fakes -- a stub
``dynamic_credentials`` module placed in ``sys.modules`` and a
stub ``urllib.request.urlopen``. No real network happens.

LQL: the parser/evaluator error and edge paths not reached by
tests/test_lql.py (escaped quotes, non-numeric number tokens,
explicit STRUCTURAL, AS_OF corner cases, the remaining comparison
operators, tier-cache hits, and the unreachable-plan guard).
"""

import json
import sys
import types
import urllib.request

import pytest

from epistemic_ledger import Ledger, consolidation, lql
from epistemic_ledger.consolidation import (
    BudgetExceeded,
    Consolidator,
    FakeLLM,
    LocalClient,
    OpenRouterClient,
    build_prompt,
    parse_relations,
)
from epistemic_ledger.lql import LQLParseError, execute, parse

# ------------------------------------------------------------------
# consolidation: OpenRouterClient through fakes
# ------------------------------------------------------------------

CATALOG = {
    "data": [
        {"id": "someone/else", "pricing": {"prompt": "9", "completion": "9"}},
        {
            "id": consolidation.DEFAULT_MODEL,
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
        },
        {"id": "free/model"},  # no pricing dict at all
    ]
}

CHAT = {
    "choices": [{"message": {"content": "the reply"}}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload


def _install_openrouter_fakes(monkeypatch, catalog=None, chat=None):
    """Stub dynamic_credentials + urlopen. Returns a capture dict."""
    catalog = CATALOG if catalog is None else catalog
    chat = CHAT if chat is None else chat
    seen = {"allowed": [], "surrogates": [], "requests": []}

    dc = types.ModuleType("dynamic_credentials")

    def ensure_allowed_url(url, hosts):
        seen["allowed"].append((url, list(hosts)))

    def add_surrogate_to_request(req, credential, allowed_hosts=None):
        seen["surrogates"].append((credential, list(allowed_hosts or [])))
        req.add_header("Authorization", "Bearer fake")

    def read_json_response(resp):
        return resp._payload

    dc.ensure_allowed_url = ensure_allowed_url
    dc.add_surrogate_to_request = add_surrogate_to_request
    dc.read_json_response = read_json_response
    monkeypatch.setitem(sys.modules, "dynamic_credentials", dc)

    def fake_urlopen(req, timeout=None):
        seen["requests"].append((req, timeout))
        if req.full_url.endswith("/models"):
            return _FakeResponse(catalog)
        assert req.full_url.endswith("/chat/completions")
        return _FakeResponse(chat)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_openrouter_init_fetches_pricing_get_without_body(monkeypatch):
    seen = _install_openrouter_fakes(monkeypatch)
    client = OpenRouterClient(cap_usd=2.50)
    assert client.model == consolidation.DEFAULT_MODEL
    assert client.cap == 2.50
    assert client.spent == 0.0
    assert client.calls == 0
    # the non-matching catalog entry is skipped, the match is priced
    assert client.pricing == (0.000003, 0.000015)
    ((req, timeout),) = seen["requests"]
    assert req.get_method() == "GET"
    assert req.data is None
    assert timeout == 120
    # a GET carries no JSON body header but does carry the static ones
    assert req.get_header("Content-type") is None
    assert req.get_header("X-title") == "epistemic-ledger-consolidation"
    assert seen["allowed"] == [
        ("https://openrouter.ai/api/v1/models", ["openrouter.ai"])
    ]
    assert seen["surrogates"] == [(consolidation.CREDENTIAL, ["openrouter.ai"])]


def test_openrouter_pricing_defaults_when_pricing_missing(monkeypatch):
    _install_openrouter_fakes(monkeypatch)
    client = OpenRouterClient(model="free/model")
    assert client.pricing == (0.0, 0.0)


def test_openrouter_unknown_model_raises_keyerror(monkeypatch):
    _install_openrouter_fakes(monkeypatch, catalog={"data": []})
    with pytest.raises(KeyError, match="not in OpenRouter catalog"):
        OpenRouterClient(model="nope/model")


def test_openrouter_complete_charges_from_usage(monkeypatch):
    seen = _install_openrouter_fakes(monkeypatch)
    client = OpenRouterClient()
    text, cost = client.complete("hello ledger")
    assert text == "the reply"
    assert cost == pytest.approx(1000 * 0.000003 + 100 * 0.000015)
    assert client.spent == pytest.approx(cost)
    assert client.calls == 1
    req, _timeout = seen["requests"][-1]
    assert req.get_method() == "POST"
    assert req.get_header("Content-type") == "application/json"
    payload = json.loads(req.data.decode())
    assert payload["model"] == consolidation.DEFAULT_MODEL
    assert payload["messages"][1] == {"role": "user", "content": "hello ledger"}
    assert payload["messages"][0]["content"] == consolidation.SYSTEM_PROMPT
    assert payload["max_tokens"] == 800
    assert payload["temperature"] == 0


def test_openrouter_complete_without_usage_is_free(monkeypatch):
    chat = {"choices": [{"message": {"content": "no usage"}}]}
    _install_openrouter_fakes(monkeypatch, chat=chat)
    client = OpenRouterClient()
    text, cost = client.complete("hi", system="custom system")
    assert (text, cost) == ("no usage", 0.0)
    assert client.calls == 1


def test_openrouter_budget_exceeded_before_any_call(monkeypatch):
    seen = _install_openrouter_fakes(monkeypatch)
    client = OpenRouterClient(cap_usd=0.01)
    client.spent = 0.01  # exactly at the cap
    with pytest.raises(BudgetExceeded, match="cap"):
        client.complete("never sent")
    # only the pricing fetch happened; no chat request was made
    assert len(seen["requests"]) == 1
    assert client.calls == 0


# ------------------------------------------------------------------
# consolidation: LocalClient through a fake urlopen
# ------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_local_fake(monkeypatch, content="local reply"):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"] = req
        seen["timeout"] = timeout
        return _FakeHTTPResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_local_client_defaults_and_thinking_on(monkeypatch):
    seen = _install_local_fake(monkeypatch)
    client = LocalClient(base_url="http://localhost:9999/v1/")
    assert client.base_url == "http://localhost:9999/v1"  # slash stripped
    assert client.spent == 0.0 and client.calls == 0
    text, cost = client.complete("prompt here")
    assert (text, cost) == ("local reply", 0.0)
    assert client.calls == 1 and client.spent == 0.0
    req = seen["req"]
    assert req.full_url == "http://localhost:9999/v1/chat/completions"
    assert seen["timeout"] == 300
    payload = json.loads(req.data.decode())
    assert payload["model"] == "qwen3-8b-local"
    assert payload["max_tokens"] == 12000
    assert "chat_template_kwargs" not in payload  # thinking stays on


def test_local_client_thinking_off_sets_template_kwargs(monkeypatch):
    seen = _install_local_fake(monkeypatch, content="bare answer")
    client = LocalClient(
        base_url="http://example.test:1234/v1",
        model="m",
        timeout=7,
        max_tokens=42,
        repeat_penalty=1.1,
        thinking=False,
    )
    text, cost = client.complete("p", system="s")
    assert (text, cost) == ("bare answer", 0.0)
    assert seen["timeout"] == 7
    payload = json.loads(seen["req"].data.decode())
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["max_tokens"] == 42
    assert payload["repeat_penalty"] == 1.1
    assert payload["messages"][0] == {"role": "system", "content": "s"}


# ------------------------------------------------------------------
# consolidation: parse_relations / build_prompt edges
# ------------------------------------------------------------------


def test_parse_relations_drops_malformed_pairs():
    text = json.dumps(
        {
            "contradicts": [["A"], ["A", "B", "C"], "AB", ["A", "B"]],
            "same": [[1, 2]],  # ids are stringified
            # "supports" key absent entirely -> empty
        }
    )
    rel = parse_relations("prefix " + text + " suffix")
    assert rel["contradicts"] == [("A", "B")]
    assert rel["same"] == [("1", "2")]
    assert rel["supports"] == []


def test_parse_relations_without_json_raises():
    with pytest.raises(ValueError, match="no JSON object"):
        parse_relations("no json here at all")


def test_build_prompt_formats_scores():
    prompt = build_prompt([{"claim_id": "C1", "statement": "alpha", "score": 0.5}])
    assert "[C1] (credence 0.50) alpha" in prompt
    assert "SUPPORTS:" in prompt


# ------------------------------------------------------------------
# consolidation: Consolidator over a stub ledger
# ------------------------------------------------------------------


class _StubLedger:
    """Just the surface Consolidator.run touches."""

    def __init__(self, rows, open_ids=()):
        self._rows = rows
        self._open_ids = set(open_ids)
        self.topics = []
        self.declared = []
        self._seq = 0

    def believed_at(self, t):
        return list(self._rows)

    def assign_topic(self, cid, topic, actor=None):
        self.topics.append((cid, topic, actor))

    def declare_contradiction(self, a, b, actor=None, auto=None, signal=None):
        self._seq += 1
        eid = f"E{self._seq}"
        self.declared.append((a, b, actor, auto, signal, eid))
        return eid

    def open_contradictions(self):
        return [{"event_id": eid} for eid in sorted(self._open_ids)]


def _rows(*ids):
    return [
        {"claim_id": cid, "statement": f"statement {cid}", "score": "0.50"}
        for cid in ids
    ]


def test_consolidator_no_claims_returns_empty_report():
    stub = _StubLedger([])
    fake = FakeLLM("{}")
    rep = Consolidator(stub, fake).run()
    assert rep["n_claims"] == 0
    assert rep["contradictions_declared"] == []
    assert rep["topics_assigned"] == {}
    assert rep["cost_usd"] == 0.0
    assert fake.calls == 0  # the LLM is never consulted


def test_consolidator_single_claim_returns_empty_report():
    stub = _StubLedger(_rows("A"))
    fake = FakeLLM("{}")
    rep = Consolidator(stub, fake).run()
    assert rep["n_claims"] == 1
    assert fake.calls == 0


def test_consolidator_held_contradiction_and_cost():
    class PaidLLM:
        def __init__(self):
            self.calls = 0

        def complete(self, prompt, system=None):
            self.calls += 1
            return (
                '{"contradicts": [["A", "B"]], "same": [], "supports": [["B", "A"]]}'
            ), 1.25

    stub = _StubLedger(_rows("A", "B"), open_ids=())  # gate holds E1
    rep = Consolidator(stub, PaidLLM(), actor="checker").run()
    assert rep["contradictions_declared"] == []
    assert rep["contradictions_held"] == ["E1"]
    assert rep["supports_proposed"] == [("B", "A")]
    assert rep["cost_usd"] == 1.25
    ((a, b, actor, auto, signal, _eid),) = stub.declared
    assert (a, b, actor, auto, signal) == (
        "A",
        "B",
        "checker",
        True,
        "llm-consolidation",
    )


def test_consolidator_transitive_same_groups():
    stub = _StubLedger(_rows("A", "B", "C", "D"))
    reply = json.dumps(
        {
            "contradicts": [],
            "same": [["A", "B"], ["B", "C"], ["C", "D"]],
            "supports": [],
        }
    )
    rep = Consolidator(stub, FakeLLM(reply)).run()
    # one group of four, topic named for the smallest id
    assert rep["topics_assigned"] == {c: "prop:A" for c in "ABCD"}
    assert {cid for cid, _t, _a in stub.topics} == set("ABCD")
    assert all(t == "prop:A" for _c, t, _a in stub.topics)


def test_consolidator_singleton_group_is_skipped(monkeypatch):
    # parse_relations can never emit a self-pair, so feed one by
    # patching the module-level parser: the union-find group then
    # has one member and must be skipped, not topic-assigned.
    stub = _StubLedger(_rows("A", "B"))
    monkeypatch.setattr(
        consolidation,
        "parse_relations",
        lambda text: {
            "contradicts": [],
            "same": [("A", "A")],
            "supports": [],
        },
    )
    rep = Consolidator(stub, FakeLLM("ignored")).run()
    assert rep["topics_assigned"] == {}
    assert stub.topics == []


def test_consolidator_real_ledger_end_to_end(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim("The bridge is safe", 0.9)
    b = led.assert_claim("The bridge is unsafe", 0.85)
    reply = json.dumps({"contradicts": [[a, b]], "same": [], "supports": []})
    rep = Consolidator(led, FakeLLM(reply)).run()
    assert len(rep["contradictions_declared"]) == 1
    assert rep["contradictions_held"] == []
    led.close()


# ------------------------------------------------------------------
# lql: tokenizer / token / number helpers
# ------------------------------------------------------------------


def test_token_repr():
    toks = lql._tokenize("CLAIMS 42")
    assert repr(toks[0]) == "<word 'CLAIMS' @0>"
    assert repr(toks[1]) == "<number '42' @7>"
    assert repr(toks[-1]) == "<eof '' @9>"


def test_tokenize_escaped_quote_in_string():
    toks = lql._tokenize("writer = 'o''brien'")
    strings = [t for t in toks if t.kind == "string"]
    assert len(strings) == 1
    assert strings[0].text == "o'brien"


def test_as_number_timestamp_like_token():
    tok = lql._Token("number", "2026-01-15", 0)
    assert lql._as_number(tok) == ("2026-01-15", False)
    tok2 = lql._Token("number", "1.5", 0)
    assert lql._as_number(tok2) == (1.5, True)


def test_compare_all_operators_and_none():
    assert lql._compare(None, "!=", "x") is True
    assert lql._compare(None, "!=", None) is False
    assert lql._compare(None, "=", "x") is False
    assert lql._compare(None, "<", 1) is False
    assert lql._compare(5, "=", 5) is True
    assert lql._compare(5, "!=", 6) is True
    assert lql._compare(5, "<", 6) is True
    assert lql._compare(5, "<=", 5) is True
    assert lql._compare(5, ">", 4) is True
    assert lql._compare(5, ">=", 5) is True


def test_parse_non_string_and_empty():
    for bad in (None, 123, "", "   "):
        with pytest.raises(LQLParseError):
            parse(bad)


# ------------------------------------------------------------------
# lql: parser error / edge paths
# ------------------------------------------------------------------


def test_escaped_quote_value_parses_and_executes(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    led.assert_claim("alpha", 0.9, writer="amy")
    plan = parse("CLAIMS WHERE writer = 'o''brien'")
    assert plan["filter"] == ("cmp", "writer", "=", "o'brien")
    assert led.query("CLAIMS WHERE writer = 'o''brien'") == []
    led.close()


def test_as_of_with_operator_or_missing_timestamp():
    with pytest.raises(LQLParseError, match="timestamp after AS_OF"):
        parse("AS_OF = CLAIMS")
    with pytest.raises(LQLParseError, match="timestamp after AS_OF"):
        parse("AS_OF")


def test_as_of_zulu_timestamp_parses():
    plan = parse("AS_OF 2026-01-15T00:00:00Z CLAIMS")
    assert plan["as_of"] == "2026-01-15T00:00:00Z"
    assert plan["kind"] == "claims"


def test_impact_structural_keyword(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim("alpha", 0.9)
    b = led.assert_claim("beta", 0.4)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    plan = parse(f"IMPACT {a} STRUCTURAL")
    assert plan == {"kind": "impact", "id": a, "mode": "structural", "value": None}
    assert led.query(f"IMPACT {a} STRUCTURAL") == led.impact(a)
    led.close()


def test_impact_propagated_to_non_number():
    with pytest.raises(LQLParseError, match="PROPAGATED TO"):
        parse("IMPACT C1 PROPAGATED TO 2026-01-15")


def test_num_field_with_timestamp_value():
    with pytest.raises(LQLParseError, match="compares numerically"):
        parse("CLAIMS WHERE score > 2026-01-15")


def test_bool_field_rejects_other_words_and_numbers():
    with pytest.raises(LQLParseError, match="true or false"):
        parse("CLAIMS WHERE critical = yes")
    with pytest.raises(LQLParseError, match="true or false"):
        parse("CLAIMS WHERE critical = 1")


def test_str_field_rejects_operator_as_value():
    with pytest.raises(LQLParseError, match="expected a value"):
        parse("CLAIMS WHERE writer = =")


def test_claim_with_quoted_id_rejected():
    with pytest.raises(LQLParseError, match="claim id after CLAIM"):
        parse("CLAIM 'C1'")


# ------------------------------------------------------------------
# lql: execution paths (operators, tier cache, AS_OF variants)
# ------------------------------------------------------------------


def _store(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim("alpha", 0.9, writer="amy", t="2026-01-01T00:00:00+00:00")
    b = led.assert_claim("beta", 0.4, writer="amy", t="2026-01-02T00:00:00+00:00")
    c = led.assert_claim("gamma", 0.7, critical=True, t="2026-01-03T00:00:00+00:00")
    led.register_writer("amy", "owner")
    did = led.record_decision("ship decision", [b], t="2026-01-04T00:00:00+00:00")
    return led, a, b, c, did


def test_not_equal_and_lte_operators(tmp_path):
    led, a, b, c, _did = _store(tmp_path)
    assert {r["claim_id"] for r in led.query("CLAIMS WHERE score <= 0.4")} == {b}
    assert {r["claim_id"] for r in led.query("CLAIMS WHERE score <= 0.7")} == {b, c}
    # writer != 'amy': the writer-less claim matches through the
    # None branch of _compare, amy's claims do not.
    assert {r["claim_id"] for r in led.query("CLAIMS WHERE writer != 'amy'")} == {c}
    assert {r["claim_id"] for r in led.query("CLAIMS WHERE status != 'dead'")} == {
        a,
        b,
        c,
    }
    led.close()


def test_tier_filter_reuses_cached_writer_tier(tmp_path):
    led, a, b, c, _did = _store(tmp_path)
    # two claims share writer 'amy': the second scan row must hit
    # the per-query tier cache rather than re-looking the writer up
    got = led.query("CLAIMS WHERE tier = 'owner'")
    assert {r["claim_id"] for r in got} == {a, b}
    assert led.query("CLAIMS WHERE tier != 'owner'")[0]["claim_id"] == c
    led.close()


def test_filter_view_direct(tmp_path):
    led, a, _b, c, _did = _store(tmp_path)
    cache = {}
    row_a = led.get_claim(a)
    view1 = lql._filter_view(led, row_a, cache)
    assert view1["tier"] == "owner" and "amy" in cache
    view2 = lql._filter_view(led, row_a, cache)  # cache-hit path
    assert view2["tier"] == "owner"
    row_c = led.get_claim(c)
    view3 = lql._filter_view(led, row_c, cache)
    assert view3["tier"] is None  # no writer -> no tier
    assert view3["kind"] == row_c.get("score_kind")
    led.close()


def test_as_of_claim_found_on_later_row_and_missing(tmp_path):
    led, a, b, _c, _did = _store(tmp_path)
    got = led.query(f"AS_OF 2026-01-15T00:00:00+00:00 CLAIM {b}")
    assert got is not None and got["claim_id"] == b  # second row
    missing = led.query("AS_OF 2026-01-15T00:00:00+00:00 CLAIM Cmissing")
    assert missing is None
    led.close()


def test_as_of_claims_and_decisions(tmp_path):
    led, a, b, c, did = _store(tmp_path)
    rows = led.query("AS_OF 2026-01-02T12:00:00+00:00 CLAIMS")
    assert {r["claim_id"] for r in rows} == {a, b}
    decs = led.query("AS_OF 2026-01-15T00:00:00+00:00 DECISIONS")
    assert [d["decision_id"] for d in decs] == [did]
    early = led.query("AS_OF 2026-01-01T00:00:00+00:00 DECISIONS")
    assert early == []
    led.close()


def test_execute_unhandled_plan_kind(monkeypatch):
    monkeypatch.setattr(lql, "parse", lambda text: {"kind": "bogus", "as_of": None})
    with pytest.raises(AssertionError, match="unhandled plan kind"):
        execute(object(), "whatever")


def test_execute_health_and_events_as_of(tmp_path):
    led, _a, _b, _c, _did = _store(tmp_path)
    assert execute(led, "HEALTH") == led.health()
    events = execute(led, "AS_OF 2026-01-02T12:00:00+00:00 EVENTS")
    assert events
    assert all(e["t"] <= "2026-01-02T12:00:00+00:00" for e in events)
    led.close()
