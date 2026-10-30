//! Signed tree heads and checkpoint proofs (DESIGN-15 D2, stage 1
//! claims A1-A3).
//!
//! Each checkpoint (DESIGN-13 section 1.2) produces a *signed tree
//! head*: the record count it covers, the checkpoint's Merkle root,
//! the checkpoint sequence, a timestamp, and the checkpoint key's
//! identity, signed by the partition's checkpoint key. The signed
//! bytes are SHA-256 over a domain separator (`ELSTH1`) and the
//! RFC 8785 canonical JSON of the unsigned head — the same
//! sign-the-hash shape the chain uses for records (`ELCHAIN1`).
//!
//! Consistency between two heads is proven by *chain linkage*: the
//! intervening checkpoints, each carrying its predecessor's root in
//! `prev_root`. The segment roots themselves are unchanged from
//! DESIGN-13 (no format change, existing snapshots stay valid);
//! any rewrite below an anchored head changes some checkpoint's
//! root and breaks the chain or an endpoint.
//!
//! Inclusion proofs are the checkpoint module's RFC 9162 audit
//! paths within one segment; this module adds the signed heads and
//! the consistency machinery around them.

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::canon::canonical_json;
use crate::checkpoint::Checkpoint;

/// One signed tree head.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Sth {
    /// Records covered: the checkpoint's last sequence number.
    pub tree_size: u64,
    /// The checkpoint's Merkle root (hex).
    pub root: String,
    /// 1-based checkpoint sequence within the partition.
    pub checkpoint_seq: u64,
    /// Issuance time (ISO 8601, caller-supplied: the key holder's
    /// clock is the authority, the store has none).
    pub timestamp: String,
    /// Identity of the checkpoint key that signed this head.
    pub key_id: String,
    /// Ed25519 signature (hex) over the signing digest.
    pub signature: String,
}

/// The digest an STH signature commits to: SHA-256 over the domain
/// separator and the canonical JSON of the unsigned head.
pub fn sth_digest(
    tree_size: u64,
    root: &str,
    checkpoint_seq: u64,
    timestamp: &str,
    key_id: &str,
) -> [u8; 32] {
    let unsigned = serde_json::json!({
        "checkpoint_seq": checkpoint_seq,
        "key_id": key_id,
        "root": root,
        "timestamp": timestamp,
        "tree_size": tree_size,
    });
    let mut h = Sha256::new();
    h.update(b"ELSTH1");
    h.update(canonical_json(&unsigned).as_bytes());
    h.finalize().into()
}

/// Sign a tree head for `checkpoint` with the checkpoint key.
pub fn sign_sth(
    checkpoint: &Checkpoint,
    checkpoint_seq: u64,
    timestamp: &str,
    key_id: &str,
    key: &SigningKey,
) -> Sth {
    let digest = sth_digest(
        checkpoint.last_seq,
        &checkpoint.root,
        checkpoint_seq,
        timestamp,
        key_id,
    );
    Sth {
        tree_size: checkpoint.last_seq,
        root: checkpoint.root.clone(),
        checkpoint_seq,
        timestamp: timestamp.to_string(),
        key_id: key_id.to_string(),
        signature: hex::encode(key.sign(&digest).to_bytes()),
    }
}

/// Verify a tree head's signature against the checkpoint key's
/// public bytes.
pub fn verify_sth(sth: &Sth, pubkey: &[u8; 32]) -> bool {
    let Ok(vk) = VerifyingKey::from_bytes(pubkey) else {
        return false;
    };
    let Ok(sig_bytes) = hex::decode(&sth.signature) else {
        return false;
    };
    let Ok(sig_arr) = <[u8; 64]>::try_from(sig_bytes.as_slice()) else {
        return false;
    };
    let digest = sth_digest(
        sth.tree_size,
        &sth.root,
        sth.checkpoint_seq,
        &sth.timestamp,
        &sth.key_id,
    );
    vk.verify(&digest, &Signature::from_bytes(&sig_arr)).is_ok()
}

/// Equivocation test (claim A3): two heads for the same checkpoint
/// (same sequence and tree size) with different roots. Both may be
/// validly signed — that is what makes it proof of equivocation
/// rather than corruption — so callers verify each signature first
/// and then apply this test.
pub fn is_fork(a: &Sth, b: &Sth) -> bool {
    a.checkpoint_seq == b.checkpoint_seq && a.tree_size == b.tree_size && a.root != b.root
}

/// A consistency proof between two checkpoints: the checkpoints
/// after `from` up to and including `to`, in order.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct ConsistencyProof {
    pub checkpoints: Vec<Checkpoint>,
}

/// Build the consistency proof between two 1-based checkpoint
/// sequences from the full checkpoint list (index i holds sequence
/// i+1). None when the range is invalid.
pub fn consistency_proof(
    checkpoints: &[Checkpoint],
    from_seq: u64,
    to_seq: u64,
) -> Option<ConsistencyProof> {
    if from_seq == 0 || to_seq < from_seq || to_seq as usize > checkpoints.len() {
        return None;
    }
    let links = checkpoints[from_seq as usize..to_seq as usize].to_vec();
    Some(ConsistencyProof { checkpoints: links })
}

/// Verify that `to` extends `from`: the proof's checkpoints link
/// the two heads' roots into one unbroken, contiguous chain. The
/// heads' signatures are verified separately (verify_sth); this
/// checks the history between them.
pub fn verify_consistency(from: &Sth, to: &Sth, proof: &ConsistencyProof) -> bool {
    if from.checkpoint_seq > to.checkpoint_seq {
        return false;
    }
    if from.checkpoint_seq == to.checkpoint_seq {
        return proof.checkpoints.is_empty()
            && from.tree_size == to.tree_size
            && from.root == to.root;
    }
    let links = &proof.checkpoints;
    if links.len() as u64 != to.checkpoint_seq - from.checkpoint_seq {
        return false;
    }
    let mut prev_root = from.root.as_str();
    let mut next_first = from.tree_size + 1;
    for link in links {
        if link.prev_root != prev_root || link.first_seq != next_first || link.last_seq < link.first_seq
        {
            return false;
        }
        prev_root = link.root.as_str();
        next_first = link.last_seq + 1;
    }
    prev_root == to.root && next_first == to.tree_size + 1
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkpoint::checkpoint_for;

    fn key() -> SigningKey {
        SigningKey::from_bytes(&[7u8; 32])
    }

    fn checkpoints(n: usize) -> Vec<Checkpoint> {
        let mut out = Vec::new();
        let mut prev = hex::encode(crate::checkpoint::merkle_root(&[]));
        for i in 0..n {
            let hashes: Vec<[u8; 32]> = (0..4).map(|j| [((i * 4 + j) % 251) as u8; 32]).collect();
            let cp = checkpoint_for(i as u64 * 4 + 1, &hashes, &prev);
            prev = cp.root.clone();
            out.push(cp);
        }
        out
    }

    #[test]
    fn sth_signs_and_verifies() {
        let cps = checkpoints(2);
        let sth = sign_sth(&cps[1], 2, "2026-10-30T00:00:00Z", "ck-1", &key());
        assert_eq!(sth.tree_size, 8);
        assert!(verify_sth(&sth, &key().verifying_key().to_bytes()));
    }

    #[test]
    fn sth_rejects_tamper_and_wrong_key() {
        let cps = checkpoints(1);
        let mut sth = sign_sth(&cps[0], 1, "2026-10-30T00:00:00Z", "ck-1", &key());
        sth.root = hex::encode([9u8; 32]);
        assert!(!verify_sth(&sth, &key().verifying_key().to_bytes()));
        let other = SigningKey::from_bytes(&[8u8; 32]);
        let sth2 = sign_sth(&cps[0], 1, "2026-10-30T00:00:00Z", "ck-1", &key());
        assert!(!verify_sth(&sth2, &other.verifying_key().to_bytes()));
    }

    #[test]
    fn consistency_links_extend() {
        let cps = checkpoints(3);
        let from = sign_sth(&cps[0], 1, "2026-10-30T00:00:00Z", "ck-1", &key());
        let to = sign_sth(&cps[2], 3, "2026-10-30T01:00:00Z", "ck-1", &key());
        let proof = consistency_proof(&cps, 1, 3).unwrap();
        assert!(verify_consistency(&from, &to, &proof));
        // A rewritten middle checkpoint breaks the chain.
        let mut bad = proof.clone();
        bad.checkpoints[0].root = hex::encode([3u8; 32]);
        assert!(!verify_consistency(&from, &to, &bad));
        // A proof that skips a link fails the count.
        let short = ConsistencyProof {
            checkpoints: proof.checkpoints[1..].to_vec(),
        };
        assert!(!verify_consistency(&from, &to, &short));
    }

    #[test]
    fn fork_detection() {
        let cps = checkpoints(1);
        let a = sign_sth(&cps[0], 1, "2026-10-30T00:00:00Z", "ck-1", &key());
        let mut other_cp = cps[0].clone();
        other_cp.root = hex::encode([5u8; 32]);
        let b = sign_sth(&other_cp, 1, "2026-10-30T00:00:00Z", "ck-1", &key());
        assert!(verify_sth(&a, &key().verifying_key().to_bytes()));
        assert!(verify_sth(&b, &key().verifying_key().to_bytes()));
        assert!(is_fork(&a, &b));
        assert!(!is_fork(&a, &a));
    }
}
