"""Evidence about Tier 1 is not evidence about Tier 3.

THE FAILURE. `RAGAdequacyEvaluator` reports SUFFICIENT with coverage 1.00
when asked for the Tier 3 hotel allowance against a chunk that defines
only Tier 1. Retrieval then hands "sufficient" evidence to generation,
generation answers confidently, and ControlPlane has done the opposite of
its job. It is the mechanism behind the 64% confabulation rate measured on
adjacent-evidence unanswerable cases.

THE ROOT CAUSE IS NOT A WEAK SIGNAL. `_tokenize` discards every token of
two characters or fewer, which deletes the only part of the query that
names the entity:

    "hotel allowance for Tier 3 cities" -> {allowance, cities, hotel, tier}
    "Q4 revenue for the Americas"       -> {americas, region, revenue}
    "maximum payload size in API v3"    -> {api, maximum, payload, size}

The tier, the quarter and the version are gone before any threshold is
consulted. No amount of tuning recovers information that was thrown away.

THE CONDITIONS.

  A_current       shipped: unigram coverage, tokens of 3+ characters
  B_numeric       A, plus tokens containing a digit (3, q4, v3, 2024)
  C_identifier    B, plus: an identifier named in the query and absent
                  from ALL evidence forces INSUFFICIENT
  D_semantic      embedding cosine between query and best chunk,
                  thresholded -- no lexical rule at all
  E_hybrid        C's identifier rule as an override, D's similarity
                  where no identifier is in play

C encodes one narrow claim: evidence that never mentions the entity the
question names is evidence about a different entity. It names no
particular tier, quarter or version, so it generalises to Band C, fiscal
2022 and API v4 without being told about them.

WHY BOTH DIRECTIONS ARE SCORED. Rejecting everything eliminates false
confidence and destroys the system. Half of `rag_adequacy_semantic_cases`
are true matches -- paraphrases ("if someone quits, how much warning must
they give"), synonyms (passphrase/password), the same entity under another
name ("customer-facing web tier" / "public web front end"), and one-digit
controls for every absence case. A condition that wins by over-rejecting
loses here, visibly.

  semantic_false_confidence_rate   gold INSUFFICIENT, called SUFFICIENT
  semantic_abstention_recall       gold INSUFFICIENT, correctly caught
  false_rejection_rate             gold SUFFICIENT, called INSUFFICIENT

Tuned on dev (32 cases), reported once on test (32). `rag_cases.json`
(150 cases, the set the shipped thresholds were calibrated on) is carried
as a regression guard so a gain here that wrecks the original
distribution is visible rather than silent.

Deterministic plus one small embedding model. No generation, no judge.

    .venv/Scripts/python -m controlplane.experiments.evaluate_rag_semantic_adequacy
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.rag.adequacy import (
    AdequacyLabel,
    RAGAdequacyEvaluator,
    _identifier_keys,
)

DATASET_ID = "rag_adequacy_semantic_cases"
DATASET_VERSION = "v1"
_DATASET = Path("data/raw/generated/rag_adequacy_semantic_cases.json")
_REGRESSION = Path("data/raw/generated/rag_cases.json")

# PARTIALLY_SUFFICIENT and CONFLICTING both mean "do not answer this
# confidently", which is what the gold INSUFFICIENT label encodes here.
_POSITIVE = {AdequacyLabel.SUFFICIENT}


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _embedder():
    from controlplane.models.local_hf_provider import LocalHFEmbeddingProvider

    return LocalHFEmbeddingProvider()


class _SemanticAdequacy:
    """Cosine between the query and its best-matching chunk.

    Deliberately experiment-local: it earns a place in the runtime by
    winning here, not by existing.
    """

    def __init__(self, threshold: float, provider) -> None:
        self._threshold = threshold
        self._provider = provider
        self._cache: dict[str, list[float]] = {}

    def _embed(self, text: str) -> list[float]:
        if text not in self._cache:
            self._cache[text] = self._provider.embed(text=text).embedding
        return self._cache[text]

    def _cosine(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def best_similarity(self, query: str, evidence: list[str]) -> float:
        q = self._embed(query)
        return max((self._cosine(q, self._embed(t)) for t in evidence), default=0.0)

    def predict_sufficient(self, query: str, evidence: list[str]) -> bool:
        return self.best_similarity(query, evidence) >= self._threshold


class _HybridAdequacy:
    """C's identifier override, D's similarity everywhere else."""

    def __init__(self, semantic: _SemanticAdequacy) -> None:
        self._semantic = semantic

    def predict_sufficient(self, query: str, evidence: list[str]) -> bool:
        evidence_ids: set[str] = set()
        for text in evidence:
            evidence_ids |= _identifier_keys(text)
        if _identifier_keys(query) - evidence_ids:
            return False
        return self._semantic.predict_sufficient(query, evidence)


def _predict(condition, query: str, evidence: list[str]) -> bool:
    if isinstance(condition, RAGAdequacyEvaluator):
        return condition.assess(query, evidence).label in _POSITIVE
    return condition.predict_sufficient(query, evidence)


def _score(condition, cases: list[dict], gold_key: str, evidence_key: str) -> dict:
    tp = fp = tn = fn = 0
    misses: list[str] = []
    for case in cases:
        gold_sufficient = case[gold_key] == "SUFFICIENT"
        evidence = case[evidence_key]
        if isinstance(evidence, str):
            evidence = [evidence]
        predicted = _predict(condition, case["query"], evidence)
        if gold_sufficient and predicted:
            tp += 1
        elif gold_sufficient and not predicted:
            fn += 1
            misses.append(f"FALSE_REJECT {case.get('case_id', '?')}")
        elif not gold_sufficient and predicted:
            fp += 1
            misses.append(f"FALSE_CONFIDENCE {case.get('case_id', '?')}")
        else:
            tn += 1

    n = tp + fp + tn + fn or 1
    prec_s = tp / (tp + fp) if tp + fp else 0.0
    rec_s = tp / (tp + fn) if tp + fn else 0.0
    f1_s = 2 * prec_s * rec_s / (prec_s + rec_s) if prec_s + rec_s else 0.0
    prec_i = tn / (tn + fn) if tn + fn else 0.0
    rec_i = tn / (tn + fp) if tn + fp else 0.0
    f1_i = 2 * prec_i * rec_i / (prec_i + rec_i) if prec_i + rec_i else 0.0
    return {
        "sample_count": n,
        "accuracy": (tp + tn) / n,
        "macro_f1": (f1_s + f1_i) / 2,
        "sufficient_precision": prec_s,
        "sufficient_recall": rec_s,
        "insufficient_precision": prec_i,
        "insufficient_recall": rec_i,
        "semantic_abstention_recall": rec_i,
        "semantic_false_confidence_rate": fp / (fp + tn) if fp + tn else 0.0,
        "false_rejection_rate": fn / (fn + tp) if fn + tp else 0.0,
        "false_positive_count": fp,
        "false_negative_count": fn,
        "misses": misses,
    }


def _tune_semantic_threshold(dev: list[dict], provider) -> tuple[float, list[dict]]:
    trace = []
    for threshold in [round(0.20 + 0.05 * i, 2) for i in range(11)]:
        metrics = _score(_SemanticAdequacy(threshold, provider), dev, "gold_adequacy", "evidence")
        trace.append({"threshold": threshold, "accuracy": metrics["accuracy"],
                      "macro_f1": metrics["macro_f1"],
                      "false_confidence": metrics["semantic_false_confidence_rate"],
                      "false_rejection": metrics["false_rejection_rate"]})
    best = max(trace, key=lambda r: r["macro_f1"])
    return best["threshold"], trace


def main() -> None:
    cases = _load(_DATASET)
    dev = [c for c in cases if c["split"] == "dev"]
    test = [c for c in cases if c["split"] == "test"]
    print(f"{len(dev)} dev / {len(test)} test cases\n")

    provider = _embedder()
    threshold, trace = _tune_semantic_threshold(dev, provider)
    print("semantic threshold tuning (DEV only):")
    print(f"{'thr':>6}{'accuracy':>11}{'macro_f1':>11}{'false_conf':>13}{'false_rej':>12}")
    for row in trace:
        print(f"{row['threshold']:>6.2f}{row['accuracy']:>11.3f}{row['macro_f1']:>11.3f}"
              f"{row['false_confidence']:>13.3f}{row['false_rejection']:>12.3f}")
    print(f"\nchosen threshold = {threshold}\n")

    semantic = _SemanticAdequacy(threshold, provider)
    # EVERY CONDITION PINS ITS OWN FLAGS EXPLICITLY.
    #
    # A_current was written as a bare ``RAGAdequacyEvaluator()``. When C
    # was adopted and the class defaults changed, the baseline silently
    # became the treatment and A, B and C reported identical numbers --
    # a comparison of one configuration against itself, in a harness whose
    # entire purpose is to compare configurations. A baseline that tracks
    # the shipped default is not a baseline.
    conditions = {
        "A_original_default": RAGAdequacyEvaluator(numeric_aware_tokens=False,
                                                   require_identifier_match=False),
        "B_numeric": RAGAdequacyEvaluator(numeric_aware_tokens=True,
                                          require_identifier_match=False),
        "C_identifier": RAGAdequacyEvaluator(numeric_aware_tokens=True,
                                             require_identifier_match=True),
        "D_semantic": semantic,
        "E_hybrid": _HybridAdequacy(semantic),
    }

    experiment_id = record_experiment(
        experiment_name="rag_semantic_adequacy",
        component="rag_adequacy",
        algorithm="identifier_binding_vs_semantic",
        algorithm_version="v1",
    )

    regression_cases = _load(_REGRESSION)
    # rag_cases.json names these fields differently; PARTIALLY_SUFFICIENT
    # maps to "not sufficient", the same collapse used for predictions.
    regression_key = "evidence_sufficiency"

    results: dict = {}
    for name, condition in conditions.items():
        results[name] = {
            "dev": _score(condition, dev, "gold_adequacy", "evidence"),
            "test": _score(condition, test, "gold_adequacy", "evidence"),
        }
        if regression_key:
            try:
                results[name]["regression_rag_cases"] = _score(
                    condition, regression_cases, regression_key, "documents")
            except Exception as exc:  # never let the guard mask the headline
                results[name]["regression_rag_cases"] = {"error": f"{type(exc).__name__}: {exc}"}

        run_id = record_run(
            experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
            model="all-MiniLM-L6-v2", configuration={"condition": name, "threshold": threshold},
            notes="semantic absence vs true match; dev tuned, test reported once",
        )
        for split in ("dev", "test"):
            record_evaluation(experiment_run_id=run_id, split=split,
                              metrics={k: v for k, v in results[name][split].items()
                                       if k != "misses"})

    for split in ("dev", "test"):
        print("=" * 104)
        print(f"{split.upper()}  ({'tuning split' if split == 'dev' else 'HELD OUT -- reported once'})")
        print("=" * 104)
        print(f"{'CONDITION':<16}{'accuracy':>10}{'macro_f1':>10}{'abstention_recall':>19}"
              f"{'false_confidence':>18}{'false_rejection':>17}")
        for name in conditions:
            m = results[name][split]
            print(f"{name:<16}{m['accuracy']:>10.3f}{m['macro_f1']:>10.3f}"
                  f"{m['semantic_abstention_recall']:>19.3f}"
                  f"{m['semantic_false_confidence_rate']:>18.3f}"
                  f"{m['false_rejection_rate']:>17.3f}")
        print()

    if regression_key:
        print("=" * 104)
        print("REGRESSION GUARD -- rag_cases.json, the distribution the shipped thresholds were tuned on")
        print("=" * 104)
        print(f"{'CONDITION':<16}{'accuracy':>10}{'macro_f1':>10}")
        for name in conditions:
            m = results[name].get("regression_rag_cases", {})
            if "error" in m:
                print(f"{name:<16}{m['error']}")
            else:
                print(f"{name:<16}{m['accuracy']:>10.3f}{m['macro_f1']:>10.3f}")
        print()

    print("test-split misses for the leading lexical condition (C_identifier):")
    for miss in results["C_identifier"]["test"]["misses"]:
        print(f"  {miss}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"rag_semantic_adequacy_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID,
                   "dataset_version": DATASET_VERSION, "semantic_threshold": threshold,
                   "threshold_trace": trace, "results": results}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
