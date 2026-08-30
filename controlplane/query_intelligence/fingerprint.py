"""Query Fingerprint -- docs/architecture/PRODUCT_THESIS_UPDATED.md SS6,
implemented as the frozen `query_profiles` table (docs/DATA/POSTGRES_SCHEMA.md
SS3.2). Enum choices and where each comes from are documented per-field
below; where two existing docs disagreed, the reconciliation is recorded
in docs/PROJECT_STATE/DECISIONS.md, not silently picked here.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Intent(str, Enum):
    """docs/PRODUCT_THESIS_UPDATED.md SS6.1. No ground-truth label exists
    for this exact categorical scheme in the generated dataset (its
    `intent` field is a free-text description) -- see
    docs/EVALUATION/QUERY_PROFILER_RESULTS.md for why this field is not
    accuracy-evaluated this milestone."""

    INFORMATIONAL = "informational"
    FACTUAL_LOOKUP = "factual_lookup"
    SUMMARIZATION = "summarization"
    TRANSFORMATION = "transformation"
    GENERATION = "generation"
    ANALYTICAL = "analytical"
    REASONING = "reasoning"
    RECOMMENDATION = "recommendation"
    DECISION_SUPPORT = "decision_support"
    ACTION_REQUEST = "action_request"
    AGENTIC_WORKFLOW = "agentic_workflow"
    CONVERSATIONAL_PERSONAL = "conversational_personal"


class Complexity(str, Enum):
    """data/schemas/query_profile.schema.json."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Sensitivity(str, Enum):
    """data/schemas/query_profile.schema.json."""

    NONE = "NONE"
    POTENTIAL_PII = "POTENTIAL_PII"
    PII_EXPOSURE = "PII_EXPOSURE"
    SENSITIVE_DATA_EXPOSURE = "SENSITIVE_DATA_EXPOSURE"


class Ambiguity(str, Enum):
    """data/schemas/query_profile.schema.json."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Impact(str, Enum):
    """docs/PRODUCT_THESIS_UPDATED.md SS6.6 -- "separate from risk"."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Actionability(str, Enum):
    """The 7 values actually observed in the generated dataset
    (docs/DATA/SCHEMA.md "Currently Unspecified" note, resolved by
    observation during the 2026-08-27 documentation audit) -- there was
    no ratified enum before this milestone."""

    INFORMATIONAL = "informational"
    ANALYTICAL = "analytical"
    PROCEDURAL = "procedural"
    GENERATIVE = "generative"
    DECISIONAL = "decisional"
    AGENTIC = "agentic"
    PENDING_CLARIFICATION = "pending_clarification"


class DataRequirement(str, Enum):
    """docs/DATA/SOURCES_AND_CAPABILITIES.md SS1 -- the canonical,
    previously-unused vocabulary (generated data used a much more
    granular, unreconciled set instead -- see BLOCKERS.md B6). This
    profiler is the first code to actually emit the canonical values."""

    SQL_DB = "SQL_DB"
    RAG_CORPUS = "RAG_CORPUS"
    CHAT_DATABASE = "CHAT_DATABASE"
    MEMORY_STORE = "MEMORY_STORE"
    WEB_SEARCH = "WEB_SEARCH"
    CONTROLPLANE_STATE = "CONTROLPLANE_STATE"


class CapabilityHint(str, Enum):
    """Milestone 2 bootstrap SS7 and SS11 give two overlapping-but-not-
    identical lists (SS7 has CHAT_HISTORY and CODING but not
    MULTI_SOURCE; SS11 has MULTI_SOURCE but not CHAT_HISTORY/CODING).
    Reconciled as their union -- see docs/PROJECT_STATE/DECISIONS.md."""

    GENERAL = "GENERAL"
    RAG = "RAG"
    SQL = "SQL"
    MEMORY = "MEMORY"
    CHAT_HISTORY = "CHAT_HISTORY"
    WEB = "WEB"
    REASONING = "REASONING"
    CODING = "CODING"
    AGENT = "AGENT"
    MULTI_SOURCE = "MULTI_SOURCE"


class QueryFingerprint(BaseModel):
    intent: Intent
    domain: str | None = None
    data_requirement: list[DataRequirement] = Field(default_factory=list)
    complexity: Complexity
    sensitivity: Sensitivity
    ambiguity: Ambiguity
    impact: Impact
    actionability: Actionability
    capability_hints: list[CapabilityHint] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    """Per-field confidence, populated only where the producing method
    actually supports one (e.g. cosine similarity from the embedding
    k-NN baseline) -- never fabricated for rule-based fields."""
    explanation: dict[str, str] = Field(default_factory=dict)
    """Per-field one-line reason (e.g. "matched rule: refund/execute" or
    "nearest exemplar: QP-042, similarity=0.81") -- required by the
    bootstrap's "the baseline must be explainable". Populated for every
    field, including generic fallback defaults -- see
    ``high_confidence_fields`` for which of these are an actual trigger
    match versus a fallback heuristic."""
    high_confidence_fields: list[str] = Field(default_factory=list)
    """Fields where a specific rule/keyword actually fired (as opposed to
    a generic fallback like the word-count-based complexity default).
    ``HybridQueryProfiler`` only trusts the rules baseline's value for a
    field when it's listed here; otherwise it defers to the embedding
    k-NN baseline, since a generic rule-based default is not evidence
    that the rule "knows" the answer."""
    source: str = "rules"
    """"rules" | "embedding_knn" | "hybrid" -- which method actually
    produced this fingerprint's values, for the evaluation harness."""

    @model_validator(mode="after")
    def _actions_must_ask_for_the_agent_capability(self) -> "QueryFingerprint":
        """An AGENTIC query without ``CapabilityHint.AGENT`` is not a
        judgement call -- it is a self-contradictory fingerprint, and it
        was reachable.

        ``CapabilityRouter`` derives ``agent_selected`` from
        ``capability_hints``, never from ``actionability``. The rules
        baseline sets both together when an action keyword fires, so the
        coupling looked total. The k-NN baseline sets them
        INDEPENDENTLY: actionability comes from a majority vote over the
        neighbours' actionability labels, while hints come from a
        majority vote over their taxonomy labels. Nothing required the
        two votes to agree.

        Measured on the 135 held-out query profiles, five queries came
        out of the shipped profiler asserting an action and requesting
        no agent capability, among them:

            "Initiate an automated batch payout of $150,000 to all
             approved affiliate partners"   -> hints ['GENERAL']
            "Scan all public GitHub repositories in our organization
             for leaked API keys, revoke any"  -> hints ['GENERAL']

        Each was routed as plain generation: no actor node, so no
        ``AgentGate`` evaluation and no chain for ``CompositionGovernor``
        to inspect. The profiler had already reached the right
        conclusion; the conclusion simply never reached the component
        that acts on it.

        Enforced here rather than in ``HybridQueryProfiler`` so that the
        invalid state is unrepresentable for every profiler, including
        ones not yet written. This adds a hint; it never removes one,
        and it never changes ``actionability`` itself.
        """
        if (self.actionability is Actionability.AGENTIC
                and CapabilityHint.AGENT not in self.capability_hints):
            self.capability_hints = [
                *[h for h in self.capability_hints if h is not CapabilityHint.GENERAL],
                CapabilityHint.AGENT,
            ]
            self.explanation.setdefault(
                "capability_hints_coherence",
                "AGENT added: actionability is AGENTIC, which requires the agent path",
            )
        return self
