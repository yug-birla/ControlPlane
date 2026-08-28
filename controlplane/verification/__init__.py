"""Verification -- the final control-loop stage before a response is
released. Examines the (possibly post-intervention) Evaluation results
one more time and decides whether the answer may actually be presented
as final. Never labels a response VERIFIED without having actually run
this check (bootstrap: "Do not return an answer as verified when
verification did not happen")."""
