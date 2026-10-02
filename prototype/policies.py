"""Abstention policies: caller-owned, ledger-informed.

Decision (settles the Design Memo 04 open item, v0.6): the ledger does NOT
decide when to abstain. It exposes credences and D-S ignorance per claim;
the calling agent owns the abstention policy, because the cost of acting
vs. abstaining lives in the agent's task, not in the belief store. This
module ships a reference implementation and the rationale.

Why caller-owned:
- The ledger knows uncertainty (ignorance); only the caller knows stakes.
  A 0.4-ignorance claim is fine to act on when the cost of being wrong is
  low and fatal when it is high. No store-side threshold is correct.
- Policies differ by deployment (chatbot vs. medical triage); baking one
  into the kernel would force every caller to fight it.
- The ledger's job is to make ignorance *visible and queryable*
  (ignorance(), get_interval()), not to gate on it.
"""

from ledger import Ledger  # noqa: F401  (type hint only)


def ignorance_gated_policy(ledger, claim_id, threshold=0.5):
    """Reference policy: abstain when D-S ignorance exceeds threshold.

    Claims without an interval carry no ignorance measure — the policy
    treats them as measurable-zero-ignorance (documented choice: no
    interval means the caller never asked for one, not total knowledge).
    Returns a dict with the decision and its inputs; the event is the
    caller's to log.
    """
    score = ledger.get_score(claim_id)
    try:
        ig = ledger.ignorance(claim_id)
    except (KeyError, TypeError):
        ig = 0.0
    action = "abstain" if ig is not None and ig > threshold else "act"
    return {"claim_id": claim_id, "action": action,
            "ignorance": ig, "score": score, "threshold": threshold}


def credence_band_policy(ledger, claim_id, act_above=0.7, abstain_below=0.3):
    """Reference policy: act above act_above, abstain below abstain_below,
    else escalate (the middle band is 'uncertain, not ignorant')."""
    score = ledger.get_score(claim_id)
    if score >= act_above:
        action = "act"
    elif score <= abstain_below:
        action = "abstain"
    else:
        action = "escalate"
    return {"claim_id": claim_id, "action": action, "score": score,
            "act_above": act_above, "abstain_below": abstain_below}
