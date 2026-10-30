"""Tenant partitions (DESIGN-15 D1, claim T1).

A tenant partition is physical: one directory holding one store,
under a partitions root. This module is the guarded convention,
mirroring the Rust core's rule exactly: tenant ids are slugs
(1-64 chars of [a-z0-9-], starting alphanumeric), and a partition
directory is always strictly inside the root it was opened under,
so no caller-supplied id can reach another tenant's directory.
"""

from __future__ import annotations

import os
import re

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def validate_tenant_id(tenant_id: str) -> str:
    """Return ``tenant_id`` if it is a valid tenant slug; raise
    ValueError otherwise. No dots, no separators, no traversal —
    refused by construction, not filtered after the fact."""
    if not isinstance(tenant_id, str) or _SLUG.fullmatch(tenant_id) is None:
        raise ValueError(
            f"invalid tenant id {tenant_id!r}: 1-64 chars of [a-z0-9-], "
            "starting alphanumeric"
        )
    return tenant_id


def partition_dir(root: str, tenant_id: str) -> str:
    """The directory of one tenant's partition under ``root``.
    The slug rule makes escape impossible; the containment check
    stays as defense in depth, mirroring the core."""
    validate_tenant_id(tenant_id)
    root_norm = os.path.normpath(root)
    joined = os.path.join(root_norm, tenant_id)
    if os.path.dirname(joined) != root_norm:
        raise ValueError(
            f"tenant id {tenant_id!r} resolves outside the partitions root"
        )
    return joined
