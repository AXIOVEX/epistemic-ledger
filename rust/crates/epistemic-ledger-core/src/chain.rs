//! Chain format v1 (rust/CHAIN-FORMAT.md): hash-chained,
//! optionally Ed25519-signed event records, one per log line with
//! a CRC32C prefix. Implements DESIGN-13 section 1 (claims H1/H2
//! at the record layer).

use std::collections::HashMap;
use std::fmt;

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

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
    let mut prev = GENESIS_PREV.to_string();
    for (i, r) in records.iter().enumerate() {
        let expected_seq = i as u64 + 1;
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
        if let Some(pk_bytes) = pubkeys.get(&r.actor) {
            let sig_hex = r.sig.as_ref().ok_or(ChainError {
                seq: r.seq,
                kind: ChainErrorKind::MissingSignature,
            })?;
            let sig_bytes = hex::decode(sig_hex).map_err(|_| ChainError {
                seq: r.seq,
                kind: ChainErrorKind::BadSignature,
            })?;
            let sig = Signature::try_from(sig_bytes.as_slice()).map_err(|_| ChainError {
                seq: r.seq,
                kind: ChainErrorKind::BadSignature,
            })?;
            let vk = VerifyingKey::from_bytes(pk_bytes).map_err(|_| ChainError {
                seq: r.seq,
                kind: ChainErrorKind::BadSignature,
            })?;
            let hash_bytes = hex::decode(&r.hash).expect("hash hex");
            if vk.verify(&hash_bytes, &sig).is_err() {
                return Err(ChainError {
                    seq: r.seq,
                    kind: ChainErrorKind::BadSignature,
                });
            }
        }
        prev = r.hash.clone();
    }
    Ok(())
}
