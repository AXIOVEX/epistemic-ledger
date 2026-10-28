//! Health report tests (DESIGN-13 section 2.4).

use epistemic_ledger_core::health::health_with_segment;
use epistemic_ledger_core::store::Store;
use serde_json::json;

fn tempdir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("elc-health-{tag}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

fn fill(dir: &std::path::Path, n: usize) {
    let mut store = Store::open(dir).unwrap();
    for i in 0..n {
        store
            .append("2026-10-27T00:00:00Z", "system", "assert", json!({"a": i}), None)
            .unwrap();
    }
}

#[test]
fn health_reports_events_checkpoints_and_lock() {
    let dir = tempdir("basic");
    fill(&dir, 10);
    let h = health_with_segment(&dir, 4).unwrap();
    assert_eq!(h.events, 10);
    assert_eq!(h.checkpoints.len(), 2);
    assert_eq!(h.checkpoints[0].first_seq, 1);
    assert_eq!(h.checkpoints[0].last_seq, 4);
    assert_eq!(h.checkpoints[1].first_seq, 5);
    assert_eq!(h.checkpoints[1].prev_root, h.checkpoints[0].root);
    assert_eq!(h.events_since_checkpoint, 2);
    assert_eq!(h.latest_checkpoint_root.as_deref(), Some(h.checkpoints[1].root.as_str()));
    assert!(!h.lock_held);
    assert_eq!(h.torn_tail_bytes, 0);
    // while a writer holds the store, health says so
    let _store = Store::open(&dir).unwrap();
    let h2 = health_with_segment(&dir, 4).unwrap();
    assert!(h2.lock_held);
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn health_on_empty_store() {
    let dir = tempdir("empty");
    std::fs::create_dir_all(&dir).unwrap();
    let h = health_with_segment(&dir, 4).unwrap();
    assert_eq!(h.events, 0);
    assert!(h.checkpoints.is_empty());
    assert_eq!(h.latest_checkpoint_root, None);
    let _ = std::fs::remove_dir_all(&dir);
}
