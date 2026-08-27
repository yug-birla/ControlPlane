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

_ACTION_KEYWORDS = ("refund", "delete", "send", "execute", "approve", "transfer", "cancel", "issue a", "process the")
_CODING_KEYWORDS = ("function", "python", "code", "script", "bug", "compile", "stack trace", "regex")
_REASONING_KEYWORDS = ("why", "explain", "analyze", "compare", "trade-off", "should we", "recommend", "evaluate whether")
_PII_KEYWORDS = ("ssn", "social security", "credit card", "date of birth", "home address", "phone number", "email address")


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
        if action_hit:
            intent = Intent.ACTION_REQUEST
            actionability = Actionability.AGENTIC
            impact = Impact.HIGH
            capability_hints.append(CapabilityHint.AGENT)
            explanation["intent"] = f"matched action keyword {action_hit!r}"
            explanation["actionability"] = f"matched action keyword {action_hit!r}"
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
