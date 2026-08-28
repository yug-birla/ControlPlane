# RAG Pipeline: Ingestion, Retrieval, Reranking, Adequacy

**Status:** IMPLEMENTED — V1 (Milestone 6 adds a real cross-encoder reranker, 2026-08-28; V0 was Milestone 4/5)

## Problem

Turn the 30-document synthetic enterprise corpus into real, queryable evidence: chunk → embed → retrieve (dense + lexical) → fuse → assess adequacy — replacing the `MOCKED` RAG handler used through Milestone 3.

## Architecture Location

`controlplane/rag/{ingestion,retrieval,adequacy}.py`, wired as a real capability in `controlplane/capabilities/rag_capability.py` and invoked by the Execution Graph's `RAG` node handler (`controlplane/runtime.py`).

## Ingestion / Chunking

`data/synthetic_enterprise/documents/` (30 files, 784 words total — these are short policy statements, not long documents, so chunking mostly yields one chunk per document). Sentence-grouped chunking, max 60 words/chunk. Embedded with the same local model already selected in Milestone 2 (`all-MiniLM-L6-v2` — no second model download). Embeddings disk-cached via `controlplane/models/embedding_cache.py` (the B9 fix, reused here for the same reproducibility guarantee).

## Retrieval — Baseline

Dense (cosine similarity) + lexical (BM25, implemented from scratch, ~40 lines, no new dependency) + min-max-normalized score fusion (0.5/0.5) as the candidate-generation stage.

## Reranking — Real Cross-Encoder (NEW, Milestone 6)

`controlplane/rag/reranker.py`: `cross-encoder/ms-marco-MiniLM-L-6-v2`, revision `c5ee24cb16019beea0893ab7796b1df96625c6b8` (pinned; MS MARCO passage-ranking cross-encoder, ~23M params, ~90MB, Apache-2.0; already fully cached locally, no download needed). `retrieve(..., rerank=True)` widens candidate generation to `max(k*3, 10)` via fusion, then re-scores/re-sorts that set with real query/passage cross-attention (not two independently-encoded vectors compared by cosine similarity, unlike the fusion stage). `RAGCapability` defaults `use_reranker=True` — a real, live stage in the runtime path, not unused infrastructure (kept as a constructor flag so the comparison experiment can run the identical capability with it off).

## Adequacy — Baseline

`SUFFICIENT`/`PARTIALLY_SUFFICIENT`/`INSUFFICIENT`/`CONFLICTING` from query-term coverage across the evidence text (+ a narrow polarity-word conflict check for `CONFLICTING`). Thresholds (0.32 sufficient, 0.05 partial) grid-searched against `data/raw/generated/rag_cases.json` (150 existing labeled examples — reused rather than seeking new data, since it already had exactly the needed labels).

**Regression fixed this milestone:** the `CONFLICTING` polarity check used a naive substring match (`"not" in text`), which matched "not" inside the unrelated word "notice" ("Resignation **not**ice is 30 days") — found via a real end-to-end trace of the RAG self-healing scenario at a widened retry `k` (bringing more, more topically-diverse candidate chunks into the same adequacy check made the false-positive reachable in practice, where it hadn't been at the smaller default `k`). Same root cause as Milestone 3's actionability false-positive (keyword presence, no word-boundary awareness); fixed the same way — `\bword\b` regex matching. Regression test: `tests/test_rag_adequacy.py::test_polarity_word_inside_an_unrelated_word_is_not_flagged_as_conflicting_regression`.

## Candidate Alternatives

- **RAGAS/ARES-style LLM-judge adequacy** — deferred as the *adequacy* mechanism; the deterministic coverage baseline is measurably useful (0.80 accuracy) on existing labeled data. A judge-based semantic **grounding** comparison was built instead (`docs/ALGORITHMS/LLM_JUDGE.md`) — a related but distinct question (is the evidence enough vs. does the answer match the evidence).
- **NLI/entailment model for grounding** — considered instead of a general-purpose judge; rejected in favor of reusing the already-validated Local Judge (one fewer model to download/maintain), at the cost of a less specialized signal than a dedicated NLI cross-encoder would give.

## Inputs / Outputs

Retrieval: `(query, k, rerank) -> list[RetrievedChunk]` (dense/lexical/fused/cross_encoder scores). Adequacy: `(query, evidence_texts) -> AdequacyResult`.

## Dataset

Corpus: 30 documents. Adequacy evaluation: `rag_cases` v0.1, 150 examples, SYNTHETIC provenance. Reranker evaluation: `data/raw/generated/rag_retrieval_relevance_cases.json` (NEW, 26 cases, provenance HUMAN — hand-authored by reading all 30 real corpus documents and writing one query per targeted document, since `rag_cases.json`'s inline evidence snippets don't literally correspond to this corpus).

## Training / Fine-Tuning Requirement

None.

## Compute / Latency

CPU only (NO-GPU DEMONSTRATION ENVIRONMENT). Real measured, this machine: fusion-only retrieval ~42-47ms warm; **cross-encoder reranking adds ~1.0-1.1s warm** (scoring ~30 candidate chunks per query, one small-transformer forward pass per candidate) — a real, non-trivial CPU cost, stated plainly rather than hidden. See `docs/EVALUATION/RAG_RESULTS.md`.

## Metrics

Adequacy: accuracy 0.80, macro-F1 0.774 (up from 0.493/0.521 at initially-guessed thresholds). Reranker comparison (26-case SMOKE_TEST, `docs/EVALUATION/RAG_RESULTS.md`): dense-only and dense+lexical fusion both already reach recall@1=0.962/recall@3=1.0/MRR=0.981 on this corpus; adding the cross-encoder reaches recall@1=1.0/recall@3=1.0/MRR=1.0 — a real but modest gain (this small, mostly single-relevant-document corpus makes the baselines close to ceiling already), at ~25x the latency.

## Failure Modes

`CONFLICTING` label is structurally supported but still has no ground-truth *positive* example in `rag_cases.json` (its dataset only ever labels these as `INSUFFICIENT` via a `failure_mode: "conflicting_evidence"` field, not the `CONFLICTING` adequacy value) — exercised by a synthetic unit test and, this milestone, a real false-positive regression (see above, now fixed and regression-tested). Retrieval has no relevance ground truth for the real 30-document corpus beyond the 26-case reranker comparison set (not exhaustive over all 30 documents).

## Result

Real, functional, wired into the live runtime, now including a real cross-encoder reranking stage — see `docs/EVALUATION/CONTROL_LOOP_RESULTS.md` for the end-to-end self-healing trace that exercises this pipeline for real (two live retrieval calls, k=5 then k=10, both reranked).

## Final Decision

V1 (with cross-encoder reranking, `use_reranker=True` by default) adopted as the runtime default for the `RAG` capability node.

## Version

v2 — 2026-08-28 (v1 was Milestone 4/5's fusion-only baseline).
