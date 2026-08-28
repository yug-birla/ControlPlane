"""LLM Judge subsystem tests -- no real model load/generation (LocalJudge's
``__init__`` model-loading calls are mocked, and ``_run_generate`` is
stubbed with canned output) and no live Gemini calls. See
tests/manual_local_judge_live_check.py for the one real local-model
integration path (deliberately not run by the default suite: a single
call measured 50-90s on this CPU-only machine)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from controlplane.evaluation.evaluators import EvaluationContext
from controlplane.evaluation.judge_evaluators import JudgeBackedEvaluator
from controlplane.judge.local_judge import LocalJudge
from controlplane.judge.parsing import extract_json_object, safe_float
from controlplane.judge.prompts import build_judge_prompt
from controlplane.judge.remote_judge import RemoteJudge
from controlplane.judge.schema import JudgeStatus
from controlplane.models.provider import ModelProviderError


def test_extract_json_object_parses_plain_json():
    assert extract_json_object('{"label": "SUPPORTED", "score": 0.9}') == {"label": "SUPPORTED", "score": 0.9}


def test_extract_json_object_strips_markdown_fences():
    text = '```json\n{"label": "SUPPORTED", "score": 0.9}\n```'
    assert extract_json_object(text) == {"label": "SUPPORTED", "score": 0.9}


def test_extract_json_object_finds_object_amid_prose():
    text = 'Sure, here is my answer: {"label": "SUPPORTED", "score": 0.9} -- hope that helps!'
    assert extract_json_object(text) == {"label": "SUPPORTED", "score": 0.9}


def test_extract_json_object_returns_none_for_unparseable_text():
    assert extract_json_object("this is not json at all") is None


def test_extract_json_object_returns_none_for_doubled_braces():
    """Regression: a real LocalJudge smoke-test once returned raw output
    containing doubled braces (`{{"label": ...}}`) because the prompt
    template itself had a formatting bug (see git history of
    controlplane/judge/prompts.py) -- verifies the parser correctly
    rejects malformed JSON rather than guessing."""
    assert extract_json_object('{{"label": "SUPPORTED"}}') is None


def test_safe_float_handles_non_numeric_gracefully():
    assert safe_float("not a number") is None
    assert safe_float(None) is None
    assert safe_float("0.75") == 0.75


def test_build_judge_prompt_rejects_unknown_task():
    with pytest.raises(ValueError):
        build_judge_prompt("not_a_real_task", query="q", answer="a")


def test_build_judge_prompt_grounding_includes_few_shot_examples_with_no_doubled_braces():
    """Milestone 8: added after the HARD judge benchmark found the Local
    Judge never once predicted PARTIALLY_SUPPORTED across 24 cases. Also
    guards against a repeat of the doubled-brace prompt bug (found
    earlier this project) in these new literal JSON examples."""
    system, user = build_judge_prompt("grounding", query="q", answer="a", evidence=["e"])
    assert "PARTIALLY_SUPPORTED" in user
    assert "EXAMPLES" in user
    assert "{{" not in user


def test_build_judge_prompt_embeds_query_answer_and_evidence():
    system, user = build_judge_prompt("grounding", query="What is X?", answer="X is Y.", evidence=["X is Y per doc."])
    assert "What is X?" in user
    assert "X is Y." in user
    assert "X is Y per doc." in user
    assert "JSON" in system


def _make_local_judge(monkeypatch) -> LocalJudge:
    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *a, **k: object())
    monkeypatch.setattr("transformers.AutoModelForCausalLM.from_pretrained", lambda *a, **k: object())
    return LocalJudge()


def test_local_judge_parses_a_well_formed_response(monkeypatch):
    judge = _make_local_judge(monkeypatch)
    judge._run_generate = lambda messages, max_new_tokens: (
        '{"label": "SUPPORTED", "score": 0.9, "issues": [], "rationale": "matches evidence"}', 1234,
    )
    result = judge.evaluate("grounding", query="q", answer="a", evidence=["e"])
    assert result.status == JudgeStatus.IMPLEMENTED
    assert result.label == "SUPPORTED"
    assert result.score == 0.9
    assert result.latency_ms == 1234


def test_local_judge_reports_parse_failed_without_fabricating(monkeypatch):
    judge = _make_local_judge(monkeypatch)
    judge._run_generate = lambda messages, max_new_tokens: ("not valid json output", 500)
    result = judge.evaluate("grounding", query="q", answer="a", evidence=["e"])
    assert result.status == JudgeStatus.PARSE_FAILED
    assert result.label is None
    assert result.score is None


def test_local_judge_generate_answer_bypasses_json_contract(monkeypatch):
    judge = _make_local_judge(monkeypatch)
    judge._run_generate = lambda messages, max_new_tokens: ("plain free-text answer", 999)
    text, latency_ms = judge.generate_answer("some open question")
    assert text == "plain free-text answer"
    assert latency_ms == 999


class _FakeGeminiResult:
    def __init__(self, content, model="fake-gemini-model"):
        self.content = content
        self.model = model


def test_remote_judge_parses_a_well_formed_response(monkeypatch):
    from controlplane.config import Settings

    monkeypatch.setattr(
        "controlplane.judge.remote_judge.get_gemini_provider",
        lambda settings: SimpleNamespace(generate=lambda prompt: _FakeGeminiResult('{"label": "GOOD", "score": 0.8, "rationale": "clear"}')),
    )
    judge = RemoteJudge(Settings())
    result = judge.evaluate("quality", query="q", answer="a")
    assert result.status == JudgeStatus.IMPLEMENTED
    assert result.label == "GOOD"
    assert result.model == "fake-gemini-model"


def test_remote_judge_reports_error_status_on_provider_failure(monkeypatch):
    from controlplane.config import Settings

    def _raise(settings):
        raise ModelProviderError("quota exceeded")

    monkeypatch.setattr("controlplane.judge.remote_judge.get_gemini_provider", _raise)
    judge = RemoteJudge(Settings())
    result = judge.evaluate("quality", query="q", answer="a")
    assert result.status == JudgeStatus.ERROR


def test_judge_backed_evaluator_maps_negative_label_to_flag_for_review():
    from controlplane.judge.schema import JudgeResult

    class _FakeJudge:
        name = "fake"

        def evaluate(self, task, *, query, answer, evidence=None):
            return JudgeResult(judge="fake", task=task, status=JudgeStatus.IMPLEMENTED, label="UNSUPPORTED", score=0.1, rationale="no support found", latency_ms=1, model="fake-model")

    evaluator = JudgeBackedEvaluator(_FakeJudge(), "grounding")
    result = evaluator.evaluate(EvaluationContext(query="q", answer="a", evidence_texts=["e"]))
    assert result.status.value == "IMPLEMENTED"
    assert result.recommended_signal == "FLAG_FOR_REVIEW"


def test_judge_backed_evaluator_returns_not_implemented_when_no_answer():
    class _FakeJudge:
        name = "fake"

        def evaluate(self, task, *, query, answer, evidence=None):
            raise AssertionError("should not be called when there is no answer")

    evaluator = JudgeBackedEvaluator(_FakeJudge(), "grounding")
    result = evaluator.evaluate(EvaluationContext(query="q", answer=None))
    assert result.status.value == "NOT_IMPLEMENTED"
