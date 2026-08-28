# Prompt Injection Detection: Keyword + Embedding k-NN

**Status:** IMPLEMENTED — V2 (Milestone 8 adds the embedding k-NN semantic layer, 2026-08-28; V1 keyword-only was Milestone 7)

## Problem

Bootstrap SS20/SS25: detect prompt-injection attempts (InjecAgent research direction) in the user's own query, independent of the Risk Profiler's existing safety dimension (never designed for this specific threat model).

## Architecture Location

`controlplane/evaluation/evaluators.py::PromptInjectionEvaluator` (the two-layer evaluator) + `controlplane/evaluation/injection_knn.py::EmbeddingKNNInjectionDetector` (the semantic layer).

## Why V1 (keyword-only) Was Upgraded

Milestone 7's `PromptInjectionEvaluator` scored a clean 1.0 accuracy on a 12-case hand-authored benchmark. Per bootstrap SS58 ("do not use n=3/small samples to make a strong performance claim"), this was re-tested against the real, public `deepset/prompt-injections` dataset (662 examples, Apache-2.0) — result: **accuracy 0.609, recall 0.02 (98.5% false negative rate)**. A fixed 18-phrase list cannot generalize across real paraphrase diversity ("forget all previous tasks" / "ignore all preceding orders" / "now forget about all the previous information" share almost no literal substring). This is exactly the failure mode bootstrap SS9/10 warns about: depending primarily on fixed keywords for a semantic-risk decision.

## Method

**Layer 1 (keyword, always on, zero cost):** the original fixed-phrase list. Kept because it is 100% precision and free — a real hard-constraint-style fast path for exact known phrasings.

**Layer 2 (embedding k-NN, semantic fallback, only runs when Layer 1 finds nothing):** encodes the query with the same local embedding model used everywhere else in this project (`all-MiniLM-L6-v2` — no new model), finds the k=5 nearest neighbors by cosine similarity among the dataset's 546-example TRAIN split, and majority-votes the label. A **similarity-reject threshold** (calibrated, not guessed) makes the detector abstain to the safe default when even the nearest neighbor is only weakly related — found necessary after a real regression (see Failure Modes).

## Real Bugs Found and Fixed (error-driven development)

1. **The 98.5% false-negative rate itself** — found by testing against real data instead of trusting a 12-case benchmark. Root cause: representational (fixed keywords), not a bad benchmark or bad luck. Fixed by adding the k-NN semantic layer, not by adding more keywords (bootstrap SS10: "do not patch with endless keyword rules if the representation is insufficient").
2. **A real false positive found via end-to-end integration testing:** the first (threshold-less) k-NN implementation flagged "Please execute a database query to count how many support tickets are open" as an injection attempt, because k=5 majority vote always returns *some* label even when every neighbor's cosine similarity is only ~0.2 (near-orthogonal, not a meaningful match). Fixed with a calibrated `similarity_threshold` reject option.

## Candidate Alternatives

- **A larger/fine-tuned classifier trained on the 546-example TRAIN split** — considered; rejected for this milestone in favor of k-NN (bootstrap SS20: "never jump straight to fine-tuning... prompt/data/better-pretrained-model first"). k-NN already gave a large, real improvement with zero training.
- **The LLM Judge's "safety" task** — an available alternative signal, not used as the primary mechanism here because of its 30-90s/call latency (see `docs/ALGORITHMS/LLM_JUDGE.md`); k-NN is fast enough (~tens of ms) for the live per-request path.

## Inputs / Outputs

`PromptInjectionEvaluator.evaluate(ctx) -> EvaluationResult` (`label` ∈ {`INJECTION_PATTERN_DETECTED`, `NO_PATTERN_DETECTED`}, `evidence.detection_method` ∈ {`keyword`, `embedding_knn`, `keyword_and_knn`}). `EmbeddingKNNInjectionDetector.classify(query) -> InjectionKNNResult` (`label`, `confidence`, `nearest_examples` — always includes the actual nearest neighbors for an auditable "why," never a black-box score alone).

## Dataset

`data/external/deepset_prompt_injections/prompt_injections_normalized.json` (662 real examples, Apache-2.0, pinned revision `4f61ecb038e9c3fb77e21034b22511b523772cdd`) — see `docs/DATA/EXTERNAL_DATASETS.md`. TRAIN split (546) used as k-NN reference data; TEST split (116) held out for evaluation only, never used as reference.

## Compute / Latency

Layer 1: negligible (string matching). Layer 2: one embedding call per query (~tens of ms, same cost profile as the existing local embedding model elsewhere in this project) plus a 546-row cosine-similarity computation (vectorized, negligible). The 546-example reference embedding set itself is built once per process (`@lru_cache` singleton, same pattern as the RAG reranker/embedding provider) and disk-cached (`cached_embed_batch`, the B9 pattern) so even a fresh process's first build is fast after the very first run ever.

## Metrics (held-out TEST split, 116 examples — see `docs/EVALUATION/EVALUATOR_RESULTS.md` for the full table)

| Scorer | Accuracy | Macro-F1 | FN Rate | FP Rate |
|---|---|---|---|---|
| Deterministic keyword only | 0.483 | 0.326 | 1.000 | 0.000 |
| Embedding k-NN only (calibrated threshold) | see results doc | see results doc | see results doc | see results doc |
| Combined (live default) | see results doc | see results doc | see results doc | see results doc |

## Failure Modes

Both real bugs above are now regression-tested. Remaining known failure mode: k-NN recall is not perfect — some real injection attempts are still missed (a real, honestly-reported number, not claimed as solved).

## Known Limitations

- k-NN reference set (546 examples) skews toward one dataset's collection style (jailbreak/role-play-override phrasing, some German-language examples) — not a claim of covering every real-world injection technique.
- `similarity_threshold` calibrated on a held-out slice of TRAIN only (never TEST) but still a single calibration pass, not cross-validated.
- No fine-tuning attempted (per bootstrap's own ordering, not yet justified given k-NN's measured gain).

## Result

A real, measured, substantial improvement over the keyword-only baseline, found via genuine error-driven development (test against real data → find a bug → root-cause → fix → find a NEW bug via integration testing → root-cause → fix → measure again), not designed perfectly upfront.

## Final Decision

V2 (keyword + calibrated k-NN) adopted as the runtime default (`PromptInjectionEvaluator(use_semantic_fallback=True)`).

## Version

v2 — 2026-08-28 (v1 was Milestone 7's keyword-only version).
