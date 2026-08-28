"""Corpus-affinity RAG detection -- "should we retrieve?" answered by
"is there actually anything to retrieve?"

WHY THIS EXISTS (Milestone 9, measured P0 finding):

Through Milestone 8, ``CapabilityHint.RAG`` came from two mechanisms:
seven literal keywords ("policy", "handbook", "document", "manual",
"guideline", "according to", "as stated in"), plus whatever the
embedding k-NN profiler's nearest neighbours happened to vote for.

Measured RAG-hint recall on 19 hand-authored questions that ARE
answerable from the real 30-document corpus:

  keyword rule alone .................. 1/19 = 0.053
  the actual M8 runtime (hybrid) ..... 10/19 = 0.526
  with corpus affinity (M9) .......... 19/19 = 1.000

Both baseline figures are stated because they answer different
questions: 0.053 is what the *keyword mechanism* achieves, 0.526 is what
the *deployed system* achieved. Quoting only the former would overstate
the size of this fix.

The consequence was architectural, not cosmetic. No RAG hint means no
RAG node in the execution graph, which means no retrieval, which means
the generation prompt contains no evidence -- so for corpus-answerable
questions ControlPlane returned *literally the same answer as an
unmanaged model*, verified by direct comparison. ControlPlane's single
largest lever over a baseline was structurally unreachable for the exact
queries it exists to serve.

WHY NOT MORE KEYWORDS (the bootstrap's explicit anti-hardcoding rule):

The failing queries are "What is our hotel allowance per night?", "How
many days of paid sick leave?", "What is the home office equipment
stipend?". Patching these means adding "allowance", "stipend", "sick
leave", "reimbursement", "retention", "notice period", ... indefinitely,
and still failing on the next unseen phrasing. The representation itself
is insufficient: surface word matching cannot express "this question is
about internal company knowledge". That is a semantic property, so it
needs a semantic representation.

THE MECHANISM:

Embed the query with the embedding model this repo already uses, and
take its maximum cosine similarity against the already-cached embeddings
of the real corpus chunks (``controlplane.rag.ingestion.load_chunks``,
whose vectors are disk-cached and committed -- see
``controlplane.models.embedding_cache`` / BLOCKERS.md B9). If the corpus
contains something semantically close to the question, retrieval is
worth doing; if it does not, it isn't.

This reuses the existing embedding model and the existing corpus
embeddings: no new model, no new dataset, no new download. It is also
self-maintaining in a way a keyword list is not -- add a document to the
corpus and questions about it become routable automatically.

THRESHOLD: calibrated, not guessed -- see
``controlplane/experiments/evaluate_corpus_affinity.py`` for the grid
search, the positives/negatives used, and the held-out evaluation. The
calibration set is deliberately disjoint from the
``baseline_vs_controlplane_cases.json`` set that the end-to-end
experiment reports on, so the routing fix is never tuned on the data
used to claim the product win.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from controlplane.rag.ingestion import load_chunks

# Grid-search optimal (F1=0.981) on the calibration split described in
# the module docstring; NOT a guessed round number. Verified afterwards
# on the held-out baseline_vs_controlplane set, which was never used to
# select it: recall 0.947, precision 0.947, F1 0.947 -- against the
# keyword rule's recall 0.053 / F1 0.100 on the same held-out data.
DEFAULT_SIMILARITY_THRESHOLD = 0.41


@dataclass(frozen=True)
class CorpusAffinity:
    max_similarity: float
    nearest_document: str | None
    is_corpus_answerable: bool


class CorpusAffinityDetector:
    def __init__(self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> None:
        self._threshold = similarity_threshold
        self._chunks = load_chunks()

    @property
    def threshold(self) -> float:
        return self._threshold

    def assess(self, query: str) -> CorpusAffinity:
        if not self._chunks:
            return CorpusAffinity(max_similarity=0.0, nearest_document=None, is_corpus_answerable=False)

        # Deliberately the SAME query-embedding path the retriever itself
        # uses (controlplane.rag.retrieval), not a second one: the
        # affinity score must mean the same thing as the dense retrieval
        # score it is predicting the usefulness of. The disk embedding
        # cache is not used here -- it keys on a fixed reference set, and
        # live user queries are unbounded and novel by nature.
        import numpy as np

        from controlplane.rag.retrieval import _embedding_provider, cosine_similarity

        query_embedding = np.array(
            _embedding_provider().embed(text=query).embedding, dtype=np.float32
        )

        best_sim, best_doc = -1.0, None
        for chunk in self._chunks:
            sim = cosine_similarity(query_embedding, chunk.embedding)
            if sim > best_sim:
                best_sim, best_doc = float(sim), chunk.document_name

        return CorpusAffinity(
            max_similarity=best_sim,
            nearest_document=best_doc,
            is_corpus_answerable=best_sim >= self._threshold,
        )


@lru_cache(maxsize=1)
def get_corpus_affinity_detector() -> CorpusAffinityDetector:
    """Process-wide singleton -- loading and holding the corpus chunk
    embeddings once, same pattern as the other expensive resources in
    this repo (embedding provider, reranker, judge, k-NN detector)."""
    return CorpusAffinityDetector()
