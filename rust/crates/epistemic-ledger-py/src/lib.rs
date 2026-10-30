//! PyO3 bindings exposing the Rust core store to Python as
//! `epistemic_ledger._core` (DESIGN-13 stage 2). Payloads and
//! records cross the boundary as JSON strings so the byte-level
//! chain format is the only contract between the languages.

use std::collections::HashMap;
use std::path::PathBuf;

use ed25519_dalek::SigningKey;
use epistemic_ledger_core::checkpoint::{
    checkpoints_for_records, inclusion_proof, verify_inclusion, Checkpoint, DEFAULT_SEGMENT,
};
use epistemic_ledger_core::health::health_with_segment;
use epistemic_ledger_core::sth::{
    consistency_proof, is_fork, sign_sth, verify_consistency, verify_sth, ConsistencyProof, Sth,
};
use epistemic_ledger_core::store::Store;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

fn err<E: std::fmt::Display>(e: E) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

fn key_from_hex(seed_hex: &str) -> PyResult<SigningKey> {
    let bytes = hex::decode(seed_hex).map_err(err)?;
    let arr: [u8; 32] = bytes
        .try_into()
        .map_err(|_| PyRuntimeError::new_err("seed must be 32 bytes (64 hex chars)"))?;
    Ok(SigningKey::from_bytes(&arr))
}

#[pyclass]
struct RustStore {
    inner: Store,
    /// Lazily computed (checkpoints, record hashes) for proof
    /// issuance; invalidated by every append. See proof_data.
    proof_cache: std::sync::Mutex<Option<(Vec<Checkpoint>, Vec<String>)>>,
}

impl RustStore {
    /// The checkpoint set and the record hashes, computed once and
    /// cached. Proof issuance on a warm store must not re-scan the
    /// log per call: DESIGN-15's 50 ms proof budget on the 100k
    /// reference store is a warm-store budget (a serving process
    /// holds the store open), and the one full computation is the
    /// warm-up, measured as its own line in the bench.
    fn proof_data(&self) -> PyResult<(Vec<Checkpoint>, Vec<String>)> {
        if let Some(data) = self.proof_cache.lock().unwrap().as_ref() {
            return Ok(data.clone());
        }
        let records = self.inner.records().map_err(err)?;
        let checkpoints = checkpoints_for_records(&records, DEFAULT_SEGMENT);
        let hashes: Vec<String> = records.iter().map(|r| r.hash.clone()).collect();
        let data = (checkpoints, hashes);
        *self.proof_cache.lock().unwrap() = Some(data.clone());
        Ok(data)
    }
}

#[pymethods]
impl RustStore {
    /// Open (creating if needed) the Rust store at `path`, taking
    /// the single-writer lock.
    #[staticmethod]
    fn open(path: String) -> PyResult<RustStore> {
        Store::open(&PathBuf::from(path))
            .map(|inner| RustStore {
                inner,
                proof_cache: std::sync::Mutex::new(None),
            })
            .map_err(err)
    }

    /// Append one event. `payload_json` is the payload as a JSON
    /// string. `signing_seed_hex` optionally signs the append with
    /// the writer's Ed25519 seed. Returns the stored record as a
    /// JSON string.
    #[pyo3(signature = (t, actor, etype, payload_json, signing_seed_hex=None))]
    fn append(
        &mut self,
        t: String,
        actor: String,
        etype: String,
        payload_json: String,
        signing_seed_hex: Option<String>,
    ) -> PyResult<String> {
        let payload: serde_json::Value = serde_json::from_str(&payload_json).map_err(err)?;
        let key = match signing_seed_hex {
            Some(h) => Some(key_from_hex(&h)?),
            None => None,
        };
        let record = self
            .inner
            .append(&t, &actor, &etype, payload, key.as_ref())
            .map_err(err)?;
        *self.proof_cache.get_mut().unwrap() = None;
        serde_json::to_string(&record).map_err(err)
    }

    /// Full chain verification. `pubkeys_json` maps actor -> public
    /// key hex for writers whose signatures must verify. Returns
    /// the number of events verified. `signed_from_seq` (default 1)
    /// is the first sequence number at which signatures are
    /// required — migrated stores pass their migration boundary.
    #[pyo3(signature = (pubkeys_json, signed_from_seq=1))]
    fn verify(&self, pubkeys_json: String, signed_from_seq: u64) -> PyResult<u64> {
        let raw: HashMap<String, String> = serde_json::from_str(&pubkeys_json).map_err(err)?;
        let mut pubkeys: HashMap<String, [u8; 32]> = HashMap::new();
        for (actor, hexkey) in raw {
            let bytes = hex::decode(hexkey).map_err(err)?;
            let arr: [u8; 32] = bytes
                .try_into()
                .map_err(|_| PyRuntimeError::new_err("pubkey must be 32 bytes"))?;
            pubkeys.insert(actor, arr);
        }
        self.inner.verify_from(&pubkeys, signed_from_seq).map_err(err)
    }

    #[getter]
    fn next_seq(&self) -> u64 {
        self.inner.next_seq()
    }

    #[getter]
    fn head_hash(&self) -> String {
        self.inner.head_hash().to_string()
    }

    /// The open report (events, head, torn-tail recovery) as JSON.
    fn open_report_json(&self) -> String {
        serde_json::to_string(&self.inner.report).unwrap_or_default()
    }

    /// Sign a tree head (DESIGN-15 D2) for one checkpoint of this
    /// store: `checkpoint_seq` is 1-based, defaulting to the latest
    /// complete checkpoint. The checkpoint key's seed is passed per
    /// call and never stored — the same custody as writer seeds.
    /// Returns the STH as a JSON string.
    #[pyo3(signature = (timestamp, key_id, seed_hex, checkpoint_seq=None))]
    fn sth_json(
        &self,
        timestamp: String,
        key_id: String,
        seed_hex: String,
        checkpoint_seq: Option<u64>,
    ) -> PyResult<String> {
        let (checkpoints, _) = self.proof_data()?;
        if checkpoints.is_empty() {
            return Err(PyRuntimeError::new_err("store has no complete checkpoint yet"));
        }
        let seq = checkpoint_seq.unwrap_or(checkpoints.len() as u64);
        if seq == 0 || seq as usize > checkpoints.len() {
            return Err(PyRuntimeError::new_err("checkpoint_seq out of range"));
        }
        let key = key_from_hex(&seed_hex)?;
        let sth = sign_sth(&checkpoints[(seq - 1) as usize], seq, &timestamp, &key_id, &key);
        serde_json::to_string(&sth).map_err(err)
    }

    /// An RFC 9162 inclusion proof for the record at `seq`, against
    /// its checkpoint's root, as a JSON string. The record must be
    /// inside a complete checkpoint. Everything a standalone
    /// verifier needs is in the returned object plus the record.
    fn inclusion_proof_json(&self, seq: u64) -> PyResult<String> {
        let (checkpoints, hashes) = self.proof_data()?;
        let idx = checkpoints
            .iter()
            .position(|cp| seq >= cp.first_seq && seq <= cp.last_seq)
            .ok_or_else(|| PyRuntimeError::new_err("record is not in a complete checkpoint"))?;
        let cp = &checkpoints[idx];
        let leaves: Vec<[u8; 32]> = hashes[(cp.first_seq - 1) as usize..(cp.last_seq as usize)]
            .iter()
            .map(|h| {
                let decoded = hex::decode(h).unwrap_or_default();
                let mut b = [0u8; 32];
                if decoded.len() == 32 {
                    b.copy_from_slice(&decoded);
                }
                b
            })
            .collect();
        let index = (seq - cp.first_seq) as usize;
        let proof = inclusion_proof(&leaves, index);
        serde_json::to_string(&serde_json::json!({
            "seq": seq,
            "checkpoint_seq": idx as u64 + 1,
            "segment_first_seq": cp.first_seq,
            "segment_last_seq": cp.last_seq,
            "segment_len": leaves.len(),
            "index": index,
            "leaf_hash": hashes[(seq - 1) as usize],
            "proof": proof.iter().map(hex::encode).collect::<Vec<_>>(),
            "root": cp.root,
        }))
        .map_err(err)
    }

    /// The consistency proof (DESIGN-15 D2) between two 1-based
    /// checkpoint sequences of this store, as a JSON string.
    fn consistency_proof_json(&self, from_seq: u64, to_seq: u64) -> PyResult<String> {
        let (checkpoints, _) = self.proof_data()?;
        let proof = consistency_proof(&checkpoints, from_seq, to_seq)
            .ok_or_else(|| PyRuntimeError::new_err("invalid checkpoint range"))?;
        serde_json::to_string(&proof).map_err(err)
    }
}

/// All records of the store at `path`, read-only, as a JSON
/// string (an array of record objects in chain order).
#[pyfunction]
fn read_records_json(path: String) -> PyResult<String> {
    let (records, _report) =
        epistemic_ledger_core::store::Store::open_readonly(&PathBuf::from(path)).map_err(err)?;
    serde_json::to_string(&records).map_err(err)
}

/// The health report for the store at `path`, as a JSON string.
#[pyfunction]
#[pyo3(signature = (path, segment=None))]
fn health_json(path: String, segment: Option<u64>) -> PyResult<String> {
    let report = health_with_segment(
        &PathBuf::from(path),
        segment.unwrap_or(DEFAULT_SEGMENT),
    )
    .map_err(err)?;
    serde_json::to_string(&report).map_err(err)
}

/// Write a snapshot bundle of the store at `store_path` into
/// `bundle_path` (DESIGN-13 section 4). Returns the snapshot
/// report as a JSON string.
#[pyfunction]
fn snapshot_json(store_path: String, bundle_path: String) -> PyResult<String> {
    let report = epistemic_ledger_core::snapshot::write_snapshot(
        &PathBuf::from(store_path),
        &PathBuf::from(bundle_path),
    )
    .map_err(err)?;
    serde_json::to_string(&report).map_err(err)
}

/// Verify the snapshot bundle at `bundle_path` from the bundle
/// alone. Returns the snapshot report as a JSON string; raises on
/// any mismatch.
#[pyfunction]
fn verify_snapshot_json(bundle_path: String) -> PyResult<String> {
    let report = epistemic_ledger_core::snapshot::verify_snapshot(&PathBuf::from(bundle_path))
        .map_err(err)?;
    serde_json::to_string(&report).map_err(err)
}

/// Restore the snapshot bundle at `bundle_path` into a new store
/// at `dst_path`. The bundle is verified before anything is
/// written. Returns the snapshot report as a JSON string.
#[pyfunction]
fn restore_snapshot_json(bundle_path: String, dst_path: String) -> PyResult<String> {
    let report = epistemic_ledger_core::snapshot::restore_snapshot(
        &PathBuf::from(bundle_path),
        &PathBuf::from(dst_path),
    )
    .map_err(err)?;
    serde_json::to_string(&report).map_err(err)
}

fn pubkey_from_hex(pubkey_hex: &str) -> PyResult<[u8; 32]> {
    let bytes = hex::decode(pubkey_hex).map_err(err)?;
    bytes
        .try_into()
        .map_err(|_| PyRuntimeError::new_err("pubkey must be 32 bytes (64 hex chars)"))
}

fn hash_from_hex(hash_hex: &str) -> PyResult<[u8; 32]> {
    let bytes = hex::decode(hash_hex).map_err(err)?;
    bytes
        .try_into()
        .map_err(|_| PyRuntimeError::new_err("hash must be 32 bytes (64 hex chars)"))
}

/// Verify a signed tree head (DESIGN-15 D2) against the checkpoint
/// key's public key hex. Standalone: JSON strings in, bool out, no
/// store access.
#[pyfunction]
fn verify_sth_json(sth_json: String, pubkey_hex: String) -> PyResult<bool> {
    let sth: Sth = serde_json::from_str(&sth_json).map_err(err)?;
    let pubkey = pubkey_from_hex(&pubkey_hex)?;
    Ok(verify_sth(&sth, &pubkey))
}

/// Verify an inclusion proof standalone (DESIGN-15 claim A2):
/// the record's hash, its index and segment length, the audit path
/// (JSON array of hex hashes), and the checkpoint root.
#[pyfunction]
fn verify_inclusion_json(
    leaf_hash_hex: String,
    index: usize,
    segment_len: usize,
    proof_json: String,
    root_hex: String,
) -> PyResult<bool> {
    let leaf = hash_from_hex(&leaf_hash_hex)?;
    let root = hash_from_hex(&root_hex)?;
    let raw: Vec<String> = serde_json::from_str(&proof_json).map_err(err)?;
    let mut proof: Vec<[u8; 32]> = Vec::new();
    for h in &raw {
        proof.push(hash_from_hex(h)?);
    }
    Ok(verify_inclusion(&leaf, index, segment_len, &proof, &root))
}

/// Verify that one STH extends another (DESIGN-15 claim A1) from
/// the two heads and a consistency proof, all as JSON strings.
#[pyfunction]
fn verify_consistency_json(
    from_json: String,
    to_json: String,
    proof_json: String,
) -> PyResult<bool> {
    let from: Sth = serde_json::from_str(&from_json).map_err(err)?;
    let to: Sth = serde_json::from_str(&to_json).map_err(err)?;
    let proof: ConsistencyProof = serde_json::from_str(&proof_json).map_err(err)?;
    Ok(verify_consistency(&from, &to, &proof))
}

/// Equivocation test (DESIGN-15 claim A3): two STHs for the same
/// checkpoint with different roots. Callers verify both signatures
/// first (verify_sth_json); a true result on two validly signed
/// heads is proof the operator equivocated.
#[pyfunction]
fn sth_fork_json(a_json: String, b_json: String) -> PyResult<bool> {
    let a: Sth = serde_json::from_str(&a_json).map_err(err)?;
    let b: Sth = serde_json::from_str(&b_json).map_err(err)?;
    Ok(is_fork(&a, &b))
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RustStore>()?;
    m.add_function(wrap_pyfunction!(health_json, m)?)?;
    m.add_function(wrap_pyfunction!(read_records_json, m)?)?;
    m.add_function(wrap_pyfunction!(snapshot_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_snapshot_json, m)?)?;
    m.add_function(wrap_pyfunction!(restore_snapshot_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_sth_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_inclusion_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_consistency_json, m)?)?;
    m.add_function(wrap_pyfunction!(sth_fork_json, m)?)?;
    Ok(())
}
