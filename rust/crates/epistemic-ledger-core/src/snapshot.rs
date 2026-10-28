//! Snapshots (DESIGN-13 section 4): a self-contained bundle of a
//! chained store that verifies on its own and restores into a new
//! store. The bundle layout is specified in rust/SNAPSHOT-FORMAT.md.
//!
//! A bundle is a directory holding two files:
//!   events.log    — the store's chained log, byte for byte.
//!   manifest.json — format, event count, chain head hash, the
//!                   checkpoint set, the SHA-256 of events.log, and
//!                   a bundle hash covering all of it.
//!
//! Verification recomputes everything from the bundle alone: the
//! log's hash, the full chain (sequence, linkage, record hashes —
//! signatures are checked separately by Store::verify, with keys),
//! the checkpoint set, and the bundle hash. Any single altered
//! byte in either file fails verification before a restore begins
//! (claim R2). Honest scope: a bundle rewritten wholesale and
//! consistently is indistinguishable from a genuine one by these
//! checks — that is what the chain's signatures and external
//! anchoring of checkpoint roots are for (DESIGN-13 section 1).

use std::collections::HashMap;
use std::fmt;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::canon::canonical_json;
use crate::chain::{parse_line, verify_chain, Record};
use crate::checkpoint::{checkpoints_for_records, Checkpoint, DEFAULT_SEGMENT};
use crate::store::{Store, StoreError};

pub const SNAPSHOT_FORMAT: u32 = 1;
pub const SNAPSHOT_KIND: &str = "epistemic-ledger-snapshot";

#[derive(Debug)]
pub enum SnapshotError {
    Store(StoreError),
    Io(std::io::Error),
    /// The bundle (or a store offered for snapshotting) failed
    /// verification; the message says exactly what did not match.
    Invalid(String),
    /// The destination already holds a store or a bundle.
    Exists(String),
}

impl fmt::Display for SnapshotError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SnapshotError::Store(e) => write!(f, "store error: {e}"),
            SnapshotError::Io(e) => write!(f, "io error: {e}"),
            SnapshotError::Invalid(m) => write!(f, "invalid snapshot: {m}"),
            SnapshotError::Exists(m) => write!(f, "destination exists: {m}"),
        }
    }
}

impl std::error::Error for SnapshotError {}

impl From<StoreError> for SnapshotError {
    fn from(e: StoreError) -> Self {
        SnapshotError::Store(e)
    }
}

impl From<std::io::Error> for SnapshotError {
    fn from(e: std::io::Error) -> Self {
        SnapshotError::Io(e)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SnapshotManifest {
    pub format: u32,
    pub kind: String,
    pub events: u64,
    pub head_hash: String,
    pub segment: u64,
    pub checkpoints: Vec<Checkpoint>,
    /// SHA-256 (hex) of the bundled events.log bytes.
    pub log_sha256: String,
    /// SHA-256 (hex) over the log hash and the canonical manifest
    /// (with this field empty); see SNAPSHOT-FORMAT.md.
    pub bundle_hash: String,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct SnapshotReport {
    pub events: u64,
    pub head_hash: String,
    pub bundle_hash: String,
    pub checkpoints: usize,
}

impl SnapshotManifest {
    fn bundle_hash_for(&self) -> String {
        let mut bare = self.clone();
        bare.bundle_hash = String::new();
        let value = serde_json::to_value(&bare).expect("manifest serializes");
        let canon = canonical_json(&value);
        let mut h = Sha256::new();
        h.update(self.log_sha256.as_bytes());
        h.update(b"\n");
        h.update(canon.as_bytes());
        hex::encode(h.finalize())
    }

    fn report(&self) -> SnapshotReport {
        SnapshotReport {
            events: self.events,
            head_hash: self.head_hash.clone(),
            bundle_hash: self.bundle_hash.clone(),
            checkpoints: self.checkpoints.len(),
        }
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    hex::encode(h.finalize())
}

fn write_durable(path: &Path, bytes: &[u8]) -> Result<(), SnapshotError> {
    let mut f = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(path)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    Ok(())
}

/// Parse the bundled log bytes into records, structurally
/// verifying the full chain (sequence, linkage, record hashes).
/// Signature checks are Store::verify's job and need keys, which a
/// bundle deliberately does not carry.
fn parse_and_verify_log(raw: &[u8]) -> Result<Vec<Record>, SnapshotError> {
    let text = std::str::from_utf8(raw)
        .map_err(|_| SnapshotError::Invalid("events.log is not valid UTF-8".into()))?;
    let mut records = Vec::new();
    for (i, line) in text.lines().enumerate() {
        if line.is_empty() {
            return Err(SnapshotError::Invalid(format!(
                "events.log line {} is empty",
                i + 1
            )));
        }
        let rec = parse_line(line).map_err(|e| {
            SnapshotError::Invalid(format!("events.log line {}: {e}", i + 1))
        })?;
        records.push(rec);
    }
    verify_chain(&records, &HashMap::new())
        .map_err(|e| SnapshotError::Invalid(format!("chain verification: {e}")))?;
    Ok(records)
}

/// Write a snapshot of the store at `store_dir` into `bundle_dir`.
/// The store is opened read-only and fully verified first: a store
/// with a torn tail or a broken chain is refused, never baked into
/// a bundle. The finished bundle is verified before this returns —
/// a snapshot the engine wrote always verifies (DESIGN-13 §4).
pub fn write_snapshot(store_dir: &Path, bundle_dir: &Path) -> Result<SnapshotReport, SnapshotError> {
    if bundle_dir.join("manifest.json").exists() || bundle_dir.join("events.log").exists() {
        return Err(SnapshotError::Exists(format!(
            "{} already holds a snapshot bundle",
            bundle_dir.display()
        )));
    }
    let (records, report) = Store::open_readonly(store_dir)?;
    if report.recovered_torn_bytes > 0 {
        return Err(SnapshotError::Invalid(format!(
            "store has a torn tail of {} bytes; open it once for writing to repair it before snapshotting",
            report.recovered_torn_bytes
        )));
    }
    verify_chain(&records, &HashMap::new())
        .map_err(|e| SnapshotError::Invalid(format!("store chain verification: {e}")))?;
    let raw = std::fs::read(Store::log_path(store_dir))?;
    let mut manifest = SnapshotManifest {
        format: SNAPSHOT_FORMAT,
        kind: SNAPSHOT_KIND.to_string(),
        events: records.len() as u64,
        head_hash: report.head_hash.clone(),
        segment: DEFAULT_SEGMENT,
        checkpoints: checkpoints_for_records(&records, DEFAULT_SEGMENT),
        log_sha256: sha256_hex(&raw),
        bundle_hash: String::new(),
    };
    manifest.bundle_hash = manifest.bundle_hash_for();
    std::fs::create_dir_all(bundle_dir)?;
    write_durable(&bundle_dir.join("events.log"), &raw)?;
    let manifest_json = serde_json::to_string_pretty(&manifest).expect("manifest serializes");
    write_durable(
        &bundle_dir.join("manifest.json"),
        manifest_json.as_bytes(),
    )?;
    verify_snapshot(bundle_dir)
}

/// Verify the bundle at `bundle_dir` from the bundle alone — no
/// live store involved. Returns the bundle's report on success.
pub fn verify_snapshot(bundle_dir: &Path) -> Result<SnapshotReport, SnapshotError> {
    let manifest_bytes = std::fs::read(bundle_dir.join("manifest.json"))?;
    let manifest: SnapshotManifest = serde_json::from_slice(&manifest_bytes)
        .map_err(|e| SnapshotError::Invalid(format!("manifest.json: {e}")))?;
    if manifest.format != SNAPSHOT_FORMAT || manifest.kind != SNAPSHOT_KIND {
        return Err(SnapshotError::Invalid(format!(
            "not a format-{SNAPSHOT_FORMAT} {SNAPSHOT_KIND} bundle"
        )));
    }
    let raw = std::fs::read(bundle_dir.join("events.log"))?;
    if sha256_hex(&raw) != manifest.log_sha256 {
        return Err(SnapshotError::Invalid(
            "events.log hash does not match the manifest".into(),
        ));
    }
    if manifest.bundle_hash_for() != manifest.bundle_hash {
        return Err(SnapshotError::Invalid(
            "bundle hash does not match the manifest contents".into(),
        ));
    }
    let records = parse_and_verify_log(&raw)?;
    if records.len() as u64 != manifest.events {
        return Err(SnapshotError::Invalid(format!(
            "event count mismatch: manifest says {}, log holds {}",
            manifest.events,
            records.len()
        )));
    }
    let head = records
        .last()
        .map(|r| r.hash.clone())
        .unwrap_or_else(|| crate::chain::GENESIS_PREV.to_string());
    if head != manifest.head_hash {
        return Err(SnapshotError::Invalid(
            "chain head does not match the manifest".into(),
        ));
    }
    let expected = checkpoints_for_records(&records, manifest.segment);
    if expected != manifest.checkpoints {
        return Err(SnapshotError::Invalid(
            "checkpoint set does not match the log".into(),
        ));
    }
    Ok(manifest.report())
}

/// Restore the bundle at `bundle_dir` into a new store at
/// `dst_dir`. The bundle is fully verified before anything is
/// written (claim R2); the restored store is then opened, which
/// re-validates the chain, and its head and event count are
/// checked against the manifest before the store is handed back
/// as a report (claim R1).
pub fn restore_snapshot(bundle_dir: &Path, dst_dir: &Path) -> Result<SnapshotReport, SnapshotError> {
    let report = verify_snapshot(bundle_dir)?;
    let dst_log = Store::log_path(dst_dir);
    if dst_log.exists() {
        return Err(SnapshotError::Exists(format!(
            "{} already holds a chained store",
            dst_dir.display()
        )));
    }
    let raw = std::fs::read(bundle_dir.join("events.log"))?;
    std::fs::create_dir_all(dst_dir)?;
    write_durable(&dst_log, &raw)?;
    let store = Store::open(dst_dir)?;
    let opened = &store.report;
    if opened.events != report.events || opened.head_hash != report.head_hash {
        return Err(SnapshotError::Invalid(
            "restored store does not match the bundle manifest".into(),
        ));
    }
    Ok(report)
}
