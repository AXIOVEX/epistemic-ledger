//! Merkle checkpoints over chain segments (DESIGN-13 section
//! 1.2, claim H3). The tree hash follows RFC 9162: leaves are
//! hashed with a 0x00 domain prefix, interior nodes with 0x01,
//! and an n-leaf tree splits at the largest power of two below n.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const DEFAULT_SEGMENT: u64 = 1024;

fn leaf_hash(data: &[u8; 32]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update([0x00]);
    h.update(data);
    h.finalize().into()
}

fn node_hash(left: &[u8; 32], right: &[u8; 32]) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update([0x01]);
    h.update(left);
    h.update(right);
    h.finalize().into()
}

/// Merkle Tree Hash over leaf data items (here: record hashes).
pub fn merkle_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    match leaves.len() {
        0 => Sha256::digest(b"").into(),
        1 => leaf_hash(&leaves[0]),
        n => {
            let mut k = 1usize;
            while k * 2 < n {
                k *= 2;
            }
            let left = merkle_root(&leaves[..k]);
            let right = merkle_root(&leaves[k..]);
            node_hash(&left, &right)
        }
    }
}

/// An inclusion proof for one leaf: sibling hashes from the leaf
/// up to (but excluding) the root, following the RFC 9162
/// subtree decomposition.
pub fn inclusion_proof(leaves: &[[u8; 32]], index: usize) -> Vec<[u8; 32]> {
    assert!(index < leaves.len(), "index out of range");
    let mut proof = Vec::new();
    build_proof(leaves, index, &mut proof);
    proof
}

fn build_proof(leaves: &[[u8; 32]], index: usize, proof: &mut Vec<[u8; 32]>) {
    let n = leaves.len();
    if n == 1 {
        return;
    }
    let mut k = 1usize;
    while k * 2 < n {
        k *= 2;
    }
    if index < k {
        build_proof(&leaves[..k], index, proof);
        proof.push(merkle_root(&leaves[k..]));
    } else {
        build_proof(&leaves[k..], index - k, proof);
        proof.push(merkle_root(&leaves[..k]));
    }
}

/// Verify an inclusion proof. The proof is ordered leaf-to-root;
/// whether each sibling sits left or right is recovered from the
/// index and the tree shape at each level.
pub fn verify_inclusion(
    leaf: &[u8; 32],
    index: usize,
    total: usize,
    proof: &[[u8; 32]],
    root: &[u8; 32],
) -> bool {
    if total == 0 || index >= total {
        return false;
    }
    let computed = fold_proof(leaf_hash(leaf), index, total, proof);
    computed.as_ref() == Some(root)
}

fn fold_proof(
    acc: [u8; 32],
    index: usize,
    total: usize,
    proof: &[[u8; 32]],
) -> Option<[u8; 32]> {
    if total == 1 {
        return if proof.is_empty() { Some(acc) } else { None };
    }
    let (sibling, rest) = proof.split_last()?;
    let mut k = 1usize;
    while k * 2 < total {
        k *= 2;
    }
    if index < k {
        let left = fold_proof(acc, index, k, rest)?;
        Some(node_hash(&left, sibling))
    } else {
        let right = fold_proof(acc, index - k, total - k, rest)?;
        Some(node_hash(sibling, &right))
    }
}

/// One checkpoint over a chain segment.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Checkpoint {
    pub first_seq: u64,
    pub last_seq: u64,
    /// Merkle root over the segment's record hashes (hex).
    pub root: String,
    /// The previous checkpoint's root (hex); genesis uses the
    /// empty-hash of zero leaves for the first checkpoint, as
    /// 64 hex chars of SHA-256("").
    pub prev_root: String,
}

pub fn checkpoint_for(
    first_seq: u64,
    record_hashes: &[[u8; 32]],
    prev_root: &str,
) -> Checkpoint {
    Checkpoint {
        first_seq,
        last_seq: first_seq + record_hashes.len() as u64 - 1,
        root: hex::encode(merkle_root(record_hashes)),
        prev_root: prev_root.to_string(),
    }
}

/// Recompute a segment's root from its record hashes and compare
/// against the checkpoint (claim H3's segment check).
pub fn verify_segment(record_hashes: &[[u8; 32]], checkpoint: &Checkpoint) -> bool {
    record_hashes.len() as u64 == checkpoint.last_seq - checkpoint.first_seq + 1
        && hex::encode(merkle_root(record_hashes)) == checkpoint.root
}
