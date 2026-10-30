//! Key governance: enrollment windows (DESIGN-15 D3, claim T1).
//!
//! A partition is self-describing: `key_enrollment` and
//! `key_revocation` records in its own chain state who was allowed
//! to write, in what role, from when until when. Governed
//! verification folds the chain in sequence order and checks every
//! record against the windows — a record signed before its key's
//! enrollment, after its revocation, or by a key that was never
//! enrolled is a violation, and governed verification fails.
//!
//! Windows are sequence intervals: an enrollment at seq S covers
//! records with seq > S; a revocation at seq R closes the window
//! for records with seq >= R. Governance records are themselves
//! authorized against the state before them: only the genesis key
//! (whose identity and public key the verifier holds out of band —
//! the same trust shape as the existing pubkeys map) or a key
//! holding the `admin` role in an open window may enroll or revoke.
//! A governance record signed by anyone else is inert and reported
//! as a violation. The genesis key cannot be revoked in-band.
//!
//! Signatures are verified sequentially here, not with the batch
//! verifier `verify` uses: the key assignment is dynamic (it is
//! what the fold computes), so each record is checked against the
//! window in force at its own sequence. Governed verification is
//! therefore slower than `verify`; it is the audit path, not the
//! hot path, and no DESIGN-13 budget applies to it.

use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

use crate::chain::{record_hash, Record, GENESIS_PREV};

pub const ENROLLMENT_TYPE: &str = "key_enrollment";
pub const REVOCATION_TYPE: &str = "key_revocation";

pub const ROLE_WRITER: &str = "writer";
pub const ROLE_CHECKPOINT: &str = "checkpoint";
pub const ROLE_ADMIN: &str = "admin";

/// One key's enrollment window.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct KeyWindow {
    pub key_id: String,
    pub pubkey: String,
    pub role: String,
    pub enrolled_seq: u64,
    pub revoked_seq: Option<u64>,
}

impl KeyWindow {
    /// Does this window cover a record at `seq`?
    pub fn covers(&self, seq: u64) -> bool {
        self.enrolled_seq < seq && self.revoked_seq.is_none_or(|r| seq < r)
    }
}

/// The outcome of folding a chain's governance: every key's
/// windows, and every violation found, in sequence order.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct GovernanceReport {
    pub genesis_key_id: String,
    pub windows: Vec<KeyWindow>,
    pub violations: Vec<String>,
}

impl GovernanceReport {
    /// The window covering `key_id` at `seq`, if any.
    pub fn window_at(&self, key_id: &str, seq: u64) -> Option<&KeyWindow> {
        self.windows
            .iter()
            .find(|w| w.key_id == key_id && w.covers(seq))
    }

    /// Was `key_id` effective (enrolled, not yet revoked) at `seq`?
    /// Verifiers use this for checkpoint keys: an STH is checked
    /// against the window at its tree size.
    pub fn key_effective_at(&self, key_id: &str, seq: u64) -> bool {
        self.window_at(key_id, seq).is_some()
    }
}

fn sig_valid(pubkey_hex: &str, hash_hex: &str, sig_hex: &str) -> bool {
    let (Ok(pk), Ok(hash), Ok(sig)) = (
        hex::decode(pubkey_hex),
        hex::decode(hash_hex),
        hex::decode(sig_hex),
    ) else {
        return false;
    };
    let (Ok(pk), Ok(sig)) = (
        <[u8; 32]>::try_from(pk.as_slice()),
        <[u8; 64]>::try_from(sig.as_slice()),
    ) else {
        return false;
    };
    let Ok(vk) = VerifyingKey::from_bytes(&pk) else {
        return false;
    };
    vk.verify(&hash, &Signature::from_bytes(&sig)).is_ok()
}

/// Fold `records` (in chain order) into a governance report.
/// `genesis_pubkey` is the raw public key of the genesis key,
/// whose actor name is `genesis_key_id`.
pub fn evaluate(
    records: &[Record],
    genesis_key_id: &str,
    genesis_pubkey: &[u8; 32],
) -> GovernanceReport {
    let genesis_hex = hex::encode(genesis_pubkey);
    let mut windows: Vec<KeyWindow> = Vec::new();
    let mut violations: Vec<String> = Vec::new();
    let mut prev_hash = GENESIS_PREV.to_string();

    let window_at = |windows: &[KeyWindow], key_id: &str, seq: u64| -> Option<KeyWindow> {
        windows
            .iter()
            .find(|w| w.key_id == key_id && w.covers(seq))
            .cloned()
    };

    for r in records {
        let seq = r.seq;
        // Structural soundness first: a record whose hash does not
        // recompute, or whose linkage is broken, is a violation
        // regardless of who signed it.
        let recomputed = record_hash(seq, &r.t, &r.actor, &r.etype, &r.payload, &r.prev_hash);
        if recomputed != r.hash || r.prev_hash != prev_hash {
            violations.push(format!("record {seq}: hash or linkage broken"));
        }
        prev_hash = r.hash.clone();

        let Some(sig) = &r.sig else {
            violations.push(format!("record {seq}: unsigned record in a governed store"));
            continue;
        };

        // Resolve the signer and verify the signature.
        let is_genesis = r.actor == genesis_key_id;
        let signer_window = if is_genesis {
            None
        } else {
            window_at(&windows, &r.actor, seq)
        };
        let (authorized, signer_role) = if is_genesis {
            (sig_valid(&genesis_hex, &r.hash, sig), "genesis")
        } else if let Some(w) = &signer_window {
            (sig_valid(&w.pubkey, &r.hash, sig), w.role.as_str())
        } else {
            // Distinguish the failure for the report. The fold is
            // causal: a window exists here only if it opened at an
            // earlier seq, so a known key that does not cover this
            // record has been revoked; an unknown key was never
            // enrolled (a record predating its key's enrollment is
            // reported the same way — at its own seq, the key was
            // not enrolled).
            let known = windows.iter().any(|w| w.key_id == r.actor);
            let msg = if known {
                format!("record {seq}: key {} revoked", r.actor)
            } else {
                format!("record {seq}: signed by unenrolled key {}", r.actor)
            };
            violations.push(msg);
            (false, "")
        };
        if !authorized {
            if signer_window.is_some() || is_genesis {
                violations.push(format!("record {seq}: signature invalid for key {}", r.actor));
            }
            // An unauthorized record changes nothing: governance
            // records it carries are inert.
            continue;
        }

        match r.etype.as_str() {
            ENROLLMENT_TYPE | REVOCATION_TYPE => {
                if !is_genesis && signer_role != ROLE_ADMIN {
                    violations.push(format!(
                        "record {seq}: governance record signed by {} without governance authority",
                        r.actor
                    ));
                    continue;
                }
                if r.etype == ENROLLMENT_TYPE {
                    let key_id = r.payload.get("key_id").and_then(|v| v.as_str());
                    let pubkey = r.payload.get("pubkey").and_then(|v| v.as_str());
                    let role = r.payload.get("role").and_then(|v| v.as_str());
                    match (key_id, pubkey, role) {
                        (Some(k), Some(p), Some(ro))
                            if [ROLE_WRITER, ROLE_CHECKPOINT, ROLE_ADMIN].contains(&ro)
                                && hex::decode(p).is_ok_and(|b| b.len() == 32) =>
                        {
                            if windows.iter().any(|w| w.key_id == k && w.revoked_seq.is_none()) {
                                violations.push(format!(
                                    "record {seq}: key {k} enrolled while a window is already open"
                                ));
                            } else {
                                windows.push(KeyWindow {
                                    key_id: k.to_string(),
                                    pubkey: p.to_string(),
                                    role: ro.to_string(),
                                    enrolled_seq: seq,
                                    revoked_seq: None,
                                });
                            }
                        }
                        _ => violations.push(format!("record {seq}: malformed key_enrollment payload")),
                    }
                } else {
                    let key_id = r.payload.get("key_id").and_then(|v| v.as_str());
                    match key_id {
                        Some(k) if k == genesis_key_id => {
                            violations.push(format!(
                                "record {seq}: the genesis key cannot be revoked in-band"
                            ));
                        }
                        Some(k) => {
                            if let Some(w) = windows
                                .iter_mut()
                                .find(|w| w.key_id == k && w.revoked_seq.is_none())
                            {
                                w.revoked_seq = Some(seq);
                            } else {
                                violations.push(format!(
                                    "record {seq}: revocation of key {k}, which has no open window"
                                ));
                            }
                        }
                        None => violations.push(format!("record {seq}: malformed key_revocation payload")),
                    }
                }
            }
            _ => {
                // Ordinary record: the signer must hold the writer
                // role (the genesis key may also write).
                if !is_genesis && signer_role != ROLE_WRITER {
                    violations.push(format!(
                        "record {seq}: key {} holds role {signer_role}, not writer",
                        r.actor
                    ));
                }
            }
        }
    }

    GovernanceReport {
        genesis_key_id: genesis_key_id.to_string(),
        windows,
        violations,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::chain::build_record;
    use ed25519_dalek::SigningKey;
    use serde_json::json;

    fn key(byte: u8) -> SigningKey {
        SigningKey::from_bytes(&[byte; 32])
    }

    fn pub_hex(k: &SigningKey) -> String {
        hex::encode(k.verifying_key().to_bytes())
    }

    struct Chain {
        records: Vec<Record>,
        prev: String,
    }

    impl Chain {
        fn new() -> Self {
            Chain {
                records: Vec::new(),
                prev: GENESIS_PREV.to_string(),
            }
        }
        fn add(&mut self, actor: &str, etype: &str, payload: serde_json::Value, k: &SigningKey) {
            let seq = self.records.len() as u64 + 1;
            let rec = build_record(
                seq,
                "2026-10-30T00:00:00Z",
                actor,
                etype,
                payload,
                &self.prev.clone(),
                Some(k),
            );
            self.prev = rec.hash.clone();
            self.records.push(rec);
        }
    }

    fn governed_chain() -> (Vec<Record>, SigningKey) {
        let genesis = key(1);
        let writer = key(2);
        let mut c = Chain::new();
        c.add(
            "genesis",
            ENROLLMENT_TYPE,
            json!({"key_id": "w1", "pubkey": pub_hex(&writer), "role": "writer"}),
            &genesis,
        );
        c.add("w1", "note", json!({"i": 1}), &writer);
        (c.records, genesis)
    }

    #[test]
    fn enrolled_writer_verifies_clean() {
        let (records, genesis) = governed_chain();
        let report = evaluate(&records, "genesis", &genesis.verifying_key().to_bytes());
        assert!(report.violations.is_empty(), "{:?}", report.violations);
        assert!(report.key_effective_at("w1", 2));
        assert!(!report.key_effective_at("w1", 1));
    }

    #[test]
    fn record_before_enrollment_and_after_revocation_fail() {
        let genesis = key(1);
        let writer = key(2);
        let mut c = Chain::new();
        // Writer writes BEFORE being enrolled.
        c.add("w1", "note", json!({"i": 0}), &writer);
        c.add(
            "genesis",
            ENROLLMENT_TYPE,
            json!({"key_id": "w1", "pubkey": pub_hex(&writer), "role": "writer"}),
            &genesis,
        );
        c.add("w1", "note", json!({"i": 1}), &writer);
        c.add(
            "genesis",
            REVOCATION_TYPE,
            json!({"key_id": "w1"}),
            &genesis,
        );
        // And after revocation.
        c.add("w1", "note", json!({"i": 2}), &writer);
        let report = evaluate(&c.records, "genesis", &genesis.verifying_key().to_bytes());
        assert_eq!(report.violations.len(), 2, "{:?}", report.violations);
        assert!(report.violations[0].contains("unenrolled key"), "{}", report.violations[0]);
        assert!(report.violations[1].contains("revoked"), "{}", report.violations[1]);
    }

    #[test]
    fn unenrolled_signer_and_inert_enrollment() {
        let genesis = key(1);
        let stranger = key(9);
        let writer = key(2);
        let mut c = Chain::new();
        // A stranger's enrollment of a writer is inert...
        c.add(
            "stranger",
            ENROLLMENT_TYPE,
            json!({"key_id": "w1", "pubkey": pub_hex(&writer), "role": "writer"}),
            &stranger,
        );
        // ...so the writer's records are unenrolled too.
        c.add("w1", "note", json!({"i": 1}), &writer);
        let report = evaluate(&c.records, "genesis", &genesis.verifying_key().to_bytes());
        assert!(report.windows.is_empty());
        assert_eq!(report.violations.len(), 2, "{:?}", report.violations);
    }

    #[test]
    fn checkpoint_key_cannot_write_records() {
        let genesis = key(1);
        let ck = key(3);
        let mut c = Chain::new();
        c.add(
            "genesis",
            ENROLLMENT_TYPE,
            json!({"key_id": "ck1", "pubkey": pub_hex(&ck), "role": "checkpoint"}),
            &genesis,
        );
        c.add("ck1", "note", json!({"i": 1}), &ck);
        let report = evaluate(&c.records, "genesis", &genesis.verifying_key().to_bytes());
        assert_eq!(report.violations.len(), 1);
        assert!(report.violations[0].contains("not writer"));
        assert!(report.key_effective_at("ck1", 2));
    }
}
