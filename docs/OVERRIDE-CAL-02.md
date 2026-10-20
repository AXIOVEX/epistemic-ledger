# OVERRIDE-CAL-02 — The override bar, calibrated against a human

**Status: packet prepared 2026-10-20; not yet run.** This document
is the frozen protocol. When the study is run, results are appended
below the line at the end, with any deviations disclosed there.

## Why this study exists

The ledger has a kill bar for human overrides: if people hand-set
more than 20% of all score revisions (`override_rate` > 0.20), the
loop is considered untrusted — humans are driving the store by hand
because the machinery is not doing its job.

OVERRIDE-CAL-01 (2026-10-02) measured that bar against *scripted*
reviewers — software personas that peek at ground truth and correct
whatever deviates from it past a threshold. Even the most aggressive
persona produced an override rate of 0.035, a sixth of the bar, and
the bar was reclassified as *calibrated-against-scripted-reviewers*.
The report said plainly what remains true: **personas are not
humans, and the bar has never been measured against a real reviewer
working from real evidence.** That is the one calibration this
program still owes. This packet is how it gets paid.

## The question

When a human editor reviews the newsroom ledger's beliefs at a
regular cadence — seeing the reports the system received and the
scores it holds, but never the ground truth —

1. what override rate do they actually produce (does the 0.20 bar
   stand, now against human data?), and
2. does their reviewing make the ledger more or less accurate than
   leaving it alone, and how does that compare with the scripted
   diligent reviewer (ledger error 0.0758 vs 0.1452 unreviewed)?

## Design (frozen)

**Workload.** Identical to OVERRIDE-CAL-01: the standard newsroom
trial (12 facts that flip over time, 6 sources — two wires, two
blogs, two unregistered rumor sources — 60 steps, `run_trial` with
the modeled extractor). Mirroring the persona study exactly is what
makes the numbers comparable; the modeled extractor is deliberate,
since the persona baseline was measured on it and the override path
— not text parsing — is what is being calibrated.

**Review points.** Every 5 steps (steps 5, 10, …, 60), the trial
pauses and the reviewer is shown, for each of the 14 reviewable
claims (10 ordinary facts, plus the wire-desk and rumor-desk
assessments of the 2 contested facts):

- the claim and its current score,
- every report received since the last review, grouped under the
  claim it was about, shown as source + the stance the sentence
  expressed (for example `wire-a:T blog-d:F rumor-e:T`),
- the system's current learned accuracy estimate for each source.

The reviewer never sees ground truth, never sees which facts have
flipped, and never sees the system's parse of a sentence — only the
reports as written. Derived claims are not directly reviewable
(they inherit through propagation), exactly as in the persona
study.

**The override.** For any claim, the reviewer may set the score to
any value in [0, 1] through the real human path (`manual_score`,
which propagates to dependents since v0.11.1). Leaving a claim alone
is a decision too and is the default. Suggested anchors, matching
the persona study's targets: 0.9 for "confident this is true", 0.1
for "confident this is false", intermediate values for genuine
uncertainty. The reviewer is asked to review as an editor, not to
game any metric: correct what the evidence says is wrong, leave
what it supports.

**Arms and seeds (frozen).** Primary: one human reviewer, cadence
5, seeds 0–2. Extension (optional, same protocol): seeds 3–4,
giving a 5-seed mean directly comparable to OVERRIDE-CAL-01's
table. Reference numbers are already measured and are not re-run:
unreviewed baseline ledger error 0.1452 / derived 0.1450; diligent
persona (cadence 5) 0.0758 / 0.0858 at override rate 0.0200. The
runner additionally verifies the baseline reproduction (seed 0 =
0.140625 exactly) before the first session, as OVERRIDE-CAL-01 did.

**Sessions and resumption.** A seed takes an estimated 15–35
minutes of reviewer time and may be split across sittings. Every
decision is written to the results file the moment it is made. If
a session stops mid-seed, rerunning the same command replays the
recorded decisions silently — the modeled trial is deterministic,
so the replay reaches the identical state — and prompting resumes
at the first unrecorded review point. Nothing already decided is
ever asked twice.

**Who reviews.** The first reviewer is the owner. Additional
reviewers may run the same protocol under their own name (the
runner records the reviewer name on every session); their rows are
reported separately, never pooled silently, and agreement between
reviewers is reported descriptively if two or more complete the
primary seeds.

## Verdict rules (frozen in advance)

- **The bar.** If any completed, protocol-clean seed shows a human
  override rate above 0.20, the bar has been breached by a healthy
  workload and moves — under the standing KILL-BARS rule — to the
  observed maximum × 1.25, with the old value recorded alongside.
  Otherwise the bar is **CONFIRMED against human data**, and its
  status upgrades from *calibrated-against-scripted-reviewers* to
  *calibrated*. Given the persona response curve (maximum 0.035),
  confirmation is the expected outcome; the value of the study is
  that the expectation becomes a measurement.
- **The benefit.** Human-arm ledger and derived error are reported
  per seed and as a mean, next to the unreviewed baseline and the
  diligent persona. No pass/fail bar exists for human accuracy and
  none is invented after the fact; the claim made is directional
  only (reviewing helped / did not help, by how much, at what
  override rate).
- **Discipline.** No protocol change after the first session
  starts. Anything that has to change is disclosed in the results
  and the affected seeds are marked; a changed protocol is a new
  study (OVERRIDE-CAL-03), not an edit to this one. One reviewer
  means every conclusion carries *n = 1 reviewer* on its face.

## Running it

On the desktop (WSL2), from the repo checkout — no server, no GPU,
no spend; the only dependency is the repo itself:

```
cd ~/epistemic-ledger/prototype/validation
python3 override_calibration_human.py --reviewer <your-name>
```

Defaults run the primary arm (seeds 0–2, cadence 5). Add
`--seeds 3,4` for the extension. `--report` prints the results
table from whatever sessions are recorded. Decisions and results
accumulate in `override_calibration_human_results.json` beside the
runner; that file is committed to the repo with the results.

At each review point the screen shows the 14 claims and their new
reports. Enter overrides as `number=value` pairs separated by
spaces (for example `3=0.9 11=0.1`), press Enter alone to keep
everything, or type `q` to save and stop.

**Packet verification (2026-10-20, before any human session).** The
runner was smoke-tested end to end with scripted input standing in
for the reviewer: the baseline gate reproduced OVERRIDE-CAL-01's
archived seed-0 number exactly, a canned override was applied and
recorded, and a no-input rerun replayed the recorded decisions and
reproduced the session's metrics exactly (ledger error 0.1323,
override rate 0.0008, 1 manual override). One defect was found and
fixed by that test: claim ids are minted fresh in every trial, so
replay resolves overrides by their stable display number rather
than by the recording run's ids.

---

## Results

*Not yet run. When the primary arm is complete, the per-seed table,
the bar verdict under the frozen rules above, and any deviations
are recorded here, and the results JSON is committed alongside.*
