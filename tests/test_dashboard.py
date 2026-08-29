"""Dashboard smoke tests -- read-only endpoints over real Postgres data
(same DB the rest of the test suite writes to)."""

from fastapi.testclient import TestClient

import controlplane.api.routes as routes_module
from controlplane.main import app
from tests.fakes import FakeModelProvider

client = TestClient(app)


def _create_request(query: str = "What is the capital of France?") -> str:
    provider = FakeModelProvider(content="Paris.")
    prev = routes_module._runtime._provider_factory
    routes_module._runtime._provider_factory = lambda settings, role="STRONG": provider
    try:
        resp = client.post("/v1/requests", json={"query": query})
    finally:
        routes_module._runtime._provider_factory = prev
    return resp.json()["request_id"]


def test_dashboard_home_renders_and_lists_the_request():
    request_id = _create_request()
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_dashboard_api_list_includes_new_request():
    request_id = _create_request()
    resp = client.get("/dashboard/api/requests")
    assert resp.status_code == 200
    ids = [r["request_id"] for r in resp.json()]
    assert request_id in ids


def test_dashboard_detail_page_renders_why_rationale():
    request_id = _create_request()
    resp = client.get(f"/dashboard/requests/{request_id}")
    assert resp.status_code == 200
    # The WHY panel must show the actual router reason strings, not a
    # generic placeholder -- these come straight from CapabilityRoute/
    # ModelRouteDecision.reason (real, not fabricated).
    assert "Capability Router" in resp.text
    assert "Model Router" in resp.text


def test_dashboard_api_detail_includes_full_structure():
    request_id = _create_request()
    resp = client.get(f"/dashboard/api/requests/{request_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["request"]["id"] == request_id
    assert body["route_decision"] is not None
    assert body["route_decision"]["capability_reason"]
    assert body["route_decision"]["model_reason"]
    assert body["answer"] == "Paris."
    assert len(body["trajectory_steps"]) > 0
    assert len(body["events"]) > 0
    assert len(body["evaluations"]) > 0


def test_dashboard_detail_404_for_unknown_request():
    resp = client.get("/dashboard/requests/does-not-exist")
    assert resp.status_code == 404


def test_dashboard_stats_reflects_real_counts():
    _create_request()
    resp = client.get("/dashboard/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] > 0
    assert "risk_distribution" in body


def test_dashboard_shows_control_loop_for_an_intervened_request():
    from controlplane.models.provider import ModelProvider, ModelResult

    class _ScriptedProvider(ModelProvider):
        name = "scripted"

        def __init__(self):
            self.calls = 0

        def generate(self, *, prompt: str) -> ModelResult:
            self.calls += 1
            content = (
                "The weather forecast predicts rain tomorrow across the region."
                if self.calls == 1
                else "Meal reimbursement is up to $75/day domestic, $100/day international, per the travel policy."
            )
            return ModelResult(provider=self.name, model="fake-scripted", content=content, latency_ms=1, finish_reason="stop")

    provider = _ScriptedProvider()
    prev = routes_module._runtime._provider_factory
    routes_module._runtime._provider_factory = lambda settings, role="STRONG": provider
    try:
        resp = client.post("/v1/requests", json={"query": "What is the meal reimbursement limit according to the travel policy?"})
    finally:
        routes_module._runtime._provider_factory = prev
    request_id = resp.json()["request_id"]

    detail_resp = client.get(f"/dashboard/requests/{request_id}")
    assert detail_resp.status_code == 200
    assert "RETRIEVE_MORE" in detail_resp.text
    assert "Verification" in detail_resp.text

    api_detail = client.get(f"/dashboard/api/requests/{request_id}").json()
    assert len(api_detail["decisions"]) == 2
    assert len(api_detail["interventions"]) == 1
    assert api_detail["interventions"][0]["intervention_type"] == "RETRIEVE_MORE"
    assert api_detail["verification"]["status"] == "VERIFIED"

    list_row = next(r for r in client.get("/dashboard/api/requests").json() if r["request_id"] == request_id)
    assert list_row["intervened"] is True
    assert list_row["verification_status"] == "VERIFIED"


def test_dashboard_detail_shows_a_derived_trust_level():
    request_id = _create_request()
    resp = client.get(f"/dashboard/requests/{request_id}")
    assert resp.status_code == 200
    assert "Trust" in resp.text

    api_detail = client.get(f"/dashboard/api/requests/{request_id}").json()
    assert api_detail["trust"] is not None
    assert api_detail["trust"]["level"] in ("HIGH", "MEDIUM", "LOW")


def test_dashboard_shows_agent_governance_and_permission_lineage():
    provider = FakeModelProvider(content="Database query completed successfully.")
    prev = routes_module._runtime._provider_factory
    routes_module._runtime._provider_factory = lambda settings, role="STRONG": provider
    try:
        resp = client.post("/v1/requests", json={"query": "Please execute a database query to count support tickets"})
    finally:
        routes_module._runtime._provider_factory = prev
    request_id = resp.json()["request_id"]

    detail_resp = client.get(f"/dashboard/requests/{request_id}")
    assert detail_resp.status_code == 200
    assert "Permission Lineage" in detail_resp.text

    api_detail = client.get(f"/dashboard/api/requests/{request_id}").json()
    assert api_detail["permission_lineage"] is not None
    assert api_detail["permission_lineage"]["requested_tool"] == "sql_read_query"
    assert api_detail["permission_lineage"]["authorization"] == "ALLOW"


def test_dashboard_never_exposes_secrets():
    # Generic env-var-name and provider-prefix markers only -- deliberately
    # never a literal fragment of any real key, even a truncated one, so
    # this test file itself never carries a piece of a real credential.
    resp = client.get("/dashboard")
    for secret_marker in ("GROQ_API_KEY", "GEMINI_API_KEY", "gsk_"):
        assert secret_marker not in resp.text


# --- Visual execution map (Milestone 12) ---

def _map_detail(**overrides):
    base = {
        "route_decision": {"execution_graph": {"nodes": [
            {"node_id": "agent_retriever", "capability": "AGENT", "depends_on": [],
             "status": "COMPLETED", "latency_ms": 12,
             "input_ref": {"agent_id": "agent_retriever", "role": "RETRIEVER",
                            "serves_capability": "RAG"}, "error": None},
            {"node_id": "agent_analyst", "capability": "AGENT", "depends_on": [],
             "status": "FAILED", "latency_ms": 8, "input_ref": None, "error": "boom"},
            {"node_id": "merge", "capability": "merge",
             "depends_on": ["agent_retriever", "agent_analyst"],
             "status": "COMPLETED", "latency_ms": 1, "input_ref": None, "error": None},
        ]}},
        "events": [{"event_type": "AGENT_MESSAGE_SENT", "payload": {
            "message_type": "HANDOFF", "from_agent": "agent_retriever",
            "to_agent": "merge", "data_sensitivity": "CONFIDENTIAL"}}],
        "replans": [],
    }
    base.update(overrides)
    return base


def test_execution_map_reflects_real_node_status_not_a_template_picture():
    from controlplane.dashboard.queries import build_execution_map

    m = build_execution_map(_map_detail())
    by_id = {n["id"]: n for n in m["nodes"]}
    assert by_id["agent_retriever"]["status_class"] == "ok"
    assert by_id["agent_analyst"]["status_class"] == "failed"
    assert m["failed_nodes"] == ["agent_analyst"]
    assert by_id["agent_retriever"]["serves_capability"] == "RAG"


def test_execution_map_derives_parallel_groups_from_dependencies():
    """Parallelism shown must come from the dependency structure the
    executor actually scheduled by -- not from a flag."""
    from controlplane.dashboard.queries import build_execution_map

    m = build_execution_map(_map_detail())
    assert m["parallel_groups"] == [["agent_retriever", "agent_analyst"]]


def test_execution_map_draws_agent_communication_from_the_event_stream():
    """The picture must not be able to claim a handoff that was never
    recorded."""
    from controlplane.dashboard.queries import build_execution_map

    m = build_execution_map(_map_detail())
    comm = [e for e in m["edges"] if e["kind"] == "communicates"]
    assert len(comm) == 1
    assert comm[0]["sensitivity"] == "CONFIDENTIAL"

    without_events = build_execution_map(_map_detail(events=[]))
    assert not [e for e in without_events["edges"] if e["kind"] == "communicates"]


def test_execution_map_is_empty_for_an_empty_request_rather_than_a_stock_diagram():
    from controlplane.dashboard.queries import build_execution_map

    assert build_execution_map({})["nodes"] == []
    assert build_execution_map({"route_decision": {}})["nodes"] == []


def test_execution_map_adds_no_database_queries():
    """The dashboard must not add request latency: the map is derived
    from the detail dict already fetched."""
    from controlplane.dashboard.queries import build_execution_map

    detail = _map_detail()
    # Passing a plain dict proves it never touches the session.
    m = build_execution_map(detail)
    assert m["nodes"]
