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

## Known Limitations

- Chunking is sentence-grouped with a 60-word cap — not benchmarked against alternative chunk sizes (the corpus is small enough, 784 words total, that this mattered less than it would for a larger corpus).
- Score fusion (0.5/0.5 dense/lexical) is not tuned — a fixed, documented default, not a grid-searched one (unlike the adequacy thresholds).
- No cross-encoder reranker (deferred, see algorithm doc).
