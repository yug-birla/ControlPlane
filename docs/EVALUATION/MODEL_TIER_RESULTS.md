# Local Model Tier Comparison — FAST vs STRONG

**Run:** `controlplane/experiments/evaluate_model_tiers.py`, 2026-08-29.
**Raw:** `docs/EVALUATION/RESULTS/model_tiers_2026-08-29.json`
**Scale:** `SMOKE_TEST` — 10 short-answer cases. This is a capability sanity check, not a model benchmark.

| Tier | Model | Revision |
|---|---|---|
| FAST | `Qwen/Qwen2.5-1.5B-Instruct` | `989aa798…` |
| STRONG | `Qwen/Qwen3-4B` | `1cfa9a72…` |

## Result

| Metric | FAST (1.5B) | STRONG (4B) |
|---|---|---|
| **Accuracy** | **0.900** | 0.800 |
| ARITHMETIC (n=5) | 0.800 | 0.800 |
| REASONING (n=2) | **1.000** | 0.500 |
| RECALL (n=3) | 1.000 | 1.000 |
| Mean latency | 7,215 ms | 17,083 ms |
| ms per output token | 1,569 | 3,973 |

## The Honest Reading: STRONG Is Not Better Here

**The larger model did not outperform the smaller one on this benchmark. It scored lower overall and cost ~2.5× more per output token.**

This must be stated plainly because an earlier commit message in this project cited a single example — "17 × 23", where FAST answered 401 (wrong) and STRONG answered 391 (correct) — as evidence that "the tier difference is real, not nominal." That was one cherry-picked case, and the full 10-case set does not support the implication. The correction is recorded here rather than left standing.

The one clear STRONG failure is `MT-06`: an expense of \$12,000 placed in the "over \$25,000" band instead of "\$5,001–\$25,000" — a genuine band-selection reasoning error, and notably the *same* failure mode as `BVC-013` in the baseline-vs-ControlPlane run.

## Why This Result Is Not Conclusive Either

Three constraints materially handicap Qwen3-4B here, and none of them are the model's fault:

1. **`enable_thinking=False`.** Qwen3 is a *hybrid reasoning* model whose chat template emits a `<think>…</think>` block by default. This repository must never store hidden chain-of-thought, so thinking is disabled — which removes precisely the mechanism Qwen3 uses for multi-step reasoning. Measuring a reasoning model with reasoning switched off is a real limitation of this setup.
2. **`max_new_tokens=24`.** STRONG measures ~4 s per output token on this CPU, so a longer budget makes the experiment infeasible. Short budgets penalize any model that reasons before answering.
3. **n=10.** One case moves accuracy by 0.100. The REASONING sub-score rests on **two** cases; 0.500 vs 1.000 there is a single question.

So this is closer to **INCONCLUSIVE** than to a clean "the larger model is worse."

## Decision

Per the project's architecture-evolution rule (adopt only on evidence; on inconclusive evidence keep the established design and document what is needed):

**The tiering is kept**, because `docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md` names Qwen3-4B as the medium tier — that is the source-of-truth architecture, and this evidence is too weak to overturn it.

**But no quality claim is made for escalation.** Specifically:

- The Model Router's `CHANGE_MODEL` escalation is **demonstrated to change the model**, and is **NOT demonstrated to improve answer quality**.
- Any future report describing model escalation as a quality improvement must cite a benchmark that actually shows one. This one does not.
- `docs/PROJECT_STATE/CURRENT_STATE.md` and the ablation write-ups should be read with this caveat attached.

## What Would Settle It

1. A larger set (100+ cases) across arithmetic, multi-step reasoning, grounded QA, and long-form generation.
2. Thinking **enabled** for Qwen3, with the `<think>` block stripped before persistence — preserving the no-stored-CoT rule while letting the model use its intended mechanism. This is the single highest-value follow-up.
3. A realistic `max_new_tokens` (256+), which needs either GPU or overnight CPU batches.
4. Quality judged by the Prometheus 7B judge rather than exact-match on short answers, which would capture long-form differences that short-answer matching cannot.

Items 2–4 are all latency- or hardware-bound on this machine and are labelled `NOT_MEASURED` rather than estimated.
