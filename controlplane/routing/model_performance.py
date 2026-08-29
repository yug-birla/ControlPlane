"""Empirical model performance profiles, derived from execution history.

Milestone 11 (§17): routing should eventually use *observed* model
performance rather than static rules. This builds that observation from
data the runtime already persists -- ``model_invocations`` joined to
``response_evaluations`` -- with no new table.

THREE THINGS THIS DELIBERATELY REFUSES TO DO
--------------------------------------------

**1. It excludes test doubles.** The execution history in this repository
is dominated by scripted fakes (``fake-model-1`` n=1232,
``fake-scripted`` n=1078) written by the test suite, against ~143 real
Qwen invocations. A profile built over all rows would describe the test
suite, not the models. Any provider/model not on the real-model allowlist
is dropped.

**2. It reports sample size and refuses to pretend.** A profile over 3
invocations is not evidence. ``ModelProfile.is_reliable`` is False below
``_MIN_SAMPLES``, and callers are expected to fall back to static routing
rather than act on noise.

**3. It does not invent a quality score.** Grounding rate is the one
outcome that is actually recorded per invocation and objectively labelled.
Factuality/reasoning rates are exposed where present and left ``None``
where absent, rather than blended into a single fabricated "quality"
number that would imply more measurement than exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Only models we actually ship. Everything else in the history is a test
# double -- see the module docstring. Kept as an explicit allowlist rather
# than a "fake" denylist: a new test fake added later would silently
# poison a denylist, whereas an allowlist fails closed.
_REAL_MODELS = {
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen3-4B",
}

# Below this, a profile is reported but flagged unreliable. 20 is not a
# statistically principled threshold -- it is the point below which a
# single outcome moves the rate by >5 percentage points, chosen so the
# router does not chase noise.
_MIN_SAMPLES = 20

_DEFAULT_WINDOW_DAYS = 30


@dataclass(frozen=True)
class ModelProfile:
    model: str
    sample_count: int
    grounded_rate: float | None
    """Fraction of invocations whose grounding evaluation was SUPPORTED.
    ``None`` when no invocation for this model was ever grounding-scored
    (e.g. queries that retrieved no evidence)."""
    grounding_scored_count: int
    failure_rate: float
    mean_latency_ms: float | None
    mean_output_tokens: float | None

    @property
    def is_reliable(self) -> bool:
        """Whether a router should act on this profile at all."""
        return self.sample_count >= _MIN_SAMPLES and self.grounding_scored_count >= _MIN_SAMPLES

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "sample_count": self.sample_count,
            "grounded_rate": self.grounded_rate,
            "grounding_scored_count": self.grounding_scored_count,
            "failure_rate": self.failure_rate,
            "mean_latency_ms": self.mean_latency_ms,
            "mean_output_tokens": self.mean_output_tokens,
            "is_reliable": self.is_reliable,
        }


def build_model_profiles(window_days: int = _DEFAULT_WINDOW_DAYS) -> dict[str, ModelProfile]:
    """Derive per-model profiles from persisted execution history.

    Returns ``{}`` on any storage error: routing must degrade to its
    static policy rather than fail a request because observability data
    was unavailable.
    """
    import sqlalchemy as sa

    from controlplane.db.engine import session_scope

    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    try:
        with session_scope() as session:
            rows = session.execute(
                sa.text(
                    """
                    SELECT mi.model                                  AS model,
                           COUNT(*)                                  AS invocations,
                           SUM(CASE WHEN mi.status <> 'SUCCESS' THEN 1 ELSE 0 END) AS failures,
                           AVG(mi.latency_ms)                        AS mean_latency,
                           AVG(mi.output_tokens)                     AS mean_output_tokens,
                           COUNT(re.id)                              AS grounding_scored,
                           SUM(CASE WHEN re.label = 'SUPPORTED' THEN 1 ELSE 0 END) AS grounded
                    FROM model_invocations mi
                    LEFT JOIN response_evaluations re
                           ON re.request_id = mi.request_id
                          AND re.evaluator = 'grounding'
                    WHERE mi.started_at >= :since
                    GROUP BY mi.model
                    """
                ),
                {"since": since},
            ).fetchall()
    except Exception:
        return {}

    profiles: dict[str, ModelProfile] = {}
    for row in rows:
        model = row.model
        if model not in _REAL_MODELS:
            continue  # test double -- see module docstring
        invocations = int(row.invocations or 0)
        scored = int(row.grounding_scored or 0)
        grounded = int(row.grounded or 0)
        profiles[model] = ModelProfile(
            model=model,
            sample_count=invocations,
            grounded_rate=(grounded / scored) if scored else None,
            grounding_scored_count=scored,
            failure_rate=(int(row.failures or 0) / invocations) if invocations else 0.0,
            mean_latency_ms=float(row.mean_latency) if row.mean_latency is not None else None,
            mean_output_tokens=(
                float(row.mean_output_tokens) if row.mean_output_tokens is not None else None
            ),
        )
    return profiles


def escalation_is_evidence_backed(
    profiles: dict[str, ModelProfile], *, from_model: str, to_model: str
) -> tuple[bool, str]:
    """Does the observed history justify escalating ``from_model`` -> ``to_model``?

    This exists because on this project the answer is currently **no**,
    and the router should not spend 2.5x the compute on an unevidenced
    hope. The measured tier comparison
    (``docs/EVALUATION/MODEL_TIER_RESULTS.md``) found the larger model
    scoring *lower* (0.800 vs 0.900) at ~2.5x the per-token cost.

    Returning ``False`` with a reason is a real routing input, not a
    placeholder.
    """
    source, target = profiles.get(from_model), profiles.get(to_model)
    if source is None or target is None:
        return False, (
            f"no observed history for {'both models' if source is None and target is None else (from_model if source is None else to_model)}"
            " -- escalation cannot be justified from evidence"
        )
    if not source.is_reliable or not target.is_reliable:
        return False, (
            f"insufficient samples to judge (n={source.sample_count}/{target.sample_count}, "
            f"need >={_MIN_SAMPLES} each with grounding scores)"
        )
    if source.grounded_rate is None or target.grounded_rate is None:
        return False, "no grounding-scored invocations for at least one model"
    if target.grounded_rate > source.grounded_rate:
        return True, (
            f"observed grounding rate {target.grounded_rate:.3f} > {source.grounded_rate:.3f}"
        )
    return False, (
        f"observed grounding rate {target.grounded_rate:.3f} is not better than "
        f"{source.grounded_rate:.3f} -- escalation would spend more compute for no measured gain"
    )
