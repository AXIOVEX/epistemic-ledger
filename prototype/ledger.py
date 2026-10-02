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
  writer      TEXT,
  PRIMARY KEY (claim_id, txn_from)
);
CREATE TABLE IF NOT EXISTS support_edges(
  claim_id    TEXT NOT NULL,
  supports_id TEXT NOT NULL,
  kind        TEXT NOT NULL,
  p_given     REAL NOT NULL,
  p_given_not REAL NOT NULL,
  strength    REAL NOT NULL DEFAULT 1.0,
  txn_from    TEXT NOT NULL,
  txn_to      TEXT,
  PRIMARY KEY (claim_id, supports_id, txn_from)
);
CREATE TABLE IF NOT EXISTS outcomes(
  claim_id TEXT NOT NULL,
  outcome  INTEGER NOT NULL,
  t        TEXT NOT NULL,
  PRIMARY KEY (claim_id, t)
);
CREATE TABLE IF NOT EXISTS claim_intervals(
  claim_id     TEXT NOT NULL,
  txn_from     TEXT NOT NULL,
  txn_to       TEXT,
  belief       REAL NOT NULL,
  plausibility REAL NOT NULL,
  PRIMARY KEY (claim_id, txn_from)
);
CREATE TABLE IF NOT EXISTS claim_combos(
  claim_id TEXT NOT NULL,
  txn_from TEXT NOT NULL,
  txn_to   TEXT,
  combo    TEXT NOT NULL,
  leak     REAL NOT NULL DEFAULT 0.0,
  PRIMARY KEY (claim_id, txn_from)
);
CREATE TABLE IF NOT EXISTS writers(
  writer_id TEXT NOT NULL,
  txn_from  TEXT NOT NULL,
  txn_to    TEXT,
  tier      TEXT NOT NULL,
  PRIMARY KEY (writer_id, txn_from)
);
CREATE TABLE IF NOT EXISTS policies(
  name        TEXT NOT NULL,
  txn_from    TEXT NOT NULL,
  txn_to      TEXT,
  description TEXT NOT NULL,
  version     INTEGER NOT NULL,
  PRIMARY KEY (name, txn_from)
);
"""

COMBO_KINDS = ("noisy-and", "noisy-or")

# Governance (Design Memo 06): writer trust tiers -> default entrenchment.
WRITER_TIERS = ("owner", "contributor", "provisional")
TIER_ENTRENCHMENT = {"owner": 0.75, "contributor": 0.5, "provisional": 0.25}
DEFAULT_POLICY = ("challenge-axiom-requires-owner",
                  "Contradiction declarations against axiomatic "
                  "(entrenchment 1.0) claims by non-owner writers are held "
                  "for owner review.")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def jeffrey(prior, p_h_given_e, p_h_given_not_e, p_e_new):
    """Probability kinematics: move the credence partway toward the
    conditional on E and partway toward the conditional on ~E,
    weighted by the new credence in E itself."""
    return p_h_given_e * p_e_new + p_h_given_not_e * (1.0 - p_e_new)


def dempster_combine(m1, m2):
    """Dempster's rule over general mass functions (Design Memo 04's
    deferred n-ary extension).

    m1, m2: dicts {frozenset(frame elements): mass}; masses must sum to 1.
    Returns (combined, K): the combined mass dict and the conflict mass K.
    Raises ValueError on total conflict (K == 1). Binary intervals are the
    special case frame {'T', 'F'} — see interval_to_mass."""
    for m in (m1, m2):
        if abs(sum(m.values()) - 1.0) > 1e-9:
            raise ValueError("masses must sum to 1")
    combined, K = {}, 0.0
    for s1, a in m1.items():
        for s2, b in m2.items():
            inter = s1 & s2
            if not inter:
                K += a * b
            else:
                combined[inter] = combined.get(inter, 0.0) + a * b
    if K >= 1.0 - 1e-12:
        raise ValueError(f"total conflict K={K:.4f}")
    n = 1.0 - K
    return {s: v / n for s, v in combined.items()}, K


def interval_to_mass(belief, plausibility):
    """Binary [Bel, Pl] as a mass function over {'T', 'F'}."""
    if not 0.0 <= belief <= plausibility <= 1.0:
        raise ValueError("need 0 <= belief <= plausibility <= 1")
    return {frozenset({"T"}): belief,
            frozenset({"F"}): 1.0 - plausibility,
            frozenset({"T", "F"}): plausibility - belief}


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
        # strength column on support_edges (added in v0.4; backfill old DBs)
        cols = [r["name"] for r in
                self.db.execute("PRAGMA table_info(support_edges)")]
        if "strength" not in cols:
            self.db.execute(
                "ALTER TABLE support_edges ADD COLUMN strength REAL NOT NULL DEFAULT 1.0")
        # writer column on claims (added in v0.6; backfill old DBs)
        cols = [r["name"] for r in
                self.db.execute("PRAGMA table_info(claims)")]
        if "writer" not in cols:
            self.db.execute("ALTER TABLE claims ADD COLUMN writer TEXT")
        self.db.commit()
        # default governance policy lives in the store (Design Memo 06)
        name, desc = DEFAULT_POLICY
        if self.audit_policy(name) is None:
            self.register_policy(name, desc, version=1, actor="system")

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
                     entrenchment=None, writer=None, actor="system", t=None):
        """Enter a new conclusion. Returns claim_id.

        entrenchment=None resolves via the writer's trust tier (Design
        Memo 06): owner 0.75, contributor 0.5, provisional 0.25, unregistered
        writer 0.25, no writer 0.5. Explicit entrenchment always overrides."""
        t = t or _now()
        if entrenchment is None:
            if writer is None:
                entrenchment = 0.5
            else:
                entrenchment = TIER_ENTRENCHMENT.get(
                    self.get_writer(writer), 0.25)
        claim_id = _new_id("C")
        if isinstance(entrenchment, str):
            entrenchment = ENTRENCHMENT_TIERS[entrenchment]
        self.db.execute(
            """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                                  valid_to, score, score_kind, status,
                                  materiality, critical, entrenchment, writer)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (claim_id, t, statement, valid_from, valid_to, float(prior),
             score_kind, float(materiality), int(critical),
             float(entrenchment), writer),
        )
        self.db.commit()
        self._emit("assert", {"claim_id": claim_id, "statement": statement,
                              "prior": float(prior), "writer": writer},
                   actor=actor, t=t)
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
                                  materiality, critical, entrenchment, writer)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim_id, t, row["statement"], row["valid_from"], row["valid_to"],
             float(score), row["score_kind"], row["status"],
             row["materiality"], row["critical"], float(entrenchment),
             row["writer"] if "writer" in row.keys() else None),
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

    def learn_entrenchment(self, min_outcomes=3, actor="system", t=None):
        """Offline learning pass (v0.3): derive entrenchment from calibration.

        For claims with >= min_outcomes recorded outcomes, entrenchment =
        1 - Brier, where each outcome is scored against the claim version
        live at the outcome's time. Claims without enough outcomes keep
        their manual tier: no data, no learning. Emits entrenchment_set
        with learned=true.

        v0.6 adds the stability path (Design Memo 03's deferred item): for
        claims with >= 5 revisions but < min_outcomes outcomes, entrenchment
        decays with churn — sign_changes/revisions, capped at 0.5. A claim
        that flip-flops across 0.5 every revision is not entrenched, even
        if nothing has falsified it yet. Decay only; stability never
        *raises* entrenchment (basis="stability" in the event)."""
        t = t or _now()
        rows = self.db.execute(
            """SELECT o.claim_id, o.outcome,
                      (SELECT c.score FROM claims c
                       WHERE c.claim_id = o.claim_id
                         AND c.txn_from <= o.t
                         AND (c.txn_to IS NULL OR c.txn_to > o.t)
                       ORDER BY c.txn_from DESC LIMIT 1) AS score_at
               FROM outcomes o""").fetchall()
        by_claim = {}
        for r in rows:
            if r["score_at"] is not None:
                by_claim.setdefault(r["claim_id"], []).append(
                    (float(r["score_at"]), int(r["outcome"])))
        report = []
        brier_done = set()
        for cid, hist in by_claim.items():
            if len(hist) < min_outcomes:
                continue
            brier = sum((s - o) ** 2 for s, o in hist) / len(hist)
            new_e = max(0.0, min(1.0, 1.0 - brier))
            live = self._live_claim(cid)
            if live is None:
                continue
            old_e = float(live["entrenchment"])
            brier_done.add(cid)
            if abs(new_e - old_e) < 1e-9:
                continue
            self._new_version(cid, float(live["score"]), new_e, t)
            self._emit("entrenchment_set",
                       {"claim_id": cid, "old": old_e, "new": new_e,
                        "learned": True, "basis": "brier",
                        "brier": round(brier, 4),
                        "n_outcomes": len(hist)},
                       actor=actor, t=t)
            report.append({"claim_id": cid, "old": old_e, "new": new_e,
                           "brier": brier, "n": len(hist)})
        # stability path: churn without outcomes
        vers = self.db.execute(
            """SELECT claim_id, score FROM claims
               ORDER BY claim_id, txn_from""").fetchall()
        by_cid = {}
        for r in vers:
            by_cid.setdefault(r["claim_id"], []).append(float(r["score"]))
        for cid, scores in by_cid.items():
            if cid in brier_done:
                continue  # Brier-learned this pass; stability is for the
            # unresolved (fewer than min_outcomes outcomes, if any)
            if len(scores) < 5:
                continue
            sides = [s > 0.5 for s in scores]
            flips = sum(1 for a, b in zip(sides, sides[1:]) if a != b)
            decay = min(0.5, flips / len(scores))
            if decay <= 0:
                continue
            live = self._live_claim(cid)
            if live is None:
                continue
            old_e = float(live["entrenchment"])
            new_e = old_e * (1.0 - decay)
            if old_e - new_e < 1e-9:
                continue
            self._new_version(cid, float(live["score"]), new_e, t)
            self._emit("entrenchment_set",
                       {"claim_id": cid, "old": old_e, "new": new_e,
                        "learned": True, "basis": "stability",
                        "revisions": len(scores), "flips": flips},
                       actor=actor, t=t)
            report.append({"claim_id": cid, "old": old_e, "new": new_e,
                           "basis": "stability", "flips": flips,
                           "revisions": len(scores)})
        return report

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
                    p_given=1.0, p_given_not=0.0, strength=1.0,
                    actor="system", t=None):
        """Record why claim_id is held. p_given = P(claim | support),
        p_given_not = P(claim | ~support): the likelihoods used by the
        revisit loop's Jeffrey updates. strength in [0,1] weights the
        parent in noisy-and/or combination (default 1)."""
        if kind not in SUPPORT_KINDS:
            raise ValueError(f"kind must be one of {SUPPORT_KINDS}")
        strength = float(strength)
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must be in [0, 1]")
        t = t or _now()
        if self._live_claim(claim_id) is None or self._live_claim(supports_id) is None:
            raise KeyError("both claims must exist")
        self.db.execute(
            """INSERT INTO support_edges(claim_id, supports_id, kind,
                                         p_given, p_given_not, strength, txn_from)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (claim_id, supports_id, kind, float(p_given),
             float(p_given_not), strength, t),
        )
        self.db.commit()
        self._emit("support", {"claim_id": claim_id, "supports_id": supports_id,
                               "kind": kind, "p_given": float(p_given),
                               "p_given_not": float(p_given_not),
                               "strength": strength},
                   actor=actor, t=t)

    # ------------------------------------------------------------------
    # joint likelihoods (Design Memo 05)
    # ------------------------------------------------------------------
    def set_combo(self, claim_id, combo, leak=0.0, strengths=None,
                  actor="system", t=None):
        """Give a claim a joint combination function over its parents'
        scores, replacing per-edge sequential Jeffrey for that node.
        combo in {'noisy-and', 'noisy-or'}; leak in [0,1]; strengths maps
        supports_id -> [0,1] (default 1.0). Bitemporal."""
        if combo not in COMBO_KINDS:
            raise ValueError(f"combo must be one of {COMBO_KINDS}")
        leak = float(leak)
        if not 0.0 <= leak <= 1.0:
            raise ValueError("leak must be in [0, 1]")
        if self._live_claim(claim_id) is None:
            raise KeyError(f"unknown claim {claim_id}")
        strengths = {k: float(v) for k, v in (strengths or {}).items()}
        for v in strengths.values():
            if not 0.0 <= v <= 1.0:
                raise ValueError("strengths must be in [0, 1]")
        t = t or _now()
        self.db.execute(
            "UPDATE claim_combos SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, claim_id))
        self.db.execute(
            "INSERT INTO claim_combos(claim_id, txn_from, combo, leak)"
            " VALUES (?, ?, ?, ?)", (claim_id, t, combo, leak))
        for pid, s in strengths.items():
            self.db.execute(
                """UPDATE support_edges SET strength = ?
                   WHERE claim_id = ? AND supports_id = ? AND txn_to IS NULL""",
                (s, claim_id, pid))
        self.db.commit()
        self._emit("combo_set",
                   {"claim_id": claim_id, "combo": combo, "leak": leak,
                    "strengths": strengths},
                   actor=actor, t=t)

    def get_combo(self, claim_id):
        r = self.db.execute(
            "SELECT combo, leak FROM claim_combos"
            " WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,)).fetchone()
        if r is None:
            return None
        strengths = {e["supports_id"]: float(e["strength"])
                     for e in self._live_edges(claim_id)}
        return r["combo"], float(r["leak"]), strengths

    @staticmethod
    def _combine_score(combo, leak, parent_scores):
        """parent_scores: {supports_id: (strength, score)}. Order-free."""
        if not parent_scores:
            return None
        if combo == "noisy-and":
            prod = 1.0
            for s, p in parent_scores.values():
                prod *= s * p + (1.0 - s)
            return leak + (1.0 - leak) * prod
        prod = 1.0
        for s, p in parent_scores.values():
            prod *= 1.0 - s * p
        return 1.0 - (1.0 - leak) * prod

    # ------------------------------------------------------------------
    # governance (Design Memo 06, Quipu-informed)
    # ------------------------------------------------------------------
    def register_writer(self, writer_id, tier, actor="system", t=None):
        """Register (or re-tier) a writer. Tiers are bitemporal."""
        if tier not in WRITER_TIERS:
            raise ValueError(f"tier must be one of {WRITER_TIERS}")
        t = t or _now()
        self.db.execute(
            "UPDATE writers SET txn_to = ? WHERE writer_id = ? AND txn_to IS NULL",
            (t, writer_id))
        self.db.execute(
            "INSERT INTO writers(writer_id, txn_from, tier) VALUES (?, ?, ?)",
            (writer_id, t, tier))
        self.db.commit()
        self._emit("writer_registered",
                   {"writer_id": writer_id, "tier": tier}, actor=actor, t=t)

    def get_writer(self, writer_id):
        """Live trust tier of a writer, or None if unregistered."""
        r = self.db.execute(
            "SELECT tier FROM writers WHERE writer_id = ? AND txn_to IS NULL",
            (writer_id,)).fetchone()
        return r["tier"] if r else None

    def get_entrenchment(self, claim_id):
        """Live entrenchment of a claim (float)."""
        row = self._live_claim(claim_id)
        if row is None:
            raise KeyError(f"unknown claim {claim_id}")
        return float(row["entrenchment"])

    def get_score(self, claim_id):
        """Live score of a claim (float)."""
        row = self._live_claim(claim_id)
        if row is None:
            raise KeyError(f"unknown claim {claim_id}")
        return float(row["score"])

    def register_policy(self, name, description, version=1, actor="system",
                        t=None):
        """Policies are facts in the store they govern (Quipu GS5)."""
        t = t or _now()
        live = self.audit_policy(name)
        if live is not None and live["version"] == version:
            return  # idempotent
        self.db.execute(
            "UPDATE policies SET txn_to = ? WHERE name = ? AND txn_to IS NULL",
            (t, name))
        self.db.execute(
            "INSERT INTO policies(name, txn_from, description, version)"
            " VALUES (?, ?, ?, ?)", (name, t, description, version))
        self.db.commit()
        self._emit("policy_registered",
                   {"name": name, "version": version}, actor=actor, t=t)

    def audit_policy(self, name, t=None):
        """The rule in force at T (Quipu GS6: bitemporal rules)."""
        t = t or _now()
        r = self.db.execute(
            "SELECT name, description, version, txn_from FROM policies"
            " WHERE name = ? AND txn_from <= ?"
            "   AND (txn_to IS NULL OR txn_to > ?)"
            " ORDER BY txn_from DESC LIMIT 1",
            (name, t, t)).fetchone()
        return dict(r) if r else None

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
            combo = self.get_combo(cid)
            if combo is not None:
                # Joint likelihood: recompute from all parents' scores
                # (updated value if the parent changed this pass, else live).
                # Products commute -> order-independent, unlike sequential
                # Jeffrey (Design Memo 05).
                name, leak, strengths = combo
                edges = self._live_edges(cid)
                if not edges or not any(e["supports_id"] in updated
                                        for e in edges):
                    report["cutoff_skipped"] += 1
                    continue
                parent_scores = {}
                for e in edges:
                    pid = e["supports_id"]
                    if pid in updated:
                        p = updated[pid]
                    else:
                        prow = self._live_claim(pid)
                        if prow is None:
                            continue
                        p = float(prow["score"])
                    parent_scores[pid] = (strengths.get(pid, 1.0), p)
                if not parent_scores:
                    continue
                score = self._combine_score(name, leak, parent_scores)
            else:
                score = float(row["score"])
                # Naive-sequential Jeffrey: apply each updated supporter in turn.
                # (Known simplification — documented, not hidden.)
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
                              actor="human", writer=None, auto=False,
                              signal=None, t=None):
        """Two active claims cannot both hold. Records the incompatibility;
        resolution is separate (resolve_contradiction). The cross-likelihood
        P(loser | winner) is elicited here; P(loser | ~winner) defaults to
        the loser's current score at resolve time.

        Governance gate (Design Memo 06): a non-owner writer declaring
        against an axiomatic (entrenchment 1.0) claim has the declaration
        HELD for owner review — it does not enter the open queue. The hold
        is a permanent verdict event (contradiction_held)."""
        t = t or _now()
        for c in (claim_a, claim_b):
            if self._live_claim(c) is None:
                raise KeyError(f"unknown claim {c}")
        tier = self.get_writer(writer) if writer else None
        axiomatic = any(float(self._live_claim(c)["entrenchment"]) >= 1.0
                        for c in (claim_a, claim_b))
        if axiomatic and tier != "owner":
            ev = self._emit(
                "contradiction_held",
                {"policy": DEFAULT_POLICY[0], "claim_a": claim_a,
                 "claim_b": claim_b, "writer": writer, "tier": tier,
                 "outcome": "held",
                 "remediation": "owner must declare_contradiction to proceed"},
                actor=actor, t=t)
            return ev["event_id"]
        ev = self._emit("contradiction",
                        {"claim_a": claim_a, "claim_b": claim_b,
                         "p_loser_given_winner": float(p_loser_given_winner),
                         "writer": writer, "auto": bool(auto),
                         "signal": signal},
                        actor=actor, t=t)
        return ev["event_id"]

    def held_contradictions(self):
        """Held declarations minus pairs an owner has since declared."""
        evs = self._events()
        open_pairs = {(e["payload"]["claim_a"], e["payload"]["claim_b"])
                      for e in evs if e["type"] == "contradiction"}
        return [e for e in evs
                if e["type"] == "contradiction_held"
                and (e["payload"]["claim_a"], e["payload"]["claim_b"])
                not in open_pairs]

    @staticmethod
    def _interval_conflict(b1, p1, b2, p2):
        """Pairwise Dempster conflict K between two binary intervals."""
        _, K = dempster_combine(interval_to_mass(b1, p1),
                                interval_to_mass(b2, p2))
        return K

    def _ancestors(self, claim_id, _memo=None):
        _memo = _memo if _memo is not None else {}
        if claim_id in _memo:
            return _memo[claim_id]
        out = set()
        for e in self._live_edges(claim_id):
            pid = e["supports_id"]
            out.add(pid)
            out |= self._ancestors(pid, _memo)
        _memo[claim_id] = out
        return out

    def detect_contradictions(self, min_opposition=0.7, conflict_k=0.7,
                              actor="system", t=None, topic_of=None):
        """Automatic contradiction detection (the piece Design Memo 02
        deferred). Two signals:

        1. score opposition — both claims decided and on opposite sides
           (|sa - sb| >= min_opposition, opposite signs around 0.5), and
           sharing a *common ancestor* (sibling/cousin opposition under the
           same lineage). Direct parent-child opposition is NOT flagged:
           the edge likelihoods already explain it, and the revisit loop
           owns that relationship. Bare disagreement between unrelated
           claims is not a contradiction either.
        2. interval conflict — both claims carry D-S intervals and their
           pairwise Dempster conflict K >= conflict_k. PRECISION NOTE:
           without proposition identity this flags ANY opposed decided
           pair, including unrelated propositions (measured in
           docs/NEWSROOM-01.md). Pass topic_of (claim_id -> hashable
           topic) to require same-topic pairs; in a real deployment the
           topics come from the caller's NL pipeline.

        Candidates auto-declare through the normal declare_contradiction
        path (auto=True, signal recorded); the governance gate still
        applies. Explicit and on-demand: NOT run inside the revisit loop
        (O(n^2) pairs; no surprise queue entries). Returns declared ids.
        """
        t = t or _now()
        rows = self.db.execute(
            "SELECT claim_id, score FROM claims WHERE txn_to IS NULL"
        ).fetchall()
        scores = {r["claim_id"]: float(r["score"]) for r in rows}
        ids = sorted(scores)
        memo = {}
        anc = {cid: self._ancestors(cid, memo) for cid in ids}

        evs = self._events()
        by_id = {}
        for e in evs:
            if e["type"] in ("contradiction", "contradiction_held"):
                pl = e["payload"]
                by_id[e["event_id"]] = frozenset(
                    (pl["claim_a"], pl["claim_b"]))
        seen = set(by_id.values())
        for e in evs:
            if e["type"] == "contradiction_resolved":
                pair = by_id.get(e["payload"]["contradiction_id"])
                if pair:
                    seen.add(pair)

        declared = []
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if frozenset((a, b)) in seen:
                    continue
                sa, sb = scores[a], scores[b]
                opposed = ((sa - 0.5) * (sb - 0.5) < 0
                           and abs(sa - sb) >= min_opposition)
                shares = bool(anc[a] & anc[b])
                signal = None
                if opposed and shares:
                    signal = "score-opposition"
                else:
                    ia, ib = self.get_interval(a), self.get_interval(b)
                    if ia is not None and ib is not None:
                        if topic_of is not None:
                            ta, tb = topic_of(a), topic_of(b)
                            if ta is None or tb is None or ta != tb:
                                continue
                        k = self._interval_conflict(ia[0], ia[1],
                                                    ib[0], ib[1])
                        if k >= conflict_k:
                            signal = f"interval-conflict:K={k:.2f}"
                if signal is None:
                    continue
                cid = self.declare_contradiction(
                    a, b, actor=actor, auto=True, signal=signal, t=t)
                declared.append(cid)
                seen.add(frozenset((a, b)))
        return declared

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
        if any(e["event_id"] == contradiction_id
               for e in self.held_contradictions()):
            return {"resolved": False, "held": True,
                    "contradiction_id": contradiction_id,
                    "hint": "held for owner review; an owner must "
                            "declare_contradiction to proceed"}
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
    # Dempster-Shafer intervals (v0.3, opt-in — see DESIGN-04)
    # ------------------------------------------------------------------
    def set_interval(self, claim_id, belief, plausibility, actor="system", t=None):
        """Attach a [Bel, Pl] ignorance interval to a claim. Bitemporal."""
        b, p = float(belief), float(plausibility)
        if not (0.0 <= b <= p <= 1.0):
            raise ValueError("need 0 <= belief <= plausibility <= 1")
        if self._live_claim(claim_id) is None:
            raise KeyError(f"unknown claim {claim_id}")
        t = t or _now()
        self.db.execute(
            "UPDATE claim_intervals SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, claim_id))
        self.db.execute(
            "INSERT INTO claim_intervals(claim_id, txn_from, belief, plausibility)"
            " VALUES (?, ?, ?, ?)", (claim_id, t, b, p))
        self.db.commit()
        self._emit("interval_set",
                   {"claim_id": claim_id, "belief": b, "plausibility": p},
                   actor=actor, t=t)

    def get_interval(self, claim_id):
        r = self.db.execute(
            "SELECT belief, plausibility FROM claim_intervals"
            " WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,)).fetchone()
        return (float(r["belief"]), float(r["plausibility"])) if r else None

    def ignorance(self, claim_id):
        """Pl - Bel: how much the ledger explicitly doesn't know."""
        iv = self.get_interval(claim_id)
        return iv[1] - iv[0] if iv else None

    def combine_interval(self, claim_id, m_h, m_nh, m_ig, actor="system", t=None):
        """Dempster-combine the claim's current interval (as a mass function)
        with new evidence (m_h, m_nh, m_ig; must sum to 1). Refuses on
        pathological conflict (K >= 0.99) — the rule misbehaves there, so
        the ledger says so instead of producing nonsense. Implemented on
        the general dempster_combine (n-ary frames); the binary case is
        just frame {'T', 'F'}."""
        cur = self.get_interval(claim_id)
        if cur is None:
            raise KeyError("no interval set; call set_interval first")
        if abs((m_h + m_nh + m_ig) - 1.0) > 1e-9:
            raise ValueError("masses must sum to 1")
        b, p = cur
        t = t or _now()
        new_ev = {frozenset({"T"}): m_h, frozenset({"F"}): m_nh,
                  frozenset({"T", "F"}): m_ig}
        try:
            combined, K = dempster_combine(interval_to_mass(b, p), new_ev)
        except ValueError:
            K = 1.0
            combined = None
        if K >= 0.99 or combined is None:
            self._emit("interval_refused",
                       {"claim_id": claim_id, "conflict": K},
                       actor=actor, t=t)
            return {"combined": False, "conflict": K}
        c_h = combined.get(frozenset({"T"}), 0.0)
        c_nh = combined.get(frozenset({"F"}), 0.0)
        new_b, new_p = c_h, 1.0 - c_nh
        self.set_interval(claim_id, new_b, new_p, actor=actor, t=t)
        self._emit("interval_combined",
                   {"claim_id": claim_id, "belief": new_b,
                    "plausibility": new_p, "conflict": K},
                   actor=actor, t=t)
        return {"combined": True, "belief": new_b,
                "plausibility": new_p, "conflict": K}

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
        """Record that a claim resolved true/false. Feeds the Brier score.
        Multiple outcomes per claim are kept (one row per event time)."""
        t = t or _now()
        self.db.execute(
            "INSERT INTO outcomes(claim_id, outcome, t) VALUES (?, ?, ?)",
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

        # 4. miscalibration: Brier score over resolved claims, each scored
        #    against the claim version live at the outcome's time.
        resolved = self.db.execute(
            """SELECT o.outcome,
                      (SELECT c.score FROM claims c
                       WHERE c.claim_id = o.claim_id
                         AND c.txn_from <= o.t
                         AND (c.txn_to IS NULL OR c.txn_to > o.t)
                       ORDER BY c.txn_from DESC LIMIT 1) AS score_at
               FROM outcomes o"""
        ).fetchall()
        scored = [(r["score_at"], r["outcome"]) for r in resolved
                  if r["score_at"] is not None]
        brier = (sum((s - o) ** 2 for s, o in scored) / len(scored)
                 if scored else None)

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

    # Kill-criterion bars (v0.6). Calibrated on synthetic workloads —
    # TRIGGER-STRESS-01 (eps 0.005: recall 0.96, precision 0.715, mean
    # flags 17.1, max 52) and the context experiments — not guesses, but
    # not real-data bars either. Re-tune on real workloads. Bars marked
    # provisional were set without a measurement behind them.
    KILL_BARS = {
        "trigger_recall": 0.90,      # held-out audit; measured 0.96
        "trigger_precision": 0.60,   # held-out audit; measured 0.715
        "mean_flags": 25.0,          # measured 17.1
        "max_flags": 60.0,           # measured max 52 (hub facts)
        "max_churn": 8,              # provisional; was 4 (no data) -> 8 =
                                    # max observed healthy tracking in
                                    # NEWSROOM-01. NOTE: churn-as-defined
                                    # (sign changes / 10 revs) conflates
                                    # healthy tracking of conflicting
                                    # evidence with loop instability; needs
                                    # a conflict-normalized metric.
        "max_fanout": 100,           # provisional: transitive support size
        "brier": 0.25,               # worse than chance = dead
        "override_rate": 0.20,       # humans override >20% = loop untrusted
        "n_open_contradictions": 10,  # provisional: unresolved pile-up
    }

    def check_kill_bars(self, trigger_recall=None, trigger_precision=None):
        """Compare live kill metrics against KILL_BARS. trigger_recall /
        precision need a held-out audit (TRIGGER-STRESS-01) — pass them in
        when measured; otherwise those two bars are skipped, not assumed.
        Returns values, bars, breached list, and ok."""
        m = self.kill_metrics()
        flags = [p.get("n_flags", 0) for p in m["trigger_log"]]
        values = {
            "trigger_recall": trigger_recall,
            "trigger_precision": trigger_precision,
            "mean_flags": (sum(flags) / len(flags)) if flags else 0.0,
            "max_flags": max(flags) if flags else 0,
            "max_churn": max(m["churn"].values()) if m["churn"] else 0,
            "max_fanout": m["fanout"]["max"],
            "brier": m["brier"],
            "override_rate": m["override_rate"],
            "n_open_contradictions": m["n_open_contradictions"],
        }
        lower_is_better = {"trigger_recall", "trigger_precision"}
        breached = []
        for name, bar in self.KILL_BARS.items():
            v = values[name]
            if v is None:
                continue  # no data: skip, don't assume
            bad = v < bar if name in lower_is_better else v > bar
            if bad:
                breached.append({"criterion": name, "value": v, "bar": bar})
        return {"values": values, "bars": dict(self.KILL_BARS),
                "breached": breached, "ok": not breached}
