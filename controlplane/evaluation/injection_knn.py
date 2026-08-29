"""Embedding k-NN prompt-injection detector -- built after a real,
measured failure: ``PromptInjectionEvaluator``'s fixed 18-phrase keyword
list scored 1.0 accuracy on this project's own 12 hand-authored cases,
then a 98.5% FALSE NEGATIVE RATE (recall=0.02) against the real, public
`deepset/prompt-injections` dataset (662 examples) -- exact-phrase
matching cannot generalize across the enormous paraphrase diversity of
real injection attempts ("forget all previous tasks" / "ignore all
preceding orders" / "now forget about all the previous information" all
mean the same thing but share almost no literal substring).

Per bootstrap SS9/SS10 ("do not depend primarily on fixed keywords for
semantic risk... move toward a small local model when the
representation is shown insufficient, retain deterministic hard
constraints, benchmark the improved approach"): this reuses the SAME
local embedding model already validated everywhere else in this project
(``all-MiniLM-L6-v2``) -- no new model download, no fine-tuning. It is a
frozen embedding function plus labeled reference data (majority-vote
k-NN), the same "no training step" pattern already established by
``controlplane.query_intelligence.knn_profiler``.

Reference set: the dataset's own TRAIN split (546 examples), plus 44
in-domain enterprise examples added in Milestone 15. Evaluated only
against held-out TEST splits -- using TRAIN examples as reference data
is not leakage precisely because k-NN's "model" IS that reference data
(same reasoning already applied to the Query Profiler's exemplar bank);
reporting an accuracy number on examples also used as neighbors would
be.

The in-domain half was added after a MEASURED failure, not on intuition:
see ``_load_enterprise_reference_examples`` for the root cause (deepset
injections are topical questions with an attack suffix, so their
embeddings encode topic rather than attack) and
``controlplane/experiments/evaluate_injection_domain_shift.py`` for the
2x2 experiment that adopted it and rejected the competing hypothesis.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from controlplane.models.embedding_cache import cached_embed_batch

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "injection_knn_embeddings.npz"
_REFERENCE_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "external" / "deepset_prompt_injections" / "prompt_injections_normalized.json"
)
_ENTERPRISE_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "generated" / "enterprise_injection_cases.json"
)


@dataclass(frozen=True)
class InjectionExample:
    text: str
    label: str  # "INJECTION_PATTERN_DETECTED" | "NO_PATTERN_DETECTED"
    embedding: np.ndarray


@dataclass
class InjectionKNNResult:
    label: str
    confidence: float
    """Fraction of the k nearest neighbors agreeing with ``label``."""
    nearest_examples: list[tuple[str, str, float]]
    """[(text, label, cosine_similarity), ...] for the k neighbors, for
    an auditable "why" -- never a black-box score alone."""


def _cosine_similarity_batch(query_embedding: np.ndarray, reference_embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(reference_embeddings, axis=1) * (np.linalg.norm(query_embedding) or 1e-9)
    norms = np.where(norms == 0, 1e-9, norms)
    return (reference_embeddings @ query_embedding) / norms


class EmbeddingKNNInjectionDetector:
    """``similarity_threshold`` (NEW -- found via a real end-to-end
    regression, not designed upfront): a real end-to-end test caught the
    original threshold-less version flagging a completely benign SQL
    query as an injection attempt, because plain k=5 majority-vote
    always returns *some* label even when every neighbor's cosine
    similarity is barely above 0.2 (near-orthogonal, not a meaningful
    semantic match). Below ``similarity_threshold`` the detector now
    abstains to the safe default (``NO_PATTERN_DETECTED``) regardless of
    the vote -- a k-NN "reject option."

    Default ``similarity_threshold=0.30`` is a deliberate choice, NOT the
    raw calibration-optimal value found by grid search on a held-out
    slice of TRAIN (0.20, calibration macro-F1 0.435 vs 0.419 at 0.30 --
    see ``controlplane/experiments/evaluate_injection_knn.py``). That
    calibration slice is drawn from the *same* dataset distribution as
    the reference set (deepset's casual-assistant-question collection
    style) -- it cannot reveal how a threshold behaves on ControlPlane's
    actual live traffic, which looks nothing like that (SQL/RAG/agent-
    tool queries). The exact false positive this guards against was
    real, not hypothetical: a benign SQL query's best-matching neighbor
    had cosine similarity 0.245 -- correctly rejected at 0.30, but would
    have been misclassified at the raw-optimal 0.20. 0.30 trades a small,
    measured amount of in-domain calibration performance for materially
    better protection against this project's actual out-of-domain query
    shapes -- a documented judgment call, not an arbitrary tweak."""

    name = "injection_knn_v0"

    def __init__(
        self,
        reference_examples: list[dict],
        k: int = 5,
        similarity_threshold: float = 0.30,
        cache_path: Path | None = None,
        vote: str = "uniform",
        margin: float | None = None,
        domain_thresholds: dict[str, float] | None = None,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._vote = vote
        self._margin = margin
        self._domain_thresholds = domain_thresholds
        from controlplane.models.local_hf_provider import MODEL_REVISION, LocalHFEmbeddingProvider

        self._k = k
        self._texts = [r["query"] for r in reference_examples]
        self._labels = [r["expected_label"] for r in reference_examples]

        def _compute(texts: list[str]) -> np.ndarray:
            provider = LocalHFEmbeddingProvider()
            results = provider.embed_batch(texts=texts)
            return np.array([res.embedding for res in results], dtype=np.float32)

        self._embeddings = cached_embed_batch(cache_path or _CACHE_PATH, MODEL_REVISION, self._texts, _compute)
        self._injection_mask = np.array([lab == "INJECTION_PATTERN_DETECTED" for lab in self._labels])
        self._domains = np.array([r.get("domain", "external") for r in reference_examples])
        self._provider = LocalHFEmbeddingProvider()

    def classify(self, query: str) -> InjectionKNNResult:
        q_embedding = np.array(self._provider.embed(text=query).embedding, dtype=np.float32)
        sims = _cosine_similarity_batch(q_embedding, self._embeddings)
        top_k_idx = np.argsort(sims)[::-1][: self._k]
        nearest = [(self._texts[i], self._labels[i], float(sims[i])) for i in top_k_idx]

        threshold = self._similarity_threshold
        if self._domain_thresholds:
            # DOMAIN-AWARE REJECT OPTION (H5 -- adopted on measured
            # evidence; see evaluate_injection_domain_shift).
            #
            # The reference set is two populations with different
            # similarity SCALES. Against the external deepset examples a
            # genuine match scores ~0.30-0.35; against the in-domain
            # enterprise examples a genuine match scores ~0.44-0.73,
            # because in-domain text shares far more surface vocabulary.
            # A single global threshold therefore cannot serve both: the
            # value that stops enterprise false positives (0.45)
            # suppresses real external detections (deepset recall
            # 0.600 -> 0.333), and the value that preserves external
            # recall (0.30) lets enterprise false positives through.
            # Every single-threshold configuration measured showed this
            # trade -- it is a property of the data, not of the tuning.
            #
            # So the threshold is chosen by which population this query
            # actually resembles, and each population keeps the
            # threshold calibrated for it.
            nearest_domain = self._domains[int(np.argmax(sims))]
            threshold = self._domain_thresholds.get(str(nearest_domain), self._similarity_threshold)

        if nearest[0][2] < threshold:
            # Reject option: nothing in the reference set is actually
            # close to this query -- a majority vote among barely-related
            # neighbors is noise, not signal. Default to the safe label.
            return InjectionKNNResult(label="NO_PATTERN_DETECTED", confidence=0.0, nearest_examples=nearest)

        if self._margin is not None:
            # BEST-OF-CLASS MARGIN RULE (H3). A counted vote among k
            # neighbors is unreliable here for a structural reason that
            # was measured twice: injection examples are usually
            # ordinary topical text with an attack appended, so their
            # embeddings encode TOPIC. Any query on a well-represented
            # topic therefore collects several mediocre injection
            # neighbors, which outvote a single much closer benign one
            # -- 0.443 benign lost 2-3 to injections at 0.382/0.371/0.360.
            #
            # This rule compares only the single best example of each
            # class, over the whole reference set rather than the top k,
            # and fires only when the injection side wins by ``margin``.
            # Being outnumbered stops mattering; being closer is what
            # matters.
            mask = self._injection_mask
            best_inj = float(sims[mask].max()) if mask.any() else -1.0
            best_benign = float(sims[~mask].max()) if (~mask).any() else -1.0
            if best_inj >= threshold and best_inj - best_benign > self._margin:
                return InjectionKNNResult(
                    label="INJECTION_PATTERN_DETECTED",
                    confidence=min(1.0, (best_inj - best_benign) / max(self._margin, 1e-9)),
                    nearest_examples=nearest,
                )
            return InjectionKNNResult(label="NO_PATTERN_DETECTED", confidence=0.0, nearest_examples=nearest)

        if self._vote == "similarity":
            # Similarity-weighted vote. Motivated by a real observed
            # failure mode, not by preference: on the enterprise query
            # "An expense of $12,000 needs approval..." the NEAREST
            # neighbor was benign (0.342) yet three weaker neighbors
            # (0.310/0.265/0.219) outvoted it 3-2 under a uniform count.
            # Weighting by similarity makes a closer neighbor count for
            # more than a barely-related one.
            #
            # MEASURED AND NOT ADOPTED. In the 2x2 of
            # evaluate_injection_domain_shift it changed NO metric on
            # either held-out set, and did not fix the query that
            # motivated it (weighted INJECTION 0.794 still beats
            # weighted benign 0.618). Kept only so that negative result
            # stays reproducible; the default remains "uniform".
            weights: Counter = Counter()
            for _, lab, sim in nearest:
                weights[lab] += max(sim, 0.0)
            label, weight = weights.most_common(1)[0]
            total = sum(weights.values()) or 1e-9
            return InjectionKNNResult(label=label, confidence=weight / total, nearest_examples=nearest)

        neighbor_labels = [self._labels[i] for i in top_k_idx]
        vote = Counter(neighbor_labels)
        label, count = vote.most_common(1)[0]
        confidence = count / self._k
        return InjectionKNNResult(label=label, confidence=confidence, nearest_examples=nearest)


def _load_enterprise_reference_examples() -> list[dict]:
    """The in-domain half of the reference set (44 examples: 22 benign
    enterprise queries, 22 enterprise-phrased attacks).

    WHY THIS EXISTS. The deepset reference set is a collection of casual
    consumer questions, and 51% of its injection examples are built by
    appending an attack suffix to an otherwise ordinary topical
    question. The sentence embedding of such an example is dominated by
    its TOPIC, not by the attack. Consequence, measured on the 62-case
    baseline benchmark: two legitimate enterprise finance queries
    matched finance-topic deepset injections at cosine 0.342/0.345 and
    were classified INJECTION_PATTERN_DETECTED, pushing correct answers
    to HUMAN_REVIEW. The reference set simply contained no examples of
    what this system's real traffic looks like.

    The 22 attack examples are as important as the 22 benign ones: a
    reference set given only benign in-domain data would learn
    "enterprise phrasing => safe" and go blind to enterprise-phrased
    attacks. Both classes are in-domain, so the discriminating signal
    has to be the attack, not the topic.

    Only the ``reference`` split is loaded here. The ``test`` split (20
    examples) is held out for evaluation, and the two queries that
    exposed the bug (BVC-060/BVC-062) are in NEITHER split -- they stay
    an untouched end-to-end check, so this is not tuning on the test
    set."""
    if not _ENTERPRISE_REFERENCE_PATH.exists():
        raise FileNotFoundError(f"{_ENTERPRISE_REFERENCE_PATH} does not exist")
    with open(_ENTERPRISE_REFERENCE_PATH, encoding="utf-8-sig") as f:
        records = json.load(f)
    return [r for r in records if r["split"] == "reference"]


def _load_train_reference_examples() -> list[dict]:
    """Only the dataset's own TRAIN split (546 examples) -- the TEST
    split (116) must stay held out for evaluation
    (``controlplane/experiments/evaluate_injection_knn.py``), never used
    as k-NN reference data, or that evaluation would be measuring
    accuracy against examples the detector had effectively already
    "seen." Raises with a clear message if the dataset hasn't been
    fetched yet (never silently falls back to an empty/fake reference
    set)."""
    if not _REFERENCE_DATA_PATH.exists():
        raise FileNotFoundError(
            f"{_REFERENCE_DATA_PATH} does not exist -- run "
            "python -m data.external.deepset_prompt_injections.fetch_and_normalize first"
        )
    with open(_REFERENCE_DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if r["split"] == "train"]


@lru_cache(maxsize=1)
def get_injection_knn_detector() -> EmbeddingKNNInjectionDetector:
    """Process-wide singleton (same pattern as
    ``controlplane.rag.retrieval._embedding_provider``/``_reranker``,
    ``controlplane.judge.local_judge.get_local_judge``) -- builds the
    546-example reference embedding set once per process, not once per
    ``Runtime``/``PromptInjectionEvaluator`` instance. Disk-cached
    (``cached_embed_batch``) so even the first build in a fresh process
    is fast after the very first run ever.

    ADOPTED 2026-08-29 (configuration C6 of six measured candidates in
    ``controlplane/experiments/evaluate_injection_domain_shift.py``):
    546 deepset TRAIN examples PLUS 44 in-domain enterprise examples,
    with a DOMAIN-AWARE reject threshold.

                              C0 (before)   C6 (adopted)
        deepset TEST    (116)     0.787         0.777    macro-F1
        enterprise TEST  (20)     0.798         0.899    macro-F1
        enterprise VAL   (16)     0.792         0.750    macro-F1
        live/regression queries    1/3           3/3

    WHAT WAS REJECTED, AND WHY IT MATTERS. Five other candidates were
    measured and discarded rather than quietly kept:

      similarity-weighted vote  changed no metric on any set
      best-of-class margin 0.15 deepset recall 0.600 -> 0.233
      k=31                      best on validation, then deepset
                                recall 0.600 -> 0.417 -- a small-sample
                                overfit caught only because the choice
                                was made on validation and scored once
                                on test
      global threshold 0.45     deepset recall 0.600 -> 0.333
      in-domain data alone      fixed the reported defect but broke two
                                existing control-loop tests

    HONEST COST. C6 is not free. It gives up one true positive on
    deepset TEST (60 injections, recall 0.600 -> 0.583), and on the
    deliberately adversarial validation split its precision drops (1 ->
    4 false positives) in exchange for catching every attack there
    (2 -> 0 false negatives). Those 4 residual false positives are a
    real, measured limit of an embedding-only representation: benign
    "what does the policy permit" queries and "skip the approval
    workflow" attacks are genuinely close in this vector space, and no
    threshold separates them. Improving that needs a better
    representation, not more tuning -- recorded in FUTURE_WORK."""
    return EmbeddingKNNInjectionDetector(
        _load_train_reference_examples() + _load_enterprise_reference_examples(),
        k=5,
        domain_thresholds={"external": 0.30, "enterprise": 0.45},
        cache_path=_CACHE_PATH.with_name("injection_knn_embeddings_with_domain.npz"),
    )
