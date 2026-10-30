# DESIGN-16 — Stress, Performance, and Robustness Program

Status: design memo, directed by the owner 2026-10-29. Spec first, per
this project's flow: this memo changes no behavior. Implementation lands
in stages under the claims of section 4.

## 1. Why this memo exists

The Ledger Standard v1 names an adversarial robustness battery as one of
its five legs. What exists today discharges the letter of that leg: a
12-drill battery (byte mutation, replay, reorder, forgery, checkpoint
mismatch, torn tails) and a budget harness, both gating every release,
all green at 0.13.1. But the battery proves *point-in-time* properties:
twelve named attacks, at chosen offsets, on a fresh store, in seconds.
It does not touch the dimensions where embedded databases actually fail
in production:

- **time** — hours of sustained load: leaks, drift, slow corruption of
  internal state;
- **crashes at arbitrary moments** — a kill between any two instructions
  of an append, not at drill-chosen points;
- **corruption at arbitrary offsets** — any byte of the log, not the
  bytes a drill author picked;
- **contention** — readers querying while the writer appends;
- **exhaustion** — a full disk mid-append, a hard memory ceiling;
- **scale** — an order of magnitude beyond the reference store;
- **arbitrary input** — parsers (the chain reader, LQL) fed bytes nobody
  designed.

This memo turns the battery from a release gate into a standing stress,
performance, and robustness program, with named tools, tiers matched to
cost, and claims stated so they can fail.

## 2. Tooling decisions

The store is embedded and single-writer. The stresses that matter are
process death, storage faults, resource exhaustion, and time — not
request floods against a server that does not exist. The tool choices
follow from that.

**Adopted.**

1. **A repo-native stress harness** (`tools/stress/`, Python) driving
   the real package in *subprocesses*. Subprocess isolation is the
   point: a crash test run in-process proves nothing about crash
   consistency. The harness provides the soak driver, the kill-point
   sweeper, the bit-rot sweeper, a disk-full chamber (a size-capped
   directory), and resource ceilings (memory and file-size limits
   applied to the child processes). No new third-party dependency.
2. **`cargo-fuzz`** (libFuzzer) targets in the Rust core: the chain
   record parser, the verifier's entry points, the canonical-JSON
   decoder, and — as DESIGN-15 lands them — the checkpoint and proof
   decoders. Installed in CI from the prebuilt release binary; corpora
   are committed to the repository; every crash a campaign finds
   becomes a permanent battery drill.
3. **Hypothesis stateful testing** (`RuleBasedStateMachine`): random
   interleavings of appends, challenges, decisions, snapshots, restores,
   and queries, checked against an independent model, extending the
   existing property tests from single properties to operation
   sequences. Hypothesis is already a dev dependency.
4. **SQLite's own integrity checks as harness steps** — `PRAGMA
   integrity_check` on every projection after every stress phase.
   Stock tooling, no new dependency. SQLite's `fuzzcheck`/`dbfuzz`
   binaries were considered and not adopted: they fuzz SQLite itself,
   not this project's use of it, they require a separate source build,
   and the projection is the rebuildable half of the store — the
   corruption sweep (decision 1) covers the risk that matters, against
   the log, which is the truth.

**Deferred, each with its trigger.**

5. **k6** (service-level load) — deferred until the DESIGN-15 ledger
   service exists. Flooding a library with an HTTP load tool today
   would measure a harness, not the product. When the service lands,
   its load program is specified then, against its real endpoints.
6. **Jepsen** (distributed-consistency checking) — deferred unless a
   replicated or multi-writer design is ever proposed. A single-writer
   embedded store presents no distributed-consistency surface to check.

**Rejected.**

7. **HammerDB, sysbench, pgbench** and the TPC benchmark family: they
   measure a client-server database over a wire protocol. The ledger
   has no wire protocol and no server. Their numbers would describe a
   different system and are not evidence about this one.

**On connectors: none is needed, and none is adopted.** Every adopted
tool is a local command-line tool or library, executed in CI from the
repository. That is a deliberate property of the program: robustness
evidence must be reproducible from the repo alone, by anyone, without
an account. A hosted load or chaos service would add a credential, a
billing surface, and a reproducibility hole to buy capabilities the
native harness already covers.

**Hosting: GitHub Actions**, this project's existing build
environment — per-PR samples inside the CI battery family, a scheduled
nightly workflow for the long tiers, and a release-gate run before each
tag. Not the development VM (it is replaced without warning; a
multi-hour soak there is evidence that can vanish mid-run), and not the
owner's desktop. Every report names the runner class it was measured
on, following the DESIGN-13 disclosure precedent: CI numbers are
runner-class numbers.

## 3. Tiers

- **T-PR (every pull request, minutes).** The existing battery and
  budgets, plus: a kill-point sample (25 kills), a bit-rot sample (500
  flips against a 10k-record store), the stateful model test at bounded
  steps, and the fuzz corpora run as regression tests.
- **T-Nightly (scheduled workflow).** A 2-hour mixed soak; a kill-point
  sweep (500 kills); the full bit-rot program (every byte offset of a
  100-record store, exhaustively; 10,000 random flips against the
  100k-record reference store); the reader-concurrency run; and a
  scale run to 1M records recording open, verify, and impact timings.
- **T-Release (before each tag).** The nightly suite, plus fuzz
  campaigns (30 minutes per target), the resource-floor runs
  (disk-full, memory ceiling), and a 4-hour soak. The release does not
  tag on a red release tier — the same standing the battery already
  has. Results are published in the release notes as the proven /
  not-proven pair.

Every tier emits a machine-readable report. A red nightly files an
issue automatically, titled by tier and date, so a failure is a tracked
defect and never weather.

## 4. Claims

- **S1 — Crash consistency (the prefix property).** The harness tracks
  every append the store has acknowledged (its write returned after
  fsync). After a SIGKILL at a random moment, the reopened store
  verifies cleanly and contains exactly a prefix of the acknowledged
  appends: every record up to some point, none after it, no torn
  middle, and no acknowledged record silently dropped from the middle
  of that prefix. *Falsifier:* the kill-point sweep, at sample size in
  T-PR and 500 in T-Nightly.
- **S2 — Corruption detection.** Every single-byte corruption of the
  committed log is detected by verification. Proven exhaustively —
  every byte offset — on the 100-record store, and by 10,000 random
  flips on the 100k-record reference store, stated as exactly that.
  *Falsifier:* either sweep finding an undetected flip.
- **S3 — Soak stability.** Two hours of mixed load (appends, verifies,
  impact analyses, LQL queries interleaved) sustain at least the
  DESIGN-13 append budget, with zero errors, memory growth bounded
  (resident size within 10% of its post-warm-up level at the end), and
  a clean full verification at the end. *Falsifier:* the soak report.
- **S4 — Concurrent readers.** With 8 reader processes querying during
  append load, no reader ever observes a partial or torn record —
  reads return whole, chain-consistent results or clean errors — and
  reader latency stays within a p99 of 250 ms for LQL point queries.
  *Falsifier:* the concurrency run's recorded observations.
- **S5 — Resource floors.** On a real full disk mid-append, the append
  fails loudly and the store reopens and verifies at its pre-append
  state (DESIGN-14's semantics under a genuine ENOSPC, not a simulated
  one). Under a 256 MB memory ceiling, full verification of the
  100k-record reference store completes. Any floor that fails is
  re-stated at the level actually proven — never silently dropped.
  *Falsifier:* the resource-floor runs.
- **S6 — Parser robustness.** The fuzz campaigns find zero panics,
  aborts, or hangs in the fuzzed entry points; LQL's parser is fuzzed
  through the stateful and corpus tests on the same terms. Any crash
  found becomes a battery drill before the campaign counts as green
  again. *Falsifier:* the campaign reports and their corpora.
- **S7 — Scale point.** At 1M records: open within 5 s, full
  verification at or above 20,000 records/s, structural impact within
  250 ms. These numbers are claims, set in advance and measured
  nightly; if one is missed it is revised in the open with the measured
  number, following the DESIGN-13 amendment pattern — never quietly
  edited after the fact.
- **G1 (standing).** The DESIGN-13 budgets and the full battery stay
  green throughout; a stress change that costs a budget is a finding,
  not a trade made silently.

**Stage 3 implementation notes (2026-10-30).** The nightly
workflow runs five legs in parallel — the 2-hour soak, 500
kill-point trials split by engine, the full bit-rot program,
reader concurrency, and the 1M-record scale run — each emitting
its JSON report as an artifact; a report job files an issue
titled by date when any leg failed or any report is missing or
failing. Three measurement decisions are recorded here rather
than buried in the runners. (1) The soak is two legs: the
append budget is measured on the chained store, the engine it
belongs to, under a full-rate append worker, while the mixed
leg (asserts, scores, supports, impacts, queries, verifies)
runs on the Python Ledger and reports its rates as measured —
no budget is invented for them. (2) Reader concurrency is
measured on the two read surfaces the architecture offers:
DESIGN-12 makes the Python Ledger single-writer (an exclusive
lock at open; LQL executes through a Ledger object), so eight
processes cannot each run LQL against the live store. The run
measures the chained store's read-only open under Rust appends
and the projection's point read — the query LQL's CLAIM
compiles to — through read-only SQLite connections under
Python appends, with the 250 ms p99 bar on both. The literal
LQL reading of S4 is therefore not what is measured; that is a
claim/architecture mismatch, recorded here in the open. (3)
The scale run's impact number is measured on the bench's
reference graph (10,000 claims, ~40,000 edges — the shape
DESIGN-13's impact budget uses), because impact is a property
of the claims graph, not of the log's length; open and verify
are measured at the full 1M records. The 100k-store bit-rot
leg applies its 10,000 flips in batches of 100 across distinct
records (tail excluded) with a full verification per batch:
flips in distinct records cannot cancel inside one record's
CRC and hash, so a detected batch detects every flip in it,
and an undetected batch is bisected to name its misses.

## 5. Honest scope — what this does not establish

- Killing a process is not cutting power. Behavior under real power
  loss depends on the storage stack's fsync honesty — the limit
  DESIGN-14 already named. The sweeps prove the software's side of the
  contract.
- CI runners are not production hardware. Numbers are reported with
  their runner class and are evidence about the software's behavior,
  not a capacity promise for any deployment.
- Fuzzing is bounded by wall-clock, not by coverage completeness. A
  quiet campaign means nothing was found in the time spent, stated as
  such.
- The 1M-record point is a chosen point. Behavior beyond it is
  unmeasured, not assumed.
- Stress evidence covers the dimensions drilled. It is not, and is
  never reported as, a proof that no other failure exists.
