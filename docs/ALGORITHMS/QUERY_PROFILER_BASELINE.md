# Query Profiler Baseline

**Status:** IMPLEMENTED (Milestone 2, 2026-08-28)

## Problem

Produce a Query Fingerprint (intent, domain, data_requirement, complexity, sensitivity, ambiguity, impact, actionability, capability_hints) from a raw query, explainably, with no training step and no learned model (bootstrap SS7-8).

## Architecture Location

`controlplane/query_intelligence/` — `fingerprint.py` (schema), `rules.py` (Baseline A), `exemplar_bank.py` + `knn_profiler.py` (Baseline B: embedding k-NN, and the Hybrid combiner used as the runtime default).

## Baseline A: Deterministic Rules

Keyword/regex matching against hand-curated trigger lists per dimension (SQL/RAG/action/reasoning/coding/PII keywords), plus a word-count-based complexity heuristic and a question-mark-based ambiguity heuristic. Zero training data, zero model calls. Every match traces to a literal keyword (`explanation` dict on the returned fingerprint).

## Baseline B: Embedding k-NN

Encodes the query with the local embedding model (`docs/ALGORITHMS/LOCAL_EMBEDDING_MODEL.md`), finds the k=5 nearest exemplars (by cosine similarity) in the 135-record train split, and majority-votes each field directly from what those exemplars already carry. No training step — the "model" is the frozen embedding function plus existing labeled data.

## Hybrid (Runtime Default)

Rules run first; a field is only trusted from rules when a **specific keyword/pattern actually fired** (tracked explicitly via `high_confidence_fields` — not merely "rules produced some value," since word-count/question-mark heuristics always produce a value even with no real signal — this distinction was a bug found and fixed during Milestone 2, see `docs/PROJECT_STATE/PROGRESS.md`). Everything else defers to the k-NN vote. List-valued fields (`capability_hints`, `data_requirement`) union both methods' outputs.

## Candidate Alternatives

- **Pure LLM-prompted classification (Groq)** — considered for SS25's comparison experiment only, explicitly not as the production default (bootstrap SS8: "Groq fallback only if justified"; adding a remote call to every query's classification step would add latency/cost this milestone doesn't need for a task the local hybrid already handles at ~20ms).
- **A dedicated fine-tuned classifier** — rejected per bootstrap SS21 (no measured baseline gap yet to justify it).

## Inputs / Outputs

Input: query string. Output: `QueryFingerprint` (see `fingerprint.py`).

## Dataset

`query_profiles_train` (135 examples, exemplar bank only) and `query_profiles_validation` (28 examples, evaluation only) — see `docs/EVALUATION/DATASETS.md`.

## Training / Fine-Tuning Requirement

None for either baseline.

## Compute / Latency

CPU only. Hybrid: ~20ms warm (dominated by the embedding call) — see `docs/EVALUATION/MODEL_BENCHMARKS.md`.

## Metrics

See `docs/EVALUATION/QUERY_PROFILER_RESULTS.md` for full accuracy/F1/confusion-matrix results and their limitations.

## Failure Modes

Local model unavailable -> `ConfigurationError` from `controlplane/runtime.py` (never a silent fallback to a remote model). Zero rule matches -> `capability_hints=[GENERAL]` floor, never an empty list.

## Result

Empirically, Hybrid beats Rules on actionability accuracy (+7.2pp) and capability-hint macro-F1 (+6.1pp), ties on ambiguity and complexity, loses on sensitivity (-7.1pp, see the results doc for the safety-relevant caveat this specific loss carries).

## Final Decision

Hybrid is the runtime default (`controlplane/runtime.py`), chosen empirically per bootstrap SS20, not by intuition. Complexity classification is flagged as needing rework before any future component gates behavior on it (see results doc).

## Version

v1 -- 2026-08-28.
