from controlplane.governance.agent_gate import AgentGate, GovernanceAction


def test_destructive_keyword_is_blocked_regardless_of_risk_label():
    decision = AgentGate().evaluate_step("db_execute(DROP TABLE users CASCADE)", step_risk="LOW_RISK")
    assert decision.action == GovernanceAction.BLOCK


def test_high_risk_step_requires_human_review():
    decision = AgentGate().evaluate_step("send_email(to='board@company.com')", step_risk="HIGH_RISK")
    assert decision.action == GovernanceAction.HUMAN_REVIEW


def test_critical_risk_step_requires_human_review():
    decision = AgentGate().evaluate_step("wire_transfer(amount=100000)", step_risk="CRITICAL")
    assert decision.action == GovernanceAction.HUMAN_REVIEW


def test_sensitive_access_keyword_is_restricted():
    decision = AgentGate().evaluate_step("db_query(SELECT ssn FROM employees)", step_risk="LOW_RISK")
    assert decision.action == GovernanceAction.RESTRICT


def test_medium_risk_step_is_restricted():
    decision = AgentGate().evaluate_step("file_write(path='reports/summary.md')", step_risk="MEDIUM_RISK")
    assert decision.action == GovernanceAction.RESTRICT


def test_benign_step_is_allowed():
    decision = AgentGate().evaluate_step("sql_query(SELECT count(*) FROM support_tickets)", step_risk="NO_ACTION")
    assert decision.action == GovernanceAction.ALLOW
