"""Living Epistemic Ledger.

An append-only epistemic database: every conclusion carries a fluid
certainty score, and new facts trigger re-evaluation of the conclusions
they touch, plus their dependents. Nothing is ever deleted; corrections
are new records that supersede old ones.

Public API:
    Ledger            -- the ledger itself (event log + bitemporal store)
    jeffrey           -- Jeffrey conditionalization for uncertain evidence
    dempster_combine  -- Dempster's rule for belief masses
    interval_to_mass  -- convert a [belief, plausibility] interval to a mass

Submodules:
    epistemic_ledger.ledger        -- core store, revisit loop, queries
    epistemic_ledger.consolidation -- offline LLM consolidation pass
    epistemic_ledger.policies      -- caller-owned abstention policies
    epistemic_ledger.elicit        -- likelihood elicitation helpers
    epistemic_ledger.ed25519       -- vendored Ed25519 (RFC 8032) for
                                      signed governance verdicts
"""

from importlib.metadata import PackageNotFoundError, version

from .ledger import (
    CLAIM_STATUSES,
    COMBO_KINDS,
    ENTRENCHMENT_TIERS,
    GATED_ACTIONS,
    SUPPORT_KINDS,
    TERMINAL_STATUSES,
    TIER_ENTRENCHMENT,
    WRITER_TIERS,
    Ledger,
    dempster_combine,
    interval_to_mass,
    jeffrey,
)

try:
    __version__ = version("epistemic-ledger")
except PackageNotFoundError:  # source checkout without an install
    __version__ = "0+unknown"

__all__ = [
    "CLAIM_STATUSES",
    "COMBO_KINDS",
    "ENTRENCHMENT_TIERS",
    "GATED_ACTIONS",
    "SUPPORT_KINDS",
    "TERMINAL_STATUSES",
    "TIER_ENTRENCHMENT",
    "WRITER_TIERS",
    "Ledger",
    "__version__",
    "dempster_combine",
    "interval_to_mass",
    "jeffrey",
]
