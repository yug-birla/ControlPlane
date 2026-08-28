"""Groq vs. Gemini comparison -- a small, deliberately bounded sample
(bootstrap instruction: "Do NOT use Gemini for every request... Use it
selectively for: model comparison... high-value benchmark samples").
Gemini quota is limited/non-free in this deployment; this script is not
meant to be run routinely.

Requires GEMINI_API_KEY_1 (and/or _2) and, for the Groq side, GROQ_API_KEY
+ GROQ_MODEL in the environment. Either side missing -> that side is
recorded as NOT_MEASURED, never fabricated.

Run:
    GEMINI_API_KEY_1=... [GROQ_API_KEY=... GROQ_MODEL=...] \
        .venv/Scripts/python -m controlplane.experiments.compare_groq_vs_gemini
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from controlplane.config import get_settings
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.models.provider import ModelProvider, ModelProviderError
from controlplane.models.registry import get_configured_provider, get_gemini_provider

_SAMPLE_QUERIES = [
    ("simple_factual", "What is the capital of France?"),
    ("reasoning", "If a train leaves at 3pm travelling 60mph and another leaves at 4pm travelling 90mph on the same route, when does the second train catch up? Explain your reasoning."),
    ("enterprise_style", "Summarize, in one sentence, the key considerations for a company deciding whether to migrate its core database to the cloud."),
]


def _call(provider: ModelProvider, prompt: str) -> dict:
    start = time.monotonic()
    try:
        result = provider.generate(prompt=prompt)
    except ModelProviderError as exc:
        return {"status": "ERROR", "error": str(exc)}
    return {
        "status": "EXECUTED",
        "model": result.model,
        "content": result.content,
        "latency_ms": result.latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "wall_clock_ms": (time.monotonic() - start) * 1000,
    }


def main() -> None:
    settings = get_settings()

    groq_provider = None
    try:
        groq_provider = get_configured_provider(settings, role="STRONG")
    except Exception:
        pass

    gemini_provider = None
    try:
        gemini_provider = get_gemini_provider(settings)
    except Exception:
        pass

    rows = []
    for category, query in _SAMPLE_QUERIES:
        row = {"category": category, "query": query}
        row["groq"] = _call(groq_provider, query) if groq_provider else {"status": "NOT_MEASURED", "reason": "GROQ_API_KEY/GROQ_MODEL not set"}
        row["gemini"] = _call(gemini_provider, query) if gemini_provider else {"status": "NOT_MEASURED", "reason": "GEMINI_API_KEY_1/2 or GEMINI_MODEL not set"}
        rows.append(row)
        print(f"[{category}] groq={row['groq']['status']} gemini={row['gemini']['status']}")

    metrics = {
        "sample_count": len(rows),
        "groq_configured": groq_provider is not None,
        "gemini_configured": gemini_provider is not None,
        "rows": rows,
        "note": "Deliberately small sample per bootstrap instruction to use Gemini conservatively (limited/non-free quota).",
    }

    experiment_id = record_experiment(
        experiment_name="groq_vs_gemini_comparison",
        component="model_provider",
        algorithm="direct_generation_comparison",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id="fixed_sample_queries",
        dataset_version="v1",
        configuration={"sample_count": len(rows)},
        notes="Small, deliberate sample -- Gemini quota is conservatively used, not benchmarked exhaustively.",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"groq_vs_gemini_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
