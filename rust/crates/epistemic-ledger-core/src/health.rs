//! Health reporting (DESIGN-13 section 2.4): a plain-values
//! snapshot of the store's state, computed read-only. The report
//! must never claim clean over damage — it surfaces the torn
//! tail and lock state it actually observed.

use std::fs::OpenOptions;
use std::path::Path;

use fs2::FileExt;
use serde::Serialize;

use crate::checkpoint::{checkpoint_for, Checkpoint, DEFAULT_SEGMENT};
use crate::store::Store;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct HealthReport {
    pub format_version: u32,
    pub events: u64,
    pub head_hash: String,
    /// True while a writer holds the store's lock.
    pub lock_held: bool,
    /// Torn-tail bytes observed by the read-only scan (0 = clean).
    pub torn_tail_bytes: u64,
    /// Complete checkpoints covering the log, oldest first.
    pub checkpoints: Vec<Checkpoint>,
    /// Events appended after the last complete checkpoint.
    pub events_since_checkpoint: u64,
    /// Records in the (not yet checkpointed) tail segment whose
    /// hashes feed the next checkpoint.
    pub latest_checkpoint_root: Option<String>,
}

pub fn health(dir: &Path) -> std::io::Result<HealthReport> {
    health_with_segment(dir, DEFAULT_SEGMENT)
}

pub fn health_with_segment(dir: &Path, segment: u64) -> std::io::Result<HealthReport> {
    let (records, report) =
        Store::open_readonly(dir).map_err(|e| std::io::Error::other(e.to_string()))?;
    // Probe the writer lock without holding it.
    let lock_held = match OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(false)
        .open(dir.join("ledger.lock"))
    {
        Ok(f) => match f.try_lock_exclusive() {
            Ok(()) => {
                let _ = f.unlock();
                false
            }
            Err(_) => true,
        },
        Err(_) => false,
    };
    let mut checkpoints = Vec::new();
    let mut prev_root = crate::checkpoint::merkle_root(&[]).to_vec();
    let hashes: Vec<[u8; 32]> = records
        .iter()
        .map(|r| {
            let b = hex::decode(&r.hash).unwrap_or_default();
            let mut a = [0u8; 32];
            a.copy_from_slice(&b[..32.min(b.len())]);
            a
        })
        .collect();
    let seg = (segment.max(1)) as usize;
    let mut first = 1u64;
    for chunk in hashes.chunks(seg) {
        if chunk.len() == seg {
            let cp = checkpoint_for(first, chunk, &hex::encode(prev_root));
            prev_root = hex::decode(&cp.root).unwrap_or_default();
            checkpoints.push(cp);
            first += seg as u64;
        }
    }
    let covered: u64 = checkpoints.len() as u64 * segment;
    Ok(HealthReport {
        format_version: 1,
        events: report.events,
        head_hash: report.head_hash,
        lock_held,
        torn_tail_bytes: report.recovered_torn_bytes,
        latest_checkpoint_root: checkpoints.last().map(|c| c.root.clone()),
        events_since_checkpoint: report.events - covered,
        checkpoints,
    })
}
