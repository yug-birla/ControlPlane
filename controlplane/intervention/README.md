# controlplane/intervention/

`InterventionEngine` converts a `ControlDecision` into a concrete `InterventionSpec` that the runtime can act on — re-retrieving with a wider `k`, changing the model role, generating a constrained response, or routing to human review. The engine just plans; `controlplane.runtime` actually executes the spec.

`RETRIEVE_MORE` widens retrieval `k` rather than reformulating the query with an LLM. That was a deliberate trade: query reformulation would require an extra model call, and widening `k` is fast and sufficient for the cases this prototype encounters. It is noted as a future improvement in `docs/PROJECT_STATE/DECISIONS.md`.
