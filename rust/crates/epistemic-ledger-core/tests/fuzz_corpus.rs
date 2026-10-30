//! Corpus regression for the fuzz entry points (DESIGN-16 stage
//! 2, claim S6). Every file committed under `rust/fuzz/corpus/`
//! is replayed through the same entry functions the cargo-fuzz
//! targets wrap: the bar is that nothing panics, aborts, or hangs
//! — malformed inputs are ordinary Err/false outcomes. When a
//! release-tier campaign finds a crash, its input is committed
//! here and this test becomes the permanent drill.

use std::fs;
use std::path::{Path, PathBuf};

use epistemic_ledger_core::fuzzing;

fn corpus_dir(target: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fuzz/corpus")
        .join(target)
}

fn replay(target: &str, entry: fn(&[u8])) -> usize {
    let dir = corpus_dir(target);
    let mut files: Vec<PathBuf> = fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("corpus dir {} unreadable: {e}", dir.display()))
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.is_file())
        .collect();
    files.sort();
    assert!(!files.is_empty(), "corpus for {target} is empty");
    for path in &files {
        let data = fs::read(path).unwrap();
        entry(&data);
    }
    files.len()
}

#[test]
fn corpus_chain_line() {
    replay("chain_line", fuzzing::entry_chain_line);
}

#[test]
fn corpus_canon_json_idempotent_on_seeds() {
    let dir = corpus_dir("canon_json");
    let mut count = 0;
    for e in fs::read_dir(&dir).unwrap() {
        let path = e.unwrap().path();
        if !path.is_file() {
            continue;
        }
        let data = fs::read(&path).unwrap();
        if let Some(canon) = fuzzing::entry_canon_json(&data) {
            assert_eq!(
                fuzzing::entry_canon_json(canon.as_bytes()).as_deref(),
                Some(canon.as_str()),
                "canonicalization not idempotent for {}",
                path.display()
            );
        }
        count += 1;
    }
    assert!(count > 0);
}

#[test]
fn corpus_sth_decode() {
    replay("sth_decode", fuzzing::entry_sth);
}

#[test]
fn corpus_consistency_decode() {
    replay("consistency_decode", fuzzing::entry_consistency);
}

#[test]
fn corpus_manifest_decode() {
    replay("manifest_decode", fuzzing::entry_manifest);
}
