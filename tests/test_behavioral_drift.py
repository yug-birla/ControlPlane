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


def test_rare_and_more_severe_together_is_high_drift():
    """EXPECTATION RAISED 2026-08-30, deliberately.

    This asserted MEDIUM, which encoded the v1 detector's CAP rather
    than the desired behaviour: the level was derived from how many of
    two signals fired, so it saturated at MEDIUM and DriftLevel.HIGH
    could never be emitted at all. A BLOCKED action on a tool this
    trajectory has never used is the strongest drift signal available,
    and it is exactly the shape this test drives.

    Measured across 22 longitudinal cases: HIGH class f1 0.000 -> 0.909,
    held-out exact accuracy 0.500 -> 0.800, with zero new false alarms.
    Both remaining signals are still required, so the original property
    is preserved below."""
    result = BehavioralDriftDetector().assess(_history(n_sql=9, n_report=1), "send_notification", "BLOCK")
    assert result.level == DriftLevel.HIGH
    assert len(result.signals) == 2


def test_a_familiar_tool_with_a_severe_outcome_stays_below_high():
    """Guard on the same change: severity alone must not reach HIGH.
    Without this, every restricted action on a routine tool would
    escalate and HIGH would stop meaning anything."""
    result = BehavioralDriftDetector().assess(_history(n_sql=9, n_report=1), "sql_read_query", "HUMAN_REVIEW")
    assert result.level == DriftLevel.MEDIUM


# --- Milestone 16: HIGH was declared and unreachable --------------


def test_high_is_actually_reachable_regression():
    """DriftLevel.HIGH existed in the enum and the detector could never
    emit it: the level came from how many of two signals fired, so it
    saturated at MEDIUM. Measured across 22 longitudinal cases as
    precision 0.000 / recall 0.000 for that class, with all six HIGH
    cases downgraded. Any consumer branching on HIGH was dead code."""
    from controlplane.governance.behavioral_drift import BehavioralDriftDetector, DriftLevel

    history = [("sql_read_query", "ALLOW")] * 12
    assessment = BehavioralDriftDetector().assess(history, "wire_transfer", "HUMAN_REVIEW")
    assert assessment.level is DriftLevel.HIGH


def test_consequence_outweighs_signal_count():
    """A BLOCKED action on an unprecedented tool must outrank two
    frequency signals on a benign one. Counting signals treated those as
    interchangeable evidence."""
    from controlplane.governance.behavioral_drift import BehavioralDriftDetector, DriftLevel

    history = [("sql_read_query", "ALLOW")] * 12
    detector = BehavioralDriftDetector()
    assert detector.assess(history, "delete_record", "BLOCK").level is DriftLevel.HIGH
    assert detector.assess(history, "send_notification", "ALLOW").level is DriftLevel.LOW


def test_severity_awareness_adds_no_false_alarms():
    """The adoption was justified partly by costing nothing: routine
    behaviour must still report NONE."""
    from controlplane.governance.behavioral_drift import BehavioralDriftDetector, DriftLevel

    history = [("sql_read_query", "ALLOW"), ("read_documents", "ALLOW"), ("write_report", "ALLOW")] * 6
    for tool in ("sql_read_query", "read_documents", "write_report"):
        assert BehavioralDriftDetector().assess(history, tool, "ALLOW").level is DriftLevel.NONE


def test_an_empty_baseline_still_reports_no_drift():
    """Reporting drift from no history would be a fabricated signal."""
    from controlplane.governance.behavioral_drift import BehavioralDriftDetector, DriftLevel

    assert BehavioralDriftDetector().assess([], "wire_transfer", "BLOCK").level is DriftLevel.NONE
