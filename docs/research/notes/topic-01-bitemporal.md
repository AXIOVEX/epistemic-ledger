# Topic 1 — Bitemporal data modeling (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism
- Two orthogonal time axes per fact:
  - **Valid time (VT):** period during which a fact is true in the modeled reality ("verifyToken() used RS256 from 2024-03-01 to 2025-01-17").
  - **Transaction time (TT):** period during which the fact was stored in the database ("the RS256 claim was in the database from 2024-03-02 to 2025-01-20").
- Bitemporal tuple = (proposition, VT_start, VT_end, TT_start, TT_end). Four query modes: current knowledge of current facts (VT_end=∞ AND TT_end=∞); historical knowledge (VT at T1 AND TT at T2); **retroactive corrections** (insert with past VT but current TT); rollback queries ("what did the system believe at TT=T2?").
- **Retroactive correction representation:** never mutate in place. Close the old record's TT interval at correction time and insert a new record with the corrected VT but current TT. A query with an earlier `known_at`/TT still returns the pre-correction answer, because the correction was not known yet. The original and corrected data remain visible simultaneously.
- Allen's interval algebra (Allen 1983, CACM 26:832–843) gives 13 primitive relations between intervals (before, meets, overlaps, starts, during, finishes, equals + inverses) for temporal queries.
- Half-open intervals [from, to) match the SQL:2011 `PERIOD FOR` convention; closing one interval and opening its successor at the same instant yields exactly one current row.
- "Bitemporal-lite" = valid-time state table + transaction-time audit; recognized defensible compromise (Snodgrass's motivating use case was precisely retroactive correction of recorded history, so systems that never edit the past may not need full bitemporality).
- Modern implementations: SQL:2011 standardized APPLICATION_TIME (valid) and SYSTEM_TIME (transaction) with `AS OF` queries; XTDB is a production bitemporal DB (snapshot/diff operators); Datomic (time-based); SQL Server temporal tables, MariaDB.

## Canonical references
1. Snodgrass & Ahn, "A Taxonomy of Time in Databases," SIGMOD 1985 — the VT/TT taxonomy.
2. Jensen et al., "The Consensus Glossary of Temporal Database Concepts," LNCS 1399 — standard vocabulary.
3. Allen, "Maintaining Knowledge about Temporal Intervals," Communications of the ACM 26:832–843, 1983 — interval algebra.
4. Snodgrass (ed.), TSQL2 (1995) — temporal SQL extension; later standardized in SQL:2011 (application time / system time).

## Practical limitations
- Querying two axes is conceptually and operationally harder; indexing bitemporal data is more expensive.
- No universal engine support; many teams hand-roll bitemporal-lite.
- Design tension: full bitemporality only pays off if you need retroactive correction of recorded history; otherwise audit logs suffice.
- Interval-boundary conventions ([from,to) vs closed) must be chosen consistently or "current" queries double-count.

## Sources
- https://github.com/adrianco/the-goodies/blob/HEAD/docs/adr/ADR-014-temporal-prior-art-and-platform.md (ADR on temporal prior art, cites Snodgrass & Ahn 1985; Jensen et al. 1994 LNCS 1399; Allen 1983; SQL:2011; XTDB; TPGM/Gradoop)
- https://github.com/bmf-san/bmf-tech/blob/HEAD/content/en/posts/nontemporarl-unitemporal-bitemporal-design.md (bitemporal table design example, retroactive correction of past validity periods)
- https://github.com/ekgardt/llm-wiki/blob/HEAD/docs/research/2026-08-28-bitemporal-claims.md (retroactive correction with known_at semantics; supersede-never-edit discipline)
- https://github.com/nodedb-lab/nodedb/blob/HEAD/docs/bitemporal.md (backdated corrections example with AS OF VALID TIME / AS OF SYSTEM TIME)
