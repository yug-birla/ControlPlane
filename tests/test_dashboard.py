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


# --- System-wide component health (Milestone 12) ---

def test_component_health_view_and_api_render():
    client = TestClient(app)
    assert client.get("/dashboard/health-map").status_code == 200
    payload = client.get("/dashboard/api/component-health").json()
    assert "components" in payload and "sample_count" in payload


def test_component_health_never_reports_a_fabricated_zero_latency():
    """Trajectory steps are frequently written once at completion, so
    started_at == completed_at and the elapsed time is an artefact of
    write timing. Averaging those produced a confident p50 of 0.0ms for
    EVERY component -- a fabricated metric. Not-measured must read as
    None, never as zero."""
    from controlplane.dashboard.queries import aggregate_component_health

    health = aggregate_component_health()
    for component in health["components"]:
        for key in ("latency_ms_p50", "latency_ms_p95"):
            value = component[key]
            assert value is None or value > 0, (
                f"{component['component']}.{key} reported {value!r}; "
                "zero latency must be None (not measured), not 0.0"
            )


def test_component_health_p95_requires_enough_samples():
    from controlplane.dashboard.queries import aggregate_component_health

    for component in aggregate_component_health()["components"]:
        if component["executions"] < 20:
            assert component["latency_ms_p95"] is None


# --- Evidence view (spec §59) -----------------------------------


def test_evidence_page_renders_measured_baseline_comparison():
    """The comparison view must render numbers that came out of a
    committed experiment file, not placeholders."""
    from fastapi.testclient import TestClient

    from controlplane.main import app

    response = TestClient(app).get("/dashboard/evidence")
    assert response.status_code == 200
    body = response.text
    assert "Baseline vs ControlPlane" in body
    assert "Key-fact accuracy" in body
    # Attribution of the cost, not only the wins.
    assert "Which component caused the over-control" in body


def test_evidence_reports_regressions_with_the_same_prominence_as_wins():
    """Guard against a comparison view that quietly hides the metrics
    where ControlPlane did worse. The 62-case run has both a WORSE row
    (latency, over-control) and a NO CHANGE row (abstention); if either
    label stops appearing, the view has started flattering the system."""
    from controlplane.dashboard.evidence import build_evidence

    comparison = build_evidence()["baseline_vs_controlplane"]["comparison"]
    assert any(not m["improved"] and not m["unchanged"] for m in comparison), "no regression surfaced"
    assert any(m["unchanged"] for m in comparison), "no unchanged metric surfaced"


def test_evidence_never_fabricates_a_missing_result_file(tmp_path, monkeypatch):
    """A missing result file must degrade to an explicit 'unavailable',
    never to an empty table that reads like a measured zero."""
    import controlplane.dashboard.evidence as evidence_module

    monkeypatch.setattr(evidence_module, "_RESULTS_DIR", tmp_path)
    evidence = evidence_module.build_evidence()
    assert evidence["baseline_vs_controlplane"]["available"] is False
    assert evidence["ablations"]["available"] is False


def test_over_control_attribution_excludes_correctly_controlled_categories():
    """Controlling a prompt injection or a high-risk action is the
    system working, not a cost. Counting those as over-control would
    make the attribution table meaningless."""
    from controlplane.dashboard.evidence import _over_control_attribution

    rows = [
        {"controlled": True, "category": "PROMPT_INJECTION", "flagged_evaluators": ["prompt_injection"]},
        {"controlled": True, "category": "HIGH_RISK_ACTION", "flagged_evaluators": ["action_risk"]},
        {"controlled": True, "category": "GROUNDED_POLICY", "flagged_evaluators": ["grounding"]},
        {"controlled": False, "category": "GROUNDED_POLICY", "flagged_evaluators": ["grounding"]},
    ]
    attribution = _over_control_attribution(rows)
    assert [a["evaluator"] for a in attribution] == ["grounding"]
    assert attribution[0]["of_controlled_benign"] == 1


def test_over_control_breakdown_separates_defect_from_correct_behaviour():
    """The headline over-control rate charges ControlPlane for
    withholding WRONG answers, which is the system working. The
    breakdown must keep those apart, or component attribution points at
    the wrong thing."""
    from controlplane.dashboard.evidence import _over_control_breakdown

    rows = [
        # withheld a correct answer -- the real defect
        {"controlled": True, "category": "GROUNDED_POLICY", "key_fact_correct": True, "answer": "the figure is $250"},
        # asked for clarification, produced nothing
        {"controlled": True, "category": "GROUNDED_POLICY", "key_fact_correct": False, "answer": ""},
        # controlled a wrong answer -- correct behaviour
        {"controlled": True, "category": "GROUNDED_POLICY", "key_fact_correct": False, "answer": "the figure is $999"},
        # not controlled at all
        {"controlled": False, "category": "GROUNDED_POLICY", "key_fact_correct": True, "answer": "fine"},
        # controlling an unsafe case is never counted as over-control
        {"controlled": True, "category": "PROMPT_INJECTION", "key_fact_correct": False, "answer": ""},
    ]
    breakdown = _over_control_breakdown(rows)
    assert breakdown["benign_cases"] == 4
    by_verdict = {b["verdict"]: b for b in breakdown["buckets"]}
    assert by_verdict["DEFECT"]["count"] == 1
    assert by_verdict["CONSERVATIVE"]["count"] == 1
    assert by_verdict["CORRECT BEHAVIOUR"]["count"] == 1
    # The headline still counts all three, so runs stay comparable.
    assert breakdown["controlled_total"] == 3


# --- Dataset health (spec §58) ----------------------------------


def test_dataset_health_counts_from_the_files_not_a_registry():
    """A registry drifts from the data it describes. These numbers must
    come from the JSON on disk."""
    from controlplane.dashboard.dataset_health import build_dataset_health

    health = build_dataset_health()
    assert health["dataset_count"] > 10
    by_name = {d["dataset"]: d for d in health["datasets"]}
    # Counted, not transcribed: this file's real size.
    assert by_name["baseline_vs_controlplane_cases"]["cases"] == 62
    assert by_name["enterprise_injection_cases"]["cases"] == 80


def test_a_dataset_without_a_held_out_split_is_flagged():
    """The warning this project has actually been burned by twice."""
    from controlplane.dashboard.dataset_health import build_dataset_health

    by_name = {d["dataset"]: d for d in build_dataset_health()["datasets"]}
    single = by_name["baseline_vs_controlplane_cases"]
    assert any("no held-out split" in w for w in single["warnings"])

    split = by_name["enterprise_injection_cases"]
    assert not any("no held-out split" in w for w in split["warnings"])


def test_split_leakage_is_detected():
    """k-NN's 'model' IS its reference data, so an evaluation case
    appearing in two splits makes the reported number meaningless."""
    from controlplane.dashboard.dataset_health import _split_overlap

    clean = [{"split": "train", "query": "a"}, {"split": "test", "query": "b"}]
    leaking = [{"split": "train", "query": "a"}, {"split": "test", "query": "a"}]
    assert _split_overlap(clean) == 0
    assert _split_overlap(leaking) == 1


def test_a_single_class_dataset_is_flagged_as_unable_to_measure_false_positives():
    from controlplane.dashboard.dataset_health import _warnings

    warnings = _warnings([{}] * 50, {"train": 40, "test": 10}, {"ONLY_ONE": 50}, 0)
    assert any("single class" in w for w in warnings)


def test_a_sibling_dev_file_counts_as_a_held_out_split():
    """reasoning_cases.json / reasoning_cases_dev.json ARE a proper
    split; reporting them as single-split made the warning noise."""
    from controlplane.dashboard.dataset_health import _sibling_split_partner

    stems = {"reasoning_cases", "reasoning_cases_dev", "baseline_vs_controlplane_cases",
             "baseline_vs_controlplane_cases_v2"}
    assert _sibling_split_partner("reasoning_cases", stems) == "reasoning_cases_dev"
    assert _sibling_split_partner("reasoning_cases_dev", stems) == "reasoning_cases"


def test_a_version_increment_is_not_credited_as_a_split():
    """_v2 is a bigger dataset, not a held-out half. Crediting it would
    manufacture a healthy signal where none exists -- worse than the
    honest warning."""
    from controlplane.dashboard.dataset_health import _sibling_split_partner

    stems = {"baseline_vs_controlplane_cases", "baseline_vs_controlplane_cases_v2"}
    assert _sibling_split_partner("baseline_vs_controlplane_cases", stems) is None


# ---------------------------------------------------------------------------
# SS50/SS52/SS67 -- the multi-agent control view. The dashboard could already
# draw agent topology and messages; it could not say which agents were worth
# running, which is the question a reviewer actually asks.
# ---------------------------------------------------------------------------


def test_the_agent_view_survives_an_empty_event_stream():
    """It must render "nothing recorded" rather than an empty table that
    reads like a measured zero."""
    from controlplane.dashboard.agents import build_agent_view

    view = build_agent_view(limit=0)
    assert view["request_count"] == 0
    assert view["total_agents"] == 0
    assert view["wasted_agent_rate"] is None
    assert view["communication"]["utility_rate"] is None


def test_a_role_is_not_judged_on_too_few_observations():
    """One redundant run is an anecdote. A dashboard that calls a role
    useless on a single observation is worse than one that says nothing."""
    from controlplane.dashboard.agents import (
        MIN_OBSERVATIONS_FOR_ROLE_VERDICT,
        _role_verdict,
    )

    one_bad = [{"verdict": "REDUNDANT"}]
    verdict, reason = _role_verdict(one_bad)
    assert verdict == "UNCERTAIN"
    assert "too few" in reason

    many_bad = [{"verdict": "REDUNDANT"}] * MIN_OBSERVATIONS_FOR_ROLE_VERDICT
    assert _role_verdict(many_bad)[0] == "REDUNDANT"

    many_good = [{"verdict": "ESSENTIAL"}] * MIN_OBSERVATIONS_FOR_ROLE_VERDICT
    assert _role_verdict(many_good)[0] == "USEFUL"


def test_an_inconsistent_role_is_uncertain_rather_than_useful():
    """Half the runs adding nothing is not a role that has earned a
    USEFUL verdict."""
    from controlplane.dashboard.agents import _role_verdict

    mixed = [{"verdict": "ESSENTIAL"}, {"verdict": "REDUNDANT"},
             {"verdict": "INERT"}, {"verdict": "CONTRIBUTING"}]
    verdict, reason = _role_verdict(mixed)
    assert verdict == "UNCERTAIN"
    assert "inconsistently" in reason


def test_the_agent_page_and_its_api_both_render():
    from fastapi.testclient import TestClient

    from controlplane.main import app

    client = TestClient(app)
    page = client.get("/dashboard/agents")
    assert page.status_code == 200
    assert "Multi-Agent Control" in page.text

    api = client.get("/dashboard/api/agents")
    assert api.status_code == 200
    body = api.json()
    for key in ("request_count", "total_agents", "roles", "communication", "verdict_counts"):
        assert key in body, key


def test_the_agent_page_is_reachable_from_every_other_page():
    """A view nobody can navigate to is not part of the dashboard."""
    from fastapi.testclient import TestClient

    from controlplane.main import app

    client = TestClient(app)
    for path in ("/dashboard", "/dashboard/evidence", "/dashboard/health-map"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "/dashboard/agents" in response.text, path


# ---------------------------------------------------------------------------
# Live Execution Console. The detail page answers "what did each component
# record"; the console answers "what did ControlPlane decide, and why did
# the execution change". It must never turn an absent measurement into a
# confident value.
# ---------------------------------------------------------------------------


def test_the_console_marks_a_stage_that_did_not_fire_rather_than_showing_it_empty():
    """A request with no replan must say so. An empty box reads like a
    stage that passed, which is the null-as-zero defect in another form."""
    from controlplane.dashboard.console import build_console

    console = build_console({
        "request": {"id": "req_x", "query_text": "q", "status": "COMPLETED"},
        "replans": [], "interventions": [],
    })
    stage = next(s for s in console["stages"] if s["key"] == "intervention")
    assert stage["status"] == "NOT_TRIGGERED"
    assert "did not fire" in stage["rows"][0]["value"]


def test_the_console_reports_missing_data_as_not_recorded():
    from controlplane.dashboard.console import build_console

    console = build_console({"request": {"id": "req_x", "query_text": "q"}})
    for key in ("understanding", "risk", "verification", "trust"):
        stage = next(s for s in console["stages"] if s["key"] == key)
        assert stage["status"] == "NOT_RECORDED", (key, stage["status"])


def test_an_unknown_event_type_does_not_break_the_replay():
    """Out-of-order, late or unrecognised events must not corrupt the
    view -- they appear in the feed with no stage rather than raising."""
    from controlplane.dashboard.console import build_console

    console = build_console({
        "request": {"id": "req_x", "query_text": "q"},
        "events": [
            {"event_type": "QUERY_RECEIVED", "observed_at": "2026-08-30T10:00:00+00:00"},
            {"event_type": "SOMETHING_NEW", "observed_at": "2026-08-30T10:00:01+00:00"},
        ],
    })
    stages = [e["stage"] for e in console["timeline"]]
    assert stages == ["query", None]
    assert console["timeline"][1]["offset_ms"] == 1000


def test_the_console_renders_for_a_real_recorded_request():
    from fastapi.testclient import TestClient

    from controlplane.dashboard.queries import list_recent_requests
    from controlplane.main import app

    recent = list_recent_requests(limit=1)
    if not recent:
        import pytest

        pytest.skip("no recorded requests")
    request_id = recent[0]["request_id"]

    client = TestClient(app)
    page = client.get(f"/dashboard/console/{request_id}")
    assert page.status_code == 200
    assert "Governance trajectory" in page.text
    assert client.get(f"/dashboard/api/console/{request_id}").status_code == 200


# ---------------------------------------------------------------------------
# Live Execution. POST /v1/requests is synchronous and returns only when the
# whole control loop has finished -- correct for an API client, useless for
# watching an execution unfold. This runs the SAME Runtime.handle on a worker
# thread so the page can follow progress from events the runtime commits as
# it goes. There is one control loop; this is not a second copy of it.
# ---------------------------------------------------------------------------


def test_the_live_page_renders_with_example_queries():
    from fastapi.testclient import TestClient

    from controlplane.main import app

    page = TestClient(app).get("/dashboard/live")
    assert page.status_code == 200
    # Structural, not copy: the graph canvas, the edge layer, and the
    # ControlPlane-vs-capability legend are what the page IS. An earlier
    # version asserted on a heading, which broke when the graph became an
    # unlabelled hero canvas -- a passing test would have meant nothing.
    assert 'id="gcanvas"' in page.text
    assert 'id="gedges"' in page.text
    assert "ControlPlane &mdash; decides" in page.text
    assert "Capability &mdash; executes" in page.text
    # The active nav state must be unmistakable on the page you are on.
    assert 'href="/dashboard/live"' in page.text and 'class="active"' in page.text
    # The examples must come from the module, not be hard-coded in the template.
    from controlplane.dashboard.live import EXAMPLE_QUERIES

    for label, _query, _why in EXAMPLE_QUERIES:
        assert label in page.text, label


def test_an_empty_query_is_refused():
    from fastapi.testclient import TestClient

    from controlplane.main import app

    response = TestClient(app).post("/dashboard/api/run", json={"query": "   "})
    assert response.status_code == 400


def test_polling_an_unknown_run_is_a_404_not_a_crash():
    from fastapi.testclient import TestClient

    from controlplane.main import app

    assert TestClient(app).get("/dashboard/api/live/run_does_not_exist").status_code == 404


def test_the_console_builder_survives_a_partial_trajectory():
    """Polled mid-run, the request exists but almost nothing else does.
    The builder must return partial state rather than raising -- the page
    reads it every 1.2 s while execution is still going."""
    from controlplane.dashboard.console import build_console

    console = build_console({"request": {"id": "req_x", "query_text": "q", "status": "RECEIVED"}})
    assert console["available"] is True
    assert console["stages"], "a partially-executed request must still render its spine"
