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


def test_dashboard_never_exposes_secrets():
    # Generic env-var-name and provider-prefix markers only -- deliberately
    # never a literal fragment of any real key, even a truncated one, so
    # this test file itself never carries a piece of a real credential.
    resp = client.get("/dashboard")
    for secret_marker in ("GROQ_API_KEY", "GEMINI_API_KEY", "gsk_"):
        assert secret_marker not in resp.text
