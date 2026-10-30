//! Fuzz and corpus entry points (DESIGN-16 stage 2, claim S6).
//!
//! Each function takes arbitrary bytes and drives one parser or
//! verifier entry point. The contract is narrow and absolute:
//! **no input may panic, abort, or hang** — malformed input is an
//! `Err`/false outcome, never a crash. The cargo-fuzz targets in
//! `rust/fuzz/` are thin wrappers over these functions, and the
//! corpus regression test (`tests/fuzz_corpus.rs`) replays the
//! committed corpora through the same functions, so what CI runs
//! per-PR is exactly what the release-tier campaigns fuzz.

use ed25519_dalek::SigningKey;
use serde::Deserialize;

use crate::canon::canonical_json;
use crate::chain::parse_line;
use crate::snapshot::SnapshotManifest;
use crate::sth::{verify_consistency, verify_sth, ConsistencyProof, Sth};

/// The chain record parser over one log line (lossy UTF-8, as the
/// store's own scanner reads the log).
pub fn entry_chain_line(data: &[u8]) {
    let text = String::from_utf8_lossy(data);
    let _ = parse_line(&text);
}

/// The canonical-JSON path: parse arbitrary JSON, canonicalize,
/// and return the canonical form (None on unparseable input).
/// Canonicalization must be idempotent — reparsing the output and
/// canonicalizing again yields the same string; the fuzz target
/// asserts this, the corpus test checks it on the seeds.
pub fn entry_canon_json(data: &[u8]) -> Option<String> {
    let value: serde_json::Value = serde_json::from_slice(data).ok()?;
    Some(canonical_json(&value))
}

/// Signed-tree-head decoding plus signature verification against a
/// fixed checkpoint key.
pub fn entry_sth(data: &[u8]) {
    if let Ok(sth) = serde_json::from_slice::<Sth>(data) {
        let pubkey = SigningKey::from_bytes(&[7u8; 32]).verifying_key().to_bytes();
        let _ = verify_sth(&sth, &pubkey);
    }
}

/// The consistency-proof bundle shape a standalone verifier
/// receives: two heads and the proof between them.
#[derive(Deserialize)]
struct ConsistencyBundle {
    from: Sth,
    to: Sth,
    proof: ConsistencyProof,
}

/// Consistency-proof decoding plus verification.
pub fn entry_consistency(data: &[u8]) {
    if let Ok(bundle) = serde_json::from_slice::<ConsistencyBundle>(data) {
        let _ = verify_consistency(&bundle.from, &bundle.to, &bundle.proof);
    }
}

/// Snapshot manifest decoding (the verifier's first step).
pub fn entry_manifest(data: &[u8]) {
    let _ = serde_json::from_slice::<SnapshotManifest>(data);
}
