"""SQL capability -- V0 template-matched, NOT general NL2SQL.

Per bootstrap instruction ("Do not let the LLM directly receive
unrestricted DB access... use read-only constraints... do not allow
arbitrary destructive SQL"): this module never constructs SQL from user
input. It matches the query text against a small, fixed set of
pre-vetted, parameter-free SELECT statements (four of which are the
existing ``v_*`` views already defined in
``data/synthetic_enterprise/nexaconsult_enterprise.sql`` -- real,
reviewable, human-designed queries, not generated). "Validation" here
means the whitelist itself: only a template ever executes, so there is
no free-form SQL to parse or sanitize.

The connection is opened in SQLite's URI read-only mode
(``?mode=ro``) as a second, independent enforcement layer beyond "we
only ever hold SELECT strings" -- a write statement would fail at the
driver level even if a future bug introduced one into the template list.

See docs/ALGORITHMS/SQL_CAPABILITY.md and
docs/PROJECT_STATE/DECISIONS.md for why SQLite (not the main
ControlPlane Postgres instance) backs this specific capability's demo
data.
"""

from __future__ import annotations

import re
import sqlite3
import time
from functools import lru_cache

from controlplane.capabilities.sql_setup import DB_PATH, build_database

_STOPWORDS = {
    "the", "and", "of", "inc", "corp", "group", "global", "systems", "health", "energy", "logistics",
    "project", "platform", "upgrade", "modernization", "transformation", "redesign", "assessment", "core",
}

# Which output column a query-text entity match should filter on, per
# template -- lets one generic entity-match step (below) apply to every
# template without each needing its own bespoke filter logic.
_FILTERABLE_COLUMNS = {
    "active_project_team": {"project": "project_name", "client": "client_name"},
    "project_financials": {"project": "project_name", "client": "client_name"},
    "overdue_invoices": {"project": "project_name", "client": "client_name"},
    "client_directory": {"client": "name"},
}

_TEMPLATES: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("revenue", "recognized revenue", "how much revenue", "department revenue"),
        "SELECT department, service_line, period_start, period_end, total_revenue_usd, project_count "
        "FROM v_department_revenue_summary ORDER BY period_start DESC LIMIT 20",
        "department_revenue_summary",
    ),
    (
        ("utilization", "billable hours", "utilization target", "non-billable"),
        "SELECT employee_code, full_name, grade, title, department, total_billable_hours, "
        "total_non_billable_hours, utilization_target FROM v_employee_utilization "
        "ORDER BY total_billable_hours DESC LIMIT 20",
        "employee_utilization",
    ),
    (
        ("overdue", "unpaid invoice", "invoice status", "past due"),
        "SELECT invoice_number, client_name, project_name, issue_date, due_date, amount_usd, status, "
        "days_overdue FROM v_overdue_invoices ORDER BY days_overdue DESC LIMIT 20",
        "overdue_invoices",
    ),
    (
        ("project team", "who is staffed", "staffing", "allocation", "who is working on"),
        "SELECT project_code, project_name, client_name, employee_name, grade, role, allocation_pct, "
        "effective_daily_rate FROM v_active_project_team ORDER BY project_code LIMIT 30",
        "active_project_team",
    ),
    (
        ("budget", "contract value", "project financial", "actual spend", "budget consumed"),
        "SELECT project_code, project_name, client_name, status, contract_value_usd, budget_usd, "
        "actual_spend_usd, budget_consumed_pct, total_recognized_revenue FROM v_project_financials "
        "ORDER BY contract_value_usd DESC LIMIT 20",
        "project_financials",
    ),
]

_FALLBACK_SQL = (
    "SELECT id, name, industry, segment, region, country, status, annual_revenue_usd "
    "FROM clients ORDER BY annual_revenue_usd DESC LIMIT 15"
)
_FALLBACK_TEMPLATE = "client_directory"


class SQLCapability:
    name = "sql_v0_template_matched"

    def __init__(self) -> None:
        build_database()  # idempotent -- no-op if already built

    def _match_template(self, query_text: str) -> tuple[str, str]:
        q = query_text.lower()
        for keywords, sql, template_name in _TEMPLATES:
            if any(kw in q for kw in keywords):
                return sql, template_name
        return _FALLBACK_SQL, _FALLBACK_TEMPLATE

    @staticmethod
    @lru_cache(maxsize=1)
    def _entities() -> tuple[tuple[str, str], ...]:
        """[(kind, name)] for every project/client name in the database --
        cached, since these barely ever change and re-querying per
        request would be wasteful (this is metadata, not the answer
        itself)."""
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            entities = [("project", n) for (n,) in conn.execute("SELECT name FROM projects")]
            entities += [("client", n) for (n,) in conn.execute("SELECT name FROM clients")]
        finally:
            conn.close()
        return tuple(entities)

    def _match_entity(self, query_text: str) -> tuple[str, str] | None:
        """Naive single-token entity match (e.g. "TerraEnergy" in "Who is
        staffed on the TerraEnergy project?") -- not full entity linking.
        First match wins; ambiguous/ overlapping names are a known V0
        limitation, see docs/ALGORITHMS/SQL_CAPABILITY.md."""
        q_tokens = set(re.findall(r"[a-z]+", query_text.lower()))
        for kind, name in self._entities():
            name_tokens = [t for t in re.findall(r"[a-z]+", name.lower()) if t not in _STOPWORDS and len(t) > 3]
            if any(t in q_tokens for t in name_tokens):
                return kind, name
        return None

    def execute(self, query_text: str) -> dict:
        sql, template_name = self._match_template(query_text)
        params: tuple = ()

        entity = self._match_entity(query_text)
        if entity:
            kind, name = entity
            filter_col = _FILTERABLE_COLUMNS.get(template_name, {}).get(kind)
            if filter_col:
                sql = f"SELECT * FROM ({sql.rstrip(';')}) WHERE {filter_col} = ?"
                params = (name,)

        start = time.monotonic()
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        latency_ms = (time.monotonic() - start) * 1000

        return {
            "status": "EXECUTED",
            "template": template_name,
            "sql": sql,
            "entity_filter": {"kind": entity[0], "name": entity[1]} if entity else None,
            "row_count": len(rows),
            "rows": [dict(r) for r in rows],
            "latency_ms": latency_ms,
            "source": "nexaconsult_enterprise (synthetic demo data, SQLite, read-only)",
        }
