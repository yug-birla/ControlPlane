# ControlPlane Data Sources and Capabilities Definition

**Purpose:** This document formally defines the allowed values for `required_data_sources` and `required_capabilities` within the ControlPlane query schema. These definitions are derived directly from the system architecture and capability layers defined in `PRODUCT_THESIS_UPDATED.md`.

---

## 1. Required Data Sources

The following data sources represent the fundamental data systems and knowledge repositories that the ControlPlane can query to fulfill user intents. 

| Source ID | Description | Primary Use Cases |
| :--- | :--- | :--- |
| `SQL_DB` | Structured Relational Database | Quantitative enterprise truth, KPIs, transactional information, and analytics. Should be used when deterministic mathematical truth is required instead of LLM estimations. |
| `RAG_CORPUS` | Unstructured Knowledge Base | Internal policies, reports, PDFs, and enterprise documentation. Requires exposing retrieved sources, chunks, and evidence coverage. |
| `CHAT_DATABASE` | Conversational Records | Customer-support history, internal discussions, and team conversations. Enforces strict access restrictions and PII controls. |
| `MEMORY_STORE` | User Context and Preferences | Personal user preferences, long-term session context, and individualized conversation history. |
| `WEB_SEARCH` | External Internet Access | Current public information, real-time external knowledge, and time-sensitive facts not contained in internal databases. |
| `CONTROLPLANE_STATE` | ControlPlane System State | Internal state, trajectory ledger, and runtime context required by the ControlPlane to govern, replan, and perform further executions. |

*Note: When annotating or generating queries, a query might require multiple data sources (e.g., `["SQL_DB", "RAG_CORPUS"]`).*

---

## 2. Required Capabilities

Capabilities represent the computational, model-specific, or tool-based actions required to successfully execute a workflow. The ControlPlane routes queries to specific nodes based on their declared capability profiles (e.g., via the Model Context Protocol / MCP).

| Capability ID | Description | Primary Use Cases |
| :--- | :--- | :--- |
| `REASONING` | Advanced Logical Deduction | Complex problem-solving, multi-step logical deduction, dependency chain analysis, and evaluating strategic tradeoffs. |
| `CODING` | Code Generation and Analysis | Writing software scripts, refactoring existing code bases, debugging errors, and creating unit tests. |
| `FAST_EVALUATION` | Low-Latency / Low-Cost Checking | Quick routing decisions, simple intent classification, formatting output, and intermediate verification checks where speed is prioritized. |
| `LONG_CONTEXT` | Large Window Processing | Summarizing massive documents (like entire product manuals or large code repositories) that require deep context retention. |
| `MULTI_MODAL` | Mixed-Media Processing | Analyzing or generating images, charts, audio, or video files. |
| `AGENTIC_EXECUTION` | State-Changing Tool Use | Executing scripts, booking events, sending emails, or triggering API calls via MCP tools. |
| `HIGH_RELIABILITY` | Deterministic Execution | Fallback routes and compliance-heavy tasks that cannot tolerate hallucination (often routing away from LLMs entirely). |

*Note: Models and tools registered in the Model Capability Registry should broadcast which of these capabilities they support, allowing the planner to dynamically orchestrate them.*

---

## 3. Known Reconciliation Gap

The generated query-profile dataset (`data/raw/generated/query_profiles_large.json`) currently populates `required_data_sources` and `required_capabilities` with a much more granular, free-text vocabulary (e.g. `enterprise_hr_system`, `internal_policy_documents`, `analytical_reasoning`, `structured_data_query`) rather than the canonical, closed lists above. This is tracked as an open item in `DATASET_GAPS.md`; either the generated data should be remapped onto the canonical lists, or this document's lists should be extended to a two-level taxonomy (canonical category → granular value). Do not treat one as silently correcting the other without an explicit reconciliation pass.

## Version

v0.1 — Initial data sources and capabilities definition, derived from `PRODUCT_THESIS_UPDATED.md`.
