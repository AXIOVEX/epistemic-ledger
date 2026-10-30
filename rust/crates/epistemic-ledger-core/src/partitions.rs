//! Tenant partitions (DESIGN-15 D1, claim T1).
//!
//! A tenant partition is physical: one directory holding one
//! chained store, under a partitions root. The package's part is
//! the guarded convention — tenant ids are slugs, and a partition
//! directory is always strictly inside the root it was opened
//! under, so no API path can be talked into touching another
//! tenant's directory by a crafted id.

use std::fmt;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PartitionError {
    /// The id is not a valid tenant slug.
    InvalidId(String),
    /// The resolved directory would escape the partitions root.
    EscapesRoot(String),
}

impl fmt::Display for PartitionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PartitionError::InvalidId(id) => write!(
                f,
                "invalid tenant id {id:?}: 1-64 chars of [a-z0-9-], starting alphanumeric"
            ),
            PartitionError::EscapesRoot(id) => {
                write!(f, "tenant id {id:?} resolves outside the partitions root")
            }
        }
    }
}

impl std::error::Error for PartitionError {}

/// Tenant ids are slugs: 1-64 characters of lowercase ASCII
/// letters, digits, and hyphens, starting with a letter or digit.
/// No dots, no separators, no traversal — by construction, not by
/// filtering after the fact.
pub fn validate_tenant_id(id: &str) -> Result<(), PartitionError> {
    let ok = !id.is_empty()
        && id.len() <= 64
        && id
            .chars()
            .next()
            .is_some_and(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && id
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-');
    if ok {
        Ok(())
    } else {
        Err(PartitionError::InvalidId(id.to_string()))
    }
}

/// The directory of one tenant's partition under `root`. The slug
/// rule makes escape impossible; the containment check stays as
/// defense in depth, so a future change to the rule cannot quietly
/// reopen the hole.
pub fn partition_dir(root: &Path, tenant_id: &str) -> Result<PathBuf, PartitionError> {
    validate_tenant_id(tenant_id)?;
    let dir = root.join(tenant_id);
    if dir.parent() != Some(root) {
        return Err(PartitionError::EscapesRoot(tenant_id.to_string()));
    }
    Ok(dir)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_ids_accepted() {
        for id in ["acme", "tenant-1", "a", "job-corps-region-5", "0abc"] {
            assert!(validate_tenant_id(id).is_ok(), "{id}");
        }
    }

    #[test]
    fn escape_spellings_refused() {
        for id in [
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
        ] {
            assert!(validate_tenant_id(id).is_err(), "{id:?} must be refused");
        }
        let long = "a".repeat(65);
        assert!(validate_tenant_id(&long).is_err());
    }

    #[test]
    fn partition_dir_stays_inside_root() {
        let root = Path::new("/srv/partitions");
        let dir = partition_dir(root, "acme").unwrap();
        assert_eq!(dir, Path::new("/srv/partitions/acme"));
        assert!(partition_dir(root, "..").is_err());
    }
}
