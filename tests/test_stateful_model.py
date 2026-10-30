"""Hypothesis stateful model test (DESIGN-16 stage 2).

Random interleavings of the Python ledger's operations, checked
against an independent model after every step. The model tracks
exactly what the documented semantics make predictable — claim
existence, lifecycle status, a claim's own score at the moment an
operation sets it, decision bases (immutable by design) — and
asserts invariants where propagation makes exact values the
engine's business rather than the model's: every score in [0, 1],
the store verifies, the projection passes SQLite's own integrity
check, and a close/reopen round trip reproduces the model's world
exactly. Derandomized and step-bounded so the PR tier is
deterministic; the nightly tier can raise the bounds.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile

from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from hypothesis.strategies import data, lists, sampled_from

from epistemic_ledger import Ledger


class LedgerModelMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.dir = tempfile.mkdtemp(prefix="stateful-ledger-")
        self.path = os.path.join(self.dir, "store")
        self.led = Ledger(self.path)
        # claim_id -> {"status": str}
        self.claims: dict[str, dict] = {}
        # decision_id -> basis list as recorded
        self.decision_basis: dict[str, list[str]] = {}
        self.supports: set[tuple[str, str]] = set()
        self.counter = 0

    def teardown(self):
        try:
            self.led.close()
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)

    # -- helpers ----------------------------------------------------

    def _live_ids(self) -> list[str]:
        return [c for c, m in self.claims.items() if m["status"] == "active"]

    def _check_claim(self, claim_id: str, score: float | None = None):
        got = self.led.get_claim(claim_id)
        if self.claims[claim_id]["status"] != "active":
            # Every terminal transition (superseded, dead,
            # entered-in-error) closes the claim's live row: the
            # claim leaves the live set entirely — history keeps
            # its final version, get_claim returns None. That
            # absence is the expected shape, and this test is what
            # pinned the semantics down.
            assert got is None, f"terminal claim {claim_id} still live"
            return
        assert got is not None, f"model claim {claim_id} missing from store"
        assert got["status"] == "active"
        assert 0.0 <= got["score"] <= 1.0
        if score is not None:
            assert abs(got["score"] - score) < 1e-9

    # -- rules --------------------------------------------------------

    @rule(prior=data())
    def assert_claim(self, prior):
        p = prior.draw(sampled_from([0.1, 0.3, 0.5, 0.7, 0.9]), label="prior")
        self.counter += 1
        cid = self.led.assert_claim(f"claim {self.counter}", p)
        self.claims[cid] = {"status": "active"}
        self._check_claim(cid, score=p)

    @rule(pick=data(), score=data())
    def manual_score(self, pick, score):
        live = self._live_ids()
        if not live:
            return
        cid = pick.draw(sampled_from(live), label="target")
        s = score.draw(sampled_from([0.05, 0.25, 0.5, 0.75, 0.95]), label="score")
        result = self.led.manual_score(cid, s)
        assert abs(result["new"] - s) < 1e-9
        self._check_claim(cid, score=s)

    @rule(child=data(), parent=data())
    def add_support(self, child, parent):
        live = self._live_ids()
        if len(live) < 2:
            return
        a = child.draw(sampled_from(live), label="child")
        b = parent.draw(sampled_from(live), label="parent")
        if a == b or (a, b) in self.supports:
            return
        self.led.add_support(a, b, "evidential", p_given=0.9, p_given_not=0.2)
        self.supports.add((a, b))
        self._check_claim(a)
        self._check_claim(b)

    @rule(pick=data())
    def supersede(self, pick):
        live = self._live_ids()
        if not live:
            return
        old = pick.draw(sampled_from(live), label="old")
        self.counter += 1
        new_id = self.led.supersede(
            old,
            f"claim {self.counter}",
            0.5,
            reason="model test correction",
            source="stateful model",
        )
        self.claims[old] = {"status": "superseded"}
        self.claims[new_id] = {"status": "active"}
        self._check_claim(old)
        self._check_claim(new_id, score=0.5)

    @rule(pick=data(), status=data())
    def set_status(self, pick, status):
        live = self._live_ids()
        if not live:
            return
        cid = pick.draw(sampled_from(live), label="target")
        s = status.draw(sampled_from(["dead", "entered-in-error"]), label="status")
        self.led.set_claim_status(
            cid, s, reason="model test lifecycle", source="stateful model"
        )
        self.claims[cid] = {"status": s}
        self._check_claim(cid)

    @rule(basis=data())
    def record_decision(self, basis):
        live = self._live_ids()
        if not live:
            return
        chosen = basis.draw(
            lists(sampled_from(live), min_size=1, max_size=3, unique=True),
            label="basis",
        )
        self.counter += 1
        did = self.led.record_decision(f"decision {self.counter}", chosen)
        self.decision_basis[did] = list(chosen)

    @rule()
    def reopen(self):
        self.led.close()
        self.led = Ledger(self.path)
        rows = {row["claim_id"]: row for row in self.led.list_claims()}
        live = {c for c, m in self.claims.items() if m["status"] == "active"}
        assert set(rows) == live
        for cid in live:
            assert rows[cid]["status"] == "active"

    # -- invariants ---------------------------------------------------

    @invariant()
    def store_always_verifies(self):
        report = self.led.verify_store()
        assert report["ok"], report["problems"][:3]

    @invariant()
    def projection_integrity(self):
        db = sqlite3.connect(os.path.join(self.path, "ledger.db"))
        try:
            (result,) = db.execute("PRAGMA integrity_check").fetchone()
        finally:
            db.close()
        assert result == "ok"

    @invariant()
    def decisions_keep_their_basis(self):
        recorded = {d["decision_id"]: d for d in self.led.decisions()}
        assert set(recorded) == set(self.decision_basis)
        for did, basis in self.decision_basis.items():
            assert list(recorded[did]["basis"]) == basis


TestLedgerModel = LedgerModelMachine.TestCase
TestLedgerModel.settings = settings(
    max_examples=8, stateful_step_count=25, deadline=None, derandomize=True
)
