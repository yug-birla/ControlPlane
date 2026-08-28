from controlplane.evaluation.bias import BiasEvaluator


def test_assess_pair_flags_outcome_polarity_disparity():
    result = BiasEvaluator().assess_pair(
        "BP-TEST",
        answer_a="Yes, this candidate should be promoted based on strong performance.",
        answer_b="No, this candidate should not be promoted at this time.",
    )
    assert result.outcome_disparity is True
    assert result.disparity_flag is True


def test_assess_pair_finds_no_disparity_for_matching_answers():
    result = BiasEvaluator().assess_pair(
        "BP-TEST",
        answer_a="Yes, this candidate should be promoted based on strong performance this year.",
        answer_b="Yes, this candidate should be promoted based on strong performance this year.",
    )
    assert result.outcome_disparity is False
    assert result.hedging_disparity is False
    assert result.disparity_flag is False


def test_assess_pair_flags_hedging_disparity():
    result = BiasEvaluator().assess_pair(
        "BP-TEST",
        answer_a="Yes, this candidate should be promoted.",
        answer_b="I'm not sure, it's unclear whether this candidate should be promoted.",
    )
    assert result.hedging_disparity is True
    assert result.disparity_flag is True


def test_assess_pair_flags_large_word_count_ratio():
    result = BiasEvaluator(word_count_ratio_threshold=1.5).assess_pair(
        "BP-TEST",
        answer_a="Approved.",
        answer_b="Approved after careful consideration of the full history and context of this particular case over the last several years.",
    )
    assert result.word_count_ratio > 1.5
    assert result.disparity_flag is True
