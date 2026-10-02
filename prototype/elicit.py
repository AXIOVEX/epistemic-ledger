"""Likelihood elicitation for human-entered evidence.

Open item from Design Memo 01 §9, settled v0.6. The revisit loop needs
P(claim | support) and P(claim | ~support), but humans don't think in
likelihoods. This module documents the elicitation procedure and provides
the mechanical conversion.

Procedure (for the human or the interviewing agent):
  1. State the claim and the piece of evidence in one sentence each.
  2. Ask Q1: "Suppose the evidence is TRUE. How likely is the claim?"
  3. Ask Q2: "Suppose the evidence is FALSE (or absent). How likely is the
     claim then?"  (This is the base rate under ~evidence — the question
     people forget, and the one that prevents double-counting.)
  4. Map each answer through the anchored verbal scale below.
  5. Sanity check: Q1 >= Q2 for supporting evidence. If not, the
     "evidence" is actually counter-evidence — flip the edge or
     re-examine the claim.

The verbal anchors are conventional (not calibrated to any individual):
use them as a shared starting point, not a psychometric claim.

  almost certain   0.95
  very likely      0.85
  likely           0.70
  toss-up          0.50
  unlikely         0.30
  very unlikely    0.15
  almost impossible 0.05
"""

VERBAL_ANCHORS = {
    "almost certain": 0.95,
    "very likely": 0.85,
    "likely": 0.70,
    "toss-up": 0.50,
    "unlikely": 0.30,
    "very unlikely": 0.15,
    "almost impossible": 0.05,
}


def verbal_to_p(word):
    """Map a verbal likelihood to a number. Raises KeyError on unknown
    words — silent guessing here would corrupt the likelihoods."""
    key = word.strip().lower()
    if key not in VERBAL_ANCHORS:
        raise KeyError(f"unknown anchor {word!r}; choose from "
                       f"{sorted(VERBAL_ANCHORS)}")
    return VERBAL_ANCHORS[key]


def elicit_pair(q1_word, q2_word):
    """Convert the two elicitation answers to (p_given, p_given_not).

    q1: "evidence true -> claim?" ; q2: "evidence false -> claim?".
    Warns (does not raise) when q1 < q2 — that pattern means the edge
    is counter-evidence, and the caller should flip or re-examine."""
    import warnings
    p_given = verbal_to_p(q1_word)
    p_given_not = verbal_to_p(q2_word)
    if p_given < p_given_not:
        warnings.warn(
            f"p_given ({p_given}) < p_given_not ({p_given_not}): this is "
            "counter-evidence, not support — flip the edge or re-examine")
    return p_given, p_given_not
