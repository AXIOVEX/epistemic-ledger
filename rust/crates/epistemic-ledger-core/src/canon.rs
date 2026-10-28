//! Canonical JSON per RFC 8785 (subset used by chain format v1):
//! sorted object keys, no whitespace, minimal string escaping, and
//! numbers laid out by the ECMAScript number-to-string algorithm.
//! Mirrors tools/chainref.py exactly; tests/vectors.json arbitrates.

use serde_json::Value;

/// Shortest round-trip digits for a finite f64 plus the decimal
/// point position n, such that value = 0.digits * 10^n. Extracted
/// from ryu's shortest form (via serde_json's number formatting),
/// then re-laid-out under ECMAScript rules in `es_number`.
fn shortest_digits(x: f64) -> (String, i32) {
    let raw = serde_json::Number::from_f64(x.abs())
        .expect("finite")
        .to_string();
    let (mant, exp) = match raw.split_once(['e', 'E']) {
        Some((m, e)) => (m.to_string(), e.parse::<i32>().unwrap_or(0)),
        None => (raw, 0),
    };
    let (ip, fp) = match mant.split_once('.') {
        Some((i, f)) => (i.to_string(), f.to_string()),
        None => (mant, String::new()),
    };
    let mut digits = format!("{ip}{fp}");
    let mut point_exp = exp - fp.len() as i32;
    digits = digits.trim_start_matches('0').to_string();
    let trimmed = digits.trim_end_matches('0').to_string();
    point_exp += (digits.len() - trimmed.len()) as i32;
    let n = point_exp + trimmed.len() as i32;
    (trimmed, n)
}

/// ECMAScript Number::toString for an f64 (RFC 8785 section 3.2.2).
pub fn es_number(x: f64) -> String {
    assert!(x.is_finite(), "non-finite numbers are not valid in payloads");
    if x == 0.0 {
        return "0".to_string();
    }
    let sign = if x < 0.0 { "-" } else { "" };
    let (digits, n) = shortest_digits(x);
    let k = digits.len() as i32;
    let body = if k <= n && n <= 21 {
        format!("{}{}", digits, "0".repeat((n - k) as usize))
    } else if 0 < n && n <= 21 {
        format!("{}.{}", &digits[..n as usize], &digits[n as usize..])
    } else if -6 < n && n <= 0 {
        format!("0.{}{}", "0".repeat((-n) as usize), digits)
    } else if k == 1 {
        let e = n - 1;
        format!("{}e{}{}", digits, if e >= 0 { "+" } else { "-" }, e.abs())
    } else {
        let e = n - 1;
        format!(
            "{}.{}e{}{}",
            &digits[..1],
            &digits[1..],
            if e >= 0 { "+" } else { "-" },
            e.abs()
        )
    };
    format!("{sign}{body}")
}

/// Canonical JSON string for a payload value.
pub fn canonical_json(value: &Value) -> String {
    let mut out = String::new();
    write_canonical(value, &mut out);
    out
}

fn write_canonical(value: &Value, out: &mut String) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                out.push_str(&i.to_string());
            } else if let Some(u) = n.as_u64() {
                out.push_str(&u.to_string());
            } else {
                out.push_str(&es_number(n.as_f64().expect("number")));
            }
        }
        Value::String(s) => {
            out.push_str(&serde_json::to_string(s).expect("string escapes"));
        }
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_canonical(item, out);
            }
            out.push(']');
        }
        Value::Object(map) => {
            // serde_json's default Map is a BTreeMap: keys iterate sorted.
            out.push('{');
            for (i, (k, v)) in map.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str(&serde_json::to_string(k).expect("key escapes"));
                out.push(':');
                write_canonical(v, out);
            }
            out.push('}');
        }
    }
}
