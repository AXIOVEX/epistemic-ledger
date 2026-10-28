//! Chain format v1 (rust/CHAIN-FORMAT.md): hash-chained,
//! optionally Ed25519-signed event records, one per log line with
//! a CRC32C prefix. Implements DESIGN-13 section 1 (claims H1/H2
//! at the record layer).

use std::collections::HashMap;
use std::fmt;

use curve25519_dalek::constants::ED25519_BASEPOINT_POINT;
use curve25519_dalek::edwards::{CompressedEdwardsY, EdwardsPoint};
use curve25519_dalek::scalar::Scalar;
use curve25519_dalek::traits::{Identity, VartimeMultiscalarMul};
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256, Sha512};

use crate::canon::canonical_json;

pub const GENESIS_PREV: &str =
    "0000000000000000000000000000000000000000000000000000000000000000";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Record {
    pub seq: u64,
    pub t: String,
    pub actor: String,
    #[serde(rename = "type")]
    pub etype: String,
    pub payload: Value,
    pub prev_hash: String,
    pub hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sig: Option<String>,
}

/// The hash input: domain separator + length-prefixed fields, in
/// the fixed order of CHAIN-FORMAT.md.
pub fn hash_input(
    seq: u64,
    t: &str,
    actor: &str,
    etype: &str,
    payload_canon: &str,
    prev_hash: &str,
) -> Vec<u8> {
    let fields = [
        seq.to_string(),
        t.to_string(),
        actor.to_string(),
        etype.to_string(),
        payload_canon.to_string(),
        prev_hash.to_string(),
    ];
    let mut out = Vec::new();
    out.extend_from_slice(b"ELCHAIN1");
    for f in &fields {
        out.extend_from_slice(&(f.len() as u32).to_be_bytes());
        out.extend_from_slice(f.as_bytes());
    }
    out
}

pub fn record_hash(
    seq: u64,
    t: &str,
    actor: &str,
    etype: &str,
    payload: &Value,
    prev_hash: &str,
) -> String {
    let canon = canonical_json(payload);
    let input = hash_input(seq, t, actor, etype, &canon, prev_hash);
    hex::encode(Sha256::digest(&input))
}

/// Build a record, computing its hash and (when a signing key is
/// given) its signature over the raw hash bytes.
pub fn build_record(
    seq: u64,
    t: &str,
    actor: &str,
    etype: &str,
    payload: Value,
    prev_hash: &str,
    signing_key: Option<&SigningKey>,
) -> Record {
    let hash = record_hash(seq, t, actor, etype, &payload, prev_hash);
    let sig = signing_key.map(|key| {
        let hash_bytes = hex::decode(&hash).expect("hash hex");
        hex::encode(key.sign(&hash_bytes).to_bytes())
    });
    Record {
        seq,
        t: t.to_string(),
        actor: actor.to_string(),
        etype: etype.to_string(),
        payload,
        prev_hash: prev_hash.to_string(),
        hash,
        sig,
    }
}

/// The stored log line: `<crc32c hex> <compact json>`.
pub fn chain_line(record: &Record) -> String {
    let json = serde_json::to_string(record).expect("record serializes");
    format!("{:08x} {}", crc32c::crc32c(json.as_bytes()), json)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LineError {
    Malformed(String),
    BadCrc,
}

impl fmt::Display for LineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LineError::Malformed(m) => write!(f, "malformed line: {m}"),
            LineError::BadCrc => write!(f, "crc mismatch (torn or corrupted line)"),
        }
    }
}
impl std::error::Error for LineError {}

pub fn parse_line(line: &str) -> Result<Record, LineError> {
    let (crc_hex, json) = line
        .split_once(' ')
        .ok_or_else(|| LineError::Malformed("missing crc prefix".into()))?;
    let want = u32::from_str_radix(crc_hex, 16)
        .map_err(|_| LineError::Malformed("bad crc hex".into()))?;
    if crc32c::crc32c(json.as_bytes()) != want {
        return Err(LineError::BadCrc);
    }
    serde_json::from_str(json).map_err(|e| LineError::Malformed(e.to_string()))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ChainErrorKind {
    BadSequence { expected: u64 },
    BadPrevHash,
    BadHash,
    MissingSignature,
    BadSignature,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChainError {
    pub seq: u64,
    pub kind: ChainErrorKind,
}

impl fmt::Display for ChainError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "chain breaks at seq {}: {:?}", self.seq, self.kind)
    }
}
impl std::error::Error for ChainError {}

/// Verify a full chain in order. `pubkeys` maps actor -> Ed25519
/// public key bytes; an actor present in the map must have a valid
/// signature on every record. Returns the first break found,
/// naming its sequence number (claim H1/H2).
pub fn verify_chain(
    records: &[Record],
    pubkeys: &HashMap<String, [u8; 32]>,
) -> Result<(), ChainError> {
    verify_chain_from(records, pubkeys, 1)
}

/// Like `verify_chain`, but signatures are required only for
/// records with `seq >= signed_from_seq`. Migrated legacy history
/// (DESIGN-13 section 9) predates signing: it is attested by the
/// chain, and authorship signatures apply from the migration
/// point forward.
///
/// Verification runs in windows: each window gets a structural
/// pass (sequence, linkage, hash, signature form), then one batch
/// Ed25519 check for all of the window's signatures. If the batch
/// check fails, the window is re-run sequentially, record by
/// record, which reproduces the exact first error — the batch is
/// an accelerator, never the arbiter. (The per-record sequential
/// path measured ~21,000 records/sec against the section 8 budget
/// of 50,000; the batch path clears it with room.)
pub fn verify_chain_from(
    records: &[Record],
    pubkeys: &HashMap<String, [u8; 32]>,
    signed_from_seq: u64,
) -> Result<(), ChainError> {
    const BATCH_WINDOW: usize = 512;
    let mut prev = GENESIS_PREV.to_string();
    let mut key_points: HashMap<[u8; 32], Option<EdwardsPoint>> = HashMap::new();
    let mut base = 0usize;
    while base < records.len() {
        let end = core::cmp::min(base + BATCH_WINDOW, records.len());
        let window = &records[base..end];
        let window_prev = prev.clone();
        let mut signed: Vec<SignedItem> = Vec::new();
        let mut local_error: Option<ChainError> = None;
        let mut scan_prev = window_prev.clone();
        for (off, r) in window.iter().enumerate() {
            if let Err(e) = check_structure(r, base as u64 + off as u64 + 1, &scan_prev) {
                local_error = Some(e);
                break;
            }
            scan_prev = r.hash.clone();
            if r.seq >= signed_from_seq {
                if let Some(pk) = pubkeys.get(&r.actor) {
                    match parse_signed_item(r, pk) {
                        Ok(item) => signed.push(item),
                        Err(e) => {
                            local_error = Some(e);
                            break;
                        }
                    }
                }
            }
        }
        if batch_verify(&signed, &mut key_points) {
            if let Some(e) = local_error {
                return Err(e);
            }
            prev = scan_prev;
        } else {
            prev = verify_sequential(window, base as u64, window_prev, pubkeys, signed_from_seq)?;
        }
        base = end;
    }
    Ok(())
}

/// The structural checks for one record: sequence, linkage, and
/// content hash, in the order the sequential verifier applies
/// them.
fn check_structure(r: &Record, expected_seq: u64, prev: &str) -> Result<(), ChainError> {
    if r.seq != expected_seq {
        return Err(ChainError {
            seq: r.seq,
            kind: ChainErrorKind::BadSequence {
                expected: expected_seq,
            },
        });
    }
    if r.prev_hash != prev {
        return Err(ChainError {
            seq: r.seq,
            kind: ChainErrorKind::BadPrevHash,
        });
    }
    let recomputed = record_hash(r.seq, &r.t, &r.actor, &r.etype, &r.payload, &r.prev_hash);
    if recomputed != r.hash {
        return Err(ChainError {
            seq: r.seq,
            kind: ChainErrorKind::BadHash,
        });
    }
    Ok(())
}

/// A signature-bearing record reduced to the bytes verification
/// needs. Parsing applies the sequential path's form checks, with
/// its error mapping (missing signature, malformed signature or
/// key bytes).
struct SignedItem {
    pk: [u8; 32],
    sig: [u8; 64],
    hash: [u8; 32],
}

fn parse_signed_item(r: &Record, pk_bytes: &[u8; 32]) -> Result<SignedItem, ChainError> {
    let bad = ChainError {
        seq: r.seq,
        kind: ChainErrorKind::BadSignature,
    };
    let sig_hex = r.sig.as_ref().ok_or(ChainError {
        seq: r.seq,
        kind: ChainErrorKind::MissingSignature,
    })?;
    let sig_bytes = hex::decode(sig_hex).map_err(|_| bad.clone())?;
    let sig: [u8; 64] = sig_bytes.as_slice().try_into().map_err(|_| bad.clone())?;
    Signature::try_from(sig_bytes.as_slice()).map_err(|_| bad.clone())?;
    VerifyingKey::from_bytes(pk_bytes).map_err(|_| bad.clone())?;
    // r.hash has just passed the structure check, so it is the
    // recomputed hash: well-formed hex of 32 bytes.
    let hash_vec = hex::decode(&r.hash).map_err(|_| bad.clone())?;
    let hash: [u8; 32] = hash_vec.as_slice().try_into().map_err(|_| bad)?;
    Ok(SignedItem {
        pk: *pk_bytes,
        sig,
        hash,
    })
}

/// One record's signature, checked the sequential way.
fn verify_one_signature(r: &Record, pk_bytes: &[u8; 32]) -> Result<(), ChainError> {
    let item = parse_signed_item(r, pk_bytes)?;
    let vk = VerifyingKey::from_bytes(&item.pk).map_err(|_| ChainError {
        seq: r.seq,
        kind: ChainErrorKind::BadSignature,
    })?;
    let sig = Signature::try_from(item.sig.as_slice()).map_err(|_| ChainError {
        seq: r.seq,
        kind: ChainErrorKind::BadSignature,
    })?;
    if vk.verify(&item.hash, &sig).is_err() {
        return Err(ChainError {
            seq: r.seq,
            kind: ChainErrorKind::BadSignature,
        });
    }
    Ok(())
}

/// The reference verifier over a slice: every check, in order.
/// Returns the chain head hash after the slice.
fn verify_sequential(
    records: &[Record],
    base: u64,
    mut prev: String,
    pubkeys: &HashMap<String, [u8; 32]>,
    signed_from_seq: u64,
) -> Result<String, ChainError> {
    for (i, r) in records.iter().enumerate() {
        check_structure(r, base + i as u64 + 1, &prev)?;
        if r.seq >= signed_from_seq {
            if let Some(pk) = pubkeys.get(&r.actor) {
                verify_one_signature(r, pk)?;
            }
        }
        prev = r.hash.clone();
    }
    Ok(prev)
}

/// Batch Ed25519 verification for one window's signatures.
///
/// For each item the Ed25519 equation is [s]B = R + [H(R,A,m)]A.
/// With deterministic per-item coefficients z_i (derived from a
/// transcript hash of the whole window, Fiat-Shamir style), the
/// summed equation
///   [sum z_i s_i]B - sum z_i R_i - sum (z_i H_i) A_i = identity
/// holds if and only if every item's equation holds, up to the
/// soundness of the coefficient derivation. Public-key terms are
/// grouped per distinct key. Any form problem (non-canonical s,
/// an R or key encoding that does not decompress) returns false,
/// handing the window to the sequential arbiter — so the batch
/// path accepts exactly the windows whose every signature the
/// sequential path would accept, and no others.
fn batch_verify(
    items: &[SignedItem],
    key_points: &mut HashMap<[u8; 32], Option<EdwardsPoint>>,
) -> bool {
    if items.is_empty() {
        return true;
    }
    let mut th = Sha512::new();
    th.update(b"ELBATCH1");
    for it in items {
        th.update(it.sig);
        th.update(it.pk);
        th.update(it.hash);
    }
    let transcript: [u8; 64] = th.finalize().into();
    let mut total_s = Scalar::ZERO;
    let mut key_terms: HashMap<[u8; 32], Scalar> = HashMap::new();
    let mut z_scalars: Vec<Scalar> = Vec::with_capacity(items.len());
    let mut r_points: Vec<EdwardsPoint> = Vec::with_capacity(items.len());
    for (i, it) in items.iter().enumerate() {
        let s_bytes: [u8; 32] = it.sig[32..].try_into().expect("signature half");
        let s_opt = Scalar::from_canonical_bytes(s_bytes);
        if s_opt.is_none().into() {
            return false;
        }
        let s = s_opt.unwrap();
        let r_point = match CompressedEdwardsY(it.sig[..32].try_into().expect("signature half"))
            .decompress()
        {
            Some(p) => p,
            None => return false,
        };
        // Populate the key-point cache and refuse the batch if a
        // key encoding does not decompress (the sequential path
        // rejects it in VerifyingKey::from_bytes).
        match key_points
            .entry(it.pk)
            .or_insert_with(|| CompressedEdwardsY(it.pk).decompress())
        {
            Some(_) => {}
            None => return false,
        }
        let mut hh = Sha512::new();
        hh.update(&it.sig[..32]);
        hh.update(it.pk);
        hh.update(it.hash);
        let h = Scalar::from_bytes_mod_order_wide(&hh.finalize().into());
        let mut zh = Sha512::new();
        zh.update(transcript);
        zh.update((i as u64).to_le_bytes());
        let mut z = Scalar::from_bytes_mod_order_wide(&zh.finalize().into());
        if z == Scalar::ZERO {
            z = Scalar::ONE;
        }
        total_s += z * s;
        *key_terms.entry(it.pk).or_insert(Scalar::ZERO) += z * h;
        z_scalars.push(z);
        r_points.push(r_point);
    }
    let mut scalars: Vec<Scalar> = Vec::with_capacity(items.len() + key_terms.len() + 1);
    let mut points: Vec<EdwardsPoint> = Vec::with_capacity(items.len() + key_terms.len() + 1);
    scalars.push(total_s);
    points.push(ED25519_BASEPOINT_POINT);
    for (z, rp) in z_scalars.iter().zip(r_points.iter()) {
        scalars.push(-(*z));
        points.push(*rp);
    }
    for (pk, acc) in key_terms.iter() {
        scalars.push(-(*acc));
        points.push(
            key_points
                .get(pk)
                .copied()
                .flatten()
                .expect("key point checked above"),
        );
    }
    EdwardsPoint::vartime_multiscalar_mul(scalars.iter(), points.iter()) == EdwardsPoint::identity()
}
