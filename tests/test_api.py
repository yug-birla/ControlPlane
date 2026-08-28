import pytest
from fastapi.testclient import TestClient

import controlplane.api.routes as routes_module
from controlplane.main import app
from tests.fakes import FailingModelProvider, FakeModelProvider

client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch):
    """Automated tests never call the live Groq API -- only
    tests/manual_groq_live_check.py does that, explicitly and manually."""
    provider = FakeModelProvider(content="a fake model response")
    monkeypatch.setattr(routes_module._runtime, "_provider_factory", lambda settings, role="STRONG": provider)
    return provider


def test_create_request_happy_path(fake_provider):
    resp = client.post("/v1/requests", json={"query": "What is the capital of France?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["request_id"].startswith("req_")
    assert body["trace_id"].startswith("trace_")
    assert body["trajectory_id"].startswith("traj_")
    assert body["answer"] == "a fake model response"
    assert fake_provider.calls == ["What is the capital of France?"]


def test_two_requests_get_distinct_ids():
    r1 = client.post("/v1/requests", json={"query": "a"}).json()
    r2 = client.post("/v1/requests", json={"query": "b"}).json()
    assert r1["request_id"] != r2["request_id"]
    assert r1["trace_id"] != r2["trace_id"]
    assert r1["trajectory_id"] != r2["trajectory_id"]


def test_empty_query_is_a_structured_validation_error():
    resp = client.post("/v1/requests", json={"query": "   "})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["retryable"] is False


def test_missing_query_field_is_a_structured_validation_error():
    resp = client.post("/v1/requests", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"


def test_response_contains_a_real_trust_assessment():
    # "risk"/"confidence" moved from forbidden to expected in Milestone 2;
    # "evaluation" moved from forbidden to expected in Milestone 4; "trust"
    # moved from forbidden to expected in Milestone 6 -- the Trust Layer
    # (controlplane.trust.engine.TrustEngine) is now real.
    resp = client.post("/v1/requests", json={"query": "hello"})
    body = resp.json()
    assert "trust" in body["metadata"]
    assert body["metadata"]["trust"]["level"] in ("HIGH", "MEDIUM", "LOW")


def test_response_contains_real_query_profile_and_risk_metadata():
    resp = client.post("/v1/requests", json={"query": "What was our Q4 revenue?"})
    body = resp.json()
    metadata = body["metadata"]
    assert "query_profile" in metadata
    assert "risk" in metadata
    assert "policy" in metadata
    assert metadata["query_profile"]["source"] in ("rules", "embedding_knn", "hybrid")
    assert metadata["risk"]["severity"] in ("NO_ACTION", "LOW_RISK", "MEDIUM_RISK", "HIGH_RISK", "CRITICAL")
    assert set(metadata["risk"]["risk_dimensions"]) == {
        "factuality", "reasoning", "privacy", "pii", "security", "bias", "financial", "action", "safety",
    }


def test_response_contains_real_evaluation_metadata():
    resp = client.post("/v1/requests", json={"query": "What is the capital of France?"})
    body = resp.json()
    evaluations = body["metadata"]["evaluation"]
    names = {e["evaluator"] for e in evaluations}
    assert {
        "privacy_pii", "action_risk", "safety", "grounding", "factuality",
        "response_confidence", "reasoning", "rag_adequacy", "agent_governance", "prompt_injection", "bias",
    } == names
    not_implemented = {e["evaluator"] for e in evaluations if e["status"] == "NOT_IMPLEMENTED"}
    assert {"bias"} == not_implemented


def test_model_provider_failure_returns_structured_dependency_error(monkeypatch):
    monkeypatch.setattr(
        routes_module._runtime, "_provider_factory", lambda settings, role="STRONG": FailingModelProvider()
    )
    quiet_client = TestClient(app, raise_server_exceptions=False)
    resp = quiet_client.post("/v1/requests", json={"query": "hello"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["error_code"] == "DEPENDENCY_ERROR"
    assert body["retryable"] is True


def test_model_provider_timeout_returns_structured_timeout_error(monkeypatch):
    monkeypatch.setattr(
        routes_module._runtime,
        "_provider_factory",
        lambda settings, role="STRONG": FailingModelProvider(timeout=True),
    )
    quiet_client = TestClient(app, raise_server_exceptions=False)
    resp = quiet_client.post("/v1/requests", json={"query": "hello"})
    assert resp.status_code == 504
    body = resp.json()
    assert body["error_code"] == "TIMEOUT_ERROR"


def test_unhandled_exception_returns_structured_internal_error_without_leaking_details(monkeypatch):
    def boom(ctx, state):
        raise RuntimeError("something exploded with a secret detail")

    monkeypatch.setattr(routes_module._runtime, "handle", boom)
    # raise_server_exceptions=False: verify the JSON response our handler
    # produced, rather than TestClient's default behavior of re-raising the
    # original exception for test visibility.
    quiet_client = TestClient(app, raise_server_exceptions=False)
    resp = quiet_client.post("/v1/requests", json={"query": "hello"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    assert "secret detail" not in resp.text
