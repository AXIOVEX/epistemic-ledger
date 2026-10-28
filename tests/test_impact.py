"""Impact analysis and decision nodes (DESIGN-13 section 3).

Claim I1: the structural closure returned by ``Ledger.impact``
equals a brute-force closure computed independently from the raw
edge set — exactly, on randomized graphs, including graphs with
diamonds, cycles, and decision nodes.

Claim I2: propagated impact scores equal the scores a real
revision to the same value produces, claim for claim.

Plus the section 3.1 contract: a decision records its basis set at
the moment it is taken, immutably, and governance acts already in
the log surface as decision nodes with the basis sets they name.
"""

import os
import shutil
import tempfile
from collections import deque

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from epistemic_ledger import Ledger
from epistemic_ledger.ledger import jeffrey


def _mk(tmp_path, name="store"):
    return Ledger(os.path.join(str(tmp_path), name))


def _chain(led, n, prior=0.9):
    ids = [led.assert_claim(f"c{i}", prior) for i in range(n)]
    for i in range(1, n):
        led.add_support(ids[i], ids[i - 1], "evidential", p_given=0.9, p_given_not=0.1)
    return ids


# ------------------------------------------------------------------
# decision nodes (section 3.1)
# ------------------------------------------------------------------


def test_record_decision_and_listing(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.8)
    b = led.assert_claim("b", 0.7)
    did = led.record_decision("ship it", [a, b, a], rationale="because")
    assert did.startswith("D")
    ds = led.decisions()
    assert len(ds) == 1
    d = ds[0]
    assert d["decision_id"] == did
    assert d["kind"] == "decision"
    assert d["label"] == "ship it"
    assert d["basis"] == [a, b]  # deduplicated, order preserved
    assert d["rationale"] == "because"
    led.close()


def test_record_decision_rejects_unknown_claim(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.8)
    with pytest.raises(KeyError):
        led.record_decision("bad", [a, "Cdoesnotexist"])
    assert led.decisions() == []
    led.close()


def test_decision_basis_is_immutable(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.8)
    b = led.assert_claim("b", 0.7)
    did = led.record_decision("first", [a])
    led.manual_score(a, 0.2)  # the ground moves under the decision
    led.record_decision("second", [a, b])
    ds = {d["decision_id"]: d for d in led.decisions()}
    assert ds[did]["basis"] == [a]  # the first decision still rests on a alone
    led.close()


def test_governance_act_surfaces_as_decision_node(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.8, entrenchment=0.9)
    b = led.assert_claim("b", 0.7, entrenchment=0.3)
    cid = led.declare_contradiction(a, b)
    out = led.resolve_contradiction(cid)
    assert out["resolved"] is True
    gov = [d for d in led.decisions() if d["kind"] == "governance"]
    assert len(gov) == 1
    g = gov[0]
    assert g["label"] == "contradiction_resolved"
    assert set(g["basis"]) == {a, b}
    # and it is reachable from either claim it rested on
    for root in (a, b):
        nodes = {n["id"]: n for n in led.impact(root)["nodes"]}
        assert g["decision_id"] in nodes
        assert nodes[g["decision_id"]]["kind"] == "decision"
        assert nodes[g["decision_id"]]["distance"] == 1
    led.close()


# ------------------------------------------------------------------
# structural impact (section 3.2)
# ------------------------------------------------------------------


def test_structural_diamond_and_decision(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.9)
    b = led.assert_claim("b", 0.8)
    c = led.assert_claim("c", 0.8)
    d = led.assert_claim("d", 0.5)
    led.add_support(b, a, "evidential", p_given=0.9, p_given_not=0.1)
    led.add_support(c, a, "evidential", p_given=0.9, p_given_not=0.1)
    led.add_support(d, b, "evidential", p_given=0.9, p_given_not=0.1)
    led.add_support(d, c, "evidential", p_given=0.9, p_given_not=0.1)
    did = led.record_decision("built on b", [b])
    res = led.impact(a)
    assert res["truncated"] is False
    nodes = {n["id"]: n for n in res["nodes"]}
    assert set(nodes) == {b, c, d, did}
    assert nodes[b]["distance"] == 1
    assert nodes[c]["distance"] == 1
    assert nodes[d]["distance"] == 2
    assert {tuple(p) for p in nodes[d]["paths"]} == {(a, b, d), (a, c, d)}
    assert nodes[did]["kind"] == "decision"
    assert nodes[did]["distance"] == 2
    assert nodes[did]["paths"] == [[a, b, did]]
    led.close()


def test_impact_unknown_claim_and_bad_mode(tmp_path):
    led = _mk(tmp_path)
    with pytest.raises(KeyError):
        led.impact("Cnope")
    a = led.assert_claim("a", 0.5)
    with pytest.raises(ValueError):
        led.impact(a, mode="sideways")
    led.close()


def test_caps_are_reported_never_silent(tmp_path):
    led = _mk(tmp_path)
    ids = _chain(led, 6)
    res = led.impact(ids[0], max_depth=2)
    assert [n["id"] for n in res["nodes"]] == ids[1:3]
    assert res["truncated"] is True
    assert "max_depth" in res["truncation_reasons"]
    res = led.impact(ids[0], max_results=2)
    assert len(res["nodes"]) == 2
    assert res["truncated"] is True
    assert "max_results" in res["truncation_reasons"]
    res = led.impact(ids[0])
    assert len(res["nodes"]) == 5
    assert res["truncated"] is False
    led.close()


# ------------------------------------------------------------------
# propagated impact (section 3.2)
# ------------------------------------------------------------------


def test_propagated_matches_hand_computed_movement(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.9)
    b = led.assert_claim("b", 0.5)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    n_events = len(led._events())
    res = led.impact(a, mode="propagated", revised_score=0.1)
    moves = {m["claim_id"]: m for m in res["movements"]}
    assert moves[a]["old"] == 0.9 and moves[a]["new"] == 0.1
    assert moves[b]["new"] == pytest.approx(jeffrey(0.5, 0.95, 0.05, 0.1))
    # the dry run changed nothing in the live store
    assert led.get_score(a) == 0.9
    assert led.get_score(b) == 0.5
    assert len(led._events()) == n_events
    led.close()


def test_propagated_default_challenge_and_decisions_affected(tmp_path):
    led = _mk(tmp_path)
    a = led.assert_claim("a", 0.9)
    b = led.assert_claim("b", 0.5)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    did = led.record_decision("resting on b", [b])
    other = led.record_decision("unrelated", [a])
    res = led.impact(a, mode="propagated")  # default: challenged to zero
    assert res["revised_score"] == 0.0
    assert set(res["decisions_affected"]) == {did, other}  # both rest on moved ground
    led.manual_score(a, 0.9)  # no-op revision: nothing moves
    res2 = led.impact(a, mode="propagated", revised_score=0.9)
    assert res2["movements"] == []
    assert res2["decisions_affected"] == []
    led.close()


# ------------------------------------------------------------------
# claim I1: structural closure == brute-force closure
# ------------------------------------------------------------------


def _brute_force(root, edges, decision_bases):
    """Independent closure: BFS over the raw edge set, then decision
    nodes attached to any claim in the closure (root included)."""
    rev = {}
    for dep, sup in edges:
        rev.setdefault(sup, set()).add(dep)
    distance = {root: 0}
    queue = deque([root])
    while queue:
        cur = queue.popleft()
        for dep in rev.get(cur, ()):
            if dep not in distance:
                distance[dep] = distance[cur] + 1
                queue.append(dep)
    nodes = {c: d for c, d in distance.items() if c != root}
    for did, basis in decision_bases.items():
        inside = [c for c in basis if c in distance]
        if inside:
            nodes[did] = min(distance[c] for c in inside) + 1
    # simple paths, enumerated independently
    adj = {c: sorted(rev.get(c, ())) for c in distance}
    for did, basis in decision_bases.items():
        if did in nodes:
            for c in basis:
                if c in distance:
                    adj.setdefault(c, []).append(did)
    paths = {}
    stack = [(root, [root])]
    while stack:
        node, path = stack.pop()
        for nxt in adj.get(node, []):
            if nxt in path:
                continue
            paths.setdefault(nxt, set()).add(tuple(path + [nxt]))
            stack.append((nxt, path + [nxt]))
    return nodes, paths


_graph_strategy = st.fixed_dictionaries(
    {
        "n": st.integers(min_value=2, max_value=8),
        "edge_pairs": st.lists(
            st.tuples(st.integers(0, 7), st.integers(0, 7)),
            min_size=0,
            max_size=14,
        ),
        "bases": st.lists(
            st.lists(st.integers(0, 7), min_size=1, max_size=3, unique=True),
            min_size=0,
            max_size=2,
        ),
        "root": st.integers(0, 7),
    }
)


@settings(max_examples=40, deadline=None)
@given(_graph_strategy)
def test_i1_structural_closure_matches_brute_force(spec):
    n = spec["n"]
    edges = {(d, s) for d, s in spec["edge_pairs"] if d < n and s < n and d != s}
    bases = [[i for i in basis if i < n] for basis in spec["bases"]]
    bases = [b for b in bases if b]
    root_i = spec["root"] % n
    tmp = tempfile.mkdtemp(prefix="epistemic-ledger-i1-")
    try:
        led = Ledger(os.path.join(tmp, "store"))
        ids = [led.assert_claim(f"s{i}", 0.5) for i in range(n)]
        for dep, sup in sorted(edges):
            led.add_support(
                ids[dep], ids[sup], "evidential", p_given=0.9, p_given_not=0.2
            )
        dec_bases = {}
        for j, basis in enumerate(bases):
            did = led.record_decision(f"d{j}", [ids[i] for i in basis])
            dec_bases[did] = [ids[i] for i in basis]
        res = led.impact(ids[root_i], max_results=100000)
        led.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert res["truncated"] is False
    got = {node["id"]: node for node in res["nodes"]}
    want_dist, want_paths = _brute_force(
        ids[root_i], {(ids[d], ids[s]) for d, s in edges}, dec_bases
    )
    assert set(got) == set(want_dist)
    for nid, dist in want_dist.items():
        assert got[nid]["distance"] == dist
        assert {tuple(p) for p in got[nid]["paths"]} == want_paths.get(nid, set())


# ------------------------------------------------------------------
# claim I2: dry run == real revision, claim for claim
# ------------------------------------------------------------------


@settings(max_examples=20, deadline=None)
@given(
    n=st.integers(min_value=2, max_value=7),
    edge_pairs=st.lists(
        st.tuples(st.integers(0, 6), st.integers(0, 6)), min_size=1, max_size=10
    ),
    priors=st.lists(st.floats(min_value=0.1, max_value=0.9), min_size=7, max_size=7),
    root=st.integers(0, 6),
    target=st.floats(min_value=0.0, max_value=1.0),
)
def test_i2_propagated_equals_real_revision(n, edge_pairs, priors, root, target):
    edges = {(d, s) for d, s in edge_pairs if d < n and s < n and d != s}
    root_i = root % n
    tmp = tempfile.mkdtemp(prefix="epistemic-ledger-i2-")
    try:
        src = os.path.join(tmp, "store")
        led = Ledger(src)
        ids = [led.assert_claim(f"s{i}", priors[i]) for i in range(n)]
        for dep, sup in sorted(edges):
            led.add_support(
                ids[dep], ids[sup], "evidential", p_given=0.9, p_given_not=0.15
            )
        before = led._all_live_scores()
        n_events = len(led._events())
        res = led.impact(ids[root_i], mode="propagated", revised_score=target)
        # the dry run left the live store untouched
        assert led._all_live_scores() == before
        assert len(led._events()) == n_events
        led.close()
        # the real revision, on a separate copy of the same store
        real_dir = os.path.join(tmp, "real")
        shutil.copytree(src, real_dir)
        real = Ledger(real_dir)
        real.manual_score(ids[root_i], target)
        after = real._all_live_scores()
        real.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    moves = {m["claim_id"]: m["new"] for m in res["movements"]}
    for cid, score in after.items():
        if cid in moves:
            assert moves[cid] == score
        else:
            assert before[cid] == score  # unmoved claims really unmoved
    assert set(moves) == {c for c in after if after[c] != before[c]}
