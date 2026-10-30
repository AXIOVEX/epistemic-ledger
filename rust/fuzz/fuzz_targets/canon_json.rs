#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // Canonicalization must be idempotent: canonicalizing the
    // canonical form changes nothing.
    if let Some(canon) = epistemic_ledger_core::fuzzing::entry_canon_json(data) {
        let again = epistemic_ledger_core::fuzzing::entry_canon_json(canon.as_bytes());
        assert_eq!(again.as_deref(), Some(canon.as_str()));
    }
});
