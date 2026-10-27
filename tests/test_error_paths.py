"""Error and edge paths: validation must refuse bad input loudly, and
the refusal branches are part of the contract."""

import subprocess
import sys

import pytest

from epistemic_ledger import dempster_combine, interval_to_mass
from epistemic_ledger.ed25519 import publickey, sign, verify
from epistemic_ledger.ledger import Ledger
from epistemic_ledger.policies import credence_band_policy, ignorance_gated_policy


def test_interval_to_mass_rejects_inverted_interval():
    with pytest.raises(ValueError):
        interval_to_mass(0.8, 0.3)


def test_dempster_rejects_masses_that_do_not_sum_to_one():
    with pytest.raises(ValueError):
        dempster_combine({frozenset({"T"}): 0.5}, {frozenset({"T"}): 1.0})


def test_dempster_rejects_total_conflict():
    m1 = {frozenset({"T"}): 1.0}
    m2 = {frozenset({"F"}): 1.0}
    with pytest.raises(ValueError):
        dempster_combine(m1, m2)


def test_ed25519_rejects_tampered_signature():
    seed = bytes(range(32))
    pk = publickey(seed)
    sig = sign(seed, b"verdict: accept")
    assert verify(pk, b"verdict: accept", sig)
    assert not verify(pk, b"verdict: reject", sig)
    assert not verify(pk, b"verdict: accept", sig[:32] + bytes(32))


def test_band_policy_all_three_bands(tmp_path):
    L = Ledger(str(tmp_path / "l"))
    hi = L.assert_claim("high", 0.95)
    mid = L.assert_claim("mid", 0.5)
    lo = L.assert_claim("low", 0.05)
    assert credence_band_policy(L, hi)["action"] == "act"
    assert credence_band_policy(L, mid)["action"] == "escalate"
    assert credence_band_policy(L, lo)["action"] == "abstain"
    L.close()


class _RaisingIgnorance:
    def get_score(self, claim_id):
        return 0.5

    def ignorance(self, claim_id):
        raise KeyError("no interval")


def test_ignorance_policy_survives_missing_interval():
    out = ignorance_gated_policy(_RaisingIgnorance(), "anything")
    assert out["action"] == "act" and out["ignorance"] == 0.0


def test_unknown_claim_operations_raise(tmp_path):
    L = Ledger(str(tmp_path / "l"))
    with pytest.raises((KeyError, ValueError)):
        L.get_score("no-such-claim")
    with pytest.raises(KeyError):
        L.set_interval("no-such-claim", 0.1, 0.9)
    L.close()


def test_module_entry_point_reports_version():
    out = subprocess.run(
        [sys.executable, "-m", "epistemic_ledger", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "epistemic-ledger" in out.stdout
