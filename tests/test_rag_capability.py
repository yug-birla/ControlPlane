from controlplane.capabilities.rag_capability import RAGCapability


def test_execute_returns_evidence_and_adequacy():
    result = RAGCapability().execute("What is our refund policy for cancelled subscriptions?")
    assert result["status"] == "EXECUTED"
    assert result["retrieved_count"] > 0
    assert result["evidence"]
    assert result["adequacy"]["label"] in ("SUFFICIENT", "PARTIALLY_SUFFICIENT", "INSUFFICIENT", "CONFLICTING")


def test_execute_accepts_a_k_override_for_the_retry_path():
    """Regression: found via manual end-to-end validation of the RAG
    self-healing loop -- controlplane.intervention.engine's RETRIEVE_MORE
    mechanism calls ``execute(query, k=...)``, which originally raised
    TypeError because ``k`` wasn't a parameter at all."""
    default_result = RAGCapability(k=2).execute("What is the meal reimbursement limit?")
    widened_result = RAGCapability(k=2).execute("What is the meal reimbursement limit?", k=8)
    assert default_result["retrieved_count"] == 2
    assert widened_result["retrieved_count"] == 8
