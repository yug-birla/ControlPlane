-- ==========================================================================
-- ControlPlane.ai — PostgreSQL Schema
-- Source: DATA_STRUCTURE/POSTGRES_SCHEMA.md
-- Covers: controlplane | enterprise_demo | evaluation schemas
-- Naming: snake_case, plural tables, id PK, <entity>_id FK, UTC timestamps
-- ==========================================================================

-- ── Schemas ────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS controlplane;
CREATE SCHEMA IF NOT EXISTS enterprise_demo;
CREATE SCHEMA IF NOT EXISTS evaluation;

-- ==========================================================================
-- SCHEMA: controlplane
-- ==========================================================================
SET search_path TO controlplane;

-- ── 3.1 requests ───────────────────────────────────────────────────────────
CREATE TABLE requests (
    id                UUID        PRIMARY KEY,
    trace_id          UUID        NOT NULL,
    session_id        UUID,
    application_id    TEXT,
    user_context_id   TEXT,
    query_text        TEXT,
    status            TEXT,
    policy_id         UUID,
    priority          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_requests_trace_id   ON requests(trace_id);
CREATE INDEX idx_requests_session_id ON requests(session_id);
CREATE INDEX idx_requests_created_at ON requests(created_at);

-- ── 3.2 query_profiles ─────────────────────────────────────────────────────
CREATE TABLE query_profiles (
    id                    UUID        PRIMARY KEY,
    request_id            UUID        NOT NULL REFERENCES requests(id),
    version               INTEGER     NOT NULL DEFAULT 1,
    intent                JSONB,
    domain                JSONB,
    data_requirements     JSONB,
    complexity            JSONB,
    sensitivity           JSONB,
    impact                JSONB,
    actionability         JSONB,
    risk_vector           JSONB,
    confidence            JSONB,
    source                TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_query_profiles_request_version ON query_profiles(request_id, version);

-- ── 3.3 execution_states ───────────────────────────────────────────────────
-- trajectory_id is the PK; current live state only (no event history here)
CREATE TABLE execution_states (
    trajectory_id           UUID        PRIMARY KEY,
    request_id              UUID        NOT NULL REFERENCES requests(id),
    current_plan_version_id UUID,
    current_node_id         UUID,
    status                  TEXT,
    risk_state              JSONB,
    confidence_state        JSONB,
    drift_state             JSONB,
    budget_state            JSONB,
    evidence_state          JSONB,
    active_capabilities     JSONB,
    active_tools            JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- PLANNING DOMAIN
-- ==========================================================================

-- ── 4.1 plans ──────────────────────────────────────────────────────────────
CREATE TABLE plans (
    id             UUID        PRIMARY KEY,
    request_id     UUID        NOT NULL REFERENCES requests(id),
    plan_type      TEXT,
    initial_reason JSONB,
    status         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_plans_request_id ON plans(request_id);

-- ── 4.2 plan_versions ──────────────────────────────────────────────────────
-- Never overwrite an old plan version — append only
CREATE TABLE plan_versions (
    id                  UUID        PRIMARY KEY,
    plan_id             UUID        NOT NULL REFERENCES plans(id),
    version             INTEGER     NOT NULL,
    parent_version_id   UUID,
    trigger_event_id    UUID,
    change_reason       JSONB,
    cost_budget         NUMERIC,
    latency_budget_ms   BIGINT,
    verification_level  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_plan_versions_plan_version ON plan_versions(plan_id, version);

-- ── 4.3 execution_nodes ────────────────────────────────────────────────────
-- Node lifecycle: PENDING | READY | RUNNING | COMPLETED | FAILED |
--                 SKIPPED | CANCELLED | WAITING_HUMAN
CREATE TABLE execution_nodes (
    id                    UUID        PRIMARY KEY,
    plan_version_id       UUID        NOT NULL REFERENCES plan_versions(id),
    node_key              TEXT,
    capability_id         UUID,
    node_type             TEXT,
    status                TEXT,
    dependency_definition JSONB,
    parallel_group        TEXT,
    input_contract        JSONB,
    output_contract       JSONB,
    retry_budget          INTEGER,
    timeout_ms            BIGINT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ
);

CREATE INDEX idx_execution_nodes_plan_status ON execution_nodes(plan_version_id, status);

-- ==========================================================================
-- ROUTING / CAPABILITY DOMAIN
-- ==========================================================================

-- ── 5.1 capability_registry ────────────────────────────────────────────────
CREATE TABLE capability_registry (
    id                    UUID        PRIMARY KEY,
    capability_key        TEXT        UNIQUE NOT NULL,
    type                  TEXT,
    description           TEXT,
    latency_class         TEXT,
    cost_class            TEXT,
    risk_class            TEXT,
    supports_parallel     BOOLEAN,
    requires_authorization BOOLEAN,
    input_schema          JSONB,
    output_schema         JSONB,
    availability_status   TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 5.2 model_registry ─────────────────────────────────────────────────────
-- Do NOT store API keys here
CREATE TABLE model_registry (
    id                  UUID        PRIMARY KEY,
    model_key           TEXT        UNIQUE NOT NULL,
    provider            TEXT,
    display_name        TEXT,
    capabilities        JSONB,
    context_window      INTEGER,
    latency_class       TEXT,
    cost_class          TEXT,
    reasoning_strength  TEXT,
    known_strengths     JSONB,
    known_weaknesses    JSONB,
    availability_status TEXT,
    version             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 5.3 route_registry ─────────────────────────────────────────────────────
CREATE TABLE route_registry (
    id                   UUID        PRIMARY KEY,
    route_key            TEXT        UNIQUE NOT NULL,
    route_type           TEXT,
    required_capabilities JSONB,
    allowed_models       JSONB,
    allowed_data_sources JSONB,
    risk_level           TEXT,
    verification_level   TEXT,
    cost_class           TEXT,
    latency_class        TEXT,
    supports_parallel    BOOLEAN,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- GOVERNANCE DOMAIN
-- ==========================================================================

-- ── 6.1 policies ───────────────────────────────────────────────────────────
-- Never overwrite an active policy version without preserving history
CREATE TABLE policies (
    id                   UUID        PRIMARY KEY,
    policy_key           TEXT        UNIQUE NOT NULL,
    application_id       TEXT,
    policy_type          TEXT,
    version              INTEGER     NOT NULL DEFAULT 1,
    rules                JSONB,
    risk_thresholds      JSONB,
    allowed_interventions JSONB,
    human_review_rules   JSONB,
    data_access_rules    JSONB,
    tool_rules           JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 6.2 decisions ──────────────────────────────────────────────────────────
-- Possible decisions: PASS | MONITOR | INTERVENE | ESCALATE | ABSTAIN |
--                     BLOCK | REPLAN | HUMAN_REVIEW
CREATE TABLE decisions (
    id                  UUID        PRIMARY KEY,
    request_id          UUID        NOT NULL REFERENCES requests(id),
    trajectory_id       UUID        NOT NULL REFERENCES execution_states(trajectory_id),
    plan_version_id     UUID,
    decision_type       TEXT,
    decision            TEXT,
    reason              JSONB,
    risk_snapshot       JSONB,
    confidence_snapshot JSONB,
    evidence_refs       JSONB,
    policy_id           UUID        REFERENCES policies(id),
    cost_snapshot       JSONB,
    latency_snapshot    JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_decisions_request_created ON decisions(request_id, created_at);

-- ── 6.3 interventions ──────────────────────────────────────────────────────
-- Intervention types: KEEP | VERIFY | RETRIEVE_MORE | RERANK | CHANGE_MODEL |
--   INCREASE_COMPUTE | DECREASE_COMPUTE | CHANGE_DATA_SOURCE | REGENERATE |
--   REPAIR | REDACT | ASK_CLARIFICATION | HUMAN_REVIEW | ABSTAIN | BLOCK
CREATE TABLE interventions (
    id                UUID        PRIMARY KEY,
    request_id        UUID        NOT NULL REFERENCES requests(id),
    trajectory_id     UUID        NOT NULL REFERENCES execution_states(trajectory_id),
    decision_id       UUID        NOT NULL REFERENCES decisions(id),
    intervention_type TEXT,
    target_node_id    UUID,
    reason            JSONB,
    expected_effect   JSONB,
    actual_effect     JSONB,
    status            TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_interventions_request_created ON interventions(request_id, created_at);

-- ==========================================================================
-- EVENT DOMAIN
-- ==========================================================================

-- ── 8.1 event_index ────────────────────────────────────────────────────────
CREATE TABLE event_index (
    id              UUID        PRIMARY KEY,
    event_type      TEXT,
    event_version   TEXT,
    request_id      UUID        NOT NULL REFERENCES requests(id),
    trace_id        TEXT,
    trajectory_id   UUID        NOT NULL REFERENCES execution_states(trajectory_id),
    plan_version_id UUID,
    node_id         UUID,
    source_type     TEXT,
    source_id       TEXT,
    severity        TEXT,
    observed_at     TIMESTAMPTZ NOT NULL,
    persisted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    causation_id    UUID,
    correlation_id  UUID,
    payload         JSONB,
    schema_version  TEXT
);

CREATE INDEX idx_event_index_request_observed ON event_index(request_id, observed_at);

-- ==========================================================================
-- TRAJECTORY DOMAIN
-- ==========================================================================

-- ── 9.1 trajectories ───────────────────────────────────────────────────────
CREATE TABLE trajectories (
    id                      UUID        PRIMARY KEY,
    request_id              UUID        NOT NULL REFERENCES requests(id),
    trajectory_type         TEXT,
    status                  TEXT,
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ,
    current_plan_version_id UUID,
    final_status            TEXT
);

-- ── 9.2 trajectory_steps ───────────────────────────────────────────────────
CREATE TABLE trajectory_steps (
    id              UUID        PRIMARY KEY,
    trajectory_id   UUID        NOT NULL REFERENCES trajectories(id),
    sequence_number INTEGER     NOT NULL,
    plan_version_id UUID,
    node_id         UUID,
    step_type       TEXT,
    actor_type      TEXT,
    actor_id        TEXT,
    input_ref       JSONB,
    output_ref      JSONB,
    status          TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- ==========================================================================
-- EXECUTION LEDGER  (append-only — never update or delete rows)
-- ==========================================================================

-- ── 10.1 execution_ledger ──────────────────────────────────────────────────
-- action_type examples: MODEL_INVOKED | DOCUMENT_ACCESSED | DATABASE_READ |
--   TOOL_PROPOSED | TOOL_AUTHORIZED | TOOL_DENIED | TOOL_EXECUTED |
--   EXTERNAL_ACTION | HUMAN_APPROVAL | DATA_TRANSFER | INTERVENTION
CREATE TABLE execution_ledger (
    id                   UUID        PRIMARY KEY,
    trajectory_id        UUID        NOT NULL REFERENCES trajectories(id),
    sequence_number      BIGINT      NOT NULL,
    occurred_at          TIMESTAMPTZ NOT NULL,
    actor_type           TEXT,
    actor_id             TEXT,
    action_type          TEXT,
    resource_type        TEXT,
    resource_id          TEXT,
    permission_used      TEXT,
    source               TEXT,
    destination          TEXT,
    authorization_result TEXT,
    consequence_class    TEXT,
    evidence_refs        JSONB,
    metadata             JSONB
);

-- ==========================================================================
-- COST / LATENCY
-- ==========================================================================

-- ── 11.1 execution_metrics ─────────────────────────────────────────────────
CREATE TABLE execution_metrics (
    id              UUID        PRIMARY KEY,
    request_id      UUID        NOT NULL REFERENCES requests(id),
    trajectory_id   UUID        NOT NULL REFERENCES trajectories(id),
    node_id         UUID,
    model_id        UUID,
    tool_id         TEXT,
    input_tokens    BIGINT,
    output_tokens   BIGINT,
    latency_ms      BIGINT      NOT NULL,
    estimated_cost  NUMERIC,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- SCHEMA: evaluation
-- ==========================================================================
SET search_path TO evaluation;

-- ── 7.1 evaluations ────────────────────────────────────────────────────────
-- evaluator_type: quality | factuality | grounding | reasoning | safety |
--   privacy | pii | bias | security | action_risk | consistency | rag_adequacy
CREATE TABLE evaluations (
    id                UUID        PRIMARY KEY,
    request_id        UUID        NOT NULL,
    trajectory_id     UUID        NOT NULL,
    node_id           UUID,
    evaluator_type    TEXT,
    algorithm_version TEXT,
    score             JSONB,
    confidence        JSONB,
    issues            JSONB,
    evidence_refs     JSONB,
    recommended_action TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_evaluations_request_created ON evaluations(request_id, created_at);

-- ── 7.2 trust_reports ──────────────────────────────────────────────────────
CREATE TABLE trust_reports (
    id                UUID        PRIMARY KEY,
    request_id        UUID        NOT NULL,
    trajectory_id     UUID        NOT NULL,
    trust_level       TEXT,
    supporting_signals JSONB,
    evidence_refs     JSONB,
    limitations       JSONB,
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 7.3 human_reviews ──────────────────────────────────────────────────────
-- decision: APPROVE | REJECT | MODIFY | ABSTAIN
CREATE TABLE human_reviews (
    id                    UUID        PRIMARY KEY,
    request_id            UUID        NOT NULL,
    trajectory_id         UUID        NOT NULL,
    review_type           TEXT,
    reviewer_id           TEXT,
    decision              TEXT,
    reason                TEXT,
    overridden_decision_id UUID,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 15. cases ──────────────────────────────────────────────────────────────
CREATE TABLE cases (
    id             UUID        PRIMARY KEY,
    case_type      TEXT,
    query          TEXT,
    domain         TEXT,
    source_dataset TEXT,
    split          TEXT,       -- TRAIN | VALIDATION | TEST | CHALLENGE
    difficulty     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 15. annotations ────────────────────────────────────────────────────────
-- Vocabulary from ANNOTATION_GUIDELINES.md v0.1
CREATE TABLE annotations (
    id                    UUID        PRIMARY KEY,
    case_id               UUID        NOT NULL REFERENCES cases(id),
    annotator_type        TEXT,       -- HUMAN | EXPERT | LLM_JUDGE | AUTOMATIC | SYNTHETIC | DERIVED
    correctness           TEXT,       -- CORRECT | MOSTLY_CORRECT | PARTIALLY_CORRECT | INCORRECT | NOT_ENOUGH_INFORMATION
    grounding             TEXT,       -- SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED | NOT_APPLICABLE
    safety                TEXT,       -- SAFE | POTENTIALLY_UNSAFE | UNSAFE
    privacy               TEXT,       -- NONE | POTENTIAL_PII | PII_EXPOSURE | SENSITIVE_DATA_EXPOSURE
    reasoning             TEXT,       -- VALID | MINOR_ERROR | MAJOR_ERROR | INVALID | NOT_APPLICABLE
    action_risk           TEXT,       -- NO_ACTION | LOW_RISK | MEDIUM_RISK | HIGH_RISK | CRITICAL
    preferred_intervention TEXT,      -- see ANNOTATION_GUIDELINES.md intervention list
    why                   TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 16. benchmark_runs ─────────────────────────────────────────────────────
CREATE TABLE benchmark_runs (
    id                UUID        PRIMARY KEY,
    benchmark_name    TEXT,
    dataset_version   TEXT,
    model_version     TEXT,
    algorithm_version TEXT,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    config            JSONB,
    results           JSONB
);

-- ==========================================================================
-- SCHEMA: enterprise_demo  (NexaConsult Global — Synthetic Company)
-- Table list from POSTGRES_SCHEMA.md §12:
--   departments, employees, clients (customers), projects, project_allocations,
--   revenue, timesheets (transactions), expenses, invoices, support_tickets,
--   okrs, performance_reviews, conversations, conversation_messages,
--   employee_skills, service_catalog
-- ==========================================================================
SET search_path TO enterprise_demo;

CREATE TABLE departments (
    id              UUID        PRIMARY KEY,
    name            TEXT        NOT NULL,
    service_line    TEXT        NOT NULL,
    practice        TEXT,
    region          TEXT        NOT NULL,
    head_employee_id UUID,
    cost_center     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE employees (
    id                  UUID        PRIMARY KEY,
    employee_code       TEXT        UNIQUE NOT NULL,
    first_name          TEXT        NOT NULL,
    last_name           TEXT        NOT NULL,
    email               TEXT        UNIQUE NOT NULL,
    phone               TEXT,
    grade               TEXT        NOT NULL,
    title               TEXT        NOT NULL,
    department_id       UUID        REFERENCES departments(id),
    manager_id          UUID,
    hire_date           DATE        NOT NULL,
    location_city       TEXT        NOT NULL,
    location_country    TEXT        NOT NULL,
    employment_type     TEXT        NOT NULL,
    base_salary         NUMERIC,
    currency            TEXT        DEFAULT 'USD',
    utilization_target  NUMERIC     DEFAULT 0.80,
    status              TEXT        DEFAULT 'ACTIVE',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE employee_skills (
    id             UUID        PRIMARY KEY,
    employee_id    UUID        NOT NULL REFERENCES employees(id),
    skill          TEXT        NOT NULL,
    category       TEXT        NOT NULL,
    proficiency    TEXT        NOT NULL,
    certified      BOOLEAN     DEFAULT FALSE,
    last_used_date DATE
);

CREATE TABLE clients (
    id                   UUID        PRIMARY KEY,
    client_code          TEXT        UNIQUE NOT NULL,
    name                 TEXT        NOT NULL,
    industry             TEXT        NOT NULL,
    segment              TEXT        NOT NULL,
    region               TEXT        NOT NULL,
    country              TEXT        NOT NULL,
    account_owner_id     UUID        REFERENCES employees(id),
    annual_revenue_usd   NUMERIC,
    relationship_start   DATE,
    status               TEXT        DEFAULT 'ACTIVE',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE projects (
    id                  UUID        PRIMARY KEY,
    project_code        TEXT        UNIQUE NOT NULL,
    name                TEXT        NOT NULL,
    client_id           UUID        NOT NULL REFERENCES clients(id),
    department_id       UUID        REFERENCES departments(id),
    project_type        TEXT        NOT NULL,
    status              TEXT        NOT NULL,
    lead_employee_id    UUID        REFERENCES employees(id),
    start_date          DATE        NOT NULL,
    end_date            DATE,
    planned_end_date    DATE,
    contract_value_usd  NUMERIC,
    budget_usd          NUMERIC,
    actual_spend_usd    NUMERIC     DEFAULT 0,
    delivery_model      TEXT,
    region              TEXT,
    sow_reference       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE project_allocations (
    id              UUID        PRIMARY KEY,
    project_id      UUID        NOT NULL REFERENCES projects(id),
    employee_id     UUID        NOT NULL REFERENCES employees(id),
    role            TEXT        NOT NULL,
    allocation_pct  NUMERIC     NOT NULL,
    start_date      DATE        NOT NULL,
    end_date        DATE,
    billing_rate    NUMERIC,
    currency        TEXT        DEFAULT 'USD',
    status          TEXT        DEFAULT 'ACTIVE'
);

-- revenue: period_start + period_end + revenue_usd — §12/13
CREATE TABLE revenue (
    id              UUID        PRIMARY KEY,
    period_start    DATE        NOT NULL,
    period_end      DATE        NOT NULL,
    project_id      UUID        REFERENCES projects(id),
    department_id   UUID        REFERENCES departments(id),
    client_id       UUID        REFERENCES clients(id),
    revenue_usd     NUMERIC     NOT NULL,
    revenue_type    TEXT        NOT NULL,
    currency        TEXT        DEFAULT 'USD',
    fx_rate         NUMERIC     DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- transactions (timesheets) — §12
CREATE TABLE timesheets (
    id                  UUID        PRIMARY KEY,
    employee_id         UUID        NOT NULL REFERENCES employees(id),
    project_id          UUID        REFERENCES projects(id),
    week_start          DATE        NOT NULL,
    billable_hours      NUMERIC     DEFAULT 0,
    non_billable_hours  NUMERIC     DEFAULT 0,
    overtime_hours      NUMERIC     DEFAULT 0,
    status              TEXT        DEFAULT 'SUBMITTED',
    approved_by         UUID        REFERENCES employees(id),
    submitted_at        TIMESTAMPTZ,
    approved_at         TIMESTAMPTZ
);

CREATE TABLE expenses (
    id              UUID        PRIMARY KEY,
    employee_id     UUID        NOT NULL REFERENCES employees(id),
    project_id      UUID        REFERENCES projects(id),
    expense_date    DATE        NOT NULL,
    category        TEXT        NOT NULL,
    amount          NUMERIC     NOT NULL,
    currency        TEXT        DEFAULT 'USD',
    description     TEXT,
    status          TEXT        DEFAULT 'PENDING',
    approved_by     UUID        REFERENCES employees(id),
    reimbursed_at   TIMESTAMPTZ
);

CREATE TABLE invoices (
    id              UUID        PRIMARY KEY,
    invoice_number  TEXT        UNIQUE NOT NULL,
    client_id       UUID        NOT NULL REFERENCES clients(id),
    project_id      UUID        NOT NULL REFERENCES projects(id),
    issue_date      DATE        NOT NULL,
    due_date        DATE        NOT NULL,
    amount_usd      NUMERIC     NOT NULL,
    status          TEXT        DEFAULT 'SENT',
    paid_date       DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE support_tickets (
    id              UUID        PRIMARY KEY,
    ticket_number   TEXT        UNIQUE NOT NULL,
    raised_by_id    UUID        REFERENCES employees(id),
    assigned_to_id  UUID        REFERENCES employees(id),
    department_id   UUID        REFERENCES departments(id),
    project_id      UUID        REFERENCES projects(id),
    category        TEXT        NOT NULL,
    priority        TEXT        NOT NULL,
    subject         TEXT        NOT NULL,
    description     TEXT,
    status          TEXT        DEFAULT 'OPEN',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    sla_hours       INTEGER
);

CREATE TABLE okrs (
    id              UUID        PRIMARY KEY,
    period          TEXT        NOT NULL,
    department_id   UUID        REFERENCES departments(id),
    objective       TEXT        NOT NULL,
    key_result      TEXT        NOT NULL,
    target_value    NUMERIC,
    actual_value    NUMERIC,
    unit            TEXT,
    status          TEXT        DEFAULT 'ON_TRACK',
    owner_id        UUID        REFERENCES employees(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE performance_reviews (
    id               UUID        PRIMARY KEY,
    employee_id      UUID        NOT NULL REFERENCES employees(id),
    reviewer_id      UUID        NOT NULL REFERENCES employees(id),
    review_period    TEXT        NOT NULL,
    overall_rating   TEXT        NOT NULL,
    technical_score  INTEGER,
    delivery_score   INTEGER,
    leadership_score INTEGER,
    comments         TEXT,
    promotion_eligible BOOLEAN   DEFAULT FALSE,
    completed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- conversations — §14
CREATE TABLE conversations (
    id            UUID        PRIMARY KEY,
    client_id     UUID        REFERENCES clients(id),
    project_id    UUID        REFERENCES projects(id),
    employee_id   UUID        REFERENCES employees(id),
    channel       TEXT        NOT NULL,
    subject       TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at      TIMESTAMPTZ,
    access_level  TEXT        DEFAULT 'INTERNAL'
);

CREATE TABLE conversation_messages (
    id              UUID        PRIMARY KEY,
    conversation_id UUID        NOT NULL REFERENCES conversations(id),
    sender_type     TEXT        NOT NULL,
    sender_id       TEXT,
    message_text    TEXT        NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sensitivity     TEXT        DEFAULT 'NONE'
);

CREATE TABLE service_catalog (
    id            UUID        PRIMARY KEY,
    service_code  TEXT        UNIQUE NOT NULL,
    name          TEXT        NOT NULL,
    category      TEXT        NOT NULL,
    department_id UUID        REFERENCES departments(id),
    day_rate_usd  NUMERIC,
    description   TEXT,
    active        BOOLEAN     DEFAULT TRUE
);
