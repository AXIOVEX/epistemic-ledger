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
- **S3 — Soak stability.** Two hours of mixed load (asserts,
  score revisions, supports, impact analyses, LQL queries
  interleaved) with zero errors and a clean full verification
  at the end, memory retention bounded (live traced bytes
  after the run within 25% plus 25 MB of the post-warm-up
  live level), and — in a sibling leg of the same duration on
  its own runner — the chained append stream sustaining at
  least the DESIGN-13 append budget with every rotated
  segment verified. *Falsifier:* the soak reports. (Memory
  instrument and leg separation revised 2026-10-31 after the
  first three soak runs; see the soak notes below.)
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

**Stage 4 implementation notes (2026-10-30).** The release
tier is a manually dispatched workflow (the release process
runs it before tagging): the resource floors, a fuzz matrix at
30 minutes per target, and a 4-hour soak, with a report job
that assembles the proven / not-proven summary — including the
latest nightly's conclusion — and files an issue on any red
leg. Two implementation choices are recorded. (1) The
disk-full floor is a genuine ENOSPC on a 96 MB loopback ext4
filesystem, not a simulated write error; where the loopback
setup is unavailable the leg reports NOT RUN with its reason,
never a synthetic pass. The floor as stated requires the
reopened store to verify at exactly the count of successful
appends — if a failure mode ever leaves an unacknowledged
record in the store, that tension with S1's one-in-flight
tolerance is a finding to report, not a tolerance to quietly
adopt here. (2) The memory floor enforces its 256 MB ceiling
with a cgroup scope where systemd-run is available, and
otherwise measures the verifying child's peak resident size
and compares — the report states which mode produced the
verdict (`enforced`). Release-notes reporting: the tier's
summary is written for the release notes verbatim — the claims
with their latest measured values, misses stated as misses.

**S4 resolution (2026-10-30, owner's decision).** The first
nightly's readers leg failed the latency half of S4 because
the chained store had no point-read surface — the leg read
the whole log per query (p99 760 ms at ~300k records) while
the integrity half held. Presented with revising the claim
to the projection surface only or building the surface, the
owner chose to build it. The core gains `StoreReader`
(`reader.rs`): a read-only byte-offset index built under the
chain's own rules (middle damage is a loud `TornMiddle`; a
writer's in-flight tail is simply not yet a record), a
`refresh()` that scans only newly appended bytes, and
`record_at(seq)`, which recomputes the record's hash in the
core before returning it — a point read is a verified point
read. The bindings expose it as `RustReader`, and the
readers leg's rust surface now measures point reads, so S4's
latency leg is measured as written from the next nightly on.

**Release-tier find (2026-10-31).** The tier's first run
(run 41156583580, on the 0.14.0 release commit) went red on
the canon_json fuzz campaign inside 25 minutes: the input
`{"n":123456789.1267893456}` broke canonicalization
idempotence — first pass ending ...35, second ...36.
Reproduced locally, the root cause is serde_json's default
float parser, which is not correctly rounded: the string
"123456789.12678935" parses to the neighboring double.
`canon.rs` is innocent; the parsed value itself moved. The
hazard is larger than the fuzz property: append and verify
both parse through serde_json, so a payload float in this
one-ulp class could hash differently across a reparse than
it did at append — and the Python reference parser, which
rounds correctly, would disagree with the Rust one. The fix
turns on serde_json's precise parser (`float_roundtrip`) in
both crates and pins the found input as a corpus seed and a
unit test (S6's crash-becomes-a-drill rule); the tier
re-runs before the 0.14.0 tag moves. Recorded honestly for
existing stores: a chain written before this fix that
contains a float in the affected class may fail
verification after it, because its hashes were computed
over the mis-parsed value. The class is narrow — a decimal
string the fast parser rounds the wrong way — and no
battery or bench chain contains one; the alternative,
keeping a parser that misreads its own canonical output,
is worse. The same run's floors leg passed outright (real
ENOSPC: 18,436 appends, the next failed loudly, the store
verified at exactly that count; verification of 100,000
records inside an enforced 256 MB ceiling, peak 187.5 MB).

**Release-tier soak verdicts (2026-10-31).** Both tier runs
completed the 4-hour soak; S3 is NOT YET PROVEN, for three
separate reasons the reports decompose cleanly. (1) A real
product defect: the Python ledger's identifiers carried 32
bits of randomness (`uuid4().hex[:8]`, for event, claim,
and decision ids alike), and both soaks crossed the
birthday bound — the first duplicate event id appeared at
line 43,138 in one run and line 104,061 in the other; every
verify_store from then on reported it, and the final
verification failed with it. Fixed by taking the full UUID
hex; soak-scale draws are pinned in a unit test. (2) A
measurement defect: end-of-run resident size grew ~26,000%
in both runs, which reads as a leak and is not one — a
local profile of the same workload (tracemalloc, 3,000
cycles) shows ~1 MB of live retained memory while peak RSS
ratchets upward: per-operation transients grow with the
store (whole-log parses, whole-graph impact walks) and the
allocator keeps the high-water mark. The drift metric as
written cannot pass on a store that grows a hundredfold
during the run, for any implementation with O(store)
operations; S3's memory leg is therefore re-stated as
RETENTION — resident memory after the ledger closes and
the allocator is trimmed, against the post-warm-up level,
with a 25% + 25 MB slack sized to allocator fragmentation,
not to the observed 26,000% (a real leak of the kind the
metric feared would blow through it). Peak resident size
stays in the report, as measured. (3) The append leg
measured 1,972 and 1,807 appends/s against the 2,000
budget — both runs soaked concurrently with each other
and with ten fuzz/floors jobs on the same hosted fleet,
and the mixed leg shares the soak runner's CPUs with the
append worker; the figure is recorded as measured under
that contention and is re-measured on the post-fix re-run,
which runs alone. What the soaks did prove, both times:
~28 million chained appends across 8 rotated segments,
every segment verified inside the S1 prefix tolerance,
and zero errors of any other kind across ~118,000 mixed
operations. The tier re-runs on the fixed code before the
0.14.0 tag moves.

**Release-tier soak, run 3 (2026-10-31).** The identifier
fix held: zero errors across ~103,000 mixed operations and
the final verification clean — the integrity half of S3 is
proven at 4-hour scale. The run still failed its two
measurement legs, and both failures were chased to ground
before changing anything. Retention, as re-instrumented in
run 3's soak (resident size after close + trim), read
225 MB against a 25 MB post-warm-up level — but the
tracemalloc census at probe scale shows ~1 MB actually
live: the gap is fragmented allocator arenas, which no
resident-size reading can separate from retention. The
instrument is therefore live traced bytes (tracemalloc from
post-warm-up to post-close), which counts exactly what the
program still holds; the 25% + 25 MB bound is unchanged.
And the append leg missed again — 1,785 appends/s, SOLO
this time — which killed the fleet-contention theory and
isolated the mechanism: the mixed leg shares the soak
runner, and its per-cycle cost grows with its store, so it
starves the co-resident append worker more every hour.
The DESIGN-13 budget was earned on an idle box; from this
revision the append leg runs on its own runner at both
tiers, and the mixed leg's cycles no longer sit on its
CPUs. S3 remains NOT PROVEN until a tier run is green
under this shape; the tag remains held.

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
