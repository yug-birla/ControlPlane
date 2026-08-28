# SQL Capability

**Status:** IMPLEMENTED — V0 template-matched (Milestone 4, 2026-08-28)

## Problem

Replace the `MOCKED` SQL handler with a real, **safe** query capability against the NexaConsult synthetic enterprise data — without giving any LLM unrestricted database access (explicit bootstrap constraint).

## Architecture Location

`controlplane/capabilities/{sql_setup,sql_capability}.py`.

## Baseline: Template Matching, Not NL2SQL

Never constructs SQL from user input. Matches query text against 5 fixed, pre-vetted `SELECT` templates (4 of which are the existing `v_*` views already defined in `nexaconsult_enterprise.sql` — human-designed, reviewable, not generated) plus a fallback client directory. A single-token entity match (e.g. "TerraEnergy") wraps the matched template in a parameterized `WHERE project_name = ?` filter — parameterized, never string-concatenated. The SQLite connection opens in URI read-only mode (`?mode=ro`) as an independent second enforcement layer beyond "only SELECT strings exist."

## Why SQLite, Not the Main ControlPlane Postgres

`nexaconsult_enterprise.sql` is written in SQLite syntax (`PRAGMA`, `julianday('now')`) with real seed data; `docs/DATA/POSTGRES_SCHEMA.md`'s Postgres `enterprise_demo` schema (`init_postgres_schema.sql`) defines matching tables but ships **zero** `INSERT`/`COPY` statements. Rather than rewrite 580+ lines of SQLite-specific SQL and fabricate seed data, this uses the real, data-complete SQLite script as-is — demo data for one capability, entirely separate from ControlPlane's own operational state (still exclusively Postgres).

## Candidate Alternatives

- **General NL2SQL (LLM-generated SQL)** — explicitly rejected per bootstrap: "do not let the LLM directly receive unrestricted DB access." A full NL2SQL project with validation/sandboxing is a large undertaking better scoped as its own milestone if evidence shows the template approach is insufficient.
- **Rewriting the Postgres `enterprise_demo` schema with fabricated data** — rejected: fabricating data values purely to have "real" Postgres data would be dishonest; the existing SQLite data is real, designed data.

## Inputs / Outputs

Input: query text. Output: `{status, template, sql, entity_filter, row_count, rows, latency_ms, source}`.

## Dataset

`nexaconsult_enterprise.sql` — 16 tables, 5 views, real (if fictional) seed data for a synthetic consulting firm.

## Compute / Latency

SQLite, local, no network. Measured (manual + `docs/EVALUATION/CONTROL_LOOP_RESULTS.md`): 0-30ms per query.

## Failure Modes

No entity match → falls back to the generic (unfiltered) template rather than guessing. Ambiguous/overlapping entity names → first match wins (documented limitation, not entity-disambiguated).

## Result

5 real templates + entity filtering verified against 8+ manually-inspected queries (`tests/test_sql_capability.py`, manual traces) — correctly narrows to a specific project/client when named, correctly falls back otherwise.

## Final Decision

V0 adopted as the runtime default for the `SQL` capability node. Resolves `docs/PROJECT_STATE/BLOCKERS.md` B4 for this specific use (which enterprise dataset backs a real capability) without resolving the broader Postgres-schema-vs-CSV question, which remains open.

## Version

v1 — 2026-08-28.
