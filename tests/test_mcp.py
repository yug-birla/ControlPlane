"""MCP capability fabric: discovery, invocation, normalization, failures,
and the architectural boundary.

The spec's hardest requirement is not a feature -- it is a prohibition:
"MCP must never become the brain." That is tested structurally here, not
just asserted in a docstring.
"""

from __future__ import annotations

import ast
import pathlib

from controlplane.mcp.client import CAPABILITY_GROUPS, MCPClient
from controlplane.mcp.contracts import MCPFailure, MCPStatus, is_retryable


def _client(**handlers) -> MCPClient:
    return MCPClient(handlers=handlers)


# --- The boundary ------------------------------------------------

def test_mcp_never_imports_the_decision_making_modules():
    """MCP provides discovery/invocation/resource access. ControlPlane owns
    routing, risk, policy, evaluation, intervention, replanning, trust and
    escalation. A docstring promising that is worth little; this checks the
    imports, so the boundary fails loudly the moment someone crosses it."""
    forbidden = {
        "controlplane.decision", "controlplane.intervention", "controlplane.planning",
        "controlplane.policy", "controlplane.risk", "controlplane.trust",
        "controlplane.verification", "controlplane.routing",
    }
    mcp_dir = pathlib.Path("controlplane/mcp")
    offences = []
    for path in mcp_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == f or name.startswith(f + ".") for f in forbidden):
                    offences.append(f"{path.name} imports {name}")
    assert not offences, "MCP is reaching into ControlPlane's decision layer: " + "; ".join(offences)


def test_the_five_specified_capability_groups_are_represented():
    """docs/architecture/...MASTER_SPEC.md section 45: Model, SQL/Data,
    RAG/Retrieval, Web/External Data, Agent/Tools."""
    assert set(CAPABILITY_GROUPS.values()) >= {
        "model", "sql-data", "rag-retrieval", "web-external", "agent-tools"
    }


# --- Discovery ---------------------------------------------------

def test_discovery_answers_what_capabilities_are_available():
    found = _client().discover()
    assert found, "discovery returned nothing"
    ids = {d.descriptor.capability_id for d in found}
    assert "RAG" in ids and "SQL" in ids
    assert all(d.server for d in found)


def test_discovery_can_be_filtered_by_data_requirement():
    """This is what makes planning discovery-driven: the planner asks
    'what serves SQL_DB?', not 'what do I do when RAG fails?'."""
    found = _client().discover(data_requirements={"SQL_DB"}, supplies_evidence=True)
    assert [d.descriptor.capability_id for d in found] == ["SQL"]


def test_discovery_excludes_mocked_capabilities_by_default():
    ids = {d.descriptor.capability_id for d in _client().discover()}
    assert "CHAT_HISTORY" not in ids and "WEB" not in ids


# --- Invocation and normalization --------------------------------

def test_successful_invocation_returns_a_normalized_result():
    client = _client(RAG=lambda q: {"chunks": [{"text": "Meals are $75/day."}], "status": "EXECUTED"})
    result = client.invoke("RAG", "what is the meal limit?")

    assert result.ok and result.status is MCPStatus.OK
    assert result.capability_id == "RAG"
    assert result.server == "rag-retrieval"
    assert result.operation_id.startswith("mcpop")
    assert result.evidence == ["Meals are $75/day."]
    assert result.latency_ms >= 0


def test_sql_rows_are_normalized_into_evidence_too():
    """Different capabilities return different shapes; normalizing them is
    the adapter's job, not every caller's."""
    client = _client(SQL=lambda q: {"rows": [{"revenue": 140000, "quarter": "Q4"}]})
    result = client.invoke("SQL", "q4 revenue?")
    assert result.evidence == ["revenue=140000, quarter=Q4"]


def test_permissions_used_are_reported_from_the_registry():
    """ControlPlane authorizes; MCP reports what a call required so that
    authorization and lineage have something to work with."""
    client = _client(SQL=lambda q: {"rows": []})
    assert "read:enterprise_db" in client.invoke("SQL", "q").permissions_used


# --- Failure taxonomy --------------------------------------------

def test_unknown_capability_is_capability_not_found():
    result = _client().invoke("NOT_A_CAPABILITY", "q")
    assert result.failure is MCPFailure.CAPABILITY_NOT_FOUND


def test_registered_but_unwired_capability_is_unavailable():
    """Registered-but-not-deployed is a different problem from
    does-not-exist, and the control loop should be able to tell them
    apart."""
    result = _client().invoke("RAG", "q")
    assert result.failure is MCPFailure.UNAVAILABLE


def test_timeout_permission_and_server_failures_are_classified_distinctly():
    def _timeout(q): raise TimeoutError("took too long")
    def _denied(q): raise PermissionError("nope")
    def _boom(q): raise RuntimeError("server exploded")

    assert _client(RAG=_timeout).invoke("RAG", "q").failure is MCPFailure.TIMEOUT
    assert _client(RAG=_denied).invoke("RAG", "q").failure is MCPFailure.PERMISSION_DENIED
    assert _client(RAG=_boom).invoke("RAG", "q").failure is MCPFailure.SERVER_FAILURE


def test_a_non_dict_response_is_an_invalid_response_not_a_crash():
    result = _client(RAG=lambda q: "just a string").invoke("RAG", "q")
    assert result.failure is MCPFailure.INVALID_RESPONSE


def test_capability_failure_never_raises():
    """A failure must be a first-class result ControlPlane can act on, not
    an exception that unwinds the execution graph."""
    def _boom(q): raise RuntimeError("boom")
    result = _client(RAG=_boom).invoke("RAG", "q")  # must not raise
    assert not result.ok and result.error


def test_retryability_is_classified_as_data_not_acted_on_by_the_fabric():
    """The fabric says which failures COULD be retried; it does not retry.
    A fabric that retries on its own has started making control decisions."""
    assert is_retryable(MCPFailure.TIMEOUT)
    assert is_retryable(MCPFailure.SERVER_FAILURE)
    assert not is_retryable(MCPFailure.PERMISSION_DENIED)
    assert not is_retryable(MCPFailure.CAPABILITY_NOT_FOUND)


# --- Health ------------------------------------------------------

def test_health_degrades_on_real_failure_rather_than_reporting_static_metadata():
    def _boom(q): raise RuntimeError("boom")
    client = _client(RAG=_boom)
    assert client.health("RAG") == "AVAILABLE"  # registry's declared status
    client.invoke("RAG", "q")
    assert client.health("RAG") == "DEGRADED"  # observed reality


def test_health_recovers_after_a_successful_call():
    client = _client(RAG=lambda q: {"chunks": []})
    client._health["RAG"] = "DEGRADED"
    client.invoke("RAG", "q")
    assert client.health("RAG") == "AVAILABLE"
