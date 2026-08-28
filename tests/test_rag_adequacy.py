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
