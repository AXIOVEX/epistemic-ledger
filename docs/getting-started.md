# Getting started

## Install

```bash
pip install epistemic-ledger
```

The package needs Python 3.10 or newer and nothing else — it runs on
the standard library alone.

## Your first ledger

A ledger lives in a directory: an append-only event log (the ground
truth) plus a database built from it (the fast way to answer
questions).

```python
from epistemic_ledger import Ledger

ledger = Ledger("my-ledger")

# State a conclusion with a starting score between 0 and 1.
safe = ledger.assert_claim("the bridge design is safe", 0.60)
ships = ledger.assert_claim("the project ships on time", 0.55)

# Record why a conclusion is held: ships-on-time rests on safety.
ledger.add_support(ships, safe, "deductive", p_given=0.90, p_given_not=0.20)

# New evidence arrives. It is itself uncertain, so it carries a score.
fact = ledger.ingest_evidence("load test passed", 0.90)["fact_id"]
ledger.add_support(safe, fact, "evidential", p_given=0.95, p_given_not=0.30)

# Ask what the ledger now believes, and why.
print(ledger.get_score(safe))
for row in ledger.why(ships):
    print(row["statement"], row["score"], row["kind"])
ledger.close()
```

When a score moves, the ledger records the move as its own event,
with a pointer to the evidence that caused it. Nothing is overwritten:
asking "what did we believe last Tuesday?" is a normal query
(`believed_at`), and "what changed since then?" is another
(`changed`).

## From the command line

```bash
epistemic-ledger demo                       # the scenario above, end to end
epistemic-ledger verify my-ledger           # check a store for tampering
epistemic-ledger kill-metrics my-ledger     # the design's self-checks, as JSON
```

`verify` re-checks the database against the event log and reports any
place they disagree — a changed score, a missing claim, a damaged log
line. It never repairs anything silently; disagreement is the finding.

## Next steps

- [Concepts](concepts.md) for the ideas — scores, revisits, intervals
  for "we don't know," contradiction handling, and governance.
- [The framing paper](PAPER.md) for the research the design came
  from, and the measured results (each result links to its report).
- [API reference](api.md) for every public class and function.
