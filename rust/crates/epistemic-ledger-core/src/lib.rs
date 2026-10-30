//! Epistemic ledger core engine (DESIGN-13). Stage 1: the chain
//! layer — canonical encoding, hash chain, signatures, log lines.

pub mod canon;
pub mod chain;
pub mod checkpoint;
pub mod fuzzing;
pub mod governance;
pub mod health;
pub mod partitions;
pub mod snapshot;
pub mod sth;
pub mod store;
