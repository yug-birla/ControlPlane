from controlplane.governance.behavioral_drift import BehavioralDriftDetector, DriftLevel


def _history(n_sql=8, n_report=2):
    return [("sql_read_query", "ALLOW")] * n_sql + [("write_report", "ALLOW")] * n_report


def test_no_history_is_no_drift():
    result = BehavioralDriftDetector().assess([], "sql_read_query", "ALLOW")
    assert result.level == DriftLevel.NONE
    assert result.baseline_sample_count == 0


def test_consistent_tool_and_governance_is_no_drift():
    result = BehavioralDriftDetector().assess(_history(), "sql_read_query", "ALLOW")
    assert result.level == DriftLevel.NONE


def test_rare_tool_is_flagged_as_low_drift():
    result = BehavioralDriftDetector().assess(_history(n_sql=9, n_report=1), "send_notification", "ALLOW")
    assert result.level == DriftLevel.LOW
    assert "send_notification" in result.reason


def test_more_severe_governance_than_history_is_flagged():
    result = BehavioralDriftDetector().assess(_history(), "sql_read_query", "BLOCK")
    assert result.level in (DriftLevel.LOW, DriftLevel.MEDIUM)
    assert "more severe" in result.reason


def test_rare_and_more_severe_together_is_medium_drift():
    result = BehavioralDriftDetector().assess(_history(n_sql=9, n_report=1), "send_notification", "BLOCK")
    assert result.level == DriftLevel.MEDIUM
    assert len(result.signals) == 2
