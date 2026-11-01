"""Build the DESIGN-17 stage-6 conformance ledger.

The ledger records this program's own design claims —
DESIGN-13, DESIGN-15, DESIGN-16, DESIGN-17 — entered
through the package's public API with the pattern fields
populated, so the repo can carry a real ledger, its
generated matrix and map, and a CI gate over all three.

Statements are compressed from the memos, which remain
the text of record; each claim's source names its memo
section and the PR or run that carries its evidence.
Priors are 0.5 throughout, deliberately uninformative:
this program settles claims by running their falsifiers,
and the outcome of that settlement lives in the source
field and the claim lifecycle, not in an invented number.

The committed `events.jsonl` IS the ledger. This script
is its recipe: re-running it mints fresh claim ids, so
it documents how the ledger was made rather than
regenerating it. The matrix and map, by contrast, are
regenerated from the committed log at any time with
`pattern-export`, and CI's pattern gate proves the
committed copies are the generated ones.

Run from the repo root with the package importable:

    PYTHONPATH=src python tools/pattern/build_program_ledger.py
"""

import os
import shutil
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")
)

from epistemic_ledger import Ledger  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
TARGET = os.path.join(ROOT, "docs", "pattern", "program-ledger")

# (statement, source, falsifier, does_not_establish)
D13 = [
    (
        "Any rewrite of committed history - a flipped bit, or a deleted, "
        "inserted, or reordered record - is detected by chain verification.",
        "DESIGN-13 sections 1 and 7; adversarial battery (CI)",
        "The battery's history attacks pass undetected.",
        None,
    ),
    (
        "Merkle checkpoints commit to each 1,024-record segment; a "
        "segment's root changes if any record it covers changes.",
        "DESIGN-13 section 1.2; battery checkpoint drills",
        "A covered record changes without its segment root changing.",
        None,
    ),
    (
        "The chained store admits exactly one writer; a second "
        "concurrent writer is refused.",
        "DESIGN-13 section 2.2; concurrency drill",
        "Two writers append to one store concurrently.",
        None,
    ),
    (
        "A torn final write is truncated at open and reported; damage "
        "in the middle of the log is a loud error, never a silent repair.",
        "DESIGN-13 section 2.3; kill-point and corruption drills",
        "A drill finds a silently repaired middle or a lost torn tail.",
        None,
    ),
    (
        "The impact query returns a claim's structural dependents and, "
        "in propagated mode, the score movement each dependent takes "
        "under a hypothetical revision.",
        "DESIGN-13 section 3; impact tests and bench",
        "A dependent is missing from the closure, or a propagated "
        "movement disagrees with re-settlement.",
        None,
    ),
    (
        "The DESIGN-13 budgets hold on the reference class: append at "
        "or above 2,000 records/s, verification at or above 50,000 "
        "records/s, open within 250 ms at 100k records.",
        "DESIGN-13 section 8; per-PR bench with budgets enforced",
        "The bench reports any budget missed.",
        "Runner-class numbers; not a guarantee on other hardware.",
    ),
]

D15 = [
    (
        "After a checkpoint is anchored, any rewrite of pre-anchor "
        "history is detected by consistency verification against the "
        "anchored signed tree head.",
        "DESIGN-15 section 4; PRs #36 and #37 (stage 1)",
        "A drill anchors, rewrites history below the anchor, and "
        "verification accepts it.",
        "Proves a history existed and was not rewritten; not that "
        "its contents were true.",
    ),
    (
        "For any record covered by an anchored checkpoint, an inclusion "
        "proof verifies against the anchored root with no access to "
        "the store.",
        "DESIGN-15 section 4; PRs #36 and #37 (stage 1)",
        "A standalone verifier accepts a proof for a mutated record, "
        "a wrong record, or a wrong checkpoint.",
        None,
    ),
    (
        "A verifier holding a pinned tree head detects equivocation: "
        "two validly signed heads at one tree size with different "
        "roots produce a hard fork error.",
        "DESIGN-15 section 4; PRs #36 and #37 (stage 1)",
        "A drill signs two such heads with the real checkpoint key "
        "and the verifier accepts both.",
        None,
    ),
    (
        "No package API path reads from or appends to a partition "
        "other than the one opened, and governed verification enforces "
        "key enrollment windows.",
        "DESIGN-15 section 5; PR #41 (stage 2a)",
        "A cross-partition probe succeeds, or a record signed outside "
        "its key's window verifies.",
        None,
    ),
    (
        "Without the tenant's HMAC key, the store's bytes do not yield "
        "payload content: a dictionary attack over a known payload "
        "space fails against the commitments, while the key holder's "
        "recomputation verifies.",
        "DESIGN-15 section 5; PR #42 (stage 2b)",
        "The drill's keyless attack recovers a payload, or the key "
        "holder's recomputation fails.",
        None,
    ),
    (
        "After an erasure record and destruction of the payload key "
        "and salt, the payload is unrecoverable from any ledger "
        "artifact, while chain verification, checkpoints, and proofs "
        "over the affected region still pass.",
        "DESIGN-15 section 5; PR #42 (stage 2b)",
        "An erasure drill recovers the payload from the store, a "
        "snapshot, or an export.",
        "An erasure record attests the act was recorded, not that a "
        "key was destroyed; destruction happens outside the ledger.",
    ),
    (
        "Appends that violate a registered schema version are refused "
        "at append time with the violated field named; appends of "
        "unregistered types behave exactly as they do today.",
        "DESIGN-15 section 6 (stage 3 - not yet built; awaits the "
        "Arcturus field-level requirements)",
        "The refusal suite accepts a violating append, or a "
        "regression run of the existing suite changes behavior.",
        None,
    ),
    (
        "A disclosure receipt validates for exactly the disclosure "
        "record it was issued from - not for another disclosure, "
        "another partition, or a mutated record.",
        "DESIGN-15 section 6 (stage 3 - not yet built; awaits the "
        "Arcturus field-level requirements)",
        "A receipt-swap or receipt-mutation drill validates.",
        None,
    ),
    (
        "The PROV export accounts for the store exactly: every "
        "exported activity maps to exactly one ledger record, the "
        "export's stated head hash equals the store's, and a "
        "re-derived export of an unchanged store is identical.",
        "DESIGN-15 section 7; PR #44 (stage 4)",
        "A round-trip accounting test over generated stores finds a "
        "mismatch.",
        "Accounts for the store's records; does not establish the "
        "records' contents are true.",
    ),
    (
        "A clean environment with no Rust toolchain installs the "
        "wheel from the package index and runs the chained-store path "
        "end to end: open, migrate, snapshot, verify.",
        "DESIGN-15 section 7; PR #49 (stage 5 PR A); every release "
        "since 0.14.0",
        "The toolchain-scrubbed install smoke fails.",
        None,
    ),
    (
        "The DESIGN-13 budgets and the full battery, extended per "
        "stage, stay green at every release; a stage that cannot keep "
        "them does not ship.",
        "DESIGN-15 G1; standing, checked at every release",
        "A release ships with a red budget or battery leg.",
        None,
    ),
]

D16_FIXED = [
    (
        "Crash consistency (the prefix property): after a SIGKILL at "
        "a random moment, the reopened store verifies cleanly and "
        "contains exactly a prefix of the acknowledged appends.",
        "DESIGN-16 S1; kill-point sweeps (nightly 500, release tier)",
        "The kill-point sweep finds a dropped acknowledged record, a "
        "torn middle, or a failed verification.",
        "Process kills, not power cuts; storage that lies to fsync "
        "is out of scope.",
    ),
    (
        "Every single-byte corruption of the committed log is "
        "detected by verification - exhaustively on the 100-record "
        "store, and by 10,000 random flips on the 100k-record store.",
        "DESIGN-16 S2; bit-rot sweeps",
        "Either sweep finds an undetected flip.",
        "Stated as exactly the two sweeps; not a proof over all "
        "stores.",
    ),
]

S3_V1 = (
    "Soak stability, as first stated: two hours of mixed load with "
    "zero errors and a clean final verification, end-of-run memory "
    "drift bounded, and the append leg sustaining the DESIGN-13 "
    "append budget of 2,000 appends/s.",
    "DESIGN-16 S3 as written 2026-10-30 (PR #32)",
    "The soak reports.",
    None,
)
S3_V2 = (
    "Soak stability, first revision: the drift criterion is "
    "quiescent retention (RSS after close, garbage collection, and "
    "allocator trim), and the mixed and append legs run as separate "
    "jobs on separate runners; the append leg sustains the append "
    "budget.",
    "DESIGN-16 S3 as revised in PRs #55 and #57 (soak run notes)",
    "The soak reports.",
    None,
)
S3_V3 = (
    "Soak stability: two hours of mixed load with zero errors and "
    "a clean final verification, live traced bytes after the run "
    "within 25% plus 25 MB of the post-warm-up live level, and a "
    "sibling append leg sustaining the full duration with every "
    "rotated segment verified, its rate reported as measured; the "
    "append budget itself is gated by the per-PR bench.",
    "DESIGN-16 S3 as re-scoped 2026-10-31 (PR #60); release-tier "
    "run 5 and the 2026-10-31 nightly both green",
    "The soak reports.",
    None,
)

D16_REST = [
    (
        "Concurrent readers: with 8 reader processes querying during "
        "append load, no reader observes a partial or torn record, "
        "and point-read latency stays within a p99 of 250 ms.",
        "DESIGN-16 S4; PR #50 (point reads); S4 run 2026-10-31 "
        "(p99 0.039 ms point reads, 18.457 ms projection)",
        "The concurrency run records a torn observation or a p99 "
        "above budget.",
        None,
    ),
    (
        "Resource floors: on a real full disk mid-append, the append "
        "fails loudly and the store reopens and verifies at its "
        "pre-append state; under a 256 MB memory ceiling, full "
        "verification of the 100k-record store completes. Any floor "
        "that fails is re-stated at the level actually proven.",
        "DESIGN-16 S5; floor legs on every tier run (18,436 appends "
        "to genuine ENOSPC, reopen verified at exactly 18,436)",
        "The resource-floor runs.",
        None,
    ),
    (
        "Parser robustness: the fuzz campaigns find zero panics, "
        "aborts, or hangs in the fuzzed entry points; any crash found "
        "becomes a battery drill before the campaign counts green.",
        "DESIGN-16 S6; fuzz legs (nightly and release tier)",
        "The campaign reports and their corpora.",
        None,
    ),
    (
        "Scale point: at 1M records, open within 5 s, full "
        "verification at or above 20,000 records/s, structural impact "
        "within 250 ms.",
        "DESIGN-16 S7; scale run 2026-10-31 (open 2.432 s, verify "
        "65,075 records/s, impact 69.6 ms, median of 5 after warm-up)",
        "The nightly scale run misses a number; a miss is revised in "
        "the open with the measured number, never quietly edited.",
        "Runner-class numbers on hosted CI hardware.",
    ),
    (
        "The DESIGN-13 budgets and the full battery stay green "
        "throughout the stress program; a stress change that costs a "
        "budget is a finding, not a trade made silently.",
        "DESIGN-16 G1; standing",
        "A budget or battery leg goes red and the change ships "
        "anyway.",
        None,
    ),
]

D17 = [
    (
        "Claim fields: a claim carries source, falsifier, and "
        "does-not-establish as first-class fields that round-trip "
        "through every read path, score revisions, and projection "
        "rebuilds.",
        "DESIGN-17 P1; PR #62",
        "A fielded claim read back with a pattern field missing or "
        "altered, at any point in that set.",
        None,
    ),
    (
        "Append-only corrections: no operation mutates a recorded "
        "claim event; a correction is a new event, and the original "
        "stands readable as written.",
        "DESIGN-17 P2; PR #62 (log-prefix assertion)",
        "A drill whose post-correction log differs anywhere before "
        "the correction's own event.",
        None,
    ),
    (
        "The matrix is generated, never made: every claim in the "
        "ledger, live or terminal, appears exactly once, and each "
        "row's fields equal the ledger's record for that claim.",
        "DESIGN-17 P3; PR #63",
        "A generated matrix that omits a claim, duplicates one, or "
        "contradicts the live projection on any row.",
        None,
    ),
    (
        "The map is generated and traceable: headline counts equal "
        "the store's own verification counts, and every element "
        "carries the ids of the ledger records it rests on.",
        "DESIGN-17 P4; PR #64",
        "An element with no ledger id, or a headline count that "
        "diverges from verification.",
        None,
    ),
    (
        "The gate regenerates the matrix and the map from the "
        "ledger's records and fails on any byte of divergence, "
        "naming the diverging layer; it writes nothing.",
        "DESIGN-17 P5; PRs #65 and #66",
        "Tamper drills: edit one byte of either artifact, drop a "
        "row, or present a stale pair, and the gate passes.",
        "Proves downstream layers are faithful to the ledger; "
        "never that the ledger is faithful to the world.",
    ),
    (
        "The engine meets pre-registered expectations on a golden "
        "ledger: expectations written from the documented rules "
        "before consulting the implementation, reproduced exactly "
        "by settlement, impact, and verification.",
        "DESIGN-17 P6; PR #65 (golden test)",
        "Any golden expectation the engine fails to reproduce.",
        None,
    ),
    (
        "The pattern module is project-agnostic and ships without "
        "breaking the 0.14.0 surface.",
        "DESIGN-17 G1; PRs #62 to #66, full CI each",
        "A project term appears in the module, or any pre-existing "
        "test changes behavior.",
        None,
    ),
]


def main():
    tmp = os.path.join(ROOT, "docs", "pattern", ".build-tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    led = Ledger(tmp)
    ids = {}

    def enter(key, entry, t):
        statement, source, falsifier, dne = entry
        ids[key] = led.assert_claim(
            statement,
            0.5,
            source=source,
            falsifier=falsifier,
            does_not_establish=dne,
            actor="design",
            t=t,
        )

    for i, e in enumerate(D13, 1):
        enter(f"D13-{i}", e, "2026-10-28T09:00:00+00:00")
    for i, e in enumerate(D15, 1):
        labels = ["A1", "A2", "A3", "T1", "T2", "T3", "R1", "R2", "V1", "W1", "G1"]
        enter(f"D15-{labels[i - 1]}", e, "2026-10-30T09:00:00+00:00")
    enter("D16-S1", D16_FIXED[0], "2026-10-30T10:00:00+00:00")
    enter("D16-S2", D16_FIXED[1], "2026-10-30T10:00:00+00:00")
    enter("D16-S3", S3_V1, "2026-10-30T10:00:00+00:00")
    v2 = led.supersede(
        ids["D16-S3"],
        S3_V2[0],
        0.5,
        reason=(
            "The first soak runs showed end-of-run RSS measures "
            "allocator state, not retention; re-instrumented to "
            "quiescent retention and the legs separated."
        ),
        source="Soak runs 1-3; PRs #55 and #57 design notes",
        falsifier=S3_V2[2],
        actor="design",
        t="2026-10-31T09:00:00+00:00",
    )
    v3 = led.supersede(
        v2,
        S3_V3[0],
        0.5,
        reason=(
            "Four append measurements against the rate gate could "
            "not be attributed to the product; the owner re-scoped "
            "the gate to the per-PR bench (decision of 2026-10-31), "
            "and retention moved to live traced bytes."
        ),
        source="PR #60; release-tier run 5; nightly 2026-10-31",
        falsifier=S3_V3[2],
        actor="design",
        t="2026-10-31T12:30:00+00:00",
    )
    ids["D16-S3"] = v3
    for label, e in zip(["S4", "S5", "S6", "S7", "G1"], D16_REST, strict=True):
        enter(f"D16-{label}", e, "2026-10-31T10:00:00+00:00")
    for label, e in zip(["P1", "P2", "P3", "P4", "P5", "P6", "G1"], D17, strict=True):
        enter(f"D17-{label}", e, "2026-11-01T08:00:00+00:00")

    led.record_decision(
        "Re-scope the soak append gate to the bench",
        [ids["D16-S3"]],
        rationale=(
            "Owner decision, 2026-10-31: the soak append leg proves "
            "endurance and integrity; the rate budget is gated by the "
            "per-PR bench, whose workload it describes."
        ),
        actor="owner",
        t="2026-10-31T12:03:00+00:00",
    )
    led.record_decision(
        "Release 0.14.0",
        [ids["D16-S1"], ids["D16-S2"], ids["D16-S3"], ids["D16-S5"],
         ids["D16-S6"], ids["D16-S7"]],
        rationale="Release-tier run 5 fully green on the release commit.",
        actor="owner",
        t="2026-10-31T17:00:00+00:00",
    )
    led.record_decision(
        "Adopt the winning-combination pattern (DESIGN-17)",
        [ids["D17-P1"], ids["D17-P2"], ids["D17-P3"], ids["D17-P4"],
         ids["D17-P5"], ids["D17-P6"]],
        rationale="Owner directive, 2026-11-01 (harmonization).",
        actor="owner",
        t="2026-11-01T08:30:00+00:00",
    )
    report = led.verify_store()
    assert report["ok"], report
    led.close()
    os.makedirs(TARGET, exist_ok=True)
    shutil.copyfile(
        os.path.join(tmp, "events.jsonl"), os.path.join(TARGET, "events.jsonl")
    )
    shutil.rmtree(tmp)
    print(f"built {TARGET}/events.jsonl; verify: {report}")


if __name__ == "__main__":
    main()
