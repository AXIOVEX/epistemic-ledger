//! Snapshot tests (DESIGN-13 section 4, claims R1 and R2):
//! a restored store matches the original at the snapshot's
//! sequence number, and a bundle with one altered byte fails its
//! own verification before any restore begins.

use std::collections::HashMap;

use epistemic_ledger_core::snapshot::{
    restore_snapshot, verify_snapshot, write_snapshot, SnapshotError,
};
use epistemic_ledger_core::store::Store;
use serde_json::json;

fn tempdir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("elc-snap-{tag}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

fn build_store(tag: &str, n: usize) -> std::path::PathBuf {
    let dir = tempdir(tag);
    let mut store = Store::open(&dir).unwrap();
    for i in 0..n {
        store
            .append(
                "2026-10-27T00:00:00Z",
                "system",
                "assert",
                json!({"i": i}),
                None,
            )
            .unwrap();
    }
    drop(store);
    dir
}

#[test]
fn snapshot_verify_restore_roundtrip() {
    let src = build_store("roundtrip-src", 7);
    let bundle = tempdir("roundtrip-bundle");
    let report = write_snapshot(&src, &bundle).unwrap();
    assert_eq!(report.events, 7);
    assert_eq!(verify_snapshot(&bundle).unwrap(), report);

    let dst = tempdir("roundtrip-dst");
    let restored = restore_snapshot(&bundle, &dst).unwrap();
    assert_eq!(restored, report);

    // Indistinguishable from the original at this sequence number:
    // same head, same count, same full verification result.
    let original = Store::open(&src).unwrap();
    let copy = Store::open(&dst).unwrap();
    assert_eq!(copy.report.head_hash, original.report.head_hash);
    assert_eq!(copy.report.events, original.report.events);
    assert_eq!(
        copy.verify(&HashMap::new()).unwrap(),
        original.verify(&HashMap::new()).unwrap()
    );
    // And the restored log is byte-identical.
    assert_eq!(
        std::fs::read(Store::log_path(&src)).unwrap(),
        std::fs::read(Store::log_path(&dst)).unwrap()
    );
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn empty_store_snapshots_and_restores() {
    let src = tempdir("empty-src");
    drop(Store::open(&src).unwrap());
    let bundle = tempdir("empty-bundle");
    let report = write_snapshot(&src, &bundle).unwrap();
    assert_eq!(report.events, 0);
    let dst = tempdir("empty-dst");
    assert_eq!(restore_snapshot(&bundle, &dst).unwrap(), report);
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn checkpoint_set_covers_complete_segments() {
    // 1030 records at the default 1024 segment: exactly one
    // checkpoint, and the bundle verifies against it.
    let src = build_store("segments-src", 1030);
    let bundle = tempdir("segments-bundle");
    let report = write_snapshot(&src, &bundle).unwrap();
    assert_eq!(report.checkpoints, 1);
    assert_eq!(verify_snapshot(&bundle).unwrap(), report);
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
}

#[test]
fn one_altered_byte_in_log_fails_verification() {
    let src = build_store("mutlog-src", 4);
    let bundle = tempdir("mutlog-bundle");
    write_snapshot(&src, &bundle).unwrap();
    let log_path = bundle.join("events.log");
    let mut bytes = std::fs::read(&log_path).unwrap();
    let mid = bytes.len() / 2;
    bytes[mid] ^= 0x01;
    std::fs::write(&log_path, &bytes).unwrap();
    let err = verify_snapshot(&bundle).unwrap_err();
    assert!(matches!(err, SnapshotError::Invalid(_)), "{err}");
    // Restore refuses too, and writes nothing.
    let dst = tempdir("mutlog-dst");
    assert!(restore_snapshot(&bundle, &dst).is_err());
    assert!(!Store::log_path(&dst).exists());
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
}

#[test]
fn one_altered_byte_in_manifest_fails_verification() {
    let src = build_store("mutman-src", 4);
    let bundle = tempdir("mutman-bundle");
    write_snapshot(&src, &bundle).unwrap();
    let manifest_path = bundle.join("manifest.json");
    let mut text = std::fs::read_to_string(&manifest_path).unwrap();
    // Flip one hex character inside the recorded head hash.
    let pos = text.find("\"head_hash\": \"").unwrap() + 14;
    let orig = text.as_bytes()[pos];
    let replacement = if orig == b'a' { "b" } else { "a" };
    text.replace_range(pos..pos + 1, replacement);
    std::fs::write(&manifest_path, &text).unwrap();
    let err = verify_snapshot(&bundle).unwrap_err();
    assert!(matches!(err, SnapshotError::Invalid(_)), "{err}");
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
}

#[test]
fn restore_refuses_an_existing_store() {
    let src = build_store("exists-src", 2);
    let bundle = tempdir("exists-bundle");
    write_snapshot(&src, &bundle).unwrap();
    let err = restore_snapshot(&bundle, &src).unwrap_err();
    assert!(matches!(err, SnapshotError::Exists(_)), "{err}");
    // Writing a second bundle over the first is refused too.
    let err = write_snapshot(&src, &bundle).unwrap_err();
    assert!(matches!(err, SnapshotError::Exists(_)), "{err}");
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
}

#[test]
fn snapshot_refuses_a_torn_store() {
    let src = build_store("torn-src", 3);
    // Simulate a crash mid-append: partial final line, no newline.
    let log_path = Store::log_path(&src);
    let mut bytes = std::fs::read(&log_path).unwrap();
    bytes.extend_from_slice(b"{\"seq\": 4, \"partial");
    std::fs::write(&log_path, &bytes).unwrap();
    let bundle = tempdir("torn-bundle");
    let err = write_snapshot(&src, &bundle).unwrap_err();
    assert!(matches!(err, SnapshotError::Invalid(_)), "{err}");
    let _ = std::fs::remove_dir_all(&src);
    let _ = std::fs::remove_dir_all(&bundle);
}
