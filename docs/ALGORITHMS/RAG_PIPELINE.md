# RAG Pipeline: Ingestion, Retrieval, Adequacy

**Status:** IMPLEMENTED — V0 (Milestone 4/5, 2026-08-28)

## Problem

Turn the 30-document synthetic enterprise corpus into real, queryable evidence: chunk → embed → retrieve (dense + lexical) → fuse → assess adequacy — replacing the `MOCKED` RAG handler used through Milestone 3.

## Architecture Location

`controlplane/rag/{ingestion,retrieval,adequacy}.py`, wired as a real capability in `controlplane/capabilities/rag_capability.py` and invoked by the Execution Graph's `RAG` node handler (`controlplane/runtime.py`).

## Ingestion / Chunking

`data/synthetic_enterprise/documents/` (30 files, 784 words total — these are short policy statements, not long documents, so chunking mostly yields one chunk per document). Sentence-grouped chunking, max 60 words/chunk. Embedded with the same local model already selected in Milestone 2 (`all-MiniLM-L6-v2` — no second model download). Embeddings disk-cached via `controlplane/models/embedding_cache.py` (the B9 fix, reused here for the same reproducibility guarantee).

## Retrieval — Baseline

Dense (cosine similarity) + lexical (BM25, implemented from scratch, ~40 lines, no new dependency) + min-max-normalized score fusion (0.5/0.5) as the "reranker." **Not a learned cross-encoder** — deferred, see Decisions.

## Adequacy — Baseline

`SUFFICIENT`/`PARTIALLY_SUFFICIENT`/`INSUFFICIENT`/`CONFLICTING` from query-term coverage across the evidence text (+ a narrow polarity-word conflict check for `CONFLICTING`). Thresholds (0.32 sufficient, 0.05 partial) grid-searched against `data/raw/generated/rag_cases.json` (150 existing labeled examples — reused rather than seeking new data, since it already had exactly the needed labels).

## Candidate Alternatives

- **Cross-encoder reranker** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) — considered, deferred given this milestone's scope (RAG + SQL + Gemini + Evaluation + Dashboard all in one pass); score fusion is a real, measured improvement over either signal alone and a defensible "small practical baseline" (bootstrap).
- **RAGAS/ARES-style LLM-judge adequacy** — deferred; the deterministic coverage baseline is measurably useful (0.80 accuracy) on existing labeled data, so bootstrap's "prefer deterministic → small model → LLM judge" ordering says try this first.

## Inputs / Outputs

Retrieval: `(query, k) -> list[RetrievedChunk]` (dense/lexical/fused scores). Adequacy: `(query, evidence_texts) -> AdequacyResult`.

## Dataset

Corpus: 30 documents (unlabeled — no formal relevance judgments exist for this specific corpus). Adequacy evaluation: `rag_cases` v0.1, 150 examples, SYNTHETIC provenance.

## Training / Fine-Tuning Requirement

None.

## Compute / Latency

CPU only. Real measured (`docs/EVALUATION/CONTROL_LOOP_RESULTS.md`/manual traces): retrieval ~20-125ms warm.

## Metrics

Adequacy: accuracy 0.80, macro-F1 0.774 (up from 0.493/0.521 at initially-guessed thresholds) — see `docs/EVALUATION/RAG_RESULTS.md`.

## Failure Modes

`CONFLICTING` label is structurally supported but has no ground-truth example in `rag_cases.json` to validate against — exercised only by a synthetic unit test (`tests/test_rag_adequacy.py`). Retrieval has no relevance ground truth for the real 30-document corpus (only functional/latency verification, not a precision/recall number).

## Result

Real, functional, wired into the live runtime — see `docs/EVALUATION/CONTROL_LOOP_RESULTS.md` for the end-to-end self-healing trace that exercises this pipeline for real (two live retrieval calls, k=5 then k=10).

## Final Decision

V0 adopted as the runtime default for the `RAG` capability node.

## Version

v1 — 2026-08-28.
