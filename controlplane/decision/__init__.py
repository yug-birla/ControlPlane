"""Decision Engine -- the control-loop stage that answers "given the
evaluated response, should ControlPlane continue, intervene, or stop?"
(docs/architecture/RUNTIME_FLOW.md's "Decide" stage). Consumes
Evaluation layer results; produces a structured ``ControlDecision`` that
``controlplane.intervention`` executes. The Decision Engine itself never
mutates execution state -- see docs/architecture/RUNTIME_FLOW.md SS2.1's
"evaluator does not directly invoke an intervention" principle, applied
one level up.
"""
