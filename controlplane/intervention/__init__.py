"""Intervention Engine -- translates a ``ControlDecision`` into a
concrete, executable change to what happens next. Per
docs/architecture/RUNTIME_FLOW.md: "Do not merely write 'recommended
action = retry' without changing execution" -- ``controlplane.runtime``
actually re-runs the changed capability/model using the spec this
package produces; the Intervention Engine itself does not execute
anything (it stays a pure planning step, same separation as
``controlplane.routing``/``controlplane.execution``).
"""
