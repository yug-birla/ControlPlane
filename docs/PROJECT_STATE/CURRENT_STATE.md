# ControlPlane.ai — Current State

**Last updated:** 2026-08-28 (Milestone 8)
**Context:** Accenture Innovation Challenge 2026, Round 2 — Prototype Development (Problem Track 1, "ControlPlane.ai"). See `Problem_Statement/` for the original brief (partially captured as screenshots; not yet transcribed to text — see `BLOCKERS.md`).

## What Exists

**Documentation:**
- `docs/ALGORITHMS/` — 16 prior files plus 1 new: `PROMPT_INJECTION_DETECTION.md`. `RAG_PIPELINE.md`/retrieval module docstring updated for the RRF fusion-method default.
- `docs/EVALUATION/` — `EVALUATOR_RESULTS.md` (Judge few-shot attempt, real 662-example prompt-injection benchmark + embedding k-NN upgrade), `RAG_RESULTS.md` (RRF vs. min-max fusion comparison) updated.
- `docs/DATA/` — 1 new: `EXTERNAL_DATASETS.md` (the `deepset/prompt-injections` dataset, provenance, license, normalization pipeline).
- `docs/PROJECT_STATE/` — this folder, updated; `BLOCKERS.md` B10 marked **FIXED** (E: drive migration — see below).

**Application code (Milestone 8 — E: Drive Migration, Judge Few-Shot, Real Public Injection Dataset + Embedding k-NN Detector, RRF Architecture Compliance — complete 2026-08-28):**

- **`BLOCKERS.md` B10 actually fixed, not just documented:** the entire ~8.6GB Hugging Face cache moved from `C:\Users\Lenovo\.cache\huggingface` to `E:\ControlPlane\.cache\huggingface`; `HF_HOME`/`HF_HUB_CACHE`/`TRANSFORMERS_CACHE` set persistently via `setx`. Reclaimed ~9GB on C: (11GB→20GB free). Verified all 3 local models still load offline afterward. Full test suite now runs in ~52-55s, matching the pre-B10 healthy baseline (down from the 76-minute anomaly).
- **Judge few-shot prompting attempted and honestly reported as insufficient:** 3 few-shot examples added to `controlplane/judge/prompts.py`'s grounding prompt (unrelated office-policy domain to avoid test leakage). Real result: accuracy 0.375→0.417, macro-F1 0.300→0.320, but Milestone 7's `PARTIALLY_SUPPORTED` class-collapse (0/24 predictions) was **not** fixed — few-shot only shifted overall bias toward `UNSUPPORTED`. Per the bootstrap's own improvement ladder, model comparison (not fine-tuning) is the next justified step, not attempted this milestone.
- **Real public dataset integrated for prompt-injection detection:** `deepset/prompt-injections` (HuggingFace, Apache-2.0, pinned revision, 662 examples: 546 train + 116 test) normalized into `data/external/deepset_prompt_injections/` with new provenance value `"EXTERNAL"`. Measured against Milestone 7's keyword-only `PromptInjectionEvaluator`: accuracy 0.609, macro-F1 0.392, **false-negative rate 98.5%** (259/263 real injections missed) — the earlier 12-case "1.0 accuracy" benchmark was confirmation bias from fixed phrases, not evidence of generalization.
- **`controlplane/evaluation/injection_knn.py` (NEW):** `EmbeddingKNNInjectionDetector` — reuses the existing local `all-MiniLM-L6-v2` embedding model, k=5 majority vote over TRAIN-split reference embeddings (disk-cached via the B9 pattern), with a `similarity_threshold` reject-option. Real measured improvement on held-out TEST split (no leakage): macro-F1 0.326→0.796. Threshold shipped at a deliberate, documented `0.30` rather than the raw grid-search-optimal `0.20`, trading measured in-domain performance for real-world generalization safety (the raw optimum would still have misclassified a real benign-SQL false positive found during testing).
- **`controlplane/evaluation/evaluators.py`'s `PromptInjectionEvaluator` upgraded to two layers:** keyword-first (free, short-circuits), embedding k-NN fallback only if the keyword layer finds nothing; degrades gracefully if the dataset is missing.
- **RRF (Reciprocal Rank Fusion) adopted as the retrieval fusion default**, replacing min-max weighted-sum fusion — `docs/specs/CONTROLPLANE_RAG_RETRIEVAL_HALLUCINATION_AGENT_GUIDE.md` explicitly mandates "Dense + BM25 + RRF + Cross-Encoder" as the source-of-truth pipeline; Milestones 4-7 were an undocumented deviation, found during this milestone's architecture audit. Measured comparison showed **identical** results (recall@1/recall@3/MRR) between RRF and min-max on the 26-case benchmark — a real null finding that removes any measured reason to keep deviating, so the spec's own default is now adopted (`min_max` kept available, not deleted).
- **A real false-positive bug found via end-to-end testing, not a targeted unit test:** the threshold-less k-NN detector flagged a benign SQL query as an injection because majority vote always returns a label regardless of similarity magnitude (all 5 neighbors were near-orthogonal, similarity ~0.2). Fixed with the reject-option threshold above.
- `tests/` — 259 automated tests (up from 253 measured at the start of this milestone), all passing, ~52s wall-clock.
- **`walledai/BBQ` bias dataset investigated but not integrated:** confirmed to exist (CC-BY-4.0) but its multiple-choice QA format doesn't map to the existing pairwise `BiasEvaluator` without substantial adapter work — documented as a deferred candidate.
- **Explicitly not implemented / deferred (unchanged from Milestone 7):** Shadow Mode (Layer 20); Behavioral Drift live-wiring (no real historical volume yet); multi-agent composition tracking; Bias dataset expansion beyond 8 pairs; fine-tuning of anything.

**What does NOT exist:**
- No root-level `AGENTS.md` (`BLOCKERS.md` B1) — unchanged.
- No single `docs/ARCHITECTURE.md` file (`BLOCKERS.md` B2) — unchanged.
- Redis and Qdrant remain unused placeholders.
- No Shadow Mode (Layer 20).
- No live Groq-vs-Gemini benchmark at scale, and no live Gemini/Groq validation at all this session (no API keys present).
- No multi-step agent tool-calling loop (one `AGENT` node per graph) — Behavioral Drift and Permission Lineage are correspondingly single-hop.
- No BBQ (or other public) bias dataset integration yet — investigated, not adapted.
- No local-generative-model comparison for the Judge's `PARTIALLY_SUPPORTED` collapse (the bootstrap's next-justified-step after few-shot).

## Phase

**Milestone 8 (E: Drive Migration + Judge Few-Shot Attempt + Real Public Prompt-Injection Dataset + Embedding k-NN Detector + RRF Architecture Compliance) complete.** Sequence: documentation audit (`4ae6a76`) → Layer 0 (`ac2f243`) → Layer 1 (`008231e`) → Milestone 1 (`463979e`) → Milestone 2 (`d396acb`) → Milestone 3 (`ba4896e`) → Milestones 4+5 (`7dc76a9`) → Milestone 6 (`a543f8c`) → Milestone 7 (`e385ad9`) → Milestone 8 (pending commit). Awaiting explicit instruction before continuing — see `FUTURE_WORK.md`.
