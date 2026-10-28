//! PyO3 bindings exposing the Rust core store to Python as
//! `epistemic_ledger._core` (DESIGN-13 stage 2). Payloads and
//! records cross the boundary as JSON strings so the byte-level
//! chain format is the only contract between the languages.

use std::collections::HashMap;
use std::path::PathBuf;

use ed25519_dalek::SigningKey;
use epistemic_ledger_core::checkpoint::DEFAULT_SEGMENT;
use epistemic_ledger_core::health::health_with_segment;
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
}

#[pymethods]
impl RustStore {
    /// Open (creating if needed) the Rust store at `path`, taking
    /// the single-writer lock.
    #[staticmethod]
    fn open(path: String) -> PyResult<RustStore> {
        Store::open(&PathBuf::from(path))
            .map(|inner| RustStore { inner })
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

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RustStore>()?;
    m.add_function(wrap_pyfunction!(health_json, m)?)?;
    m.add_function(wrap_pyfunction!(read_records_json, m)?)?;
    Ok(())
}
