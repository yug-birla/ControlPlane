# Chat-History Capability Results

**Run:** `controlplane/experiments/evaluate_chat_history.py`, 2026-08-29.
**Data:** `data/raw/generated/chat_history_sessions.json` — 18 sessions.
**Provenance:** content `SYNTHETIC`, labels `LLM_JUDGE`. **The labels are model-authored, not human ground truth.** They encode defensible judgements (a pronoun needs its antecedent; a superseded policy value must not be reused) but have not been human-reviewed.
**Scale:** `DEVELOPMENT_TEST`.

## Result

| Metric | ALWAYS_ALL | LAST_2 | **SEMANTIC** |
|---|---|---|---|
| Decision accuracy | 0.444 | 0.444 | **0.944** |
| False-inject rate | 0.556 | 0.556 | **0.056** |
| False-omit rate | 0.000 | 0.000 | **0.000** |
| Turn-selection F1 | 0.796 | 0.662 | **0.808** |
| Hazard leak rate | 1.000 | 1.000 | **0.143** |

The two naive strategies **leak 100% of hazardous history** — every session containing an injection, a standing action instruction, PII, or a superseded policy value gets carried forward into the prompt.

## The design error that the measurement exposed

The first version used a single relevance threshold (0.45) for everything, and scored:

| | decision acc | turn F1 | hazard leak |
|---|---|---|---|
| threshold 0.45 | 0.667 | 0.271 | 0.143 |
| threshold 0.25 | 0.833 | 0.808 | 0.429 |

That looked like an unavoidable safety-vs-utility trade-off. It wasn't — it was **the wrong instrument**. Staleness and PII are not "less relevant" content; they are *hazards that happen to be highly relevant*. `CH-018` is the clearest case: *"Which projects were active last quarter?"* is nearly identical in meaning to *"Which projects are active right now?"*, so raising a **semantic** threshold to suppress it also suppresses every legitimate follow-up.

Making staleness, PII, injection and standing-instructions **hard exclusions**, then setting the threshold purely for relevance, improved both halves at once: decision accuracy 0.667 → 0.944, turn F1 0.271 → 0.808, with hazard leak unchanged at 0.143. Using a relevance knob as a safety control had been costing both.

## Two findings reported rather than smoothed over

**1. The remaining leak is commercial confidentiality, not personal PII.** `CH-017` carries "Client Meridian Health's account number is 8842-1190 and their contract value is $2.4M" into a request to draft a *public* case study. The PII check reuses the existing `RuleBasedQueryProfiler` sensitivity signal, which covers personal identifiers (SSN, employee ID) but not commercial confidentiality. Deliberately **not** patched with another keyword list — the principled fix is classification against the corpus's own `DATA_CLASSIFICATION_MATRIX`, which is future work.

**2. One "correct" exclusion was correct for the wrong reason.** `CH-005` (a staleness case) was excluded because the **injection detector false-positived** on the benign turn *"Under the 2023 policy, what was the hotel allowance?"* — flagged `INJECTION_PATTERN_DETECTED` by the embedding k-NN layer. The outcome was right; the reason was not, so the 0.143 hazard-leak figure is partly luck.

This is the domain-shift risk flagged in Milestone 8 when the k-NN threshold was set to 0.30 rather than the calibration-optimal 0.20 — the reference data is casual-assistant phrasing, and enterprise policy questions sit outside it. **Scope checked immediately:** the same evaluator produces **0 false positives on the 19 benign enterprise queries** used for the baseline-vs-ControlPlane claim, so that headline result is unaffected. The failing construction is specifically past-tense policy-version phrasing.

## Limitations

- **18 sessions, model-authored labels.** Enough to expose a design error (which it did) and to separate three strategies; not enough to state a rate with confidence. Human review of the labels is the obvious next step.
- **The capability is not yet runtime-wired.** `CHAT_HISTORY` remains registered `MOCKED` in the Capability Registry because no real conversation store exists — the capability is implemented and measured, but the runtime has no multi-turn session to feed it.
- **Relevance is per-turn cosine similarity**, so a turn that matters only in combination with another can be missed.
