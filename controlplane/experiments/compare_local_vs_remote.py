"""Local (embedding k-NN) vs Remote (Groq-prompted) query classification
comparison -- bootstrap Milestone 2 SS25.

Fixed test set: the first 10 validation-split queries (deterministic,
not cherry-picked). Compares the existing HybridQueryProfiler (local,
free, ~30ms warm per docs/EVALUATION/MODEL_BENCHMARKS.md) against asking
Groq to produce the same classification via a JSON-constrained prompt.

Requires GROQ_API_KEY. If unset, this records the comparison as
NOT_MEASURED on the remote side rather than fabricating numbers -- see
docs/EVALUATION/MODEL_BENCHMARKS.md for the actual run status.

Run:
    GROQ_API_KEY=... GROQ_MODEL=... .venv/Scripts/python -m controlplane.experiments.compare_local_vs_remote
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.config import get_settings
from controlplane.experiments.metrics import accuracy
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.query_intelligence.knn_profiler import HybridQueryProfiler

_VALIDATION_PATH = Path("data/evaluation/validation/query_profiles_validation.json")
_FIELDS = ["complexity", "sensitivity", "ambiguity", "actionability"]
_TEST_SET_SIZE = 10

_PROMPT_TEMPLATE = """Classify this query. Respond with ONLY a JSON object, no other text:
{{"complexity": "low|medium|high", "sensitivity": "NONE|POTENTIAL_PII|PII_EXPOSURE|SENSITIVE_DATA_EXPOSURE", "ambiguity": "low|medium|high", "actionability": "informational|analytical|procedural|generative|decisional|agentic|pending_clarification"}}

Query: {query}"""


def _load_test_set() -> list[dict]:
    with open(_VALIDATION_PATH, encoding="utf-8-sig") as f:
        return json.load(f)[:_TEST_SET_SIZE]


def _run_local(records: list[dict]) -> dict:
    profiler = HybridQueryProfiler()
    predictions = {f: [] for f in _FIELDS}
    latencies = []
    for record in records:
        start = time.monotonic()
        fp = profiler.profile(record["query"])
        latencies.append((time.monotonic() - start) * 1000)
        predictions["complexity"].append(fp.complexity.value)
        predictions["sensitivity"].append(fp.sensitivity.value)
        predictions["ambiguity"].append(fp.ambiguity.value)
        predictions["actionability"].append(fp.actionability.value)
    accuracies = {f: accuracy([r[f] for r in records], predictions[f]) for f in _FIELDS}
    return {
        "method": "local_embedding_knn",
        "cost": "free",
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else "NOT_MEASURED",
        "accuracy_by_field": accuracies,
    }


def _run_groq(records: list[dict]) -> dict:
    settings = get_settings()
    if not settings.groq_api_key or not settings.groq_model:
        return {
            "method": "groq_prompted_classification",
            "status": "NOT_MEASURED",
            "reason": "GROQ_API_KEY/GROQ_MODEL not set in this environment run -- see docs/EVALUATION/MODEL_BENCHMARKS.md",
        }

    from controlplane.models.groq_provider import GroqProvider

    provider = GroqProvider(api_key=settings.groq_api_key, model=settings.groq_model)
    predictions = {f: [] for f in _FIELDS}
    latencies = []
    parse_failures = 0
    for record in records:
        start = time.monotonic()
        result = provider.generate(prompt=_PROMPT_TEMPLATE.format(query=record["query"]))
        latencies.append(result.latency_ms)
        try:
            parsed = json.loads(result.content.strip().strip("`"))
        except json.JSONDecodeError:
            parse_failures += 1
            parsed = {}
        for f in _FIELDS:
            predictions[f].append(parsed.get(f, "PARSE_FAILURE"))

    accuracies = {f: accuracy([r[f] for r in records], predictions[f]) for f in _FIELDS}
    return {
        "method": "groq_prompted_classification",
        "model": settings.groq_model,
        "cost": "metered (per-token)",
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else "NOT_MEASURED",
        "parse_failures": parse_failures,
        "accuracy_by_field": accuracies,
    }


def main() -> None:
    records = _load_test_set()
    local_result = _run_local(records)
    remote_result = _run_groq(records)

    print("LOCAL:", json.dumps(local_result, indent=2))
    print("REMOTE:", json.dumps(remote_result, indent=2))

    experiment_id = record_experiment(
        experiment_name="local_vs_remote_query_classification",
        component="query_profiler",
        algorithm="embedding_knn_vs_groq_prompt",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id="query_profiles_validation_first10",
        dataset_version="v0.1",
        configuration={"test_set_size": _TEST_SET_SIZE},
        status="SUCCESS" if remote_result.get("status") != "NOT_MEASURED" else "PARTIAL",
        notes="remote side NOT_MEASURED if GROQ_API_KEY unavailable this run" if remote_result.get("status") == "NOT_MEASURED" else None,
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics={"local": local_result, "remote": remote_result})

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"local_vs_remote_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "run_id": run_id, "local": local_result, "remote": remote_result}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
