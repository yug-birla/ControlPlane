from controlplane.rag.adequacy import AdequacyLabel, RAGAdequacyEvaluator


def test_no_evidence_is_insufficient():
    result = RAGAdequacyEvaluator().assess("What is the refund policy?", [])
    assert result.label == AdequacyLabel.INSUFFICIENT
    assert result.coverage == 0.0


def test_high_overlap_evidence_is_sufficient():
    result = RAGAdequacyEvaluator().assess(
        "What is the refund policy for cancelled subscriptions?",
        ["Digital subscription plans cancelled within 30 days are eligible for pro-rated refund."],
    )
    assert result.label == AdequacyLabel.SUFFICIENT


def test_unrelated_evidence_is_insufficient():
    result = RAGAdequacyEvaluator().assess(
        "What is the refund policy for cancelled subscriptions?",
        ["Recovery Point Objective for core database is 1 hour."],
    )
    assert result.label == AdequacyLabel.INSUFFICIENT


def test_conflicting_polarity_evidence_is_flagged():
    result = RAGAdequacyEvaluator().assess(
        "Is two-factor authentication required for all employees?",
        ["Two-factor authentication is mandatory for all employees.", "Two-factor authentication is optional for contractors."],
    )
    assert result.label == AdequacyLabel.CONFLICTING


def test_query_with_no_scorable_terms_is_insufficient():
    result = RAGAdequacyEvaluator().assess("the of to", ["some evidence text"])
    assert result.label == AdequacyLabel.INSUFFICIENT


def test_polarity_word_inside_an_unrelated_word_is_not_flagged_as_conflicting_regression():
    """Regression: found via a real end-to-end trace of the RAG
    self-healing scenario at a widened retry k -- a naive substring check
    matched "not" inside "notice" (HR Policy's "Resignation notice is 30
    days"), flagging it as conflicting with an unrelated document
    containing "must", even though neither document is about the query
    or about each other. Fixed with word-boundary matching."""
    result = RAGAdequacyEvaluator().assess(
        "What is the meal reimbursement limit?",
        [
            "Resignation notice is 30 days for individual contributors.",
            "Vendors processing customer PII must hold a valid certification.",
        ],
    )
    assert result.label != AdequacyLabel.CONFLICTING


# ---------------------------------------------------------------------------
# SEMANTIC ABSENCE. Evidence about Tier 1 is not evidence about Tier 3.
#
# The old default tokenizer discarded every token of two characters or
# fewer, which deleted the only part of the query that names the entity:
# "Tier 3" became {tier}, "Q4 revenue" became {revenue}. The evaluator was
# not weighing a weak signal -- the discriminating token was gone before
# any threshold was consulted, so a Tier 1 chunk covered a Tier 3 question
# completely and returned SUFFICIENT.
#
# Measured on held-out data, the old default called 13 of 14 semantic
# absence cases SUFFICIENT (false-confidence rate 0.929).
# ---------------------------------------------------------------------------

_TIER_EVIDENCE = (
    "Travel Policy 4.2: Hotel accommodation is reimbursed up to $250 per night "
    "in Tier 1 cities and up to $180 per night elsewhere."
)


def test_evidence_about_tier_one_is_insufficient_for_a_tier_three_question():
    from controlplane.rag.adequacy import AdequacyLabel, RAGAdequacyEvaluator

    result = RAGAdequacyEvaluator().assess(
        "What is the hotel allowance for Tier 3 cities?", [_TIER_EVIDENCE]
    )
    assert result.label is AdequacyLabel.INSUFFICIENT, result.reason


def test_the_one_digit_control_still_answers():
    """The guard against fixing absence by rejecting everything: this
    query differs from the one above by a single character and the
    evidence genuinely answers it."""
    from controlplane.rag.adequacy import AdequacyLabel, RAGAdequacyEvaluator

    result = RAGAdequacyEvaluator().assess(
        "What is the hotel allowance for Tier 1 cities?", [_TIER_EVIDENCE]
    )
    assert result.label is AdequacyLabel.SUFFICIENT, result.reason


def test_the_tokenizer_no_longer_deletes_the_entity_name():
    """The root cause, pinned directly. If these identifiers stop
    surviving tokenization, the evaluator goes blind again regardless of
    what its thresholds say."""
    from controlplane.rag.adequacy import _numeric_aware_tokenize

    assert "3" in _numeric_aware_tokenize("What is the hotel allowance for Tier 3 cities?")
    assert "q4" in _numeric_aware_tokenize("What was Q4 revenue for the Americas region?")
    assert "v3" in _numeric_aware_tokenize("What is the payload limit in API v3?")


def test_a_quarter_absent_from_the_evidence_is_insufficient():
    from controlplane.rag.adequacy import AdequacyLabel, RAGAdequacyEvaluator

    evidence = ["Regional Results: Americas Q3 revenue was $410,000, up from $380,000 in Q2."]
    evaluator = RAGAdequacyEvaluator()
    assert evaluator.assess("What was Q4 revenue for the Americas region?", evidence).label \
        is AdequacyLabel.INSUFFICIENT
    assert evaluator.assess("What was Q3 revenue for the Americas region?", evidence).label \
        is AdequacyLabel.SUFFICIENT


def test_more_evidence_does_not_manufacture_sufficiency():
    """Three chunks all about tiers, none defining Tier 2. Retrieval depth
    raises lexical coverage while the answer stays absent, so a
    coverage-only rule gets MORE confident the more it retrieves."""
    from controlplane.rag.adequacy import AdequacyLabel, RAGAdequacyEvaluator

    result = RAGAdequacyEvaluator().assess(
        "What is the hotel allowance for Tier 2 cities?",
        [
            _TIER_EVIDENCE,
            "Travel Policy 4.3: Cities are classified into tiers annually by the Finance team.",
            "Travel Policy 4.4: Employees travelling to Tier 1 cities may book via the portal.",
        ],
    )
    assert result.label is AdequacyLabel.INSUFFICIENT, result.reason
