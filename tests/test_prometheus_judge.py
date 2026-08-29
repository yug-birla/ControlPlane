"""Prometheus 2 judge: prompt construction, parsing, and label mapping.

No real model load here -- the model is ~14.5GB. The one real load
attempt is the experiment script, which reports the outcome honestly
including failure.
"""

from __future__ import annotations

from controlplane.judge.prometheus_judge import (
    _SCORE_TO_GROUNDING_LABEL,
    build_prometheus_prompt,
    parse_prometheus_output,
)


def test_prompt_uses_prometheus_own_template_not_this_repos_json_contract():
    """Prometheus 2 was trained on a specific absolute-grading template.
    Feeding it this repo's generic JSON judge prompt would measure a
    prompt mismatch rather than the model."""
    prompt = build_prometheus_prompt(
        query="What is the meal limit?", answer="It is $75/day.",
        evidence=["Meal reimbursement is up to $75/day domestic."],
    )
    assert "###Task Description:" in prompt
    assert "###The instruction to evaluate:" in prompt
    assert "###Response to evaluate:" in prompt
    assert "###Score Rubrics:" in prompt
    assert "[RESULT]" in prompt  # the required output contract is stated
    assert "It is $75/day." in prompt
    assert "up to $75/day domestic" in prompt


def test_prompt_is_explicit_when_no_evidence_is_available():
    """An empty evidence block must be stated, not silently omitted --
    otherwise the judge cannot distinguish 'no evidence' from
    'evidence that happens to be empty'."""
    prompt = build_prometheus_prompt(query="q", answer="a", evidence=[])
    assert "(no evidence provided)" in prompt


def test_parses_the_result_score_and_feedback():
    raw = "Feedback: The response restates the evidence accurately. [RESULT] 5"
    score, feedback = parse_prometheus_output(raw)
    assert score == 5
    assert "restates the evidence accurately" in feedback
    assert "[RESULT]" not in feedback


def test_missing_result_marker_is_a_parse_failure_not_a_guess():
    """Never fabricate a score. The Qwen judge has the same contract."""
    score, _feedback = parse_prometheus_output("The answer looks broadly fine to me.")
    assert score is None


def test_out_of_range_scores_are_not_accepted():
    score, _ = parse_prometheus_output("Feedback: bad. [RESULT] 9")
    assert score is None


def test_score_scale_maps_onto_the_existing_grounding_vocabulary():
    """The mapping must not invent a parallel label set, and the middle
    of the scale must reach PARTIALLY_SUPPORTED -- that is precisely the
    class the Qwen judge could never predict (0/24), which is why this
    model is being tried."""
    assert set(_SCORE_TO_GROUNDING_LABEL.values()) == {
        "UNSUPPORTED", "PARTIALLY_SUPPORTED", "SUPPORTED"
    }
    assert _SCORE_TO_GROUNDING_LABEL[3] == "PARTIALLY_SUPPORTED"
    assert _SCORE_TO_GROUNDING_LABEL[1] == "UNSUPPORTED"
    assert _SCORE_TO_GROUNDING_LABEL[5] == "SUPPORTED"
    assert sorted(_SCORE_TO_GROUNDING_LABEL) == [1, 2, 3, 4, 5]
