"""Seeds ``model_registry`` with the models/roles this milestone actually
uses. Run once (idempotent -- upserts by ``model_key``):

    .venv/Scripts/python -m controlplane.models.registry_seed
"""

from __future__ import annotations

from sqlalchemy import select

from controlplane.db.engine import session_scope
from controlplane.db.models import ModelRegistryRecord, new_id
from controlplane.judge.local_judge import MODEL_REPO as JUDGE_MODEL_REPO
from controlplane.judge.local_judge import MODEL_REVISION as JUDGE_MODEL_REVISION
from controlplane.models.local_hf_provider import EMBEDDING_DIMENSION, MODEL_REPO, MODEL_REVISION
from controlplane.rag.reranker import MODEL_REPO as RERANKER_MODEL_REPO
from controlplane.rag.reranker import MODEL_REVISION as RERANKER_MODEL_REVISION

_ENTRIES = [
    dict(
        model_key="local_hf_all_minilm_l6_v2",
        provider="local_hf",
        source="huggingface",
        display_name="all-MiniLM-L6-v2 (local)",
        model_family="MiniLM",
        capabilities={"tasks": ["EMBEDDING"]},
        parameter_count=22_700_000,  # verified via file-size/fp32 math, see docs/ALGORITHMS/LOCAL_EMBEDDING_MODEL.md
        context_window=256,
        latency_class="fast",
        cost_class="free",
        local_or_remote="LOCAL",
        hardware_requirements={"ram_mb": 200, "disk_mb": 100, "gpu_required": False},
        license="apache-2.0",
        revision=MODEL_REVISION,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["fast CPU inference", "no API cost", "no network dependency at inference time"]},
        known_weaknesses={"notes": ["384-dim embeddings only", "256-token max sequence length", "no generation capability"]},
    ),
    dict(
        model_key="groq_configured_model",
        provider="groq",
        source="groq_api",
        display_name="Groq (model selected via GROQ_MODEL env var)",
        model_family=None,
        capabilities={"tasks": ["GENERATION"]},
        parameter_count=None,
        context_window=None,
        latency_class="fast",
        cost_class="metered",
        local_or_remote="REMOTE",
        hardware_requirements={},
        license=None,
        revision=None,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["low-latency hosted inference", "no local compute/RAM cost"]},
        known_weaknesses={
            "notes": [
                "requires network + GROQ_API_KEY",
                "per-token cost",
                "actual model/parameter_count/context_window vary by GROQ_MODEL and are not known until configured -- never hard-coded, see docs/PROJECT_STATE/DECISIONS.md",
            ]
        },
    ),
    dict(
        model_key="groq_fast_role",
        provider="groq",
        source="groq_api",
        display_name="Groq FAST role (model selected via GROQ_MODEL_FAST, falls back to GROQ_MODEL)",
        model_family=None,
        capabilities={"tasks": ["GENERATION"], "router_role": "FAST"},
        parameter_count=None,
        context_window=None,
        latency_class="fast",
        cost_class="metered",
        local_or_remote="REMOTE",
        hardware_requirements={},
        license=None,
        revision=None,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["Model Router's default for low complexity/low risk queries -- see controlplane/routing/model_router.py"]},
        known_weaknesses={
            "notes": [
                "same model as groq_configured_model unless GROQ_MODEL_FAST is set separately",
                "no local (non-network) FAST option yet -- the Qwen3 ~1.3B local tier from docs/architecture/MODEL_AND_EVALUATION_DECISIONS.md was deferred this milestone, see docs/PROJECT_STATE/DECISIONS.md",
                "latency_class/cost_class are ESTIMATES, not measurements -- no GROQ_API_KEY was available to benchmark this milestone",
            ]
        },
    ),
    dict(
        model_key="groq_strong_role",
        provider="groq",
        source="groq_api",
        display_name="Groq STRONG role (model selected via GROQ_MODEL_STRONG, falls back to GROQ_MODEL)",
        model_family=None,
        capabilities={"tasks": ["GENERATION"], "router_role": "STRONG"},
        parameter_count=None,
        context_window=None,
        latency_class="slow",
        cost_class="metered",
        local_or_remote="REMOTE",
        hardware_requirements={},
        license=None,
        revision=None,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["Model Router's choice for HIGH_RISK/CRITICAL_ACTION policy tiers, high impact, or high complexity -- see controlplane/routing/model_router.py"]},
        known_weaknesses={
            "notes": [
                "same model as groq_configured_model unless GROQ_MODEL_STRONG is set separately",
                "latency_class/cost_class are ESTIMATES, not measurements -- no GROQ_API_KEY was available to benchmark this milestone",
            ]
        },
    ),
    dict(
        model_key="local_cross_encoder_ms_marco_minilm_l6_v2",
        provider="local_hf",
        source="huggingface",
        display_name="cross-encoder/ms-marco-MiniLM-L-6-v2 (local, RAG reranker)",
        model_family="MiniLM",
        capabilities={"tasks": ["RERANKING"]},
        parameter_count=22_700_000,
        context_window=512,
        latency_class="slow",  # ~1.1s per query for ~30 candidates on CPU -- measured, see docs/EVALUATION/RAG_RESULTS.md
        cost_class="free",
        local_or_remote="LOCAL",
        hardware_requirements={"ram_mb": 300, "disk_mb": 100, "gpu_required": False},
        license="apache-2.0",
        revision=RERANKER_MODEL_REVISION,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["real query/passage cross-attention, not independently-encoded vectors", "no network dependency at inference time"]},
        known_weaknesses={"notes": ["~25x the latency of dense+lexical fusion alone on this CPU-only machine -- see docs/EVALUATION/RAG_RESULTS.md"]},
    ),
    dict(
        model_key="local_qwen2_5_1_5b_instruct_judge",
        provider="local_hf",
        source="huggingface",
        display_name="Qwen2.5-1.5B-Instruct (local, LLM Judge)",
        model_family="Qwen2.5",
        capabilities={"tasks": ["JUDGE", "GENERATION"]},
        parameter_count=1_500_000_000,
        context_window=32768,
        latency_class="slow",  # 30-90s per structured judgment on CPU -- measured, see docs/ALGORITHMS/LLM_JUDGE.md
        cost_class="free",
        local_or_remote="LOCAL",
        hardware_requirements={"ram_mb": 4000, "disk_mb": 3100, "gpu_required": False},
        license="apache-2.0",
        revision=JUDGE_MODEL_REVISION,
        availability_status="AVAILABLE",
        known_strengths={"notes": ["no API cost/quota", "no network dependency at inference time", "instruction-tuned, reliable structured JSON output once the prompt template bug was fixed"]},
        known_weaknesses={"notes": ["30-90s/call on this CPU-only machine -- not used in the live per-request Evaluation Suite, offline calibration/comparison only"]},
    ),
]


def seed() -> list[str]:
    seeded = []
    with session_scope() as session:
        for entry in _ENTRIES:
            existing = session.execute(
                select(ModelRegistryRecord).where(ModelRegistryRecord.model_key == entry["model_key"])
            ).scalar_one_or_none()
            if existing:
                for key, value in entry.items():
                    setattr(existing, key, value)
                seeded.append(existing.id)
            else:
                record = ModelRegistryRecord(id=new_id("model"), **entry)
                session.add(record)
                seeded.append(record.id)
    return seeded


if __name__ == "__main__":
    ids = seed()
    print(f"Seeded/updated {len(ids)} model_registry rows: {ids}")
