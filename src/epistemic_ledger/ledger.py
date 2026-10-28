"""
Living Epistemic Ledger — core module.

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
import os
import shutil
import sqlite3
import tempfile
import uuid

try:
    import fcntl
except ImportError:  # non-Unix: writer lock unenforced (DESIGN-12)
    fcntl = None  # type: ignore[assignment]

from collections import deque
from datetime import datetime, timezone

from . import ed25519

SUPPORT_KINDS = ("deductive", "evidential", "llm-generated", "human-asserted")

# Claim lifecycle statuses. History is never deleted: a claim leaves
# 'active' by a status change that is itself an event in the log.
# 'superseded' is set by supersede(); 'entered-in-error' and 'dead'
# are set by set_claim_status(). Both paths require a reason bundle.
CLAIM_STATUSES = ("active", "superseded", "entered-in-error", "dead")
TERMINAL_STATUSES = ("superseded", "entered-in-error", "dead")

# Entrenchment tiers (manual in v0.2; learned tiers deferred to v0.3).
ENTRENCHMENT_TIERS = {
    "axiomatic": 1.0,  # definitional; loses only to another 1.0 (-> human)
    "measured": 0.75,  # directly observed / instrumented
    "inferred": 0.5,  # default for derived conclusions
    "provisional": 0.25,  # LLM-generated or single weak source
    "deprecated": 0.0,  # superseded soon; loses every tie-break
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
  pubkey    TEXT,
  PRIMARY KEY (writer_id, txn_from)
);
CREATE TABLE IF NOT EXISTS policies(
  name        TEXT NOT NULL,
  txn_from    TEXT NOT NULL,
  txn_to      TEXT,
  description TEXT NOT NULL,
  version     INTEGER NOT NULL,
  rule        TEXT,
  PRIMARY KEY (name, txn_from)
);
CREATE TABLE IF NOT EXISTS graphs(
  name        TEXT NOT NULL,
  txn_from    TEXT NOT NULL,
  txn_to      TEXT,
  ceiling     REAL NOT NULL,
  PRIMARY KEY (name, txn_from)
);
CREATE TABLE IF NOT EXISTS claim_graphs(
  claim_id TEXT NOT NULL,
  txn_from TEXT NOT NULL,
  txn_to   TEXT,
  graph    TEXT NOT NULL,
  PRIMARY KEY (claim_id, txn_from)
);
CREATE TABLE IF NOT EXISTS claim_topics(
  claim_id TEXT NOT NULL,
  txn_from TEXT NOT NULL,
  txn_to   TEXT,
  topic    TEXT NOT NULL,
  PRIMARY KEY (claim_id, txn_from)
);
"""

COMBO_KINDS = ("noisy-and", "noisy-or")

# Governance (Design Memo 06): writer trust tiers -> default entrenchment.
WRITER_TIERS = ("owner", "contributor", "provisional")
TIER_ENTRENCHMENT = {"owner": 0.75, "contributor": 0.5, "provisional": 0.25}
DEFAULT_POLICY = (
    "challenge-axiom-requires-owner",
    "Contradiction declarations against axiomatic "
    "(entrenchment 1.0) claims by non-owner writers are held "
    "for owner review.",
)
# The default policy as data (Design Memo 11): the gate semantics,
# spelled out in the predicate language and stored in the policies
# table at version 2. Legacy rows without a rule fall back to this.
DEFAULT_POLICY_RULE = {
    "action": "declare_contradiction",
    "effect": "hold",
    "when": {
        "all": [
            {"field": "target_entrenchment", "op": ">=", "value": 1.0},
            {"field": "writer_tier", "op": "!=", "value": "owner"},
        ]
    },
}
# Partitions (Design Memo 11): unassigned claims live here, ceiling 1.
DEFAULT_GRAPH = "public"
GATED_ACTIONS = (
    "declare_contradiction",
    "resolve_contradiction",
    "escalate_contradiction",
)
PREDICATE_OPS = ("==", "!=", "<", "<=", ">", ">=", "in", "not_in")


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
    combined: dict = {}
    K = 0.0
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
    return {
        frozenset({"T"}): belief,
        frozenset({"F"}): 1.0 - plausibility,
        frozenset({"T", "F"}): plausibility - belief,
    }


def _validate_pred(pred):
    """Structural validation for the predicate language (Memo 11)."""
    if not isinstance(pred, dict):
        raise ValueError("predicate must be a dict")
    keys = set(pred)
    if keys == {"field", "op", "value"}:
        if pred["op"] not in PREDICATE_OPS:
            raise ValueError(f"unknown predicate op {pred['op']!r}")
        if not isinstance(pred["field"], str):
            raise ValueError("predicate field must be a string")
        return
    if keys in ({"all"}, {"any"}):
        subs = pred[next(iter(keys))]
        if not isinstance(subs, list) or not subs:
            raise ValueError("all/any need a non-empty list")
        for s in subs:
            _validate_pred(s)
        return
    if keys == {"not"}:
        _validate_pred(pred["not"])
        return
    raise ValueError(f"malformed predicate: {sorted(keys)}")


def _validate_rule(rule):
    if not isinstance(rule, dict) or set(rule) != {"action", "effect", "when"}:
        raise ValueError("rule must be {action, effect, when}")
    if rule["action"] not in GATED_ACTIONS:
        raise ValueError(f"rule action must be one of {GATED_ACTIONS}")
    if rule["effect"] not in ("hold", "deny"):
        raise ValueError("rule effect must be 'hold' or 'deny'")
    if rule["effect"] == "hold" and rule["action"] != "declare_contradiction":
        raise ValueError("'hold' requires a verdict queue: declare_contradiction only")
    _validate_pred(rule["when"])


def _eval_pred(pred, ctx):
    """Evaluate a validated predicate over a post-state context.
    A missing field makes a leaf false (fail-closed for gates)."""
    if "field" in pred:
        if pred["field"] not in ctx:
            return False
        v, op, want = ctx[pred["field"]], pred["op"], pred["value"]
        try:
            if op == "==":
                return v == want
            if op == "!=":
                return v != want
            if op == "<":
                return v < want
            if op == "<=":
                return v <= want
            if op == ">":
                return v > want
            if op == ">=":
                return v >= want
            if op == "in":
                return v in want
            if op == "not_in":
                return v not in want
        except TypeError:
            return False
        return False
    if "all" in pred:
        return all(_eval_pred(s, ctx) for s in pred["all"])
    if "any" in pred:
        return any(_eval_pred(s, ctx) for s in pred["any"])
    return not _eval_pred(pred["not"], ctx)


# ----------------------------------------------------------------------
# projection rebuild (v0.13, DESIGN-13 section 7): the log is ground
# truth and ledger.db is a fold of it. _fold_event applies one
# event's projection effect — the same mutations its write method
# performed, minus the emission. Event types whose state is derived
# from the log at read time (decisions, contradictions, verdicts)
# and pure record events fold as no-ops. An event type the fold
# does not know stops the rebuild loudly: a partial or approximate
# projection is worse than none.
# ----------------------------------------------------------------------

_FOLD_NOOP_TYPES = frozenset(
    {
        "revisit",
        "policy_denied",
        "interval_refused",
        "interval_combined",  # its set_interval emitted interval_set
        "contradiction",
        "contradiction_held",
        "contradiction_dismissed",
        "contradiction_resolved",
        "contradiction_unresolved",
        "contract",  # the score change rides its score_revision
        "decision",
    }
)


def _fold_live_row(db, table, where, params):
    return db.execute(
        f"SELECT rowid, * FROM {table} WHERE {where} AND txn_to IS NULL", params
    ).fetchone()


def _fold_claim_version(db, claim_id, t, score=None, entrenchment=None, status=None):
    row = _fold_live_row(db, "claims", "claim_id = ?", (claim_id,))
    if row is None:
        raise ValueError(f"rebuild: event for unknown claim {claim_id}")
    db.execute("UPDATE claims SET txn_to = ? WHERE rowid = ?", (t, row["rowid"]))
    if status is not None:
        db.execute(
            "UPDATE claims SET status = ? WHERE rowid = ?", (status, row["rowid"])
        )
        return
    db.execute(
        """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                              valid_to, score, score_kind, status,
                              materiality, critical, entrenchment, writer)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            claim_id,
            t,
            row["statement"],
            row["valid_from"],
            row["valid_to"],
            float(row["score"] if score is None else score),
            row["score_kind"],
            row["status"],
            row["materiality"],
            row["critical"],
            float(row["entrenchment"] if entrenchment is None else entrenchment),
            row["writer"],
        ),
    )


def _fold_event(db, event):
    etype = event["type"]
    p = event["payload"]
    t = event["t"]
    if etype in _FOLD_NOOP_TYPES:
        return
    if etype == "assert":
        if "entrenchment" in p:
            entrenchment = float(p["entrenchment"])
        elif p.get("writer") is None:
            entrenchment = 0.5
        else:
            wrow = _fold_live_row(db, "writers", "writer_id = ?", (p["writer"],))
            tier = wrow["tier"] if wrow is not None else None
            entrenchment = (
                TIER_ENTRENCHMENT.get(tier, 0.25) if tier is not None else 0.25
            )
        db.execute(
            """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                                  valid_to, score, score_kind, status,
                                  materiality, critical, entrenchment, writer)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (
                p["claim_id"],
                t,
                p["statement"],
                p.get("valid_from"),
                p.get("valid_to"),
                float(p["prior"]),
                p.get("score_kind", "credence"),
                float(p.get("materiality", 0.05)),
                int(bool(p.get("critical", False))),
                entrenchment,
                p.get("writer"),
            ),
        )
        return
    if etype == "score_revision":
        _fold_claim_version(db, p["claim_id"], t, score=float(p["new_score"]))
        return
    if etype == "entrenchment_set":
        _fold_claim_version(db, p["claim_id"], t, entrenchment=float(p["new"]))
        return
    if etype == "supersede":
        _fold_claim_version(db, p["old_claim_id"], t, status="superseded")
        return
    if etype == "claim_status_changed":
        _fold_claim_version(db, p["claim_id"], t, status=p["status"])
        return
    if etype == "support":
        db.execute(
            """INSERT INTO support_edges(claim_id, supports_id, kind,
                                         p_given, p_given_not, strength, txn_from)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                p["claim_id"],
                p["supports_id"],
                p["kind"],
                float(p["p_given"]),
                float(p["p_given_not"]),
                float(p["strength"]),
                t,
            ),
        )
        return
    if etype == "retract_support":
        db.execute(
            """UPDATE support_edges SET txn_to = ?
               WHERE claim_id = ? AND supports_id = ? AND txn_to IS NULL""",
            (t, p["claim_id"], p["supports_id"]),
        )
        return
    if etype == "combo_set":
        db.execute(
            "UPDATE claim_combos SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, p["claim_id"]),
        )
        db.execute(
            "INSERT INTO claim_combos(claim_id, txn_from, combo, leak)"
            " VALUES (?, ?, ?, ?)",
            (p["claim_id"], t, p["combo"], float(p["leak"])),
        )
        for pid, s in (p.get("strengths") or {}).items():
            db.execute(
                """UPDATE support_edges SET strength = ?
                   WHERE claim_id = ? AND supports_id = ? AND txn_to IS NULL""",
                (float(s), p["claim_id"], pid),
            )
        return
    if etype == "writer_registered":
        db.execute(
            "UPDATE writers SET txn_to = ? WHERE writer_id = ? AND txn_to IS NULL",
            (t, p["writer_id"]),
        )
        db.execute(
            "INSERT INTO writers(writer_id, txn_from, tier, pubkey)"
            " VALUES (?, ?, ?, ?)",
            (p["writer_id"], t, p["tier"], p.get("pubkey")),
        )
        return
    if etype == "policy_registered":
        db.execute(
            "UPDATE policies SET txn_to = ? WHERE name = ? AND txn_to IS NULL",
            (t, p["name"]),
        )
        description = p.get("description")
        rule = p.get("rule")
        if p["name"] == DEFAULT_POLICY[0]:
            if description is None:
                description = DEFAULT_POLICY[1]
            if rule is None:
                rule = DEFAULT_POLICY_RULE
        db.execute(
            "INSERT INTO policies(name, txn_from, description, version, rule)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                p["name"],
                t,
                description,
                p["version"],
                json.dumps(rule) if rule is not None else None,
            ),
        )
        return
    if etype == "graph_registered":
        db.execute(
            "UPDATE graphs SET txn_to = ? WHERE name = ? AND txn_to IS NULL",
            (t, p["graph"]),
        )
        db.execute(
            "INSERT INTO graphs(name, txn_from, ceiling) VALUES (?, ?, ?)",
            (p["graph"], t, float(p["ceiling"])),
        )
        return
    if etype == "graph_assigned":
        db.execute(
            "UPDATE claim_graphs SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, p["claim_id"]),
        )
        db.execute(
            "INSERT INTO claim_graphs(claim_id, txn_from, graph) VALUES (?, ?, ?)",
            (p["claim_id"], t, p["graph"]),
        )
        return
    if etype == "topic_assigned":
        db.execute(
            "UPDATE claim_topics SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, p["claim_id"]),
        )
        db.execute(
            "INSERT INTO claim_topics(claim_id, txn_from, topic) VALUES (?, ?, ?)",
            (p["claim_id"], t, p["topic"]),
        )
        return
    if etype == "interval_set":
        db.execute(
            "UPDATE claim_intervals SET txn_to = ?"
            " WHERE claim_id = ? AND txn_to IS NULL",
            (t, p["claim_id"]),
        )
        db.execute(
            "INSERT INTO claim_intervals(claim_id, txn_from, belief, plausibility)"
            " VALUES (?, ?, ?, ?)",
            (p["claim_id"], t, float(p["belief"]), float(p["plausibility"])),
        )
        return
    if etype == "outcome":
        db.execute(
            "INSERT INTO outcomes(claim_id, outcome, t) VALUES (?, ?, ?)",
            (p["claim_id"], int(bool(p["outcome"])), t),
        )
        return
    raise ValueError(
        f"rebuild: unsupported event type {etype!r} "
        f"(event {event.get('event_id')}); refusing to approximate"
    )


class Ledger:
    def __init__(self, path):
        """path: directory holding events.jsonl and ledger.db (created if missing).

        Single-writer (v0.11, DESIGN-12): opening a ledger takes an
        exclusive advisory lock on <path>/ledger.lock, held for the
        object's lifetime; a second opener fails loudly instead of
        interleaving appends. close() releases it; process exit
        releases it automatically. Unix-only (fcntl)."""
        os.makedirs(path, exist_ok=True)
        self.path = path
        self.log_path = os.path.join(path, "events.jsonl")
        self._lock_file = None
        if fcntl is not None:
            lf = open(os.path.join(path, "ledger.lock"), "a+")
            try:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lf.close()
                raise RuntimeError(
                    f"ledger at {path} is already open by another "
                    "writer (single-writer store; DESIGN-12)"
                ) from None
            self._lock_file = lf
        self.db = sqlite3.connect(os.path.join(path, "ledger.db"))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._ensure_columns(self.db)
        self.db.commit()
        # default governance policy lives in the store (Design Memo 06);
        # v0.10 registers its rule as data at version 2 (Memo 11)
        name, desc = DEFAULT_POLICY
        live = self.audit_policy(name)
        if live is None or live["version"] < 2:
            self.register_policy(
                name, desc, version=2, actor="system", rule=DEFAULT_POLICY_RULE
            )

    @staticmethod
    def _ensure_columns(db):
        """Backfill columns added after the first schema (strength
        in v0.4, writer in v0.6, pubkey in v0.9, rule in v0.10) so
        fresh and historical databases converge on one shape."""
        cols = [r["name"] for r in db.execute("PRAGMA table_info(support_edges)")]
        if "strength" not in cols:
            db.execute(
                "ALTER TABLE support_edges ADD COLUMN strength REAL NOT NULL DEFAULT 1.0"
            )
        cols = [r["name"] for r in db.execute("PRAGMA table_info(claims)")]
        if "writer" not in cols:
            db.execute("ALTER TABLE claims ADD COLUMN writer TEXT")
        cols = [r["name"] for r in db.execute("PRAGMA table_info(writers)")]
        if "pubkey" not in cols:
            db.execute("ALTER TABLE writers ADD COLUMN pubkey TEXT")
        cols = [r["name"] for r in db.execute("PRAGMA table_info(policies)")]
        if "rule" not in cols:
            db.execute("ALTER TABLE policies ADD COLUMN rule TEXT")

    @classmethod
    def rebuild_projection(cls, path):
        """Rebuild ledger.db from events.jsonl — the recovery path
        for a deleted or corrupted projection (DESIGN-13 section
        7). The store must not be open elsewhere.

        The log is folded event by event into a fresh database,
        which then replaces ledger.db and is verified end to end
        (verify_store). If verification fails and a previous
        projection existed, the original file is restored and the
        failure raised; a fold that meets an event type it does
        not know refuses outright rather than approximating.

        Exactness: events recorded since 0.13 carry every field
        the projection holds, so the rebuild is exact. For older
        logs, assert-time claim metadata the old events never
        recorded (validity window, score kind, materiality,
        critical flag, explicit entrenchment) falls back to the
        documented defaults and tier derivation — scores, edges,
        versions, and verification are exact for every era.
        """
        log_path = os.path.join(path, "events.jsonl")
        with open(log_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
        scratch = os.path.join(path, "ledger.db.rebuild-tmp")
        if os.path.exists(scratch):
            os.remove(scratch)
        db = sqlite3.connect(scratch)
        db.row_factory = sqlite3.Row
        try:
            db.executescript(SCHEMA)
            cls._ensure_columns(db)
            for event in events:
                _fold_event(db, event)
            db.commit()
        finally:
            db.close()
        db_path = os.path.join(path, "ledger.db")
        backup = None
        if os.path.exists(db_path):
            backup = db_path + ".bak"
            os.replace(db_path, backup)
        os.replace(scratch, db_path)
        led = cls(path)
        try:
            check = led.verify_store()
        finally:
            led.close()
        if not check["ok"]:
            if backup is not None:
                os.replace(backup, db_path)
            raise RuntimeError(
                "rebuilt projection failed verification: "
                + "; ".join(check["problems"][:3])
            )
        if backup is not None:
            os.remove(backup)
        return {
            "events": len(events),
            "claims_checked": check["claims_checked"],
            "ok": True,
        }

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
            f.flush()
            os.fsync(f.fileno())  # the log is ground truth: durable
        return event

    def _events(self):
        try:
            with open(self.log_path, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def close(self):
        """Close the database and release the writer lock."""
        try:
            self.db.close()
        finally:
            if self._lock_file is not None:
                self._lock_file.close()
                self._lock_file = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def verify_store(self):
        """Read-only integrity check (v0.11, DESIGN-12): the JSONL
        event log is the ground truth and the SQLite tables are its
        projection — verify they agree, in both directions. Checks:
        every log line parses with the required fields; event ids
        are unique; every asserted claim has a live projection row
        (unless the log moves it to a terminal lifecycle status, in
        which case it must have none); every live row's score equals
        the claim's last score_revision
        new_score (or its assert prior if never revised); and every
        projection claim row — and every claim id referenced by the
        other claim-scoped projection tables — has a corresponding
        assert event in the log (the reverse direction: a projection
        row with no log event is how a crash between the SQLite
        commit and the log append, or a planted row, shows up).
        Returns {ok, events, claims_checked, projection_checked,
        problems[:20]}; never raises on bad data — bad data is the
        finding."""
        problems = []
        events = []
        try:
            with open(self.log_path, encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []
        seen_ids = set()
        expected = {}  # claim_id -> expected live score
        asserted = set()  # claim_ids with an assert event in the log
        terminal = set()  # claim_ids the log moves to a terminal status
        for n, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                problems.append(f"line {n}: unparseable JSON")
                continue
            for field in ("event_id", "t", "type", "payload"):
                if field not in e:
                    problems.append(f"line {n}: missing {field}")
            eid = e.get("event_id")
            if eid in seen_ids:
                problems.append(f"line {n}: duplicate event_id {eid}")
            seen_ids.add(eid)
            events.append(e)
            p = e.get("payload") or {}
            cid = p.get("claim_id")
            if e.get("type") == "assert" and cid:
                expected[cid] = p.get("prior")
                asserted.add(cid)
            elif e.get("type") == "score_revision" and cid:
                expected[cid] = p.get("new_score")
            elif e.get("type") == "supersede" and p.get("old_claim_id"):
                terminal.add(p["old_claim_id"])
            elif e.get("type") == "claim_status_changed" and cid:
                terminal.add(cid)
        checked = 0
        for cid, want in expected.items():
            row = self._live_claim(cid)
            if cid in terminal:
                # A claim that reached a terminal lifecycle status
                # (superseded / entered-in-error / dead) is supposed
                # to have no live row; that is its legitimate end,
                # not a missing projection.
                if row is not None:
                    problems.append(
                        f"{cid}: terminal lifecycle status but still has a live row"
                    )
                continue
            if row is None:
                problems.append(f"{cid}: asserted but no live row")
                continue
            checked += 1
            if want is not None and abs(float(row["score"]) - want) > 1e-9:
                problems.append(
                    f"{cid}: live score {row['score']} != log terminal {want}"
                )
        # Reverse direction: projection -> log. Every claim id the
        # projection knows about must trace back to an assert event;
        # anything else has no corresponding event in the log.
        projection_claims = set()
        for (cid,) in self.db.execute("SELECT DISTINCT claim_id FROM claims"):
            projection_claims.add(cid)
        claim_tables = (
            "support_edges",
            "outcomes",
            "claim_intervals",
            "claim_combos",
            "claim_graphs",
            "claim_topics",
        )
        referenced: dict = {}  # claim_id -> first table that references it
        for table in claim_tables:
            for (cid,) in self.db.execute(
                f"SELECT DISTINCT claim_id FROM {table}"  # noqa: S608 — fixed table names above
            ):
                referenced.setdefault(cid, table)
            if table == "support_edges":
                for (cid,) in self.db.execute(
                    "SELECT DISTINCT supports_id FROM support_edges"
                ):
                    referenced.setdefault(cid, table)
        for cid in sorted(projection_claims - asserted):
            problems.append(
                f"{cid}: projection row in claims with no corresponding "
                "log event (no assert event)"
            )
        for cid in sorted(set(referenced) - asserted):
            if cid in projection_claims:
                continue  # already reported against the claims table
            problems.append(
                f"{cid}: projection row in {referenced[cid]} with no "
                "corresponding log event (no assert event)"
            )
        return {
            "ok": not problems,
            "events": len(events),
            "claims_checked": checked,
            "projection_checked": len(projection_claims | set(referenced)),
            "problems": problems[:20],
        }

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

    def assert_claim(
        self,
        statement,
        prior,
        valid_from=None,
        valid_to=None,
        score_kind="credence",
        materiality=0.05,
        critical=False,
        entrenchment=None,
        writer=None,
        actor="system",
        t=None,
    ):
        """Enter a new conclusion. Returns claim_id.

        entrenchment=None resolves via the writer's trust tier (Design
        Memo 06): owner 0.75, contributor 0.5, provisional 0.25, unregistered
        writer 0.25, no writer 0.5. Explicit entrenchment always overrides."""
        t = t or _now()
        if entrenchment is None:
            if writer is None:
                entrenchment = 0.5
            else:
                entrenchment = TIER_ENTRENCHMENT.get(self.get_writer(writer), 0.25)
        claim_id = _new_id("C")
        if isinstance(entrenchment, str):
            entrenchment = ENTRENCHMENT_TIERS[entrenchment]
        self.db.execute(
            """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                                  valid_to, score, score_kind, status,
                                  materiality, critical, entrenchment, writer)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (
                claim_id,
                t,
                statement,
                valid_from,
                valid_to,
                float(prior),
                score_kind,
                float(materiality),
                int(critical),
                float(entrenchment),
                writer,
            ),
        )
        self.db.commit()
        self._emit(
            "assert",
            {
                "claim_id": claim_id,
                "statement": statement,
                "prior": float(prior),
                "writer": writer,
                # The full row parameters, recorded since 0.13 so the
                # log alone can rebuild the projection exactly
                # (rebuild_projection). Older logs lack these keys;
                # the fold falls back to documented defaults there.
                "valid_from": valid_from,
                "valid_to": valid_to,
                "score_kind": score_kind,
                "materiality": float(materiality),
                "critical": bool(critical),
                "entrenchment": float(entrenchment),
            },
            actor=actor,
            t=t,
        )
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
            (
                claim_id,
                t,
                row["statement"],
                row["valid_from"],
                row["valid_to"],
                float(score),
                row["score_kind"],
                row["status"],
                row["materiality"],
                row["critical"],
                float(entrenchment),
                row["writer"] if "writer" in row.keys() else None,
            ),
        )
        self.db.commit()
        return old_score, old_entr

    def _set_score(
        self, claim_id, new_score, triggering_event_id, actor="system", t=None
    ):
        """Bitemporal score update: close the old version, open a new one."""
        t = t or _now()
        row = self._live_claim(claim_id)
        entrenchment = float(row["entrenchment"]) if row else 0.5
        old, _ = self._new_version(claim_id, new_score, entrenchment, t)
        self._emit(
            "score_revision",
            {
                "claim_id": claim_id,
                "old_score": old,
                "new_score": float(new_score),
                "triggering_event_id": triggering_event_id,
            },
            actor=actor,
            t=t,
        )
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
        self._emit(
            "entrenchment_set",
            {"claim_id": claim_id, "old": old_entr, "new": value},
            actor=actor,
            t=t,
        )
        return old_entr, value

    def apply_tier(self, claim_id, tier, actor="human", t=None):
        """Assign a named entrenchment tier (see ENTRENCHMENT_TIERS)."""
        if tier not in ENTRENCHMENT_TIERS:
            raise KeyError(
                f"unknown tier {tier!r}; choose from {sorted(ENTRENCHMENT_TIERS)}"
            )
        return self.set_entrenchment(
            claim_id, ENTRENCHMENT_TIERS[tier], actor=actor, t=t
        )

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
               FROM outcomes o"""
        ).fetchall()
        by_claim: dict = {}
        for r in rows:
            if r["score_at"] is not None:
                by_claim.setdefault(r["claim_id"], []).append(
                    (float(r["score_at"]), int(r["outcome"]))
                )
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
            self._emit(
                "entrenchment_set",
                {
                    "claim_id": cid,
                    "old": old_e,
                    "new": new_e,
                    "learned": True,
                    "basis": "brier",
                    "brier": round(brier, 4),
                    "n_outcomes": len(hist),
                },
                actor=actor,
                t=t,
            )
            report.append(
                {
                    "claim_id": cid,
                    "old": old_e,
                    "new": new_e,
                    "brier": brier,
                    "n": len(hist),
                }
            )
        # stability path: churn without outcomes
        vers = self.db.execute(
            """SELECT claim_id, score FROM claims
               ORDER BY claim_id, txn_from"""
        ).fetchall()
        by_cid: dict = {}
        for r in vers:
            by_cid.setdefault(r["claim_id"], []).append(float(r["score"]))
        for cid, scores in by_cid.items():
            if cid in brier_done:
                continue  # Brier-learned this pass; stability is for the
            # unresolved (fewer than min_outcomes outcomes, if any)
            if len(scores) < 5:
                continue
            sides = [s > 0.5 for s in scores]
            flips = sum(1 for a, b in zip(sides, sides[1:]) if a != b)  # noqa: B905 — pairwise shift, lengths differ by design
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
            self._emit(
                "entrenchment_set",
                {
                    "claim_id": cid,
                    "old": old_e,
                    "new": new_e,
                    "learned": True,
                    "basis": "stability",
                    "revisions": len(scores),
                    "flips": flips,
                },
                actor=actor,
                t=t,
            )
            report.append(
                {
                    "claim_id": cid,
                    "old": old_e,
                    "new": new_e,
                    "basis": "stability",
                    "flips": flips,
                    "revisions": len(scores),
                }
            )
        return report

    def manual_score(self, claim_id, score, actor="human", t=None):
        """A human hand-sets a score. Counts toward the override-rate
        metric. Propagates to dependents: a human correction is new
        information, and the revisit contract (dependents re-derive)
        applies to it exactly as to ingested evidence. Before
        v0.11.1 the dependents were left stale until evidence next
        touched the parent — OVERRIDE-CAL-01 measured that gap at
        ~2 points of derived error under an identical reviewer."""
        t = t or _now()
        old, new = self._set_score(claim_id, score, None, actor=actor, t=t)
        rep = self._revisit(claim_id, {claim_id: new}, actor=actor, t=t)
        return {
            "claim_id": claim_id,
            "old": old,
            "new": new,
            "revisited": len(rep["updates"]),
        }

    @staticmethod
    def _require_reason_bundle(reason, source):
        """The reason bundle every lifecycle change must carry: a
        non-empty reason and a non-empty source, alongside the actor
        recorded on the event itself. A status change without its
        why and where-from is not auditable, so it is refused."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("a non-empty reason is required")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("a non-empty source is required")

    def supersede(
        self, old_claim_id, statement, prior, *, reason, source, actor="system", t=None
    ):
        """Correction: close the old claim's transaction-time interval, open a new claim.

        The reason bundle is required (keyword-only): `reason` says
        why the old claim is being replaced and `source` says where
        that judgment came from; `actor` (recorded on the event) says
        who did it. The bundle is carried on the supersede event."""
        self._require_reason_bundle(reason, source)
        t = t or _now()
        old = self._live_claim(old_claim_id)
        if old is None:
            raise KeyError(f"unknown claim {old_claim_id}")
        self._close_claim_version(old_claim_id, t)
        self.db.execute(
            "UPDATE claims SET status = 'superseded' WHERE claim_id = ? AND txn_from = ?",
            (old_claim_id, old["txn_from"]),
        )
        new_id = self.assert_claim(
            statement,
            prior,
            actor=actor,
            t=t,
            materiality=old["materiality"],
            critical=bool(old["critical"]),
            entrenchment=old["entrenchment"],
        )
        self.db.commit()
        self._emit(
            "supersede",
            {
                "old_claim_id": old_claim_id,
                "new_claim_id": new_id,
                "reason": reason,
                "source": source,
            },
            actor=actor,
            t=t,
        )
        return new_id

    def set_claim_status(
        self, claim_id, status, *, reason, source, actor="system", t=None
    ):
        """Move a live claim to a terminal lifecycle status without
        deleting anything: 'entered-in-error' (the claim should never
        have been entered) or 'dead' (the claim no longer applies).
        'superseded' is not set here — use supersede(), which opens
        the replacement claim.

        Mirrors supersede(): the claim's live version closes, its
        final version carries the new status, and the change is
        itself an event in the log (claim_status_changed) carrying
        the required reason bundle (reason + source, with the actor
        recorded on the event)."""
        if status not in ("entered-in-error", "dead"):
            raise ValueError(
                "status must be 'entered-in-error' or 'dead' "
                f"(got {status!r}); use supersede() for 'superseded'"
            )
        self._require_reason_bundle(reason, source)
        t = t or _now()
        row = self._live_claim(claim_id)
        if row is None:
            raise KeyError(f"unknown claim {claim_id}")
        self._close_claim_version(claim_id, t)
        self.db.execute(
            "UPDATE claims SET status = ? WHERE claim_id = ? AND txn_from = ?",
            (status, claim_id, row["txn_from"]),
        )
        self.db.commit()
        self._emit(
            "claim_status_changed",
            {
                "claim_id": claim_id,
                "status": status,
                "reason": reason,
                "source": source,
            },
            actor=actor,
            t=t,
        )

    # ------------------------------------------------------------------
    # support edges
    # ------------------------------------------------------------------
    def add_support(
        self,
        claim_id,
        supports_id,
        kind,
        p_given=1.0,
        p_given_not=0.0,
        strength=1.0,
        actor="system",
        t=None,
    ):
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
            (
                claim_id,
                supports_id,
                kind,
                float(p_given),
                float(p_given_not),
                strength,
                t,
            ),
        )
        self.db.commit()
        self._emit(
            "support",
            {
                "claim_id": claim_id,
                "supports_id": supports_id,
                "kind": kind,
                "p_given": float(p_given),
                "p_given_not": float(p_given_not),
                "strength": strength,
            },
            actor=actor,
            t=t,
        )

    # ------------------------------------------------------------------
    # joint likelihoods (Design Memo 05)
    # ------------------------------------------------------------------
    def set_combo(
        self, claim_id, combo, leak=0.0, strengths=None, actor="system", t=None
    ):
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
            (t, claim_id),
        )
        self.db.execute(
            "INSERT INTO claim_combos(claim_id, txn_from, combo, leak)"
            " VALUES (?, ?, ?, ?)",
            (claim_id, t, combo, leak),
        )
        for pid, s in strengths.items():
            self.db.execute(
                """UPDATE support_edges SET strength = ?
                   WHERE claim_id = ? AND supports_id = ? AND txn_to IS NULL""",
                (s, claim_id, pid),
            )
        self.db.commit()
        self._emit(
            "combo_set",
            {
                "claim_id": claim_id,
                "combo": combo,
                "leak": leak,
                "strengths": strengths,
            },
            actor=actor,
            t=t,
        )

    def get_combo(self, claim_id):
        r = self.db.execute(
            "SELECT combo, leak FROM claim_combos"
            " WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,),
        ).fetchone()
        if r is None:
            return None
        strengths = {
            e["supports_id"]: float(e["strength"]) for e in self._live_edges(claim_id)
        }
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
    def register_writer(self, writer_id, tier, actor="system", t=None, public_key=None):
        """Register (or re-tier) a writer. Tiers are bitemporal.

        public_key (v0.9, Design Memo 10): hex ed25519 public key.
        None preserves the writer's current key (re-tiering must not
        silently strip signing); pass a key to set or rotate."""
        if tier not in WRITER_TIERS:
            raise ValueError(f"tier must be one of {WRITER_TIERS}")
        if public_key is not None:
            if len(bytes.fromhex(public_key)) != 32:
                raise ValueError("public_key must be 32 bytes, hex")
        t = t or _now()
        if public_key is None:
            public_key = self.get_writer_pubkey(writer_id)
        self.db.execute(
            "UPDATE writers SET txn_to = ? WHERE writer_id = ? AND txn_to IS NULL",
            (t, writer_id),
        )
        self.db.execute(
            "INSERT INTO writers(writer_id, txn_from, tier, pubkey)"
            " VALUES (?, ?, ?, ?)",
            (writer_id, t, tier, public_key),
        )
        self.db.commit()
        self._emit(
            "writer_registered",
            {"writer_id": writer_id, "tier": tier, "pubkey": public_key},
            actor=actor,
            t=t,
        )

    def get_writer(self, writer_id):
        """Live trust tier of a writer, or None if unregistered."""
        r = self.db.execute(
            "SELECT tier FROM writers WHERE writer_id = ? AND txn_to IS NULL",
            (writer_id,),
        ).fetchone()
        return r["tier"] if r else None

    def get_writer_pubkey(self, writer_id):
        """Live ed25519 public key (hex) of a writer, or None."""
        if writer_id is None:
            return None
        r = self.db.execute(
            "SELECT pubkey FROM writers WHERE writer_id = ? AND txn_to IS NULL",
            (writer_id,),
        ).fetchone()
        return r["pubkey"] if r else None

    def audit_writer_pubkey(self, writer_id, t):
        """The ed25519 public key (hex) in force for a writer at time
        T, or None. The writers table is bitemporal: a rotation closes
        the old row and opens a new one, so the key that governed a
        past moment stays answerable after the writer rotates."""
        if writer_id is None:
            return None
        r = self.db.execute(
            "SELECT pubkey FROM writers"
            " WHERE writer_id = ? AND txn_from <= ?"
            "   AND (txn_to IS NULL OR txn_to > ?)"
            " ORDER BY txn_from DESC, rowid DESC LIMIT 1",
            (writer_id, t, t),
        ).fetchone()
        return r["pubkey"] if r else None

    # ------------------------------------------------------------------
    # signed verdicts (v0.9, Design Memo 10)
    # ------------------------------------------------------------------
    @staticmethod
    def verdict_message(action, target_id, writer, decision=None):
        """Canonical bytes a writer signs for a verdict action."""
        msg = (
            f"axiovex-ledger/verdict/v1|action={action}|id={target_id}|writer={writer}"
        )
        if decision is not None:
            msg += f"|decision={decision}"
        return msg

    def _require_verdict_signature(self, writer, signature, message):
        """Enforce the signed-verdict rule: a writer WITH a registered
        key must sign; writers without keys act unsigned (pre-v0.9
        behavior). Returns payload fields to record, or None."""
        if writer is None:
            return None
        pub = self.get_writer_pubkey(writer)
        if pub is None:
            return None
        if not signature:
            raise PermissionError(
                f"writer {writer} has a registered key: verdict requires a signature"
            )
        try:
            ok = ed25519.verify(
                bytes.fromhex(pub), message.encode(), bytes.fromhex(signature)
            )
        except Exception:
            ok = False
        if not ok:
            raise PermissionError(f"invalid verdict signature for writer {writer}")
        return {"signer": writer, "signature": signature, "signed_message": message}

    def verify_verdict_signatures(self):
        """Audit: re-verify every signed verdict in the log against
        the key in force for the signer at the verdict's signing
        (event) time. The writers table is bitemporal, so a later
        key rotation does not invalidate verdicts signed under the
        key that governed when they were signed — and a verdict
        signed with a key that was not in force at its signing time
        (for example the signer's current key, backdated) fails."""
        checked = valid = 0
        invalid = []
        for e in self._events():
            p = e["payload"]
            if "signature" not in p or "signed_message" not in p:
                continue
            checked += 1
            pub = self.audit_writer_pubkey(p.get("signer"), e.get("t"))
            ok = False
            if pub is not None:
                try:
                    ok = ed25519.verify(
                        bytes.fromhex(pub),
                        p["signed_message"].encode(),
                        bytes.fromhex(p["signature"]),
                    )
                except Exception:
                    ok = False
            if ok:
                valid += 1
            else:
                invalid.append(e["event_id"])
        return {"checked": checked, "valid": valid, "invalid": invalid}

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

    def register_policy(
        self, name, description, version=1, actor="system", t=None, rule=None
    ):
        """Policies are facts in the store they govern (Quipu GS5).
        rule (v0.10, Design Memo 11): a predicate-policy dict
        {"action": ..., "effect": "hold"|"deny", "when": <predicate>},
        validated at registration and stored as JSON beside the prose."""
        if rule is not None:
            _validate_rule(rule)
        t = t or _now()
        live = self.audit_policy(name)
        if live is not None and live["version"] == version:
            return  # idempotent
        self.db.execute(
            "UPDATE policies SET txn_to = ? WHERE name = ? AND txn_to IS NULL",
            (t, name),
        )
        self.db.execute(
            "INSERT INTO policies(name, txn_from, description, version,"
            " rule) VALUES (?, ?, ?, ?, ?)",
            (
                name,
                t,
                description,
                version,
                json.dumps(rule) if rule is not None else None,
            ),
        )
        self.db.commit()
        self._emit(
            "policy_registered",
            {
                "name": name,
                "version": version,
                # Recorded since 0.13 so the log can rebuild the
                # projection exactly (see the assert event).
                "description": description,
                "rule": rule,
            },
            actor=actor,
            t=t,
        )

    def audit_policy(self, name, t=None):
        """The rule in force at T (Quipu GS6: bitemporal rules)."""
        t = t or _now()
        r = self.db.execute(
            "SELECT name, description, version, txn_from, rule"
            " FROM policies"
            " WHERE name = ? AND txn_from <= ?"
            "   AND (txn_to IS NULL OR txn_to > ?)"
            " ORDER BY txn_from DESC LIMIT 1",
            (name, t, t),
        ).fetchone()
        if r is None:
            return None
        d = dict(r)
        d["rule"] = json.loads(d["rule"]) if d.get("rule") else None
        return d

    def live_policies(self):
        """All currently-live policy rows (rules parsed)."""
        rows = self.db.execute(
            "SELECT name, description, version, txn_from, rule"
            " FROM policies WHERE txn_to IS NULL"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["rule"] = json.loads(d["rule"]) if d.get("rule") else None
            out.append(d)
        return out

    def _policy_gate(self, action, ctx):
        """Evaluate live predicate policies over a post-state context
        (Design Memo 11). Returns (effect, policy_name); deny beats
        hold. The default policy's semantics apply even when its live
        row predates rules (compiled-in fallback, same predicate)."""
        hits = []
        default_has_rule = False
        for p in self.live_policies():
            rule = p.get("rule")
            if not rule or rule.get("action") != action:
                continue
            if p["name"] == DEFAULT_POLICY[0]:
                default_has_rule = True
            if _eval_pred(rule["when"], ctx):
                hits.append((rule["effect"], p["name"]))
        if action == "declare_contradiction" and not default_has_rule:
            if _eval_pred(DEFAULT_POLICY_RULE["when"], ctx):
                hits.append(("hold", DEFAULT_POLICY[0]))
        for effect in ("deny", "hold"):
            for eff, name_ in hits:
                if eff == effect:
                    return effect, name_
        return None, None

    def _deny(self, policy, action, ctx, actor, t):
        """A policy denial is a verdict (GS2): persisted, then raised."""
        self._emit(
            "policy_denied",
            {"policy": policy, "action": action, "writer": ctx.get("writer")},
            actor=actor,
            t=t,
        )
        raise PermissionError(f"policy {policy} denies {action}")

    # ------------------------------------------------------------------
    # named-graph partitions (v0.10, Design Memo 11; Quipu GS3/GS4)
    # ------------------------------------------------------------------
    def register_graph(self, name, ceiling, actor="system", t=None):
        """Register (or re-ceiling) a partition. Bitemporal: the old
        row closes, the new one opens, audit_graph answers for T."""
        ceiling = float(ceiling)
        if not 0.0 <= ceiling <= 1.0:
            raise ValueError("ceiling must be in [0, 1]")
        t = t or _now()
        self.db.execute(
            "UPDATE graphs SET txn_to = ? WHERE name = ? AND txn_to IS NULL", (t, name)
        )
        self.db.execute(
            "INSERT INTO graphs(name, txn_from, ceiling) VALUES (?, ?, ?)",
            (name, t, ceiling),
        )
        self.db.commit()
        self._emit(
            "graph_registered", {"graph": name, "ceiling": ceiling}, actor=actor, t=t
        )

    def audit_graph(self, name, t=None):
        """The graph registration in force at T, or None."""
        t = t or _now()
        r = self.db.execute(
            "SELECT name, ceiling, txn_from FROM graphs"
            " WHERE name = ? AND txn_from <= ?"
            "   AND (txn_to IS NULL OR txn_to > ?)"
            " ORDER BY txn_from DESC LIMIT 1",
            (name, t, t),
        ).fetchone()
        return dict(r) if r else None

    def get_graph_ceiling(self, name):
        """Live ceiling of a graph; the default graph caps nothing."""
        if name == DEFAULT_GRAPH:
            live = self.audit_graph(name)
            return float(live["ceiling"]) if live else 1.0
        live = self.audit_graph(name)
        if live is None:
            raise KeyError(f"unregistered graph {name}")
        return float(live["ceiling"])

    def assign_graph(self, claim_id, graph, actor="system", t=None):
        """Assign a claim to a partition (bitemporal)."""
        if self._live_claim(claim_id) is None:
            raise KeyError(f"unknown claim {claim_id}")
        self.get_graph_ceiling(graph)  # KeyError if unregistered
        t = t or _now()
        self.db.execute(
            "UPDATE claim_graphs SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, claim_id),
        )
        self.db.execute(
            "INSERT INTO claim_graphs(claim_id, txn_from, graph) VALUES (?, ?, ?)",
            (claim_id, t, graph),
        )
        self.db.commit()
        self._emit(
            "graph_assigned", {"claim_id": claim_id, "graph": graph}, actor=actor, t=t
        )

    def get_graph(self, claim_id):
        """Live partition of a claim (default graph if unassigned)."""
        r = self.db.execute(
            "SELECT graph FROM claim_graphs WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,),
        ).fetchone()
        return r["graph"] if r else DEFAULT_GRAPH

    def effective_entrenchment(self, claim_id):
        """Entrenchment as decisions may use it (Memo 11): the stored
        value capped by the claim's partition ceiling and by the
        ceilings of its direct supporters' partitions. Composition
        never widens authority; the stored value is never rewritten."""
        row = self._live_claim(claim_id)
        if row is None:
            raise KeyError(f"unknown claim {claim_id}")
        eff = float(row["entrenchment"])
        eff = min(eff, self.get_graph_ceiling(self.get_graph(claim_id)))
        for e in self._live_edges(claim_id):
            eff = min(eff, self.get_graph_ceiling(self.get_graph(e["supports_id"])))
        return eff

    def assign_topic(self, claim_id, topic, actor="system", t=None):
        """Assign a proposition-identity topic to a claim (bitemporal).
        Topics are how the ledger knows two claims are about the same
        proposition; the consolidation pass assigns them, humans can
        override, detect_contradictions consumes them via topic_of."""
        if self._live_claim(claim_id) is None:
            raise KeyError(f"unknown claim {claim_id}")
        t = t or _now()
        self.db.execute(
            "UPDATE claim_topics SET txn_to = ? WHERE claim_id = ? AND txn_to IS NULL",
            (t, claim_id),
        )
        self.db.execute(
            "INSERT INTO claim_topics(claim_id, txn_from, topic) VALUES (?, ?, ?)",
            (claim_id, t, str(topic)),
        )
        self.db.commit()
        self._emit(
            "topic_assigned",
            {"claim_id": claim_id, "topic": str(topic)},
            actor=actor,
            t=t,
        )

    def get_topic(self, claim_id):
        """Live topic of a claim, or None."""
        r = self.db.execute(
            "SELECT topic FROM claim_topics WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,),
        ).fetchone()
        return r["topic"] if r else None

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
        self._emit(
            "retract_support",
            {"claim_id": claim_id, "supports_id": supports_id},
            actor=actor,
            t=t,
        )

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

    def ingest_evidence(
        self, statement, credence, actor="system", t=None, epsilon=0.005
    ):
        """New fact arrives: assert it, then propagate Jeffrey updates through
        the support closure with early cutoff. Returns the revisit report."""
        t = t or _now()
        fact_id = self.assert_claim(
            statement, prior=credence, actor=actor, t=t, entrenchment=1.0
        )
        return self._revisit(
            fact_id, {fact_id: float(credence)}, actor=actor, t=t, epsilon=epsilon
        )

    def _revisit(self, fact_id, new_scores, actor="system", t=None, epsilon=0.005):
        t = t or _now()
        order = self._dependents_bfs(fact_id)
        updated = dict(new_scores)  # claim_id -> new score this pass
        report = {
            "fact_id": fact_id,
            "t": t,
            "updates": [],
            "flags": [],
            "closure_size": len(order),
            "cutoff_skipped": 0,
        }
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
                if not edges or not any(e["supports_id"] in updated for e in edges):
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
                        score = jeffrey(
                            score,
                            float(e["p_given"]),
                            float(e["p_given_not"]),
                            updated[e["supports_id"]],
                        )
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
        self._emit(
            "revisit",
            {
                "fact_id": fact_id,
                "closure_size": report["closure_size"],
                "n_revisited": report["n_revisited"],
                "n_cutoff": report["cutoff_skipped"],
                "n_flags": len(report["flags"]),
            },
            actor=actor,
            t=t,
        )
        return report

    # ------------------------------------------------------------------
    # contradiction resolution (Design Memo 02)
    # ------------------------------------------------------------------
    def declare_contradiction(
        self,
        claim_a,
        claim_b,
        p_loser_given_winner=0.05,
        actor="human",
        writer=None,
        auto=False,
        signal=None,
        t=None,
    ):
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
        target = max(
            self.effective_entrenchment(claim_a), self.effective_entrenchment(claim_b)
        )
        ctx = {
            "action": "declare_contradiction",
            "writer": writer,
            "writer_tier": tier,
            "target_entrenchment": target,
            "claim_a": claim_a,
            "claim_b": claim_b,
        }
        effect, policy = self._policy_gate("declare_contradiction", ctx)
        if effect == "deny":
            self._deny(policy, "declare_contradiction", ctx, actor, t)
        if effect == "hold":
            ev = self._emit(
                "contradiction_held",
                {
                    "policy": policy,
                    "claim_a": claim_a,
                    "claim_b": claim_b,
                    "writer": writer,
                    "tier": tier,
                    "p_loser_given_winner": float(p_loser_given_winner),
                    "outcome": "held",
                    "remediation": "owner must escalate_contradiction"
                    " (release or dismiss)",
                },
                actor=actor,
                t=t,
            )
            return ev["event_id"]
        ev = self._emit(
            "contradiction",
            {
                "claim_a": claim_a,
                "claim_b": claim_b,
                "p_loser_given_winner": float(p_loser_given_winner),
                "writer": writer,
                "auto": bool(auto),
                "signal": signal,
            },
            actor=actor,
            t=t,
        )
        return ev["event_id"]

    def held_contradictions(self):
        """Held declarations minus released pairs (an owner escalated
        to a real declaration) and minus dismissed held ids."""
        evs = self._events()
        open_pairs = {
            (e["payload"]["claim_a"], e["payload"]["claim_b"])
            for e in evs
            if e["type"] == "contradiction"
        }
        dismissed = {
            e["payload"]["held_id"]
            for e in evs
            if e["type"] == "contradiction_dismissed"
        }
        return [
            e
            for e in evs
            if e["type"] == "contradiction_held"
            and e["event_id"] not in dismissed
            and (e["payload"]["claim_a"], e["payload"]["claim_b"]) not in open_pairs
        ]

    def escalate_contradiction(
        self, held_id, decision, writer=None, signature=None, actor="system", t=None
    ):
        """Owner verdict on a held contradiction (Design Memo 10).

        decision="release": the declaration enters the open queue as
        a normal contradiction (the held event's cross-likelihood is
        preserved). decision="dismiss": the hold is closed without a
        declaration. Owner tier required; a keyed owner must sign."""
        t = t or _now()
        if decision not in ("release", "dismiss"):
            raise ValueError("decision must be 'release' or 'dismiss'")
        if self.get_writer(writer) != "owner":
            raise PermissionError("escalation requires an owner-tier writer")
        held = next(
            (e for e in self.held_contradictions() if e["event_id"] == held_id), None
        )
        if held is None:
            raise KeyError(f"no held contradiction {held_id}")
        ctx = {
            "action": "escalate_contradiction",
            "writer": writer,
            "writer_tier": "owner",
            "decision": decision,
            "held_id": held_id,
        }
        effect, policy = self._policy_gate("escalate_contradiction", ctx)
        if effect == "deny":
            self._deny(policy, "escalate_contradiction", ctx, actor, t)
        msg = self.verdict_message("escalate", held_id, writer, decision)
        verdict = self._require_verdict_signature(writer, signature, msg)
        hp = held["payload"]
        a, b = hp["claim_a"], hp["claim_b"]
        if decision == "dismiss":
            payload = {
                "held_id": held_id,
                "claim_a": a,
                "claim_b": b,
                "escalated_by": writer,
            }
            if verdict:
                payload.update(verdict)
            ev = self._emit("contradiction_dismissed", payload, actor=actor, t=t)
            return {
                "decision": "dismiss",
                "held_id": held_id,
                "event_id": ev["event_id"],
            }
        payload = {
            "claim_a": a,
            "claim_b": b,
            "p_loser_given_winner": float(hp.get("p_loser_given_winner", 0.05)),
            "writer": hp.get("writer"),
            "auto": False,
            "signal": "escalation-release",
            "released_from": held_id,
            "escalated_by": writer,
        }
        if verdict:
            payload.update(verdict)
        ev = self._emit("contradiction", payload, actor=actor, t=t)
        return {
            "decision": "release",
            "held_id": held_id,
            "contradiction_id": ev["event_id"],
        }

    @staticmethod
    def _interval_conflict(b1, p1, b2, p2):
        """Pairwise Dempster conflict K between two binary intervals."""
        _, K = dempster_combine(interval_to_mass(b1, p1), interval_to_mass(b2, p2))
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

    def detect_contradictions(
        self, min_opposition=0.7, conflict_k=0.7, actor="system", t=None, topic_of=None
    ):
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
        memo: dict = {}
        anc = {cid: self._ancestors(cid, memo) for cid in ids}

        evs = self._events()
        by_id = {}
        for e in evs:
            if e["type"] in ("contradiction", "contradiction_held"):
                pl = e["payload"]
                by_id[e["event_id"]] = frozenset((pl["claim_a"], pl["claim_b"]))
        seen = set(by_id.values())
        for e in evs:
            if e["type"] == "contradiction_resolved":
                pair = by_id.get(e["payload"]["contradiction_id"])
                if pair:
                    seen.add(pair)

        declared = []
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                if frozenset((a, b)) in seen:
                    continue
                sa, sb = scores[a], scores[b]
                opposed = (sa - 0.5) * (sb - 0.5) < 0 and abs(sa - sb) >= min_opposition
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
                        k = self._interval_conflict(ia[0], ia[1], ib[0], ib[1])
                        if k >= conflict_k:
                            signal = f"interval-conflict:K={k:.2f}"
                if signal is None:
                    continue
                cid = self.declare_contradiction(
                    a, b, actor=actor, auto=True, signal=signal, t=t
                )
                declared.append(cid)
                seen.add(frozenset((a, b)))
        return declared

    def open_contradictions(self):
        """Declared contradictions minus resolved ones (event-sourced)."""
        evs = self._events()
        resolved = {
            e["payload"]["contradiction_id"]
            for e in evs
            if e["type"] == "contradiction_resolved"
        }
        return [
            e
            for e in evs
            if e["type"] == "contradiction" and e["event_id"] not in resolved
        ]

    def resolve_contradiction(
        self,
        contradiction_id,
        actor="system",
        t=None,
        epsilon=0.005,
        writer=None,
        signature=None,
    ):
        """Entrenchment-ordered contraction. The less-entrenched claim is
        revised down via Jeffrey against the winner's score, then its
        dependents are re-propagated. Ties go to a human."""
        t = t or _now()
        if any(e["event_id"] == contradiction_id for e in self.held_contradictions()):
            return {
                "resolved": False,
                "held": True,
                "contradiction_id": contradiction_id,
                "hint": "held for owner review; an owner must "
                "escalate_contradiction (release/dismiss)",
            }
        if all(e["event_id"] != contradiction_id for e in self.open_contradictions()):
            return {
                "resolved": True,
                "already": True,
                "contradiction_id": contradiction_id,
            }
        ce = next(e for e in self._events() if e["event_id"] == contradiction_id)
        a, b = ce["payload"]["claim_a"], ce["payload"]["claim_b"]
        ra, rb = self._live_claim(a), self._live_claim(b)
        if ra is None or rb is None:
            self._emit(
                "contradiction_unresolved",
                {
                    "contradiction_id": contradiction_id,
                    "reason": "claim no longer live",
                },
                actor=actor,
                t=t,
            )
            return {
                "resolved": False,
                "reason": "claim not live",
                "contradiction_id": contradiction_id,
            }
        ea, eb = (self.effective_entrenchment(a), self.effective_entrenchment(b))
        if abs(ea - eb) < 1e-9:
            self._emit(
                "contradiction_unresolved",
                {
                    "contradiction_id": contradiction_id,
                    "reason": "entrenchment tie",
                    "entrenchment": ea,
                },
                actor=actor,
                t=t,
            )
            return {
                "resolved": False,
                "reason": "tie",
                "contradiction_id": contradiction_id,
            }
        loser, winner = (a, b) if ea < eb else (b, a)
        ctx = {
            "action": "resolve_contradiction",
            "writer": writer,
            "writer_tier": (self.get_writer(writer) if writer else None),
            "loser": loser,
            "winner": winner,
            "loser_entrenchment": min(ea, eb),
            "winner_entrenchment": max(ea, eb),
        }
        effect, policy = self._policy_gate("resolve_contradiction", ctx)
        if effect == "deny":
            self._deny(policy, "resolve_contradiction", ctx, actor, t)
        msg = self.verdict_message("resolve", contradiction_id, writer)
        verdict = self._require_verdict_signature(writer, signature, msg)
        rl, rw = self._live_claim(loser), self._live_claim(winner)
        sl, sw = float(rl["score"]), float(rw["score"])
        p_lw = float(ce["payload"]["p_loser_given_winner"])
        # P(loser | ~winner) = loser's current score: the winner's falsity
        # tells us nothing new about the loser.
        new_l = jeffrey(sl, p_lw, sl, sw)
        self._set_score(loser, new_l, contradiction_id, actor=actor, t=t)
        self._emit(
            "contract",
            {
                "contradiction_id": contradiction_id,
                "loser": loser,
                "winner": winner,
                "old": sl,
                "new": new_l,
                "loser_entrenchment": min(ea, eb),
                "winner_entrenchment": max(ea, eb),
            },
            actor=actor,
            t=t,
        )
        resolved_payload = {
            "contradiction_id": contradiction_id,
            "loser": loser,
            "winner": winner,
        }
        if verdict:
            resolved_payload.update(verdict)
        self._emit("contradiction_resolved", resolved_payload, actor=actor, t=t)
        rep = self._revisit(loser, {loser: new_l}, actor=actor, t=t, epsilon=epsilon)
        return {
            "resolved": True,
            "loser": loser,
            "winner": winner,
            "old": sl,
            "new": new_l,
            "contradiction_id": contradiction_id,
            "revisit": rep,
        }

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
            (t, claim_id),
        )
        self.db.execute(
            "INSERT INTO claim_intervals(claim_id, txn_from, belief, plausibility)"
            " VALUES (?, ?, ?, ?)",
            (claim_id, t, b, p),
        )
        self.db.commit()
        self._emit(
            "interval_set",
            {"claim_id": claim_id, "belief": b, "plausibility": p},
            actor=actor,
            t=t,
        )

    def get_interval(self, claim_id):
        r = self.db.execute(
            "SELECT belief, plausibility FROM claim_intervals"
            " WHERE claim_id = ? AND txn_to IS NULL",
            (claim_id,),
        ).fetchone()
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
        new_ev = {
            frozenset({"T"}): m_h,
            frozenset({"F"}): m_nh,
            frozenset({"T", "F"}): m_ig,
        }
        try:
            combined, K = dempster_combine(interval_to_mass(b, p), new_ev)
        except ValueError:
            K = 1.0
            combined = None
        if K >= 0.99 or combined is None:
            self._emit(
                "interval_refused",
                {"claim_id": claim_id, "conflict": K},
                actor=actor,
                t=t,
            )
            return {"combined": False, "conflict": K}
        c_h = combined.get(frozenset({"T"}), 0.0)
        c_nh = combined.get(frozenset({"F"}), 0.0)
        new_b, new_p = c_h, 1.0 - c_nh
        self.set_interval(claim_id, new_b, new_p, actor=actor, t=t)
        self._emit(
            "interval_combined",
            {
                "claim_id": claim_id,
                "belief": new_b,
                "plausibility": new_p,
                "conflict": K,
            },
            actor=actor,
            t=t,
        )
        return {"combined": True, "belief": new_b, "plausibility": new_p, "conflict": K}

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def believed_at(self, t):
        """What did we believe at transaction time T?"""
        return [
            dict(r)
            for r in self.db.execute(
                """SELECT * FROM claims
               WHERE txn_from <= ? AND (txn_to IS NULL OR txn_to > ?)
               ORDER BY txn_from, claim_id""",
                (t, t),
            )
        ]

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
            out.append(
                {
                    "supports_id": e["supports_id"],
                    "statement": s["statement"] if s else None,
                    "score": float(s["score"]) if s else None,
                    "kind": e["kind"],
                    "p_given": float(e["p_given"]),
                    "p_given_not": float(e["p_given_not"]),
                }
            )
        return out

    # ------------------------------------------------------------------
    # read views, health, and the query face (v0.13, DESIGN-13 5-6)
    # ------------------------------------------------------------------
    @staticmethod
    def _claim_dict(row):
        d = dict(row)
        for key in ("score", "materiality", "entrenchment"):
            if d.get(key) is not None:
                d[key] = float(d[key])
        if d.get("critical") is not None:
            d["critical"] = bool(d["critical"])
        return d

    def get_claim(self, claim_id):
        """The live record of one claim as a plain dict, or None."""
        row = self._live_claim(claim_id)
        return self._claim_dict(row) if row is not None else None

    def list_claims(self):
        """Every live claim as a plain dict, ordered by claim_id."""
        rows = self.db.execute(
            "SELECT * FROM claims WHERE txn_to IS NULL ORDER BY claim_id"
        ).fetchall()
        return [self._claim_dict(r) for r in rows]

    def verify(self, deep=False):
        """Integrity verification. The base check is verify_store()
        (log and projection agree, both directions). deep=True also
        re-verifies every signed verdict in the log against the key
        in force at signing time and reports both results."""
        result = self.verify_store()
        if deep:
            sig = self.verify_verdict_signatures()
            result = dict(result)
            result["verdict_signatures"] = sig
            result["ok"] = bool(result["ok"]) and not sig["invalid"]
        return result

    def health(self):
        """Health report for this store (DESIGN-13 section 2.4,
        legacy-format surface): format, event and claim counts, and
        the verification state. Never claims clean over damage —
        ``ok`` is exactly verify_store()'s verdict and the problems
        list travels with it."""
        check = self.verify_store()
        claims = self.db.execute(
            "SELECT COUNT(*) AS n FROM claims WHERE txn_to IS NULL"
        ).fetchone()["n"]
        return {
            "format": "0.12-jsonl",
            "events": check["events"],
            "claims": claims,
            "ok": check["ok"],
            "problems": check["problems"],
        }

    def query(self, text):
        """Run an LQL query (DESIGN-13 section 5; grammar in
        docs/lql.md). Read-only: LQL has no writes. Raises
        LQLParseError (with the offending position) on malformed
        input, before anything executes."""
        from .lql import execute

        return execute(self, text)

    # ------------------------------------------------------------------
    # decisions and impact analysis (v0.13, DESIGN-13 section 3)
    # ------------------------------------------------------------------
    # A decision is a node in the dependency graph: it records the
    # claims it rested on (its basis set) at the moment it was taken.
    # Governance acts already in the log (holds, dismissals,
    # resolutions) surface as decision nodes too: their claim
    # references become basis sets where the act names them, and
    # acts that name no claims (policy denials) get an empty basis
    # set, honestly, not a reconstructed one.
    _GOVERNANCE_ACTS = (
        "contradiction_held",
        "contradiction_dismissed",
        "contradiction_resolved",
    )
    _GOVERNANCE_BASIS_KEYS = ("claim_a", "claim_b", "loser", "winner")
    _MAX_PATHS_PER_NODE = 100
    _MAX_PATH_STEPS = 200_000

    def record_decision(self, label, basis, actor="human", t=None, rationale=None):
        """Record a decision resting on the claims in ``basis``.

        The basis set is fixed at record time and never rewritten:
        later score changes, supersessions, or new decisions do not
        alter what this decision was standing on. Returns the
        decision_id. Raises KeyError if a basis claim is unknown.
        """
        t = t or _now()
        basis_list = []
        for cid in basis:
            if cid not in basis_list:
                basis_list.append(cid)
        for cid in basis_list:
            if self._live_claim(cid) is None:
                raise KeyError(f"unknown claim in basis: {cid}")
        decision_id = _new_id("D")
        self._emit(
            "decision",
            {
                "decision_id": decision_id,
                "label": label,
                "basis": basis_list,
                "rationale": rationale,
            },
            actor=actor,
            t=t,
        )
        return decision_id

    def _decision_index(self):
        """Every decision node, derived from the log (the ground
        truth): explicit ``decision`` events plus the governance
        acts named in DESIGN-13 section 3.1. Cached per instance;
        rebuilt whenever the log has grown since the last build."""
        try:
            size = os.path.getsize(self.log_path)
        except OSError:
            size = -1
        cached = getattr(self, "_decision_cache", None)
        if cached is not None and cached[0] == size:
            return cached[1]
        events = self._events()
        known = {
            e["payload"].get("claim_id")
            for e in events
            if e["type"] == "assert" and e["payload"].get("claim_id")
        }
        decisions = {}
        for e in events:
            p = e["payload"] or {}
            if e["type"] == "decision":
                decisions[p["decision_id"]] = {
                    "decision_id": p["decision_id"],
                    "label": p.get("label"),
                    "basis": list(p.get("basis") or []),
                    "rationale": p.get("rationale"),
                    "t": e["t"],
                    "actor": e["actor"],
                    "kind": "decision",
                }
            elif e["type"] in self._GOVERNANCE_ACTS:
                basis = []
                for key in self._GOVERNANCE_BASIS_KEYS:
                    v = p.get(key)
                    if v in known and v not in basis:
                        basis.append(v)
                decisions[e["event_id"]] = {
                    "decision_id": e["event_id"],
                    "label": e["type"],
                    "basis": basis,
                    "rationale": None,
                    "t": e["t"],
                    "actor": e["actor"],
                    "kind": "governance",
                }
        self._decision_cache = (size, decisions)
        return decisions

    def decisions(self):
        """All decision nodes (recorded decisions and governance
        acts), oldest first. Each carries its immutable basis set."""
        idx = self._decision_index()
        return [idx[k] for k in sorted(idx, key=lambda k: (idx[k]["t"], k))]

    def _dependents_adjacency(self, root):
        """Breadth-first closure of the claims depending on ``root``
        over live support edges. Returns (order, distance, adjacency):
        order is BFS order starting at root, distance maps claim_id
        to its shortest-path distance from root, adjacency maps a
        claim_id to the sorted claim ids that directly depend on it.
        """
        # Load every live edge once and walk in memory: asking the
        # database for each node's dependents in turn costs a query
        # per node, which dominated this walk on large graphs.
        reverse: dict[str, list[str]] = {}
        for e in self.db.execute(
            "SELECT claim_id, supports_id FROM support_edges "
            "WHERE txn_to IS NULL ORDER BY rowid"
        ):
            reverse.setdefault(e["supports_id"], []).append(e["claim_id"])
        distance = {root: 0}
        order = [root]
        adjacency = {}
        queue = deque([root])
        while queue:
            cur = queue.popleft()
            deps = sorted(set(reverse.get(cur, ())))
            adjacency[cur] = deps
            for dep in deps:
                if dep not in distance:
                    distance[dep] = distance[cur] + 1
                    order.append(dep)
                    queue.append(dep)
        return order, distance, adjacency

    def _all_live_scores(self):
        return {
            r["claim_id"]: float(r["score"])
            for r in self.db.execute(
                "SELECT claim_id, score FROM claims WHERE txn_to IS NULL"
            )
        }

    def _dry_run_revision(self, claim_id, target):
        """Revise ``claim_id`` to ``target`` on a throwaway copy of
        this store, using the ordinary revision machinery
        (``manual_score``), and report every resulting score
        movement. The live store is never written: the copy is
        deleted afterwards, events and all."""
        tmp = tempfile.mkdtemp(prefix="epistemic-ledger-impact-")
        try:
            copy_path = os.path.join(tmp, "store")
            shutil.copytree(
                self.path,
                copy_path,
                ignore=shutil.ignore_patterns("ledger.lock"),
            )
            before = self._all_live_scores()
            clone = Ledger(copy_path)
            try:
                clone.manual_score(claim_id, target, actor="impact-dry-run")
                after = clone._all_live_scores()
            finally:
                clone.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        movements = []
        for cid in sorted(set(before) | set(after)):
            old, new = before.get(cid), after.get(cid)
            if old is not None and new is not None and new != old:
                movements.append(
                    {"claim_id": cid, "old": old, "new": new, "delta": new - old}
                )
        return movements

    def impact(
        self,
        claim_id,
        mode="structural",
        *,
        revised_score=None,
        max_depth=None,
        max_results=1000,
    ):
        """What rests on this claim? (DESIGN-13 section 3.2)

        Structural mode returns the transitive closure of dependents
        — derived claims and decision nodes — each with its graph
        distance from ``claim_id`` and the paths it was reached by.

        Propagated mode additionally reports the score movement each
        claim would see if ``claim_id`` were revised to
        ``revised_score`` (default 0.0: the claim is challenged to
        zero), computed by running a real revision on a throwaway
        copy of the store. Nothing in this store changes. Decisions
        whose basis set intersects the moved claims are listed under
        ``decisions_affected``: they rested on ground that moved.
        (That a decision is in the blast radius does not make it
        wrong — only exposed. Judging it stays with people.)

        Caps: ``max_depth`` bounds graph distance, ``max_results``
        bounds the number of nodes returned, and at most
        100 paths per node are listed. Whenever a cap binds,
        ``truncated`` is True and ``truncation_reasons`` says which
        cap — a capped answer is never silently partial.
        """
        if self._live_claim(claim_id) is None:
            raise KeyError(f"unknown claim {claim_id}")
        if mode not in ("structural", "propagated"):
            raise ValueError("mode must be 'structural' or 'propagated'")
        truncated = False
        reasons = []

        order, distance, adjacency = self._dependents_adjacency(claim_id)
        if max_depth is not None:
            if any(d > max_depth for d in distance.values()):
                truncated = True
                reasons.append("max_depth")
            order = [c for c in order if distance[c] <= max_depth]
            distance = {c: distance[c] for c in order}
            adjacency = {c: adjacency.get(c, []) for c in order}

        index = self._decision_index()
        dec_distance = {}
        dec_parents = {}
        for did, d in index.items():
            inside = [c for c in d["basis"] if c in distance]
            if inside:
                dec_parents[did] = inside
                dec_distance[did] = min(distance[c] for c in inside) + 1
        if max_depth is not None:
            over = [k for k, v in dec_distance.items() if v > max_depth]
            if over:
                truncated = True
                if "max_depth" not in reasons:
                    reasons.append("max_depth")
            for k in over:
                del dec_distance[k]
                del dec_parents[k]

        candidates = [(distance[c], c, "claim") for c in order if c != claim_id]
        candidates += [(dec_distance[k], k, "decision") for k in dec_distance]
        candidates.sort()
        if len(candidates) > max_results:
            truncated = True
            reasons.append("max_results")
            candidates = candidates[:max_results]
        kept = {claim_id} | {cid for _, cid, _ in candidates}
        kept_claims = kept & set(distance)

        full_adj = {}
        for c in kept_claims:
            full_adj[c] = sorted(d for d in adjacency.get(c, []) if d in kept)
        for did, parents in dec_parents.items():
            if did in kept:
                for p in parents:
                    if p in kept_claims:
                        full_adj.setdefault(p, []).append(did)
        for c in full_adj:
            full_adj[c] = sorted(set(full_adj[c]))

        # Enumerate simple paths from the root, iteratively (an
        # explicit stack, so long chains cannot hit the interpreter
        # recursion limit). Per-node and global budgets keep dense
        # graphs bounded; hitting either is reported, never silent.
        paths: dict[str, list] = {}
        steps = 0
        stack = [(claim_id, [claim_id], 0)]
        on_path = {claim_id}
        while stack:
            node, path, idx = stack[-1]
            children = full_adj.get(node, [])
            if idx >= len(children):
                stack.pop()
                on_path.discard(node)
                continue
            stack[-1] = (node, path, idx + 1)
            steps += 1
            if steps > self._MAX_PATH_STEPS:
                truncated = True
                if "paths" not in reasons:
                    reasons.append("paths")
                break
            nxt = children[idx]
            if nxt in on_path:
                continue
            lst = paths.setdefault(nxt, [])
            if len(lst) < self._MAX_PATHS_PER_NODE:
                lst.append(path + [nxt])
            else:
                truncated = True
                if "paths" not in reasons:
                    reasons.append("paths")
            stack.append((nxt, path + [nxt], 0))
            on_path.add(nxt)

        nodes = [
            {
                "id": cid,
                "kind": kind,
                "distance": dist,
                "paths": paths.get(cid, []),
            }
            for dist, cid, kind in candidates
        ]
        result = {
            "claim_id": claim_id,
            "mode": mode,
            "nodes": nodes,
            "truncated": truncated,
            "truncation_reasons": reasons,
            "caps": {
                "max_depth": max_depth,
                "max_results": max_results,
                "max_paths_per_node": self._MAX_PATHS_PER_NODE,
            },
        }
        if mode == "propagated":
            target = 0.0 if revised_score is None else float(revised_score)
            movements = self._dry_run_revision(claim_id, target)
            moved = {m["claim_id"] for m in movements}
            result["revised_score"] = target
            result["movements"] = movements
            result["decisions_affected"] = [
                d["decision_id"] for d in self.decisions() if moved & set(d["basis"])
            ]
        return result

    # ------------------------------------------------------------------
    # kill-criteria instrumentation
    # ------------------------------------------------------------------
    def record_outcome(self, claim_id, outcome, t=None):
        """Record that a claim resolved true/false. Feeds the Brier score.
        Multiple outcomes per claim are kept (one row per event time)."""
        t = t or _now()
        self.db.execute(
            "INSERT INTO outcomes(claim_id, outcome, t) VALUES (?, ?, ?)",
            (claim_id, int(bool(outcome)), t),
        )
        self.db.commit()
        self._emit("outcome", {"claim_id": claim_id, "outcome": bool(outcome)}, t=t)

    def kill_metrics(self):
        """The five kill criteria, instrumented. Bars are guesses in v0.1."""
        events = self._events()
        revs = [e for e in events if e["type"] == "revisit"]
        score_revs = [e for e in events if e["type"] == "score_revision"]

        # 1. missed triggers: revisit log is the audit surface (held-out
        #    audit judges recall later; here we expose the raw decisions).
        trigger_log = [e["payload"] for e in revs]

        # 2. churn: sign changes of score deltas over each claim's history,
        #    plus the conflict-normalized variant (Design Memo 09):
        #    material churn. Walk the score trajectory with a hysteresis
        #    anchor at the claim's materiality: only moves >= materiality
        #    register, and churn counts direction reversals among them.
        #    Sub-materiality tug-of-war (balanced adversarial reports,
        #    propagation residue) is absorbed - it changes no decision.
        by_claim: dict = {}
        for seq, e in enumerate(score_revs):
            p = e["payload"]
            # Order by log sequence, not by t: t is caller-supplied and
            # may mix types (ISO strings from _now(), ints from logical
            # clocks) — sorting on it crashed kill_metrics the first
            # time a human manual_score met a step-clocked trial
            # (OVERRIDE-CAL-01). Append order IS transaction order.
            by_claim.setdefault(p["claim_id"], []).append(
                (seq, p["old_score"], p["new_score"])
            )
        mat_of = {
            r["claim_id"]: float(r["materiality"])
            for r in self.db.execute(
                "SELECT claim_id, materiality FROM claims WHERE txn_to IS NULL"
            )
        }
        churn = {}
        churn_detail = {}
        for cid, hist in by_claim.items():
            hist.sort()
            deltas = [n - o for _, o, n in hist[-10:] if abs(n - o) > 1e-9]
            signs = [1 if d > 0 else -1 for d in deltas]
            raw = sum(1 for a, b in zip(signs, signs[1:]) if a != b)  # noqa: B905 — pairwise shift
            churn[cid] = raw
            gross = sum(abs(d) for d in deltas)
            up = sum(d for d in deltas if d > 0)
            down = -sum(d for d in deltas if d < 0)
            balance = 2.0 * min(up, down) / (up + down) if up + down > 0 else 0.0
            band = mat_of.get(cid, 0.05)
            win = hist[-10:]
            scores = [win[0][1]] + [n for _, _, n in win]
            anchor = scores[0]
            move_dirs = []
            for s in scores[1:]:
                if abs(s - anchor) >= band:
                    move_dirs.append(1 if s > anchor else -1)
                    anchor = s
            mat_churn = sum(
                1
                for a, b in zip(move_dirs, move_dirs[1:])  # noqa: B905 — pairwise shift
                if a != b
            )
            churn_detail[cid] = {
                "raw": raw,
                "gross_travel": gross,
                "conflict_balance": balance,
                "material_moves": len(move_dirs),
                "material_churn": mat_churn,
            }

        # 3. support-graph blowup: transitive support fan-out per claim.
        live = [
            r["claim_id"]
            for r in self.db.execute("SELECT claim_id FROM claims WHERE txn_to IS NULL")
        ]
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
        fanout = {
            "n_claims": len(live),
            "avg": sum(fanouts) / len(fanouts) if fanouts else 0.0,
            "max": max(fanouts) if fanouts else 0,
        }

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
        scored = [
            (r["score_at"], r["outcome"]) for r in resolved if r["score_at"] is not None
        ]
        brier = sum((s - o) ** 2 for s, o in scored) / len(scored) if scored else None

        # 5. override rate: human score_revisions without a triggering event.
        manual = [
            e
            for e in score_revs
            if e["actor"] == "human" and not e["payload"].get("triggering_event_id")
        ]
        override_rate = (len(manual) / len(score_revs)) if score_revs else None

        return {
            "trigger_log": trigger_log,
            "churn": churn,
            "churn_detail": churn_detail,
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
        "trigger_recall": 0.90,  # held-out audit; measured 0.96
        "trigger_precision": 0.60,  # held-out audit; measured 0.715
        "mean_flags": 37.0,  # KILL-BARS-01: hub-heavier stress
        # config (600 claims/25 facts) is
        # healthy at 29.2; adjusted to
        # observed x 1.25 (was 25, set on
        # the 300/40 config's 17.1 alone)
        "max_flags": 270.0,  # KILL-BARS-01: same config flags
        # 215 on one hub fact; adjusted to
        # observed x 1.25 (was 60, set on
        # the 300/40 config's max 52).
        # NOTE: flag bars scale with graph
        # size and hub degree — they are
        # review-burden alarms for a given
        # deployment's graph, not
        # universal constants.
        "max_material_churn": 8,  # Design Memo 09 (supersedes raw
        # max_churn as the gate; raw churn
        # stays reported in values, ungated —
        # NEWSROOM-01 finding 3: raw churn
        # conflates healthy tracking with
        # instability). Calibrated CHURN-01:
        # healthy newsroom worst 7 (seed 4),
        # jitter absorbed at 0, synthetic
        # material oscillation 9. Trips only
        # on near-total position instability;
        # integrator quality below that is
        # the Brier bar's job.
        "max_fanout": 100,  # provisional: transitive support size
        "brier": 0.25,  # worse than chance = dead
        "override_rate": 0.20,  # OVERRIDE-CAL-01: scripted reviewers
        # (incl. an every-step corrector) land
        # at 0.005-0.036 in the newsroom — the
        # bar can only trip in quiet ledgers,
        # where hand edits dominate revisions:
        # the condition it exists to catch.
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
            "max_material_churn": (
                max(d["material_churn"] for d in m["churn_detail"].values())
                if m["churn_detail"]
                else 0
            ),
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
        return {
            "values": values,
            "bars": dict(self.KILL_BARS),
            "breached": breached,
            "ok": not breached,
        }
