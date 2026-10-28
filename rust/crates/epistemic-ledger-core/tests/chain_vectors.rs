//! Cross-implementation vectors (tests/vectors.json, produced by
//! tools/chainref.py) plus the H1/H2 tamper battery at the record
//! layer. If Rust and Python disagree, these tests fail — by design.

use std::collections::HashMap;

use ed25519_dalek::SigningKey;
use epistemic_ledger_core::canon::{canonical_json, es_number};
use epistemic_ledger_core::chain::{
    build_record, chain_line, parse_line, verify_chain, ChainErrorKind, Record, GENESIS_PREV,
};
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("vectors.json")).expect("vectors parse")
}

fn sample_records() -> Vec<Record> {
    let inputs = [
        (
            "2026-10-27T00:00:00Z",
            "system",
            "assert",
            json!({"claim_id": "C-0001", "prior": 0.5, "statement": "genesis claim"}),
        ),
        (
            "2026-10-27T00:01:00Z",
            "wire-desk",
            "support",
            json!({"claim_id": "C-0002", "parent": "C-0001", "strength": 1}),
        ),
        (
            "2026-10-27T00:02:00Z",
            "wire-desk",
            "score_revision",
            json!({"claim_id": "C-0001", "new_score": 0.75}),
        ),
    ];
    let mut prev = GENESIS_PREV.to_string();
    let mut out = Vec::new();
    for (i, (t, actor, etype, payload)) in inputs.into_iter().enumerate() {
        let r = build_record(i as u64 + 1, t, actor, etype, payload, &prev, None);
        prev = r.hash.clone();
        out.push(r);
    }
    out
}

#[test]
fn number_vectors_match_python_reference() {
    let v = vectors();
    for (repr, want) in v["numbers"].as_object().expect("numbers object") {
        let x: f64 = repr.parse().expect("repr parses as f64");
        assert_eq!(es_number(x), want.as_str().unwrap(), "number {repr}");
    }
}

#[test]
fn chain_lines_match_python_reference() {
    let v = vectors();
    let want_lines: Vec<String> = v["lines"]
        .as_array()
        .unwrap()
        .iter()
        .map(|l| l.as_str().unwrap().to_string())
        .collect();
    let records = sample_records();
    let got_lines: Vec<String> = records.iter().map(chain_line).collect();
    assert_eq!(got_lines, want_lines);
    assert_eq!(records.last().unwrap().hash, v["chain_head"].as_str().unwrap());
    // and the reference lines parse back into a verifying chain
    let parsed: Vec<Record> = want_lines.iter().map(|l| parse_line(l).unwrap()).collect();
    verify_chain(&parsed, &HashMap::new()).expect("reference chain verifies");
}

#[test]
fn tampered_payload_breaks_at_that_record() {
    let mut records = sample_records();
    records[1].payload = json!({"claim_id": "C-0002", "parent": "C-0001", "strength": 2});
    let err = verify_chain(&records, &HashMap::new()).unwrap_err();
    assert_eq!(err.seq, 2);
    assert_eq!(err.kind, ChainErrorKind::BadHash);
}

#[test]
fn deleted_record_breaks_the_chain() {
    let mut records = sample_records();
    records.remove(1);
    let err = verify_chain(&records, &HashMap::new()).unwrap_err();
    // the record now at position 2 carries seq 3 and a prev_hash
    // pointing at the deleted record: either way, it is named.
    assert!(matches!(
        err.kind,
        ChainErrorKind::BadSequence { .. } | ChainErrorKind::BadPrevHash
    ));
}

#[test]
fn reordered_records_break_the_chain() {
    let mut records = sample_records();
    records.swap(1, 2);
    assert!(verify_chain(&records, &HashMap::new()).is_err());
}

#[test]
fn forged_signature_fails_even_with_consistent_hashes() {
    let real = SigningKey::from_bytes(&[7u8; 32]);
    let forger = SigningKey::from_bytes(&[9u8; 32]);
    let mut pubkeys = HashMap::new();
    pubkeys.insert("wire-desk".to_string(), real.verifying_key().to_bytes());
    // an attacker who recomputes every hash correctly but signs
    // with the wrong key must still fail (claim H2)
    let inputs = [
        ("2026-10-27T00:00:00Z", "system", "assert", json!({"a": 1})),
        ("2026-10-27T00:01:00Z", "wire-desk", "support", json!({"b": 2})),
    ];
    let mut prev = GENESIS_PREV.to_string();
    let mut records = Vec::new();
    for (i, (t, actor, etype, payload)) in inputs.into_iter().enumerate() {
        let key = if actor == "wire-desk" { Some(&forger) } else { None };
        let r = build_record(i as u64 + 1, t, actor, etype, payload, &prev, key);
        prev = r.hash.clone();
        records.push(r);
    }
    let err = verify_chain(&records, &pubkeys).unwrap_err();
    assert_eq!(err.seq, 2);
    assert_eq!(err.kind, ChainErrorKind::BadSignature);
    // and a properly signed chain verifies
    let mut prev = GENESIS_PREV.to_string();
    let mut records = Vec::new();
    for (i, (t, actor, etype, payload)) in [
        ("2026-10-27T00:00:00Z", "system", "assert", json!({"a": 1})),
        ("2026-10-27T00:01:00Z", "wire-desk", "support", json!({"b": 2})),
    ]
    .into_iter()
    .enumerate()
    {
        let key = if actor == "wire-desk" { Some(&real) } else { None };
        let r = build_record(i as u64 + 1, t, actor, etype, payload, &prev, key);
        prev = r.hash.clone();
        records.push(r);
    }
    verify_chain(&records, &pubkeys).expect("honest signed chain verifies");
}

#[test]
fn canonical_object_keys_are_sorted() {
    let v = json!({"b": 1, "a": {"d": 4, "c": 3}});
    assert_eq!(canonical_json(&v), "{\"a\":{\"c\":3,\"d\":4},\"b\":1}");
}
