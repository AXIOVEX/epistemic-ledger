//! Merkle checkpoint tests (claim H3): segment roots, tamper
//! isolation between segments, and inclusion proofs.

use epistemic_ledger_core::checkpoint::{
    checkpoint_for, inclusion_proof, merkle_root, verify_inclusion, verify_segment,
};
use sha2::{Digest, Sha256};

fn leaf(i: u32) -> [u8; 32] {
    Sha256::digest(format!("record-{i}").as_bytes()).into()
}

fn leaves(n: u32) -> Vec<[u8; 32]> {
    (0..n).map(leaf).collect()
}

#[test]
fn segment_verification_accepts_and_rejects() {
    let seg = leaves(8);
    let cp = checkpoint_for(1, &seg, "genesis");
    assert!(verify_segment(&seg, &cp));
    let mut tampered = seg.clone();
    tampered[3] = leaf(999);
    assert!(!verify_segment(&tampered, &cp));
    // wrong length also fails
    assert!(!verify_segment(&seg[..7], &cp));
}

#[test]
fn tampering_outside_a_segment_does_not_affect_it() {
    let seg_a = leaves(4);
    let seg_b: Vec<[u8; 32]> = (100..104).map(leaf).collect();
    let cp_a = checkpoint_for(1, &seg_a, "genesis");
    let mut seg_b_bad = seg_b.clone();
    seg_b_bad[0] = leaf(555);
    // segment A's verdict is computed from A's records alone
    assert!(verify_segment(&seg_a, &cp_a));
    let cp_b = checkpoint_for(5, &seg_b, &cp_a.root);
    assert!(!verify_segment(&seg_b_bad, &cp_b));
    assert!(verify_segment(&seg_b, &cp_b));
}

#[test]
fn inclusion_proofs_verify_for_every_leaf() {
    for n in [1u32, 2, 3, 5, 8, 13, 100] {
        let ls = leaves(n);
        let root = merkle_root(&ls);
        for i in 0..n as usize {
            let proof = inclusion_proof(&ls, i);
            assert!(
                verify_inclusion(&ls[i], i, n as usize, &proof, &root),
                "n={n} i={i}"
            );
            // a proof for the wrong leaf or wrong index must fail
            let wrong = leaf(10_000 + i as u32);
            assert!(!verify_inclusion(&wrong, i, n as usize, &proof, &root));
        }
    }
}

#[test]
fn empty_tree_root_is_sha256_of_empty() {
    let root = merkle_root(&[]);
    assert_eq!(hex::encode(root), hex::encode(Sha256::digest(b"")));
}
