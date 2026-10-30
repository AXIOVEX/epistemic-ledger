#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    epistemic_ledger_core::fuzzing::entry_chain_line(data);
});
