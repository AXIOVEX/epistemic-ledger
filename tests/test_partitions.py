"""Tenant partition convention (DESIGN-15 D1, claim T1, Python side).

The slug rule and the containment rule, over the spellings an
escape would actually use. The cross-partition probe suite over
live stores lives with the bindings tests; this file pins the
path convention both engines share.
"""

from __future__ import annotations

import os

import pytest

from epistemic_ledger import partitions


@pytest.mark.parametrize(
    "tenant_id", ["acme", "tenant-1", "a", "job-corps-region-5", "0abc"]
)
def test_valid_ids_accepted(tenant_id):
    assert partitions.validate_tenant_id(tenant_id) == tenant_id


@pytest.mark.parametrize(
    "tenant_id",
    [
        "",
        "..",
        "../sibling",
        "a/b",
        "a\\b",
        ".hidden",
        "-leading-hyphen",
        "Upper",
        "under_score",
        "white space",
        "dot.name",
        "a" * 65,
    ],
)
def test_escape_spellings_refused(tenant_id):
    with pytest.raises(ValueError):
        partitions.validate_tenant_id(tenant_id)
    with pytest.raises(ValueError):
        partitions.partition_dir("/srv/partitions", tenant_id)


def test_partition_dir_stays_inside_root():
    # The root is normalized first (on Windows that also means
    # native separators); the expectation is built the same way.
    expected = os.path.join(os.path.normpath("/srv/partitions"), "acme")
    assert partitions.partition_dir("/srv/partitions", "acme") == expected
    # A trailing slash on the root changes nothing.
    assert partitions.partition_dir("/srv/partitions/", "acme") == expected
