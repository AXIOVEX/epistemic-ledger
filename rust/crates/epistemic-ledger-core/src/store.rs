//! The store: an append-only `events.log` of chained records
//! (chain format v1) with single-writer locking, torn-tail
//! recovery on open, and full verification on demand.
//! Implements DESIGN-13 sections 2.1-2.2 (claims E1/E2 at the
//! storage layer).

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, Write};
use std::path::{Path, PathBuf};

use ed25519_dalek::SigningKey;
use fs2::FileExt;
use serde_json::Value;

use crate::chain::{
    build_record, chain_line, parse_line, verify_chain, ChainError, Record, GENESIS_PREV,
};

#[derive(Debug)]
pub enum StoreError {
    Io(std::io::Error),
    Locked,
    Chain(ChainError),
    TornMiddle { line: usize },
}

impl fmt::Display for StoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StoreError::Io(e) => write!(f, "io error: {e}"),
            StoreError::Locked => write!(f, "store is already open by another writer"),
            StoreError::Chain(e) => write!(f, "{e}"),
            StoreError::TornMiddle { line } => {
                write!(f, "log line {line} is damaged and is not the tail")
            }
        }
    }
}
impl std::error::Error for StoreError {}
impl From<std::io::Error> for StoreError {
    fn from(e: std::io::Error) -> Self {
        StoreError::Io(e)
    }
}
impl From<ChainError> for StoreError {
    fn from(e: ChainError) -> Self {
        StoreError::Chain(e)
    }
}

use std::fmt;

/// Outcome of opening a store, including any recovery performed.
#[derive(Debug, Default, Clone, PartialEq, Eq, serde::Serialize)]
pub struct OpenReport {
    pub events: u64,
    pub head_hash: String,
    /// Bytes of torn tail truncated during this open (0 = clean).
    pub recovered_torn_bytes: u64,
}

#[derive(Debug)]
pub struct Store {
    dir: PathBuf,
    log: File,
    lock: File,
    next_seq: u64,
    head_hash: String,
    pub report: OpenReport,
}

impl Store {
    pub fn log_path(dir: &Path) -> PathBuf {
        dir.join("events.log")
    }

    /// Open (creating if needed) the store at `dir`, taking the
    /// single-writer lock. The log is scanned on open: sequence
    /// and prev-hash linkage are checked for every record, and a
    /// torn final line (crash mid-append) is truncated — the store
    /// recovers to the last complete record and says so in the
    /// report. Hash recomputation is `verify`'s job, not open's
    /// (the open-time budget in DESIGN-13 section 8 forbids it).
    pub fn open(dir: &Path) -> Result<Store, StoreError> {
        std::fs::create_dir_all(dir)?;
        let lock = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(false)
            .open(dir.join("ledger.lock"))?;
        lock.try_lock_exclusive().map_err(|_| StoreError::Locked)?;
        let log_path = Self::log_path(dir);
        let mut log = OpenOptions::new()
            .create(true)
            .read(true)
            .append(true)
            .truncate(false)
            .open(&log_path)?;
        let mut raw = Vec::new();
        log.rewind()?;
        log.read_to_end(&mut raw)?;
        let (records, torn_bytes) = scan_log(&raw)?;
        if torn_bytes > 0 {
            let keep = raw.len() as u64 - torn_bytes;
            log.set_len(keep)?;
            log.sync_all()?;
        }
        let head_hash = records
            .last()
            .map(|r| r.hash.clone())
            .unwrap_or_else(|| GENESIS_PREV.to_string());
        let report = OpenReport {
            events: records.len() as u64,
            head_hash: head_hash.clone(),
            recovered_torn_bytes: torn_bytes,
        };
        Ok(Store {
            dir: dir.to_path_buf(),
            log,
            lock,
            next_seq: records.len() as u64 + 1,
            head_hash,
            report,
        })
    }

    /// Open read-only: no lock taken, no truncation, no writes of
    /// any kind. A torn tail is reported, not repaired.
    pub fn open_readonly(dir: &Path) -> Result<(Vec<Record>, OpenReport), StoreError> {
        let log_path = Self::log_path(dir);
        let raw = std::fs::read(&log_path).unwrap_or_default();
        let (records, torn_bytes) = scan_log(&raw)?;
        let head_hash = records
            .last()
            .map(|r| r.hash.clone())
            .unwrap_or_else(|| GENESIS_PREV.to_string());
        let events = records.len() as u64;
        Ok((
            records,
            OpenReport {
                events,
                head_hash,
                recovered_torn_bytes: torn_bytes,
            },
        ))
    }

    /// Append one event: build the chained (and optionally signed)
    /// record, write its line, fsync. The log is ground truth, so
    /// the append is durable before this returns.
    pub fn append(
        &mut self,
        t: &str,
        actor: &str,
        etype: &str,
        payload: Value,
        signing_key: Option<&SigningKey>,
    ) -> Result<Record, StoreError> {
        let record = build_record(
            self.next_seq,
            t,
            actor,
            etype,
            payload,
            &self.head_hash,
            signing_key,
        );
        let line = chain_line(&record);
        self.log.write_all(line.as_bytes())?;
        self.log.write_all(b"\n")?;
        self.log.sync_all()?;
        self.head_hash = record.hash.clone();
        self.next_seq += 1;
        self.report.events += 1;
        self.report.head_hash = self.head_hash.clone();
        Ok(record)
    }

    /// Full verification: parse the whole log from disk and check
    /// sequence, linkage, hashes, CRCs, and (for actors present in
    /// `pubkeys`) signatures. Complete, not sampled (claim H4).
    pub fn verify(&self, pubkeys: &HashMap<String, [u8; 32]>) -> Result<u64, StoreError> {
        let raw = std::fs::read(Self::log_path(&self.dir))?;
        let (records, torn) = scan_log(&raw)?;
        if torn > 0 {
            return Err(StoreError::TornMiddle { line: records.len() + 1 });
        }
        verify_chain(&records, pubkeys)?;
        Ok(records.len() as u64)
    }

    pub fn next_seq(&self) -> u64 {
        self.next_seq
    }

    pub fn head_hash(&self) -> &str {
        &self.head_hash
    }
}

impl Drop for Store {
    fn drop(&mut self) {
        let _ = self.lock.unlock();
    }
}

/// Scan raw log bytes into records. Returns the records and the
/// byte count of a torn tail (an incomplete or CRC-failing final
/// line). Damage anywhere but the tail is an error — silently
/// skipping a middle record would rewrite history.
fn scan_log(raw: &[u8]) -> Result<(Vec<Record>, u64), StoreError> {
    let text = String::from_utf8_lossy(raw);
    let mut records = Vec::new();
    let mut prev = GENESIS_PREV.to_string();
    let mut torn = 0u64;
    let ends_with_newline = raw.is_empty() || raw.ends_with(b"\n");
    let lines: Vec<&str> = text.lines().collect();
    for (i, line) in lines.iter().enumerate() {
        let is_last = i == lines.len() - 1;
        match parse_line(line) {
            Ok(r) => {
                if r.seq != records.len() as u64 + 1 || r.prev_hash != prev {
                    if is_last && !ends_with_newline {
                        torn = line.len() as u64;
                        break;
                    }
                    return Err(StoreError::TornMiddle { line: i + 1 });
                }
                prev = r.hash.clone();
                records.push(r);
            }
            Err(_) => {
                if is_last {
                    torn = line.len() as u64 + if ends_with_newline { 1 } else { 0 };
                    break;
                }
                return Err(StoreError::TornMiddle { line: i + 1 });
            }
        }
    }
    Ok((records, torn))
}
