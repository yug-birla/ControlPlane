"""Baseline A: deterministic rule-based Query Profiler.

No model, no training data, no embeddings. Every decision traces to a
literal keyword match, so ``explanation`` always names the exact trigger.
This is the profiler's floor: high precision on the patterns it covers,
zero recall on anything it doesn't -- see docs/EVALUATION/QUERY_PROFILER_RESULTS.md
for the measured trade-off against Baseline B (embedding k-NN).
"""

from __future__ import annotations

import re

from controlplane.query_intelligence.fingerprint import (
    Actionability,
    Ambiguity,
    CapabilityHint,
    Complexity,
    DataRequirement,
    Impact,
    Intent,
    QueryFingerprint,
    Sensitivity,
)


def _has_any(query_lower: str, *keywords: str) -> str | None:
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", query_lower):
            return kw
    return None


# (keywords, data_requirement, capability_hints) -- checked in order, first
# match per category wins; a query may match multiple categories.
_DATA_SIGNALS: list[tuple[tuple[str, ...], DataRequirement, CapabilityHint]] = [
    (("revenue", "sales", "database", "table", "sql", "query the", "quarter", "q4", "q1", "q2", "q3"),
     DataRequirement.SQL_DB, CapabilityHint.SQL),
    (("policy", "according to", "handbook", "document", "manual", "guideline", "as stated in"),
     DataRequirement.RAG_CORPUS, CapabilityHint.RAG),
    (("previously", "last time", "you said", "we discussed", "earlier conversation", "remind me what"),
     DataRequirement.CHAT_DATABASE, CapabilityHint.CHAT_HISTORY),
    (("remember", "my preference", "i told you", "as i mentioned before"),
     DataRequirement.MEMORY_STORE, CapabilityHint.MEMORY),
    (("current", "latest news", "today's", "right now", "as of today"),
     DataRequirement.WEB_SEARCH, CapabilityHint.WEB),
]

_ACTION_KEYWORDS = (
    "refund", "delete", "send", "execute", "approve", "transfer", "cancel", "issue a", "process the",
    "truncate", "wipe", "purge",
)

# Milestone 7 finding (real end-to-end trace of the new AgentCapability
# hard-block, controlplane/capabilities/agent_capability.py): "Please
# drop the customers table from the database" never reached the AGENT
# capability at all -- "drop" wasn't in _ACTION_KEYWORDS, so the query
# was never even classified as agentic, and the carefully-built
# destructive-operation hard block downstream was structurally
# unreachable for this common phrasing. "drop" itself can't be a bare
# keyword the way "truncate"/"wipe"/"purge" safely are ("a drop in
# revenue," "price drop" are common non-destructive uses) -- this
# requires it to appear near a data-object noun, the same "don't trust
# bare keyword presence" lesson as _is_topic_reference above, applied to
# a different false-positive direction (this time avoiding a false
# NEGATIVE on a real safety-relevant phrase, not a false positive).
_DESTRUCTIVE_DROP_PATTERN = re.compile(
    r"\bdrop\b.{0,40}\b(table|database|schema|column|index|collection|records?|data)\b", re.IGNORECASE
)
_CODING_KEYWORDS = ("function", "python", "code", "script", "bug", "compile", "stack trace", "regex")
_REASONING_KEYWORDS = ("why", "explain", "analyze", "compare", "trade-off", "should we", "recommend", "evaluate whether")
_PII_KEYWORDS = ("ssn", "social security", "credit card", "date of birth", "home address", "phone number", "email address")

# Milestone 5 fix (found during the milestone's mandatory architecture
# audit, listed there as a named regression: "semantic actionability
# false-positive"): an action keyword immediately followed by one of
# these nouns is a topic/policy REFERENCE ("the refund policy", "our
# cancellation terms"), not a command to perform the action. Root cause
# (bootstrap SS4's error-driven checklist): a weak algorithm -- pure
# keyword presence cannot distinguish a verb usage from a noun-phrase
# usage of the same word -- not bad data or bad taxonomy. This is a
# targeted syntactic-position check, not a broader semantic model,
# consistent with keeping this baseline a zero-model baseline; see
# docs/ALGORITHMS/QUERY_PROFILER_BASELINE.md for why a full
# semantic/small-model upgrade was not attempted this milestone.
_TOPIC_REFERENCE_FOLLOWERS = (
    "policy", "policies", "document", "documents", "guideline", "guidelines",
    "terms", "procedure", "procedures", "rules", "form", "faq",
)


def _is_topic_reference(query_lower: str, keyword: str) -> bool:
    match = re.search(rf"\b{re.escape(keyword)}\b\s+(\w+)", query_lower)
    return bool(match and match.group(1) in _TOPIC_REFERENCE_FOLLOWERS)


# Milestone 9 fix (found by tracing the baseline-vs-ControlPlane
# dataset, not by a unit test): purely informational questions about a
# policy THRESHOLD were classified agentic and escalated to HIGH_RISK --
# "Above what wire transfer amount is dual authorization required?",
# "Within how many days can a subscription be cancelled for a pro-rated
# refund?", "How long must an outage last to qualify for a refund?".
# Each contains an action keyword ("transfer"/"cancel"/"refund") used as
# a NOUN or in the PASSIVE, not as a command. The result was a
# false-positive control action on a benign question -- over-control,
# which is a real usability cost, measured as
# ``control_rate_on_benign_cases`` in the end-to-end experiment.
#
# The discriminator is deliberately CONJUNCTIVE and biased toward
# keeping things agentic, because the dangerous direction here is the
# other one: turning a genuine action request into "informational" would
# be a safety false negative, which matters more than average accuracy.
# A query is only demoted when ALL THREE hold:
#
#   1. it asks about a quantity/condition ("what amount", "how long",
#      "how many days", "above what", ...)  -- a threshold question,
#   2. it contains no requester phrase ("can you", "please", "i need
#      you to", ...) -- nobody is being asked to do anything,
#   3. it does not open with an imperative action verb -- it is not a
#      command.
#
# These are grammatical properties, not domain vocabulary, so the rule
# generalizes across domains instead of needing a new keyword per policy
# area. Both directions are regression-tested in tests/test_query_profiler.py.
_THRESHOLD_QUESTION_PATTERN = re.compile(
    r"\b(above|below|over|under|within|after|before)\s+(what|how)\b"
    r"|\bwhat\s+(is|are|was)\s+the\s+(limit|maximum|minimum|threshold|amount|cap|allowance)\b"
    r"|\bhow\s+(long|much|many)\b"
    r"|\bwhat\s+\w*\s*(amount|threshold|limit|period|deadline)\b",
    re.IGNORECASE,
)

_REQUESTER_PHRASES = (
    "can you", "could you", "would you", "will you", "please", "i want you to",
    "i need you to", "go ahead and", "make sure you", "i'd like you to",
)


def _is_threshold_question(query_lower: str, keyword: str) -> bool:
    """True when an action keyword appears inside a question ABOUT a
    policy threshold rather than a request to perform the action."""
    if not _THRESHOLD_QUESTION_PATTERN.search(query_lower):
        return False
    if any(phrase in query_lower for phrase in _REQUESTER_PHRASES):
        return False
    # An imperative command opens with the action verb itself
    # ("Issue a refund...", "Cancel the subscription...", "Transfer
    # $40,000..."). Those must stay agentic.
    first_word = query_lower.strip().split()[0] if query_lower.strip() else ""
    if first_word and keyword.split()[0].startswith(first_word):
        return False
    return True


class RuleBasedQueryProfiler:
    name = "rules"

    def profile(self, query: str) -> QueryFingerprint:
        q = query.lower()
        data_requirement: list[DataRequirement] = []
        capability_hints: list[CapabilityHint] = []
        explanation: dict[str, str] = {}
        high_confidence: set[str] = set()

        for keywords, req, hint in _DATA_SIGNALS:
            hit = _has_any(q, *keywords)
            if hit:
                data_requirement.append(req)
                capability_hints.append(hint)
                explanation.setdefault("data_requirement", f"matched keyword {hit!r} -> {req.value}")
                high_confidence.add("data_requirement")

        intent = Intent.INFORMATIONAL
        actionability = Actionability.INFORMATIONAL
        impact = Impact.LOW

        action_hit = _has_any(q, *_ACTION_KEYWORDS)
        if action_hit and (_is_topic_reference(q, action_hit) or _is_threshold_question(q, action_hit)):
            action_hit = None
        destructive_drop_match = _DESTRUCTIVE_DROP_PATTERN.search(q)
        if action_hit or destructive_drop_match:
            intent = Intent.ACTION_REQUEST
            actionability = Actionability.AGENTIC
            impact = Impact.HIGH
            capability_hints.append(CapabilityHint.AGENT)
            trigger = action_hit or destructive_drop_match.group(0)
            explanation["intent"] = f"matched action keyword {trigger!r}"
            explanation["actionability"] = f"matched action keyword {trigger!r}"
            high_confidence.update({"intent", "actionability"})

        reasoning_hit = _has_any(q, *_REASONING_KEYWORDS)
        if reasoning_hit:
            if intent == Intent.INFORMATIONAL:
                intent = Intent.REASONING
                high_confidence.add("intent")
            capability_hints.append(CapabilityHint.REASONING)
            explanation.setdefault("intent", f"matched reasoning keyword {reasoning_hit!r}")

        coding_hit = _has_any(q, *_CODING_KEYWORDS)
        if coding_hit:
            capability_hints.append(CapabilityHint.CODING)
            explanation.setdefault("capability_hints", f"matched coding keyword {coding_hit!r}")

        sensitivity = Sensitivity.NONE
        pii_hit = _has_any(q, *_PII_KEYWORDS)
        if pii_hit:
            sensitivity = Sensitivity.POTENTIAL_PII
            explanation["sensitivity"] = f"matched PII keyword {pii_hit!r}"
            high_confidence.add("sensitivity")

        word_count = len(query.split())
        if word_count <= 8:
            complexity = Complexity.LOW
        elif word_count <= 20:
            complexity = Complexity.MEDIUM
        else:
            complexity = Complexity.HIGH
        # Word count is a weak, always-available heuristic, not a
        # confident trigger match -- HybridQueryProfiler should still
        # defer to embedding k-NN for this field. See fingerprint.py's
        # high_confidence_fields docstring.
        explanation.setdefault("complexity", f"word_count={word_count} (weak heuristic, not a confident trigger)")

        ambiguity = Ambiguity.HIGH if "?" not in query and word_count <= 4 else Ambiguity.LOW
        explanation.setdefault(
            "ambiguity",
            "short query with no question mark (weak heuristic, not a confident trigger)" if ambiguity == Ambiguity.HIGH else "default",
        )

        if not capability_hints:
            capability_hints = [CapabilityHint.GENERAL]
            explanation.setdefault("capability_hints", "no keyword rule matched -> GENERAL fallback")

        # dedupe while preserving order
        data_requirement = list(dict.fromkeys(data_requirement))
        capability_hints = list(dict.fromkeys(capability_hints))

        return QueryFingerprint(
            intent=intent,
            domain=None,
            data_requirement=data_requirement,
            complexity=complexity,
            sensitivity=sensitivity,
            ambiguity=ambiguity,
            impact=impact,
            actionability=actionability,
            capability_hints=capability_hints,
            confidence={},
            explanation=explanation,
            high_confidence_fields=sorted(high_confidence),
            source=self.name,
        )
