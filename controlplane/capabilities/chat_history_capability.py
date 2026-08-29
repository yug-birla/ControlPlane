"""Chat-history capability: decide WHICH prior turns are relevant, if any.

Milestone 11 (§27/§28). The architecture is explicit: *"Do not inject all
history into every prompt. ControlPlane should determine when history is
relevant."*

That instruction rules out both naive strategies:

- **Inject everything** wastes prompt budget, buries the relevant turns
  among noise, and -- measurably worse -- propagates PII, superseded
  policy values, and injections planted in earlier turns into a prompt
  where none of them belong.
- **Inject the last N turns** fails whenever the relevant context is
  older than the pleasantries that follow it (``CH-013`` in the dataset
  is exactly this trap).

MECHANISM. Two signals, deterministic first:

1. **Hard exclusions** come first, because they are safety properties
   rather than relevance ones. History containing a prompt injection, a
   standing action instruction, or sensitive data is not "less relevant"
   -- it must not be carried forward at all, however topically related
   it looks.
2. **Semantic relevance** for everything else: cosine similarity between
   the current query and each prior turn, using the embedding model this
   repo already uses. This is the same reasoning as corpus-affinity
   routing (Milestone 9): "is this turn about what I am now asking?" is a
   semantic question, and a keyword or recency rule cannot answer it.

WHAT THIS DELIBERATELY DOES NOT DO. It does not decide whether to *use*
the selected turns in a prompt, or what to do about a detected injection.
It reports relevance and hazards; ControlPlane decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Calibrated in controlplane/experiments/evaluate_chat_history.py against the
# labelled sessions. Set for RELEVANCE utility alone, which is only
# defensible because staleness/PII/injection are now HARD exclusions above
# rather than things this threshold was implicitly (and badly) suppressing.
# The first version used 0.45 to hold the hazard leak down, which collapsed
# turn-selection F1 to 0.271 -- using a relevance knob as a safety control
# cost both.
DEFAULT_RELEVANCE_THRESHOLD = 0.25

# Phrases that make history unsafe to carry forward regardless of topical
# relevance. Deliberately small: this is a fast pre-filter, and the real
# semantic injection detection is the k-NN detector reused below.
_STANDING_ACTION_MARKERS = (
    "from now on", "whenever i ask", "for the rest of this conversation",
    "always email", "always send", "remember for later", "here is some context for later",
)


@dataclass
class ChatHistoryResult:
    relevant_turn_ids: list[int] = field(default_factory=list)
    relevant_texts: list[str] = field(default_factory=list)
    history_is_relevant: bool = False
    excluded_reason: str | None = None
    contains_injection: bool = False
    contains_standing_action_instruction: bool = False
    contains_sensitive_data: bool = False
    history_is_stale: bool = False
    max_similarity: float = 0.0
    status: str = "EXECUTED"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "relevant_turn_ids": self.relevant_turn_ids,
            "history_is_relevant": self.history_is_relevant,
            "excluded_reason": self.excluded_reason,
            "contains_injection": self.contains_injection,
            "contains_standing_action_instruction": self.contains_standing_action_instruction,
            "contains_sensitive_data": self.contains_sensitive_data,
            "history_is_stale": self.history_is_stale,
            "max_similarity": round(self.max_similarity, 4),
            "relevant_turn_count": len(self.relevant_turn_ids),
        }


class ChatHistoryCapability:
    name = "chat_history_v1"

    def __init__(self, relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD) -> None:
        self._threshold = relevance_threshold

    def select(self, query: str, turns: list[dict]) -> ChatHistoryResult:
        """Choose the prior turns worth carrying forward for ``query``."""
        user_turns = [t for t in turns if t.get("role") == "user" and t.get("text") != query]
        prior = [t for t in turns if t.get("text") != query]
        if not prior:
            return ChatHistoryResult(history_is_relevant=False, excluded_reason="no prior turns")

        # --- 1. Hard exclusions: safety before relevance ---------------
        standing = [t for t in user_turns if _has_standing_action_instruction(t.get("text", ""))]
        if standing:
            return ChatHistoryResult(
                history_is_relevant=False,
                contains_standing_action_instruction=True,
                excluded_reason=(
                    "history contains a standing action instruction; carrying it forward "
                    "would let an earlier turn silently escalate a read-only query into an "
                    "action, so the whole history is withheld and ControlPlane is told why"
                ),
            )

        injection = _detect_injection([t.get("text", "") for t in user_turns])
        if injection:
            return ChatHistoryResult(
                history_is_relevant=False,
                contains_injection=True,
                excluded_reason=(
                    "history contains a prompt-injection attempt; an injection planted in an "
                    "earlier turn is invisible to a detector that only inspects the current query"
                ),
            )

        if _contains_pii([t.get("text", "") for t in prior]):
            return ChatHistoryResult(
                history_is_relevant=False,
                contains_sensitive_data=True,
                excluded_reason=(
                    "history contains personal or confidential identifiers; carrying it forward "
                    "would propagate them into a downstream prompt for no benefit"
                ),
            )

        if _is_superseded_by(query, [t.get("text", "") for t in prior]):
            return ChatHistoryResult(
                history_is_relevant=False,
                history_is_stale=True,
                excluded_reason=(
                    "the current query asks for CURRENT state while the history describes a "
                    "prior period or policy version; reusing it would produce a confidently "
                    "outdated answer"
                ),
            )

        # --- 2. Semantic relevance -------------------------------------
        try:
            similarities = _similarities(query, prior)
        except Exception:
            # Never fail a request because the embedding model is
            # unavailable -- degrade to "no history", which is the safe
            # direction: omitting context degrades an answer, whereas
            # injecting the wrong context can corrupt it.
            return ChatHistoryResult(
                history_is_relevant=False,
                excluded_reason="relevance model unavailable; history omitted rather than guessed",
                status="DEGRADED",
            )

        selected = [(t, s) for t, s in zip(prior, similarities) if s >= self._threshold]
        max_similarity = max(similarities) if similarities else 0.0

        if not selected:
            return ChatHistoryResult(
                history_is_relevant=False, max_similarity=max_similarity,
                excluded_reason=f"no prior turn reached the relevance threshold "
                                f"({max_similarity:.3f} < {self._threshold:.2f})",
            )

        return ChatHistoryResult(
            relevant_turn_ids=[t["turn_id"] for t, _ in selected],
            relevant_texts=[t.get("text", "") for t, _ in selected],
            history_is_relevant=True,
            max_similarity=max_similarity,
        )

    def execute(self, query: str, turns: list[dict] | None = None, **_kwargs) -> dict:
        """Capability-node entry point, matching the shape the other
        capabilities return so the MCP adapter needs no special case."""
        result = self.select(query, turns or [])
        return {**result.to_dict(), "chunks": [{"text": t} for t in result.relevant_texts]}


def _has_standing_action_instruction(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _STANDING_ACTION_MARKERS)


def _detect_injection(texts: list[str]) -> bool:
    """Reuse the existing two-layer injection evaluator rather than adding
    a third detector with its own thresholds to keep in sync."""
    from controlplane.evaluation.evaluators import EvaluationContext, PromptInjectionEvaluator

    evaluator = PromptInjectionEvaluator()
    for text in texts:
        result = evaluator.evaluate(EvaluationContext(query=text, answer=""))
        if result.label == "INJECTION_PATTERN_DETECTED":
            return True
    return False


def _similarities(query: str, turns: list[dict]) -> list[float]:
    import numpy as np

    from controlplane.rag.retrieval import _embedding_provider, cosine_similarity

    provider = _embedding_provider()
    query_vec = np.array(provider.embed(text=query).embedding, dtype=np.float32)
    scores = []
    for turn in turns:
        turn_vec = np.array(provider.embed(text=turn.get("text", "")).embedding, dtype=np.float32)
        scores.append(float(cosine_similarity(query_vec, turn_vec)))
    return scores


# Temporal markers. Staleness is a TEMPORAL property, not a semantic one:
# "Which projects were active last quarter?" is near-identical in meaning
# to "Which projects are active right now?", which is exactly why semantic
# similarity cannot catch it and a separate check is needed.
_PAST_MARKERS = (
    "last quarter", "last year", "last month", "previously", "at that time",
    "used to be", "back then", "2019", "2020", "2021", "2022", "2023",
    "under the 2023", "former", "prior policy", "old policy", "was active",
    "were active",
)
_CURRENT_MARKERS = (
    "current", "currently", "right now", "today", "now", "at present",
    "2024", "2025", "latest", "up to date", "these days",
)


def _is_superseded_by(query: str, prior_texts: list[str]) -> bool:
    """True when the query asks about CURRENT state and history describes
    a prior period/version."""
    q = query.lower()
    if not any(marker in q for marker in _CURRENT_MARKERS):
        return False
    joined = " ".join(prior_texts).lower()
    return any(marker in joined for marker in _PAST_MARKERS)


def _contains_pii(texts: list[str]) -> bool:
    """Reuse the existing privacy signal rather than adding a third
    PII detector with its own patterns to keep in sync."""
    from controlplane.query_intelligence.rules import RuleBasedQueryProfiler

    profiler = RuleBasedQueryProfiler()
    for text in texts:
        sensitivity = profiler.profile(text).sensitivity
        if getattr(sensitivity, "value", str(sensitivity)) not in ("NONE", "none"):
            return True
    return False
