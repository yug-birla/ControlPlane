# controlplane/judge/

**Purpose:** LLM-as-a-Judge  -  Local (offline) and Remote (Gemini) implementations of a shared structured-output contract. See `docs/ALGORITHMS/LLM_JUDGE.md`.

## Interface

- `schema.py`: `JudgeResult` (`judge`, `task`, `status`, `label`, `score`, `issues`, `rationale`, `latency_ms`, `model`, `raw_output`), `JudgeStatus` (`IMPLEMENTED`/`PARSE_FAILED`/`ERROR`).
- `prompts.py`: `build_judge_prompt(task, *, query, answer, evidence) -> (system, user)`  -  one shared template per task (`grounding`/`quality`/`reasoning`/`safety`), used identically by both judges.
- `parsing.py`: `extract_json_object(text) -> dict | None`, `safe_float(value) -> float | None`  -  recovers from markdown fences/stray prose without ever fabricating a field.
- `local_judge.py`: `LocalJudge` (Qwen2.5-1.5B-Instruct, CPU-only, offline-first)  -  `.evaluate(...)` and `.generate_answer(...)` (plain generation, used by the Bias evaluator).
- `remote_judge.py`: `RemoteJudge` (Gemini via `controlplane.models.registry.get_gemini_provider`).

## Dependencies

`torch`, `transformers` (lazy-imported, only needed for `LocalJudge`), `controlplane.models.registry` (for `RemoteJudge`).

## Limitations

Local Judge measured latency is 30-90s/call on CPU  -  not suitable for a live per-request path. Remote Judge not live-validated this session (no API key present).

## Extension points

New judge tasks: add one entry to `prompts._TASK_INSTRUCTIONS`. New judge backends: implement `.evaluate(task, *, query, answer, evidence) -> JudgeResult` and it's usable anywhere `JudgeBackedEvaluator` (`controlplane/evaluation/judge_evaluators.py`) is.
