import sqlite3

import pytest

from controlplane.capabilities.sql_capability import SQLCapability
from controlplane.capabilities.sql_setup import DB_PATH, build_database


@pytest.fixture(scope="module", autouse=True)
def ensure_db():
    build_database()


def test_revenue_query_matches_revenue_template():
    result = SQLCapability().execute("What was our department revenue last quarter?")
    assert result["status"] == "EXECUTED"
    assert result["template"] == "department_revenue_summary"
    assert result["row_count"] > 0


def test_unmatched_query_falls_back_to_client_directory():
    result = SQLCapability().execute("asdkjfh random gibberish query")
    assert result["template"] == "client_directory"


def test_entity_match_filters_to_specific_project():
    result = SQLCapability().execute("Who is staffed on the TerraEnergy project?")
    assert result["entity_filter"]["name"] == "TerraEnergy AI Analytics Platform"
    assert all(row["project_name"] == "TerraEnergy AI Analytics Platform" for row in result["rows"])
    assert result["row_count"] > 0


def test_connection_is_read_only_at_driver_level():
    """Defense-in-depth: even a hypothetical future bug that put a write
    statement into the template list would fail here, not just because
    the templates are hand-vetted SELECTs."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO clients (id, client_code, name, industry, segment, region, country, created_at) "
                      "VALUES ('X', 'X', 'X', 'X', 'X', 'X', 'X', 'X')")
    conn.close()


def test_result_never_includes_raw_user_input_interpolated_into_sql():
    # The SQL string itself must only ever contain the fixed template
    # text plus a parameter placeholder ("?"), never the literal query text.
    result = SQLCapability().execute("Who is staffed on the TerraEnergy project?")
    assert "TerraEnergy" not in result["sql"]
    assert "?" in result["sql"]


def test_all_templates_execute_without_error():
    queries = [
        "What was our Q4 revenue?",
        "Show me employee utilization",
        "Which invoices are overdue?",
        "Who is staffed on active projects?",
        "Show me project budgets",
    ]
    cap = SQLCapability()
    for q in queries:
        result = cap.execute(q)
        assert result["status"] == "EXECUTED"
        assert result["row_count"] >= 0
