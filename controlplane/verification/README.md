# controlplane/verification/

`VerificationEngine` runs at the end of the control loop, after any intervention and replanning have completed. It decides whether the final response can be released (`VERIFIED`), released with caveats (`PARTIALLY_VERIFIED`), or must be held back (`NOT_VERIFIED` / `REJECTED`).

The main limitation right now: verification reads the same evaluator signals that the Decision Engine already read. There is no separate verifier model that independently reassesses the response. This is a known gap — a genuinely independent verification step would need its own evidence path — but building one was out of scope for this prototype. See `docs/ALGORITHMS/CONTROL_LOOP.md`.
