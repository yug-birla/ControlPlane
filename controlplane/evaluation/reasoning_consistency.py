"""Self-contradiction detection beyond a fixed polarity-phrase list.

WHY THIS EXISTS. ``ReasoningEvaluator`` checks a hand-written list of
adjacent polarity pairs ("is allowed" / "is not allowed"). Expanding the
reasoning dataset from 12 to 24 cases measured its real recall at
**0.167** -- it finds the easy case where both halves of a contradiction
sit next to each other and misses everything else. Spec §37 rules out
the obvious response ("do not fix it by adding more keyword rules") and
names the alternatives: claim extraction, semantic consistency,
entailment, numeric consistency, scope.

THREE FAILURE SHAPES THE KEYWORD LIST STRUCTURALLY CANNOT SEE:

  split polarity   "Contractors must complete the security module
                   before access is granted, though contractors are not
                   required to complete it." The two halves are a clause
                   apart, and in the worst cases ("needs HR sign-off" vs
                   "may authorise it on their own") there is no negation
                   token at all.

  numeric          "Managers must give 60 days notice. The required
                   notice for managers is 30 days." No polarity words
                   exist, so a polarity-pair check cannot fire even in
                   principle.

  scope            A universal claim followed by an in-scope exception
                   that denies it.

TWO INDEPENDENT DETECTORS, MEASURED SEPARATELY AND TOGETHER
(``controlplane/experiments/evaluate_reasoning_consistency.py``):

  NUMERIC   Deterministic. Extracts (value, unit, subject) claims and
            flags two claims that share a subject and unit but disagree
            on value. Deterministic is the right tool here: numeric
            disagreement is exact, not a judgement call.

  ENTAILMENT  ``google/flan-t5-base``, already in the local cache -- no
            new download, no fine-tuning, CPU-feasible. FLAN's training
            mixture includes MNLI/RTE/ANLI, so it answers a
            contradiction question zero-shot. This is the same "reuse
            the smallest already-validated local model" pattern used for
            the injection k-NN.

WHAT MAKES THIS HARD, AND WHY THE FALSE-POSITIVE GUARDS MATTER MORE THAN
THE POSITIVE CASES. Most real answers that *look* contradictory are
correctly scoped: "Vendors are not paid before delivery under standard
terms, but prepayment is permitted for contracts under $2,000." Both a
naive polarity check and an off-the-shelf NLI model call that a
contradiction. A detector that flags every qualified statement would
score well on the contradiction cases and be unusable in the live suite,
where it would drive exactly the over-control this project just spent a
milestone reducing. The dev split is therefore majority
NOT_CONTRADICTORY by design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

_CLAUSE_SPLIT = re.compile(
    r"(?:(?<=[.!?])\s+)|(?:[;]\s*)|(?:,\s+(?:and|but|though|although|while|whereas|yet|so)\s+)|"
    r"(?:\s+(?:however|nevertheless|whereas)\s*,?\s+)",
    re.IGNORECASE,
)

# Units are matched as written, then normalised, so "$12,000" and
# "12000 dollars" compare equal and "30 days" never compares against
# "30 hours".
_UNIT_ALIASES = {
    "$": "currency", "usd": "currency", "dollar": "currency", "dollars": "currency",
    "day": "day", "days": "day", "month": "month", "months": "month",
    "year": "year", "years": "year", "hour": "hour", "hours": "hour",
    "minute": "minute", "minutes": "minute", "week": "week", "weeks": "week",
    "%": "percent", "percent": "percent", "character": "character", "characters": "character",
    "attempt": "attempt", "attempts": "attempt", "approval": "approval", "approvals": "approval",
}

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_CURRENCY_CLAIM = re.compile(rf"\$\s*({_NUMBER})\s*(k|m)?\b", re.IGNORECASE)
_UNIT_CLAIM = re.compile(rf"({_NUMBER})\s*(-|\s)?\s*([A-Za-z%]+)", re.IGNORECASE)

_STOPWORDS = frozenset("""
a an the of for to in on at by with and or but is are was were be been being
this that these those it its as from any all each per than then so such
must may can could should would will shall do does did not no non
""".split())


@dataclass
class NumericClaim:
    value: float
    unit: str
    subject: frozenset[str]
    text: str


@dataclass
class ConsistencyFinding:
    kind: str  # "NUMERIC" | "ENTAILMENT"
    detail: str
    evidence: tuple[str, str]


@dataclass
class ConsistencyReport:
    contradictory: bool
    findings: list[ConsistencyFinding] = field(default_factory=list)


def split_clauses(text: str) -> list[str]:
    """Sentence split, plus splitting on the coordinating conjunctions
    that carry contrast. The split-polarity cases put both halves of a
    contradiction inside ONE sentence joined by "and"/"though", so
    sentence splitting alone leaves them invisible."""
    parts = [p.strip(" ,;") for p in _CLAUSE_SPLIT.split(text) if p and p.strip(" ,;")]
    return [p for p in parts if len(p.split()) >= 3]


def _content_words(clause: str) -> frozenset[str]:
    words = re.findall(r"[a-z]+", clause.lower())
    # Crude singularisation, enough to make "contractors"/"contractor"
    # and "engineers"/"engineering" share a stem. A real stemmer would
    # be better; this is deliberately dependency-free and is measured,
    # not assumed adequate.
    stems = {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words}
    return frozenset(s for s in stems if s not in _STOPWORDS and len(s) > 2)


def extract_numeric_claims(clause: str) -> list[NumericClaim]:
    subject = _content_words(clause)
    claims: list[NumericClaim] = []
    consumed: list[tuple[int, int]] = []

    for m in _CURRENCY_CLAIM.finditer(clause):
        value = float(m.group(1).replace(",", ""))
        if (m.group(2) or "").lower() == "k":
            value *= 1_000
        elif (m.group(2) or "").lower() == "m":
            value *= 1_000_000
        claims.append(NumericClaim(value, "currency", subject, m.group(0)))
        consumed.append(m.span())

    for m in _UNIT_CLAIM.finditer(clause):
        if any(start <= m.start() < end for start, end in consumed):
            continue
        unit = _UNIT_ALIASES.get(m.group(3).lower())
        if unit is None:
            continue
        claims.append(NumericClaim(float(m.group(1).replace(",", "")), unit, subject, m.group(0)))
    return claims


def _subject_overlap(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def check_numeric_consistency(text: str, overlap_threshold: float = 0.25) -> list[ConsistencyFinding]:
    """Two claims that share a subject and a unit but disagree on value.

    ``overlap_threshold`` guards the case this check would otherwise get
    wrong constantly: an answer legitimately containing several
    different numbers about *different* subjects ("a six-month contract
    requires 30 days notice, which is half the 60 days required for
    annual contracts"). Requiring the two clauses to be ABOUT the same
    thing is what separates a contradiction from an ordinary comparison.

    0.25 was chosen on the DEV split alone (never on the held-out test
    set). It is not a knife edge: every value from 0.15 to 0.28 gives
    the identical result -- 2 of 11 contradictions caught and ZERO false
    positives across all 13 consistent cases, including the three
    guards specifically built to break this check (different-subject
    numbers, identical boundary numbers, and multi-role numbers). Above
    0.30 the check silently stops firing at all.

    Recall of 0.182 is low and is reported as such. This check exists to
    cover the numeric shape that a polarity-pair list cannot see even in
    principle; the remaining contradictions are semantic and are the
    entailment layer's job.
    """
    claims_by_clause = [extract_numeric_claims(c) for c in split_clauses(text)]
    findings: list[ConsistencyFinding] = []
    flat = [(i, c) for i, claims in enumerate(claims_by_clause) for c in claims]

    for idx, (i, first) in enumerate(flat):
        for j, second in flat[idx + 1:]:
            if i == j or first.unit != second.unit or first.value == second.value:
                continue
            if _subject_overlap(first.subject, second.subject) < overlap_threshold:
                continue
            findings.append(ConsistencyFinding(
                kind="NUMERIC",
                detail=f"same subject and unit, conflicting values: {first.text} vs {second.text}",
                evidence=(first.text, second.text),
            ))
    return findings


@lru_cache(maxsize=1)
def _entailment_model():
    """``google/flan-t5-base`` from the local cache. Loaded lazily and
    once per process: this is a live-suite evaluator, so paying the load
    cost per request would be unacceptable."""
    import os

    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    repo = "google/flan-t5-base"
    kwargs = {"local_files_only": True} if not os.environ.get("CONTROLPLANE_ALLOW_DOWNLOAD") else {}
    tokenizer = AutoTokenizer.from_pretrained(repo, **kwargs)
    model = AutoModelForSeq2SeqLM.from_pretrained(repo, **kwargs)
    model.eval()
    return tokenizer, model


_NLI_PROMPT = (
    "Read the two statements. They come from the same answer about the same company policy.\n"
    'Statement 1: "{a}"\n'
    'Statement 2: "{b}"\n'
    "If the two statements cannot both be true about the same case, answer contradiction. "
    "If they are about different cases, different conditions, or different things, answer consistent.\n"
    "Answer contradiction or consistent."
)


def check_entailment_consistency(text: str, max_pairs: int = 12) -> list[ConsistencyFinding]:
    """Pairwise contradiction check over clauses using the local FLAN
    model. ``max_pairs`` bounds the cost: clause pairs grow
    quadratically and this runs inside a live request."""
    clauses = split_clauses(text)
    if len(clauses) < 2:
        return []

    import torch

    tokenizer, model = _entailment_model()
    findings: list[ConsistencyFinding] = []
    pairs = [(a, b) for i, a in enumerate(clauses) for b in clauses[i + 1:]][:max_pairs]
    if not pairs:
        return []

    prompts = [_NLI_PROMPT.format(a=a, b=b) for a, b in pairs]
    inputs = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=256)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=5, do_sample=False)
    answers = tokenizer.batch_decode(outputs, skip_special_tokens=True)

    for (a, b), answer in zip(pairs, answers):
        if "contradict" in answer.strip().lower():
            findings.append(ConsistencyFinding(
                kind="ENTAILMENT",
                detail=f"clauses cannot both hold: {a!r} vs {b!r}",
                evidence=(a, b),
            ))
    return findings


def analyse(text: str, use_numeric: bool = True, use_entailment: bool = True) -> ConsistencyReport:
    findings: list[ConsistencyFinding] = []
    if use_numeric:
        findings.extend(check_numeric_consistency(text))
    if use_entailment:
        findings.extend(check_entailment_consistency(text))
    return ConsistencyReport(contradictory=bool(findings), findings=findings)
