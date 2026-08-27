"""Capability Router + Model Router -- Milestone 3.

See docs/specs/CONTROLPLANE_ROUTING_SYSTEM_SPEC.md. Both routers are
pure functions of (QueryFingerprint, RiskProfile, PolicyDecision) -- no
model call, no DB access, no hidden state -- so every decision is cheap,
deterministic, and reproducible from its inputs (spec SS3: "risk
profiling and capability routing should be cheaper and faster than the
model they are deciding whether to call").
"""
