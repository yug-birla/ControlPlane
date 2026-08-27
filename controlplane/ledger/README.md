# controlplane/ledger/

**Purpose:** the Execution Ledger — "append-only record of consequential execution facts" (`docs/architecture/TRAJECTORY_AND_LEDGER.md`). Rows are never updated or deleted by application code (`docs/DATA/POSTGRES_SCHEMA.md` §10.1: "If a correction is required, append a compensating record.").

## Interface

`ExecutionLedger.append(...)` (per-trajectory monotonic `sequence_number`, computed from `MAX(sequence_number)+1` at append time), `ExecutionLedger.get_by_trajectory(...)` (chronological). `ConsequenceClass` enum (`READ_ONLY`/`REVERSIBLE_WRITE`/`IRREVERSIBLE_WRITE`/`HIGH_IMPACT_ACTION`, from `docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md` §30).

## Dependencies

`controlplane/db/` (Postgres).

## Limitations

Sequence-number assignment is a read-then-write within one transaction, not a DB sequence/trigger — correct at current single-writer-per-trajectory scale, would need revisiting under concurrent writers to the same trajectory.

## Extension points

Every consequential fact a future layer introduces (tool calls, data access, human approvals, interventions) appends here using the `action_type` examples already listed in `docs/DATA/POSTGRES_SCHEMA.md` §10.1 — don't invent a second ledger.
