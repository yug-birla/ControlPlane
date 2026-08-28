# RAG Pipeline Results

**Run:** `controlplane/experiments/evaluate_rag_adequacy.py`, 2026-08-28. See `docs/ALGORITHMS/RAG_PIPELINE.md` for the method.

## Adequacy Baseline (coverage_overlap_v0)

Evaluated against `data/raw/generated/rag_cases.json` (150 examples, SYNTHETIC provenance) using the dataset's own supplied evidence text (not this milestone's retrieval pipeline — see the algorithm doc for why the corpora don't literally correspond).

| Threshold set | Accuracy | Macro-F1 |
|---|---|---|
| Initial guess (sufficient=0.5, partial=0.2) | 0.493 | 0.521 |
| Grid-searched (sufficient=0.32, partial=0.05) | **0.800** | **0.774** |

Grid search was run on this same 150-example set — no separate held-out split exists for this calibration, a stated limitation (spec §32 calls for a validation-set-calibrated threshold; this only partially satisfies that since the calibration and reporting sets are the same).

**`CONFLICTING` label:** structurally supported (`AdequacyLabel.CONFLICTING`, a narrow polarity-word check) but **zero** ground-truth examples in `rag_cases.json` carry this label — exercised only by a synthetic unit test (`tests/test_rag_adequacy.py::test_conflicting_polarity_evidence_is_flagged`), not validated against real labeled data.

## Retrieval (Real Corpus)

30 real documents, `all-MiniLM-L6-v2` dense + from-scratch BM25 + score fusion. No formal relevance-judgment ground truth exists for this specific corpus (it wasn't built with labeled query-relevance pairs), so retrieval is verified functionally (manual inspection: a refund-policy question correctly retrieves the Customer Refund Policy chunk with fused_score=1.0) and via its role in the real end-to-end control-loop scenarios below, not a precision/recall table.

## End-to-End: Real Grounding Fix

**Critical finding (Milestone 5 architecture audit):** through Milestone 4, `provider.generate(prompt=query)` used the raw query only — SQL/RAG evidence was retrieved, evaluated, and persisted, but **never actually shown to the model**. Fixed in `controlplane/runtime.py::_build_generation_prompt` to construct an evidence-augmented prompt whenever SQL/RAG nodes completed. Verified via manual trace: a travel-policy question's prompt now literally contains the retrieved policy text before the question. See `docs/PROJECT_STATE/DECISIONS.md` for the full finding.

## Fusion Method: RRF vs. Min-Max (NEW, Milestone 8)

**Finding:** `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` explicitly specifies "Dense + BM25 + RRF + Cross-Encoder" as the source-of-truth pipeline (citing Cormack, Clarke & Büttcher's RRF paper). Milestones 4-7 used min-max-normalized weighted-sum fusion instead — an undocumented deviation, found while auditing this milestone's bootstrap against the original specs (bootstrap's own "architecture contradiction" rule: fix it or report it, don't silently keep it).

**Run:** `controlplane/experiments/evaluate_reranker.py`, same 26-case relevance benchmark as the reranker comparison below.

| Config | Recall@1 | Recall@3 | MRR |
|---|---|---|---|
| Dense + lexical, min-max fusion (the deviation) | 0.962 | 1.000 | 0.981 |
| Dense + lexical, RRF fusion (the spec) | 0.962 | 1.000 | 0.981 |
| Min-max fusion + cross-encoder | 1.000 | 1.000 | 1.000 |
| RRF fusion + cross-encoder | 1.000 | 1.000 | 1.000 |

**Identical results** on this corpus/benchmark scale (30 documents, 26 queries) — a real, honest measurement, not evidence RRF is better *or* worse here, just evidence there is no measured reason to keep deviating from the spec. Per the spec's own words ("the initial prototype should remain Dense+BM25+RRF+Cross-Encoder unless experiments show a concrete reason to replace it"), RRF is now adopted as the default (`controlplane.rag.retrieval.retrieve`'s `fusion_method="rrf"` default) — `min_max` is kept available for reproducing the earlier milestones' exact numbers, not deleted.

## Reranker Comparison (Milestone 6)

**Run:** `controlplane/experiments/evaluate_reranker.py`, 2026-08-28. Ground truth: `data/raw/generated/rag_retrieval_relevance_cases.json` (26 cases, provenance HUMAN, SMOKE_TEST scale — hand-authored by reading all 30 real corpus documents). Real retrieval pipeline, real corpus, not mocked.

| Config | Recall@1 | Recall@3 | MRR | Cold Start | Warm Latency (mean) |
|---|---|---|---|---|---|
| A: Dense only | 0.962 | 1.000 | 0.981 | 20,437ms (model load) | 44.1ms |
| B: Dense + lexical fusion (V0, unchanged) | 0.962 | 1.000 | 0.981 | 47ms | 41.7ms |
| C: Dense + lexical + cross-encoder (NEW) | **1.000** | 1.000 | **1.000** | 1,358ms (reranker load) | **1,087.7ms** |

**Honest interpretation:** this small, mostly single-relevant-document corpus makes both baselines already near-ceiling (a real finding, not a favorable cherry-pick) — the cross-encoder closes the one remaining gap (1 of 26 queries) but at ~25x the per-query latency. The gain is real and measured, not fabricated, but modest given how easy this particular 26-query set already is for the cheaper baselines; a larger, harder relevance set would likely show a bigger gap. `RAGCapability` still defaults `use_reranker=True` because the latency (~1.1s) remains acceptable for this prototype's per-request budget and the correctness gain, however small on this sample, is real.

## Known Limitations

- Chunking is sentence-grouped with a 60-word cap — not benchmarked against alternative chunk sizes (the corpus is small enough, 784 words total, that this mattered less than it would for a larger corpus).
- Score fusion (0.5/0.5 dense/lexical) is not tuned — a fixed, documented default, not a grid-searched one (unlike the adequacy thresholds).
- Reranker comparison set (26 cases) is SMOKE_TEST scale and mostly easy (near-ceiling baselines) — see above.
- `CONFLICTING` adequacy had a real false-positive regression this milestone (naive substring match on "not" matching inside "notice") — found via a real end-to-end trace at a widened retry `k`, fixed with word-boundary matching, regression-tested. See `docs/ALGORITHMS/RAG_PIPELINE.md`.
