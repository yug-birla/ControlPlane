# controlplane/verification/

**Purpose:** the final control-loop stage — decides whether a (possibly post-intervention) response may actually be released as final. See `docs/ALGORITHMS/CONTROL_LOOP.md`.

## Interface

- `engine.py`: `VerificationStatus` (`VERIFIED`/`PARTIALLY_VERIFIED`/`NOT_VERIFIED`/`REJECTED`), `VerificationResult`, `VerificationEngine.verify(evaluation_results, decision) -> VerificationResult`.

## Dependencies

`controlplane.decision.engine`, `controlplane.evaluation.evaluators`.

## Limitations

Uses the same evaluator set the Decision Engine already read — no independent "verifier model" distinct from those signals yet.

## Extension points

A dedicated verifier model/capability would populate a new `EvaluationResult` this engine additionally checks, without changing its interface.
