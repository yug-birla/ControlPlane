# controlplane/ledger/

The execution ledger is an append-only record of consequential facts — tool calls, data reads, external actions, human approvals, interventions. Rows are never updated; if a correction is needed, a compensating record is appended. See `docs/architecture/TRAJECTORY_AND_LEDGER.md` and `docs/DATA/POSTGRES_SCHEMA.md` §10.

Sequence numbers are computed at append time as `MAX(sequence_number)+1` within one transaction. This works correctly at current single-writer-per-trajectory scale; it would need rethinking if multiple writers could touch the same trajectory concurrently.

Every consequential fact a future capability introduces (additional tool calls, approvals, interventions) uses the `action_type` values already in `docs/DATA/POSTGRES_SCHEMA.md` §10.1. There should be exactly one ledger.
