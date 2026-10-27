# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.12.x | Yes |
| < 0.12 | No (research prototype releases, pre-PyPI) |

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's "Report a
vulnerability" button on the Security tab of
https://github.com/AXIOVEX/epistemic-ledger — do not open a public
issue for a security problem.

The ledger is a single-writer, local store. The most security-relevant
surfaces are store integrity (the `verify` command detects tampering
with the projection or the event log), the signed-verdict machinery,
and the optional consolidation client, which is the only component
that can make network calls, and only when a caller runs it on purpose.
