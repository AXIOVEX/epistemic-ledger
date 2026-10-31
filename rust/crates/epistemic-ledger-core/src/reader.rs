//! Verified point reads over the chained store's log
//! (DESIGN-16, the claim S4 resolution).
//!
//! The store's other read paths materialize every record —
//! right for verification and export, wrong for a reader that
//! wants one record from a growing log: the nightly stress
//! tier measured a whole-log read per query at p99 760 ms on a
//! ~300k-record store, and the latency half of S4 failed while
//! its integrity half held. This module is the point-read
//! surface the claim is measured against:
//!
//! - [`StoreReader`] opens `events.log` read-only — no lock
//!   file, no writes, no repair — so any number of readers can
//!   sit beside the single writer.
//! - Opening builds a byte-offset index (8 bytes per record;
//!   the records themselves are not kept) by scanning the log
//!   under the store's own rules: `chain::parse_line` plus
//!   sequence / previous-hash linkage. A bad line that is not
//!   the final line is [`StoreError::TornMiddle`]; a partial
//!   or bad final line simply ends the index — it is the
//!   writer's in-flight append, not yet a record.
//! - [`StoreReader::refresh`] extends the index by scanning
//!   only the bytes appended since the last scan, under the
//!   same rules. When nothing was appended it costs one
//!   metadata check.
//! - [`StoreReader::record_at`] seeks to one line, parses it,
//!   and recomputes the record's hash in the core before
//!   returning it: a mismatch is an error, never a returned
//!   record. A point read is a verified point read.
//!
//! What this is not: per-read signature checks stay with the
//! full-chain `Store::verify`, and a reader is a view of the
//! longest valid prefix of the log, not an auditor.

use std::fs::File;
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use crate::chain::{parse_line, record_hash, ChainError, ChainErrorKind, Record, GENESIS_PREV};
use crate::store::{Store, StoreError};

#[derive(Debug)]
pub struct StoreReader {
    dir: PathBuf,
    /// Byte offset of each record's line start; `offsets[i]`
    /// is where record `i + 1` begins.
    offsets: Vec<u64>,
    /// Bytes of the log covered by the index — the end of the
    /// last complete, verified line. Refresh resumes here.
    indexed_len: u64,
    /// Hash of the last indexed record (the indexed prefix's
    /// head), or the genesis previous-hash when empty.
    head_hash: String,
}

impl StoreReader {
    /// Open a store directory for point reads and build the
    /// offset index. The directory need not exist yet as a
    /// store: a missing log reads as an empty store.
    pub fn open(dir: &Path) -> Result<StoreReader, StoreError> {
        let mut reader = StoreReader {
            dir: dir.to_path_buf(),
            offsets: Vec::new(),
            indexed_len: 0,
            head_hash: GENESIS_PREV.to_string(),
        };
        reader.refresh()?;
        Ok(reader)
    }

    /// Records in the indexed prefix.
    pub fn count(&self) -> u64 {
        self.offsets.len() as u64
    }

    /// Hash of the last indexed record.
    pub fn head_hash(&self) -> &str {
        &self.head_hash
    }

    /// Extend the index over any bytes appended since the last
    /// scan. Returns the indexed record count. If the log
    /// shrank under the reader — a writer's verified rollback
    /// truncating in place, or the store replaced wholesale —
    /// the index no longer describes the file and is rebuilt
    /// from zero rather than serving offsets into a different
    /// history.
    pub fn refresh(&mut self) -> Result<u64, StoreError> {
        let log_path = Store::log_path(&self.dir);
        let mut file = match File::open(&log_path) {
            Ok(f) => f,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(self.count()),
            Err(e) => return Err(StoreError::Io(e)),
        };
        let len = file.metadata()?.len();
        if len < self.indexed_len {
            self.offsets.clear();
            self.indexed_len = 0;
            self.head_hash = GENESIS_PREV.to_string();
        }
        if len == self.indexed_len {
            return Ok(self.count());
        }
        file.seek(SeekFrom::Start(self.indexed_len))?;
        let mut raw = Vec::new();
        file.read_to_end(&mut raw)?;
        let consumed = scan_region(
            &raw,
            self.indexed_len,
            &mut self.offsets,
            &mut self.head_hash,
        )?;
        self.indexed_len += consumed;
        Ok(self.count())
    }

    /// Read one record by sequence number, verifying its hash
    /// in the core before returning it. `Ok(None)` when `seq`
    /// is outside `1..=count`. `seq == 0` is outside.
    pub fn record_at(&self, seq: u64) -> Result<Option<Record>, StoreError> {
        if seq == 0 || seq > self.count() {
            return Ok(None);
        }
        let log_path = Store::log_path(&self.dir);
        let mut file = File::open(&log_path)?;
        file.seek(SeekFrom::Start(self.offsets[(seq - 1) as usize]))?;
        let mut line = String::new();
        BufReader::new(file).read_line(&mut line)?;
        let line = line.trim_end_matches(['\n', '\r']);
        let record = parse_line(line).map_err(|e| {
            StoreError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("point read at seq {seq}: indexed line no longer parses: {e}"),
            ))
        })?;
        let recomputed = record_hash(
            record.seq,
            &record.t,
            &record.actor,
            &record.etype,
            &record.payload,
            &record.prev_hash,
        );
        if record.seq != seq || recomputed != record.hash {
            return Err(StoreError::Chain(ChainError {
                seq,
                kind: ChainErrorKind::BadHash,
            }));
        }
        Ok(Some(record))
    }
}

/// Scan one region of log bytes (starting at absolute offset
/// `base`, with the chain's expected head in `head`), pushing
/// each complete record's absolute offset onto `offsets`.
/// Returns the bytes consumed — up to the end of the last
/// complete, valid line. A trailing partial line is left
/// unconsumed. Any other bad line errors as
/// [`StoreError::TornMiddle`], mirroring `scan_log`: damage is
/// loud, never silently skipped.
fn scan_region(
    raw: &[u8],
    base: u64,
    offsets: &mut Vec<u64>,
    head: &mut String,
) -> Result<u64, StoreError> {
    let mut consumed = 0usize;
    let mut pos = 0usize;
    while let Some(nl) = raw[pos..].iter().position(|&b| b == b'\n') {
        let line_start = pos;
        let line_bytes = &raw[pos..pos + nl];
        pos += nl + 1;
        let text = String::from_utf8_lossy(line_bytes);
        let line = text.strip_suffix('\r').unwrap_or(&*text);
        let expected = offsets.len() as u64 + 1;
        let record = parse_line(line)
            .map_err(|_| StoreError::TornMiddle { line: expected as usize })?;
        if record.seq != expected || record.prev_hash != *head {
            return Err(StoreError::TornMiddle {
                line: expected as usize,
            });
        }
        offsets.push(base + line_start as u64);
        *head = record.hash.clone();
        consumed = pos;
    }
    Ok(consumed as u64)
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
            "el-reader-test-{}-{tag}-{n}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        dir
    }

    fn build_store(dir: &Path, n: u64) -> Vec<Record> {
        let mut store = Store::open(dir).unwrap();
        let mut out = Vec::new();
        for i in 0..n {
            out.push(
                store
                    .append(
                        "2026-01-01T00:00:00Z",
                        "alice",
                        "assert",
                        json!({"i": i}),
                        None,
                    )
                    .unwrap(),
            );
        }
        out
    }

    #[test]
    fn index_and_point_reads_match_the_full_scan() {
        let dir = temp_store_dir("match");
        let records = build_store(&dir, 50);
        let reader = StoreReader::open(&dir).unwrap();
        assert_eq!(reader.count(), 50);
        assert_eq!(reader.head_hash(), records[49].hash);
        for (i, want) in records.iter().enumerate() {
            let got = reader.record_at(i as u64 + 1).unwrap().unwrap();
            assert_eq!(&got, want);
        }
        assert_eq!(reader.record_at(0).unwrap(), None);
        assert_eq!(reader.record_at(51).unwrap(), None);
    }

    #[test]
    fn refresh_picks_up_appends_and_ignores_a_torn_tail() {
        let dir = temp_store_dir("refresh");
        let mut store = Store::open(&dir).unwrap();
        let first = store
            .append("2026-01-01T00:00:00Z", "alice", "assert", json!({"i": 0}), None)
            .unwrap();
        let mut reader = StoreReader::open(&dir).unwrap();
        assert_eq!(reader.count(), 1);
        let second = store
            .append("2026-01-01T00:01:00Z", "alice", "assert", json!({"i": 1}), None)
            .unwrap();
        assert_eq!(reader.refresh().unwrap(), 2);
        assert_eq!(reader.record_at(2).unwrap().unwrap(), second);
        drop(store);
        // Simulate the writer mid-append: half of the third
        // record's line, no newline. Not a record yet.
        let third = crate::chain::build_record(
            3,
            "2026-01-01T00:02:00Z",
            "alice",
            "assert",
            json!({"i": 2}),
            &second.hash,
            None,
        );
        let third_line = crate::chain::chain_line(&third);
        let log_path = Store::log_path(&dir);
        let mut bytes = Vec::new();
        for r in [&first, &second] {
            bytes.extend_from_slice(crate::chain::chain_line(r).as_bytes());
            bytes.push(b'\n');
        }
        let mut torn = bytes.clone();
        torn.extend_from_slice(&third_line.as_bytes()[..third_line.len() / 2]);
        std::fs::write(&log_path, &torn).unwrap();
        assert_eq!(reader.refresh().unwrap(), 2);
        // The append completes: the full line lands.
        bytes.extend_from_slice(third_line.as_bytes());
        bytes.push(b'\n');
        std::fs::write(&log_path, &bytes).unwrap();
        assert_eq!(reader.refresh().unwrap(), 3);
        assert_eq!(reader.record_at(3).unwrap().unwrap(), third);
    }

    #[test]
    fn middle_damage_is_loud_not_skipped() {
        let dir = temp_store_dir("damage");
        build_store(&dir, 6);
        let log_path = Store::log_path(&dir);
        let raw = std::fs::read(&log_path).unwrap();
        let mut lines: Vec<&[u8]> = raw.split(|&b| b == b'\n').collect();
        // Corrupt a byte inside the third line's JSON (the CRC
        // no longer matches, so the line fails to parse).
        let mut third = lines[2].to_vec();
        let at = 15;
        third[at] = if third[at] == b'a' { b'b' } else { b'a' };
        lines[2] = &third;
        let mut joined = Vec::new();
        for (i, l) in lines.iter().enumerate() {
            if i > 0 {
                joined.push(b'\n');
            }
            joined.extend_from_slice(l);
        }
        std::fs::write(&log_path, &joined).unwrap();
        let err = StoreReader::open(&dir).expect_err("middle damage must be loud");
        assert!(matches!(err, StoreError::TornMiddle { line: 3 }), "{err}");
    }

    #[test]
    fn a_rewritten_line_with_a_valid_crc_but_wrong_hash_is_refused() {
        let dir = temp_store_dir("badhash");
        build_store(&dir, 4);
        let reader = StoreReader::open(&dir).unwrap();
        // Rewrite record 2's line carrying a hash that does not
        // recompute, with the CRC fixed up so the line parses.
        let mut forged = crate::chain::build_record(
            2,
            "2026-01-01T00:00:00Z",
            "alice",
            "assert",
            json!({"i": 999}),
            reader.record_at(1).unwrap().unwrap().hash.as_str(),
            None,
        );
        forged.hash = "f".repeat(64);
        forged.sig = None;
        let log_path = Store::log_path(&dir);
        let text = std::fs::read_to_string(&log_path).unwrap();
        let mut lines: Vec<&str> = text.lines().collect();
        let forged_line = crate::chain::chain_line(&forged);
        lines[1] = &forged_line;
        std::fs::write(&log_path, lines.join("\n") + "\n").unwrap();
        let err = reader
            .record_at(2)
            .expect_err("a hash that does not recompute must be refused");
        assert!(matches!(err, StoreError::Chain(_)), "{err}");
    }
}
