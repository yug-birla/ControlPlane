"""Before/after and counterfactual measurement of the control loop
(Decision -> Intervention -> Replan -> Verification) -- bootstrap
SS43/44: "one of the most important final competition metrics."

Uses SCRIPTED model responses (same technique as
tests/test_control_loop_scenarios.py), not live Groq/Gemini calls at
scale: this measures whether the control-loop MECHANISM changes
outcomes on deliberately-constructed inputs, not live-model quality
statistics across many real prompts (which would need a much larger
model-comparison budget -- NOT_MEASURED here, see
docs/EVALUATION/CONTROL_LOOP_RESULTS.md for why).

For each scenario: "BASELINE" = the first model response, returned
unconditionally with no evaluation/intervention (what a system without
ControlPlane would do). "CONTROLPLANE" = the actual final answer this
milestone's Runtime produces after the full control loop. Both are
scored with the identical Grounding/Confidence evaluators for a fair,
apples-to-apples comparison -- the scoring mechanism never differs
between the two conditions, only what each condition allows through.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_control_loop_before_after
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from controlplane.context import RequestContext
from controlplane.evaluation.evaluators import EvaluationContext, GroundingEvaluator, ResponseConfidenceEvaluator
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run
from controlplane.models.provider import ModelProvider, ModelResult
from controlplane.rag.retrieval import retrieve
from controlplane.runtime import build_default_runtime
from controlplane.state import ExecutionState

_QUALITY_RANK = {"UNSUPPORTED": 0, "LOW": 0, "PARTIALLY_SUPPORTED": 1, "MEDIUM": 1, "SUPPORTED": 2, "HIGH": 2, "NOT_APPLICABLE": 1}


class _ScriptedProvider(ModelProvider):
    name = "scripted"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    def generate(self, *, prompt: str) -> ModelResult:
        content = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return ModelResult(provider=self.name, model="fake-scripted", content=content, latency_ms=250, finish_reason="stop")


@dataclass
class Scenario:
    scenario_id: str
    query: str
    responses: list[str]
    rag_relevant: bool  # whether to fetch real RAG evidence for scoring the baseline answer


_SCENARIOS = [
    Scenario(
        "rag_recovery", "What is the meal reimbursement limit according to the travel policy?",
        ["The weather forecast predicts rain tomorrow across the region.",
         "Meal reimbursement is up to $75/day domestic, $100/day international, per the travel policy."],
        rag_relevant=True,
    ),
    Scenario(
        "rag_exhausted", "What is the meal reimbursement limit according to the travel policy?",
        ["The weather forecast predicts rain tomorrow across the region.",
         "Our quarterly sports league standings were updated yesterday."],
        rag_relevant=True,
    ),
    Scenario(
        "model_escalation", "What is the capital of France?",
        ["I'm not sure, it's unclear to me.", "The capital of France is Paris, a well-established fact."],
        rag_relevant=False,
    ),
    Scenario(
        "clean_no_intervention_needed", "What is the capital of Japan?",
        ["The capital of Japan is Tokyo, a well-established fact."],
        rag_relevant=False,
    ),
    Scenario(
        "clean_rag_already_grounded", "What is our refund policy for cancelled subscriptions?",
        ["Digital subscription plans cancelled within 30 days are eligible for a pro-rated refund."],
        rag_relevant=True,
    ),
]


def _score(query: str, answer: str, evidence_texts: list[str]) -> dict:
    grounding = GroundingEvaluator().evaluate(EvaluationContext(query=query, answer=answer, evidence_texts=evidence_texts))
    confidence = ResponseConfidenceEvaluator().evaluate(EvaluationContext(query=query, answer=answer))
    return {"grounding": grounding.label, "confidence": confidence.label}


def run_scenario(scenario: Scenario) -> dict:
    evidence_texts = [r.chunk.text for r in retrieve(scenario.query, k=5)] if scenario.rag_relevant else []

    provider = _ScriptedProvider(scenario.responses)
    rt = build_default_runtime(provider_factory=lambda settings, role="STRONG": provider)
    ctx = RequestContext.new()
    with ctx.bind():
        state = ExecutionState.initial(ctx=ctx, query=scenario.query)
        state = rt.handle(ctx, state)

    baseline_answer = scenario.responses[0]
    controlplane_answer = state.metadata["answer"]

    baseline_score = _score(scenario.query, baseline_answer, evidence_texts)
    controlplane_score = _score(scenario.query, controlplane_answer, evidence_texts) if controlplane_answer else {"grounding": "NONE (abstained/clarification)", "confidence": "NONE"}

    def rank(label: str) -> int:
        return _QUALITY_RANK.get(label, 1)

    # Bug found while first inspecting these results (real, not
    # hypothetical): comparing grounding rank alone silently ignored a
    # genuine confidence improvement (the model-escalation scenario) and
    # had no way to credit a correct, safe abstention as anything but
    # "not improved" (the rag-exhausted scenario). Fixed to check both
    # axes, and to separately track safety-motivated abstention, which
    # is a different kind of win than "a better answer was returned."
    grounding_improved = controlplane_answer and rank(controlplane_score["grounding"]) > rank(baseline_score["grounding"])
    confidence_improved = controlplane_answer and rank(controlplane_score["confidence"]) > rank(baseline_score["confidence"])
    improved = bool(grounding_improved or confidence_improved)
    safety_correct_abstention = (not controlplane_answer) and (
        rank(baseline_score["grounding"]) == 0 or rank(baseline_score["confidence"]) == 0
    )

    return {
        "scenario_id": scenario.scenario_id,
        "query": scenario.query,
        "model_calls": provider.calls,
        "extra_model_calls_vs_baseline": provider.calls - 1,
        "extra_latency_ms_estimate": (provider.calls - 1) * 250,  # scripted provider's fixed 250ms per call
        "baseline_answer": baseline_answer,
        "baseline_score": baseline_score,
        "controlplane_answer": controlplane_answer,
        "controlplane_score": controlplane_score,
        "decision_action": state.metadata["decision"]["action"],
        "verification_status": state.metadata["verification"]["status"],
        "improved_over_baseline": improved,
        "safety_correct_abstention": safety_correct_abstention,
        "unnecessary_intervention": provider.calls > 1 and not improved and not safety_correct_abstention,
    }


def main() -> None:
    results = [run_scenario(s) for s in _SCENARIOS]

    n = len(results)
    improved_count = sum(1 for r in results if r["improved_over_baseline"])
    abstention_count = sum(1 for r in results if r["safety_correct_abstention"])
    unnecessary_count = sum(1 for r in results if r["unnecessary_intervention"])
    intervened_count = sum(1 for r in results if r["model_calls"] > 1)
    avg_extra_latency = sum(r["extra_latency_ms_estimate"] for r in results) / n

    metrics = {
        "sample_count": n,
        "scenarios_where_controlplane_intervened": f"{intervened_count}/{n}",
        "scenarios_improved_over_baseline": f"{improved_count}/{n}",
        "scenarios_with_safety_correct_abstention": f"{abstention_count}/{n}",
        "unnecessary_intervention_rate": f"{unnecessary_count}/{n}",
        "avg_extra_latency_ms_per_request": avg_extra_latency,
        "results": results,
        "note": (
            "Scripted model responses, not live-model statistics at scale (see module docstring). "
            "Measures whether the control-loop mechanism changes outcomes on constructed inputs, "
            "not aggregate live-model quality improvement -- that would need a real, larger "
            "model-comparison budget (NOT_MEASURED)."
        ),
    }

    print(f"intervened={metrics['scenarios_where_controlplane_intervened']} "
          f"improved={metrics['scenarios_improved_over_baseline']} "
          f"safety_correct_abstention={metrics['scenarios_with_safety_correct_abstention']} "
          f"unnecessary_intervention={metrics['unnecessary_intervention_rate']} "
          f"avg_extra_latency_ms={avg_extra_latency:.0f}")

    experiment_id = record_experiment(
        experiment_name="control_loop_before_after_counterfactual",
        component="decision_intervention_replan_verification",
        algorithm="scripted_scenario_comparison",
        algorithm_version="v1",
    )
    run_id = record_run(
        experiment_id=experiment_id,
        dataset_id="control_loop_scenarios",
        dataset_version="v1",
        configuration={"scenario_count": n},
        notes="Scripted-provider controlled comparison, not live-model statistics -- see module docstring.",
    )
    record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"control_loop_before_after_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "metrics": metrics}, f, indent=2, default=str)
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
