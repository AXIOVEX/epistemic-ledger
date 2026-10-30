//! The store: an append-only `events.log` of chained records
//! (chain format v1) with single-writer locking, torn-tail
//! recovery on open, and full verification on demand.
//! Implements DESIGN-13 sections 2.1-2.2 (claims E1/E2 at the
//! storage layer).

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use ed25519_dalek::SigningKey;
use fs2::FileExt;
use serde_json::Value;

use crate::chain::{
    build_record, chain_line, parse_line, verify_chain_from, ChainError, Record, GENESIS_PREV,
};
use crate::checkpoint::{checkpoints_for_records, Checkpoint, DEFAULT_SEGMENT};
use crate::governance::{self, GovernanceReport};

#[derive(Debug)]
pub enum StoreError {
    Io(std::io::Error),
    Locked,
    Chain(ChainError),
    TornMiddle { line: usize },
    /// Governed verification found enrollment-window violations
    /// (DESIGN-15 D3); the strings are the report's violations, in
    /// sequence order.
    Governance(Vec<String>),
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
            StoreError::Governance(violations) => {
                write!(f, "governance violations: {}", violations.join("; "))
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
    /// Byte length of the log as last verified (open scan, or a
    /// read-back-verified append). Appends verify against it.
    log_len: u64,
    pub report: OpenReport,
}

/// Confirm a file's length is exactly `want`. The torn-tail
/// repair in `Store::open` is a write, and a write is not done
/// until it is verified (DESIGN-14 W4).
fn verify_file_len(file: &File, want: u64) -> Result<(), StoreError> {
    let got = file.metadata()?.len();
    if got != want {
        return Err(StoreError::Io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("log length is {got} after repair, expected {want}; repair unverified"),
        )));
    }
    Ok(())
}

/// Fault injection for tests (DESIGN-14 section 3.5): simulates
/// the silent-short-write defect by mangling the bytes an append
/// actually lands, so the production read-back and rollback run
/// against a genuinely wrong file. Compiled only under
/// `cfg(test)`; the mode is thread-local so parallel tests do
/// not leak modes into each other, and a test must run its store
/// operations on the thread that set the mode.
#[cfg(test)]
pub(crate) mod fault {
    use std::cell::Cell;

    thread_local! {
        pub static APPEND_MODE: Cell<u8> = const { Cell::new(0) };
    }

    pub const OFF: u8 = 0;
    pub const TRUNCATE: u8 = 1;
    pub const ZERO: u8 = 2;

    pub fn set_append_mode(mode: u8) {
        APPEND_MODE.with(|m| m.set(mode));
    }

    pub fn mangle_append(bytes: Vec<u8>) -> Vec<u8> {
        match APPEND_MODE.with(|m| m.get()) {
            TRUNCATE => bytes[..bytes.len() / 2].to_vec(),
            ZERO => vec![0u8; bytes.len()],
            _ => bytes,
        }
    }
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
            verify_file_len(&log, keep)?;
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
            log_len: raw.len() as u64 - torn_bytes,
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
    /// record, write its line, fsync — then read the appended
    /// bytes back and compare them before the record counts as
    /// committed (DESIGN-14 W2). The log is ground truth, and a
    /// write is not done until it is verified: the platform this
    /// engine runs on can land a write short or empty while
    /// reporting success, which fsync cannot see. A landing that
    /// verifies short, empty, or corrupted is rolled back — the
    /// log is truncated to its pre-append length and fsynced, so
    /// a partial record never stands — and the append returns an
    /// error. Sequence and head advance only for a verified
    /// record.
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
        let mut expected = chain_line(&record).into_bytes();
        expected.push(b'\n');
        #[cfg(test)]
        let to_write = fault::mangle_append(expected.clone());
        #[cfg(not(test))]
        let to_write = expected.clone();
        self.log.write_all(&to_write)?;
        self.log.sync_all()?;
        if !self.verify_tail(&expected)? {
            // Roll back so the unverified record never stands.
            let rolled_back = self
                .log
                .set_len(self.log_len)
                .and_then(|_| self.log.sync_all())
                .is_ok();
            let _ = self.log.seek(SeekFrom::End(0));
            return Err(StoreError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                if rolled_back {
                    format!(
                        "append of seq {} failed read-back verification; \
                         the record was rolled back and is NOT committed",
                        record.seq
                    )
                } else {
                    format!(
                        "append of seq {} failed read-back verification AND \
                         the rollback truncation failed; the log tail must \
                         be treated as torn",
                        record.seq
                    )
                },
            )));
        }
        self.log_len += expected.len() as u64;
        self.head_hash = record.hash.clone();
        self.next_seq += 1;
        self.report.events += 1;
        self.report.head_hash = self.head_hash.clone();
        Ok(record)
    }

    /// Read back the record just appended — the bytes starting at
    /// the tracked log length — and compare them with what was
    /// written; also confirm the file's total length. Restores
    /// the file position to end-of-log either way.
    fn verify_tail(&mut self, expected: &[u8]) -> Result<bool, StoreError> {
        let mut back = vec![0u8; expected.len()];
        let read_ok = self
            .log
            .seek(SeekFrom::Start(self.log_len))
            .and_then(|_| self.log.read_exact(&mut back))
            .is_ok();
        let len_ok = matches!(
            self.log.metadata(),
            Ok(m) if m.len() == self.log_len + expected.len() as u64
        );
        let _ = self.log.seek(SeekFrom::End(0));
        Ok(read_ok && len_ok && back == expected)
    }

    /// Full verification: parse the whole log from disk and check
    /// sequence, linkage, hashes, CRCs, and (for actors present in
    /// `pubkeys`) signatures. Complete, not sampled (claim H4).
    pub fn verify(&self, pubkeys: &HashMap<String, [u8; 32]>) -> Result<u64, StoreError> {
        self.verify_from(pubkeys, 1)
    }

    /// Full verification where signatures are required only for
    /// records at or after `signed_from_seq` (migrated stores,
    /// DESIGN-13 section 9).
    pub fn verify_from(
        &self,
        pubkeys: &HashMap<String, [u8; 32]>,
        signed_from_seq: u64,
    ) -> Result<u64, StoreError> {
        let raw = std::fs::read(Self::log_path(&self.dir))?;
        let (records, torn) = scan_log(&raw)?;
        if torn > 0 {
            return Err(StoreError::TornMiddle { line: records.len() + 1 });
        }
        verify_chain_from(&records, pubkeys, signed_from_seq)?;
        Ok(records.len() as u64)
    }

    /// All records currently in the log, in chain order. A torn
    /// tail at this point means another writer damaged the log
    /// after open — reported as TornMiddle rather than silently
    /// truncating history the open scan had accepted.
    pub fn records(&self) -> Result<Vec<Record>, StoreError> {
        let raw = std::fs::read(Self::log_path(&self.dir))?;
        let (records, torn) = scan_log(&raw)?;
        if torn > 0 {
            return Err(StoreError::TornMiddle {
                line: records.len() + 1,
            });
        }
        Ok(records)
    }

    /// The checkpoint set over the log at the canonical segment
    /// (DESIGN-15 D2: signed tree heads are issued per checkpoint,
    /// at this segment, whatever segment a health report used).
    pub fn checkpoints(&self) -> Result<Vec<Checkpoint>, StoreError> {
        Ok(checkpoints_for_records(&self.records()?, DEFAULT_SEGMENT))
    }

    /// The governance report over the current log (DESIGN-15 D3):
    /// every key's enrollment windows and every violation, folded
    /// in sequence order against the genesis key the caller holds
    /// out of band.
    pub fn governance_report(
        &self,
        genesis_key_id: &str,
        genesis_pubkey: &[u8; 32],
    ) -> Result<GovernanceReport, StoreError> {
        Ok(governance::evaluate(
            &self.records()?,
            genesis_key_id,
            genesis_pubkey,
        ))
    }

    /// Governed verification (DESIGN-15 D3, claim T1): the full
    /// chain plus enrollment windows — every record signed inside
    /// its key's window, every governance record authorized. Plain
    /// `verify` keeps its semantics; governance is additive.
    /// Returns the record count on success.
    pub fn verify_governed(
        &self,
        genesis_key_id: &str,
        genesis_pubkey: &[u8; 32],
    ) -> Result<u64, StoreError> {
        let records = self.records()?;
        let report = governance::evaluate(&records, genesis_key_id, genesis_pubkey);
        if report.violations.is_empty() {
            Ok(records.len() as u64)
        } else {
            Err(StoreError::Governance(report.violations))
        }
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::atomic::{AtomicU64, Ordering};

    fn temp_store_dir(tag: &str) -> PathBuf {
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let dir = std::env::temp_dir().join(format!(
            "el-store-test-{}-{tag}-{n}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    /// DESIGN-14 W2 falsifier, driven for each fault mode: an
    /// append whose bytes land truncated or zeroed must error,
    /// must not advance sequence or head, and — the rollback
    /// having truncated the partial record — must leave a log
    /// that reopens with zero torn bytes and the pre-append
    /// record count. A later healthy append then takes the
    /// sequence number the failed one would have taken.
    fn fault_mode_rolls_back(mode: u8) {
        let dir = temp_store_dir("fault");
        let mut store = Store::open(&dir).unwrap();
        let first = store
            .append("2026-01-01T00:00:00Z", "alice", "assert", json!({"n": 1}), None)
            .unwrap();
        assert_eq!(store.next_seq(), 2);
        fault::set_append_mode(mode);
        let err = store
            .append("2026-01-01T00:01:00Z", "alice", "assert", json!({"n": 2}), None)
            .expect_err("a mangled landing must not return Ok");
        fault::set_append_mode(fault::OFF);
        assert!(
            err.to_string().contains("NOT committed"),
            "error must say the record is not committed: {err}"
        );
        assert_eq!(store.next_seq(), 2, "sequence must not advance");
        assert_eq!(store.head_hash(), first.hash, "head must not advance");
        drop(store);
        let mut store = Store::open(&dir).unwrap();
        assert_eq!(store.report.events, 1);
        assert_eq!(
            store.report.recovered_torn_bytes, 0,
            "rollback leaves no torn tail"
        );
        let second = store
            .append("2026-01-01T00:01:00Z", "alice", "assert", json!({"n": 2}), None)
            .unwrap();
        assert_eq!(second.seq, 2);
        assert_eq!(second.prev_hash, first.hash);
        drop(store);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn append_truncated_landing_rolls_back() {
        fault_mode_rolls_back(fault::TRUNCATE);
    }

    #[test]
    fn append_zeroed_landing_rolls_back() {
        fault_mode_rolls_back(fault::ZERO);
    }

    #[test]
    fn verify_file_len_accepts_exact_and_rejects_other() {
        let dir = temp_store_dir("len");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("f.bin");
        std::fs::write(&path, b"12345").unwrap();
        let f = File::open(&path).unwrap();
        assert!(verify_file_len(&f, 5).is_ok());
        assert!(verify_file_len(&f, 6).is_err());
        assert!(verify_file_len(&f, 4).is_err());
        drop(f);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
