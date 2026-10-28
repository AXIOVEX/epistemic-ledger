//! Store-layer tests: persistence, writer lock, torn-tail
//! recovery (claim E1), and verify naming the damaged record.

use std::collections::HashMap;
use std::io::Write;

use epistemic_ledger_core::store::{Store, StoreError};
use serde_json::json;

fn tempdir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "elc-store-{tag}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

#[test]
fn appends_persist_and_verify() {
    let dir = tempdir("persist");
    {
        let mut store = Store::open(&dir).unwrap();
        store
            .append("2026-10-27T00:00:00Z", "system", "assert", json!({"a": 1}), None)
            .unwrap();
        store
            .append("2026-10-27T00:01:00Z", "system", "assert", json!({"a": 2}), None)
            .unwrap();
        assert_eq!(store.next_seq(), 3);
    }
    let store = Store::open(&dir).unwrap();
    assert_eq!(store.report.events, 2);
    assert_eq!(store.report.recovered_torn_bytes, 0);
    assert_eq!(store.verify(&HashMap::new()).unwrap(), 2);
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn second_writer_is_refused() {
    let dir = tempdir("lock");
    let _first = Store::open(&dir).unwrap();
    match Store::open(&dir) {
        Err(StoreError::Locked) => {}
        other => panic!("expected Locked, got {other:?}"),
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn torn_tail_is_truncated_and_the_chain_continues() {
    let dir = tempdir("torn");
    let head_before;
    {
        let mut store = Store::open(&dir).unwrap();
        store
            .append("2026-10-27T00:00:00Z", "system", "assert", json!({"a": 1}), None)
            .unwrap();
        head_before = store.head_hash().to_string();
    }
    // simulate a crash mid-append: half a line, no newline
    let log_path = Store::log_path(&dir);
    let mut f = std::fs::OpenOptions::new()
        .append(true)
        .open(&log_path)
        .unwrap();
    f.write_all(b"a1b2c3d4 {\"seq\":2,\"t\":\"2026-10-27T00:0").unwrap();
    drop(f);
    {
        let mut store = Store::open(&dir).unwrap();
        assert!(store.report.recovered_torn_bytes > 0);
        assert_eq!(store.report.events, 1);
        assert_eq!(store.head_hash(), head_before);
        // the store keeps working and the chain continues from the
        // last good record
        let r = store
            .append("2026-10-27T00:02:00Z", "system", "assert", json!({"a": 2}), None)
            .unwrap();
        assert_eq!(r.seq, 2);
        assert_eq!(r.prev_hash, head_before);
        assert_eq!(store.verify(&HashMap::new()).unwrap(), 2);
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn damage_in_the_middle_is_an_error_not_a_skip() {
    let dir = tempdir("middle");
    {
        let mut store = Store::open(&dir).unwrap();
        for i in 0..3 {
            store
                .append("2026-10-27T00:00:00Z", "system", "assert", json!({"a": i}), None)
                .unwrap();
        }
    }
    // corrupt one byte inside the first line's JSON
    let log_path = Store::log_path(&dir);
    let mut raw = std::fs::read(&log_path).unwrap();
    raw[20] ^= 0x01;
    std::fs::write(&log_path, &raw).unwrap();
    // opening fails loudly (middle damage), and so does verify via
    // a read-only scan
    match Store::open(&dir) {
        Err(StoreError::TornMiddle { line: 1 }) => {}
        other => panic!("expected TornMiddle at line 1, got {other:?}"),
    }
    let _ = std::fs::remove_dir_all(&dir);
}
