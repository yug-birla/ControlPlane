# controlplane/trust/

`TrustEngine` is the last step before the response leaves the control loop. It takes the verification result, decision action, and risk profile and produces a `HIGH`/`MEDIUM`/`LOW` verdict with a stated reason. There is no invented confidence score here — the verdict follows deterministically from those three signals.

The engine is not persisted to its own table. Trust is a pure function of data that is already committed elsewhere, so storing it separately would just create a second copy that could drift. It is recomputed on read in `controlplane.runtime` and `controlplane.dashboard.queries`.

Currently only three signals feed into it. The architecture notes that evaluator agreement and model reliability could also contribute, but neither has a reliable metric yet. See `docs/ALGORITHMS/TRUST_LAYER.md`.
