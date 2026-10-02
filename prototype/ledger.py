"""
Living Epistemic Ledger — v0.1 prototype.

Implements Design Memo 01 (docs/DESIGN-01-record-schema-scoring.md):
  - Append-only JSONL event log (write model, ground truth).
  - SQLite bitemporal claim table + bitemporal support edges (read model).
  - Single credences, Jeffrey conditionalization for uncertain evidence.
  - Support-edge revisit loop with early cutoff + materiality flags.
  - Queries: BELIEVED_AT / CHANGED / DEPENDS_ON / WHY.
  - The five kill criteria instrumented from day one.

Stdlib only. No distributed anything.
"""

import json
import sqlite3
import uuid
from collections import deque
from datetime import datetime, timezone

SUPPORT_KINDS = ("deductive", "evidential", "llm-generated", "human-asserted")

# Entrenchment tiers (manual in v0.2; learned tiers deferred to v0.3).
ENTRENCHMENT_TIERS = {
    "axiomatic": 1.0,    # definitional; loses only to another 1.0 (-> human)
    "measured": 0.75,    # directly observed / instrumented
    "inferred": 0.5,     # default for derived conclusions
    "provisional": 0.25, # LLM-generated or single weak source
    "deprecated": 0.0,   # superseded soon; loses every tie-break
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims(
  claim_id    TEXT NOT NULL,
  txn_from    TEXT NOT NULL,
  txn_to      TEXT,
  statement   TEXT NOT NULL,
  valid_from  TEXT,
  valid_to    TEXT,
  score       REAL NOT NULL,
  score_kind  TEXT NOT NULL DEFAULT 'credence',
  status      TEXT NOT NULL DEFAULT 'active',
  materiality REAL NOT NULL DEFAULT 0.05,
  critical    INTEGER NOT NULL DEFAULT 0,
  entrenchment REAL NOT NULL DEFAULT 0.5,
  PRIMARY KEY (claim_id, txn_from)
);
CREATE TABLE IF NOT EXISTS support_edges(
  claim_id    TEXT NOT NULL,
  supports_id TEXT NOT NULL,
  kind        TEXT NOT NULL,
  p_given     REAL NOT NULL,
  p_given_not REAL NOT NULL,
  txn_from    TEXT NOT NULL,
  txn_to      TEXT,
  PRIMARY KEY (claim_id, supports_id, txn_from)
);
CREATE TABLE IF NOT EXISTS outcomes(
  claim_id TEXT PRIMARY KEY,
  outcome  INTEGER NOT NULL,
  t        TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def jeffrey(prior, p_h_given_e, p_h_given_not_e, p_e_new):
    """Probability kinematics: move the credence partway toward the
    conditional on E and partway toward the conditional on ~E,
    weighted by the new credence in E itself."""
    return p_h_given_e * p_e_new + p_h_given_not_e * (1.0 - p_e_new)


class Ledger:
    def __init__(self, path):
        """path: directory holding events.jsonl and ledger.db (created if missing)."""
        import os
        os.makedirs(path, exist_ok=True)
        self.path = path
        self.log_path = os.path.join(path, "events.jsonl")
        self.db = sqlite3.connect(os.path.join(path, "ledger.db"))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------------
    # events (write model)
    # ------------------------------------------------------------------
    def _emit(self, etype, payload, actor="system", t=None):
        t = t or _now()
        event = {
            "event_id": _new_id("E"),
            "t": t,
            "actor": actor,
            "type": etype,
            "payload": payload,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def _events(self):
        try:
            with open(self.log_path, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []

    # ------------------------------------------------------------------
    # claims (read model)
    # ------------------------------------------------------------------
    def _live_claim(self, claim_id):
        return self.db.execute(
            "SELECT * FROM claims WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,),
        ).fetchone()

    def _close_claim_version(self, claim_id, t):
        self.db.execute(
            "UPDATE claims SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, claim_id),
        )

    def assert_claim(self, statement, prior, valid_from=None, valid_to=None,
                     score_kind="credence", materiality=0.05, critical=False,
                     entrenchment=0.5, actor="system", t=None):
        """Enter a new conclusion. Returns claim_id."""
        t = t or _now()
        claim_id = _new_id("C")
        self.db.execute(
            """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                                  valid_to, score, score_kind, status,
                                  materiality, critical, entrenchment)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (claim_id, t, statement, valid_from, valid_to, float(prior),
             score_kind, float(materiality), int(critical), float(entrenchment)),
        )
        self.db.commit()
        self._emit("assert", {"claim_id": claim_id, "statement": statement,
                              "prior": float(prior)}, actor=actor, t=t)
        return claim_id

    def _new_version(self, claim_id, score, entrenchment, t):
        """Bitemporal versioning: close the old row, open a new one."""
        row = self._live_claim(claim_id)
        if row is None:
            raise KeyError(f"unknown claim {claim_id}")
        old_score, old_entr = float(row["score"]), float(row["entrenchment"])
        self._close_claim_version(claim_id, t)
        self.db.execute(
            """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                                  valid_to, score, score_kind, status,
                                  materiality, critical, entrenchment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim_id, t, row["statement"], row["valid_from"], row["valid_to"],
             float(score), row["score_kind"], row["status"],
             row["materiality"], row["critical"], float(entrenchment)),
        )
        self.db.commit()
        return old_score, old_entr

    def _set_score(self, claim_id, new_score, triggering_event_id, actor="system", t=None):
        """Bitemporal score update: close the old version, open a new one."""
        t = t or _now()
        row = self._live_claim(claim_id)
        entrenchment = float(row["entrenchment"]) if row else 0.5
        old, _ = self._new_version(claim_id, new_score, entrenchment, t)
        self._emit("score_revision",
                   {"claim_id": claim_id, "old_score": old,
                    "new_score": float(new_score),
                    "triggering_event_id": triggering_event_id},
                   actor=actor, t=t)
        return old, float(new_score)

    def set_entrenchment(self, claim_id, value, actor="human", t=None):
        """Manual entrenchment assignment (v0.2). Versioned bitemporally;
        score untouched. Emits entrenchment_set."""
        t = t or _now()
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError("entrenchment must be in [0, 1]")
        row = self._live_claim(claim_id)
        if row is None:
            raise KeyError(f"unknown claim {claim_id}")
        _, old_entr = self._new_version(claim_id, float(row["score"]), value, t)
        self._emit("entrenchment_set",
                   {"claim_id": claim_id, "old": old_entr, "new": value},
                   actor=actor, t=t)
        return old_entr, value

    def apply_tier(self, claim_id, tier, actor="human", t=None):
        """Assign a named entrenchment tier (see ENTRENCHMENT_TIERS)."""
        if tier not in ENTRENCHMENT_TIERS:
            raise KeyError(f"unknown tier {tier!r}; choose from {sorted(ENTRENCHMENT_TIERS)}")
        return self.set_entrenchment(claim_id, ENTRENCHMENT_TIERS[tier],
                                     actor=actor, t=t)

    def manual_score(self, claim_id, score, actor="human", t=None):
        """A human hand-sets a score. Counts toward the override-rate metric."""
        t = t or _now()
        old, new = self._set_score(claim_id, score, None, actor=actor, t=t)
        return {"claim_id": claim_id, "old": old, "new": new}

    def supersede(self, old_claim_id, statement, prior, actor="system", t=None):
        """Correction: close the old claim's transaction-time interval, open a new claim."""
        t = t or _now()
        old = self._live_claim(old_claim_id)
        if old is None:
            raise KeyError(f"unknown claim {old_claim_id}")
        self._close_claim_version(old_claim_id, t)
        self.db.execute(
            "UPDATE claims SET status = 'superseded' WHERE claim_id = ? AND txn_from = ?",
            (old_claim_id, old["txn_from"]),
        )
        new_id = self.assert_claim(statement, prior, actor=actor, t=t,
                                   materiality=old["materiality"],
                                   critical=bool(old["critical"]),
                                   entrenchment=old["entrenchment"])
        self.db.commit()
        self._emit("supersede", {"old_claim_id": old_claim_id,
                                 "new_claim_id": new_id}, actor=actor, t=t)
        return new_id

    # ------------------------------------------------------------------
    # support edges
    # ------------------------------------------------------------------
    def add_support(self, claim_id, supports_id, kind,
                    p_given=1.0, p_given_not=0.0, actor="system", t=None):
        """Record why claim_id is held. p_given = P(claim | support),
        p_given_not = P(claim | ~support): the likelihoods used by the
        revisit loop's Jeffrey updates."""
        if kind not in SUPPORT_KINDS:
            raise ValueError(f"kind must be one of {SUPPORT_KINDS}")
        t = t or _now()
        if self._live_claim(claim_id) is None or self._live_claim(supports_id) is None:
            raise KeyError("both claims must exist")
        self.db.execute(
            """INSERT INTO support_edges(claim_id, supports_id, kind,
                                         p_given, p_given_not, txn_from)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (claim_id, supports_id, kind, float(p_given),
             float(p_given_not), t),
        )
        self.db.commit()
        self._emit("support", {"claim_id": claim_id, "supports_id": supports_id,
                               "kind": kind, "p_given": float(p_given),
                               "p_given_not": float(p_given_not)},
                   actor=actor, t=t)

    def retract_support(self, claim_id, supports_id, actor="system", t=None):
        t = t or _now()
        cur = self.db.execute(
            """UPDATE support_edges SET txn_to = ?
               WHERE claim_id = ? AND supports_id = ? AND txn_to IS NULL""",
            (t, claim_id, supports_id),
        )
        if cur.rowcount == 0:
            raise KeyError("no live support edge to retract")
        self.db.commit()
        self._emit("retract_support",
                   {"claim_id": claim_id, "supports_id": supports_id},
                   actor=actor, t=t)

    def _live_edges(self, claim_id):
        # ORDER BY txn_from, rowid: deterministic, causal (attachment) order.
        # Sequential Jeffrey is order-dependent, so the application order
        # must not depend on random uuid assignment. (Found by the v0.1
        # stress harness: without this, identical evidence gave different
        # scores across runs.)
        return self.db.execute(
            """SELECT * FROM support_edges
               WHERE claim_id = ? AND txn_to IS NULL
               ORDER BY txn_from, rowid""",
            (claim_id,),
        ).fetchall()

    def _reverse_edges(self, supports_id):
        return self.db.execute(
            """SELECT * FROM support_edges
               WHERE supports_id = ? AND txn_to IS NULL
               ORDER BY rowid""",
            (supports_id,),
        ).fetchall()

    # ------------------------------------------------------------------
    # revisit loop
    # ------------------------------------------------------------------
    def _dependents_bfs(self, fact_id):
        """Claims depending on fact_id (transitively), supporters first."""
        seen = {fact_id}
        order = []
        queue = deque([fact_id])
        while queue:
            cur = queue.popleft()
            for e in self._reverse_edges(cur):
                cid = e["claim_id"]
                if cid not in seen:
                    seen.add(cid)
                    order.append(cid)
                    queue.append(cid)
        return order

    def ingest_evidence(self, statement, credence, actor="system", t=None,
                        epsilon=0.005):
        """New fact arrives: assert it, then propagate Jeffrey updates through
        the support closure with early cutoff. Returns the revisit report."""
        t = t or _now()
        fact_id = self.assert_claim(statement, prior=credence, actor=actor, t=t,
                                    entrenchment=1.0)
        return self._revisit(fact_id, {fact_id: float(credence)},
                             actor=actor, t=t, epsilon=epsilon)

    def _revisit(self, fact_id, new_scores, actor="system", t=None, epsilon=0.005):
        t = t or _now()
        order = self._dependents_bfs(fact_id)
        updated = dict(new_scores)  # claim_id -> new score this pass
        report = {"fact_id": fact_id, "t": t, "updates": [], "flags": [],
                  "closure_size": len(order), "cutoff_skipped": 0}
        for cid in order:
            row = self._live_claim(cid)
            if row is None:
                continue
            score = float(row["score"])
            # Naive-sequential Jeffrey: apply each updated supporter in turn.
            # (Known v0.1 simplification — documented, not hidden.)
            for e in self._live_edges(cid):
                if e["supports_id"] in updated:
                    score = jeffrey(score, float(e["p_given"]),
                                    float(e["p_given_not"]),
                                    updated[e["supports_id"]])
            delta = score - float(row["score"])
            if abs(delta) < epsilon:
                report["cutoff_skipped"] += 1
                continue  # early cutoff: treat as unchanged, don't propagate
            old, new = self._set_score(cid, score, fact_id, actor=actor, t=t)
            updated[cid] = new
            entry = {"claim_id": cid, "old": old, "new": new, "delta": new - old}
            report["updates"].append(entry)
            # Materiality layer: flag unless below threshold and not critical.
            if abs(new - old) >= float(row["materiality"]) or row["critical"]:
                report["flags"].append(entry)
        report["n_revisited"] = len(report["updates"])
        self._emit("revisit", {"fact_id": fact_id,
                               "closure_size": report["closure_size"],
                               "n_revisited": report["n_revisited"],
                               "n_cutoff": report["cutoff_skipped"],
                               "n_flags": len(report["flags"])},
                   actor=actor, t=t)
        return report

    # ------------------------------------------------------------------
    # contradiction resolution (Design Memo 02)
    # ------------------------------------------------------------------
    def declare_contradiction(self, claim_a, claim_b, p_loser_given_winner=0.05,
                              actor="human", t=None):
        """Two active claims cannot both hold. Records the incompatibility;
        resolution is separate (resolve_contradiction). The cross-likelihood
        P(loser | winner) is elicited here; P(loser | ~winner) defaults to
        the loser's current score at resolve time."""
        t = t or _now()
        for c in (claim_a, claim_b):
            if self._live_claim(c) is None:
                raise KeyError(f"unknown claim {c}")
        ev = self._emit("contradiction",
                        {"claim_a": claim_a, "claim_b": claim_b,
                         "p_loser_given_winner": float(p_loser_given_winner)},
                        actor=actor, t=t)
        return ev["event_id"]

    def open_contradictions(self):
        """Declared contradictions minus resolved ones (event-sourced)."""
        evs = self._events()
        resolved = {e["payload"]["contradiction_id"] for e in evs
                    if e["type"] == "contradiction_resolved"}
        return [e for e in evs
                if e["type"] == "contradiction"
                and e["event_id"] not in resolved]

    def resolve_contradiction(self, contradiction_id, actor="system", t=None,
                              epsilon=0.005):
        """Entrenchment-ordered contraction. The less-entrenched claim is
        revised down via Jeffrey against the winner's score, then its
        dependents are re-propagated. Ties go to a human."""
        t = t or _now()
        if all(e["event_id"] != contradiction_id
               for e in self.open_contradictions()):
            return {"resolved": True, "already": True,
                    "contradiction_id": contradiction_id}
        ce = next(e for e in self._events()
                  if e["event_id"] == contradiction_id)
        a, b = ce["payload"]["claim_a"], ce["payload"]["claim_b"]
        ra, rb = self._live_claim(a), self._live_claim(b)
        if ra is None or rb is None:
            self._emit("contradiction_unresolved",
                       {"contradiction_id": contradiction_id,
                        "reason": "claim no longer live"},
                       actor=actor, t=t)
            return {"resolved": False, "reason": "claim not live",
                    "contradiction_id": contradiction_id}
        ea, eb = float(ra["entrenchment"]), float(rb["entrenchment"])
        if abs(ea - eb) < 1e-9:
            self._emit("contradiction_unresolved",
                       {"contradiction_id": contradiction_id,
                        "reason": "entrenchment tie", "entrenchment": ea},
                       actor=actor, t=t)
            return {"resolved": False, "reason": "tie",
                    "contradiction_id": contradiction_id}
        loser, winner = (a, b) if ea < eb else (b, a)
        rl, rw = self._live_claim(loser), self._live_claim(winner)
        sl, sw = float(rl["score"]), float(rw["score"])
        p_lw = float(ce["payload"]["p_loser_given_winner"])
        # P(loser | ~winner) = loser's current score: the winner's falsity
        # tells us nothing new about the loser.
        new_l = jeffrey(sl, p_lw, sl, sw)
        self._set_score(loser, new_l, contradiction_id, actor=actor, t=t)
        self._emit("contract",
                   {"contradiction_id": contradiction_id,
                    "loser": loser, "winner": winner,
                    "old": sl, "new": new_l,
                    "loser_entrenchment": min(ea, eb),
                    "winner_entrenchment": max(ea, eb)},
                   actor=actor, t=t)
        self._emit("contradiction_resolved",
                   {"contradiction_id": contradiction_id,
                    "loser": loser, "winner": winner},
                   actor=actor, t=t)
        rep = self._revisit(loser, {loser: new_l}, actor=actor, t=t,
                            epsilon=epsilon)
        return {"resolved": True, "loser": loser, "winner": winner,
                "old": sl, "new": new_l,
                "contradiction_id": contradiction_id, "revisit": rep}

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def believed_at(self, t):
        """What did we believe at transaction time T?"""
        return [dict(r) for r in self.db.execute(
            """SELECT * FROM claims
               WHERE txn_from <= ? AND (txn_to IS NULL OR txn_to > ?)
               ORDER BY txn_from, claim_id""",
            (t, t))]

    def changed(self, t1, t2):
        """What changed between T1 and T2? (event-log filter)"""
        return [e for e in self._events() if t1 <= e["t"] < t2]

    def depends_on(self, fact_id):
        """Full revisit closure of a fact: every claim depending on it."""
        return self._dependents_bfs(fact_id)

    def why(self, claim_id):
        """The claim's live support set with scores and kinds. The audit view."""
        out = []
        for e in self._live_edges(claim_id):
            s = self._live_claim(e["supports_id"])
            out.append({
                "supports_id": e["supports_id"],
                "statement": s["statement"] if s else None,
                "score": float(s["score"]) if s else None,
                "kind": e["kind"],
                "p_given": float(e["p_given"]),
                "p_given_not": float(e["p_given_not"]),
            })
        return out

    # ------------------------------------------------------------------
    # kill-criteria instrumentation
    # ------------------------------------------------------------------
    def record_outcome(self, claim_id, outcome, t=None):
        """Record that a claim resolved true/false. Feeds the Brier score."""
        t = t or _now()
        self.db.execute(
            "INSERT OR REPLACE INTO outcomes(claim_id, outcome, t) VALUES (?, ?, ?)",
            (claim_id, int(bool(outcome)), t))
        self.db.commit()
        self._emit("outcome", {"claim_id": claim_id,
                               "outcome": bool(outcome)}, t=t)

    def kill_metrics(self):
        """The five kill criteria, instrumented. Bars are guesses in v0.1."""
        events = self._events()
        revs = [e for e in events if e["type"] == "revisit"]
        score_revs = [e for e in events if e["type"] == "score_revision"]

        # 1. missed triggers: revisit log is the audit surface (held-out
        #    audit judges recall later; here we expose the raw decisions).
        trigger_log = [e["payload"] for e in revs]

        # 2. churn: sign changes of score deltas over each claim's history.
        by_claim = {}
        for e in score_revs:
            p = e["payload"]
            by_claim.setdefault(p["claim_id"], []).append(
                (e["t"], p["new_score"] - p["old_score"]))
        churn = {}
        for cid, hist in by_claim.items():
            hist.sort()
            deltas = [d for _, d in hist[-10:] if abs(d) > 1e-9]
            signs = [1 if d > 0 else -1 for d in deltas]
            churn[cid] = sum(1 for a, b in zip(signs, signs[1:]) if a != b)

        # 3. support-graph blowup: transitive support fan-out per claim.
        live = [r["claim_id"] for r in self.db.execute(
            "SELECT claim_id FROM claims WHERE txn_to IS NULL")]
        fanouts = []
        for cid in live:
            seen, q = set(), deque([cid])
            while q:
                cur = q.popleft()
                for e in self._live_edges(cur):
                    if e["supports_id"] not in seen:
                        seen.add(e["supports_id"])
                        q.append(e["supports_id"])
            fanouts.append(len(seen))
        fanout = {"n_claims": len(live),
                  "avg": sum(fanouts) / len(fanouts) if fanouts else 0.0,
                  "max": max(fanouts) if fanouts else 0}

        # 4. miscalibration: Brier score over resolved claims.
        resolved = self.db.execute(
            """SELECT c.score, o.outcome FROM outcomes o
               JOIN claims c ON c.claim_id = o.claim_id AND c.txn_to IS NULL"""
        ).fetchall()
        brier = (sum((r["score"] - r["outcome"]) ** 2 for r in resolved)
                 / len(resolved)) if resolved else None

        # 5. override rate: human score_revisions without a triggering event.
        manual = [e for e in score_revs
                  if e["actor"] == "human"
                  and not e["payload"].get("triggering_event_id")]
        override_rate = (len(manual) / len(score_revs)) if score_revs else None

        return {
            "trigger_log": trigger_log,
            "churn": churn,
            "fanout": fanout,
            "brier": brier,
            "override_rate": override_rate,
            "n_score_revisions": len(score_revs),
            "n_manual_overrides": len(manual),
            "n_open_contradictions": len(self.open_contradictions()),
        }
