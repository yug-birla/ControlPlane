"""Response Evaluation layer -- modular evaluator interfaces
(docs/architecture/RUNTIME_FLOW.md's "Evaluation" stage). Each evaluator
answers one narrow question about a completed response; ControlPlane
(not the evaluator) decides what, if anything, to do about the result
(bootstrap: "the evaluator does not directly invoke an intervention
merely because its recommendation says so").

No Intervention Engine or Replanner exists yet (Layer 15-16) -- results
are recorded (``response_evaluations`` table, ``EVALUATION_COMPLETED``
event) for observability/the dashboard, not yet acted on.
"""
