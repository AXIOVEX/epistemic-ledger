# Topic 8 — LLM context and memory management ("context cleanup") (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism — four lines of attack

1. **Memory hierarchies (MemGPT/Letta).** Packer et al., "MemGPT: Towards LLMs as Operating Systems" (arXiv:2310.08560, 2023; UC Berkeley) — treat the context window like RAM and external stores like disk. Three tiers: **Core memory** (always in context; persona, key facts, editable by the agent), **Recall memory** (recent conversation, searchable), **Archival memory** (external DB, retrieved on demand). The agent manages its own memory via function calls; a **memory-pressure interrupt** forces it to summarize/evict when the window fills. Letta is the productionized, open, self-hostable successor. Motivation: bigger windows are quadratically expensive *and* models ignore the middle of long contexts ("lost in the middle"), so allocation beats capacity.
2. **Summarization / distillation.** Rolling compaction at token thresholds (e.g., compact at 8K); hierarchical summarization of older turns; MCOS-style three-tier mobile adaptation (core ~600–2000 tokens pinned, recall compacted, archival top-K(5) per turn).
3. **Consolidation & forgetting (offline > write-time).**
   - **Generative Agents** (Park et al., UIST 2023): **memory stream** = timestamped append-only log of observations; retrieval scored by **recency** (exponential decay) + **importance** (LLM-rated 1–10 at creation) + **relevance** (embedding cosine); **reflection** triggered when summed importance of recent events exceeds a threshold (150): agent poses salient questions, answers from retrieved memories, stores insights *with pointers to evidence* — a **reflection tree** (leaves = observations, internal nodes = inferences). Ablations: removing reflection degraded believability.
   - **Letta sleep-time compute:** dual-agent design — primary agent *cannot* edit core memory; an offline **sleep-time agent** rewrites shared blocks (`rethink_memory`). Explicit motivation: MemGPT-style incremental self-editing "became messy and disorganized over time." Pareto improvement in quality at lower interaction-time latency/cost.
   - **MemoryBank:** Ebbinghaus forgetting-curve decay + access reinforcement (frequently retrieved memories strengthen — retrieval-practice effect).
   - CoALA (Sumers et al. 2024): cognitive-science taxonomy — working, episodic, semantic, procedural memory; most frameworks implement only working + one external store.
   - Reflexion (Shinn et al., NeurIPS 2023): verbal self-reflection on failures stored in an episodic buffer; storing the *reflection* beats storing the failure.
4. **RAG source-document invalidation (the stale-index problem).** A vector DB is frozen in time; stale chunks ground confident wrong answers (indistinguishable from hallucination). Production strategies:
   - **Change detection by content hash:** re-crawl, re-chunk/re-embed only docs whose hash changed; stamp the rest as freshly verified — cost ∝ change, not corpus size.
   - **Deterministic chunk IDs** so re-indexing *replaces* rather than duplicates; delete chunks whose source disappeared (garbage collection tied to doc lifecycle).
   - **verified-at timestamps** on every chunk so retrieval/generation can filter or down-rank stale content; **TTL-based invalidation** (mark stale, re-embed on miss; background refresh).
   - **Versioned indexes for embedder upgrades:** embeddings from different models live in different vector spaces (mixing = garbage similarity). Pattern: build v2 index in parallel → shadow traffic → A/B 10% → cutover → keep v1 for rollback → decommission. Tag vectors with `embedder_version`.
   - **Cache invalidation:** versioned cache keys (`v{cache_version}` bumped on any doc change) + explicit delete-on-change + TTL safety net; fail-open on cache outage.
   - **Monitoring:** recall@5 on a frozen labeled eval set (alert on >5% weekly drop); top-1 similarity distribution drift; document coverage (never-retrieved docs are stale/irrelevant).
5. **Parametric knowledge editing** (for completeness): ROME (Meng et al. 2022 — causal tracing, rank-one MLP updates), MEMIT (2023 — batched multi-layer edits, thousands of facts), MEND. Suffers off-target effects and catastrophic forgetting in continual settings — not the SOTA for keeping *working context* accurate.

## State of the art (2026) for keeping working context accurate
- Retrieval-side freshness (hash-based change detection, versioned indexes, verified-at metadata) is the production-grade answer for RAG.
- For agent memory: hierarchical paging (Letta) + **offline consolidation** (sleep-time compute / reflect stages, e.g., Hindsight's 91.4% LongMemEval attributed largely to offline reflect: dedup, contradiction reconciliation, entity profiles) beats write-time extraction.
- Zep/Graphiti: bitemporal knowledge graphs for agents — every edge carries **event time** (when true in world) + **ingestion time** (when observed) → non-lossy retroactive correction and fact invalidation/supersession, hybrid semantic+BM25+graph retrieval at P95 ≈ 300ms, no LLM calls at retrieval. (Directly the "living ledger" shape: bitemporal + invalidation.)
- Frontier gap: **no production system runs a formal classical TMS at LLM-KG scale**; engineered detect-then-resolve pipelines (CRDL) and dual-memory routing (WISE) substitute for dependency-directed justification tracking (davidamitchell 2026 survey).

## Practical limitations
- Lost-in-the-middle: long contexts degrade; summarization loses detail and can introduce drift/hallucination.
- Self-edited memory becomes messy/disorganized over time (motivated Letta's sleep-time compute).
- Embedder upgrades force full re-indexing; mixing versions silently breaks retrieval.
- Staleness monitoring (drift metrics, frozen eval sets) is immature in most deployments; "append-only index forever" anti-pattern accumulates superseded vectors.
- Frontier LLMs measurably violate AGM rationality postulates under iterated belief revision — the reasoner itself is the weak link in any justification-tracking scheme.

## Sources
- https://github.com/atharvax16/til/blob/HEAD/papers/LLVM/MemGPT/memgpt-study-notes.md (Packer et al. arXiv:2310.08560; OS analogy; page faults; model as allocator; lost-in-the-middle motivation)
- https://github.com/haozhe-xing/agent_learning/blob/HEAD/src/en/chapter_memory/06b_memgpt_practice.md (three tiers; memory decay; access reinforcement; Letta docs)
- https://github.com/deibler/edmund-harness/blob/HEAD/docs/research/memory-architecture-2026-07-28.md (Generative Agents recency/importance/relevance + reflection threshold 150 + reflection tree; Letta sleep-time compute/rethink_memory; Hindsight arXiv 2512.12818)
- https://github.com/qr-madness/agentx/blob/HEAD/todo/research/2026-07-memory-recall-research.md (Zep/Graphiti bitemporal edges: event time + ingestion time; retroactive correction; P95 ≈ 300ms)
- https://github.com/coetzeevs/cerebro/blob/HEAD/docs/research/agent-memory-architectures-research.md (Generative Agents three-factor retrieval; CoALA four memory types; Reflexion)
- https://dev.to/promptcloud_services/scraping-for-rag-keeping-your-retrieval-index-fresh-and-why-staleness-hallucinates-3km8 (RAG freshness architecture: content hashing, volatility-matched TTLs, deterministic chunk IDs, verified-at, staleness as first-class metric)
- https://github.com/ather-techie/rag-interview-system/blob/HEAD/03_failure_modes/04-stale_index_problem.md (TTL-based invalidation with re-embed on miss; deletion handling)
- https://github.com/mrsameerkhan/sameerkhan/blob/HEAD/10.mlops/13_production_rag_ops.md (versioned indexes for embedder upgrades; shadow/A-B/cutover; recall@5 drift monitoring)
- https://github.com/huangsam/systology/blob/HEAD/site/content/principles/retrieval.md (index versioning, provenance metadata, "append-only index forever" anti-pattern, GC tied to doc lifecycle)
- https://arxiv.org/pdf/2512.13564v1 ("Memory in the Age of AI Agents": ROME/MEMIT/MEND knowledge editing; off-target effects; catastrophic forgetting)
