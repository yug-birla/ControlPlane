# LLM-as-a-Judge: Local + Remote

**Status:** IMPLEMENTED — V0 (Milestone 6, 2026-08-28)

## Problem

The Evaluation layer's deterministic evaluators (Milestone 4/5) are cheap and fast but structurally limited: lexical grounding can't tell a paraphrase from an unsupported claim, and there was no mechanism at all for a general "is this response good" judgment. Bootstrap SS13/14: build a real LLM-as-a-Judge subsystem, with both a local (offline) and remote path, used selectively rather than on every request.

## Architecture Location

`controlplane/judge/{schema,prompts,parsing,local_judge,remote_judge}.py`. `controlplane/evaluation/judge_evaluators.py::JudgeBackedEvaluator` adapts either judge to the standard `Evaluator` interface (proving it is a genuinely swappable strategy), but is **not** included in `EvaluationSuite()`'s default list used by the live runtime — see Compute/Latency below for why.

## Method

Both judges are asked the identical templated question (`controlplane.judge.prompts`, one template per task: `grounding`/`quality`/`reasoning`/`safety`) and must return one JSON object: `{"label", "score", "issues", "rationale"}` — no chain-of-thought is requested or stored (bootstrap SS13: "do NOT expose hidden chain-of-thought; only store structured reasoning summaries"). A response that isn't valid JSON is reported as `PARSE_FAILED`, never coerced into a fabricated label (`controlplane/judge/parsing.py::extract_json_object`).

**Local Judge:** `Qwen/Qwen2.5-1.5B-Instruct`, revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` (Apache-2.0, ~1.5B params, ~3GB in bf16). Selected because its tokenizer was already partially staged in this environment before this milestone (a strong signal it was the intended choice for this exact repo), it's instruction-tuned (needed for reliable JSON output), and it's small enough for bounded (if slow) CPU-only inference.

**Remote Judge:** Gemini, via the existing `get_gemini_provider` accessor — same "never the default, used conservatively" rule as everywhere else Gemini appears in this codebase.

## Real Bugs Found and Fixed

1. **Doubled-brace prompt bug:** the JSON-example text in `prompts.py` was originally written with `{{"label": ...}}` (escaped for an f-string that was never actually applied to that substring) — the model faithfully echoed invalid doubled-brace JSON back, which then correctly failed to parse. Found via a real LocalJudge smoke-test, not assumed. Fixed to single braces; regression test: `test_extract_json_object_returns_none_for_doubled_braces`.
2. **Windows paging-file error on model load:** `AutoModelForCausalLM.from_pretrained(...)` with default settings raised `OSError: The paging file is too small` while memory-mapping the 3GB safetensors file (an implicit float32 upcast doubles the resident footprint during load). Fixed with explicit `dtype=torch.bfloat16, low_cpu_mem_usage=True` — loads successfully, uses less memory.

## Candidate Alternatives

- **A larger judge model** (e.g. 7B-class) — rejected without evidence the 1.5B model is actually inadequate; would roughly proportionally worsen the already-significant CPU latency.
- **Quantized (int8/int4) local judge** — considered for latency; not attempted this milestone (would need `bitsandbytes` or a GGUF runtime, an added dependency not yet justified by a measured need beyond "it would be faster").

## Inputs / Outputs

`judge.evaluate(task, *, query, answer, evidence) -> JudgeResult` (`judge`, `task`, `status`, `label`, `score`, `issues`, `rationale`, `latency_ms`, `model`, `raw_output`).

## Dataset

Judge calibration: a DERIVED 20-case grounding benchmark built from `rag_cases.json`'s SUFFICIENT records (see `docs/EVALUATION/EVALUATOR_RESULTS.md` for construction and results — no organic grounding-labeled dataset exists for this system).

## Compute / Latency (measured, this CPU-only machine — NO-GPU DEMONSTRATION ENVIRONMENT)

| Judge | Cold load | Per-call (short structured output) |
|---|---|---|
| Local (Qwen2.5-1.5B-Instruct) | ~3s | **30-90s** (measured 56.7s for one 80-token grounding judgment after setting `torch.set_num_threads()` to all 16 cores, down from 88.4s at torch's default 10-thread setting) |
| Remote (Gemini) | n/a | ~1-2s (not live-measured this session — no API key present, see Model Results) |

This is exactly why `JudgeBackedEvaluator` is **not** wired into the live per-request `EvaluationSuite()` default: the rest of that suite runs in under ~100ms total. A single Local Judge call would make every request 300-900x slower. This is a stated architecture decision (bootstrap SS15/43: "use judges selectively, not blindly"), not an oversight.

## Metrics

See `docs/EVALUATION/EVALUATOR_RESULTS.md` for the deterministic-vs-Local-Judge-vs-Remote-Judge calibration comparison.

## Failure Modes

`PARSE_FAILED` is reported (not fabricated) when a model's output isn't valid JSON even after fence-stripping and brace-matching recovery. `ERROR` is reported when the underlying model call itself fails (e.g. Remote Judge with no API key/quota exhausted).

## Known Limitations

- Local Judge latency makes it usable only for offline calibration/comparison, not live per-request evaluation, on this hardware.
- Remote Judge not live-validated this session (no `GEMINI_API_KEY_1`/`GEMINI_API_KEY_2` present) — reported `NOT_MEASURED`, not assumed working from a prior session.
- No judge fine-tuning or few-shot calibration attempted — zero-shot instructions only.

## Result

A real, working, tested LLM-as-a-Judge subsystem (both local and remote paths implemented, structured-output contract enforced, no hidden chain-of-thought) exists and is measured — but is deliberately not the default per-request evaluator due to measured CPU latency.

## Final Decision

Adopted for offline calibration/comparison use; live per-request wiring deferred pending either a much smaller/faster local model, GPU access, or a demonstrated need that the deterministic evaluators can't meet.

## Version

v1 — 2026-08-28.
