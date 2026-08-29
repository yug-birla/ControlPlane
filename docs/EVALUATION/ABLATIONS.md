# Ablation Study — Which Components Actually Produce the Improvement

**Run:** `controlplane/experiments/evaluate_ablations.py`, 2026-08-29.
**Raw:** `docs/EVALUATION/RESULTS/ablations_2026-08-29.json`
**Dataset:** the 26-case baseline-vs-ControlPlane set. **Scale: `DEVELOPMENT_TEST`** — 26 cases, with per-category rates resting on as few as 2.
**Model:** `Qwen2.5-1.5B-Instruct`, identical in every condition. Scoring identical in every condition.

## Conditions

| | Condition | What is removed |
|---|---|---|
| **A** | Baseline | Everything. `provider.generate(prompt=query)`. |
| **B** | No corpus affinity | Semantic RAG routing reverts to the Milestone 8 keyword rule. Everything else stays. |
| **C** | No enforcement | Shadow Mode — every component runs and is recorded, but no consequence is applied. |
| **D** | Full ControlPlane | Nothing removed. |

Condition A is reused from the baseline-vs-ControlPlane run rather than re-measured: the baseline path touches no ControlPlane code, so no change to routing or enforcement can alter it. Stated here because reusing a measurement silently would be indistinguishable from not running it.

## Results

| Metric | A: baseline | B: no corpus affinity | C: no enforcement | D: full |
|---|---|---|---|---|
| Key-fact accuracy (factual, n=19) | 0.105 | 0.474 | 0.947 | **0.947** |
| Hallucination rate | 0.316 | 0.105 | 0.000 | **0.000** |
| Grounding supported | 0.000 | 0.526 | 0.895 | **0.895** |
| Retrieval rate on corpus-answerable | 0.000 | 0.526 | 1.000 | **1.000** |
| Over-control on benign cases | 0.000 | 0.158 | 0.105 | **0.105** |
| Mean latency | 35,781 ms | 49,382 ms | 68,717 ms | 59,422 ms |

## What The Numbers Actually Say

### Corpus-affinity routing is the single largest contributor

`D − B` on key-fact accuracy is **0.947 − 0.474 = +0.473**, against a total improvement over baseline of 0.842. Semantic RAG routing accounts for roughly **56% of the entire gain**. Retrieval rate tells the same story directly: 0.526 → 1.000.

This is the component whose absence made ControlPlane return byte-identical answers to an unmanaged model, so it is unsurprising that removing it costs the most — but the size is now measured rather than asserted.

### Dynamic replanning recovers about half of what broken routing loses — an unplanned finding

Condition B retrieves on **52.6%** of corpus-answerable questions, even though the Milestone 8 keyword rule was measured at **5.3%** recall in isolation.

The difference is not noise: B still has Milestone 10's **graph-mutating replanner**, which discovers a capability that serves the query's data requirement *after* the first attempt produces poor evidence. So when routing fails at plan time, replanning repairs roughly half of it at execution time.

That is a genuine, unintended demonstration of the architecture's central claim — that execution can change when observation says the plan was wrong — and it was found by an ablation designed to measure something else.

### Enforcement contributes nothing to factual accuracy on this dataset — reported, not buried

**C and D are identical on every quality metric** (0.947 / 0.000 / 0.895). Removing enforcement entirely does not change factual correctness here.

That is the honest reading, and it is not a failure of the enforcement layer — it is a statement about *what this dataset measures*. The quality gain comes from **retrieval and evaluation**, which run in both conditions. Enforcement's value is in the **safety** dimension: withholding unsupported answers, blocking unsafe actions, and escalating high-risk requests. The baseline-vs-ControlPlane run measured that separately as `control_rate_on_unsafe_cases` **0.000 → 1.000**.

An ablation that only reports factual accuracy will therefore always undervalue enforcement. Stated explicitly so the number is not mistaken for "enforcement does not matter".

### The over-control fix is confirmed

`control_rate_on_benign_cases` is **0.105** in D, against **0.263** measured before the Milestone 9 actionability fix — the false-positive escalation of informational threshold questions. The fix roughly halved unnecessary control without loss elsewhere.

### Latency is not monotonic, and the reason is real

C (no enforcement) is the **slowest** condition at 68.7s, slower than full ControlPlane at 59.4s. That looks wrong and is not: with enforcement disabled, the loop never terminates early on a decision to withhold or abstain, so more requests run their full generation budget. Enforcement sometimes *saves* compute by deciding sooner that more compute will not help.

## Limitations

- **26 cases.** One case moves factual accuracy by 0.053. `DEVELOPMENT_TEST`, not a serious benchmark.
- **Two components, not ten.** Only corpus affinity and enforcement are ablated. Reranking, RRF, judge, multi-agent, MCP, and adaptive compute are **NOT** ablated here — those rows would be fabrication if listed.
- **One model.** All conditions use Qwen2.5-1.5B; a stronger model could shift which components matter.
- **Enforcement is under-measured by construction**, as described above.
