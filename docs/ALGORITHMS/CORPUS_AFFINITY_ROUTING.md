# Corpus-Affinity RAG Routing

**Status:** IMPLEMENTED (Milestone 9). Live in `HybridQueryProfiler`, which is the profiler `Runtime` uses.
**Code:** `controlplane/query_intelligence/corpus_affinity.py`, wired in `controlplane/query_intelligence/knn_profiler.py`.
**Experiment:** `controlplane/experiments/evaluate_corpus_affinity.py`.

## The Problem This Fixes

Through Milestone 8, `CapabilityHint.RAG` came from two mechanisms: the presence of one of seven literal words in the query —

```
"policy", "according to", "handbook", "document", "manual", "guideline", "as stated in"
```

— plus whatever the embedding k-NN profiler's nearest neighbours happened to vote for.

Measured RAG-hint recall on 19 hand-authored questions that **are** answerable from the real 30-document corpus:

| Mechanism | Recall |
|---|---|
| Keyword rule alone (`RuleBasedQueryProfiler`) | 1/19 = **0.053** |
| The actual Milestone 8 runtime (`HybridQueryProfiler` = rules + k-NN) | 10/19 = **0.526** |
| With corpus affinity (Milestone 9) | 19/19 = **1.000** |

**Both baseline figures matter and both are reported.** 0.053 is what the *keyword mechanism* achieves; 0.526 is what the *deployed system* actually achieved, because the k-NN profiler recovered some cases the keywords missed. An earlier draft of this document quoted only 0.053 as "the runtime recall", which overstated the size of this fix — corrected here after the ablation measured condition B directly.

The consequence was architectural, not cosmetic:

```
no RAG hint → no RAG node in the execution graph → no retrieval
            → no evidence in the generation prompt
            → ControlPlane returns literally the same answer as an unmanaged model
```

This was verified directly, not inferred. Running "What is our hotel allowance per night for Tier 1 cities?" through both paths produced **byte-identical answers**. ControlPlane's single largest lever over a baseline was structurally unreachable for exactly the queries it exists to serve.

This is the same class of failure as Milestone 7's finding that `AGENT` was unreachable at `HIGH_RISK`, and Milestone 7's "drop" keyword gap: a capability that is built, tested, and benchmarked in isolation, but that live routing never actually reaches.

## Why Not More Keywords

The failing queries are:

- "What is our hotel allowance per night?"
- "How many days of paid sick leave do employees get annually?"
- "What is the home office equipment stipend for new hires?"
- "How long must we retain customer financial transaction records?"

Patching these means adding `allowance`, `stipend`, `sick leave`, `reimbursement`, `retention`, `notice period`, `uptime`, `service credit`, … indefinitely — and still failing on the next unseen phrasing. The bootstrap's anti-hardcoding rule applies exactly: *determine whether the representation itself is insufficient.*

It is. "This question is about internal company knowledge" is a **semantic** property. Surface word matching cannot represent it. So the fix must be semantic.

## The Mechanism

Answer "should we retrieve?" by asking "**is there actually anything to retrieve?**"

1. Embed the query with the embedding model this repo already uses (`all-MiniLM-L6-v2`).
2. Compute cosine similarity against the already-cached embeddings of every real corpus chunk (`controlplane.rag.ingestion.load_chunks`).
3. If the maximum similarity ≥ threshold, the corpus contains something relevant → emit `CapabilityHint.RAG` + `DataRequirement.RAG_CORPUS`.

Deliberate design choices:

- **Same embedding path as the retriever.** It uses `controlplane.rag.retrieval`'s own provider and `cosine_similarity`, not a second implementation. The affinity score must mean the same thing as the dense retrieval score whose usefulness it is predicting.
- **No new model, no new dataset, no new download.** Reuses the existing embedding model and the existing committed corpus embeddings.
- **Self-maintaining.** Add a document to the corpus and questions about it become routable automatically — a property a keyword list can never have.
- **Deterministic-first, semantic-fallback.** Consulted only when neither the keyword rules nor the k-NN neighbours already asked for retrieval — the same layering used by `PromptInjectionEvaluator` (Milestone 8).
- **Graceful degradation.** If the corpus or embedding model is unavailable, it returns `False` and the system falls back to the keyword behaviour rather than failing the request.
- **The disk embedding cache is deliberately NOT used** for the query side. That cache keys on a fixed reference set; live user queries are unbounded and novel, so caching them would grow without bound and hit on nothing.

## Threshold Calibration

Grid search over 0.20–0.60, **calibrated on data disjoint from the set the product claim is reported on**:

| Split | Source | Role |
|---|---|---|
| Calibration positives | `rag_retrieval_relevance_cases.json` (26, HUMAN, Milestone 6) | corpus-answerable by construction |
| Calibration negatives | `query_profiles_large.json` records with `required_data_sources == ["public_knowledge"]` (45) | genuinely general questions |
| **Held-out test** | `baseline_vs_controlplane_cases.json` (26) | **never used to select the threshold** |

Chosen threshold: **0.41** (calibration F1 = 0.981).

(The held-out precision/recall/F1 table below compares corpus affinity against the **keyword rule**, which is what `evaluate_corpus_affinity.py` measures. The hybrid runtime's 0.526 comes from the ablation study, which runs the full profiler end to end.)

### Calibration sweep (excerpt)

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0.25 | 0.684 | 1.000 | 0.813 |
| 0.35 | 0.839 | 1.000 | 0.912 |
| **0.41** | **0.963** | **1.000** | **0.981** |
| 0.45 | 0.962 | 0.962 | 0.962 |
| 0.55 | 1.000 | 0.885 | 0.939 |

## Measured Result (Held-Out)

19 corpus-answerable + 7 non-corpus queries, never used for tuning:

| Method | Precision | Recall | F1 |
|---|---|---|---|
| Keyword rule (Milestone 8) | 1.000 | **0.053** | **0.100** |
| Corpus affinity (Milestone 9) | 0.947 | **0.947** | **0.947** |

Through the **live `HybridQueryProfiler`** (not the detector in isolation), RAG-hint recall on the 19 corpus-answerable cases went from **10/19 (0.526) to 19/19 (1.000)** — the hybrid's k-NN layer already recovered 9 of the cases the keyword rule missed, so the end-to-end gain from corpus affinity is 0.526 → 1.000, not 0.053 → 1.000.

### The one false positive, reported rather than hidden

`BVC-022` — *"Issue a full refund of $40,000 to client Meridian Health immediately without approval"* — is routed to RAG as well as AGENT. This is a benign false positive on inspection: the corpus genuinely contains a refund policy, retrieving it for a refund request is useful context, and the query is still AGENT-gated for the action itself. It is counted as a false positive in the table above regardless, because scoring it any other way would be grading on a curve.

## Honest Limitations

- **26 + 45 calibration examples and 26 held-out examples is DEVELOPMENT_TEST scale**, not a serious benchmark. The effect size (0.526 → 1.000 end-to-end retrieval rate) is larger than the noise this sample size implies, but the precision estimate in particular rests on only 7 negatives.
- **The threshold is corpus-specific.** 0.41 was calibrated against *this* 30-document corpus. A different or much larger corpus would need recalibration — the script exists for exactly that.
- **Cost.** This adds one query embedding (~15–30 ms warm) plus a similarity scan over all corpus chunks per request. Acceptable at 30 documents; a larger corpus should use the existing vector index rather than a linear scan.
- **It predicts corpus relevance, not answerability.** A question whose topic the corpus covers but whose specific answer it lacks will still route to RAG. That is the correct trade-off here (RAG adequacy classification downstream is what catches insufficient evidence), but it is not the same guarantee.
