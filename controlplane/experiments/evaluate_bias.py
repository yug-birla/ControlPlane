"""Bias evaluation -- generates a real paired answer for each of the 8
hand-authored cases in ``data/raw/generated/bias_paired_cases.json`` and
runs ``controlplane.evaluation.bias.BiasEvaluator`` on each pair.

Answer generation uses ``LocalJudge.generate_answer`` (the same
Qwen2.5-1.5B-Instruct model as the judge, used here for plain
generation, not judging) because no live Groq/Gemini key is available
this session -- documented plainly, not silently substituted. If a
GROQ_API_KEY is available in a future session, swap in
``controlplane.models.registry.get_configured_provider`` instead for a
generation path closer to the live system's actual answer model.

SMOKE_TEST scale (bootstrap SS40): 8 pairs, one axis of variation
(name), one task family (professional recommendation queries). Not a
general fairness audit -- see docs/EVALUATION/EVALUATOR_RESULTS.md.

Run (takes ~15-20 minutes: 16 local generations at ~60-90s each):
    .venv/Scripts/python -m controlplane.experiments.evaluate_bias
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.evaluation.bias import BiasEvaluator
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.judge.local_judge import LocalJudge

_DATASET_PATH = Path("data/raw/generated/bias_paired_cases.json")
DATASET_ID = "bias_paired_cases"
DATASET_VERSION = "v0.1"


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def main() -> None:
    cases = _load()
    generator = LocalJudge(max_new_tokens=60)
    evaluator = BiasEvaluator()

    experiment_id = record_experiment(
        experiment_name="bias_paired_comparison",
        component="evaluation_bias",
        algorithm="paired_counterfactual_v0",
        algorithm_version="v1",
    )

    assessments = []
    for case in cases:
        print(f"Generating pair for {case['case_id']} ({case['topic']})...")
        answer_a, latency_a = generator.generate_answer(case["query_a"])
        answer_b, latency_b = generator.generate_answer(case["query_b"])
        result = evaluator.assess_pair(case["case_id"], answer_a, answer_b)
        assessments.append({
            "case_id": case["case_id"], "topic": case["topic"], "variant_dimension": case["variant_dimension"],
            "answer_a": answer_a, "answer_b": answer_b,
            "latency_ms_a": latency_a, "latency_ms_b": latency_b,
            "disparity_flag": result.disparity_flag, "rationale": result.rationale,
            "outcome_polarity_a": result.outcome_polarity_a, "outcome_polarity_b": result.outcome_polarity_b,
            "word_count_ratio": result.word_count_ratio,
        })
        print(f"  disparity_flag={result.disparity_flag} ({result.rationale})")

    flagged = [a for a in assessments if a["disparity_flag"]]
    metrics = {
        "sample_count": len(assessments),
        "disparity_rate": len(flagged) / len(assessments) if assessments else 0.0,
        "flagged_case_ids": [a["case_id"] for a in flagged],
        "mean_word_count_ratio": sum(a["word_count_ratio"] for a in assessments) / len(assessments) if assessments else None,
        "generator_model": LocalJudge.name,
        "generator_note": "no live Groq/Gemini key available this session -- used the Local Judge model for plain generation instead, documented explicitly",
    }

    run_id = record_run(
        experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
        model=LocalJudge.name, configuration={"max_new_tokens": 60},
        notes="SMOKE_TEST scale (8 pairs, one variation axis); CPU-only local generation",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    print(f"disparity_rate={metrics['disparity_rate']:.2f} flagged={metrics['flagged_case_ids']}")

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"bias_paired_comparison_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION,
                    "metrics": metrics, "assessments": assessments}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
