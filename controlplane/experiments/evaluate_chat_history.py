"""Evaluate the chat-history capability against labelled sessions.

Milestone 11 (§27/§28/§48). Answers two questions:

1. Does it correctly decide **whether** history is relevant at all?
   (The costly errors are asymmetric: injecting stale/sensitive/injected
   history is worse than omitting useful history, so false positives are
   reported separately from false negatives.)
2. When history IS relevant, does it pick the **right turns**?

BASELINES it is measured against, because "better than nothing" is not a
claim worth making without something to compare to:

  ALWAYS_ALL      inject every prior turn (the naive default)
  LAST_2          inject the two most recent turns (the common heuristic)
  SEMANTIC        this capability

DATA: ``data/raw/generated/chat_history_sessions.json`` -- 18 sessions,
content ``SYNTHETIC``, labels ``LLM_JUDGE``. **The labels are model-authored,
not human ground truth**, which the project's data-quality policy requires
be stated rather than assumed away. They encode defensible judgements
(a pronoun needs its antecedent; a superseded policy value must not be
reused), but they have not been human-reviewed, and the honest scale
label is ``DEVELOPMENT_TEST``.

Run:
    .venv/Scripts/python -m controlplane.experiments.evaluate_chat_history
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from controlplane.capabilities.chat_history_capability import ChatHistoryCapability
from controlplane.experiments.tracking import record_evaluation, record_experiment, record_run

_DATASET_PATH = Path("data/raw/generated/chat_history_sessions.json")
DATASET_ID = "chat_history_sessions"
DATASET_VERSION = "v0.1"

# Hazard flags: history that must NOT be carried forward whatever its
# topical relevance.
_HAZARD_KEYS = (
    "history_contains_injection",
    "history_contains_standing_action_instruction",
    "history_contains_sensitive_data",
    "history_is_stale",
)


def _load() -> list[dict]:
    with open(_DATASET_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _predict_always_all(session: dict) -> tuple[bool, list[int]]:
    prior = [t for t in session["turns"] if t["text"] != session["current_query"]]
    return (bool(prior), [t["turn_id"] for t in prior])


def _predict_last_2(session: dict) -> tuple[bool, list[int]]:
    prior = [t for t in session["turns"] if t["text"] != session["current_query"]]
    picked = prior[-2:]
    return (bool(picked), [t["turn_id"] for t in picked])


def _predict_semantic(session: dict, capability: ChatHistoryCapability) -> tuple[bool, list[int]]:
    result = capability.select(session["current_query"], session["turns"])
    return result.history_is_relevant, result.relevant_turn_ids


def _score(sessions: list[dict], predictions: list[tuple[bool, list[int]]]) -> dict:
    tp = fp = fn = tn = 0
    turn_f1s: list[float] = []
    hazard_total = hazard_leaked = 0

    for session, (used, turn_ids) in zip(sessions, predictions):
        expected_used = session["history_is_relevant"]
        expected_ids = set(session["relevant_turn_ids"])

        if used and expected_used:
            tp += 1
        elif used and not expected_used:
            fp += 1
        elif not used and expected_used:
            fn += 1
        else:
            tn += 1

        # Turn selection quality, only where history genuinely is relevant.
        if expected_used:
            predicted = set(turn_ids)
            if predicted or expected_ids:
                overlap = len(predicted & expected_ids)
                precision = overlap / len(predicted) if predicted else 0.0
                recall = overlap / len(expected_ids) if expected_ids else 0.0
                turn_f1s.append(
                    (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
                )

        # Hazard leakage: did it carry forward history it should not have?
        if any(session.get(k) for k in _HAZARD_KEYS):
            hazard_total += 1
            if used:
                hazard_leaked += 1

    total = len(sessions)
    return {
        "sample_count": total,
        "decision_accuracy": (tp + tn) / total if total else 0.0,
        "false_inject_rate": fp / total if total else 0.0,
        "false_omit_rate": fn / total if total else 0.0,
        "turn_selection_f1": sum(turn_f1s) / len(turn_f1s) if turn_f1s else None,
        "hazardous_sessions": hazard_total,
        "hazard_leak_count": hazard_leaked,
        "hazard_leak_rate": hazard_leaked / hazard_total if hazard_total else None,
    }


def main() -> None:
    sessions = _load()
    print(f"Loaded {len(sessions)} labelled sessions "
          f"(content SYNTHETIC, labels LLM_JUDGE -- not human ground truth)\n")

    capability = ChatHistoryCapability()
    strategies = {
        "ALWAYS_ALL": [_predict_always_all(s) for s in sessions],
        "LAST_2": [_predict_last_2(s) for s in sessions],
        "SEMANTIC": [_predict_semantic(s, capability) for s in sessions],
    }

    experiment_id = record_experiment(
        experiment_name="chat_history_relevance",
        component="chat_history_capability",
        algorithm="always_all_vs_last2_vs_semantic",
        algorithm_version="v1",
    )

    results = {}
    for name, predictions in strategies.items():
        metrics = _score(sessions, predictions)
        results[name] = metrics
        run_id = record_run(
            experiment_id=experiment_id, dataset_id=DATASET_ID, dataset_version=DATASET_VERSION,
            model=name, configuration={"strategy": name},
            notes="18 labelled sessions; labels are LLM_JUDGE provenance, not human ground "
                  "truth; DEVELOPMENT_TEST scale",
        )
        record_evaluation(experiment_run_id=run_id, split=None, metrics=metrics)

    keys = ["decision_accuracy", "false_inject_rate", "false_omit_rate",
            "turn_selection_f1", "hazard_leak_rate"]
    print("=" * 74)
    print(f"{'METRIC':<28}" + "".join(f"{n:>15}" for n in strategies))
    print("=" * 74)
    for key in keys:
        row = f"{key:<28}"
        for name in strategies:
            v = results[name].get(key)
            row += f"{v:>15.3f}" if isinstance(v, float) else f"{str(v):>15}"
        print(row)

    out_dir = Path("docs/EVALUATION/RESULTS")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"chat_history_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"experiment_id": experiment_id, "dataset_id": DATASET_ID,
                   "dataset_version": DATASET_VERSION, "results": results}, f, indent=2, default=str)
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
